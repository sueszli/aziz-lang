.section .data
msg:
    .string "hello world!\n"

.section .text
.global _start

_start:
    la a0, msg              # a0 = address of msg
    li a1, 0x10000000       # a1 = UART address (stdout)
    
print_loop:
    lb a2, 0(a0)            # load byte from string
    beqz a2, done           # if zero, we're done
    sb a2, 0(a1)            # write to UART
    addi a0, a0, 1          # next character
    j print_loop            # repeat
    
done:                       # qemu magic to exit
    li a0, 0x100000
    li a1, 0x5555
    sw a1, 0(a0)
1:  j 1b
