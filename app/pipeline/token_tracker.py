"""TokenTracker — logs every agent call to token_usage.jsonl, aggregates totals."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional


class TokenTracker:
    """Singleton that logs token usage per agent call and computes aggregates.

    Usage::

        tracker = TokenTracker.get()
        tracker.log_call(
            project_dir, scene_id, agent_name="Planner",
            provider="deepseek", model="deepseek-chat",
            prompt_tokens=1200, completion_tokens=400,
        )
        session_total = tracker.session_total_tokens
        project_total = tracker.get_project_total(project_dir)
    """

    _instance: Optional[TokenTracker] = None

    def __init__(self) -> None:
        self._session_total: int = 0
        self._session_prompt: int = 0
        self._session_completion: int = 0
        self._session_cost: float = 0.0  # DeepSeek only

    @classmethod
    def get(cls) -> TokenTracker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for tests)."""
        cls._instance = None

    @property
    def session_total_tokens(self) -> int:
        return self._session_total

    @property
    def session_cost(self) -> float:
        return self._session_cost

    def get_project_total(self, project_dir: Path) -> int:
        """Sum all token counts from the project's token_usage.jsonl."""
        filepath = project_dir / "token_usage.jsonl"
        if not filepath.exists():
            return 0
        total = 0
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    total += entry.get("total_tokens", 0)
                except json.JSONDecodeError:
                    continue
        return total

    def log_call(
        self,
        project_dir: Path,
        scene_id: str,
        agent_name: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int = 0,
    ) -> None:
        """Append one line to token_usage.jsonl and update session totals."""
        total = prompt_tokens + completion_tokens
        self._session_total += total
        self._session_prompt += prompt_tokens
        self._session_completion += completion_tokens

        # DeepSeek cost estimate
        cost = _estimate_cost(provider, model, prompt_tokens, completion_tokens)
        self._session_cost += cost

        entry = {
            "timestamp": time.time(),
            "scene_id": scene_id,
            "agent": agent_name,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
            "cost_usd": round(cost, 6),
            "duration_ms": duration_ms,
        }

        filepath = project_dir / "token_usage.jsonl"
        with open(filepath, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# DeepSeek pricing per 1M tokens (USD)
# deepseek-chat: $0.27/M input, $1.10/M output
# deepseek-reasoner: $0.55/M input, $2.19/M output
DEEPSEEK_PRICING = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}


def _estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a provider/model combination."""
    if provider != "deepseek":
        return 0.0
    input_price, output_price = DEEPSEEK_PRICING.get(model, (0.27, 1.10))
    cost = (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price
    return cost
