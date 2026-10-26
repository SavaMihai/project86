bits 16
org 100h
mov ax,7fffh
add ax,1
jno failed
jc failed
cmp ax,8000h
jne failed
mov bx,sp
push sp
pop ax
cmp ax,bx
jne failed
mov ax,1234h
mov cl,32
shl ax,cl
cmp ax,1234h
jne failed
push ds
pop es
mov si,message
mov di,buffer
mov cx,message_end-message
cld
rep movsb
mov byte [patch+1],42
patch: mov al,0
cmp al,42
jne failed
mov dx,buffer
mov ah,9
int 21h
mov ax,4c00h
int 21h
failed:
mov dx,error
mov ah,9
int 21h
mov ax,4c01h
int 21h
message db 'P86 ASSEMBLED CPU PASS',13,10,'$'
message_end:
error db 'P86 ASSEMBLED CPU FAILED',13,10,'$'
buffer times 64 db 0
