import re
from typing import List, Tuple

from xdsl.utils.lexer import Location

from ast_nodes import BinaryExprAST, CallExprAST, ExprAST, FunctionAST, ModuleAST, NumberExprAST, PrintExprAST, PrototypeAST, StringExprAST, VariableExprAST


class Parser:
    def __init__(self, program: str, filename: str = "<string>"):
        self.filename = filename
        self.tokens = self._tokenize(program)
        self.pos = 0

    def _tokenize(self, text: str) -> List[Tuple[str, int, int]]:
        tokens, line, line_start = [], 1, 0
        parts = text.split('"')

        for i, part in enumerate(parts):
            if i % 2 == 1:
                tokens.append((f'"{part}"', line, len("".join(parts[:i])) - line_start + 1))
                continue

            for match in re.finditer(r";[^\n]*|([()])|([^\s()]+)|\n", part):
                text_val = match.group()

                if text_val == "\n":
                    line += 1
                    line_start = len("".join(parts[:i])) + match.end()
                    continue

                if text_val.startswith(";") or not text_val.strip():
                    continue

                abs_pos = len("".join(parts[:i])) + match.start()
                tokens.append((text_val, line, abs_pos - line_start + 1))

        return tokens

    def _peek(self, offset: int = 0):
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _consume(self):
        if self.pos >= len(self.tokens):
            raise Exception("Unexpected EOF")
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def _expect(self, expected: str):
        t = self._peek()
        if t and t[0] == expected:
            return self._consume()

        t_str = t[0] if t else "EOF"
        loc = self._loc(t) if t else Location(self.filename, 0, 0)
        raise Exception(f"Expected '{expected}', got '{t_str}' at {loc}")

    def _loc(self, token):
        return Location(self.filename, token[1], token[2])

    def _parse_atom(self, token_text: str, token) -> ExprAST:
        if token_text.startswith('"') and token_text.endswith('"'):
            return StringExprAST(self._loc(token), token_text[1:-1])

        try:
            val = float(token_text) if "." in token_text else int(token_text)
            return NumberExprAST(self._loc(token), val)
        except ValueError:
            return VariableExprAST(self._loc(token), token_text)

    def parse_module(self) -> ModuleAST:
        ops = []
        while self._peek():
            t0, t1 = self._peek(), self._peek(1)
            is_defun = t0 and t0[0] == "(" and t1 and t1[0] == "defun"
            ops.append(self.parse_definition() if is_defun else self.parse_expr())
        return ModuleAST(tuple(ops))

    def parse_definition(self) -> FunctionAST:
        self._expect("(")
        self._expect("defun")
        name_token = self._consume()
        self._expect("(")

        args = []
        while (t := self._peek()) and t[0] != ")":
            args.append(self._consume()[0])
        self._expect(")")

        body = []
        while (t := self._peek()) and t[0] != ")":
            body.append(self.parse_expr())
        self._expect(")")

        proto = PrototypeAST(self._loc(name_token), name_token[0], args)
        return FunctionAST(self._loc(name_token), proto, tuple(body))

    def parse_expr(self) -> ExprAST:
        if not (t := self._peek()):
            raise Exception("Unexpected EOF in expr")

        if t[0] != "(":
            self._consume()
            return self._parse_atom(t[0], t)

        self._consume()
        if not (head := self._peek()):
            raise Exception("Unexpected EOF in list")

        if head[0] == "print":
            self._consume()
            arg = self.parse_expr()
            self._expect(")")
            return PrintExprAST(self._loc(head), arg)

        if head[0] in ("+", "*"):
            op = self._consume()
            lhs, rhs = self.parse_expr(), self.parse_expr()
            self._expect(")")
            return BinaryExprAST(self._loc(op), head[0], lhs, rhs)

        callee = self._consume()
        args = []
        while (pt := self._peek()) and pt[0] != ")":
            args.append(self.parse_expr())
        self._expect(")")
        return CallExprAST(self._loc(callee), callee[0], args)
