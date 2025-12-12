# Aziz Language

A toy Lisp-like language implemented using xDSL.

## Usage

```bash
python3 main.py examples/test.aziz
```

## Structure

- `aziz/dialects/aziz.py`: Defines the Aziz dialect operations.
- `aziz/frontend/ast.py`: Defines the AST.
- `aziz/frontend/parser.py`: Parses `.aziz` files to AST.
- `aziz/frontend/ir_gen.py`: Generates xDSL IR from AST.

## Example

```lisp
(define (add a b)
  (return (+ a b)))

(define (main)
  (print (add 1 2))
  (return 0))
```
