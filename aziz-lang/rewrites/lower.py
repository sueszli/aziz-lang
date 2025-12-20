from dialects import aziz
from xdsl.context import Context
from xdsl.dialects import arith, func, memref, printf, scf
from xdsl.dialects.builtin import AnyFloat, FloatAttr, IndexType, IntegerAttr, IntegerType, ModuleOp, StringAttr, i8
from xdsl.ir import Block, Region
from xdsl.passes import ModulePass
from xdsl.pattern_rewriter import GreedyRewritePatternApplier, PatternRewriter, PatternRewriteWalker, RewritePattern, op_type_rewrite_pattern
from xdsl.rewriter import InsertPoint


class AddOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.AddOp, rewriter: PatternRewriter):
        if isinstance(op.lhs.type, AnyFloat):
            rewriter.replace_op(op, arith.AddfOp(op.lhs, op.rhs))
        else:
            rewriter.replace_op(op, arith.AddiOp(op.lhs, op.rhs))


class SubOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.SubOp, rewriter: PatternRewriter):
        if isinstance(op.lhs.type, AnyFloat):
            rewriter.replace_op(op, arith.SubfOp(op.lhs, op.rhs))
        else:
            rewriter.replace_op(op, arith.SubiOp(op.lhs, op.rhs))


class MulOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.MulOp, rewriter: PatternRewriter):
        if isinstance(op.lhs.type, AnyFloat):
            rewriter.replace_op(op, arith.MulfOp(op.lhs, op.rhs))
        else:
            rewriter.replace_op(op, arith.MuliOp(op.lhs, op.rhs))


class LessThanEqualOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.LessThanEqualOp, rewriter: PatternRewriter):
        if isinstance(op.lhs.type, AnyFloat):
            rewriter.replace_op(op, arith.CmpfOp(op.lhs, op.rhs, "ole"))  # ordered less equal
        else:
            rewriter.replace_op(op, arith.CmpiOp(op.lhs, op.rhs, "sle"))  # signed less equal


class ConstantOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.ConstantOp, rewriter: PatternRewriter):
        val = op.value
        if isinstance(val, IntegerAttr):
            rewriter.replace_op(op, arith.ConstantOp(val))
        elif isinstance(val, FloatAttr):
            rewriter.replace_op(op, arith.ConstantOp(val))


# todo: fix this weird string stuff?
class StringConstantOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.StringConstantOp, rewriter: PatternRewriter):
        val = op.value
        assert isinstance(val, StringAttr)
        string_val = val.data
        # convert the string to utf-8 bytes and store them in an i8 memref
        encoded_val = val.data.encode("utf-8")
        str_len = len(encoded_val)

        # allocate memref of size [len] x i8
        alloc = memref.AllocOp.get(i8, None, [str_len])
        rewriter.insert_op(alloc, InsertPoint.before(op))

        # store each character
        for i, char in enumerate(encoded_val):
            char_val = arith.ConstantOp(IntegerAttr(char, i8))
            rewriter.insert_op(char_val, InsertPoint.before(op))
            idx = arith.ConstantOp(IntegerAttr(i, IndexType()))
            rewriter.insert_op(idx, InsertPoint.before(op))
            store = memref.StoreOp.get(char_val, alloc, [idx])
            rewriter.insert_op(store, InsertPoint.before(op))

        # todo: dealloc the memref so we don't leak
        rewriter.replace_op(op, [], [alloc.memref])


# todo: fix this weird string stuff?
class PrintOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.PrintOp, rewriter: PatternRewriter):
        if isinstance(op.input.type, memref.MemRefType):
            # it's a string (memref<...xi8>)
            memref_type = op.input.type
            shape = memref_type.get_shape()
            assert len(shape) == 1
            size = shape[0]

            # create a loop to print characters one by one
            # manual region construction for scf.ForOp
            lb = arith.ConstantOp(IntegerAttr(0, IndexType()))
            ub = arith.ConstantOp(IntegerAttr(size, IndexType()))
            step = arith.ConstantOp(IntegerAttr(1, IndexType()))

            rewriter.insert_op(lb, InsertPoint.before(op))
            rewriter.insert_op(ub, InsertPoint.before(op))
            rewriter.insert_op(step, InsertPoint.before(op))

            # type matches bounds (index)
            block = Block(arg_types=[IndexType()])
            iv = block.args[0]

            load = memref.LoadOp.get(op.input, [iv])
            block.add_op(load)

            prt = printf.PrintFormatOp("{}", load.res)
            block.add_op(prt)

            block.add_op(scf.YieldOp())

            loop = scf.ForOp(lb, ub, step, [], Region(block))
            rewriter.replace_op(op, loop)

        else:
            rewriter.replace_op(op, printf.PrintFormatOp("{}", op.input))


class ReturnOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.ReturnOp, rewriter: PatternRewriter):
        rewriter.replace_op(op, func.ReturnOp(op.input) if op.input else func.ReturnOp())


class FuncOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.FuncOp, rewriter: PatternRewriter):
        new_op = func.FuncOp(op.sym_name.data, op.function_type, rewriter.move_region_contents_to_new_regions(op.body), visibility=op.sym_visibility)
        rewriter.replace_op(op, new_op)


class CallOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.CallOp, rewriter: PatternRewriter):
        rewriter.replace_op(op, func.CallOp(op.callee, op.arguments, op.res.types))


class IfOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.IfOp, rewriter: PatternRewriter):
        then_region = rewriter.move_region_contents_to_new_regions(op.then_region)
        else_region = rewriter.move_region_contents_to_new_regions(op.else_region)

        # if (integer) -> if (integer != 0)
        # because scf.IfOp condition must be i1
        cond = op.cond
        wider_than_bool = isinstance(cond.type, IntegerType) and cond.type.width.data != 1
        if wider_than_bool:
            zero = arith.ConstantOp(IntegerAttr(0, cond.type))
            rewriter.insert_op(zero, InsertPoint.before(rewriter.current_operation))
            cmp = arith.CmpiOp(cond, zero.result, "ne")  # condition != 0
            rewriter.insert_op(cmp, InsertPoint.before(rewriter.current_operation))
            cond = cmp.result

        new_op = scf.IfOp(cond, [op.res.type], then_region, else_region)
        rewriter.replace_op(op, new_op)


class YieldOpLowering(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: aziz.YieldOp, rewriter: PatternRewriter):
        rewriter.replace_op(op, scf.YieldOp(op.input))


class LowerAzizPass(ModulePass):
    name = "lower-aziz"

    def apply(self, _: Context, op: ModuleOp) -> None:
        PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    AddOpLowering(),
                    SubOpLowering(),
                    MulOpLowering(),
                    LessThanEqualOpLowering(),
                    ConstantOpLowering(),
                    StringConstantOpLowering(),
                    PrintOpLowering(),
                    ReturnOpLowering(),
                    FuncOpLowering(),
                    CallOpLowering(),
                    IfOpLowering(),
                    YieldOpLowering(),
                ]
            )
        ).rewrite_module(op)
