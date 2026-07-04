"""
FastAPI application — exposes the DatabaseAgent over HTTP.

Endpoints:
  GET  /health      — liveness check
  GET  /schema      — returns the full DB schema
  POST /query       — natural language → SQL → answer
"""
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from src.database import Database
from src.agent import DatabaseAgent

# ---------------------------------------------------------------------------
# Shared state — initialised once at startup
# ---------------------------------------------------------------------------
_db: Database | None = None
_agent: DatabaseAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _agent
    _db = Database()
    _agent = DatabaseAgent(db=_db)
    yield
    _db = None
    _agent = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="DB Agent API",
    description="Ask natural-language questions, get SQL-backed answers.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000, example="Which product category has the highest revenue?")


class QueryResponse(BaseModel):
    answer: str
    sql_queries: list[str]
    data: list[dict]
    iterations: int
    success: bool
    latency_ms: float


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def serve_ui():
    index = _frontend / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Frontend not found. Run the Streamlit UI instead."}


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "model": os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")}


@app.get("/schema", tags=["Meta"])
def get_schema():
    if _db is None:
        raise HTTPException(503, "Database not initialised.")
    return {"schema": _db.get_schema()}


@app.post("/query", response_model=QueryResponse, tags=["Agent"])
def query(req: QueryRequest):
    if _agent is None:
        raise HTTPException(503, "Agent not initialised.")

    t0 = time.perf_counter()
    result = _agent.query(req.question)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    return QueryResponse(
        answer=result.answer,
        sql_queries=result.sql_queries,
        data=result.data,
        iterations=result.iterations,
        success=result.success,
        latency_ms=latency_ms,
    )
