"""
Unified Grok Client for Learn to Sushi
Handles both regular chat completions and Voice Agent API calls.
"""

import os
import json
from typing import List, Dict, Any, Optional
import httpx
from openai import AsyncOpenAI  # xAI is OpenAI-compatible

XAI_API_KEY = os.getenv("XAI_API_KEY_LTS")
XAI_BASE_URL = "https://api.x.ai/v1"

# Voice Agent model
VOICE_MODEL = "grok-voice-think-fast-1.0"

client = AsyncOpenAI(
    api_key=XAI_API_KEY,
    base_url=XAI_BASE_URL,
)


async def chat_completion(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict]] = None,
    model: str = "grok-4.20-0309-reasoning"
) -> str:
    """Standard chat completion for web chat."""
    try:
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
    Returns the session configuration for xAI Voice Agent API.
    This is sent when establishing the WebSocket connection.
    """
    return {
        "model": VOICE_MODEL,
        "instructions": """You are Sensei from Learn to Sushi — warm, joyful, and helpful. 
        Follow the brand guideline: warm, fun, family-positive. 
        Never say 'conveyor belt' for the Sushi River — it's a beautiful self-serve wavy table with 5 rows.
        Keep responses natural and conversational for voice.""",
        "voice": "eve",  # or ara, rex, sal, leo
        "input_audio_format": "pcm16",
        "output_audio_format": "pcm16",
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500
        },
        "tools": []  # Add tools here if needed
    }