"""
Twilio SMS Webhook for Learn to Sushi
Handles incoming text messages with the same personality as web chat.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

from packages.core import GrokClient, get_knowledge_context

router = APIRouter()


@router.post("/webhook")
async def sms_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...)
):
    """Handle incoming SMS from Twilio."""
    
    # Get relevant knowledge
    knowledge = await get_knowledge_context(Body)
    
    # Create conversation context
    messages = [
        {"role": "system", "content": "You are Sensei from Learn to Sushi. Be warm, fun, and family-positive. Keep SMS responses concise (under 160 characters when possible)."},
        {"role": "user", "content": f"{Body}\n\nRelevant knowledge:\n{knowledge}"}
    ]
    
    # Get Grok response
    client = GrokClient()
    reply = await client.chat_completion(messages)
    
    # Send SMS response
    twiml = MessagingResponse()
    twiml.message(reply[:1600])  # Twilio SMS limit
    
    return Response(content=str(twiml), media_type="application/xml")