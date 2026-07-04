"""
agent.py — Core ReAct agent loop built from scratch using Groq's function-calling API.

ReAct (Reasoning + Acting) is an agentic pattern where the LLM alternates between:
  - Reasoning: deciding which tool to call next
  - Acting: executing the tool and observing the result
The loop continues until the LLM produces a final text answer (no more tool calls).
"""

import json                          # parse tool-call arguments from the LLM response
import os                            # read GROQ_API_KEY from environment
from collections import OrderedDict  # LRU-style eviction for the session store
from dataclasses import dataclass, field  # lightweight value objects (no ORM needed)

from groq import Groq, BadRequestError   # Groq SDK — wraps the REST API

from src.database import Database    # our SQLite connection layer
from src.validator import SQLValidator   # blocks destructive SQL before execution
from src.tools import TOOL_DEFINITIONS, execute_tool  # tool schemas + dispatcher

# Safety cap: stop the loop after this many LLM calls to avoid infinite loops
MAX_ITERATIONS = 10

# Default model — llama-3.3-70b-versatile supports reliable function/tool calling
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Conversation memory bounds — keeps per-session history from growing unbounded
# in this single-process, in-memory store (fine for a portfolio demo; a real
# deployment would move this to Redis/a DB with TTLs).
MAX_HISTORY_TURNS = 6       # user turns kept per session before the oldest is dropped
MAX_SESSIONS = 200          # oldest session is evicted once this many are active

# System prompt tells the LLM its role, available tools, and rules for using them
SYSTEM_PROMPT = """\
You are an expert SQL data analyst. Users ask you questions in plain English and \
you answer them by querying a SQLite database.

You have four tools:
  • report_plan       — announce an ordered plan before a multi-part question
  • get_schema        — full database schema with tables, columns, FK relationships
  • get_sample_rows   — preview 3 rows of any table to understand data format
  • run_sql           — execute a SELECT query; returns rows or an error message

Working rules:
1. For multi-part or open-ended questions (e.g. "give me a report on...", \
   "analyze...", "break down..."), call report_plan ONCE at the very start \
   with your ordered list of sub-steps, before any other tool call. Skip this \
   for simple single-fact questions.
2. Call get_schema first when you do not know the table/column names.
3. Call get_sample_rows when you need to see how values are formatted \
   (e.g. date format, capitalisation of enums).
4. Write efficient, correct SQLite-compatible SELECT queries only.
5. If run_sql returns an error, carefully read it, fix the SQL, and retry — \
   do not give up after the first failure.
6. Aggregate large result sets in SQL (GROUP BY, COUNT, SUM) — avoid returning \
   thousands of raw rows.
7. When you have enough data to answer, stop calling tools and reply in plain \
   English. Highlight key numbers. Be concise.
8. If the question cannot be answered from the available data, say so clearly.
9. This conversation may continue across follow-up questions (e.g. "now break \
   that down by month"). Use the prior turns in this conversation to resolve \
   references like "that", "those", or "the same customers" instead of asking \
   the user to repeat themselves.
"""


@dataclass
class AgentResponse:
    """Structured result returned to the Django view after the agent finishes."""
    answer: str                                      # final plain-English answer from the LLM
    sql_queries: list[str] = field(default_factory=list)  # every SELECT the agent executed
    data: list[dict] = field(default_factory=list)   # last query's result rows (shown in UI table)
    plan: list[str] = field(default_factory=list)    # ordered sub-steps the agent announced, if any
    iterations: int = 0                              # how many LLM calls were made
    success: bool = True                             # False if the agent hit max iterations
    error: str | None = None                         # machine-readable error code if success=False


