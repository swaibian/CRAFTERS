"""Crafter controller service: chat-driven document agent over real files.

Package layout (wiring chain)::

    uvicorn controller.service:app --port 8790
      → create_app() (controller/service.py)
      → /api/settings/* (controller/settings.py store)
      → /api/files/open (controller/documents.py adapters)
      → /api/chat/stream (controller/agent.py loop + controller/llm.py brain)
      → SSE events framed like swaibian-one send_task_stream

SW-REQ: SW-REQ-STREAM (TC-B stream + settings surface, controller side).
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
