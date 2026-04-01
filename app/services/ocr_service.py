from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import json
import re

from app.utils.logger import get_logger

logger = get_logger(__name__)

RECEIPT_EXTRACTION_PROMPT = """Analiza esta imagen de boleta/factura/recibo y extrae la siguiente información en JSON:

{
  "establishment": "nombre del negocio o establecimiento",
  "total": número con el monto total (solo número, sin S/),
  "igv": número con el IGV si se muestra (18% del subtotal),
  "subtotal": número sin IGV,
  "date": "fecha en formato YYYY-MM-DD si aparece",
  "items": [
    {"description": "descripción del item", "amount": número}
  ],
  "document_type": "boleta|factura|ticket|otro",
  "ruc": "RUC del emisor si aparece",
  "raw_text": "texto completo extraído de la imagen"
}

Si no puedes extraer algún campo, usa null.
Responde SOLO con el JSON, sin texto adicional.
"""


class OCRService:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", max_tokens=1000)

    async def extract_receipt(self, image_url: str) -> dict | None:
        """
        Extract structured data from a receipt image.

        Args:
            image_url: Public URL of the image

        Returns:
            Dict with extracted receipt data or None if extraction failed
        """
        try:
            message = HumanMessage(
                content=[
                    {"type": "text", "text": RECEIPT_EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                ]
            )
            response = await self.llm.ainvoke([message])
            raw = response.content.strip()

            # Clean up potential markdown code blocks
            raw = re.sub(r"```json\n?", "", raw)
            raw = re.sub(r"```\n?", "", raw)

            data = json.loads(raw)
            logger.info(f"Receipt extracted: {data.get('establishment')} — S/{data.get('total')}")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"OCR JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return None

    async def extract_document(self, image_url: str) -> dict | None:
        """
        General document extraction (DNI, contracts, etc.).
        Returns raw text and basic metadata.
        """
        try:
            message = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": "Extrae todo el texto de este documento en formato JSON: {'raw_text': '...', 'document_type': '...', 'key_data': {...}}",
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]
            )
            response = await self.llm.ainvoke([message])
            raw = re.sub(r"```json\n?|```\n?", "", response.content.strip())
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Document extraction failed: {e}")
            return None
