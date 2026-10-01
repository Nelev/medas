import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, GreetingName, get_auth_settings
from controller import ask_question, get_conversation, index_upload
from database.database import dispose_engine, get_session, init_engine
from model import greeting_texts, list_conversations
from rag_pipeline.vector_store import init_vector_store
from ratelimit import LIMITS, READ_LIMITS, limiter
from schema import AgentUnavailable, FileTooLarge, NewMessage, NotAPdf, NotFound

# Copies .env into os.environ for what reads it directly rather than through
# a settings class -- the agent's OPENROUTER_API_KEY among them.
load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Fail loudly at boot rather than on the first request: a missing
    # CLERK_SECRET_KEY stops the app here instead of turning every request
    # into a 500.
    get_auth_settings()
    engine = init_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    # Likewise a missing record_chunks table (migrations not run) fails here.
    await init_vector_store(engine)

    yield

    await dispose_engine()


app = FastAPI(lifespan=lifespan)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(NotFound)
async def not_found(_: Request, exc: NotFound) -> JSONResponse:
    # One mapping for every route: a conversation that is someone else's is
    # only indistinguishable from a missing one if every route answers alike.
    return JSONResponse(status_code=404, content={"detail": exc.detail})


@app.exception_handler(AgentUnavailable)
async def agent_unavailable(_: Request, exc: AgentUnavailable) -> JSONResponse:
    logger.error("agent call failed", exc_info=exc.__cause__)
    return JSONResponse(status_code=503, content={"detail": "Assistant unavailable"})


@app.exception_handler(FileTooLarge)
async def file_too_large(_: Request, __: FileTooLarge) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": "File too large"})


@app.exception_handler(NotAPdf)
async def not_a_pdf(_: Request, __: NotAPdf) -> JSONResponse:
    return JSONResponse(status_code=415, content={"detail": "Not a PDF"})


# No CORS middleware: the browser never calls this API directly. The UI's
# requests go through its own server, so every caller here is server-side
# and same-origin rules do not apply.


@app.get("/")
@limiter.limit(READ_LIMITS)
async def init_user_profile(
    request: Request, user_id: CurrentUser, session: SessionDep, name: GreetingName
):
    # The greeting is not persisted: it is the preview shown before the user
    # says anything, and the stored copy is seeded by POST /ask from the same
    # text. Alongside it, the user's past conversations for the sidebar. Signed
    # in or nothing, like every other route here.
    conversations = await list_conversations(session, user_id)
    return {
        "messages": [
            {"role": "assistant", "text": text} for text in greeting_texts(name)
        ],
        "conversations": [{"conversation_id": c} for c in conversations],
    }


@app.post("/ask", status_code=201)
@limiter.limit(LIMITS)
async def ask(
    request: Request,
    message: NewMessage,
    user_id: CurrentUser,
    session: SessionDep,
    name: GreetingName,
    conversationId: uuid.UUID | None = None,
):
    """Ask the agent. Starts a conversation when there is not one yet.

    conversationId is a query parameter rather than a path segment because a
    path segment cannot be absent, and rather than a body field because the
    body is a message and this is not part of one.

    Who is asking comes from the session token, never from the request.
    """
    conversation_id, messages = await ask_question(
        session, user_id, name, message, conversationId
    )
    return {"conversation_id": conversation_id, "messages": messages}


@app.get("/conversations/{conversation_id}")
@limiter.limit(READ_LIMITS)
async def read_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    user_id: CurrentUser,
    session: SessionDep,
):
    messages = await get_conversation(session, user_id, conversation_id)
    return {"conversation_id": conversation_id, "messages": messages}


@app.post("/documents", status_code=201)
@limiter.limit(LIMITS)
async def upload_document(
    request: Request,
    file: UploadFile,
    user_id: CurrentUser,
    session: SessionDep,
    name: GreetingName,
    conversationId: uuid.UUID | None = None,
):
    """Have the agent add a PDF to the signed-in user's record, for it to
    search. Answers like /ask: the conversation, started when there is not
    one yet, and the turns this upload added -- the request and the agent's
    answer, whether it stored the file or refused it.
    """
    conversation_id, messages = await index_upload(
        session, user_id, name, file, conversationId
    )
    return {"conversation_id": conversation_id, "messages": messages}


@app.get("/health/db")
@limiter.limit(LIMITS)
async def health_db(request: Request, session: SessionDep):
    version = await session.scalar(text("SHOW server_version"))
    return {"status": "ok", "server_version": version}
