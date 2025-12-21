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

.PHONY: run-riscv
run-riscv:
	@command -v qemu-system-riscv64 >/dev/null || (echo "qemu not installed" && exit 1)
	@base=$$(basename $(FILE) .s); \
	riscv64-unknown-elf-as -o $$base.o $(FILE) && \
	riscv64-unknown-elf-ld -Ttext=0x80000000 -o $$base $$base.o && \
	qemu-system-riscv64 -machine virt -nographic -bios none -kernel $$base; \
	rm -f $$base.o $$base
