"""
Unified Grok Client for Learn to Sushi
Handles both regular chat completions and Voice Agent API calls.
"""

import os
import json
from typing import List, Dict, Any, Optional
import httpx
from openai import AsyncOpenAI  # xAI is OpenAI-compatible

XAI_BASE_URL = "https://api.x.ai/v1"

# Voice Agent model
VOICE_MODEL = "grok-voice-think-fast-1.0"

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    """Lazy init so importing the app does not require XAI_API_KEY_LTS at boot."""
    global _client
    if _client is not None:
        return _client
    key = os.getenv("XAI_API_KEY_LTS")
    if not key:
        return None
    _client = AsyncOpenAI(api_key=key, base_url=XAI_BASE_URL)
    return _client


async def chat_completion(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict]] = None,
    model: str = "grok-4.20-0309-reasoning"
) -> str:
    """Standard chat completion for web chat."""
    try:
        client = _get_client()
        if client is None:
            print("Grok chat error: XAI_API_KEY_LTS is not set")
            return "I'm having a quick moment — please try again in a second!"
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else None,
            temperature=0.7,
        )
        
        message = response.choices[0].message
        
        # Handle tool calls
        if message.tool_calls:
            # For now, return a placeholder - in production we'd execute tools
            return "I can help you create a custom menu proposal. Could you share the event name, date, number of guests, and your email?"
        
        return message.content or "I'm here to help with your sushi event!"
        
    except Exception as e:
        print(f"Grok chat error: {e}")
        return "I'm having a quick moment — please try again in a second!"


async def get_voice_agent_session_instructions() -> Dict[str, Any]:
    """
    Returns the session payload for session.update xAI Voice Realtime (OpenAI-compatible).
    Model is selected via WS URL (?model=...), not inside session.

    Twilio Media Streams sends G.711 μ-law at 8 kHz. xAI emits PCM16; we negotiate 8 kHz PCM
    and transcode μ-law ↔ PCM in the voice bridge (see voice_stream.py).
    """
    return {
        "instructions": """You are Sensei from Learn to Sushi — warm, joyful, and helpful.
        Follow the brand guideline: warm, fun, family-positive.
        Never say 'conveyor belt' for the Sushi River — it's a beautiful self-serve wavy table with 5 rows.
        Keep responses natural and conversational for voice.""",
        "voice": "eve",
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500,
        },
        "audio": {
            "input": {"format": {"type": "audio/pcm", "rate": 8000}},
            "output": {"format": {"type": "audio/pcm", "rate": 8000}},
        },
        "tools": [],
    }


class GrokClient:
    """Instance API used by SMS and other handlers."""

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        model: str = "grok-4.20-0309-reasoning",
    ) -> str:
        return await chat_completion(messages, tools=tools, model=model)