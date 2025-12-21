# run: `make run-riscv FILE=hello.s`

.PHONY: run-riscv
run-riscv:
	@command -v qemu-system-riscv64 >/dev/null || (echo "qemu not installed" && exit 1)
	@base=$$(basename $(FILE) .s); \
	riscv64-unknown-elf-as -o $$base.o $(FILE) && \
	riscv64-unknown-elf-ld -Ttext=0x80000000 -o $$base $$base.o && \
	qemu-system-riscv64 -machine virt -nographic -bios none -kernel $$base; \
	rm -f $$base.o $$base
