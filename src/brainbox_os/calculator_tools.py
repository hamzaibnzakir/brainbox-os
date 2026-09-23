from __future__ import annotations

import ast
import math
from typing import Any


_ALLOWED_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_ALLOWED_UNARY = {ast.UAdd: lambda a: +a, ast.USub: lambda a: -a}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent is too large")
        return _ALLOWED_BINOPS[type(node.op)](left, right)
    raise ValueError("Unsupported arithmetic expression")


def calculate_expression(expression: str) -> dict[str, Any]:
    """Evaluate a simple arithmetic expression exactly without executing arbitrary code."""
    expression = expression.strip().replace("×", "*").replace("÷", "/")
    if not expression or len(expression) > 200:
        raise ValueError("Expression must be 1 to 200 characters")
    tree = ast.parse(expression, mode="eval")
    result = _eval(tree.body)
    if not math.isfinite(result):
        raise ValueError("Result is not finite")
    if result.is_integer():
        value: int | float = int(result)
    else:
        value = result
    return {"expression": expression, "result": value}


def register_calculator_tools(registry: Any) -> None:
    from .execution import ToolSpec
    from .policy import Risk

    registry.register(ToolSpec(
        name="calculate_expression",
        function=calculate_expression,
        risk=Risk.READ,
        description="Calculate a simple arithmetic expression exactly. Use this for arithmetic instead of guessing or relying on visual keyboard entry. Supports +, -, *, /, %, ** and parentheses.",
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string", "maxLength": 200}},
            "required": ["expression"],
        },
    ))


def parse_arithmetic_request(text: str) -> dict[str, Any] | None:
    """Extract a simple two operand arithmetic request from natural language."""
    import re
    normalized = text.lower().replace(",", "")
    pattern = re.compile(
        r"\b(\d+(?:\.\d+)?)\s*(?:times|multiplied by|multiply by|x|\*)\s*(\d+(?:\.\d+)?)\b"
    )
    match = pattern.search(normalized)
    if match:
        expression = f"{match.group(1)} * {match.group(2)}"
    else:
        pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:plus|\+)\s*(\d+(?:\.\d+)?)\b")
        match = pattern.search(normalized)
        if match:
            expression = f"{match.group(1)} + {match.group(2)}"
        else:
            pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:minus|subtract)\s*(\d+(?:\.\d+)?)\b")
            match = pattern.search(normalized)
            if match:
                expression = f"{match.group(1)} - {match.group(2)}"
            else:
                pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:divided by|divide by|/)\s*(\d+(?:\.\d+)?)\b")
                match = pattern.search(normalized)
                if match:
                    expression = f"{match.group(1)} / {match.group(2)}"
                else:
                    return None
    return {"expression": expression, "open_calculator": bool(re.search(r"\bcalculator\b", normalized))}
