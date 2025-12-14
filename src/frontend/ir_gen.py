from __future__ import annotations

from xdsl.builder import Builder, InsertPoint
from xdsl.dialects.builtin import FunctionType, ModuleOp, i32
from xdsl.ir import Block, Region, SSAValue
from xdsl.utils.scoped_dict import ScopedDict

from dialects.aziz import AddOp, CallOp, ConstantOp, FuncOp, IfOp, LessThanEqualOp, MulOp, PrintOp, ReturnOp, StringConstantOp, SubOp, YieldOp

from .ast_nodes import BinaryExprAST, CallExprAST, ExprAST, FunctionAST, IfExprAST, ModuleAST, NumberExprAST, PrintExprAST, PrototypeAST, StringExprAST, VariableExprAST


class IRGenError(Exception):
    pass


class IRGen:
    module: ModuleOp  # generated MLIR ModuleOp from AST
    builder: Builder  # keeps current insertion point for next op
    symbol_table: ScopedDict[str, SSAValue] | None = None  # variable name -> SSAValue for current scope. dropped on scope exit
    declarations: dict[str, FuncOp]  # function name -> FuncOp (required for dedup on recursion)

    def __init__(self):
        self.module = ModuleOp([])
        self.builder = Builder(InsertPoint.at_end(self.module.body.blocks[0]))
        self.declarations = {}

    def ir_gen_module(self, module_ast: ModuleAST) -> ModuleOp:
        functions = [op for op in module_ast.ops if isinstance(op, FunctionAST)]

        # implicit main function
        main_body = [op for op in module_ast.ops if isinstance(op, ExprAST)]
        if main_body:
            loc = main_body[0].loc
            main_func = FunctionAST(loc, PrototypeAST(loc, "main", []), tuple(main_body))
            functions.append(main_func)

        for func_ast in functions:
            self._declare_function(func_ast)
        for func_ast in functions:
            self._define_function(func_ast)

        # verify types
        self.module.verify()
        return self.module

    def _declare_function(self, func_ast: FunctionAST):
        # create FuncOp with correct name, but default i32 type and empty body for now
        arg_types = [i32] * len(func_ast.proto.args)
        return_types = [i32]
        func_type = FunctionType.from_lists(inputs=arg_types, outputs=return_types)

        block = Block(arg_types=arg_types)
        region = Region(block)

        func_op = FuncOp(func_ast.proto.name, func_type, region)
        self.module.body.blocks[0].add_op(func_op)
        self.declarations[func_ast.proto.name] = func_op

    def _define_function(self, func_ast: FunctionAST):
        func_op = self.declarations[func_ast.proto.name]
        block = func_op.body.blocks[0]

        # save current builder and symbol table
        parent_builder = self.builder
        self.symbol_table = ScopedDict()
        self.builder = Builder(InsertPoint.at_end(block))

        # init argument variables in symbol table
        for name, value in zip(func_ast.proto.args, block.args):
            self._declare(name, value)

        # generate body
        last_val = None
        for expr in func_ast.body:
            last_val = self._ir_gen_expr(expr)

        return_types = []
        if not block.ops or not isinstance(block.last_op, ReturnOp):
            # return 0 by default
            val = last_val if last_val is not None else self.builder.insert(ConstantOp(0)).res
            self.builder.insert(ReturnOp(val))
            return_types = [val.type]
        elif block.last_op.input:
            # infer return type from last return value
            return_types = [block.last_op.input.type]

        # update function signature if necessary
        current_return_types = func_op.function_type.outputs.data
        if list(current_return_types) != return_types:
            func_type = FunctionType.from_lists(inputs=func_op.function_type.inputs.data, outputs=return_types)
            func_op.function_type = func_type

        # restore state
        self.symbol_table = None
        self.builder = parent_builder

    def _declare(self, var: str, value: SSAValue) -> bool:
        # declare a variable in the current scope, return success if not already declared
        assert self.symbol_table is not None
        if var in self.symbol_table:
            return False
        self.symbol_table[var] = value
        return True

    def _ir_gen_expr(self, expr: ExprAST) -> SSAValue:
        if isinstance(expr, BinaryExprAST):
            return self._ir_gen_binary_expr(expr)
        if isinstance(expr, NumberExprAST):
            return self._ir_gen_number_expr(expr)
        if isinstance(expr, VariableExprAST):
            return self._ir_gen_variable_expr(expr)
        if isinstance(expr, CallExprAST):
            return self._ir_gen_call_expr(expr)
        if isinstance(expr, PrintExprAST):
            self._ir_gen_print_expr(expr)
            return None  # Print is void/statement-like in usage often, but expr in AST?
        if isinstance(expr, IfExprAST):
            return self._ir_gen_if_expr(expr)
        if isinstance(expr, StringExprAST):
            return self._ir_gen_string_expr(expr)

        raise IRGenError(f"unknown expr: {expr}")

    def _ir_gen_binary_expr(self, expr: BinaryExprAST) -> SSAValue:
        lhs = self._ir_gen_expr(expr.lhs)
        rhs = self._ir_gen_expr(expr.rhs)

        if expr.op == "+":
            return self.builder.insert(AddOp(lhs, rhs)).res
        if expr.op == "-":
            return self.builder.insert(SubOp(lhs, rhs)).res
        if expr.op == "*":
            return self.builder.insert(MulOp(lhs, rhs)).res
        if expr.op == "<=":
            return self.builder.insert(LessThanEqualOp(lhs, rhs)).res
        raise IRGenError(f"unknown op {expr.op}")

    def _ir_gen_number_expr(self, expr: NumberExprAST) -> SSAValue:
        return self.builder.insert(ConstantOp(expr.val)).res

    def _ir_gen_variable_expr(self, expr: VariableExprAST) -> SSAValue:
        if self.symbol_table is None or expr.name not in self.symbol_table:
            raise IRGenError(f"undefined var {expr.name}")
        return self.symbol_table[expr.name]

    def _ir_gen_call_expr(self, expr: CallExprAST) -> SSAValue:
        args = [self._ir_gen_expr(arg) for arg in expr.args]

        if expr.callee not in self.declarations:
            raise IRGenError(f"unknown function called: {expr.callee}")
        callee_op = self.declarations[expr.callee]
        ret_type = callee_op.function_type.outputs.data[0] # assume single result

        return self.builder.insert(CallOp(expr.callee, args, [ret_type])).res[0]

    def _ir_gen_print_expr(self, expr: PrintExprAST) -> None:
        self.builder.insert(PrintOp(self._ir_gen_expr(expr.arg)))

    def _ir_gen_if_expr(self, expr: IfExprAST) -> SSAValue:
        cond = self._ir_gen_expr(expr.cond)

        if_op = IfOp(cond, i32)  # Defaulting to i32 result
        self.builder.insert(if_op)

        # Then
        cursor = self.builder
        self.builder = Builder(InsertPoint.at_end(if_op.then_region.blocks[0]))
        then_val = self._ir_gen_expr(expr.then_expr)
        self.builder.insert(YieldOp(then_val))

        # Else
        self.builder = Builder(InsertPoint.at_end(if_op.else_region.blocks[0]))
        else_val = self._ir_gen_expr(expr.else_expr)
        self.builder.insert(YieldOp(else_val))

        self.builder = cursor
        return if_op.res

    def _ir_gen_string_expr(self, expr: StringExprAST) -> SSAValue:
        return self.builder.insert(StringConstantOp(expr.val)).res
