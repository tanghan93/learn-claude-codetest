"""Utility functions module."""


def add(a, b):
    """Return a + b."""
    return a + b


def subtract(a, b):
    """Return a - b."""
    return a - b


def multiply(a, b):
    """Return a * b."""
    return a * b


def divide(a, b):
    """Return a / b, or raise ValueError for division by zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def greet(name):
    """Return 'Hello, {name}!'.
    
    Args:
        name: The name to greet.
    
    Returns:
        A greeting string.
    """
    return f"Hello, {name}!"
