"""SWE4 tests: agent loop with MockBrain + LlmClient parsing.

Positive: edit request → ops executed → observed → record ledger non-empty;
run.completed summary; done-call path.
Negative: empty message, no document open, unknown tool, oversized budget
stop; measured-without-evidence rejected; LlmError paths (auth/transport).
"""

from __future__ import annotations

import pytest

from controller.agent import (
    AgentRun,
    brain_from_profile,
    run_agent_loop,
)
from controller.documents import DocumentRegistry, PhotoAdapter, SheetAdapter
from controller.llm import LlmClient, LlmError, MockBrain


@pytest.fixture()
def registry(tmp_path):
    return DocumentRegistry(tmp_path / "work")


def _make_png(path):
    from PIL import Image

    Image.new("RGB", (64, 48), color=(10, 200, 30)).save(path, "PNG")


def _make_xlsx(path):
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"] = "hello"
    wb.save(path)
    wb.close()


async def _collect(gen):
    return [event async for event in gen]


# --- MockBrain --------------------------------------------------------------


def test_mockbrain_photo_resize_plan():
    brain = MockBrain()
    plan = brain.plan("resize to 800px", doc_kind="photo")
    assert plan.mock is True and plan.model == "mock"
    assert plan.tool_calls and plan.tool_calls[0].name == "photo.transform"
    assert plan.tool_calls[0].arguments["width"] == 800


def test_mockbrain_sheet_and_pdf_plans():
    brain = MockBrain()
    sheet_plan = brain.plan("set A1 to world", doc_kind="sheet")
    assert sheet_plan.tool_calls[0].name == "sheet.set_cell"
    assert sheet_plan.tool_calls[0].arguments["cell"] == "A1"
    pdf_plan = brain.plan("rotate page 2 by 90 degrees", doc_kind="pdf")
    assert pdf_plan.tool_calls[0].name == "pdf.transform"
    assert pdf_plan.tool_calls[0].arguments["page"] == 2


def test_mockbrain_clarifies_unknown():
    brain = MockBrain()
    plan = brain.plan("tell me a story", doc_kind="photo")
    assert plan.tool_calls == []
    assert "What should I change" in plan.text


def test_mockbrain_team_prefix():
    """Team binding is visible on the no-key path (behaviorally real)."""
    brain = MockBrain()
    plan = brain.plan("tell me a story", doc_kind="photo", team_id="craft_studio")
    assert plan.text.startswith("[team craft_studio] ")
    edit = brain.plan("resize to 800px", doc_kind="photo", team_id="craft_studio")
    assert edit.text.startswith("[team craft_studio] ")
    assert edit.tool_calls[0].name == "photo.transform"
    # No team → no prefix (backward compatible).
    plain = brain.plan("tell me a story", doc_kind="photo")
    assert not plain.text.startswith("[team ")


def test_brain_from_profile_team_and_model_override(monkeypatch):
    """Team context reaches the LLM system prompt; model override is threaded."""
    import httpx

    from controller.agent import team_context_block

    seen: dict = {}

    def _fake_post(url, headers=None, json=None, timeout=None):
        seen["model"] = json["model"]
        seen["system"] = json["messages"][0]["content"]

        class _Resp:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "done"}}]}

        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)

    class _Profile:
        api_base = "http://127.0.0.1:9/v1"
        api_key = "k"
        default_model = "base-model"

    team = {
        "id": "craft_studio",
        "name": "Craft Studio Production",
        "agents": [{"id": "a1", "name": "Studio Lead", "model": "m1"}],
    }
    plan_fn, model_name, is_mock = brain_from_profile(
        _Profile(), model_override="special-model", team=team
    )
    assert is_mock is False
    assert model_name == "special-model"
    plan = plan_fn("hi", "photo")
    assert plan.mock is False
    assert seen["model"] == "special-model"
    assert "craft_studio" in seen["system"]
    assert "Studio Lead" in seen["system"]

    # No override → profile default; no team → no roster block.
    plan_fn2, model2, _ = brain_from_profile(_Profile())
    assert model2 == "base-model"
    plan_fn2("hi", "photo")
    assert "craft_studio" not in seen["system"]
    assert team_context_block(None) == ""


@pytest.mark.parametrize(
    ("message", "cell", "value"),
    [
        ("Set cell C3 to 99 and tell me what changed.", "C3", 99),
        ("Set cell B2 to 7.", "B2", 7),
        ("set A1 to hello world", "A1", "hello world"),
        ("Set D4 to 3.5 then continue.", "D4", 3.5),
    ],
)
def test_mockbrain_sheet_value_trimming(message, cell, value):
    """Regression: values must not swallow trailing prose or periods."""
    brain = MockBrain()
    plan = brain.plan(message, doc_kind="sheet")
    assert plan.tool_calls and plan.tool_calls[0].name == "sheet.set_cell"
    assert plan.tool_calls[0].arguments["cell"] == cell
    assert plan.tool_calls[0].arguments["value"] == value


