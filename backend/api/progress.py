"""
api/progress.py — WebSocket de progreso en vivo.

Canales:
  /ws/progress/session/{session_id}   progreso del análisis
  /ws/progress/run/{run_id}           progreso de la corrección

El cliente recibe eventos JSON {phase, processed, total, percent, ...}. Al
conectar recibe el último evento conocido (si lo hay) para no perder estado.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.progress_hub import hub

router = APIRouter(tags=["progress"])


async def _stream(ws: WebSocket, channel: str) -> None:
    await ws.accept()
    q = await hub.subscribe(channel)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=25.0)
                await ws.send_json(event)
                if event.get("status") in ("completed", "failed"):
                    # deja que el cliente reciba el final y cierra
                    await asyncio.sleep(0.1)
            except asyncio.TimeoutError:
                # ping keep-alive
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(channel, q)


@router.websocket("/ws/progress/session/{session_id}")
async def ws_session(ws: WebSocket, session_id: int):
    await _stream(ws, f"session:{session_id}")


@router.websocket("/ws/progress/run/{run_id}")
async def ws_run(ws: WebSocket, run_id: str):
    await _stream(ws, f"run:{run_id}")
