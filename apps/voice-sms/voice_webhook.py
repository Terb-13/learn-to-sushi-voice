"""
Twilio Voice Webhook for Learn to Sushi
Returns TwiML that connects the call to our WebSocket stream.
"""

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

router = APIRouter()


@router.post("/webhook")
async def voice_webhook(request: Request):
    """Handle incoming voice calls from Twilio."""
    form = await request.form()
    
    # Get the public URL for this Fly.io app
    base_url = request.headers.get("X-Forwarded-Proto", "https") + "://" + request.headers.get("Host", "")
    
    response = VoiceResponse()
    
    # Connect to our WebSocket stream
    connect = Connect()
    stream = Stream(
        url=f"wss://{request.headers.get('Host')}/voice-stream/ws",
        track="both_tracks"
    )
    connect.append(stream)
    response.append(connect)
    
    return Response(content=str(response), media_type="application/xml")