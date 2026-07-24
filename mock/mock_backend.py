"""Deterministic offline backend for DEMO_MODE=mock.

Important: this does NOT skip code execution. Each task still runs through
the exact same `run_python` tool contract the live agent uses (same function,
same input/output shape) — it just replaces the *LLM's* choice of what code
to write with a fixed snippet, so a reviewer can see the full pipeline
(task -> tool call -> sandboxed execution -> scored answer) without an
Anthropic or E2B API key.

Swapping DEMO_MODE=live removes this file from the call path entirely; the
model then has to write and debug its own code from scratch.
"""
from __future__ import annotations

from agent.sandbox_tool import run_python

_SOLUTIONS: dict[str, str] = {
    "t1_compound_interest": "result = round(4200 * (1.065 ** 7), 2)",
    "t2_median_from_text": (
        "vals = [214,198,231,205,260,199,222,241,189,250,217]\n"
        "s = sorted(vals)\n"
        "result = s[len(s)//2]"
    ),
    "t3_threshold_count": (
        "temps = [21,24,19,27,30,22,18,26,31,20,23,29,17,25]\n"
        "result = sum(1 for t in temps if t > 24)"
    ),
    "t4_table_aggregate": (
        "rows = [('widgetA','tools',12,3.50),('widgetB','tools',5,7.25),"
        "('gadgetC','parts',20,1.10),('gadgetD','parts',8,2.75),('widgetE','tools',3,9.00)]\n"
        "result = round(sum(q*p for _, cat, q, p in rows if cat == 'tools'), 2)"
    ),
    "t5_word_puzzle": (
        "import re\n"
        "sentence = 'Curious biologists quietly examine rare orchids near flooded gullies.'\n"
        "words = re.findall(r'[A-Za-z]+', sentence)\n"
        "vowels = set('aeiouAEIOU')\n"
        "def has_gap_pair(w):\n"
        "    idxs = [i for i, ch in enumerate(w) if ch in vowels]\n"
        "    return any(idxs[j]-idxs[i] >= 2 for i in range(len(idxs)) for j in range(i+1, len(idxs)))\n"
        "result = sum(1 for w in words if has_gap_pair(w))"
    ),
    "t6_unit_conversion": (
        "d1 = 42 * (25/60)\n"
        "d2 = 18 * (40/60)\n"
        "result = round((d1 + d2) * 1000)"
    ),
    "t7_date_arithmetic": (
        "import datetime\n"
        "start = datetime.date(2026, 3, 6)\n"
        "end = start + datetime.timedelta(days=45)\n"
        "result = end.strftime('%A')"
    ),
    "t8_combinatorics": (
        "import math\n"
        "total = math.comb(9, 3)\n"
        "bad = math.comb(7, 1)\n"
        "result = total - bad"
    ),
}


async def solve_with_mock(task: dict) -> tuple[str, list[str], int]:
    code = _SOLUTIONS.get(task["id"])
    if code is None:
        return "", [f"[mock] no scripted solution for {task['id']}"], 0

    transcript = [f"[mock reasoning] delegating to run_python for task {task['id']}"]
    # run_python is wrapped by the SDK's @tool decorator into an SdkMcpTool;
    # .handler is the actual async function, same one the live agent invokes.
    tool_output = await run_python.handler({"code": code})
    text = tool_output["content"][0]["text"]
    transcript.append(text)

    result_line = next((l for l in text.splitlines() if l.startswith("result:")), "result: ")
    answer = result_line.split("result:", 1)[1].strip()
    transcript.append(f"FINAL ANSWER: {answer}")
    return answer, transcript, 1
