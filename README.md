# GAIA-Style Agent Benchmark Demo

Small, runnable proof of the exact architecture the "AI Agent Builder" trial
asks for: **Claude Agent SDK + E2B sandboxed code execution + a reproducible
eval harness that reports accuracy *and* cost per task, averaged over 3
runs.**

**Author:** Ainoa Figueroa Vidal

## Honest scope of this demo

This is **not** a submission of the real GAIA benchmark — that requires the
gated Hugging Face dataset and is out of scope for a portfolio piece. It's a
smaller, self-authored task set (`benchmark/tasks.json`) modeled on GAIA's
own conventions: closed-form short answers, multi-step reasoning that must
not be done in free text, and the `FINAL ANSWER: <x>` extraction format GAIA
itself uses. The point is to demonstrate the *pipeline* — agent design,
sandboxed execution, permission gating, reproducible scoring, cost
accounting — not to claim a specific GAIA leaderboard number.

## Architecture

```
task prompt
  -> Claude Agent SDK (claude-opus-4-8, system prompt enforces "compute via
     tool, don't eyeball arithmetic")
  -> run_python tool call (the ONLY tool the model is allowed to use —
     everything else is denied by can_use_tool, fail-closed)
  -> E2B sandbox executes the code, returns stdout/result/error
  -> model reads the result, emits "FINAL ANSWER: <x>"
  -> scorer.py does quasi-exact-match scoring (GAIA-style normalization)
  -> run_benchmark.py repeats 3x, reports accuracy mean/stdev + $/task
```

This mirrors the permission-gate + audit pattern from my
[agent-engineering-demo](https://github.com/Ainoafv/agent-engineering-demo)
(model *proposes*, code *decides*, nothing runs that isn't explicitly
allowed) and the eval-harness discipline from my
[RAG retrieval eval demo](https://github.com/Ainoafv/Demo) (scored eval set,
not vibes-based testing).

## Run it — mock mode (default, no keys, $0, instant)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m benchmark.run_benchmark
```

Mock mode swaps out *only* the model's reasoning step with a scripted
choice of what code to write per task — the `run_python` tool, the sandbox
executor, and the scorer are the exact same code the live agent uses. This
lets anyone review the full pipeline end-to-end without spending API
credits. It is clearly labeled in the output and is never used as a
stand-in for a real benchmark number.

## Run it — live mode (real Claude Agent SDK + real E2B sandbox)

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY and E2B_API_KEY in .env
DEMO_MODE=live python3 -m benchmark.run_benchmark
```

In live mode, `claude-opus-4-8` has to write and debug its own Python for
every task from scratch — the mock solutions in `mock/mock_backend.py` are
never imported on this path. Cost is read directly from the SDK's own
`ResultMessage.total_cost_usd` / `model_usage`, not estimated.

## What I'd change for the real GAIA benchmark (165 tasks)

- Add a `web_search` and a `file_read` tool alongside `run_python` (many GAIA
  tasks need external lookups, not just computation) — same permission-gate
  pattern, just a longer `allowed_tools` list.
- Add a self-verification pass: before emitting `FINAL ANSWER`, ask the model
  to re-derive the answer a second way when the task is numeric, and flag
  disagreement rather than silently pick one.
- Cap `max_turns` / use `task_budget` (a real `ClaudeAgentOptions` field) per
  task so a stuck agent can't burn tokens indefinitely — this is the
  cost-efficiency axis the trial explicitly scores on.
- Run the harness with concurrency (bounded, e.g. 5 tasks in flight) since
  165 tasks x 3 runs sequentially would be slow; the current runner is
  intentionally sequential/simple for readability.

## Repo layout

```
agent/
  sandbox_tool.py   # E2B-backed run_python tool (+ local exec fallback for mock mode)
  gaia_agent.py      # ClaudeSDKClient wiring, permission policy, cost extraction
  prompts.py         # system prompt (GAIA-style FINAL ANSWER convention)
mock/
  mock_backend.py    # offline demo backend — reuses the real tool, scripts the reasoning
benchmark/
  tasks.json         # 8 GAIA-style self-authored tasks (verified answers, see below)
  scorer.py          # quasi-exact-match scoring
  run_benchmark.py   # 3x repeat runner, accuracy mean/stdev + cost report
```

## Note on task correctness

Every `expected_answer` in `tasks.json` was independently computed and
verified with a throwaway script before being committed — three of my first
draft answers were wrong (arithmetic slip, an off-by-one in a combinatorics
exclusion, a date miscalculation) and were corrected before this demo was
written. That verification habit is exactly why an eval harness matters:
I don't trust an answer key, mine or anyone else's, until code has checked
it.
