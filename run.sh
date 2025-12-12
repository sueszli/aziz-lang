#!/bin/bash
set -e

# Usage: ./run.sh <file.aziz>
if [ -z "$1" ]; then
    echo "Usage: ./run.sh <file.aziz>"
    exit 1
fi

BASENAME="${1%.*}"
MLIR_FILE="${BASENAME}.mlir"

# Compile to MLIR
.venv/bin/python aziz-lang/main.py "$1" > "$MLIR_FILE"

# Execute MLIR
.venv/bin/python aziz-lang/main.py "$MLIR_FILE" --run

# Optional: Clean up MLIR file to be "clean"
rm "$MLIR_FILE"
