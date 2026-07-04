"""
Streamlit chat UI for the DB Agent.
Connects directly to the agent (no API hop needed for local runs).
"""
import os                  # unused directly, kept for parity with other entry scripts
import sys                 # used to extend the import path below
from pathlib import Path   # cross-platform path handling

import pandas as pd        # renders SQL result rows as an interactive dataframe
import streamlit as st     # the UI framework itself — every st.* call renders a widget
from dotenv import load_dotenv   # reads GROQ_API_KEY etc. from the .env file

load_dotenv()   # must run before DatabaseAgent() reads os.environ, below
# This file lives in ui/, but imports from src/ at the project root —
# add the project root to sys.path so `from src...` resolves regardless of cwd.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Database                  # SQLite wrapper — shared schema/query layer
from src.agent import DatabaseAgent, AgentResponse  # the ReAct agent + its structured result type

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="DB Agent",
    page_icon="🤖",
    layout="wide",                        # use the full browser width, not a centered column
    initial_sidebar_state="expanded",     # show the schema/examples sidebar by default
)

st.title("🤖 DB Agent — Ask your database anything")
st.caption("Powered by Groq · llama-3.1-70b-versatile · SQLite")

# ---------------------------------------------------------------------------
# Sidebar — schema viewer + example questions
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📋 Database Schema")
    db = Database()                    # opens/creates the connection wrapper (no network hop — same process)
    schema_text = db.get_schema()       # formatted string: tables, columns, FKs, sample enum values
    st.code(schema_text, language="sql")   # monospace block so column lists stay aligned

    st.divider()
    st.header("💡 Try these questions")
    examples = [
        "Which product category has the highest total revenue?",
        "Who are the top 5 customers by total spending?",
        "What is the average order value per country?",
        "Which products have an average rating below 3?",
        "How many orders were placed each month in 2024?",
        "What percentage of orders are completed vs cancelled?",
        "Which city has the most Premium segment customers?",
        "What are the top 3 best-selling products by quantity?",
        "Show revenue trend month over month for 2024.",
        "Which customers have placed more than 5 orders?",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["prefill"] = ex   # picked up by the chat input below on next rerun

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
# Streamlit reruns this whole script on every interaction, so anything that
# must survive a rerun (chat history, the agent instance) lives in session_state.
if "messages" not in st.session_state:
    st.session_state.messages = []   # list of {"role", "content", "sql_queries", "data", "meta"} dicts

if "agent" not in st.session_state:
    st.session_state.agent = DatabaseAgent(db=db)   # created once per browser session, reused across reruns

# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):          # styles the bubble as user or assistant
        st.markdown(msg["content"])              # the plain-English answer (or question)
        if msg.get("sql_queries"):
            with st.expander("🔍 SQL used"):     # collapsed by default — click to inspect
                for i, sql in enumerate(msg["sql_queries"], 1):
                    st.code(sql, language="sql")
        if msg.get("data"):
            with st.expander(f"📊 Raw data ({len(msg['data'])} rows)"):
                st.dataframe(pd.DataFrame(msg["data"]), use_container_width=True)
        if msg.get("meta"):
            st.caption(msg["meta"])   # small grey text: iteration count, model name, convergence flag

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
prefill = st.session_state.pop("prefill", "")                  # clicked example question, if any
user_input = st.chat_input("Ask a question about the data…") or prefill

if user_input:
    # Show user message immediately, before the (potentially slow) agent call
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):                                   # spinner while the ReAct loop runs
            response: AgentResponse = st.session_state.agent.query(user_input)

        st.markdown(response.answer)

        if response.sql_queries:
            with st.expander("🔍 SQL used"):
                for i, sql in enumerate(response.sql_queries, 1):
                    st.code(sql, language="sql")

        if response.data:
            with st.expander(f"📊 Raw data ({len(response.data)} rows)"):
                st.dataframe(pd.DataFrame(response.data), use_container_width=True)

        meta = f"Iterations: {response.iterations} · Model: llama-3.1-70b-versatile"
        if not response.success:
            meta += " · ⚠️ Did not converge"    # flags when the agent hit MAX_ITERATIONS without an answer
        st.caption(meta)

    # Persist to history — without this, the answer would vanish on the next Streamlit rerun
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response.answer,
            "sql_queries": response.sql_queries,
            "data": response.data,
            "meta": meta,
        }
    )
