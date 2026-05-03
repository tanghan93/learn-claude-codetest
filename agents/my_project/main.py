#!/usr/bin/env python3
"""Main entry point for the project."""

from utils import greet, add


def main():
    name = input("Enter your name: ")
    print(greet(name))

    a = float(input("Enter first number: "))
    b = float(input("Enter second number: "))
    print(f"{a} + {b} = {add(a, b)}")


if __name__ == "__main__":
    main()
