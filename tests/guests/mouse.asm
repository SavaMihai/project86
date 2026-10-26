bits 16
org 100h
; Exercise the installed guest driver's INT 33h services; no host mouse shortcut.
mov ax,4
mov cx,320
mov dx,100
int 33h
mov ax,0bh
int 33h
xor ax,ax
int 16h
mov ax,3
int 33h
mov [report],bx
mov [report+2],cx
mov [report+4],dx
mov ax,0bh
int 33h
mov [report+6],cx
mov [report+8],dx
mov dx,filename
xor cx,cx
mov ah,3ch
int 21h
jc failed
mov bx,ax
mov cx,10
mov dx,report
mov ah,40h
int 21h
jc failed
mov ah,3eh
int 21h
mov ax,4c00h
int 21h
failed:
mov ax,4c01h
int 21h
filename db 'MOUSE.DAT',0
report times 5 dw 0
