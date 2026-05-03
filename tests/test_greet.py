"""Tests for the greet CLI tool."""

import pytest
from greet import greet, parse_args, main


class TestGreetFunction:
    """Tests for the greet() function."""

    def test_default_greeting(self):
        """Default greeting should produce 'Hello, <name>!'."""
        assert greet("Alice") == "Hello, Alice!"

    def test_custom_greeting(self):
        """Custom greeting word should replace 'Hello'."""
        assert greet("Bob", greeting="Hi") == "Hi, Bob!"

    def test_formal_greeting(self):
        """Formal mode should produce formal greeting."""
        assert greet("Charlie", formal=True) == "Good day, Charlie. Pleased to meet you."

    def test_formal_with_custom_greeting(self):
        """Formal mode should ignore custom greeting word."""
        result = greet("Dave", greeting="Hey", formal=True)
        assert result == "Good day, Dave. Pleased to meet you."

    def test_excited_greeting(self):
        """Excited mode should add extra exclamation marks."""
        assert greet("Eve", excited=True) == "Hello, Eve!!!"

    def test_uppercase_greeting(self):
        """Uppercase mode should convert to uppercase."""
        assert greet("Frank", uppercase=True) == "HELLO, FRANK!"

    def test_excited_uppercase(self):
        """Combined excited and uppercase."""
        result = greet("Grace", excited=True, uppercase=True)
        assert result == "HELLO, GRACE!!!"

    def test_all_options(self):
        """All options combined."""
        result = greet("Heidi", greeting="Yo", excited=True, uppercase=True)
        assert result == "YO, HEIDI!!!"

    def test_empty_name(self):
        """Empty string name."""
        assert greet("") == "Hello, !"

    def test_special_characters(self):
        """Name with special characters."""
        assert greet("Jean-Luc") == "Hello, Jean-Luc!"


class TestParseArgs:
    """Tests for the parse_args() function."""

    def test_name_only(self):
        args = parse_args(["Alice"])
        assert args.name == "Alice"
        assert args.formal is False
        assert args.greeting == "Hello"
        assert args.excited is False
        assert args.uppercase is False
        assert args.count == 1

    def test_formal_flag(self):
        args = parse_args(["Bob", "--formal"])
        assert args.name == "Bob"
        assert args.formal is True

    def test_custom_greeting(self):
        args = parse_args(["Charlie", "-g", "Hi"])
        assert args.greeting == "Hi"

    def test_excited_flag(self):
        args = parse_args(["Dave", "-e"])
        assert args.excited is True

    def test_uppercase_flag(self):
        args = parse_args(["Eve", "-u"])
        assert args.uppercase is True

    def test_count(self):
        args = parse_args(["Frank", "-c", "3"])
        assert args.count == 3

    def test_all_flags(self):
        args = parse_args(["Grace", "--formal", "-g", "Hey", "-e", "-u", "-c", "5"])
        assert args.name == "Grace"
        assert args.formal is True
        assert args.greeting == "Hey"
        assert args.excited is True
        assert args.uppercase is True
        assert args.count == 5


class TestMain:
    """Tests for the main() function using capsys."""

    def test_main_default(self, capsys):
        main(["Alice"])
        captured = capsys.readouterr()
        assert captured.out.strip() == "Hello, Alice!"

    def test_main_formal(self, capsys):
        main(["Bob", "--formal"])
        captured = capsys.readouterr()
        assert captured.out.strip() == "Good day, Bob. Pleased to meet you."

    def test_main_count(self, capsys):
        main(["Charlie", "-c", "3"])
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3
        assert all(line == "Hello, Charlie!" for line in lines)

    def test_main_uppercase(self, capsys):
        main(["Dave", "-u"])
        captured = capsys.readouterr()
        assert captured.out.strip() == "HELLO, DAVE!"
