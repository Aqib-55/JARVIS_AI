"""Tests for the calculator tool."""

from tools.calculator import calculate


class TestCalculator:
    """Test suite for safe mathematical expression evaluation."""

    def test_addition(self):
        result = calculate("2 + 3")
        assert result.success is True
        assert result.result["answer"] == 5

    def test_subtraction(self):
        result = calculate("10 - 4")
        assert result.success is True
        assert result.result["answer"] == 6

    def test_multiplication(self):
        result = calculate("6 * 7")
        assert result.success is True
        assert result.result["answer"] == 42

    def test_division(self):
        result = calculate("15 / 3")
        assert result.success is True
        assert result.result["answer"] == 5

    def test_large_sum(self):
        result = calculate("1500 + 2500 + 3000")
        assert result.success is True
        assert result.result["answer"] == 7000

    def test_parentheses(self):
        result = calculate("(5 + 3) * 2")
        assert result.success is True
        assert result.result["answer"] == 16

    def test_exponentiation(self):
        result = calculate("2 ** 10")
        assert result.success is True
        assert result.result["answer"] == 1024

    def test_modulo(self):
        result = calculate("17 % 5")
        assert result.success is True
        assert result.result["answer"] == 2

    def test_floor_division(self):
        result = calculate("17 // 5")
        assert result.success is True
        assert result.result["answer"] == 3

    def test_negative_number(self):
        result = calculate("-5 + 3")
        assert result.success is True
        assert result.result["answer"] == -2

    def test_decimal(self):
        result = calculate("3.14 * 2")
        assert result.success is True
        assert abs(result.result["answer"] - 6.28) < 0.001

    def test_division_by_zero(self):
        result = calculate("10 / 0")
        assert result.success is False
        assert "Division by zero" in result.error

    def test_invalid_expression(self):
        result = calculate("hello + world")
        assert result.success is False

    def test_blocked_function_call(self):
        result = calculate("__import__('os').system('ls')")
        assert result.success is False

    def test_too_large_exponent(self):
        result = calculate("2 ** 10000")
        assert result.success is False
        assert "too large" in result.error.lower()

    def test_empty_expression(self):
        result = calculate("")
        assert result.success is False
