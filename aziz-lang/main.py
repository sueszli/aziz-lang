# /// script
# requires-python = "==3.14"
# dependencies = [
#     "xdsl==0.55.4",
# ]
# ///

import argparse
from pathlib import Path

from compiler import compile, context, parse_aziz, transform
from interpreter import AzizFunctions
from xdsl.interpreter import Interpreter

# parser = argparse.ArgumentParser(description="aziz language")
# parser.add_argument("file", help="source file")
# group = parser.add_mutually_exclusive_group()
# group.add_argument("--ast", action="store_true", help="print IR")
# group.add_argument("--mlir", action="store_true", help="print MLIR")
# parser.add_argument("--interpret", action="store_true", help="Interpret the code")
# args = parser.parse_args()
# assert args.file.endswith(".aziz")
# src = Path(args.file).read_text()


# def context():
#     ctx = Context()
#     # ctx.load_dialect(affine.Affine)
#     # ctx.load_dialect(arith.Arith)
#     ctx.load_dialect(Builtin)
#     # ctx.load_dialect(func.Func)
#     # ctx.load_dialect(memref.MemRef)
#     # ctx.load_dialect(printf.Printf)
#     # ctx.load_dialect(riscv_func.RISCV_Func)
#     # ctx.load_dialect(riscv.RISCV)
#     # ctx.load_dialect(scf.Scf)
#     ctx.load_dialect(aziz.Aziz)
#     return ctx


# # ctx not necessary if only using interpreter
# ctx = context()

# module_ast = AzizParser(ctx, src).parse_module()  # source -> ast
# if args.ast:
#     print(dump(module_ast), "\n")

# module_op = IRGen().ir_gen_module(module_ast)  # ast -> mlir
# if args.mlir:
#     print(module_op, "\n")


# # code = compile(program)
# # emulate_riscv(code)


# if args.interpret:
#     interpreter = Interpreter(module_op)
#     interpreter.register_implementations(AzizFunctions())
#     interpreter.call_op("main", ())


def main():
    parser = argparse.ArgumentParser(description="aziz language")
    parser.add_argument("file", help="source file")
    parser.add_argument("--target", help="target dialect", default="riscv-lowered")
    parser.add_argument("--interpret", action="store_true", help="interpret the code")
    parser.add_argument("--print-op", action="store_true", help="print the operation after transformation")
    args = parser.parse_args()

    assert args.file.endswith(".aziz")
    src = Path(args.file).read_text()

    if args.interpret:
        ctx = context()
        module_op = parse_aziz(src, ctx)
        interpreter = Interpreter(module_op)
        interpreter.register_implementations(AzizFunctions())
        interpreter.call_op("main", ())
        return

    if args.print_op:
        ctx = context()
        module_op = parse_aziz(src, ctx)
        transform(ctx, module_op, target=args.target)
        print(module_op)
        return

    print(compile(src))


if __name__ == "__main__":
    main()
