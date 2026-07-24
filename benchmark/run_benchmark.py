"""Reproducible benchmark runner.

    python -m benchmark.run_benchmark            # DEMO_MODE from .env / default mock
    DEMO_MODE=live python -m benchmark.run_benchmark

Runs the full task set REPEATS times (default 3, per the job spec: "informed
in 3 runs, mean + dispersion, not a single cherry-picked number"), scores
each attempt, and reports accuracy mean/stdev plus total and per-task cost
read from the model's own usage numbers (real cost in live mode, $0 in mock
mode since no API is called).
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from agent.gaia_agent import GaiaAgent  # noqa: E402
from benchmark.scorer import is_correct  # noqa: E402

TASKS_PATH = Path(__file__).parent / "tasks.json"
REPEATS = int(os.getenv("BENCHMARK_REPEATS", "3"))


async def run_once(agent: GaiaAgent, tasks: list[dict]) -> dict:
    correct, total_cost, total_in, total_out = 0, 0.0, 0, 0
    per_task = []
    for task in tasks:
        r = await agent.solve(task)
        ok = is_correct(r.answer, task["expected_answer"])
        correct += ok
        total_cost += r.cost_usd
        total_in += r.input_tokens
        total_out += r.output_tokens
        per_task.append(
            {
                "id": task["id"],
                "correct": ok,
                "predicted": r.answer,
                "expected": task["expected_answer"],
                "cost_usd": r.cost_usd,
                "tool_calls": r.tool_calls,
            }
        )
    return {
        "accuracy": correct / len(tasks),
        "cost_usd": total_cost,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "per_task": per_task,
    }


async def main() -> None:
    tasks = json.loads(TASKS_PATH.read_text())
    agent = GaiaAgent()
    runs = [await run_once(agent, tasks) for _ in range(REPEATS)]

    accuracies = [r["accuracy"] for r in runs]
    costs = [r["cost_usd"] for r in runs]
    mean_acc = statistics.mean(accuracies)
    stdev_acc = statistics.stdev(accuracies) if len(accuracies) > 1 else 0.0

    print(f"\nDEMO_MODE = {agent.demo_mode}")
    print(f"Tasks per run: {len(tasks)}  |  Runs: {REPEATS}\n")
    print(f"{'run':<6}{'accuracy':<12}{'cost_usd':<12}")
    for i, r in enumerate(runs, 1):
        print(f"{i:<6}{r['accuracy']*100:>7.1f}%    ${r['cost_usd']:<10.4f}")
    print("-" * 30)
    print(f"mean   {mean_acc*100:>7.1f}%    ${statistics.mean(costs):<10.4f}")
    print(f"stdev  {stdev_acc*100:>7.1f}pp")

    if agent.demo_mode == "mock":
        print(
            "\n[mock mode] Accuracy above reflects the scripted demo backend,\n"
            "not a real claude-opus-4-8 run. Set DEMO_MODE=live with real\n"
            "ANTHROPIC_API_KEY / E2B_API_KEY to produce submittable numbers."
        )

    out_path = Path(__file__).parent / "results.json"
    out_path.write_text(json.dumps({"runs": runs, "mean_accuracy": mean_acc, "stdev_accuracy": stdev_acc}, indent=2))
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
