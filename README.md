# DB Agent — Natural Language to SQL, Built from Scratch

> Ask your database anything in plain English. The AI agent writes the SQL, runs it, and explains the results.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![Django](https://img.shields.io/badge/Django-6.0-green?logo=django)
![Groq](https://img.shields.io/badge/LLM-Groq%20llama--3.3--70b-orange)
![Bootstrap](https://img.shields.io/badge/UI-Bootstrap%205.3-purple?logo=bootstrap)
![SQLite](https://img.shields.io/badge/DB-SQLite-lightgrey?logo=sqlite)
![Docker](https://img.shields.io/badge/Deploy-Docker-blue?logo=docker)

**🔗 Live demo:** [db-agent-si8m.onrender.com](https://db-agent-si8m.onrender.com/)
*(hosted on Render's free tier — it spins down after ~15 min idle, so the first request after a while can take 30-60s to wake back up)*

---

## The Problem

Answering a data question usually means finding someone who knows SQL, explaining what you want, and waiting for a query back — or learning SQL yourself and reverse-engineering table names and joins from scratch. Non-technical stakeholders end up either blocked on an analyst's time or avoiding the data entirely. DB Agent removes that bottleneck: anyone can ask a plain-English question and get a grounded, data-backed answer immediately, without knowing the schema or writing a single line of SQL — while a safety layer guarantees the underlying database can only ever be read, never modified.

---

## What it does

DB Agent takes a plain-English question, autonomously reasons about the database schema, writes and executes SQL queries, recovers from errors, and returns a concise answer — all without any user writing SQL.

```
User:  "Which product category has the highest revenue in 2024?"
Agent: Calls get_schema → writes SELECT → runs it → answers in plain English
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (Bootstrap UI)                    │
│  Sidebar: DB Schema    │    Chat: Questions & Answers        │
│  Example Questions     │    SQL accordion | Data table       │
└────────────────────────┼────────────────────────────────────┘
                         │ HTTP JSON
┌────────────────────────▼────────────────────────────────────┐
│                   Django Web Server                          │
│  GET  /              → Bootstrap chat page                   │
│  GET  /api/schema/   → DB schema for sidebar                 │
│  POST /api/query/    → run agent, return answer + SQL        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              ReAct Agent Loop  (src/agent.py)               │
│                                                              │
│  ┌─────────────┐     ┌──────────────┐     ┌─────────────┐  │
│  │  get_schema │     │get_sample_rows│     │   run_sql   │  │
│  │  (tools.py) │     │  (tools.py)  │     │  (tools.py) │  │
│  └──────┬──────┘     └──────┬───────┘     └──────┬──────┘  │
│         └──────────────┬────┘                    │          │
│                        ▼                         ▼          │
│              ┌──────────────────┐    ┌──────────────────┐   │
│              │  SQLValidator    │    │    Database       │   │
│              │  (validator.py)  │───▶│  (database.py)   │   │
│              │ blocks non-SELECT│    │   sqlite3 + ORM  │   │
│              └──────────────────┘    └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         │
               ┌─────────▼──────────┐
               │     Groq API       │
               │ llama-3.3-70b      │
               │  (free tier)       │
               └────────────────────┘
```

---

## Key Engineering Decisions

| Decision | Why |
|---|---|
| **ReAct loop from scratch** | No LangChain/LlamaIndex — shows deep understanding of how agents work under the hood |
| **Groq + llama-3.3-70b** | Free tier, ~1-3s responses, reliable function calling |
| **SQL safety validator** | Two-layer defence: regex patterns + sqlparse token walk — blocks DROP/DELETE/UPDATE even if the LLM hallucinates |
| **Django over FastAPI** | Single server for both UI and API — simpler deployment, fewer moving parts |
| **Lazy singleton agent pool** | One Groq client shared across all requests — avoids cold-start latency per request |
| **Eval harness** | 10 gold Q&A pairs with execution accuracy scoring — measurable quality metric |

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Groq API — `llama-3.3-70b-versatile` |
| Agent | Custom ReAct loop with Groq function calling |
| Backend | Django 6 |
| Frontend | Bootstrap 5.3 (dark theme) + vanilla JS |
| Database | SQLite — seeded e-commerce dataset |
| Deployment | Docker + Docker Compose |
| Eval | Custom gold-query benchmark (10 Q&A pairs) |

---

## Dataset

The SQLite database contains a realistic e-commerce dataset:

| Table | Rows | Description |
|---|---|---|
| `customers` | 150 | name, email, city, country, segment |
| `products` | 50 | name, category, price |
| `orders` | 684 | customer_id, status, total_amount, order_date |
| `order_items` | 1,727 | order_id, product_id, quantity, unit_price |
| `reviews` | 381 | product_id, customer_id, rating, review_text |

---

## Getting Started

### Prerequisites
- Python 3.11+
- A free [Groq API key](https://console.groq.com) (no credit card required)

### Local setup

```bash
# 1. Clone the repo
git clone https://github.com/RishabhVishwakarma1729/db-agent.git
cd db-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and set your GROQ_API_KEY

# 4. Seed the database
python db/seed.py

# 5. Start the server
python manage.py runserver

# Open http://localhost:8000
```

### Docker

```bash
cp .env.example .env   # add your GROQ_API_KEY
docker-compose up --build
# Open http://localhost:8000
```

---

## Project Structure

```
db-agent/
├── src/
│   ├── agent.py        # ReAct loop — the core AI engine
│   ├── tools.py        # Tool definitions + execution dispatcher
│   ├── database.py     # SQLite connection + schema introspection
│   └── validator.py    # SQL safety layer (SELECT-only enforcement)
├── chat/
│   ├── views.py        # Django API endpoints
│   ├── agent_pool.py   # Lazy singleton — one agent per process
│   ├── urls.py         # URL routing
│   └── templates/chat/
│       └── index.html  # Bootstrap 5.3 chat UI
├── config/
│   ├── settings.py     # Django configuration
│   └── urls.py         # Root URL router
├── db/
│   └── seed.py         # Seeds the SQLite DB with e-commerce data
├── eval/
│   ├── gold_queries.json  # 10 benchmark Q&A pairs
│   └── evaluate.py        # Execution accuracy scorer
├── manage.py
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Evaluation

Run the benchmark against 10 gold questions:

```bash
python eval/evaluate.py
```

Measures:
- **Answer rate** — did the agent produce an answer vs. hit max iterations?
- **Execution accuracy** — do the agent's SQL results match the gold SQL results?
- **Average iterations** — how many LLM calls per question?

---

## Example Questions

| Question | SQL Complexity |
|---|---|
| Which product category has the highest total revenue? | 2-table JOIN + GROUP BY |
| Who are the top 5 customers by total spending? | JOIN + WHERE + ORDER BY |
| Which products have an average rating below 3? | HAVING clause |
| How many orders were placed each month in 2024? | SQLite date functions |
| What percentage of orders are completed? | Window functions |

---

## Requirements

```
groq>=1.5.0
django>=4.2
python-dotenv==1.0.1
sqlparse==0.5.1
```

---

## Author

**Rishabh Vishwakarma**
- GitHub: [@RishabhVishwakarma1729](https://github.com/RishabhVishwakarma1729)
- Email: rsbvishwa88@gmail.com
