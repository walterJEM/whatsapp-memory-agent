"""
WhatsApp Service — Sends messages via Twilio or 360dialog.
Abstracts the provider so you can switch without touching the rest of the code.
"""

import os
import httpx
from app.utils.logger import get_logger

logger = get_logger(__name__)

PROVIDER = os.getenv("WHATSAPP_PROVIDER", "twilio")  # twilio | 360dialog

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# 360dialog
DIALOG360_API_KEY = os.getenv("DIALOG360_API_KEY", "")
DIALOG360_PHONE_ID = os.getenv("DIALOG360_PHONE_NUMBER_ID", "")


class WhatsAppService:

    async def send_message(self, to_phone: str, message: str) -> bool:
        """
        Send a WhatsApp message to a phone number.

        Args:
            to_phone: Phone number with country code (e.g. +51987654321)
            message: Text to send

        Returns:
            True if sent successfully, False otherwise
        """
        if PROVIDER == "twilio":
            return await self._send_twilio(to_phone, message)
        elif PROVIDER == "360dialog":
            return await self._send_360dialog(to_phone, message)
        else:
            logger.error(f"Unknown WhatsApp provider: {PROVIDER}")
            return False

    async def _send_twilio(self, to_phone: str, message: str) -> bool:
        """Send via Twilio WhatsApp API."""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                    data={
                        "From": TWILIO_FROM,
                        "To": f"whatsapp:{to_phone}",
                        "Body": message,
                    },
                )
                response.raise_for_status()
                logger.info(f"Message sent to {to_phone} via Twilio")
                return True
            except httpx.HTTPError as e:
                logger.error(f"Twilio send failed for {to_phone}: {e}")
                return False

    async def _send_360dialog(self, to_phone: str, message: str) -> bool:
        """Send via 360dialog (Meta Cloud API format)."""
        url = f"https://waba.360dialog.io/v1/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone.replace("+", ""),
            "type": "text",
            "text": {"body": message},
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "D360-API-KEY": DIALOG360_API_KEY,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                logger.info(f"Message sent to {to_phone} via 360dialog")
                return True
            except httpx.HTTPError as e:
                logger.error(f"360dialog send failed for {to_phone}: {e}")
                return False

    async def get_media_url(self, media_id: str) -> str:
        """
        Resolve a media ID to a downloadable URL (360dialog only).
        Used to download images before sending to GPT-4o vision.
        """
        url = f"https://waba.360dialog.io/v1/media/{media_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"D360-API-KEY": DIALOG360_API_KEY},
            )
            data = response.json()
            return data.get("url", "")
