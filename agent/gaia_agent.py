"""Task-solving agent built on the Claude Agent SDK.

Two backends behind one interface (`GaiaAgent.solve`):
  - mock: deterministic, offline, zero-cost — for reviewing the pipeline.
  - live: real ClaudeSDKClient + E2B sandbox — for actual benchmark runs.

Permission policy mirrors agent-engineering-demo: the model may only ever
call `run_python`. Every other tool (bash, file write, web, etc.) is denied
by default — fail closed, not fail open.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from .prompts import SYSTEM_PROMPT
from .sandbox_tool import run_python

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

# Anthropic list pricing for cost-per-task reporting (USD / 1M tokens).
# Update if the client's provided key uses a different rate card.
PRICE_PER_M_INPUT = 15.0
PRICE_PER_M_OUTPUT = 75.0


@dataclass
class AgentResult:
    task_id: str
    answer: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    tool_calls: int = 0
    transcript: list[str] = field(default_factory=list)

    @property
    def is_mock(self) -> bool:
        return self.cost_usd == 0.0 and self.input_tokens == 0


class GaiaAgent:
    def __init__(self, demo_mode: str | None = None):
        self.demo_mode = (demo_mode or os.getenv("DEMO_MODE", "mock")).lower()

    async def solve(self, task: dict) -> AgentResult:
        start = time.perf_counter()
        if self.demo_mode == "mock":
            result = await self._solve_mock(task)
        else:
            result = await self._solve_live(task)
        result.wall_seconds = round(time.perf_counter() - start, 3)
        return result

    # ---- mock backend ------------------------------------------------
    async def _solve_mock(self, task: dict) -> AgentResult:
        from mock.mock_backend import solve_with_mock

        answer, transcript, tool_calls = await solve_with_mock(task)
        return AgentResult(
            task_id=task["id"],
            answer=answer,
            transcript=transcript,
            tool_calls=tool_calls,
        )

    # ---- live backend (real Claude Agent SDK + E2B) -------------------
    async def _solve_live(self, task: dict) -> AgentResult:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            PermissionResultAllow,
            PermissionResultDeny,
            ResultMessage,
            TextBlock,
            create_sdk_mcp_server,
        )

        server = create_sdk_mcp_server(name="gaia-tools", version="1.0.0", tools=[run_python])

        async def can_use_tool(tool_name, _input, _context):
            if tool_name == "mcp__gaia-tools__run_python":
                return PermissionResultAllow()
            return PermissionResultDeny(message="Only run_python is permitted for this task.")

        options = ClaudeAgentOptions(
            model=CLAUDE_MODEL,
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={"gaia-tools": server},
            allowed_tools=["mcp__gaia-tools__run_python"],
            can_use_tool=can_use_tool,
            permission_mode="default",
        )

        transcript: list[str] = []
        tool_calls = 0
        final_text = ""
        input_tokens = output_tokens = 0
        cost_usd = 0.0

        async with ClaudeSDKClient(options=options) as client:
            await client.query(task["prompt"])
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            transcript.append(block.text)
                            final_text += block.text
                        else:
                            tool_calls += 1
                if isinstance(message, ResultMessage):
                    # total_cost_usd is the SDK's own billed cost for the turn —
                    # prefer it over hand-rolling a price table. model_usage
                    # gives per-model token breakdown (camelCase keys) for the
                    # per-task report; fall back to the raw usage dict if a
                    # future SDK version omits model_usage.
                    if message.total_cost_usd is not None:
                        cost_usd = message.total_cost_usd
                    if message.model_usage:
                        mu = next(iter(message.model_usage.values()))
                        input_tokens = mu.get("inputTokens", 0)
                        output_tokens = mu.get("outputTokens", 0)
                        if cost_usd == 0.0:
                            cost_usd = mu.get("costUSD", 0.0)
                    elif message.usage:
                        input_tokens = message.usage.get("input_tokens", 0)
                        output_tokens = message.usage.get("output_tokens", 0)

        if cost_usd == 0.0 and (input_tokens or output_tokens):
            cost_usd = (input_tokens / 1_000_000) * PRICE_PER_M_INPUT + (
                output_tokens / 1_000_000
            ) * PRICE_PER_M_OUTPUT

        answer = _extract_final_answer(final_text)
        return AgentResult(
            task_id=task["id"],
            answer=answer,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost_usd, 6),
            tool_calls=tool_calls,
            transcript=transcript,
        )


def _extract_final_answer(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip().upper().startswith("FINAL ANSWER:"):
            return line.split(":", 1)[1].strip()
    return text.strip().splitlines()[-1] if text.strip() else ""
