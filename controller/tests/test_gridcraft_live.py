"""GridCraft-specific wire contracts, independent of PhotoCraft fixtures."""

import pytest

from controller.agent import _live_detail
from controller.live import LiveExecutor, LiveManager
from controller.tests.test_live import LiveStubServer, _bridge, _client

GRID_UI = {
    "documents": [{"title": "Book1", "dirty": False}, {"title": "Budget.xlsx", "dirty": True}],
    "activeDocument": 1,
    "window": [1440, 900],
    "grid": [28, 205, 1398, 637],
}
GRID_DOC = {
    "title": "Budget.xlsx", "activeSheet": 0, "activeCell": "B2",
    "selection": "B2:D4", "dirty": True, "undo": ["Enter Cell"],
    "sheets": [{"name": "Summary", "usedRange": "A1:D4", "cells": 12}],
}


def test_gridcraft_list_and_attach_real_payload(tmp_path, monkeypatch):
    with LiveStubServer(ui_inspect=GRID_UI, document_inspect=GRID_DOC) as stub:
        client = _client(tmp_path, monkeypatch, {"gridcraft": _bridge("gridcraft", stub.port)})
        response = client.get("/api/live/documents", params={"app": "gridcraft"})
        assert response.status_code == 200
        result = response.json()
        assert result["active"] == 1
        assert [doc["name"] for doc in result["documents"]] == ["Book1", "Budget.xlsx"]
        assert result["documents"][1]["dirty"] is True
        assert result["documents"][1]["active"] is True
        response = client.post("/api/live/attach", json={"session_id": "grid", "app": "gridcraft", "document": 1})
        assert response.status_code == 201
        assert response.json()["name"] == "Budget.xlsx (live gridcraft)"


@pytest.mark.asyncio
async def test_gridcraft_execution_uses_window_activation_and_direct_inspection():
    with LiveStubServer(ui_inspect=GRID_UI, document_inspect=GRID_DOC) as stub:
        executor = LiveExecutor(LiveManager({"gridcraft": _bridge("gridcraft", stub.port)}), "gridcraft", 1)
        assert await executor.inspect() == GRID_DOC
        await executor.execute("cell.get", {"cell": "B2"})
        assert stub.activate_calls == [1, 1]
        assert stub.execute_calls == [("cell.get", {"cell": "B2"})]


def test_gridcraft_observation_preserves_sheet_and_range_context():
    detail = _live_detail(GRID_DOC)
    assert detail["title"] == "Budget.xlsx"
    assert detail["activeSheet"] == 0
    assert detail["activeCell"] == "B2"
    assert detail["selection"] == "B2:D4"
    assert detail["sheets"][0]["name"] == "Summary"
