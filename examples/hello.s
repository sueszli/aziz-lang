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
    
done:
    li a0, 0x100000         # a0 = exit syscall address
    li a1, 0x5555           # a1 = exit code
    sw a1, 0(a0)            # store exit code to trigger exit

1:  j 1b                    # infinite loop to end program as 
