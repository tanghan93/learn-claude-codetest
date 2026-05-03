"""Tests for the Calculator module."""

import pytest
from calculator import Calculator, CalculatorError, run_cli


class TestCalculatorBasicOperations:
    """Tests for basic arithmetic operations."""

    def setup_method(self):
        self.calc = Calculator()

    def test_add_two_numbers(self):
        assert self.calc.add(2, 3) == 5

    def test_add_negative_numbers(self):
        assert self.calc.add(-5, 3) == -2

    def test_add_floats(self):
        assert self.calc.add(1.5, 2.5) == 4.0

    def test_add_zero(self):
        assert self.calc.add(0, 0) == 0
        assert self.calc.add(7, 0) == 7

    def test_subtract_two_numbers(self):
        assert self.calc.subtract(10, 3) == 7

    def test_subtract_negative_result(self):
        assert self.calc.subtract(3, 10) == -7

    def test_subtract_floats(self):
        assert self.calc.subtract(5.5, 2.0) == 3.5

    def test_multiply_two_numbers(self):
        assert self.calc.multiply(4, 5) == 20

    def test_multiply_by_zero(self):
        assert self.calc.multiply(5, 0) == 0

    def test_multiply_negative(self):
        assert self.calc.multiply(-3, 4) == -12

    def test_multiply_floats(self):
        assert self.calc.multiply(2.5, 3.0) == 7.5

    def test_divide_exact(self):
        assert self.calc.divide(10, 2) == 5.0

    def test_divide_float_result(self):
        assert self.calc.divide(7, 2) == 3.5

    def test_divide_negative(self):
        assert self.calc.divide(-6, 3) == -2.0

    def test_divide_by_zero_raises_error(self):
        with pytest.raises(CalculatorError, match="Cannot divide by zero"):
            self.calc.divide(10, 0)


class TestCalculatorAdvancedOperations:
    """Tests for advanced operations."""

    def setup_method(self):
        self.calc = Calculator()

    def test_power_positive(self):
        assert self.calc.power(2, 3) == 8

    def test_power_zero_exponent(self):
        assert self.calc.power(5, 0) == 1

    def test_power_negative_exponent(self):
        assert self.calc.power(2, -1) == 0.5

    def test_sqrt_positive(self):
        assert self.calc.sqrt(9) == 3.0

    def test_sqrt_zero(self):
        assert self.calc.sqrt(0) == 0.0

    def test_sqrt_negative_raises_error(self):
        with pytest.raises(CalculatorError, match="square root of a negative"):
            self.calc.sqrt(-4)

    def test_modulo_normal(self):
        assert self.calc.modulo(10, 3) == 1

    def test_modulo_by_zero_raises_error(self):
        with pytest.raises(CalculatorError, match="modulo by zero"):
            self.calc.modulo(5, 0)

    def test_modulo_negative(self):
        assert self.calc.modulo(-5, 3) == 1  # Python's modulo behavior

    def test_factorial_zero(self):
        assert self.calc.factorial(0) == 1

    def test_factorial_positive(self):
        assert self.calc.factorial(5) == 120

    def test_factorial_negative_raises_error(self):
        with pytest.raises(CalculatorError, match="factorial of a negative"):
            self.calc.factorial(-3)

    def test_factorial_non_integer_raises_error(self):
        with pytest.raises(CalculatorError, match="Factorial requires an integer"):
            self.calc.factorial(5.5)

    def test_absolute_positive(self):
        assert self.calc.absolute(5) == 5

    def test_absolute_negative(self):
        assert self.calc.absolute(-5) == 5

    def test_absolute_zero(self):
        assert self.calc.absolute(0) == 0


class TestCalculatorMemory:
    """Tests for memory operations."""

    def setup_method(self):
        self.calc = Calculator()

    def test_memory_store_and_recall(self):
        self.calc.memory_store(42)
        assert self.calc.memory_recall() == 42

    def test_memory_clear(self):
        self.calc.memory_store(42)
        self.calc.memory_clear()
        assert self.calc.memory_recall() is None

    def test_memory_add_to_existing(self):
        self.calc.memory_store(10)
        self.calc.memory_add(5)
        assert self.calc.memory_recall() == 15

    def test_memory_add_when_empty(self):
        self.calc.memory_add(5)
        assert self.calc.memory_recall() == 5

    def test_memory_store_overwrites(self):
        self.calc.memory_store(10)
        self.calc.memory_store(20)
        assert self.calc.memory_recall() == 20

    def test_memory_default_is_none(self):
        assert self.calc.memory_recall() is None


class TestCalculatorHistory:
    """Tests for history tracking."""

    def setup_method(self):
        self.calc = Calculator()

    def test_history_starts_empty(self):
        assert self.calc.history == []

    def test_history_tracks_add(self):
        self.calc.add(1, 2)
        assert len(self.calc.history) == 1
        assert self.calc.history[0][1] == 3

    def test_history_tracks_multiple_operations(self):
        self.calc.add(1, 2)
        self.calc.multiply(3, 4)
        assert len(self.calc.history) == 2

    def test_clear_history(self):
        self.calc.add(1, 2)
        self.calc.clear_history()
        assert self.calc.history == []

    def test_history_is_copy(self):
        """History property should return a copy, not the internal list."""
        self.calc.add(1, 2)
        hist = self.calc.history
        hist.clear()
        assert len(self.calc.history) == 1  # Internal list should be unchanged


class TestCalculatorEdgeCases:
    """Tests for edge cases."""

    def setup_method(self):
        self.calc = Calculator()

    def test_large_numbers(self):
        result = self.calc.add(10**15, 10**15)
        assert result == 2 * 10**15

    def test_very_small_floats(self):
        result = self.calc.multiply(1e-10, 1e-10)
        assert result == pytest.approx(1e-20)

    def test_chained_operations(self):
        """Test operations using previous results."""
        a = self.calc.add(5, 3)      # 8
        b = self.calc.multiply(a, 2)  # 16
        c = self.calc.divide(b, 4)    # 4.0
        assert c == 4.0

    def test_string_representation(self):
        assert "Calculator" in str(self.calc)
        assert "memory" in str(self.calc)

    def test_fractional_power(self):
        result = self.calc.power(9, 0.5)
        assert result == 3.0


class TestCalculatorEvaluateExpression:
    """Tests for expression evaluation."""

    def setup_method(self):
        self.calc = Calculator()

    def test_simple_addition_expression(self):
        result = self.calc.evaluate_expression("1 + 2")
        assert result == 3

    def test_complex_expression(self):
        result = self.calc.evaluate_expression("(2 + 3) * 4")
        assert result == 20

    def test_invalid_expression_raises_error(self):
        with pytest.raises(CalculatorError):
            self.calc.evaluate_expression("1 + 2 +")  # Incomplete expression

    def test_expression_with_invalid_chars_raises_error(self):
        with pytest.raises(CalculatorError, match="invalid characters"):
            self.calc.evaluate_expression("1 + 2; import os")

    def test_expression_adds_to_history(self):
        self.calc.evaluate_expression("10 / 2")
        assert len(self.calc.history) == 1


class TestCalculatorStr:
    """Tests for __str__ method."""

    def setup_method(self):
        self.calc = Calculator()

    def test_str_initial_state(self):
        assert "memory=None" in str(self.calc)
        assert "history_count=0" in str(self.calc)

    def test_str_after_operations(self):
        self.calc.add(1, 2)
        assert "history_count=1" in str(self.calc)

    def test_str_after_memory_store(self):
        self.calc.memory_store(100)
        assert "memory=100" in str(self.calc)
