"""
Voice Stream WebSocket Handler
Bridges Twilio Media Streams with xAI Grok Voice Agent API.
"""

import os
import json
import asyncio
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from packages.core import get_voice_agent_session_instructions

router = APIRouter()

XAI_API_KEY = os.getenv("XAI_API_KEY_LTS")
XAI_VOICE_WS = "wss://api.x.ai/v1/realtime?model=grok-voice-think-fast-1.0"


@router.websocket("/ws")
async def voice_stream(websocket: WebSocket):
    """Handle bidirectional audio streaming between Twilio and xAI."""
    await websocket.accept()
    
    try:
        # Connect to xAI Voice Agent
        async with websockets.connect(
            XAI_VOICE_WS,
            extra_headers={"Authorization": f"Bearer {XAI_API_KEY}"}
        ) as xai_ws:
            
            # Send session configuration
            session_config = await get_voice_agent_session_instructions()
            await xai_ws.send(json.dumps({
                "type": "session.update",
                "session": session_config
            }))
            
            # Main audio forwarding loop
            async def forward_twilio_to_xai():
                while True:
                    try:
                        data = await websocket.receive_bytes()
                        # Forward raw audio to xAI
                        await xai_ws.send(data)
                    except WebSocketDisconnect:
                        break
            
            async def forward_xai_to_twilio():
                while True:
                    try:
                        message = await xai_ws.recv()
                        if isinstance(message, bytes):
                            # Audio response from xAI
                            await websocket.send_bytes(message)
                        else:
                            # JSON event from xAI
                            event = json.loads(message)
                            if event.get("type") == "response.audio.delta":
                                # Forward audio delta
                                audio_data = event.get("delta", "")
                                if audio_data:
                                    await websocket.send_bytes(audio_data.encode())
                    except Exception as e:
                        print(f"xAI forward error: {e}")
                        break
            
            # Run both directions concurrently
            await asyncio.gather(
                forward_twilio_to_xai(),
                forward_xai_to_twilio()
            )
            
    except Exception as e:
        print(f"Voice stream error: {e}")
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()