"""
Evaluation script — runs gold questions through the agent and measures:
  • execution accuracy  (agent SQL returns same rows as gold SQL)
  • answer rate         (agent produced an answer vs hit max iterations)
  • average iterations

Usage:
  python eval/evaluate.py
"""
import json                    # load gold_queries.json and write results.json
import os                      # unused directly here but kept for parity with other entry scripts
import sys                     # used to extend the import path below
from pathlib import Path       # cross-platform path handling

# This script lives in eval/, but imports from src/ at the project root —
# add the project root to sys.path so `from src...` resolves regardless of cwd.
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv   # reads GROQ_API_KEY etc. from the .env file
load_dotenv()                    # must run before DatabaseAgent() reads os.environ

from src.database import Database      # SQLite wrapper — used to compute gold-SQL ground truth
from src.agent import DatabaseAgent    # the ReAct agent under test

GOLD_PATH = Path(__file__).parent / "gold_queries.json"   # 10 question/gold-SQL pairs


def normalise(rows: list[dict]) -> list[frozenset]:
    """Convert rows to a set of frozensets for order-insensitive comparison."""
    # frozenset of (column, str(value)) pairs — two result sets compare equal
    # regardless of row order or which underlying column ordering SQLite returned.
    return [frozenset((k, str(v)) for k, v in row.items()) for row in rows]


def run_evaluation() -> None:
    db = Database()                # one shared SQLite connection wrapper for all 10 questions
    agent = DatabaseAgent(db=db)   # one shared agent — session_id below keeps questions independent

    with open(GOLD_PATH) as f:
        gold_set = json.load(f)    # list of {"id", "question", "gold_sql"} dicts

    results = []   # accumulate one summary dict per question, written to results.json at the end
    print(f"\nRunning evaluation on {len(gold_set)} questions...\n{'='*60}")

    for item in gold_set:
        qid = item["id"]                # question number, used for logging and session_id
        question = item["question"]     # plain-English question given to the agent
        gold_sql = item["gold_sql"]     # hand-written "correct" SQL for this question

        # Ground truth via gold SQL — run the reference query against the live DB
        gold_result = db.execute(gold_sql)
        gold_rows = gold_result.data if gold_result.success else []   # empty if the gold SQL itself errors

        # Agent answer — a unique session_id per question keeps gold questions
        # independent; otherwise the new conversation-memory feature would let
        # unrelated prior questions leak into each other's context.
        response = agent.query(question, session_id=f"eval-{qid}")
        agent_rows = response.data      # rows from the agent's own last executed SELECT

        # Execution accuracy: do the result sets match, ignoring row/column order?
        exec_match = normalise(gold_rows) == normalise(agent_rows) if gold_rows and agent_rows else False
        answered = response.success and bool(response.answer)   # did the agent produce any answer at all?

        results.append(
            {
                "id": qid,
                "question": question,
                "answered": answered,
                "exec_match": exec_match,
                "iterations": response.iterations,       # how many LLM round-trips this question took
                "sql_queries": response.sql_queries,      # every SELECT the agent attempted
            }
        )

        # Emoji status: ✅ correct match, 💬 answered but rows differ, ❌ never converged
        status = "✅" if exec_match else ("💬" if answered else "❌")
        print(f"{status} Q{qid}: {question[:60]}")
        print(f"     Iterations: {response.iterations} | SQL attempts: {len(response.sql_queries)}")
        if response.sql_queries:
            print(f"     Last SQL: {response.sql_queries[-1][:80]}...")   # preview only — full SQL is in results.json
        print()

    # ── Summary ────────────────────────────────────────────────────────────────
    total = len(results)
    answered_count = sum(r["answered"] for r in results)     # count of True values
    exec_acc = sum(r["exec_match"] for r in results)         # count of exact-match results
    avg_iter = sum(r["iterations"] for r in results) / total  # mean LLM calls per question

    print("=" * 60)
    print(f"EVALUATION SUMMARY")
    print(f"  Total questions : {total}")
    print(f"  Answer rate     : {answered_count}/{total} ({100*answered_count/total:.0f}%)")
    print(f"  Execution match : {exec_acc}/{total} ({100*exec_acc/total:.0f}%)")
    print(f"  Avg iterations  : {avg_iter:.1f}")
    print("=" * 60)

    # Save results — lets you diff runs over time or inspect a failing question in detail
    out_path = Path(__file__).parent / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to {out_path}")


if __name__ == "__main__":
    run_evaluation()   # only run when invoked directly (`python eval/evaluate.py`), not on import
