; Project86: obtain the active DOS DBCS lead-byte ranges.
; Near C call, far-pointer result DX:AX. All other registers are preserved.
; DOS INT 21h executes in the real guest kernel.
.8086
_TEXT segment word public 'CODE'
assume cs:_TEXT
public _p86_dbcs
_p86_dbcs proc near
    push bx
    push cx
    push si
    push di
    push bp
    push ds
    push es
    mov ax,6300h
    int 21h
    jc no_table
    mov ax,si
    mov dx,ds
    jmp short done
no_table:
    xor ax,ax
    xor dx,dx
done:
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop cx
    pop bx
    ret
_p86_dbcs endp
_TEXT ends
end
