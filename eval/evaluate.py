"""
Evaluation script — runs gold questions through the agent and measures:
  • execution accuracy  (agent SQL returns same rows as gold SQL)
  • answer rate         (agent produced an answer vs hit max iterations)
  • average iterations

Usage:
  python eval/evaluate.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.database import Database
from src.agent import DatabaseAgent

GOLD_PATH = Path(__file__).parent / "gold_queries.json"


def normalise(rows: list[dict]) -> list[frozenset]:
    """Convert rows to a set of frozensets for order-insensitive comparison."""
    return [frozenset((k, str(v)) for k, v in row.items()) for row in rows]


def run_evaluation() -> None:
    db = Database()
    agent = DatabaseAgent(db=db)

    with open(GOLD_PATH) as f:
        gold_set = json.load(f)

    results = []
    print(f"\nRunning evaluation on {len(gold_set)} questions...\n{'='*60}")

    for item in gold_set:
        qid = item["id"]
        question = item["question"]
        gold_sql = item["gold_sql"]

        # Ground truth via gold SQL
        gold_result = db.execute(gold_sql)
        gold_rows = gold_result.data if gold_result.success else []

        # Agent answer
        response = agent.query(question)
        agent_rows = response.data

        # Execution accuracy: do the result sets match?
        exec_match = normalise(gold_rows) == normalise(agent_rows) if gold_rows and agent_rows else False
        answered = response.success and bool(response.answer)

        results.append(
            {
                "id": qid,
                "question": question,
                "answered": answered,
                "exec_match": exec_match,
                "iterations": response.iterations,
                "sql_queries": response.sql_queries,
            }
        )

        status = "✅" if exec_match else ("💬" if answered else "❌")
        print(f"{status} Q{qid}: {question[:60]}")
        print(f"     Iterations: {response.iterations} | SQL attempts: {len(response.sql_queries)}")
        if response.sql_queries:
            print(f"     Last SQL: {response.sql_queries[-1][:80]}...")
        print()

    # Summary
    total = len(results)
    answered_count = sum(r["answered"] for r in results)
    exec_acc = sum(r["exec_match"] for r in results)
    avg_iter = sum(r["iterations"] for r in results) / total

    print("=" * 60)
    print(f"EVALUATION SUMMARY")
    print(f"  Total questions : {total}")
    print(f"  Answer rate     : {answered_count}/{total} ({100*answered_count/total:.0f}%)")
    print(f"  Execution match : {exec_acc}/{total} ({100*exec_acc/total:.0f}%)")
    print(f"  Avg iterations  : {avg_iter:.1f}")
    print("=" * 60)

    # Save results
    out_path = Path(__file__).parent / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to {out_path}")


if __name__ == "__main__":
    run_evaluation()
