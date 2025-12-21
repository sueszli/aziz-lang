from xdsl.context import Context
from xdsl.dialects import arith, riscv
from xdsl.dialects.builtin import ModuleOp, UnrealizedConversionCastOp
from xdsl.passes import ModulePass
from xdsl.pattern_rewriter import GreedyRewritePatternApplier, PatternRewriter, PatternRewriteWalker, RewritePattern, op_type_rewrite_pattern
from xdsl.rewriter import InsertPoint


class SelectOpLowering(RewritePattern):
    # lower arith.select
    # by replacing branches with bitwise operations
    #
    # mask = 0b1111 if cond=1, 0b0000 if cond=0
    # result = (true_val & mask) | (false_val & ~mask)
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: arith.SelectOp, rewriter: PatternRewriter):
        cond = op.cond
        true_val = op.lhs
        false_val = op.rhs
        reg_type = riscv.IntRegisterType.unallocated()

        # cast 1 bit width condition to full 32/64 bit riscv register
        cond_cast = UnrealizedConversionCastOp.create(operands=[cond], result_types=[reg_type])
        rewriter.insert_op(cond_cast, InsertPoint.before(op))
        cond_reg = cond_cast.results[0]

        # cast true_val and false_val to riscv registers for bitwise ops
        true_cast = UnrealizedConversionCastOp.create(operands=[true_val], result_types=[reg_type])
        rewriter.insert_op(true_cast, InsertPoint.before(op))
        true_reg = true_cast.results[0]

        false_cast = UnrealizedConversionCastOp.create(operands=[false_val], result_types=[reg_type])
        rewriter.insert_op(false_cast, InsertPoint.before(op))
        false_reg = false_cast.results[0]

        # mask = 0 - cond
        #
        # when cond = 0:
        #   mask = 0 - 0 = 0b0000
        #
        # when cond = 1:
        #   mask = 0 - 1 = -1 = 0b1111
        zero = riscv.GetRegisterOp(riscv.Registers.ZERO)
        rewriter.insert_op(zero, InsertPoint.before(op))
        mask = riscv.SubOp(zero.res, cond_reg, rd=reg_type)
        rewriter.insert_op(mask, InsertPoint.before(op))

        # t1 = true_val & mask
        #
        # when cond = 1 (mask = 0b1111):
        #   t1 = true_val & 0b1111 = true_val (keeps true_val)
        #
        # when cond = 0 (mask = 0b0000):
        #   t1 = true_val & 0b0000 = 0 (zeros out true_val)
        t1 = riscv.AndOp(true_reg, mask.rd, rd=reg_type)
        rewriter.insert_op(t1, InsertPoint.before(op))

        # not_mask = mask XOR -1
        not_mask = riscv.XoriOp(mask.rd, -1, rd=reg_type)
        rewriter.insert_op(not_mask, InsertPoint.before(op))

        # t2 = false_val & not_mask
        #
        # when cond = 1 (not_mask = 0b0000):
        #   t2 = false_val & 0b0000 = 0 (zeros out false_val)
        #
        # when cond = 0 (not_mask = 0b1111):
        #   t2 = false_val & 0b1111 = false_val (keeps false_val)
        t2 = riscv.AndOp(false_reg, not_mask.rd, rd=reg_type)
        rewriter.insert_op(t2, InsertPoint.before(op))

        # combine the masked values
        # result = t1 | t2
        #
        # when cond = 1:
        #   result = true_val | 0 = true_val
        #
        # when cond = 0:
        #   result = 0 | false_val = false_val
        result = riscv.OrOp(t1.rd, t2.rd, rd=reg_type)
        rewriter.insert_op(result, InsertPoint.before(op))

        # riscv register -> type that arith.select returned
        result_cast = UnrealizedConversionCastOp.create(operands=[result.rd], result_types=[op.result.type])
        rewriter.insert_op(result_cast, InsertPoint.before(op))

        # replace the select op with our branchless implementation
        rewriter.replace_op(op, [], [result_cast.results[0]])


class LowerSelectPass(ModulePass):
    name = "lower-select"

    def apply(self, _: Context, op: ModuleOp) -> None:
        PatternRewriteWalker(GreedyRewritePatternApplier([SelectOpLowering()])).rewrite_module(op)
