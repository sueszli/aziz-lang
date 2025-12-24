.PHONY: venv
venv:
	test -f requirements.txt || (uvx pipreqs . --mode no-pin --encoding utf-8 --ignore .venv && mv requirements.txt requirements.in && uv pip compile requirements.in -o requirements.txt)
	uv venv .venv --python 3.11
	uv pip install -r requirements.txt
	@echo "activate venv with: \033[1;33msource .venv/bin/activate\033[0m"

.PHONY: lock
lock:
	uv pip freeze > requirements.in
	uv pip compile requirements.in -o requirements.txt

.PHONY: fmt
fmt:
	uvx isort .
	uvx autoflake --remove-all-unused-imports --recursive --in-place .
	uvx black --line-length 5000 .

.PHONY: run
run:
	for file in examples/*.aziz; do \
		echo "------------------------------------------------------------ $$file"; \
		uv run aziz-lang/main.py $$file --interpret --execute-riscv --execute-llvm; \
	done

.PHONY: run-tiny
run-tiny:
	for file in examples/*.aziz; do \
		echo "------------------------------------------------------------ $$file"; \
		cat $$file; \
		echo "---"; \
		uv run aziz-lang-tiny/main.py $$file | mlir-opt --convert-scf-to-cf --convert-func-to-llvm --convert-arith-to-llvm --convert-cf-to-llvm --reconcile-unrealized-casts | mlir-translate --mlir-to-llvmir | lli; \
	done
