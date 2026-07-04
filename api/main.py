"""
FastAPI application — exposes the DatabaseAgent over HTTP.

Endpoints:
  GET  /health      — liveness check
  GET  /schema      — returns the full DB schema
  POST /query       — natural language → SQL → answer
"""
import os                                          # read GROQ_MODEL env var for the health endpoint
import time                                        # measure end-to-end latency per query
from contextlib import asynccontextmanager         # defines FastAPI's startup/shutdown hook below
from pathlib import Path                           # locate the frontend/ static folder

from dotenv import load_dotenv                     # reads GROQ_API_KEY etc. from the .env file
from fastapi import FastAPI, HTTPException         # web framework + typed HTTP error responses
from fastapi.middleware.cors import CORSMiddleware # allow browser requests from other origins
from fastapi.responses import FileResponse         # serve frontend/index.html as a raw file
from fastapi.staticfiles import StaticFiles        # serve frontend/ assets (css/js/images) if present
from pydantic import BaseModel, Field              # request/response schemas with validation

load_dotenv()   # must run before DatabaseAgent() reads os.environ, below

from src.database import Database      # SQLite wrapper — shared schema/query layer
from src.agent import DatabaseAgent    # the ReAct agent loop

# ---------------------------------------------------------------------------
# Shared state — initialised once at startup
# ---------------------------------------------------------------------------
_db: Database | None = None          # module-level singleton, set in lifespan() below
_agent: DatabaseAgent | None = None  # same — avoids reconnecting/recreating the Groq client per request


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts, and once more (after yield) when it shuts down."""
    global _db, _agent
    _db = Database()                 # open the SQLite connection wrapper
    _agent = DatabaseAgent(db=_db)   # create the Groq client + validator, reusing _db
    yield                            # server runs and serves requests here
    _db = None                       # cleanup on shutdown — mainly so re-imports don't see stale state
    _agent = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="DB Agent API",
    description="Ask natural-language questions, get SQL-backed answers.",
    version="1.0.0",
    lifespan=lifespan,   # wires the startup/shutdown hook defined above
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # permissive for a portfolio demo — a real deployment would allowlist origins
    allow_methods=["*"],
    allow_headers=["*"],
)

_frontend = Path(__file__).parent.parent / "frontend"   # static HTML/JS frontend, sibling to api/
if _frontend.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")   # serves any non-HTML assets under /static


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    # min/max length mirror the same guard the Django view applies in chat/views.py
    question: str = Field(..., min_length=3, max_length=1000, example="Which product category has the highest revenue?")


class QueryResponse(BaseModel):
    answer: str              # plain-English answer from the LLM
    sql_queries: list[str]   # every SELECT the agent executed
    data: list[dict]         # last query's result rows
    iterations: int          # number of LLM calls made
    success: bool            # False if the agent hit MAX_ITERATIONS
    latency_ms: float        # total wall-clock time for the request


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)   # excluded from the auto-generated OpenAPI docs
def serve_ui():
    index = _frontend / "index.html"
    if index.exists():
        return FileResponse(str(index))                                  # serve the static frontend page
    return {"message": "Frontend not found. Run the Streamlit UI instead."}   # fallback if frontend/ wasn't shipped


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "model": os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")}


@app.get("/schema", tags=["Meta"])
def get_schema():
    if _db is None:
        raise HTTPException(503, "Database not initialised.")   # only possible if called before lifespan startup completes
    return {"schema": _db.get_schema()}


@app.post("/query", response_model=QueryResponse, tags=["Agent"])
def query(req: QueryRequest):
    if _agent is None:
        raise HTTPException(503, "Agent not initialised.")

    t0 = time.perf_counter()                       # start the clock
    result = _agent.query(req.question)            # ReAct loop — may take several seconds
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)   # convert to milliseconds

    return QueryResponse(
        answer=result.answer,
        sql_queries=result.sql_queries,
        data=result.data,
        iterations=result.iterations,
        success=result.success,
        latency_ms=latency_ms,
    )
