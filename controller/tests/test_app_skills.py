"""Provider-bound regression checks for app knowledge and tool feedback."""

import copy

import pytest

from controller.agent import (
    _execute_live_call,
    _live_detail,
    brain_from_profile,
    run_agent_loop,
)
from controller.app_skills import app_skill
from controller.documents import DocumentRegistry
from controller.llm import LlmClient, LlmPlan, ToolCall


def test_app_guides_are_distinct_and_path_safe():
    assert '"ellipse": true' in app_skill("photocraft")
    assert "cell.set" in app_skill("gridcraft")
    assert app_skill("../settings.local.json") == ""


def test_provider_receives_skill_history_tools_and_real_image(monkeypatch):
    from types import SimpleNamespace

    requests = []
    calls = [ToolCall("look", {}, "look_1"), ToolCall("doc_inspect", {}, "inspect_1")]

    def chat(self, messages, **kwargs):
        requests.append(copy.deepcopy(messages))
        return LlmPlan(tool_calls=calls if len(requests) == 1 else [ToolCall("done", {"summary": "done"}, "done_1")])

    monkeypatch.setattr(LlmClient, "chat", chat)
    plan, _, _ = brain_from_profile(
        SimpleNamespace(api_key="test", api_base="http://example.invalid", default_model="test"),
        live=True, live_app="photocraft",
        history=[{"role": "assistant", "text": "Created Background copy, layer 7."}],
    )
    plan("Circle the people", "photo")
    plan.tool_result(calls[0], {"image_url": "data:image/png;base64,aGVsbG8=", "bytes": 5}, True, "")
    plan.tool_result(calls[1], {"detail": {"activeLayer": 7}}, True, "")
    plan("Continue", "photo")
    first, second = requests
    assert "PhotoCraft operating skill" in first[0]["content"]
    assert any("layer 7" in str(m["content"]) for m in first)
    results = [m for m in second if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in results] == ["look_1", "inspect_1"]
    assert '"activeLayer": 7' in results[1]["content"]
    image_index = next(i for i, m in enumerate(second) if isinstance(m.get("content"), list))
    assert second[image_index]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert second[image_index - 1]["tool_call_id"] == "inspect_1"


def test_inspection_preserves_targets_selection_and_units():
    detail = _live_detail({
        "activeLayer": 7, "selectedLayers": [7], "revision": 12,
        "hasSelection": True, "selectionBounds": [10, 20, 40, 40],
        "layers": [{"id": 7, "name": "Copy", "opacity": 1.0, "blend": "Screen", "bounds": [0, 0, 100, 100]}],
    })
    assert detail["activeLayer"] == 7
    assert detail["layer_tree"][0]["id"] == 7
    assert detail["selectionBounds"] == [10, 20, 40, 40]
    assert "100%" in detail["layer_summary"][0]


@pytest.mark.asyncio
async def test_discovery_preserves_ranking_and_full_contract():
    entries = [
        {"id": "other.command", "label": "Misc", "params": '{"curves": true}', "enabled": False},
        {"id": "image.adjustments.curves", "label": "Curves", "params": "x" * 200, "enabled": True},
    ]

    class Executor:
        async def commands(self, filter=None):
            return {"commands": entries}

    result = await _execute_live_call(ToolCall("command_list", {"filter": "curves"}), Executor())
    assert result["entries"][0]["id"] == "image.adjustments.curves"
    assert len(result["entries"][0]["params"]) == 200
    assert result["entries"][1]["enabled"] is False
    contract = await _execute_live_call(ToolCall("command_describe", {"command": "image.adjustments.curves"}), Executor())
    assert contract["entries"][0] == entries[1]


@pytest.mark.asyncio
async def test_alternating_discovery_stops_with_blocked_outcome(tmp_path):
    class Executor:
        app = "photocraft"

        async def inspect(self):
            return {"revision": 1, "layers": []}

        async def commands(self, filter=None):
            return {"commands": []}

    count = 0

    def plan(message, kind):
        nonlocal count
        count += 1
        return LlmPlan(tool_calls=[ToolCall("doc_inspect" if count % 2 else "command_list", {} )])

    events = [event async for event in run_agent_loop(
        "circle", doc_id=None, registry=DocumentRegistry(tmp_path),
        plan_fn=plan, executor=Executor(),
    )]
    assert events[-1]["outcome"] == "blocked"
    assert events[-1]["iterations"] < 10


@pytest.mark.asyncio
async def test_provider_can_correct_a_rejected_command(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from controller.live import LiveError

    requests = []

    def chat(self, messages, **kwargs):
        requests.append(copy.deepcopy(messages))
        if len(requests) == 1:
            return LlmPlan(tool_calls=[ToolCall("command_run", {"command": "layer.setProps", "params": {"blend": "scren"}}, "bad")])
        if len(requests) == 2:
            return LlmPlan(tool_calls=[ToolCall("command_run", {"command": "layer.setProps", "params": {"blend": "Screen"}}, "fixed")])
        return LlmPlan(tool_calls=[ToolCall("done", {"summary": "Set Screen"}, "done")])

    class Executor:
        app = "photocraft"
        blend = "Normal"

        async def inspect(self):
            return {"revision": int(self.blend == "Screen"), "layers": [{"id": 1, "blend": self.blend}]}

        async def execute(self, command, params):
            if params["blend"] == "scren":
                raise LiveError("unknown blend mode scren")
            self.blend = params["blend"]
            return {"layer": 1}

    monkeypatch.setattr(LlmClient, "chat", chat)
    planner, model, mock = brain_from_profile(
        SimpleNamespace(api_key="test", api_base="http://example.invalid", default_model="test"),
        live=True, live_app="photocraft",
    )
    executor = Executor()
    events = [event async for event in run_agent_loop(
        "set Screen", doc_id=None, registry=DocumentRegistry(tmp_path), plan_fn=planner,
        model_name=model, is_mock=mock, executor=executor,
    )]
    assert executor.blend == "Screen"
    assert events[-1]["outcome"] == "succeeded"
    assert any('unknown blend mode scren' in m.get("content", "") for m in requests[1] if m["role"] == "tool")
