import httpx
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
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
]


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load guidelines from DB."""
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
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
            },
            timeout=10.0,
        )

    if response.status_code != 200:
        logger.error(f"Failed to create realtime session: {response.status_code} {response.text}")
        return {"error": "Failed to create session", "detail": response.text}

    data = response.json()
    logger.info(f"Created realtime session: {data.get('id', 'unknown')}")
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
                )
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
            )
        }

    except Exception as e:
        logger.error(f"KB search error: {e}")
        return {
            "result": (
                "I'm having trouble looking that up right now. "
                "You can call us at 587-391-5753 for more details."
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


# ── Static Files ─────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    """Serve the main page."""
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