class DatabaseAgent:
    """
    Wraps the Groq LLM in a ReAct loop that can query an SQLite database.

    On each iteration:
      1. Send the full conversation history to the LLM.
      2. If the LLM returns tool calls → execute them, append results, loop again.
      3. If the LLM returns plain text → that is the final answer, return it.
    """

    def __init__(self, db: Database | None = None, model: str = DEFAULT_MODEL):
        self.db = db or Database()              # reuse an existing DB connection or create one
        self.validator = SQLValidator()          # validates every query before it runs
        # Initialise the Groq client — reads GROQ_API_KEY from os.environ
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model = model                       # can be overridden per-request

        # Per-session conversation history so follow-up questions ("now break that
        # down by month") can refer back to earlier turns. OrderedDict gives us
        # cheap LRU eviction once MAX_SESSIONS is exceeded — see _get_history().
        self.sessions: OrderedDict[str, list[dict]] = OrderedDict()

    def _get_history(self, session_id: str) -> list[dict]:
        """Fetch (or create) the message history for a session, evicting the oldest if full."""
        if session_id in self.sessions:
            self.sessions.move_to_end(session_id)   # mark as most-recently-used
            return self.sessions[session_id]

        if len(self.sessions) >= MAX_SESSIONS:
            self.sessions.popitem(last=False)        # evict the least-recently-used session

        history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.sessions[session_id] = history
        return history

    def reset_session(self, session_id: str) -> None:
        """Drop a session's history — used by the UI's "New chat" action."""
        self.sessions.pop(session_id, None)

    def query(self, question: str, session_id: str = "default") -> AgentResponse:
        """
        Run the full ReAct loop for a user question and return a structured response.

        Args:
            question:   plain-English question from the user (e.g. "top 5 customers by spend")
            session_id: identifies which conversation this question belongs to, so
                        follow-up questions see prior turns. Defaults to a single
                        shared session for callers that don't track one.

        Returns:
            AgentResponse with the answer, SQL queries used, and result data.
        """
        # Reuse this session's prior turns (or start a fresh one with just the
        # system prompt) so the LLM can resolve references to earlier answers.
        messages = self._get_history(session_id)
        messages.append({"role": "user", "content": question})

        sql_queries: list[str] = []   # collect every SQL query executed during this run
        last_data: list[dict] = []    # keep track of the most recent result rows for the UI
        plan: list[str] = []          # ordered sub-steps the agent announced, if any

        # ── ReAct loop ────────────────────────────────────────────────────────
        for iteration in range(MAX_ITERATIONS):

            # Send the full conversation history to the LLM
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,   # tell the LLM which tools are available
                    tool_choice="auto",       # let the LLM decide whether to call a tool
                    temperature=0,            # deterministic output — SQL needs to be consistent
                    max_tokens=4096,          # generous token budget for complex multi-step queries
                )
            except BadRequestError as e:
                # Groq occasionally rejects a malformed tool call the model emitted
                # (code "tool_use_failed") before we ever see a message to recover
                # from. Retry once forcing plain text so one bad generation can't
                # crash the whole request.
                if getattr(e, "code", None) != "tool_use_failed" and \
                   "tool_use_failed" not in str(e):
                    raise
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="none",       # force a plain-text reply this round
                    temperature=0,
                    max_tokens=4096,
                )

            choice = response.choices[0]   # Groq always returns at least one choice
            msg = choice.message           # the assistant's reply (may contain tool_calls)

            # ── No tool calls → LLM has produced its final answer ─────────────
            if not msg.tool_calls:
                messages.append({"role": "assistant", "content": msg.content or ""})
                self._trim_history(messages)
                return AgentResponse(
                    answer=msg.content or "No answer generated.",
                    sql_queries=sql_queries,
                    data=last_data,
                    plan=plan,
                    iterations=iteration + 1,
                    success=True,
                )

            # ── Append the assistant's message (with tool_calls) to history ───
            # We must serialize tool_calls to plain dicts — the API expects that format
            assistant_msg: dict = {"role": "assistant", "content": msg.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,           # unique ID used to match the tool result back
                    "type": "function",
                    "function": {
                        "name": tc.function.name,        # e.g. "run_sql"
                        "arguments": tc.function.arguments,  # JSON string of kwargs
                    },
                }
                for tc in msg.tool_calls
            ]
            messages.append(assistant_msg)

            # ── Execute each tool and feed the results back to the LLM ────────
            for tc in msg.tool_calls:
                # Parse the JSON arguments the LLM sent (e.g. {"query": "SELECT ..."})
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}   # fall back to empty dict if the LLM sends malformed JSON

                # Dispatch to the correct tool handler (get_schema / get_sample_rows / run_sql)
                result = execute_tool(tc.function.name, args, self.db, self.validator)

                # Track SQL queries and the latest data rows for the UI
                if tc.function.name == "run_sql":
                    if "query" in args:
                        sql_queries.append(args["query"])    # save each executed SQL
                    if result.get("data"):
                        last_data = result["data"]           # overwrite with latest rows

                # Surface the agent's announced plan so the UI can show it as a
                # distinct "reasoning" artifact, separate from the SQL it runs.
                # steps arrives as a " | "-delimited string (see tools.py) — a
                # flat string is far less likely to trip up the model's
                # function-calling than a nested array parameter.
                if tc.function.name == "report_plan":
                    plan.extend(
                        step.strip() for step in args.get("steps", "").split("|") if step.strip()
                    )

                # Append the tool result so the LLM can read it on the next iteration
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,               # must match the assistant's call ID
                        "content": json.dumps(result, default=str),  # serialize to JSON string
                    }
                )

        # ── Reached MAX_ITERATIONS without a final answer ────────────────────
        self._trim_history(messages)
        return AgentResponse(
            answer="Reached the maximum number of reasoning steps without a final answer. "
                   "Please try rephrasing your question.",
            sql_queries=sql_queries,
            data=last_data,
            plan=plan,
            iterations=MAX_ITERATIONS,
            success=False,
            error="max_iterations_reached",
        )

    @staticmethod
    def _trim_history(messages: list[dict]) -> None:
        """
        Cap a session's stored history in place, keeping the system prompt plus
        only the most recent MAX_HISTORY_TURNS user turns. Trims at user-message
        boundaries (never mid-turn) so an assistant's tool_calls are never
        separated from their matching tool-result messages, which the Groq/OpenAI
        API requires to stay adjacent.
        """
        user_indices = [i for i, m in enumerate(messages) if m["role"] == "user"]
        if len(user_indices) > MAX_HISTORY_TURNS:
            cutoff = user_indices[-MAX_HISTORY_TURNS]   # start of the oldest turn to keep
            del messages[1:cutoff]                      # keep system prompt, drop older turns
