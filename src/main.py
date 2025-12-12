# /// script
# requires-python = "==3.14"
# dependencies = [
#     "xdsl==0.55.4",
# ]
# ///

import sys

from xdsl.interpreter import Interpreter

from compiler import IRGen, Parser
from interpreter import AzizFunctions

assert len(sys.argv) == 2, "requires .aziz file as argument"
file = sys.argv[1]
prog = open(file, "r").read()

module_op = IRGen().ir_gen_module(Parser(prog, file).parse_module())
i = Interpreter(module_op)
i.register_implementations(AzizFunctions())
i.call_op("main", ())
