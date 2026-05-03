"""CLI greeting tool with customizable options.

Usage:
    python greet.py <name>
    python greet.py <name> --formal
    python greet.py <name> -g "Hi" -e -u -c 3
"""

import argparse


def greet(
    name: str,
    greeting: str = "Hello",
    formal: bool = False,
    excited: bool = False,
    uppercase: bool = False,
) -> str:
    """Generate a greeting message.

    Args:
        name: The name of the person to greet.
        greeting: The greeting word to use (default: "Hello").
        formal: Whether to use formal greeting style.
        excited: Whether to add exclamation marks.
        uppercase: Whether to convert to uppercase.

    Returns:
        A formatted greeting string.
    """
    if formal:
        msg = f"Good day, {name}. Pleased to meet you."
    else:
        if excited:
            msg = f"{greeting}, {name}!!!"
        else:
            msg = f"{greeting}, {name}!"

    if uppercase:
        msg = msg.upper()

    return msg


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Greet a user with a customizable message."
    )
    parser.add_argument("name", help="Name of the person to greet")
    parser.add_argument(
        "--formal",
        action="store_true",
        help="Use formal greeting style",
    )
    parser.add_argument(
        "-g",
        "--greeting",
        default="Hello",
        help="Custom greeting word (default: Hello)",
    )
    parser.add_argument(
        "-e",
        "--excited",
        action="store_true",
        help="Add exclamation marks",
    )
    parser.add_argument(
        "-u",
        "--uppercase",
        action="store_true",
        help="Output greeting in uppercase",
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=1,
        help="Repeat greeting N times (default: 1)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the CLI.

    Args:
        argv: Argument list (for testing, defaults to sys.argv[1:]).
    """
    args = parse_args(argv)
    msg = greet(
        name=args.name,
        greeting=args.greeting,
        formal=args.formal,
        excited=args.excited,
        uppercase=args.uppercase,
    )
    for _ in range(args.count):
        print(msg)


if __name__ == "__main__":
    main()
