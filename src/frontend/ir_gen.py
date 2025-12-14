from __future__ import annotations

from xdsl.builder import Builder, InsertPoint
from xdsl.dialects.builtin import FunctionType, ModuleOp, f64, i32
from xdsl.ir import Attribute, Block, Region, SSAValue
from xdsl.utils.scoped_dict import ScopedDict

from dialects.aziz import AddOp, CallOp, ConstantOp, FuncOp, IfOp, LessThanEqualOp, MulOp, PrintOp, ReturnOp, StringConstantOp, SubOp, YieldOp, string_type

from .ast_nodes import BinaryExprAST, CallExprAST, ExprAST, FunctionAST, IfExprAST, ModuleAST, NumberExprAST, PrintExprAST, PrototypeAST, StringExprAST, VariableExprAST


class IRGenError(Exception):
    pass


class IRGen:
    module: ModuleOp  # source code
    builder: Builder  # current insertion point for next op
    symbol_table: ScopedDict[str, SSAValue] | None = None  # variable name -> SSA value for current scope, dropped on scope exit
    function_signatures: dict[str, tuple[list[Attribute], Attribute]]  # function name -> (arg types, return type)

    def __init__(self):
        self.module = ModuleOp([])
        self.builder = Builder(InsertPoint.at_end(self.module.body.blocks[0]))
        self.function_signatures = {}

    def ir_gen_module(self, module_ast: ModuleAST) -> ModuleOp:
        self._collect_function_signatures(module_ast)

        main_body = []
        for op in module_ast.ops:
            if isinstance(op, FunctionAST):
                self.ir_gen_function(op)
            elif isinstance(op, ExprAST):
                main_body.append(op)

        if main_body:
            # create a main function for top-level expressions
            loc = main_body[0].loc
            main_func = FunctionAST(loc, PrototypeAST(loc, "main", []), tuple(main_body))
            self.ir_gen_function(main_func)

        self.module.verify()
        return self.module

    def _collect_function_signatures(self, module_ast: ModuleAST):
        # first pass: collect function signatures from call sites.
        for op in module_ast.ops:
            if isinstance(op, CallExprAST):
                arg_types = [self._infer_type_from_expr(arg) for arg in op.args]
                # Infer return type - for now, use the type of the first argument
                ret_type = arg_types[0] if arg_types else i32
                self.function_signatures[op.callee] = (arg_types, ret_type)
            elif isinstance(op, PrintExprAST):
                if isinstance(op.arg, CallExprAST):
                    arg_types = [self._infer_type_from_expr(arg) for arg in op.arg.args]
                    ret_type = arg_types[0] if arg_types else i32
                    self.function_signatures[op.arg.callee] = (arg_types, ret_type)

    def _infer_type_from_expr(self, expr: ExprAST) -> Attribute:
        # Infer the type of an expression without generating IR.
        if isinstance(expr, NumberExprAST):
            return f64 if isinstance(expr.val, float) else i32
        if isinstance(expr, StringExprAST):
            return string_type
        # For other expressions, default to i32
        return i32

    def declare(self, var: str, value: SSAValue) -> bool:
        assert self.symbol_table is not None
        if var in self.symbol_table:
            return False
        self.symbol_table[var] = value
        return True

    def ir_gen_function(self, func_ast: FunctionAST) -> FuncOp:
        parent_builder = self.builder
        self.symbol_table = ScopedDict()

        # Get function signature from first pass, or default to i32
        if func_ast.proto.name in self.function_signatures:
            arg_types, ret_type = self.function_signatures[func_ast.proto.name]
        else:
            arg_types = [i32] * len(func_ast.proto.args)
            ret_type = i32

        # Create the block for the current function
        block = Block(arg_types=arg_types)
        self.builder = Builder(InsertPoint.at_end(block))

        for name, value in zip(func_ast.proto.args, block.args):
            self.declare(name, value)

        last_val = None
        for expr in func_ast.body:
            last_val = self.ir_gen_expr(expr)

        if not block.ops or not isinstance(block.last_op, ReturnOp):
            val = last_val if last_val else self.builder.insert(ConstantOp(0)).res
            self.builder.insert(ReturnOp(val))

        ret_types = [ret_type] if isinstance(block.last_op, ReturnOp) and block.last_op.operands else []
        func_op = FuncOp(
            func_ast.proto.name,
            FunctionType.from_lists(arg_types, ret_types),
            Region(block),
        )

        self.symbol_table = None
        self.builder = parent_builder
        return self.builder.insert(func_op)

    def ir_gen_binary_expr(self, expr: BinaryExprAST) -> SSAValue:
        lhs, rhs = self.ir_gen_expr(expr.lhs), self.ir_gen_expr(expr.rhs)
        if expr.op == "+":
            return self.builder.insert(AddOp(lhs, rhs)).res
        if expr.op == "*":
            return self.builder.insert(MulOp(lhs, rhs)).res
        if expr.op == "-":
            return self.builder.insert(SubOp(lhs, rhs)).res
        if expr.op == "<=":
            return self.builder.insert(LessThanEqualOp(lhs, rhs)).res
        raise IRGenError(f"Unknown op {expr.op}")

    def ir_gen_number_expr(self, expr: NumberExprAST) -> SSAValue:
        return self.builder.insert(ConstantOp(expr.val)).res

    def ir_gen_variable_expr(self, expr: VariableExprAST) -> SSAValue:
        if self.symbol_table is None or expr.name not in self.symbol_table:
            raise IRGenError(f"Undefined var {expr.name}")
        return self.symbol_table[expr.name]

    def ir_gen_call_expr(self, expr: CallExprAST) -> SSAValue:
        args = [self.ir_gen_expr(arg) for arg in expr.args]
        # Get return type from function signature
        ret_type = i32
        if expr.callee in self.function_signatures:
            _, ret_type = self.function_signatures[expr.callee]
        return self.builder.insert(CallOp(expr.callee, args, [ret_type])).res[0]

    def ir_gen_print_expr(self, expr: PrintExprAST) -> SSAValue | None:
        self.builder.insert(PrintOp(self.ir_gen_expr(expr.arg)))
        return None

    def ir_gen_if_expr(self, expr: IfExprAST) -> SSAValue:
        cond = self.ir_gen_expr(expr.cond)
        if_op = IfOp(cond)
        self.builder.insert(if_op)

        # Generate Then Block
        cursor = self.builder
        self.builder = Builder(InsertPoint.at_end(if_op.then_region.blocks[0]))
        then_result = self.ir_gen_expr(expr.then_expr)
        self.builder.insert(YieldOp(then_result))

        # Generate Else Block
        self.builder = Builder(InsertPoint.at_end(if_op.else_region.blocks[0]))
        else_result = self.ir_gen_expr(expr.else_expr)
        self.builder.insert(YieldOp(else_result))

        self.builder = cursor
        return if_op.res

    def ir_gen_string_expr(self, expr: StringExprAST) -> SSAValue:
        return self.builder.insert(StringConstantOp(expr.val)).res

    def ir_gen_expr(self, expr: ExprAST) -> SSAValue | None:
        if isinstance(expr, BinaryExprAST):
            return self.ir_gen_binary_expr(expr)
        if isinstance(expr, NumberExprAST):
            return self.ir_gen_number_expr(expr)
        if isinstance(expr, VariableExprAST):
            return self.ir_gen_variable_expr(expr)
        if isinstance(expr, CallExprAST):
            return self.ir_gen_call_expr(expr)
        if isinstance(expr, PrintExprAST):
            return self.ir_gen_print_expr(expr)
        if isinstance(expr, IfExprAST):
            return self.ir_gen_if_expr(expr)
        if isinstance(expr, StringExprAST):
            return self.ir_gen_string_expr(expr)

        raise IRGenError(f"Unknown expr: {expr}")
