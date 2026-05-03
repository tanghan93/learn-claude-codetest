"""Tests for utils module."""

import pytest
from utils import add, subtract, multiply, divide, greet


class TestAdd:
    """Tests for the add function."""

    def test_add_two_positive_numbers(self):
        assert add(1, 2) == 3

    def test_add_positive_and_negative(self):
        assert add(5, -3) == 2

    def test_add_zero(self):
        assert add(0, 0) == 0
        assert add(7, 0) == 7

    def test_add_floats(self):
        assert add(1.5, 2.5) == 4.0


class TestSubtract:
    """Tests for the subtract function."""

    def test_subtract_two_positive_numbers(self):
        assert subtract(5, 3) == 2

    def test_subtract_negative_result(self):
        assert subtract(3, 5) == -2

    def test_subtract_zero(self):
        assert subtract(10, 0) == 10

    def test_subtract_floats(self):
        assert subtract(5.5, 2.0) == 3.5


class TestMultiply:
    """Tests for the multiply function."""

    def test_multiply_two_positive_numbers(self):
        assert multiply(3, 4) == 12

    def test_multiply_by_zero(self):
        assert multiply(5, 0) == 0

    def test_multiply_negative(self):
        assert multiply(-2, 3) == -6

    def test_multiply_floats(self):
        assert multiply(2.5, 2.0) == 5.0


class TestDivide:
    """Tests for the divide function."""

    def test_divide_two_positive_numbers(self):
        assert divide(10, 2) == 5.0

    def test_divide_negative_result(self):
        assert divide(-6, 3) == -2.0

    def test_divide_floats(self):
        assert divide(5.0, 2.0) == 2.5

    def test_divide_by_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            divide(10, 0)


class TestGreet:
    """Tests for the greet function."""

    def test_greet_with_name(self):
        assert greet("Alice") == "Hello, Alice!"

    def test_greet_with_another_name(self):
        assert greet("Bob") == "Hello, Bob!"

    def test_greet_with_empty_string(self):
        assert greet("") == "Hello, !"
