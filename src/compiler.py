from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, List, NamedTuple, Tuple

from xdsl.builder import Builder, InsertPoint
from xdsl.dialects.builtin import FunctionType, ModuleOp, i32
from xdsl.ir import Block, Region, SSAValue
from xdsl.utils.lexer import Location
from xdsl.utils.scoped_dict import ScopedDict

from ops import AddOp, CallOp, ConstantOp, FuncOp, MulOp, PrintOp, ReturnOp

INDENT = 2


class Dumper(NamedTuple):
    lines: list[str]
    indentation: int = 0

    def append(self, prefix: str, line: str):
        self.lines.append(" " * self.indentation * INDENT + prefix + line)

    def append_list(self, prefix: str, open_paren: str, exprs: Iterable[ExprAST | FunctionAST], close_paren: str, block: Callable[[Dumper, ExprAST | FunctionAST], None]):
        self.append(prefix, open_paren)
        child = self.child()
        for expr in exprs:
            block(child, expr)
        self.append("", close_paren)

    def child(self):
        return Dumper(self.lines, self.indentation + 1)

    @property
    def message(self):
        return "\n".join(self.lines)


class ReturnExprAST(NamedTuple):
    loc: Location
    expr: ExprAST | None

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append(prefix, "Return")
        if self.expr is not None:
            self.expr.inner_dump("", dumper.child())


class NumberExprAST(NamedTuple):
    loc: Location
    val: int

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append(prefix, f" {self.val}")


class VariableExprAST(NamedTuple):
    loc: Location
    name: str

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append("var: ", f"{self.name} @{self.loc}")


class BinaryExprAST(NamedTuple):
    loc: Location
    op: str
    lhs: ExprAST
    rhs: ExprAST

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append(prefix, f"BinOp: {self.op} @{self.loc}")
        child = dumper.child()
        self.lhs.inner_dump("", child)
        self.rhs.inner_dump("", child)


class CallExprAST(NamedTuple):
    loc: Location
    callee: str
    args: list[ExprAST]

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append_list(prefix, f"Call '{self.callee}' [ @{self.loc}", self.args, "]", lambda dd, arg: arg.inner_dump("", dd))


class PrintExprAST(NamedTuple):
    loc: Location
    arg: ExprAST

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append(prefix, "Print")
        self.arg.inner_dump("arg: ", dumper.child())


class PrototypeAST(NamedTuple):
    loc: Location
    name: str
    args: list[str]

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append("", f"Proto '{self.name}' @{self.loc}")
        dumper.append("Params: ", f"[{', '.join(self.args)}]")


class FunctionAST(NamedTuple):
    loc: Location
    proto: PrototypeAST
    body: tuple[ExprAST, ...]

    def dump(self):
        dumper = Dumper([])
        self.inner_dump("", dumper)
        return dumper.message

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append(prefix, "Function")
        child = dumper.child()
        self.proto.inner_dump("proto: ", child)
        child.append_list("Block ", "{", self.body, "} // Block", lambda dd, stmt: stmt.inner_dump("", dd))


class ModuleAST(NamedTuple):
    funcs: tuple[FunctionAST, ...]

    def dump(self):
        dumper = Dumper([])
        self.inner_dump("", dumper)
        return dumper.message

    def inner_dump(self, prefix: str, dumper: Dumper):
        dumper.append_list(prefix, "Module:", self.funcs, "", lambda dd, func: func.inner_dump("", dd))


ExprAST = BinaryExprAST | VariableExprAST | CallExprAST | NumberExprAST | PrintExprAST | ReturnExprAST


