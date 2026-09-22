from __future__ import annotations

from typing import Any


class ToolRoutingEvaluator:
    """Small deterministic regression suite for reflex routing.

    This does not decide whether an action is safe to execute. The Harness remains
    responsible for permissions, confidence, confirmation, and execution.
    """

    CASES = (
        ("Open Chrome", "open_application", {"name": "Chrome"}),
        ("Launch Discord", "open_application", {"name": "Discord"}),
        ("Open VS Code", "open_application", {"name": "VS Code"}),
        ("Check the status of the VPS", "get_status", {"service": "VPS"}),
        ("Check VPS status", "get_status", {"service": "VPS"}),
        ("Is the VPS running?", "get_status", {"service": "VPS"}),
    )

    NEGATIVE = (
        "Hey Brainbox",
        "How are you?",
        "Who are you?",
        "Thanks bro",
        "Research Shopify",
        "Write Python code",
        "Deploy the backend",
        "Take a screenshot",
    )

    @classmethod
    def evaluate(cls, reflex: Any, tools: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for text, expected_name, expected_args in cls.CASES:
            decision = reflex.decide(text, tools)
            calls = decision.get("function_calls", [])
            actual = calls[0] if calls else None
            ok = bool(actual and actual.get("name") == expected_name and actual.get("arguments") == expected_args)
            results.append({"text": text, "expected": {"name": expected_name, "arguments": expected_args}, "actual": actual, "passed": ok})

        negative_results = []
        for text in cls.NEGATIVE:
            decision = reflex.decide(text, tools)
            calls = decision.get("function_calls", [])
            ok = not calls
            negative_results.append({"text": text, "actual": calls, "passed": ok})

        total = len(results) + len(negative_results)
        passed = sum(x["passed"] for x in results) + sum(x["passed"] for x in negative_results)
        return {"passed": passed, "total": total, "rate": passed / total if total else 1.0, "tool_cases": results, "no_tool_cases": negative_results}
