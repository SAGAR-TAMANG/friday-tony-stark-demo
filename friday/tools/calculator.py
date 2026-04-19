"""
Calculator tool — safe arithmetic evaluation using Python's ast module.
No exec/eval with builtins; only whitelisted math operations are allowed.
"""

import ast
import math
import operator

# Whitelisted operators
_OPS: dict = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Whitelisted math functions
_FUNCS: dict = {
    name: getattr(math, name)
    for name in ("sqrt", "log", "log10", "sin", "cos", "tan", "ceil", "floor", "fabs")
}
_CONSTS: dict = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}


def _eval_node(node: ast.AST) -> float:
    """Recursively evaluate a whitelisted AST node."""
    match node:
        case ast.Constant(value=v) if isinstance(v, (int, float)):
            return v
        case ast.Name(id=name) if name in _CONSTS:
            return _CONSTS[name]
        case ast.BinOp(left=l, op=op, right=r) if type(op) in _OPS:
            return _OPS[type(op)](_eval_node(l), _eval_node(r))
        case ast.UnaryOp(op=op, operand=o) if type(op) in _OPS:
            return _OPS[type(op)](_eval_node(o))
        case ast.Call(func=ast.Name(id=fn), args=args) if fn in _FUNCS:
            return _FUNCS[fn](*[_eval_node(a) for a in args])
        case _:
            raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def register(mcp):

    @mcp.tool()
    def calculate(expression: str) -> str:
        """
        Evaluate a mathematical expression and return the result.
        Supports +, -, *, /, **, %, sqrt(), sin(), cos(), log(), pi, e, etc.
        Use when the boss asks for a calculation or quick math.
        Examples: '2 ** 10', 'sqrt(144)', 'sin(pi / 2)', '(100 * 1.08) ** 3'
        """
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            result = _eval_node(tree.body)
            formatted = f"{result:.6g}"  # up to 6 sig figs, drops trailing zeros
            return f"{expression} = {formatted}"
        except ZeroDivisionError:
            return "Division by zero, sir. Check your denominator."
        except Exception as exc:
            return f"Can't evaluate that expression: {exc}"
