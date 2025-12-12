import argparse
import sys
import os
import traceback

# Add the parent directory to sys.path to allow importing 'aziz' package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aziz.compiler import IRGen, Parser
from aziz.interpreter import AzizFunctions
from aziz.ops import Aziz
from xdsl.dialects.builtin import Builtin
from xdsl.interpreter import Interpreter
from xdsl.context import Context
from xdsl.parser import Parser as XDSLParser


def main():
    parser = argparse.ArgumentParser(description="Aziz Language Compiler")
    parser.add_argument("file", help="Input file")
    parser.add_argument("--run", action="store_true", help="Run the program")
    parser.add_argument("--output", help="Output file for MLIR")
    args = parser.parse_args()

    try:
        with open(args.file, "r") as f:
            prog = f.read()
    except FileNotFoundError:
        print(f"Error: '{args.file}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        if args.file.endswith(".mlir"):
            ctx = Context()
            ctx.load_dialect(Builtin)
            ctx.load_dialect(Aziz)
            module_op = XDSLParser(ctx, prog).parse_module()
        else:
            module_op = IRGen().ir_gen_module(Parser(prog, args.file).parse_module())

        if args.output:
            with open(args.output, "w") as f:
                print(module_op, file=f)

        if args.run:
            i = Interpreter(module_op)
            i.register_implementations(AzizFunctions())
            i.call_op("main", ())
        
        if not args.run and not args.output:
            print(module_op)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
