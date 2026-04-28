"""
Voice Stream WebSocket Handler
Bridges Twilio Media Streams (μ-law, 8 kHz) ↔ xAI Grok Voice Realtime (PCM16 at 24 kHz).

Grok session uses audio/pcm @ 24000 Hz (same as the official sample). Twilio stays at 8 kHz
mulaw; we resample with audioop.ratecv and convert mulaw ↔ linear PCM.
Python 3.13+ requires PyPI `audioop-lts` (stdlib `audioop` was removed).
"""

import asyncio
import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

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


def _twilio_mulaw_b64_to_xai_pcm24_b64(
    payload_b64: str, rate_state: List[Optional[tuple]]
) -> str:
    mulaw_raw = base64.b64decode(payload_b64)
    if audioop is None:
        return payload_b64
    pcm8 = audioop.ulaw2lin(mulaw_raw, 2)
    pcm24, rate_state[0] = audioop.ratecv(pcm8, 2, 1, 8000, 24000, rate_state[0])
    return base64.b64encode(pcm24).decode("ascii")


def _xai_pcm24_b64_to_twilio_ulaw_chunks(
    pcm24_b64_piece: str, pcm24_buf: bytearray, rate_state: List[Optional[tuple]]
) -> list[str]:
    if not pcm24_b64_piece or audioop is None:
        return []
    pcm24_buf.extend(base64.b64decode(pcm24_b64_piece))
    n = (len(pcm24_buf) // 2) * 2
    if not n:
        return []
    pcm24_block = bytes(pcm24_buf[:n])
    del pcm24_buf[:n]
    pcm8, rate_state[0] = audioop.ratecv(
        pcm24_block, 2, 1, 24000, 8000, rate_state[0]
    )
    if not pcm8:
        return []
    if len(pcm8) % 2:
        pcm8 = pcm8[:-1]
    if not pcm8:
        return []
    ulaw = audioop.lin2ulaw(pcm8, 2)
    return [base64.b64encode(ulaw).decode("ascii")]


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


def _decode_xai_msg(raw_msg: Any) -> Dict[str, Any]:
    if isinstance(raw_msg, bytes):
        raw_msg = raw_msg.decode("utf-8", errors="replace")
    return json.loads(raw_msg)


async def _xai_realtime_handshake(xai_ws: Any) -> None:
    """
    xAI sends session/conversation preamble before accept; then we must wait for
    session.updated after session.update before creating responses.
    """
    for i in range(3):
        raw = await asyncio.wait_for(xai_ws.recv(), timeout=5.0)
        ev = _decode_xai_msg(raw)
        et = ev.get("type")
        logger.info("xAI handshake prelude [%s]: %s", i, et)
        if et == "error":
            logger.error("xAI error during prelude: %s", ev)
            raise RuntimeError(ev.get("message", "xAI realtime error"))
        if et in ("conversation.created", "session.created"):
            break
    else:
        logger.warning("xAI prelude: did not see conversation/session.created in 3 msgs")


async def _xai_wait_session_updated(xai_ws: Any) -> None:
    for i in range(50):
        raw = await asyncio.wait_for(xai_ws.recv(), timeout=25.0)
        ev = _decode_xai_msg(raw)
        et = ev.get("type")
        logger.info("await session.updated [%s]: %s", i, et)
        if et == "session.updated":
            return
        if et == "error":
            logger.error("xAI error before session.updated: %s", ev)
            raise RuntimeError(ev.get("message", "xAI error"))
    logger.warning("session.updated not seen after 50 xAI events")


@router.websocket("/ws")
async def voice_stream(websocket: WebSocket):
    """Bridge Twilio Media Stream ↔ xAI; resample 8 kHz ↔ 24 kHz PCM."""
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
            await _xai_realtime_handshake(xai_ws)

            session_cfg = await get_voice_agent_session_instructions()
            await xai_ws.send(
                json.dumps({"type": "session.update", "session": session_cfg})
            )

            await _xai_wait_session_updated(xai_ws)

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
            pcm24_to_8_buf = bytearray()
            rate_up: List[Optional[tuple]] = [None]
            rate_dn: List[Optional[tuple]] = [None]

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
                        else:
                            logger.error("Twilio start missing streamSid: %s", msg)
                        continue

                    if evt == "media":
                        media = msg.get("media") or {}
                        payload_b64 = media.get("payload")
                        if payload_b64:
                            pcm24_b64 = _twilio_mulaw_b64_to_xai_pcm24_b64(
                                payload_b64, rate_up
                            )
                            await xai_ws.send(
                                json.dumps(
                                    {
                                        "type": "input_audio_buffer.append",
                                        "audio": pcm24_b64,
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
                        try:
                            event = _decode_xai_msg(raw_msg)
                        except json.JSONDecodeError:
                            logger.warning(
                                "non-JSON xAI message: %s",
                                raw_msg[:256]
                                if isinstance(raw_msg, str)
                                else raw_msg[:256],
                            )
                            continue

                        et = event.get("type")
                        if xai_evt_n < 30:
                            logger.info("xAI stream event [%s]: %s", xai_evt_n, et)
                        xai_evt_n += 1

                        if et in _AUDIO_DELTA_TYPES:
                            pcm_b64 = _xai_audio_delta_b64(event)
                            if not pcm_b64:
                                continue
                            chunks = _xai_pcm24_b64_to_twilio_ulaw_chunks(
                                pcm_b64, pcm24_to_8_buf, rate_dn
                            )
                            for ulaw_b64 in chunks:
                                await to_caller.put(ulaw_b64)
                        elif et == "error":
                            logger.error("xAI voice error event: %s", event)
                finally:
                    if len(pcm24_to_8_buf):
                        logger.debug(
                            "dropping %s trailing PCM bytes at xAI stream end",
                            len(pcm24_to_8_buf),
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
                chunks_out = 0
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
                    chunks_out += 1
                    if chunks_out <= 5 or chunks_out % 50 == 0:
                        logger.info("sent Twilio media chunk #%s", chunks_out)

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