class Parser:
    def __init__(self, program: str, filename: str = "<string>"):
        self.filename, self.tokens, self.pos = filename, self._tokenize(program), 0

    def _tokenize(self, text: str) -> List[Tuple[str, int, int]]:
        token_re = re.compile(r";[^\n]*|([()])|([^\s()]+)|\n")
        tokens, line, line_start = [], 1, 0
        for match in token_re.finditer(text):
            text_val, start = match.group(), match.start()
            if text_val.startswith(";"):
                continue
            if text_val == "\n":
                line, line_start = line + 1, match.end()
                continue
            if not text_val.strip():
                continue
            tokens.append((text_val, line, start - line_start + 1))
        return tokens

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _consume(self):
        if self.pos >= len(self.tokens):
            raise Exception("Unexpected EOF")
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def _match(self, expected):
        if (t := self._peek()) and t[0] == expected:
            self._consume()
            return True
        return False

    def _expect(self, expected):
        if not self._match(expected):
            t = self._peek()
            raise Exception(f"Expected '{expected}', got '{t[0] if t else 'EOF'}' at {self._loc(t)}")

    def _loc(self, token):
        return Location(self.filename, token[1], token[2]) if token else Location(self.filename, 0, 0)

    def parse_module(self) -> ModuleAST:
        funcs = []
        while self._peek():
            funcs.append(self.parse_definition())
        return ModuleAST(tuple(funcs))

    def parse_definition(self) -> FunctionAST:
        self._expect("(")
        if (t := self._consume())[0] != "define":
            raise Exception(f"Expected 'define', got '{t[0]}' at {self._loc(t)}")
        self._expect("(")
        name_token, args = self._consume(), []
        while self._peek() and self._peek()[0] != ")":
            args.append(self._consume()[0])
        self._expect(")")
        proto = PrototypeAST(self._loc(name_token), name_token[0], args)
        body = []
        while self._peek() and self._peek()[0] != ")":
            body.append(self.parse_expr())
        self._expect(")")
        return FunctionAST(proto.loc, proto, tuple(body))

    def parse_expr(self) -> ExprAST:
        if not (t := self._peek()):
            raise Exception("Unexpected EOF in expr")
        if t[0] == "(":
            self._consume()
            if not (head := self._peek()):
                raise Exception("Unexpected EOF in list")
            if head[0] == "print":
                self._consume()
                arg = self.parse_expr()
                self._expect(")")
                return PrintExprAST(self._loc(head), arg)
            elif head[0] == "return":
                self._consume()
                arg = self.parse_expr()
                self._expect(")")
                return ReturnExprAST(self._loc(head), arg)
            elif head[0] in ("+", "*"):
                op, lhs, rhs = self._consume(), self.parse_expr(), self.parse_expr()
                self._expect(")")
                return BinaryExprAST(self._loc(op), head[0], lhs, rhs)
            else:
                callee, args = self._consume(), []
                while self._peek() and self._peek()[0] != ")":
                    args.append(self.parse_expr())
                self._expect(")")
                return CallExprAST(self._loc(callee), callee[0], args)
        elif t[0].isdigit():
            self._consume()
            return NumberExprAST(self._loc(t), int(t[0]))
        else:
            self._consume()
            return VariableExprAST(self._loc(t), t[0])


class IRGenError(Exception):
    pass


@dataclass
class IRGen:
    module: ModuleOp = ModuleOp([])
    builder: Builder = None
    symbol_table: ScopedDict[str, SSAValue] | None = None

    def __post_init__(self):
        self.builder = Builder(InsertPoint.at_end(self.module.body.blocks[0]))

    def ir_gen_module(self, module_ast: ModuleAST) -> ModuleOp:
        for f in module_ast.funcs:
            self.ir_gen_function(f)
        try:
            self.module.verify()
        except Exception as e:
            print(e)
            raise
        return self.module

    def ir_gen_function(self, func_ast: FunctionAST) -> FuncOp:
        parent_builder, self.symbol_table = self.builder, ScopedDict()
        block = Block(arg_types=[i32] * len(func_ast.proto.args))
        self.builder = Builder(InsertPoint.at_end(block))

        for name, value in zip(func_ast.proto.args, block.args):
            self.symbol_table[name] = value
        for expr in func_ast.body:
            self.ir_gen_expr(expr)

        if not block.ops or not isinstance(block.last_op, ReturnOp):
            self.builder.insert(ReturnOp())

        ret_types = [i32] if isinstance(block.last_op, ReturnOp) and block.last_op.operands else []
        func_op = FuncOp(func_ast.proto.name, FunctionType.from_lists([i32] * len(func_ast.proto.args), ret_types), Region(block))

        self.builder = parent_builder
        return self.builder.insert(func_op)

    def ir_gen_expr(self, expr: ExprAST) -> SSAValue | None:
        if isinstance(expr, BinaryExprAST):
            lhs, rhs = self.ir_gen_expr(expr.lhs), self.ir_gen_expr(expr.rhs)
            if expr.op == "+":
                return self.builder.insert(AddOp(lhs, rhs)).res
            if expr.op == "*":
                return self.builder.insert(MulOp(lhs, rhs)).res
            raise IRGenError(f"Unknown op {expr.op}")
        elif isinstance(expr, NumberExprAST):
            return self.builder.insert(ConstantOp(expr.val)).res
        elif isinstance(expr, VariableExprAST):
            if expr.name not in self.symbol_table:
                raise IRGenError(f"Undefined var {expr.name}")
            return self.symbol_table[expr.name]
        elif isinstance(expr, CallExprAST):
            args = [self.ir_gen_expr(arg) for arg in expr.args]
            return self.builder.insert(CallOp(expr.callee, args, [i32])).res[0]
        elif isinstance(expr, PrintExprAST):
            self.builder.insert(PrintOp(self.ir_gen_expr(expr.arg)))
        elif isinstance(expr, ReturnExprAST):
            self.builder.insert(ReturnOp(self.ir_gen_expr(expr.expr) if expr.expr else None))
        else:
            raise IRGenError(f"Unknown expr: {expr}")
