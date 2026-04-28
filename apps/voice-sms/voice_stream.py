"""
Voice Stream WebSocket Handler
Bridges Twilio Media Streams (μ-law, 8 kHz) ↔ xAI Grok Voice Realtime (PCM16 8 kHz in session).

Inbound: Twilio mulaw base64 → PCM16 base64 for input_audio_buffer.append.
Outbound: response.output_audio PCM base64 → mulaw base64 for Twilio media events.
Python 3.13+ requires PyPI `audioop-lts` (stdlib `audioop` was removed).
"""

import asyncio
import base64
import json
import logging
import os
from typing import Any, Dict, Optional

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed

try:
    import audioop
except ImportError:
    audioop = None

from packages.core import get_voice_agent_session_instructions

logger = logging.getLogger(__name__)

router = APIRouter()

XAI_API_KEY = os.getenv("XAI_API_KEY_LTS")
XAI_VOICE_WS = "wss://api.x.ai/v1/realtime?model=grok-voice-think-fast-1.0"

# Server events for streamed TTS chunks (GA + beta aliases)
_AUDIO_DELTA_TYPES = frozenset(
    {"response.output_audio.delta", "response.audio.delta"}
)


def _xai_audio_delta_b64(event: Dict[str, Any]) -> str:
    d = event.get("delta")
    if isinstance(d, str):
        return d
    if isinstance(d, dict):
        return str(d.get("audio") or d.get("delta") or "")
    return ""


