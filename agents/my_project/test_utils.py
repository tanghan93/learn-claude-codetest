#!/usr/bin/env python3
"""Tests for the utils module."""

import pytest
from utils import greet, add


class TestGreet:
    """Tests for the greet function."""

    def test_greet_with_name(self):
        """Test greet with a normal name."""
        result = greet("Alice")
        assert result == "Hello, Alice! Welcome to the project."

    def test_greet_with_empty_string(self):
        """Test greet with an empty string."""
        result = greet("")
        assert result == "Hello, ! Welcome to the project."

    def test_greet_with_special_characters(self):
        """Test greet with special characters."""
        result = greet("Jean-Pierre")
        assert result == "Hello, Jean-Pierre! Welcome to the project."

    def test_greet_returns_string(self):
        """Test greet returns a string."""
        result = greet("Bob")
        assert isinstance(result, str)


class TestAdd:
    """Tests for the add function."""

    def test_add_two_positive_numbers(self):
        """Test adding two positive numbers."""
        result = add(3, 5)
        assert result == 8

    def test_add_positive_and_negative(self):
        """Test adding a positive and a negative number."""
        result = add(10, -3)
        assert result == 7

    def test_add_two_negative_numbers(self):
        """Test adding two negative numbers."""
        result = add(-4, -6)
        assert result == -10

    def test_add_with_zero(self):
        """Test adding zero to a number."""
        result = add(7, 0)
        assert result == 7

    def test_add_floating_point(self):
        """Test adding floating point numbers."""
        result = add(1.5, 2.3)
        assert result == 3.8

    def test_add_returns_number(self):
        """Test add returns a numeric type."""
        result = add(2, 3)
        assert isinstance(result, (int, float))


if __name__ == "__main__":
    pytest.main([__file__])
