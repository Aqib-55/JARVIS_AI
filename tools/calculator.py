"""
Calculator tool — safe mathematical expression evaluation.

Supports basic arithmetic without using eval() or exec().
Uses Python's ast module for safe expression parsing.
"""

import ast
import logging
import operator

from tools import ToolCategory, ToolDefinition, ToolParameter, PermissionLevel, ToolResult

logger = logging.getLogger(__name__)

# Allowed binary and unary operators for safe evaluation
_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Maximum power exponent to prevent huge computations
_MAX_POWER = 1000


def _safe_eval(node: ast.AST) -> float | int:
    """
    Recursively evaluate an AST node using only allowed operations.

    Safe because:
    - Only literal numbers and basic arithmetic operators are permitted.
    - No function calls, attribute access, or variable references.
    - Power operations are capped to prevent memory exhaustion.
    """
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        op_func = _BINARY_OPS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")

        left = _safe_eval(node.left)
        right = _safe_eval(node.right)

        # Safety: cap exponentiation
        if isinstance(node.op, ast.Pow):
            if isinstance(right, (int, float)) and abs(right) > _MAX_POWER:
                raise ValueError(f"Exponent too large (max {_MAX_POWER})")

        # Safety: division by zero
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ValueError("Division by zero")

        return op_func(left, right)

    if isinstance(node, ast.UnaryOp):
        op_func = _UNARY_OPS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_func(_safe_eval(node.operand))

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def calculate(expression: str) -> ToolResult:
    """
    Safely evaluate a mathematical expression.

    Supports: +  -  *  /  //  %  **  and parentheses.
    Does NOT support functions, variables, or arbitrary code.

    Args:
        expression: Mathematical expression string (e.g. "2 + 3 * 4").
    """
    try:
        expr = expression.strip()
        if not expr:
            raise ValueError("Empty expression")

        # Parse into an AST and evaluate safely
        tree = ast.parse(expr, mode="eval")
        result = _safe_eval(tree)

        # Clean up floating-point results
        if isinstance(result, float):
            if result == int(result) and abs(result) < 1e15:
                result = int(result)
            else:
                result = round(result, 10)

        return ToolResult(
            success=True,
            result={"expression": expression, "answer": result},
        )

    except (ValueError, SyntaxError, TypeError) as e:
        return ToolResult(success=False, error=f"Cannot evaluate '{expression}': {e}")
    except Exception as e:
        logger.error("Unexpected calculator error: %s", e)
        return ToolResult(success=False, error=f"Calculation error: {e}")


# ---- Tool definition for the registry ----
definition = ToolDefinition(
    name="calculator",
    description="Evaluate a mathematical expression (+, -, *, /, //, %, **, parentheses).",
    parameters=[
        ToolParameter(
            name="expression",
            type="string",
            description="Math expression (e.g. '2 + 3 * 4').",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.PRODUCTIVITY,
)