def _pcm_b64_to_ulaw_chunks(pcm_b64_piece: str, buf: bytearray) -> list[str]:
    """PCM16 LE (8 kHz, base64 fragments) → Twilio μ-law base64 chunks."""
    if not pcm_b64_piece or audioop is None:
        return []
    buf.extend(base64.b64decode(pcm_b64_piece))
    n = (len(buf) // 2) * 2
    if not n:
        return []
    pcm_block = bytes(buf[:n])
    del buf[:n]
    ulaw = audioop.lin2ulaw(pcm_block, 2)
    return [base64.b64encode(ulaw).decode("ascii")]


def _twilio_mulaw_b64_to_xai_pcm_b64(payload_b64: str) -> str:
    mulaw_raw = base64.b64decode(payload_b64)
    if audioop is None:
        return payload_b64
    pcm_raw = audioop.ulaw2lin(mulaw_raw, 2)
    return base64.b64encode(pcm_raw).decode("ascii")


def _parse_twilio_message(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if raw.get("type") != "websocket.receive":
        return None
    text = raw.get("text")
    if text is None and raw.get("bytes") is not None:
        raw_bytes = raw.get("bytes")
        if isinstance(raw_bytes, (bytes, memoryview)):
            text = raw_bytes.decode("utf-8", errors="replace")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Non-JSON Twilio frame: %s", text[:200])
        return None


@router.websocket("/ws")
async def voice_stream(websocket: WebSocket):
    """Bridge Twilio Media Stream ↔ xAI; transcode Twilio mulaw ↔ 8 kHz PCM for xAI."""
    await websocket.accept()

    if audioop is None:
        logger.error(
            "stdlib audioop unavailable (Py3.13+): install dependency audioop-lts"
        )
        await websocket.close(code=1011)
        return

    if not XAI_API_KEY:
        logger.error("XAI_API_KEY_LTS missing; closing voice stream")
        await websocket.close(code=1011)
        return

    try:
        async with websockets.connect(
            XAI_VOICE_WS,
            extra_headers={"Authorization": f"Bearer {XAI_API_KEY}"},
        ) as xai_ws:
            session_cfg = await get_voice_agent_session_instructions()
            await xai_ws.send(
                json.dumps({"type": "session.update", "session": session_cfg})
            )

            # Optional: immediate greeting so the caller hears Sensei without speaking first.
            await xai_ws.send(
                json.dumps(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "The caller just connected by phone. "
                                        "Respond with one brief warm greeting as Sensei "
                                        "from Learn to Sushi, then listen for their question."
                                    ),
                                }
                            ],
                        },
                    }
                )
            )
            await xai_ws.send(json.dumps({"type": "response.create"}))

            stream_sid: Optional[str] = None
            sid_ready = asyncio.Event()
            to_caller = asyncio.Queue[Optional[str]]()
            pcm_to_mulaw_buf = bytearray()

            async def from_twilio() -> None:
                nonlocal stream_sid
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
                    evt = msg.get("event")

                    if evt == "connected":
                        continue

                    if evt == "start":
                        start = msg.get("start") or {}
                        stream_sid = msg.get("streamSid") or start.get("streamSid")
                        if stream_sid:
                            sid_ready.set()
                            logger.info("Twilio Media Stream start streamSid set")
                        continue

                    if evt == "media":
                        media = msg.get("media") or {}
                        payload_b64 = media.get("payload")
                        if payload_b64:
                            pcm_b64 = _twilio_mulaw_b64_to_xai_pcm_b64(payload_b64)
                            await xai_ws.send(
                                json.dumps(
                                    {
                                        "type": "input_audio_buffer.append",
                                        "audio": pcm_b64,
                                    }
                                )
                            )
                        continue

                    if evt == "stop":
                        break

            async def from_xai() -> None:
                xai_evt_n = 0
                try:
                    while True:
                        try:
                            raw_msg = await xai_ws.recv()
                        except ConnectionClosed as cc:
                            logger.info(
                                "xAI realtime WebSocket closed code=%s reason=%r",
                                cc.code,
                                cc.reason,
                            )
                            return
                        if isinstance(raw_msg, bytes):
                            raw_msg = raw_msg.decode("utf-8", errors="replace")
                        try:
                            event = json.loads(raw_msg)
                        except json.JSONDecodeError:
                            logger.warning("non-JSON xAI message: %s", raw_msg[:256])
                            continue

                        et = event.get("type")
                        if xai_evt_n < 25:
                            logger.info("xAI event [%s]: %s", xai_evt_n, et)
                        xai_evt_n += 1

                        if et in _AUDIO_DELTA_TYPES:
                            pcm_b64 = _xai_audio_delta_b64(event)
                            if not pcm_b64:
                                continue
                            for ulaw_b64 in _pcm_b64_to_ulaw_chunks(
                                pcm_b64, pcm_to_mulaw_buf
                            ):
                                await to_caller.put(ulaw_b64)
                        elif et == "error":
                            logger.error("xAI voice error event: %s", event)
                finally:
                    if len(pcm_to_mulaw_buf):
                        logger.debug(
                            "dropping %s odd PCM bytes at xAI stream end",
                            len(pcm_to_mulaw_buf),
                        )

            async def to_twilio() -> None:
                try:
                    await asyncio.wait_for(sid_ready.wait(), timeout=20.0)
                except asyncio.TimeoutError:
                    logger.error(
                        "Twilio never sent start with streamSid within 20s; no outbound audio"
                    )
                    return
                if not stream_sid:
                    logger.error("missing streamSid from Twilio start event")
                    return
                while True:
                    chunk_b64 = await to_caller.get()
                    if chunk_b64 is None:
                        break
                    await websocket.send_json(
                        {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": chunk_b64},
                        }
                    )

            b2t = asyncio.create_task(from_twilio())
            x2q = asyncio.create_task(from_xai())
            sender = asyncio.create_task(to_twilio())

            done, pending = await asyncio.wait(
                {b2t, x2q}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in done:
                try:
                    exc = t.exception()
                except asyncio.CancelledError:
                    continue
                if exc is not None:
                    logger.error("voice bridge task failed", exc_info=exc)
            await to_caller.put(None)
            sender.cancel()
            all_done = pending | {sender}
            for t in all_done:
                t.cancel()
            for t in all_done:
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    except Exception:
        logger.exception("Voice stream error")
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
