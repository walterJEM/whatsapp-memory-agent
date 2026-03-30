# 🧠 WhatsApp Memory Agent

> **Asistente personal con IA que convierte tu chat de WhatsApp en una memoria inteligente.**

Un agente de IA construido con LangChain + GPT-4o que vive en WhatsApp. Guarda, clasifica y recuerda cualquier cosa que le envíes: gastos, tareas, ideas, fotos de boletas. Búsqueda en lenguaje natural. Recordatorios automáticos. Pensado para freelancers en Latinoamérica.

---

## ✨ Features

| Feature | Descripción |
|---|---|
| 💾 **Guardado inteligente** | Clasifica automáticamente texto, ideas, gastos y tareas |
| 🔍 **Búsqueda semántica** | "¿qué hice el lunes?" — encuentra info aunque uses palabras diferentes |
| 📄 **OCR de boletas** | Extrae monto, establecimiento e IGV de fotos de recibos |
| ⏰ **Recordatorios** | Detecta fechas en el texto y crea recordatorios automáticamente |
| 📊 **Resumen semanal** | Todos los domingos recibe un resumen de tu semana |
| 💰 **Reporte de gastos** | Resumen por categoría para declaración de impuestos |

---

## 🏗️ Arquitectura

```
WhatsApp  →  Twilio/360dialog  →  FastAPI Webhook
                                        │
                              LangChain Agent (GPT-4o-mini)
                              ┌─────────┴──────────┐
                         Tools / Skills         Memory
                         ─────────────         ───────
                         save_note         PostgreSQL
                         search_memory     pgvector (embeddings)
                         extract_receipt   Redis (sessions)
                         set_reminder      Celery (scheduler)
                         get_expenses
```

### Stack

- **Backend**: Python 3.12 + FastAPI
- **Agente IA**: LangChain + GPT-4o-mini
- **Memoria semántica**: PostgreSQL + pgvector + OpenAI Embeddings
- **OCR**: GPT-4o vision
- **Scheduler**: Celery + Redis
- **WhatsApp**: Twilio Sandbox (dev) / 360dialog (prod)
- **Deploy**: Docker Compose / Railway

---

## 🚀 Quickstart

### 1. Clonar e instalar

```bash
git clone https://github.com/tu-usuario/whatsapp-memory-agent.git
cd whatsapp-memory-agent

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tu OPENAI_API_KEY y credenciales de Twilio
```

### 3. Levantar base de datos y Redis

```bash
docker-compose up db redis -d
```

### 4. Correr migraciones

```bash
alembic upgrade head
```

### 5. Iniciar el servidor

```bash
uvicorn app.api.webhook:app --reload
```

### 6. Exponer con ngrok (para pruebas con Twilio)

```bash
ngrok http 8000
# Copia la URL y pégala en Twilio Sandbox como webhook:
# https://xxxx.ngrok.io/webhook/twilio
```

---

## 📁 Estructura del proyecto

```
whatsapp-memory-agent/
├── app/
│   ├── agent/
│   │   ├── memory_agent.py     # Agente principal LangChain
│   │   └── tools.py            # Tools: save, search, OCR, reminders
│   ├── api/
│   │   └── webhook.py          # FastAPI endpoints (Twilio + 360dialog)
│   ├── db/
│   │   ├── models.py           # SQLAlchemy ORM models
│   │   ├── repositories.py     # Data access layer
│   │   ├── session.py          # DB session management
│   │   └── vector_store.py     # pgvector semantic search
│   ├── services/
│   │   ├── ocr_service.py      # Receipt extraction con GPT-4o vision
│   │   ├── scheduler.py        # Celery tasks (reminders, summaries)
│   │   ├── session_service.py  # Chat history management
│   │   └── whatsapp_service.py # WhatsApp message sending
│   └── utils/
│       └── logger.py           # Structured logging
├── tests/
│   ├── test_agent.py
│   ├── test_ocr.py
│   └── test_webhook.py
├── docs/
│   └── architecture.md
├── scripts/
│   └── seed_test_data.py
├── alembic/                    # DB migrations
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## 💬 Ejemplos de conversación

**Guardar un gasto:**
```
Usuario: taxi al aeropuerto 45 soles
  Bot:   ✅ Gasto de transporte guardado — S/45
         Este mes llevas S/180 en transporte 🚕
```

**Buscar información:**
```
Usuario: ¿cuánto gasté esta semana?
  Bot:   📊 Semana del 24–30 marzo:
         🚕 Transporte: S/85
         🍔 Comida: S/142
         Total: S/227
```

**Foto de boleta:**
```
Usuario: [foto de boleta]
  Bot:   📄 Boleta detectada:
         • Establecimiento: Bembos Miraflores
         • Total: S/38.50 (IGV: S/5.85)
         • Fecha: 28/03/2025
         ¿La guardo como gasto de alimentación?
```

---

## 🧪 Tests

```bash
pytest tests/ -v
```

---

## 🗺️ Roadmap

- [x] MVP: guardar, buscar, recordatorios, OCR
- [ ] Transcripción de audios (Whisper)
- [ ] Dashboard web con historial
- [ ] Exportación a PDF para declaración SUNAT
- [ ] Integración con Google Calendar
- [ ] Modo multi-espacio (personal / trabajo)
- [ ] Plan Pro con Stripe

---

## 📄 Licencia

MIT — úsalo, modifícalo, contribuye.

---

## 🤝 Contribuir

1. Fork el repositorio
2. Crea un branch: `git checkout -b feature/nueva-feature`
3. Commit: `git commit -m 'feat: agrega X feature'`
4. Push: `git push origin feature/nueva-feature`
5. Abre un Pull Request

---
