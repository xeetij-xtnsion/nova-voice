import httpx
import logging
import uuid
from datetime import datetime, date, time
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, Base
from app.models.appointment import Appointment, AppointmentStatus
from app.models.analytics import ChatAnalytics
from app.services.embedding import embedding_service
from app.services.retrieval import retrieve_with_confidence
from app.services.guidelines import load_guidelines, get_guidelines
from app.services.known_topics import build_topic_data
from app.prompts.system_prompt import VOICE_SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Tool definitions for the Realtime API session ────────────────────

REALTIME_TOOLS = [
    {
        "type": "function",
        "name": "search_knowledge_base",
        "description": (
            "Search the Nova Clinic knowledge base for information about services, "
            "practitioners, conditions treated, testing, treatments, and other clinic details. "
            "Use this when the caller asks something specific that isn't covered by get_clinic_info. "
            "The result contains reference info — summarize it naturally in 1-2 sentences "
            "for the caller. Don't read it verbatim."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query based on what the caller is asking about",
                }
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_clinic_info",
        "description": (
            "Get structured clinic information for common topics. "
            "Returns factual clinic data. Give a brief 1-sentence answer first. "
            "Only share more detail if the caller asks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": [
                        "services",
                        "hours",
                        "location",
                        "parking",
                        "practitioners",
                        "consultations",
                        "rescheduling",
                        "testing",
                        "what_to_bring",
                    ],
                    "description": "The clinic topic to get information about",
                }
            },
            "required": ["topic"],
        },
    },
    {
        "type": "function",
        "name": "book_appointment",
        "description": (
            "Book an appointment at Nova Clinic. Call this ONLY after you have collected "
            "all required fields from the caller through conversation: appointment type, "
            "practitioner preference, desired date, desired time, patient name, and phone number. "
            "Do NOT call this until all fields are confirmed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_type": {
                    "type": "string",
                    "description": "Type of appointment, e.g. 'Naturopathic Medicine', 'Acupuncture', 'Massage Therapy', 'IV Therapy', 'Meet and Greet'",
                },
                "practitioner": {
                    "type": "string",
                    "description": "Preferred practitioner name, or 'no preference'",
                },
                "date": {
                    "type": "string",
                    "description": "Requested date in YYYY-MM-DD format",
                },
                "time": {
                    "type": "string",
                    "description": "Requested time in HH:MM format (24-hour)",
                },
                "patient_name": {
                    "type": "string",
                    "description": "Full name of the patient",
                },
                "phone_number": {
                    "type": "string",
                    "description": "Patient's phone number",
                },
            },
            "required": ["appointment_type", "practitioner", "date", "time", "patient_name", "phone_number"],
        },
    },
]


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load guidelines from DB, ensure tables exist."""
    from app.database import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified.")
    logger.info("Loading guidelines from KB...")
    await load_guidelines()
    logger.info("Guidelines loaded. Nova Voice AI ready.")
    yield


app = FastAPI(title="Nova Voice AI", lifespan=lifespan)


# ── API Endpoints ────────────────────────────────────────────────────

@app.get("/api/session")
async def create_session():
    """Create an ephemeral Realtime API session and return the client secret."""
    instructions = VOICE_SYSTEM_PROMPT + get_guidelines()
    voice_session_id = f"voice-{uuid.uuid4().hex[:16]}"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_realtime_model,
                "voice": settings.realtime_voice,
                "instructions": instructions,
                "tools": REALTIME_TOOLS,
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": "low",
                    "create_response": True,
                    "interrupt_response": True,
                },
                "input_audio_noise_reduction": {
                    "type": "near_field",
                },
            },
            timeout=10.0,
        )

    if response.status_code != 200:
        logger.error(f"Failed to create realtime session: {response.status_code} {response.text}")
        return {"error": "Failed to create session", "detail": response.text}

    data = response.json()
    data["voice_session_id"] = voice_session_id
    logger.info(f"Created realtime session: {data.get('id', 'unknown')} (voice: {voice_session_id})")
    return data


class KBSearchRequest(BaseModel):
    query: str


@app.post("/api/tools/search_kb")
async def search_kb(req: KBSearchRequest, db: AsyncSession = Depends(get_db)):
    """Search the knowledge base and return formatted results."""
    try:
        # Embed the query
        query_embedding = await embedding_service.embed_text(req.query)

        # Search pgvector
        result = await retrieve_with_confidence(query_embedding, db)

        if not result["chunks"] or not result["is_confident"]:
            return {
                "result": (
                    "I don't have specific information about that in our knowledge base. "
                    "You might want to call us at 587-391-5753 or email admin@novaclinic.ca "
                    "for more details."
                ),
                "is_knowledge_gap": True,
                "max_similarity": result.get("max_similarity", 0),
                "chunk_count": 0,
                "confidence": "low",
            }

        # Format top chunks into a concise text block
        content_parts = []
        for chunk in result["chunks"][:5]:  # Limit to top 5 for voice brevity
            heading = chunk.get("section_heading", "")
            content = chunk["content"].strip()
            if heading:
                content_parts.append(f"[{heading}]: {content}")
            else:
                content_parts.append(content)

        combined = "\n\n".join(content_parts)

        return {
            "result": (
                f"Here is the relevant information from our knowledge base. "
                f"Summarize this naturally in 1-2 conversational sentences for the caller. "
                f"Do not read it word for word:\n\n{combined}"
            ),
            "is_knowledge_gap": False,
            "max_similarity": result.get("max_similarity", 0),
            "chunk_count": len(result["chunks"]),
            "confidence": "high",
        }

    except Exception as e:
        logger.error(f"KB search error: {e}")
        return {
            "result": (
                "I'm having trouble looking that up right now. "
                "You can call us at 587-391-5753 for more details."
            )
        }


class BookAppointmentRequest(BaseModel):
    appointment_type: str
    practitioner: str
    date: str
    time: str
    patient_name: str
    phone_number: str
    session_id: Optional[str] = None


@app.post("/api/tools/book_appointment")
async def book_appointment(req: BookAppointmentRequest, db: AsyncSession = Depends(get_db)):
    """Book an appointment and store it in the shared database."""
    logger.info(
        f"BOOKING REQUEST: name={req.patient_name} phone={req.phone_number} "
        f"type={req.appointment_type} practitioner={req.practitioner} "
        f"date={req.date} time={req.time} session={req.session_id}"
    )
    try:
        # Parse date — handle common formats
        try:
            appt_date = date.fromisoformat(req.date)
        except ValueError:
            from dateutil import parser as dateparser
            appt_date = dateparser.parse(req.date).date()

        # Parse time — handle HH:MM, HH:MM:SS, and natural formats like "2:00 PM"
        try:
            appt_time = time.fromisoformat(req.time)
        except ValueError:
            from dateutil import parser as dateparser
            appt_time = dateparser.parse(req.time).time()

        appointment = Appointment(
            patient_name=req.patient_name,
            phone=req.phone_number,
            service=req.appointment_type,
            practitioner=req.practitioner if req.practitioner.lower() != "no preference" else None,
            delivery_mode="In-person",
            appointment_date=appt_date,
            appointment_time=appt_time,
            status=AppointmentStatus.pending,
            session_id=req.session_id,
            notes="Booked via Nova Voice AI",
        )
        db.add(appointment)
        await db.commit()

        logger.info(
            f"APPOINTMENT SAVED: {req.patient_name} | {req.phone_number} | "
            f"{req.appointment_type} with {req.practitioner} on {appt_date} at {appt_time}"
        )

        return {
            "result": (
                f"Appointment confirmed! Here are the details to read back to the caller:\n"
                f"- Type: {req.appointment_type}\n"
                f"- Practitioner: {req.practitioner}\n"
                f"- Date: {req.date}\n"
                f"- Time: {req.time}\n"
                f"- Patient: {req.patient_name}\n"
                f"- Phone: {req.phone_number}\n\n"
                f"Summarize the booking naturally in 1-2 sentences. "
                f"Let them know we'll send a confirmation to their phone number."
            )
        }

    except Exception as e:
        logger.error(f"Booking error: {e}", exc_info=True)
        await db.rollback()
        return {
            "result": (
                "I'm sorry, there was a problem saving the appointment. "
                "Please try again or call us directly at 587-391-5753."
            )
        }


class ClinicInfoRequest(BaseModel):
    topic: str


@app.post("/api/tools/get_clinic_info")
async def get_clinic_info(req: ClinicInfoRequest):
    """Return structured clinic info for a known topic."""
    data = build_topic_data(req.topic)

    if not data:
        return {
            "result": "I don't have information about that topic. Please try asking about our services, hours, location, parking, practitioners, consultations, rescheduling, testing, or what to bring."
        }

    detail = data.get("detail", "")
    return {
        "result": (
            f"Here is the clinic information. Give a brief 1-sentence answer first. "
            f"Only share more if the caller asks:\n\n{detail}"
        )
    }


# ── Debug: KB status ─────────────────────────────────────────────

@app.get("/api/debug/kb-status")
async def kb_status(db: AsyncSession = Depends(get_db)):
    """Check KB connectivity and chunk count."""
    from sqlalchemy import text
    try:
        row = await db.execute(text(
            "SELECT COUNT(*) as total, "
            "COUNT(*) FILTER (WHERE kb_version = :v) as version_match "
            "FROM kb_chunks"
        ), {"v": settings.kb_version})
        r = row.one()
        versions = await db.execute(text(
            "SELECT kb_version, COUNT(*) as cnt FROM kb_chunks GROUP BY kb_version ORDER BY kb_version"
        ))
        guidelines_text = get_guidelines()
        return {
            "total_chunks": r.total,
            "version_match": r.version_match,
            "kb_version_config": settings.kb_version,
            "versions": {str(v.kb_version): v.cnt for v in versions.all()},
            "guidelines_length": len(guidelines_text),
            "guidelines_preview": guidelines_text[:3000] if guidelines_text else "(empty)",
        }
    except Exception as e:
        return {"error": str(e)}



# ── Conversation Logging ─────────────────────────────────────────────

class LogConversationRequest(BaseModel):
    session_id: str
    question: str
    answer: str
    route_taken: str = "standard"
    confidence: str = "high"
    max_similarity: Optional[float] = None
    chunk_count: int = 0
    is_knowledge_gap: bool = False


@app.post("/api/log_conversation")
async def log_conversation(req: LogConversationRequest, db: AsyncSession = Depends(get_db)):
    """Log a voice conversation turn to the shared analytics table."""
    try:
        entry = ChatAnalytics(
            session_id=req.session_id,
            question=req.question,
            answer=req.answer,
            response_source="voice",
            route_taken=req.route_taken,
            confidence=req.confidence,
            max_similarity=req.max_similarity,
            chunk_count=req.chunk_count,
            is_knowledge_gap=req.is_knowledge_gap,
            sentiment="neutral",
        )
        db.add(entry)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Conversation log error: {e}")
        await db.rollback()
        return {"status": "error"}


# ── Static Files ─────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    """Serve the main page."""
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
