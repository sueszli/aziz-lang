import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from aziz.compiler import IRGen, Parser
from aziz.interpreter import AzizFunctions
from xdsl.dialects.builtin import Builtin
from xdsl.interpreter import Interpreter


def main():
    parser = argparse.ArgumentParser(description="Aziz Language Compiler")
    parser.add_argument("file", help="Input file")
    parser.add_argument("--run", action="store_true", help="Run the program")
    args = parser.parse_args()

    try:
        with open(args.file, "r") as f:
            prog = f.read()
    except FileNotFoundError:
        print(f"Error: '{args.file}' not found.")
        sys.exit(1)

    try:
        if args.file.endswith(".mlir"):
            from aziz.ops import Aziz
            from xdsl.context import Context
            from xdsl.parser import Parser as XDSLParser

            ctx = Context()
            ctx.load_dialect(Builtin)
            ctx.load_dialect(Aziz)
            module_op = XDSLParser(ctx, prog).parse_module()
        else:
            module_op = IRGen().ir_gen_module(Parser(prog, args.file).parse_module())

        if args.run:
            i = Interpreter(module_op)
            i.register_implementations(AzizFunctions())
            i.call_op("main", ())
        else:
            print(module_op)
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
