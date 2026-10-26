; Test-only guest interrupt hook. Every DOS service except the DBCS range query
; is forwarded to the real DOS kernel. Production libraries never use this file.
.8086
_TEXT segment word public 'CODE'
assume cs:_TEXT
old21 dd 0
ranges db 81h,9fh,0e0h,0fch,0,0,0,0,0,0,0,0
handler proc far
    cmp ax,6300h
    jne forward
    push bp
    mov bp,sp
    and word ptr ss:[bp+6],0fffeh
    pop bp
    push cs
    pop ds
    mov si,offset ranges
    xor ax,ax
    iret
forward:
    jmp dword ptr cs:old21
handler endp
public _test_install, _test_restore
_test_install proc near
    push ax
    push bx
    push dx
    push ds
    push es
    mov ax,3521h
    int 21h
    mov word ptr cs:old21,bx
    mov word ptr cs:old21+2,es
    push cs
    pop ds
    mov dx,offset handler
    mov ax,2521h
    int 21h
    pop es
    pop ds
    pop dx
    pop bx
    pop ax
    ret
_test_install endp
_test_restore proc near
    push ax
    push dx
    push ds
    lds dx,cs:old21
    mov ax,2521h
    int 21h
    pop ds
    pop dx
    pop ax
    ret
_test_restore endp
_TEXT ends
end
