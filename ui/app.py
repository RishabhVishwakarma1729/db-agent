"""
Streamlit chat UI for the DB Agent.
Connects directly to the agent (no API hop needed for local runs).
"""
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Database
from src.agent import DatabaseAgent, AgentResponse

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="DB Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🤖 DB Agent — Ask your database anything")
st.caption("Powered by Groq · llama-3.1-70b-versatile · SQLite")

# ---------------------------------------------------------------------------
# Sidebar — schema viewer + example questions
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📋 Database Schema")
    db = Database()
    schema_text = db.get_schema()
    st.code(schema_text, language="sql")

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
            st.session_state["prefill"] = ex

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent" not in st.session_state:
    st.session_state.agent = DatabaseAgent(db=db)

# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sql_queries"):
            with st.expander("🔍 SQL used"):
                for i, sql in enumerate(msg["sql_queries"], 1):
                    st.code(sql, language="sql")
        if msg.get("data"):
            with st.expander(f"📊 Raw data ({len(msg['data'])} rows)"):
                st.dataframe(pd.DataFrame(msg["data"]), use_container_width=True)
        if msg.get("meta"):
            st.caption(msg["meta"])

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Ask a question about the data…") or prefill

if user_input:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
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
            meta += " · ⚠️ Did not converge"
        st.caption(meta)

    # Persist to history
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response.answer,
            "sql_queries": response.sql_queries,
            "data": response.data,
            "meta": meta,
        }
    )
