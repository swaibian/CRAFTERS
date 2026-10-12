"""SWE4 tests: agent loop with MockBrain + LlmClient parsing.

Positive: edit request → ops executed → observed → record ledger non-empty;
run.completed summary; done-call path. Live lane: MockBrain plans generically
from the CommandCatalog (no phrase→id table), command_run arg unwrapping
accepts double-wrapped envelopes, unknown-command errors gain nearest-id
suggestions, and brain_from_profile(live=True) advertises LIVE_APP_TOOLS
with the live system prompt.
Negative: empty message, no document open, unknown tool, oversized budget
stop; measured-without-evidence rejected; LlmError paths (auth/transport).
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from controller.agent import (
    MAX_ITERATIONS,
    AgentRun,
    _evidence_hint,
    _execute_live_call,
    brain_from_profile,
    run_agent_loop,
)
from controller.documents import (
    DocumentError,
    DocumentRegistry,
    PhotoAdapter,
    SheetAdapter,
)
from controller.llm import LlmClient, LlmError, LlmPlan, MockBrain, ToolCall
from controller.tests.test_commands import make_catalog


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


@pytest.mark.parametrize(
    ("message", "arguments"),
    [
        (
            "rotate the picture clockwise",
            {"command": "image.imageRotation.90cw"},
        ),
        ("rotate 90 clockwise", {"command": "image.imageRotation.90cw"}),
        (
            "make it black and white",
            {"command": "image.adjustments.blackWhite"},
        ),
        (
            "can you please make the picture black & white ?",
            {"command": "image.adjustments.blackWhite"},
        ),
        (
            "duplicate the layer",
            {"command": "layer.duplicate"},
        ),
    ],
)
def test_mockbrain_live_plans_from_catalog(message, arguments):
    """Live mode discovers ids from the catalog — no phrase→id table."""
    brain = MockBrain(catalog=make_catalog())
    plan = brain.plan(message, live=True)
    assert plan.mock is True and plan.model == "mock"
    assert plan.tool_calls and plan.tool_calls[0].name == "command_run"
    assert plan.tool_calls[0].arguments == arguments


def test_mockbrain_live_blend_mode_params_from_schema():
    """Blend modes are PARAM VALUES of one layer command, inferred from schema."""
    brain = MockBrain(catalog=make_catalog())
    plan = brain.plan("set the layer blend mode to multiply", live=True)
    call = plan.tool_calls[0]
    assert call.name == "command_run"
    assert call.arguments["command"] in {
        "layer.setProps",
        "layer.layerStyle.blendingOptions",
    }
    assert "Multiply" in call.arguments.get("params", {}).values()


def test_mockbrain_live_no_catalog_plans_command_list():
    """No catalog (or no match) → discovery call for the top keyword."""
    brain = MockBrain()
    plan = brain.plan("make it black and white", live=True)
    assert plan.tool_calls[0].name == "command_list"
    assert plan.tool_calls[0].arguments == {"filter": "black"}
    blind = MockBrain(catalog=make_catalog())
    unmatchable = blind.plan("frobnicate the widget", live=True)
    assert unmatchable.tool_calls[0].name == "command_list"
    assert unmatchable.tool_calls[0].arguments == {"filter": "frobnicate"}


def test_mockbrain_live_save_and_done():
    brain = MockBrain(catalog=make_catalog())
    save_plan = brain.plan("please save the document", live=True)
    assert save_plan.tool_calls[0].name == "doc_save"
    other = brain.plan("do it", live=True)
    assert other.tool_calls[0].name == "done"
    assert other.tool_calls[0].arguments["summary"]
    followup = brain.plan(
        "Done so far: Ran image.imageRotation.90cw in the open app. "
        "Original request: rotate the picture clockwise.",
        live=True,
    )
    assert followup.tool_calls[0].name == "done"


def test_mockbrain_adapter_mode_unchanged_for_live_phrasing():
    """Adapter planning is untouched: live phrasing still maps to adapters."""
    brain = MockBrain()
    plan = brain.plan("rotate the picture clockwise", doc_kind="photo")
    assert plan.tool_calls[0].name == "photo.transform"


# --- command_run arg normalization -------------------------------------------


class _RecordingExecutor:
    """Minimal live-executor stand-in recording command_run round trips."""

    app = "photocraft"

    def __init__(self, error=None):
        self.calls = []
        self._error = error

    async def execute(self, command, params=None):
        if self._error is not None:
            raise self._error
        self.calls.append((command, params))
        return {}

    async def commands(self, filter=None):
        return {"commands": []}

    async def inspect(self):
        return {}

    async def look(self):
        return b"fake-png-bytes"

    async def save(self, path=None):
        return {"path": path or "own.psd"}


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"command": "x"}, ("x", {})),
        ({"id": "x"}, ("x", {})),
        ({"command": "x", "params": {"a": 1}}, ("x", {"a": 1})),
        ({"id": "x", "params": {"a": 1}}, ("x", {"a": 1})),
        ({"command": {"command": "x", "params": {"a": 1}}}, ("x", {"a": 1})),
        ({"command": {"id": "x"}}, ("x", {})),
        ({"id": {"command": "x", "params": {"a": 1}}}, ("x", {"a": 1})),
        ({"command": '{"command": "x"}'}, ("x", {})),
        ({"command": '{"id": "x", "params": {"a": 1}}'}, ("x", {"a": 1})),
        ({"id": '{"command": "x"}'}, ("x", {})),
        ({"command": {"command": {"id": "x"}}}, ("x", {})),
        (
            {"command": {"command": "x", "params": {"a": 1}}, "params": {"b": 2}},
            ("x", {"a": 1}),
        ),
    ],
)
async def test_command_run_arg_unwrap_matrix(arguments, expected):
    """command_run accepts command/id keys and unwraps nested/JSON envelopes."""
    executor = _RecordingExecutor()
    await _execute_live_call(
        ToolCall(name="command_run", arguments=dict(arguments), call_id="mock_1"),
        executor,
    )
    assert executor.calls == [expected]


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"command": "not an id!"},
        {"command": {"foo": 1}},
        {"command": 5},
        {"command": '{"command": '},
        {"id": "x y"},
    ],
)
async def test_command_run_arg_unwrap_garbage_clear_error(arguments):
    """Garbage ids fail with one clear hint, never an app-side wall."""
    executor = _RecordingExecutor()
    with pytest.raises(DocumentError) as excinfo:
        await _execute_live_call(
            ToolCall(name="command_run", arguments=dict(arguments), call_id="mock_1"),
            executor,
        )
    message = str(excinfo.value)
    assert "bare command id" in message
    assert "image.imageRotation.90cw" in message
    assert "command_list" in message


# --- command_list client-side filtering --------------------------------------


class _ListAllExecutor(_RecordingExecutor):
    """Executor whose engine.commands IGNORES the filter (like the desktop)."""

    REGISTRY: ClassVar[list] = [
        {"id": "app.new", "label": "New"},
        {"id": "image.imageRotation.90cw", "label": "90° Clockwise"},
        {"id": "image.imageRotation.90ccw", "label": "90° Counter Clockwise"},
        {"id": "image.adjustments.desaturate", "label": "Desaturate"},
        {"id": "image.adjustments.blackWhite", "label": "Black & White"},
        {"id": "layer.duplicate", "label": "Duplicate Layer"},
    ]

    async def commands(self, filter=None):
        return {"commands": list(self.REGISTRY)}  # never filters server-side


@pytest.mark.asyncio()
async def test_command_list_filters_client_side_desktop_ignores_filter():
    """Desktop engine.commands returns the WHOLE registry even with a
    filter (it ignores the param) — the tool layer must filter, or the
    planner re-lists 818 entries forever (tonight's transcript bug)."""
    executor = _ListAllExecutor()
    evidence = await _execute_live_call(
        ToolCall(name="command_list", arguments={"filter": "rotate"}, call_id="mock_1"),
        executor,
    )
    ids = [e["id"] for e in evidence["entries"]]
    assert "image.imageRotation.90cw" in ids
    assert "image.imageRotation.90ccw" in ids
    assert "layer.duplicate" not in ids
    assert evidence["count"] == len(ids)  # matched, not 6
    assert evidence["total"] == 6  # registry size still reported
    assert evidence["filter"] == "rotate"


@pytest.mark.asyncio()
async def test_command_list_without_filter_returns_whole_registry():
    executor = _ListAllExecutor()
    evidence = await _execute_live_call(
        ToolCall(name="command_list", arguments={}, call_id="mock_1"),
        executor,
    )
    assert evidence["count"] == evidence["total"] == 6
    assert evidence["filter"] == ""


@pytest.mark.asyncio()
async def test_command_list_carries_params_schema_for_the_planner():
    """The planner must learn HOW to call an id (curves takes
    {"points": [[in,out],…]}) — without the schema it cannot form a
    highlight-reducing curve from 'the faces are too bright'."""
    executor = _ListAllExecutor()
    executor.REGISTRY = [  # type: ignore[misc]
        {
            "id": "image.adjustments.curves",
            "label": "Curves…",
            "params": '{"points":json} (curves as [[in,out],…] in 0..255, 2..19 points)',
        }
    ]
    evidence = await _execute_live_call(
        ToolCall(name="command_list", arguments={"filter": "curves"}, call_id="mock_1"),
        executor,
    )
    entry = evidence["entries"][0]
    assert entry["id"] == "image.adjustments.curves"
    assert "points" in entry["params"]
    hint = _evidence_hint(evidence)
    assert "points" in hint
    assert "command_run" in hint


@pytest.mark.asyncio()
async def test_command_list_empty_match_is_honest():
    executor = _ListAllExecutor()
    evidence = await _execute_live_call(
        ToolCall(
            name="command_list", arguments={"filter": "frobnicate"}, call_id="mock_1"
        ),
        executor,
    )
    assert evidence["entries"] == []
    assert evidence["count"] == 0
    hint = _evidence_hint(evidence)
    assert "No commands match filter 'frobnicate'" in hint


# --- unknown-command suggestions ---------------------------------------------


@pytest.mark.asyncio()
async def test_unknown_command_error_suggests_nearest_ids(tmp_path):
    from controller.live import LiveError

    def _plan(message, kind):
        return LlmPlan(
            text="",
            tool_calls=[
                ToolCall(
                    name="command_run",
                    arguments={"command": "image.adjustments.desatur"},
                    call_id="mock_1",
                )
            ],
            mock=True,
            model="mock",
        )

    executor = _RecordingExecutor(
        error=LiveError(
            "engine.execute failed: unknown command `image.adjustments.desatur`"
        )
    )
    events = [
        event
        async for event in run_agent_loop(
            "make it desaturated",
            doc_id=None,
            registry=DocumentRegistry(tmp_path / "work"),
            plan_fn=_plan,
            executor=executor,
            live_app="photocraft",
            catalog=make_catalog(),
        )
    ]
    results = [e for e in events if e["type"] == "tool.result"]
    assert results[0]["ok"] is False
    error = results[0]["error"]
    assert "did you mean: " in error
    assert "image.adjustments.desaturate" in error
    assert "command_list to discover ids" in error


# --- verification loop (observe → reason → stop) ------------------------------


class _StatefulExecutor(_RecordingExecutor):
    """Executor whose inspect() reflects how many edits landed."""

    def __init__(self):
        super().__init__()
        self.history = ["open"]
        self.rotated = 0

    async def execute(self, command, params=None):
        self.calls.append((command, params))
        if command != "document.inspect":
            self.history.append(command)
            if "Rotation" in command:
                self.rotated += 1
        return {}

    async def inspect(self):
        width, height = 48, 32
        if self.rotated % 2 == 1:
            width, height = 32, 48
        return {
            "width": width,
            "height": height,
            "layers": [{"name": "Background", "kind": "raster", "opacity": 100}],
            "history": [{"name": h} for h in self.history],
        }


def _fixed_plan(*calls):
    """plan_fn returning the given calls as one batch, then done."""

    batch = list(calls)

    def _plan(message, kind):
        if message.startswith("Done so far:"):
            return LlmPlan(
                text="",
                tool_calls=[
                    ToolCall(
                        name="done",
                        arguments={"summary": "Done."},
                        call_id="mock_done",
                    )
                ],
                mock=True,
                model="mock",
            )
        if batch:
            taken = list(batch)
            batch.clear()
            return LlmPlan(text="on it", tool_calls=taken, mock=True, model="mock")
        return LlmPlan(
            text="",
            tool_calls=[
                ToolCall(
                    name="done",
                    arguments={"summary": "Done."},
                    call_id="mock_done",
                )
            ],
            mock=True,
            model="mock",
        )

    return _plan


@pytest.mark.asyncio()
async def test_repeated_mutation_across_look_is_refused(tmp_path):
    """rotate → look → rotate: the second rotate must NOT run (was the
    triple-rotate bug — the guard only caught consecutive repeats)."""
    from controller.live import LiveError  # noqa: F401  (import sanity)

    executor = _StatefulExecutor()
    rotate = ToolCall(
        name="command_run",
        arguments={"command": "image.imageRotation.90cw"},
        call_id="mock_r1",
    )
    look = ToolCall(name="look", arguments={}, call_id="mock_l1")
    events = [
        event
        async for event in run_agent_loop(
            "rotate the picture clockwise",
            doc_id=None,
            registry=DocumentRegistry(tmp_path / "work"),
            plan_fn=_fixed_plan(rotate, look, rotate),
            executor=executor,
            live_app="photocraft",
        )
    ]
    rotates = [c for c in executor.calls if c[0] != "document.inspect"]
    assert rotates == [("image.imageRotation.90cw", {})], rotates
    results = [e for e in events if e["type"] == "tool.result"]
    assert results[0]["ok"] is True
    assert results[-1]["ok"] is False
    assert "already applied earlier in this run" in results[-1]["error"]
    assert "apply the change twice" in results[-1]["error"]
    assert "earlier application stands" in events[-1]["summary"]


@pytest.mark.asyncio()
async def test_followup_prompt_carries_state_and_change_verdict(tmp_path):
    """The planner must SEE that the edit landed — the blind 'I'll verify'
    loop re-ran edits because nothing reported the new state."""
    seen_messages: list[str] = []
    executor = _StatefulExecutor()

    def _plan(message, kind):
        seen_messages.append(message)
        if message.startswith("Done so far:"):
            return LlmPlan(
                text="",
                tool_calls=[
                    ToolCall(
                        name="done", arguments={"summary": "Done."}, call_id="mock_done"
                    )
                ],
                mock=True,
                model="mock",
            )
        return LlmPlan(
            text="",
            tool_calls=[
                ToolCall(
                    name="command_run",
                    arguments={"command": "image.imageRotation.90cw"},
                    call_id="mock_r",
                )
            ],
            mock=True,
            model="mock",
        )

    events = [
        event
        async for event in run_agent_loop(
            "rotate the picture clockwise",
            doc_id=None,
            registry=DocumentRegistry(tmp_path / "work"),
            plan_fn=_plan,
            executor=executor,
            live_app="photocraft",
        )
    ]
    followup = seen_messages[-1]
    assert followup.startswith("Done so far:")
    assert "Ran image.imageRotation.90cw" in followup
    assert "Current document state:" in followup
    assert "32x48 px" in followup  # dims swapped = the rotation landed
    assert "history 2" in followup
    assert "satisfies the request" in followup
    assert events[-1]["type"] == "run.completed"


@pytest.mark.asyncio()
async def test_observe_reports_change_between_steps(tmp_path):
    """observe events carry the changed verdict (True after an edit)."""
    executor = _StatefulExecutor()
    events = [
        event
        async for event in run_agent_loop(
            "rotate the picture clockwise",
            doc_id=None,
            registry=DocumentRegistry(tmp_path / "work"),
            plan_fn=_fixed_plan(
                ToolCall(
                    name="command_run",
                    arguments={"command": "image.imageRotation.90cw"},
                    call_id="mock_r",
                ),
                ToolCall(name="doc_inspect", arguments={}, call_id="mock_i"),
            ),
            executor=executor,
            live_app="photocraft",
        )
    ]
    observes = [e for e in events if e["type"] == "observe"]
    # Baseline before the first edit → the first observe can PROVE the
    # rotation landed (dims swapped), the read-only inspect after it
    # correctly reports "unchanged".
    assert observes[0]["changed"] is True
    assert observes[1]["changed"] is False


def test_brain_from_profile_live_uses_live_tools(monkeypatch):
    """live=True advertises LIVE_APP_TOOLS and the live system prompt."""
    import httpx

    from controller.llm import AGENT_TOOLS, LIVE_APP_TOOLS

    seen: dict = {}

    def _fake_post(url, headers=None, json=None, timeout=None):
        seen["tools"] = json["tools"]
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
        default_model = "m"

    plan_fn, model_name, is_mock = brain_from_profile(
        _Profile(), live=True, live_app="photocraft"
    )
    assert is_mock is False and model_name == "m"
    plan_fn("rotate the picture clockwise", "photo")
    assert seen["tools"] is LIVE_APP_TOOLS
    assert "photocraft" in seen["system"]
    assert "command surface" in seen["system"]
    assert "doc_save ONLY" in seen["system"]

    # Headless lane keeps the adapter prompt + adapter tools.
    headless_fn, _, _ = brain_from_profile(_Profile())
    headless_fn("hi", "photo")
    assert seen["tools"] is AGENT_TOOLS
    assert "open document copy" in seen["system"]

    # The no-key path plans live commands generically from the catalog.
    mock_fn, mock_model, mock_flag = brain_from_profile(
        None, MockBrain(catalog=make_catalog()), live=True
    )
    assert mock_flag is True and mock_model == "mock"
    plan = mock_fn("rotate the picture clockwise", "photo")
    assert plan.tool_calls[0].name == "command_run"
    assert plan.tool_calls[0].arguments == {"command": "image.imageRotation.90cw"}


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


def test_agent_iteration_budget_defaults_to_32():
    assert MAX_ITERATIONS == 32
    assert AgentRun(run_id="run_x", session_id="s").max_iterations == 32


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
