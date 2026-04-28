"""
Twilio SMS Webhook for Learn to Sushi
Handles incoming text messages with the same personality as web chat.
"""

import logging

from fastapi import APIRouter, Form
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

from packages.core import GrokClient, get_knowledge_context

logger = logging.getLogger(__name__)

router = APIRouter()

TWIML_XML = "text/xml; charset=utf-8"


@router.post("/webhook")
async def sms_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
):
    """Handle incoming SMS from Twilio."""
    try:
        knowledge = await get_knowledge_context(Body)
        messages = [
            {
                "role": "system",
                "content": "You are Sensei from Learn to Sushi. Be warm, fun, and family-positive. Keep SMS responses concise (under 160 characters when possible).",
            },
            {
                "role": "user",
                "content": f"{Body}\n\nRelevant knowledge:\n{knowledge}",
            },
        ]
        client = GrokClient()
        reply = await client.chat_completion(messages)
        twiml = MessagingResponse()
        twiml.message(reply[:1600])
        return Response(content=str(twiml), media_type=TWIML_XML)
    except Exception as e:
        logger.exception("sms webhook error: %s", e)
        twiml = MessagingResponse()
        twiml.message(
            "Sensei is having a quick technical moment — please text us again in a minute!"
        )
        return Response(content=str(twiml), media_type=TWIML_XML)
