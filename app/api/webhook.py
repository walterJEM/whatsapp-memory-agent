"""
WhatsApp Webhook — FastAPI endpoint that receives messages from WhatsApp
via Twilio or 360dialog and routes them to the Memory Agent.
"""

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import hashlib
import hmac
import os

from app.agent.memory_agent import MemoryAgent
from app.db.session import init_db
from app.services.whatsapp_service import WhatsAppService
from app.services.session_service import SessionService
from app.utils.logger import get_logger

logger = get_logger(__name__)

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "my_verify_token")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WhatsApp Memory Agent...")
    await init_db()
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="WhatsApp Memory Agent",
    description="AI-powered personal memory assistant for WhatsApp",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

whatsapp = WhatsAppService()
sessions = SessionService()


# ─── Twilio Webhook ───────────────────────────────────────────────────────────

@app.post("/webhook/twilio")
async def twilio_webhook(request: Request):
    """
    Receives WhatsApp messages from Twilio.
    Twilio sends form-encoded data.
    """
    form = await request.form()

    from_number = form.get("From", "").replace("whatsapp:", "")
    body = form.get("Body", "").strip()
    media_url = form.get("MediaUrl0")      # Image if attached
    media_type = form.get("MediaContentType0", "")

    if not from_number:
        raise HTTPException(status_code=400, detail="Missing From number")

    logger.info(f"Message from {from_number}: {body[:50]}...")

    # Process asynchronously and return TwiML immediately
    # (Twilio expects a fast response)
    import asyncio
    asyncio.create_task(
        _process_and_reply(from_number, body, media_url, media_type)
    )

    # Return empty TwiML — we'll send the reply separately
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


# ─── 360dialog Webhook ────────────────────────────────────────────────────────

@app.post("/webhook/360dialog")
async def dialog360_webhook(request: Request):
    """
    Receives WhatsApp messages from 360dialog.
    Uses Meta's Cloud API format.
    """
    payload = await request.json()

    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]["value"]
        message = changes["messages"][0]
        from_number = message["from"]

        body = ""
        image_url = None

        if message["type"] == "text":
            body = message["text"]["body"]
        elif message["type"] == "image":
            image_id = message["image"]["id"]
            image_url = await whatsapp.get_media_url(image_id)
            body = message.get("image", {}).get("caption", "")
        elif message["type"] == "audio":
            # Future: transcribe with Whisper
            body = "[AUDIO — transcripción próximamente]"

    except (KeyError, IndexError) as e:
        logger.warning(f"Malformed 360dialog payload: {e}")
        return {"status": "ignored"}

    import asyncio
    asyncio.create_task(
        _process_and_reply(from_number, body, image_url, "image/jpeg" if image_url else "")
    )

    return {"status": "ok"}


# ─── Meta Webhook Verification ────────────────────────────────────────────────

@app.get("/webhook/360dialog")
async def verify_webhook(
    hub_mode: str = "",
    hub_verify_token: str = "",
    hub_challenge: str = "",
):
    """Meta requires GET verification when setting up the webhook."""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "whatsapp-memory-agent"}


# ─── Internal ─────────────────────────────────────────────────────────────────

async def _process_and_reply(
    user_phone: str,
    message: str,
    image_url: str | None,
    media_type: str,
):
    """Core processing pipeline: receive → agent → reply."""
    try:
        # Get or create session (chat history)
        history = await sessions.get_history(user_phone)

        # Run the agent
        agent = MemoryAgent(user_phone=user_phone)
        response = await agent.process_message(
            message=message,
            chat_history=history,
            image_url=image_url if media_type.startswith("image") else None,
        )

        # Save to session history
        await sessions.add_messages(user_phone, message, response)

        # Send reply via WhatsApp
        await whatsapp.send_message(user_phone, response)

    except Exception as e:
        logger.error(f"Pipeline error for {user_phone}: {e}", exc_info=True)
        await whatsapp.send_message(
            user_phone,
            "Hubo un error procesando tu mensaje. Por favor intenta de nuevo 🙏"
        )
