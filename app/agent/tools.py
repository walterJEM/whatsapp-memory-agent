"""
Agent Tools — LangChain tools that give the agent its capabilities.
Each tool is a function the LLM can call to interact with the system.
"""


from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from app.db.vector_store import VectorStore
from app.db.repositories import NoteRepository, ReminderRepository
from app.services.ocr_service import OCRService
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─── Input Schemas ────────────────────────────────────────────────────────────

class SaveNoteInput(BaseModel):
    content: str = Field(description="The exact content to save")
    category: str = Field(
        description="Category: gasto, tarea, idea, documento, dato_importante, nota_general"
    )
    amount: Optional[float] = Field(None, description="Amount in soles if it's a expense")
    expense_category: Optional[str] = Field(
        None, description="Expense subcategory: transporte, comida, servicios, otros"
    )
    tags: Optional[list[str]] = Field(None, description="Relevant tags for this note")


class SearchMemoryInput(BaseModel):
    query: str = Field(description="Natural language query to search in memory")
    category_filter: Optional[str] = Field(None, description="Filter by category if specified")
    date_filter: Optional[str] = Field(None, description="Date filter: 'today', 'this_week', 'this_month'")


class ExpensesSummaryInput(BaseModel):
    period: str = Field(description="Period: 'today', 'this_week', 'this_month', 'last_month'")
    category: Optional[str] = Field(None, description="Optional expense subcategory filter")


class SetReminderInput(BaseModel):
    content: str = Field(description="What to remind the user about")
    remind_at: str = Field(description="ISO datetime string for when to send the reminder")
    original_text: str = Field(description="Original text the user wrote")


class ExtractReceiptInput(BaseModel):
    image_url: str = Field(description="URL of the receipt/invoice image")
    additional_context: Optional[str] = Field(None, description="Any extra context from the user")


# ─── Tool Factories ────────────────────────────────────────────────────────────

def save_note_tool(user_phone: str, repo: NoteRepository, vs: VectorStore) -> StructuredTool:
    async def _save_note(
        content: str,
        category: str,
        amount: Optional[float] = None,
        expense_category: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        note = await repo.create(
            user_phone=user_phone,
            content=content,
            category=category,
            amount=amount,
            expense_category=expense_category,
            tags=tags or [],
            created_at=datetime.now(),
        )
        # Store embedding for semantic search
        await vs.add_document(
            doc_id=str(note.id),
            content=content,
            metadata={
                "user_phone": user_phone,
                "category": category,
                "note_id": str(note.id),
                "created_at": note.created_at.isoformat(),
            }
        )
        logger.info(f"Saved note {note.id} for {user_phone} — {category}")
        return f"OK:{note.id}"

    return StructuredTool.from_function(
        coroutine=_save_note,
        name="save_note",
        description="Save any information the user sends: notes, ideas, expenses, tasks, important data.",
        args_schema=SaveNoteInput,
    )


def search_memory_tool(user_phone: str, vs: VectorStore) -> StructuredTool:
    async def _search_memory(
        query: str,
        category_filter: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> str:
        filters = {"user_phone": user_phone}
        if category_filter:
            filters["category"] = category_filter

        results = await vs.similarity_search(
            query=query,
            filters=filters,
            k=5,
            date_filter=date_filter,
        )

        if not results:
            return "NO_RESULTS"

        formatted = []
        for i, r in enumerate(results, 1):
            date_str = r.metadata.get("created_at", "")[:10]
            formatted.append(f"{i}. [{date_str}] {r.page_content}")

        return "\n".join(formatted)

    return StructuredTool.from_function(
        coroutine=_search_memory,
        name="search_memory",
        description="Search the user's saved notes using natural language. Use this when the user asks about past info.",
        args_schema=SearchMemoryInput,
    )


def get_expenses_summary_tool(user_phone: str, repo: NoteRepository) -> StructuredTool:
    async def _get_expenses_summary(
        period: str,
        category: Optional[str] = None,
    ) -> str:
        summary = await repo.get_expenses_summary(
            user_phone=user_phone,
            period=period,
            category=category,
        )

        if not summary["items"]:
            return f"No hay gastos registrados para {period}"

        lines = [f"Total {period}: S/{summary['total']:.2f}", ""]
        for cat, amount in summary["by_category"].items():
            lines.append(f"• {cat}: S/{amount:.2f}")

        return "\n".join(lines)

    return StructuredTool.from_function(
        coroutine=_get_expenses_summary,
        name="get_expenses_summary",
        description="Get expense summary for a time period. Use when user asks how much they spent.",
        args_schema=ExpensesSummaryInput,
    )


def set_reminder_tool(user_phone: str, repo: ReminderRepository) -> StructuredTool:
    async def _set_reminder(
        content: str,
        remind_at: str,
        original_text: str,
    ) -> str:
        reminder = await repo.create(
            user_phone=user_phone,
            content=content,
            remind_at=datetime.fromisoformat(remind_at),
            original_text=original_text,
        )
        remind_dt = datetime.fromisoformat(remind_at)
        return f"REMINDER_SET:{reminder.id}:{remind_dt.strftime('%d/%m/%Y %H:%M')}"

    return StructuredTool.from_function(
        coroutine=_set_reminder,
        name="set_reminder",
        description="Set a reminder when the user mentions a future date or task deadline.",
        args_schema=SetReminderInput,
    )


def extract_receipt_tool(
    user_phone: str,
    repo: NoteRepository,
    vs: VectorStore,
) -> StructuredTool:
    async def _extract_receipt(
        image_url: str,
        additional_context: Optional[str] = None,
    ) -> str:
        ocr = OCRService()
        extracted = await ocr.extract_receipt(image_url)

        if not extracted:
            return "EXTRACTION_FAILED"

        note = await repo.create(
            user_phone=user_phone,
            content=extracted["raw_text"],
            category="documento",
            amount=extracted.get("total"),
            expense_category="boleta",
            tags=["boleta", "escaneado"],
            metadata=extracted,
            created_at=datetime.now(),
        )
        await vs.add_document(
            doc_id=str(note.id),
            content=extracted["raw_text"],
            metadata={"user_phone": user_phone, "category": "documento", "note_id": str(note.id)},
        )

        return (
            f"RECEIPT_EXTRACTED:"
            f"establecimiento={extracted.get('establishment', 'Desconocido')},"
            f"total={extracted.get('total', 0)},"
            f"fecha={extracted.get('date', 'desconocida')},"
            f"igv={extracted.get('igv', 0)}"
        )

    return StructuredTool.from_function(
        coroutine=_extract_receipt,
        name="extract_receipt",
        description="Extract data from a receipt or invoice image (boleta/factura). Use when user sends an image.",
        args_schema=ExtractReceiptInput,
    )
