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
        { "question": "Who are the top 5 customers by spending?" }

    Response body (JSON):
        {
            "answer":      "The top 5 customers are ...",
            "sql_queries": ["SELECT ..."],
            "data":        [{"name": "Alice", "total": 999.0}, ...],
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

    question = (body.get("question") or "").strip()   # clean up leading/trailing whitespace

    # ── Validate the question length ──────────────────────────────────────────
    if len(question) < 3:
        return JsonResponse({"error": "Question must be at least 3 characters."}, status=400)
    if len(question) > 1000:
        return JsonResponse({"error": "Question too long (max 1000 chars)."}, status=400)

    # ── Run the agent ─────────────────────────────────────────────────────────
    p  = pool.get()                        # get the shared agent instance
    t0 = time.perf_counter()              # start the clock
    result = p.agent.query(question)      # ReAct loop — may take several seconds
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)   # convert to milliseconds

    # ── Return structured JSON to the frontend ────────────────────────────────
    return JsonResponse({
        "answer":      result.answer,       # plain-English answer from the LLM
        "sql_queries": result.sql_queries,  # list of SELECT queries the agent ran
        "data":        result.data,         # last query's result rows (rendered as table in UI)
        "iterations":  result.iterations,   # number of LLM calls (shows agent reasoning depth)
        "success":     result.success,      # False if agent hit MAX_ITERATIONS
        "latency_ms":  latency_ms,          # total wall-clock time for this request
    })
