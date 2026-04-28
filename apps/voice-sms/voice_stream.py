"""
Voice Stream WebSocket Handler
Bridges Twilio Media Streams with xAI Grok Voice Agent API.
"""

import base64
import json
import logging
import os
import asyncio
from typing import Any, Dict, Optional

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from packages.core import get_voice_agent_session_instructions

logger = logging.getLogger(__name__)

router = APIRouter()

XAI_API_KEY = os.getenv("XAI_API_KEY_LTS")
XAI_VOICE_WS = "wss://api.x.ai/v1/realtime?model=grok-voice-think-fast-1.0"


def _parse_twilio_message(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if raw.get("type") != "websocket.receive":
        return None
    text = raw.get("text")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Non-JSON Twilio frame: %s", text[:200])
        return None


@router.websocket("/ws")
async def voice_stream(websocket: WebSocket):
    """Handle bidirectional audio streaming between Twilio and xAI."""
    await websocket.accept()

    if not XAI_API_KEY:
        logger.error("XAI_API_KEY_LTS missing; closing voice stream")
        await websocket.close(code=1011)
        return

    try:
        async with websockets.connect(
            XAI_VOICE_WS,
            extra_headers={"Authorization": f"Bearer {XAI_API_KEY}"},
        ) as xai_ws:
            session_config = await get_voice_agent_session_instructions()
            await xai_ws.send(
                json.dumps({"type": "session.update", "session": session_config})
            )

            async def forward_twilio_to_xai():
                while True:
                    try:
                        raw = await websocket.receive()
                    except WebSocketDisconnect:
                        break
                    if raw.get("type") == "websocket.disconnect":
                        break
                    msg = _parse_twilio_message(raw)
                    if not msg:
                        continue
                    event = msg.get("event")
                    if event == "media":
                        media = msg.get("media") or {}
                        payload_b64 = media.get("payload")
                        if payload_b64:
                            try:
                                chunk = base64.b64decode(payload_b64)
                                await xai_ws.send(chunk)
                            except Exception as e:
                                logger.warning("twilio media decode/send: %s", e)
                    elif event == "stop":
                        break

            async def forward_xai_to_twilio():
                while True:
                    try:
                        message = await xai_ws.recv()
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            event = json.loads(message)
                            if event.get("type") == "response.audio.delta":
                                audio_data = event.get("delta", "")
                                if audio_data:
                                    await websocket.send_bytes(
                                        audio_data.encode("utf-8", errors="replace")
                                    )
                    except Exception as e:
                        logger.warning("xAI forward error: %s", e)
                        break

            results = await asyncio.gather(
                forward_twilio_to_xai(),
                forward_xai_to_twilio(),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    logger.warning("voice stream task error: %s", r)

    except Exception as e:
        logger.exception("Voice stream error: %s", e)
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
