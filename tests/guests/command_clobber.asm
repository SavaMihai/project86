; Overwrite the memory DOS granted this COM program above its first 64 KiB.
; This deliberately destroys COMMAND.COM's transient section, forcing reload.
bits 16
org 100h
    mov dx,[2]
    mov ax,cs
    add ax,1000h
next_segment:
    cmp ax,dx
    jae finished
    mov es,ax
    mov bx,dx
    sub bx,ax
    mov cx,8000h
    cmp bx,1000h
    jae fill
    mov cx,bx
    shl cx,1
    shl cx,1
    shl cx,1
fill:
    push ax
    mov ax,0a55ah
    xor di,di
    cld
    rep stosw
    pop ax
    add ax,1000h
    jmp next_segment
finished:
    mov dx,message
    mov ah,9
    int 21h
    mov ax,4c00h
    int 21h
message db 'TRANSIENT CLOBBERED',13,10,'$'
