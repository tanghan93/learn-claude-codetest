"""Utility functions for the myapp package."""


def add(a: int, b: int) -> int:
    """Add two integers together.

    Args:
        a: The first integer.
        b: The second integer.

    Returns:
        The sum of a and b.
    """
    return a + b


def is_palindrome(text: str) -> bool:
    """Check if a string is a palindrome (ignoring case and spaces).

    Args:
        text: The string to check.

    Returns:
        True if the text is a palindrome, False otherwise.
    """
    cleaned = text.replace(" ", "").lower()
    return cleaned == cleaned[::-1]
