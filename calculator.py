"""A comprehensive Calculator program.

This module provides a Calculator class with basic and advanced operations,
memory functionality, and an interactive CLI interface.
"""

import math
import operator
from typing import Union, Optional, List, Tuple

Number = Union[int, float]


class CalculatorError(Exception):
    """Custom exception for calculator errors."""
    pass


class Calculator:
    """A calculator with memory and various math operations."""

    def __init__(self):
        """Initialize calculator with zero memory."""
        self._memory: Optional[Number] = None
        self._history: List[Tuple[str, Number]] = []

    # ---- Basic Operations ----

    def add(self, a: Number, b: Number) -> Number:
        """Return a + b."""
        result = a + b
        self._add_history(f"{a} + {b}", result)
        return result

    def subtract(self, a: Number, b: Number) -> Number:
        """Return a - b."""
        result = a - b
        self._add_history(f"{a} - {b}", result)
        return result

    def multiply(self, a: Number, b: Number) -> Number:
        """Return a * b."""
        result = a * b
        self._add_history(f"{a} * {b}", result)
        return result

    def divide(self, a: Number, b: Number) -> float:
        """Return a / b. Raises CalculatorError if b is zero."""
        if b == 0:
            raise CalculatorError("Cannot divide by zero")
        result = a / b
        self._add_history(f"{a} / {b}", result)
        return result

    # ---- Advanced Operations ----

    def power(self, base: Number, exp: Number) -> Number:
        """Return base raised to the power of exp (base ** exp)."""
        result = base ** exp
        self._add_history(f"{base} ^ {exp}", result)
        return result

    def sqrt(self, x: Number) -> float:
        """Return the square root of x. Raises CalculatorError for negative x."""
        if x < 0:
            raise CalculatorError("Cannot compute square root of a negative number")
        result = math.sqrt(x)
        self._add_history(f"sqrt({x})", result)
        return result

    def modulo(self, a: Number, b: Number) -> Number:
        """Return a % b. Raises CalculatorError if b is zero."""
        if b == 0:
            raise CalculatorError("Cannot compute modulo by zero")
        result = a % b
        self._add_history(f"{a} % {b}", result)
        return result

    def factorial(self, n: int) -> int:
        """Return n! (factorial). Raises CalculatorError for negative or non-integer n."""
        if not isinstance(n, int) or isinstance(n, bool):
            raise CalculatorError("Factorial requires an integer")
        if n < 0:
            raise CalculatorError("Cannot compute factorial of a negative number")
        result = math.factorial(n)
        self._add_history(f"{n}!", result)
        return result

    def absolute(self, x: Number) -> Number:
        """Return the absolute value of x."""
        result = abs(x)
        self._add_history(f"|{x}|", result)
        return result

    # ---- Memory Operations ----

    def memory_store(self, value: Number) -> None:
        """Store a value in memory."""
        self._memory = value

    def memory_recall(self) -> Optional[Number]:
        """Recall the value stored in memory."""
        return self._memory

    def memory_clear(self) -> None:
        """Clear the memory."""
        self._memory = None

    def memory_add(self, value: Number) -> None:
        """Add value to the value currently in memory."""
        if self._memory is None:
            self._memory = value
        else:
            self._memory += value

    # ---- History ----

    @property
    def history(self) -> List[Tuple[str, Number]]:
        """Return the calculation history."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear all calculation history."""
        self._history.clear()

    def _add_history(self, operation: str, result: Number) -> None:
        """Add an entry to the calculation history."""
        self._history.append((operation, result))

    # ---- Utility ----

    def evaluate_expression(self, expression: str) -> Number:
        """Safely evaluate a simple arithmetic expression string.
        
        Supports: +, -, *, /, //, %, **
        Only works with numbers and basic operators.
        """
        allowed_chars = set("0123456789.+-*/%() ")
        if not all(c in allowed_chars for c in expression):
            raise CalculatorError("Expression contains invalid characters")
        try:
            result = eval(expression, {"__builtins__": {}}, {"math": math})
            self._add_history(expression, result)
            return result
        except Exception as e:
            raise CalculatorError(f"Invalid expression: {e}")

    def __str__(self) -> str:
        return f"Calculator(memory={self._memory}, history_count={len(self._history)})"


def run_cli():
    """Run the interactive calculator command-line interface."""
    calc = Calculator()
    print("=" * 50)
    print("         Welcome to the Python Calculator!")
    print("=" * 50)
    print("Commands:")
    print("  add <a> <b>        - Addition")
    print("  sub <a> <b>        - Subtraction")
    print("  mul <a> <b>        - Multiplication")
    print("  div <a> <b>        - Division")
    print("  pow <base> <exp>   - Power")
    print("  sqrt <x>           - Square Root")
    print("  mod <a> <b>        - Modulo")
    print("  fact <n>           - Factorial")
    print("  abs <x>            - Absolute Value")
    print("  ms <value>         - Memory Store")
    print("  mr                 - Memory Recall")
    print("  mc                 - Memory Clear")
    print("  m+ <value>         - Memory Add")
    print("  history            - Show history")
    print("  clear              - Clear history")
    print("  help               - Show this help")
    print("  quit               - Exit")
    print("=" * 50)

    while True:
        try:
            user_input = input("\ncalc> ").strip().lower()
            if not user_input:
                continue

            if user_input == "quit":
                print("Goodbye!")
                break
            elif user_input == "help":
                print("Commands: add, sub, mul, div, pow, sqrt, mod, fact, abs")
                print("          ms, mr, mc, m+, history, clear, quit")
            elif user_input == "history":
                for op, res in calc.history:
                    print(f"  {op} = {res}")
                if not calc.history:
                    print("  No calculations yet.")
            elif user_input == "clear":
                calc.clear_history()
                print("  History cleared.")
            elif user_input == "mr":
                val = calc.memory_recall()
                print(f"  Memory = {val}" if val is not None else "  Memory is empty")
            elif user_input == "mc":
                calc.memory_clear()
                print("  Memory cleared.")
            else:
                parts = user_input.split()
                cmd = parts[0]
                args = parts[1:]

                if cmd == "add":
                    result = calc.add(float(args[0]), float(args[1]))
                elif cmd == "sub":
                    result = calc.subtract(float(args[0]), float(args[1]))
                elif cmd == "mul":
                    result = calc.multiply(float(args[0]), float(args[1]))
                elif cmd == "div":
                    result = calc.divide(float(args[0]), float(args[1]))
                elif cmd == "pow":
                    result = calc.power(float(args[0]), float(args[1]))
                elif cmd == "sqrt":
                    result = calc.sqrt(float(args[0]))
                elif cmd == "mod":
                    result = calc.modulo(float(args[0]), float(args[1]))
                elif cmd == "fact":
                    result = calc.factorial(int(args[0]))
                elif cmd == "abs":
                    result = calc.absolute(float(args[0]))
                elif cmd == "ms":
                    calc.memory_store(float(args[0]))
                    print(f"  Stored {args[0]} to memory")
                    continue
                elif cmd == "m+":
                    calc.memory_add(float(args[0]))
                    print(f"  Memory is now {calc.memory_recall()}")
                    continue
                else:
                    print(f"  Unknown command: {cmd}. Type 'help' for commands.")
                    continue

                print(f"  = {result}")

        except (CalculatorError, ValueError, IndexError) as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    run_cli()
