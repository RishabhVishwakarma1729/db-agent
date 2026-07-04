"""
agent.py — Core ReAct agent loop built from scratch using Groq's function-calling API.

ReAct (Reasoning + Acting) is an agentic pattern where the LLM alternates between:
  - Reasoning: deciding which tool to call next
  - Acting: executing the tool and observing the result
The loop continues until the LLM produces a final text answer (no more tool calls).
"""

import json                          # parse tool-call arguments from the LLM response
import os                            # read GROQ_API_KEY from environment
from dataclasses import dataclass, field  # lightweight value objects (no ORM needed)

from groq import Groq                # Groq SDK — wraps the REST API

from src.database import Database    # our SQLite connection layer
from src.validator import SQLValidator   # blocks destructive SQL before execution
from src.tools import TOOL_DEFINITIONS, execute_tool  # tool schemas + dispatcher

# Safety cap: stop the loop after this many LLM calls to avoid infinite loops
MAX_ITERATIONS = 10

# Default model — llama-3.3-70b-versatile supports reliable function/tool calling
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# System prompt tells the LLM its role, available tools, and rules for using them
SYSTEM_PROMPT = """\
You are an expert SQL data analyst. Users ask you questions in plain English and \
you answer them by querying a SQLite database.

You have three tools:
  • get_schema        — full database schema with tables, columns, FK relationships
  • get_sample_rows   — preview 3 rows of any table to understand data format
  • run_sql           — execute a SELECT query; returns rows or an error message

Working rules:
1. Call get_schema first when you do not know the table/column names.
2. Call get_sample_rows when you need to see how values are formatted \
   (e.g. date format, capitalisation of enums).
3. Write efficient, correct SQLite-compatible SELECT queries only.
4. If run_sql returns an error, carefully read it, fix the SQL, and retry — \
   do not give up after the first failure.
5. Aggregate large result sets in SQL (GROUP BY, COUNT, SUM) — avoid returning \
   thousands of raw rows.
6. When you have enough data to answer, stop calling tools and reply in plain \
   English. Highlight key numbers. Be concise.
7. If the question cannot be answered from the available data, say so clearly.
"""


@dataclass
class AgentResponse:
    """Structured result returned to the Django view after the agent finishes."""
    answer: str                                      # final plain-English answer from the LLM
    sql_queries: list[str] = field(default_factory=list)  # every SELECT the agent executed
    data: list[dict] = field(default_factory=list)   # last query's result rows (shown in UI table)
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

    def query(self, question: str) -> AgentResponse:
        """
        Run the full ReAct loop for a user question and return a structured response.

        Args:
            question: plain-English question from the user (e.g. "top 5 customers by spend")

        Returns:
            AgentResponse with the answer, SQL queries used, and result data.
        """
        # Start the conversation: system instructions + the user's question
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": question},
        ]

        sql_queries: list[str] = []   # collect every SQL query executed during this run
        last_data: list[dict] = []    # keep track of the most recent result rows for the UI

        # ── ReAct loop ────────────────────────────────────────────────────────
        for iteration in range(MAX_ITERATIONS):

            # Send the full conversation history to the LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_DEFINITIONS,   # tell the LLM which tools are available
                tool_choice="auto",       # let the LLM decide whether to call a tool
                temperature=0,            # deterministic output — SQL needs to be consistent
                max_tokens=4096,          # generous token budget for complex multi-step queries
            )

            choice = response.choices[0]   # Groq always returns at least one choice
            msg = choice.message           # the assistant's reply (may contain tool_calls)

            # ── No tool calls → LLM has produced its final answer ─────────────
            if not msg.tool_calls:
                return AgentResponse(
                    answer=msg.content or "No answer generated.",
                    sql_queries=sql_queries,
                    data=last_data,
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

                # Append the tool result so the LLM can read it on the next iteration
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,               # must match the assistant's call ID
                        "content": json.dumps(result, default=str),  # serialize to JSON string
                    }
                )

        # ── Reached MAX_ITERATIONS without a final answer ────────────────────
        return AgentResponse(
            answer="Reached the maximum number of reasoning steps without a final answer. "
                   "Please try rephrasing your question.",
            sql_queries=sql_queries,
            data=last_data,
            iterations=MAX_ITERATIONS,
            success=False,
            error="max_iterations_reached",
        )
