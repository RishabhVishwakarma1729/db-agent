"""
tools.py — Tool definitions and execution dispatcher for the ReAct agent.

Groq's function-calling API requires two things:
  1. TOOL_DEFINITIONS — JSON schema descriptions the LLM reads to decide which tool to call.
  2. execute_tool()   — Python dispatcher that actually runs the tool and returns results.

The three tools mirror what a human SQL analyst would do:
  get_schema      → open the database and read the table structure
  get_sample_rows → peek at a few rows to understand value formats
  run_sql         → run a SELECT query and read the results
"""

import json                          # used to format tool results as JSON strings
from src.database import Database, QueryResult   # our SQLite wrapper
from src.validator import SQLValidator           # security gate for incoming SQL

# ── Tool schema definitions ───────────────────────────────────────────────────
# These are sent to the LLM on every call so it knows what tools exist.
# The format follows OpenAI / Groq function-calling spec.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            # Description is what the LLM reads to decide when to call this tool
            "description": (
                "Retrieve the complete database schema: all tables, columns, data types, "
                "primary keys, foreign key relationships, and distinct values for key columns. "
                "Call this first when you are unsure about table or column names."
            ),
            # No parameters required — always returns the full schema
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sample_rows",
            "description": (
                "Preview 3 sample rows from a specific table to understand data format, "
                "value ranges, and string casing before writing a query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        # Hints guide the LLM toward correct values
                        "description": "Exact name of the table to sample (e.g. 'customers', 'orders').",
                    }
                },
                "required": ["table_name"],   # the LLM must always provide the table name
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_plan",
            "description": (
                "Announce your plan before starting a multi-part or open-ended question "
                "(e.g. 'give me a report on...', 'analyze...', 'break down...'). Call this "
                "ONCE, before any run_sql calls, with an ordered list of the sub-steps you "
                "intend to take. Skip this entirely for simple single-fact questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "string",
                        "description": (
                            "Ordered sub-steps separated by ' | ', e.g. "
                            "'Find revenue by category | Find top customers | Compare against last year'. "
                            "A flat string, not an array — keeps function-calling reliable."
                        ),
                    }
                },
                "required": ["steps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "Execute a SQL SELECT query against the database and return results as JSON. "
                "Only SELECT statements are allowed — any attempt to modify data will be blocked. "
                "If the query fails, you will receive the error message so you can correct and retry."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A valid SQLite SELECT query.",
                    }
                },
                "required": ["query"],   # the LLM must always provide the SQL string
            },
        },
    },
]


def execute_tool(
    name: str,
    args: dict,
    db: Database,
    validator: SQLValidator,
) -> dict:
    """
    Dispatch a tool call by name and return a JSON-serialisable result dict.

    The dict is appended to the conversation as a 'tool' message so the LLM
    can read the result on the next iteration.

    Args:
        name:      tool name from the LLM's tool_call (e.g. "run_sql")
        args:      parsed arguments dict from the LLM (e.g. {"query": "SELECT ..."})
        db:        open Database instance to execute queries against
        validator: SQLValidator to block non-SELECT statements

    Returns:
        dict with either a result payload or an {"error": "..."} entry
    """

    # ── get_schema ────────────────────────────────────────────────────────────
    if name == "get_schema":
        schema = db.get_schema()           # returns formatted string of all tables/columns
        return {"schema": schema}          # LLM reads this to learn the DB structure

    # ── report_plan ───────────────────────────────────────────────────────────
    # No-op for the database — agent.py intercepts this call to record the plan
    # steps onto AgentResponse.plan before this dispatcher even runs. We still
    # return an ack so the LLM's conversation history stays well-formed.
    if name == "report_plan":
        return {"status": "plan recorded"}

    # ── get_sample_rows ───────────────────────────────────────────────────────
    if name == "get_sample_rows":
        table_name = args.get("table_name", "")         # table the LLM wants to preview
        result: QueryResult = db.get_sample_rows(table_name)
        if result.success:
            # Return the table name + rows so the LLM knows which table these came from
            return {"table": table_name, "rows": result.data, "columns": result.columns}
        return {"error": result.error}     # e.g. "no such table: xyz"

    # ── run_sql ───────────────────────────────────────────────────────────────
    if name == "run_sql":
        query = args.get("query", "")      # the SQL the LLM wants to run

        # Safety gate — reject anything that isn't a pure SELECT
        is_safe, reason = validator.validate(query)
        if not is_safe:
            # Return the rejection reason so the LLM can self-correct
            return {"error": f"Query blocked by safety validator: {reason}"}

        result = db.execute(query)         # run the validated query
        if result.success:
            return {
                "columns": result.columns,
                "data": result.data[:100],            # cap at 100 rows to protect context window
                "row_count": result.row_count,
                "truncated": result.row_count > 100,  # flag if we clipped the result
            }
        return {"error": result.error}     # SQL syntax error, missing column, etc.

    # ── Unknown tool ──────────────────────────────────────────────────────────
    # This should never happen unless the LLM hallucinates a tool name
    return {"error": f"Unknown tool: {name}"}
