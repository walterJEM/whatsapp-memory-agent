"""
WhatsApp Memory Agent — Core Agent
Uses LangChain + GPT-4o-mini + pgvector for semantic memory.
"""

from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from langchain_core.messages import HumanMessage, AIMessage

from app.agent.tools import (
    save_note_tool,
    search_memory_tool,
    get_expenses_summary_tool,
    set_reminder_tool,
    extract_receipt_tool,
)
from app.db.vector_store import VectorStore
from app.db.repositories import NoteRepository, ReminderRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """Eres un asistente de memoria personal que vive en WhatsApp.
Tu trabajo es ayudar al usuario a guardar, organizar y encontrar información.

Reglas de comportamiento:
- Responde siempre en español, de forma breve y clara
- Cuando el usuario guarde algo, confirma con un emoji relevante
- Cuando busques información, muestra resultados ordenados y limpios
- Detecta automáticamente el tipo de contenido: gasto, tarea, idea, dato importante
- Si detectas una fecha o "mañana/el lunes/etc", crea un recordatorio automáticamente
- Nunca inventes información — si no tienes datos, dilo claramente

Categorías que manejas:
- 💰 gasto (transporte, comida, servicios, etc.)
- ✅ tarea (hacer, llamar, enviar, etc.)
- 💡 idea (proyectos, negocios, pensamientos)
- 📄 documento (boletas, facturas, contratos)
- 📌 dato_importante (RUC, cuentas, contactos, contraseñas)
- 📓 nota_general (cualquier otra cosa)

Usuario actual: {user_phone}
Fecha y hora actual: {current_datetime}
"""


class MemoryAgent:
    def __init__(self, user_phone: str):
        self.user_phone = user_phone
        self.vector_store = VectorStore()
        self.note_repo = NoteRepository()
        self.reminder_repo = ReminderRepository()

        self.llm = ChatGroq(
            model="llama-3.1-70b-versatile",
            temperature=0.2,
        )

        self.tools = [
            save_note_tool(user_phone, self.note_repo, self.vector_store),
            search_memory_tool(user_phone, self.vector_store),
            get_expenses_summary_tool(user_phone, self.note_repo),
            set_reminder_tool(user_phone, self.reminder_repo),
            extract_receipt_tool(user_phone, self.note_repo, self.vector_store),
        ]

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        self.executor = create_react_agent(
            self.llm,
            self.tools,
        )

    async def process_message(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        image_url: str | None = None,
    ) -> str:
        """
        Process a WhatsApp message and return the agent's response.

        Args:
            message: Text message from the user
            chat_history: Previous messages for context (last 10 messages)
            image_url: Optional URL of an attached image (receipt/document)

        Returns:
            Agent's response as string
        """
        from datetime import datetime

        if image_url:
            message = f"[IMAGEN ADJUNTA: {image_url}]\n{message or 'Analiza esta imagen'}"

        history = self._format_chat_history(chat_history or [])

        try:
            result = await self.executor.ainvoke({
                "input": message,
                "chat_history": history,
                "user_phone": self.user_phone,
                "current_datetime": datetime.now().strftime("%A %d/%m/%Y %H:%M"),
            })
            return result["output"]

        except Exception as e:
            logger.error(f"Agent error for {self.user_phone}: {e}")
            return "Ocurrió un error procesando tu mensaje. Intenta de nuevo 🙏"

    def _format_chat_history(self, history: list[dict]) -> list:
        """Convert raw chat history dicts to LangChain message objects."""
        messages = []
        for msg in history[-10:]:  # Keep last 10 messages for context
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages
