"""SWE4 unit tests for gateway/perception.py (SWE3-C-01).

Positive: doc/screen round-trip; canvas-rect synthesis; widget filters
(query/role/focused/limit+truncated); canned AccessKit shape;
query_map put/get; full register_perception_tools wiring.
Negative: unknown app/direction; bad zoom/canvas/point shapes; allowlist
denial; widget text (label/value/description) never reaches logs.
"""

from __future__ import annotations

import logging

import pytest
from fastmcp.exceptions import ToolError

from gateway.auth import AuthStore, TokenRecord
from gateway.backends import BackendManager, SessionRegistry
from gateway.perception import (
    PerceptionTools,
    QueryMap,
    doc_to_screen,
    filter_widgets,
    redact_widgets,
    register_perception_tools,
    screen_to_doc,
    synthesize_canvas_rect,
)

FULL_TOKEN = "perception-full-token"
BOGUS_TOKEN = "bogus-token"


@pytest.fixture()
def setup(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = AuthStore()
    store.register(
        FULL_TOKEN,
        TokenRecord(
            key_id="key_full",
            user_id="op",
            allowlist=frozenset({"craft_widgets", "craft_map"}),
        ),
    )
    manager = BackendManager(use_fake=True)
    sessions = SessionRegistry(default_roots=[work])
    sessions.create("s1", "op", key_id="key_full")
    impl = PerceptionTools(manager, sessions, store)
    return impl, manager, sessions, store


# --- coordinate math ---


def test_doc_screen_round_trip() -> None:
    doc = (120.0, 80.0)
    screen = doc_to_screen(doc, zoom=2.0, centre=(100.0, 100.0), view_size=(800, 600))
    assert screen == pytest.approx(((120 - 100) * 2 + 400, (80 - 100) * 2 + 300))
    back = screen_to_doc(screen, zoom=2.0, centre=(100.0, 100.0), view_size=(800, 600))
    assert back == pytest.approx(doc)


def test_centre_maps_to_view_centre() -> None:
    assert doc_to_screen(
        (50, 50), zoom=1.5, centre=(50, 50), view_size=(800, 600)
    ) == pytest.approx((400.0, 300.0))


@pytest.mark.parametrize("bad_zoom", [0.0, -1.0])
def test_bad_zoom_rejected(bad_zoom: float) -> None:
    with pytest.raises(ValueError, match="zoom must be positive"):
        doc_to_screen((0, 0), zoom=bad_zoom, centre=(0, 0), view_size=(8, 8))
    with pytest.raises(ValueError, match="zoom must be positive"):
        screen_to_doc((0, 0), zoom=bad_zoom, centre=(0, 0), view_size=(8, 8))
    with pytest.raises(ValueError, match="zoom must be positive"):
        synthesize_canvas_rect(
            zoom=bad_zoom, centre=(0, 0), canvas_size=(10, 10), view_size=(8, 8)
        )


def test_bad_canvas_size_rejected() -> None:
    with pytest.raises(ValueError, match="canvas_size must be positive"):
        synthesize_canvas_rect(
            zoom=1.0, centre=(0, 0), canvas_size=(0, 10), view_size=(8, 8)
        )


def test_synthesize_canvas_rect() -> None:
    rect = synthesize_canvas_rect(
        zoom=2.0,
        centre=(100.0, 100.0),
        canvas_size=(200.0, 100.0),
        view_size=(800.0, 600.0),
    )
    assert rect["w"] == pytest.approx(400.0)
    assert rect["h"] == pytest.approx(200.0)
    assert (rect["x"], rect["y"]) == pytest.approx(
        doc_to_screen((0, 0), zoom=2.0, centre=(100.0, 100.0), view_size=(800, 600))
    )


# --- widget filters ---


def _widgets():
    return [
        {"id": "a", "role": "button", "label": "Save File", "focused": True},
        {"id": "b", "role": "list", "label": "Layers", "focused": False},
        {"id": "c", "role": "button", "label": "Export", "focused": False},
    ]


def test_filter_query() -> None:
    kept, truncated = filter_widgets(_widgets(), query="save")
    assert [w["id"] for w in kept] == ["a"]
    assert truncated is False


def test_filter_role() -> None:
    kept, _ = filter_widgets(_widgets(), role="button")
    assert [w["id"] for w in kept] == ["a", "c"]


def test_filter_focused() -> None:
    kept, _ = filter_widgets(_widgets(), focused=True)
    assert [w["id"] for w in kept] == ["a"]


def test_filter_limit_truncates() -> None:
    kept, truncated = filter_widgets(_widgets(), limit=2)
    assert len(kept) == 2
    assert truncated is True


def test_redact_widgets_drops_text() -> None:
    raw = [
        {
            "id": "a",
            "role": "button",
            "label": "Secret Doc Name",
            "value": "pii@example.com",
            "description": "private note",
            "rect": [0, 0, 10, 10],
            "enabled": True,
            "focused": False,
        }
    ]
    (scrubbed,) = redact_widgets(raw)
    assert scrubbed["id"] == "a"
    assert scrubbed["has_rect"] is True
    for forbidden in ("Secret Doc Name", "pii@example.com", "private note"):
        assert forbidden not in str(scrubbed)
    assert "label" not in scrubbed and "value" not in scrubbed


# --- tools ---


@pytest.mark.asyncio()
async def test_widgets_happy_path(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_widgets(
        app="pdfcraft", user_id="op", session_id="s1", raw_token=FULL_TOKEN
    )
    assert result["app"] == "pdfcraft"
    assert result["count"] == 3
    assert result["truncated"] is False
    assert len(result["query_map_ids"]) == 3
    roles = {w["role"] for w in result["widgets"]}
    assert roles == {"button", "list"}


@pytest.mark.asyncio()
async def test_widgets_filters(setup) -> None:
    impl, *_ = setup
    result = await impl.craft_widgets(
        app="pdfcraft",
        role="button",
        user_id="op",
        session_id="s1",
        raw_token=FULL_TOKEN,
    )
    assert result["count"] == 2
    result = await impl.craft_widgets(
        app="pdfcraft",
        query="layers",
        user_id="op",
        session_id="s1",
        raw_token=FULL_TOKEN,
    )
    assert result["count"] == 1


@pytest.mark.asyncio()
async def test_widgets_unknown_app(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="unknown app"):
        await impl.craft_widgets(
            app="nosuchcraft", user_id="op", session_id="s1", raw_token=FULL_TOKEN
        )


@pytest.mark.asyncio()
async def test_widgets_allowlist_denial(setup) -> None:
    impl, _, _, _store = setup
    with pytest.raises(ToolError, match="access denied"):
        await impl.craft_widgets(
            app="pdfcraft", user_id="op", session_id="s1", raw_token=BOGUS_TOKEN
        )
    limited = AuthStore()
    limited.register(
        "limited",
        TokenRecord(key_id="k", user_id="v", allowlist=frozenset({"craft_map"})),
    )
    impl2 = PerceptionTools(impl._backends, impl._sessions, limited)
    with pytest.raises(ToolError, match="access denied"):
        await impl2.craft_widgets(
            app="pdfcraft", user_id="v", session_id="s1", raw_token="limited"
        )


@pytest.mark.asyncio()
async def test_widgets_logs_carry_no_text(setup, caplog) -> None:
    """Widget label/value/description (potential PII) never reach logs."""
    impl, *_ = setup
    with caplog.at_level(logging.INFO):
        await impl.craft_widgets(
            app="pdfcraft", user_id="op", session_id="s1", raw_token=FULL_TOKEN
        )
    text = "\n".join(f"{r.name} {r.getMessage()} {r.args}" for r in caplog.records)
    assert "Save the current document" not in text
    assert "Document layer list" not in text
    assert FULL_TOKEN not in text


@pytest.mark.asyncio()
async def test_map_point_round_trip(setup) -> None:
    impl, *_ = setup
    out = await impl.craft_map(
        app="photocraft",
        direction="doc_to_screen",
        point=[120.0, 80.0],
        zoom=2.0,
        centre=[100.0, 100.0],
        view_size=[800.0, 600.0],
        user_id="op",
        session_id="s1",
        raw_token=FULL_TOKEN,
    )
    assert out["result"] == pytest.approx([440.0, 260.0])
    back = await impl.craft_map(
        app="photocraft",
        direction="screen_to_doc",
        point=out["result"],
        zoom=2.0,
        centre=[100.0, 100.0],
        view_size=[800.0, 600.0],
        user_id="op",
        session_id="s1",
        raw_token=FULL_TOKEN,
    )
    assert back["result"] == pytest.approx([120.0, 80.0])


@pytest.mark.asyncio()
async def test_map_canvas_rect(setup) -> None:
    impl, *_ = setup
    out = await impl.craft_map(
        app="photocraft",
        direction="canvas_rect",
        point=[0, 0],
        zoom=2.0,
        centre=[100.0, 100.0],
        view_size=[800.0, 600.0],
        canvas_size=[200.0, 100.0],
        user_id="op",
        session_id="s1",
        raw_token=FULL_TOKEN,
    )
    assert out["result"]["w"] == pytest.approx(400.0)
    assert out["query_map_id"].startswith("qm_")


@pytest.mark.asyncio()
@pytest.mark.parametrize("direction", ["sideways", ""])
async def test_map_unknown_direction(setup, direction: str) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="unknown direction"):
        await impl.craft_map(
            app="photocraft",
            direction=direction,
            point=[0, 0],
            user_id="op",
            session_id="s1",
            raw_token=FULL_TOKEN,
        )


@pytest.mark.asyncio()
async def test_map_bad_shapes(setup) -> None:
    impl, *_ = setup
    with pytest.raises(ToolError, match="point must be"):
        await impl.craft_map(
            app="photocraft",
            direction="doc_to_screen",
            point=[0, 0, 0],
            user_id="op",
            session_id="s1",
            raw_token=FULL_TOKEN,
        )
    with pytest.raises(ToolError, match="canvas_rect requires"):
        await impl.craft_map(
            app="photocraft",
            direction="canvas_rect",
            point=[0, 0],
            user_id="op",
            session_id="s1",
            raw_token=FULL_TOKEN,
        )
    with pytest.raises(ToolError, match="zoom must be positive"):
        await impl.craft_map(
            app="photocraft",
            direction="doc_to_screen",
            point=[0, 0],
            zoom=0,
            user_id="op",
            session_id="s1",
            raw_token=FULL_TOKEN,
        )


def test_query_map_put_get() -> None:
    qm = QueryMap("s1")
    entry_id = qm.put("canvas_rect", {"x": 1.0})
    assert entry_id.startswith("qm_")
    assert qm.get(entry_id) == {"id": entry_id, "kind": "canvas_rect", "x": 1.0}
    assert qm.get("qm_999") is None


def test_register_perception_tools_wires_both(setup) -> None:
    _, manager, sessions, store = setup
    from gateway.main import create_gateway

    mcp = create_gateway(auth_store=store, backend_manager=manager, sessions=sessions)
    impl = register_perception_tools(
        mcp, backend_manager=manager, sessions=sessions, auth_store=store
    )
    assert isinstance(impl, PerceptionTools)
    assert mcp.perception is impl  # type: ignore[attr-defined]