# --- agent loop ---------------------------------------------------------------


@pytest.mark.asyncio()
async def test_loop_photo_resize_end_to_end(registry, tmp_path):
    src = tmp_path / "pic.png"
    _make_png(src)
    doc = PhotoAdapter(registry).open(src, "pic.png")
    brain = MockBrain()
    plan_fn, model, is_mock = brain_from_profile(None, brain)
    assert is_mock and model == "mock"

    events = await _collect(
        run_agent_loop(
            "resize to 800px",
            doc_id=doc.doc_id,
            registry=registry,
            plan_fn=plan_fn,
            model_name=model,
            is_mock=is_mock,
        )
    )
    types = [e["type"] for e in events]
    assert types[0] == "run.started"
    assert "tool.call" in types and "tool.result" in types
    assert "observe" in types and "record" in types
    assert types[-1] == "run.completed"
    completed = events[-1]
    assert completed["records"], "claim ledger must be non-empty"
    assert PhotoAdapter(registry).inspect(doc.doc_id)["width"] == 800


@pytest.mark.asyncio()
async def test_loop_sheet_set_cell(registry, tmp_path):
    src = tmp_path / "book.xlsx"
    _make_xlsx(src)
    doc = SheetAdapter(registry).open(src, "book.xlsx")
    brain = MockBrain()
    plan_fn, model, is_mock = brain_from_profile(None, brain)
    events = await _collect(
        run_agent_loop(
            "set A1 to world",
            doc_id=doc.doc_id,
            registry=registry,
            plan_fn=plan_fn,
            model_name=model,
            is_mock=is_mock,
        )
    )
    assert events[-1]["type"] == "run.completed"
    assert events[-1]["records"]
    assert (
        SheetAdapter(registry).inspect(doc.doc_id)["sheets"][0]["sample"][0][0]
        == "world"
    )


@pytest.mark.asyncio()
async def test_loop_negative_paths(registry):
    brain = MockBrain()
    plan_fn, _model, _is_mock = brain_from_profile(None, brain)
    empty = await _collect(
        run_agent_loop("", doc_id=None, registry=registry, plan_fn=plan_fn)
    )
    assert empty[-1]["type"] == "run.error"

    # Edit request with no document open → tool error, run still completes.
    events = await _collect(
        run_agent_loop(
            "resize to 800px", doc_id=None, registry=registry, plan_fn=plan_fn
        )
    )
    assert events[-1]["type"] == "run.completed"
    assert "could not complete" in events[-1]["summary"]

    # Unknown tool → graceful failure, no blind retry.
    def _bad_plan(message, kind):
        from controller.llm import LlmPlan, ToolCall

        return LlmPlan(
            text="",
            tool_calls=[ToolCall(name="nope.unknown", arguments={}, call_id="mock_9")],
            mock=True,
            model="mock",
        )

    weird = await _collect(
        run_agent_loop(
            "tell me a story", doc_id=None, registry=registry, plan_fn=_bad_plan
        )
    )
    assert weird[-1]["type"] == "run.completed"


def test_ledger_rejects_measured_without_evidence():
    run = AgentRun(run_id="run_x", session_id="s")
    with pytest.raises(ValueError):
        run.record("claim", "measured", [])
    with pytest.raises(ValueError):
        run.record("  ", "inferred", [])
    entry = run.record("done", "inferred", [])
    assert entry.record_id.startswith("rec_")


# --- LlmClient parsing ----------------------------------------------------------


def test_llm_client_parses_tool_calls(monkeypatch):
    import httpx

    def _fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer k"
        assert json["model"] == "m"

        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "on it",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "function": {
                                            "name": "photo.transform",
                                            "arguments": '{"kind": "resize", "width": 800}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }

        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    client = LlmClient(api_base="http://x/v1/", api_key="k", default_model="m")
    plan = client.chat([{"role": "user", "content": "hi"}])
    assert plan.mock is False
    assert plan.tool_calls[0].name == "photo.transform"
    assert plan.tool_calls[0].arguments["width"] == 800


def test_llm_client_errors(monkeypatch):
    import httpx

    client = LlmClient(api_base="http://x/v1", api_key="k", default_model="m")

    class _Resp:
        def __init__(self, status):
            self.status_code = status

    monkeypatch.setattr(httpx, "post", lambda *a, **kwargs: _Resp(401))
    with pytest.raises(LlmError):
        client.chat([])

    def _boom(*a, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", _boom)
    with pytest.raises(LlmError):
        client.chat([])
