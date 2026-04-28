"""
Twilio Voice Webhook for Learn to Sushi
Returns TwiML that connects the call to our WebSocket stream.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

logger = logging.getLogger(__name__)

router = APIRouter()

TWIML_XML = "text/xml; charset=utf-8"


@router.post("/webhook")
async def voice_webhook(request: Request):
    """Handle incoming voice calls from Twilio."""
    try:
        await request.form()
    except Exception as e:
        logger.warning("voice webhook form parse: %s", e)

    try:
        host = request.headers.get("Host") or ""
        if not host:
            raise ValueError("Missing Host header")

        response = VoiceResponse()
        connect = Connect()
        # Connect+<Stream>: only inbound_track allowed (both_tracks is for <Start>).
        stream = Stream(
            url=f"wss://{host}/voice-stream/ws",
            track="inbound_track",
        )
        connect.append(stream)
        response.append(connect)
        return Response(content=str(response), media_type=TWIML_XML)
    except Exception as e:
        logger.exception("voice webhook error: %s", e)
        err = VoiceResponse()
        err.say(
            "We are having a technical issue. Please try again in a moment.",
            voice="Polly.Joanna",
        )
        return Response(content=str(err), media_type=TWIML_XML)
