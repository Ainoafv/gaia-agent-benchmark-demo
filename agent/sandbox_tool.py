"""E2B-backed code-execution tool exposed to the Claude Agent SDK.

Real mode: spins up an E2B sandbox per task, runs the model's Python, returns
stdout/stderr/result. Mock mode: executes the same code locally in-process
(still real Python execution, just without the sandbox boundary) so the demo
runs offline with zero API cost while exercising the identical tool-call
contract the live agent uses.

Security note (same pattern as agent-engineering-demo): the sandbox tool is
the *only* side-effecting capability we hand to the model. Everything else is
denied by the permission policy in gaia_agent.py — fail closed.
"""
from __future__ import annotations

import contextlib
import io
import os
import traceback

from claude_agent_sdk import tool

DEMO_MODE = os.getenv("DEMO_MODE", "mock").lower()


async def _run_in_e2b(code: str) -> dict:
    from e2b_code_interpreter import Sandbox

    sbx = Sandbox.create()
    try:
        execution = sbx.run_code(code)
        stdout = "".join(getattr(execution.logs, "stdout", []) or [])
        stderr = "".join(getattr(execution.logs, "stderr", []) or [])
        result = execution.text if execution.results else None
        error = str(execution.error) if execution.error else None
        return {"stdout": stdout, "stderr": stderr, "result": result, "error": error}
    finally:
        sbx.kill()


async def _run_locally(code: str) -> dict:
    """Mock-mode executor: real Python exec(), no sandbox isolation.

    Only ever used with DEMO_MODE=mock against synthetic benchmark tasks —
    never with untrusted input, and never in the live-mode code path.
    """
    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    # Single namespace (not separate globals/locals): a def'd helper function
    # inside `code` needs to resolve other top-level names as free variables,
    # which only works reliably when exec() globals and locals are the same
    # dict — otherwise CPython can't see them via LOAD_GLOBAL.
    namespace: dict = {"__name__": "__main__"}
    error = None
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            exec(code, namespace)
    except Exception:
        error = traceback.format_exc(limit=3)
    result = namespace.get("result")
    return {
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "result": str(result) if result is not None else None,
        "error": error,
    }


@tool(
    "run_python",
    "Execute Python code in an isolated sandbox and return stdout/stderr/result. "
    "Use this for any calculation, data parsing, or multi-step logic instead of "
    "reasoning about arithmetic in free text.",
    {"code": str},
)
async def run_python(args: dict) -> dict:
    code = args["code"]
    outcome = await (_run_locally(code) if DEMO_MODE == "mock" else _run_in_e2b(code))
    text = (
        f"stdout:\n{outcome['stdout']}\n"
        f"result: {outcome['result']}\n"
        f"error: {outcome['error'] or 'none'}"
    )
    return {"content": [{"type": "text", "text": text}]}
