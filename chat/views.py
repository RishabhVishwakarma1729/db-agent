"""
views.py — Django view functions that power the DB Agent web app.

Routes:
  GET  /              → serve the Bootstrap chat UI (index.html)
  GET  /api/health/   → liveness check (used by the frontend status dot)
  GET  /api/schema/   → return the full DB schema (loaded into the sidebar)
  POST /api/query/    → accept a natural-language question, run the agent, return JSON
"""

import json          # parse the incoming POST body
import os            # read GROQ_MODEL env var for the health endpoint
import time          # measure end-to-end latency per query

from django.http import JsonResponse          # return JSON without manually setting Content-Type
from django.shortcuts import render           # render an HTML template with context
from django.views.decorators.csrf import csrf_exempt   # allow AJAX POST without CSRF token
from django.views.decorators.http import require_GET, require_POST  # enforce HTTP method
from groq import GroqError, RateLimitError    # base class for all Groq API failures

from .agent_pool import pool   # lazy singleton — creates Database + Agent on first use


def index(request):
    """Serve the single-page Bootstrap chat UI."""
    return render(request, "chat/index.html")


@require_GET   # reject POST/PUT/DELETE with 405 Method Not Allowed
def api_health(request):
    """
    Liveness endpoint — the frontend pings this on page load to show the green dot.
    Returns the active model name so the UI can display it in the header badge.
    """
    return JsonResponse({
        "status": "ok",
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    })


@require_GET
def api_schema(request):
    """
    Return the full database schema as a plain-text string.
    The sidebar <pre> block renders this so the user can see all tables/columns.
    pool.get() initialises the Database and Agent on the first call.
    """
    p = pool.get()                         # ensures DB is initialised before we call get_schema
    return JsonResponse({"schema": p.db.get_schema()})


@csrf_exempt   # AJAX from the same-origin page — CSRF protection not needed here
@require_POST  # only POST is valid — GET would be confusing for a query endpoint
def api_query(request):
    """
    Accept a natural-language question, run it through the ReAct agent, return JSON.

    Request body (JSON):
        { "question": "Who are the top 5 customers by spending?", "session_id": "abc-123" }

    session_id groups a conversation so follow-up questions ("now break that down
    by month") can refer back to earlier turns. The frontend generates one UUID
    per browser tab and reuses it until the user starts a "New chat".

    Response body (JSON):
        {
            "answer":      "The top 5 customers are ...",
            "sql_queries": ["SELECT ..."],
            "data":        [{"name": "Alice", "total": 999.0}, ...],
            "plan":        ["Find revenue by category", "Compare to last year"],
            "iterations":  3,
            "success":     true,
            "latency_ms":  1234.5
        }
    """
    # ── Parse request body ────────────────────────────────────────────────────
    try:
        body = json.loads(request.body)    # request.body is bytes — json.loads handles it
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    question   = (body.get("question") or "").strip()      # clean up leading/trailing whitespace
    session_id = (body.get("session_id") or "default").strip()[:100]  # cap length defensively

    # ── Validate the question length ──────────────────────────────────────────
    if len(question) < 3:
        return JsonResponse({"error": "Question must be at least 3 characters."}, status=400)
    if len(question) > 1000:
        return JsonResponse({"error": "Question too long (max 1000 chars)."}, status=400)

    # ── Run the agent ─────────────────────────────────────────────────────────
    p  = pool.get()                        # get the shared agent instance
    t0 = time.perf_counter()              # start the clock
    try:
        result = p.agent.query(question, session_id=session_id)  # ReAct loop — may take several seconds
    except RateLimitError:
        # Groq's free tier caps tokens/day — surface a clean message instead of
        # a raw 500 page, which is the difference between "demo looks broken"
        # and "demo explains itself" when someone hits the quota.
        return JsonResponse(
            {"error": "The Groq API rate limit was reached. Please try again in a few minutes."},
            status=503,
        )
    except GroqError:
        return JsonResponse(
            {"error": "The LLM provider is temporarily unavailable. Please try again shortly."},
            status=503,
        )
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)   # convert to milliseconds

    # ── Return structured JSON to the frontend ────────────────────────────────
    return JsonResponse({
        "answer":      result.answer,       # plain-English answer from the LLM
        "sql_queries": result.sql_queries,  # list of SELECT queries the agent ran
        "data":        result.data,         # last query's result rows (rendered as table in UI)
        "plan":        result.plan,         # ordered sub-steps the agent announced, if any
        "iterations":  result.iterations,   # number of LLM calls (shows agent reasoning depth)
        "success":     result.success,      # False if agent hit MAX_ITERATIONS
        "latency_ms":  latency_ms,          # total wall-clock time for this request
    })


@csrf_exempt
@require_POST
def api_reset(request):
    """
    Drop a conversation's history — called when the user starts a "New chat".

    Request body (JSON): { "session_id": "abc-123" }
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    session_id = (body.get("session_id") or "").strip()[:100]
    if session_id:
        p = pool.get()
        p.agent.reset_session(session_id)

    return JsonResponse({"status": "ok"})
