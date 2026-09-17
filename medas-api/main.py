from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import dispose_engine, get_session, init_engine
from schema import MessageRequest


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Fail loudly at boot rather than on the first request.
    engine = init_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    yield

    await dispose_engine()


app = FastAPI(lifespan=lifespan)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/messages")
def create_message(message_request: MessageRequest):
    return {
        "user_name": message_request.user_name,
        "message": message_request.message,
    }

@app.get("/init")
def init_user_profile(user: str):
    return {"messages": [{"role": "assistant", "text": f"Hi {user}, how can I help you?"}]}

@app.get("/health/db")
async def health_db(session: SessionDep):
    version = await session.scalar(text("SHOW server_version"))
    return {"status": "ok", "server_version": version}
