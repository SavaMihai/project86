; Guest comparison of the CASSFAR APIs used for video, key search and help.
.8086
extrn GVIDO:far,INSTRN:far,HLPRD:far,WWRAP:far
public __acrtused
__acrtused equ 1
TESTSTK segment para stack 'STACK'
    dw 512 dup(0)
TESTSTK ends
TESTDATA segment para public 'DATA'
magic db 'CAS1'
video db 125 dup(0)
ins dw 10 dup(0)
hrd dw 40 dup(0)
wwp dw 16 dup(0)
header dw 4 dup(0)
helpname db 'A:\SELECT.HLP',0
helpid dw 1
buffer db 8192 dup(0)
include cases.inc
TESTDATA ends
TESTCODE segment para public 'CODE'
assume cs:TESTCODE,ds:TESTDATA,es:TESTDATA
write proc near
    push ax
    push bx
    mov bx,1
    mov ah,40h
    int 21h
    pop bx
    pop ax
    ret
write endp
start:
    mov ax,TESTDATA
    mov ds,ax
    mov es,ax
    mov dx,offset magic
    mov cx,4
    call write
    mov di,offset video
    call GVIDO
    mov dx,offset video
    mov cx,85
    call write
    mov si,offset cases
    mov bp,case_count
nextcase:
    mov ax,[si]
    mov ins,ax
    mov ax,[si+2]
    mov ins+2,ax
    mov ax,[si+4]
    mov ins+4,ax
    mov ax,[si+6]
    mov ins+6,ax
    mov ins+8,ds
    mov ax,[si+8]
    mov ins+10,ax
    mov ax,[si+10]
    mov ins+12,ax
    mov ins+14,ds
    mov ax,[si+12]
    mov ins+16,ax
    mov di,offset ins
    call INSTRN
    mov dx,offset ins+18
    mov cx,2
    call write
    add si,14
    dec bp
    jnz nextcase
nexthelp:
    mov hrd,2
    mov hrd+2,8192
    mov hrd+4,offset buffer
    mov hrd+6,ds
    mov ax,helpid
    mov hrd+8,ax
    mov header,ax
    mov hrd+10,offset helpname
    mov hrd+12,ds
    mov di,offset hrd
    call HLPRD
    mov ax,hrd+28
    mov header+2,ax
    mov ax,hrd+30
    mov header+4,ax
    mov ax,hrd+22
    mov header+6,ax
    mov dx,offset header
    mov cx,8
    call write
    cmp hrd+28,0
    je help_error_ok
    jmp failed
help_error_ok:
    cmp hrd+30,0
    je help_dos_ok
    jmp failed
help_dos_ok:
    mov cx,hrd+22
    mov dx,hrd+24
    call write
    mov wwp,41
    mov ax,hrd+22
    mov wwp+2,ax
    mov ax,hrd+24
    mov wwp+4,ax
    mov ax,hrd+26
    mov wwp+6,ax
    mov wwp+8,8192
    mov wwp+16,54
    mov byte ptr wwp+20,'@'
    mov byte ptr wwp+21,'@'
    mov byte ptr wwp+22,'#'
    mov byte ptr wwp+23,'-'
    mov byte ptr wwp+24,'&'
    mov di,offset wwp
    call WWRAP
    mov ax,wwp+18
    mov header,ax
    mov ax,wwp+25
    mov header+2,ax
    mov dx,offset header
    mov cx,4
    call write
    mov ax,wwp+18
    mov bx,54
    mul bx
    cmp ax,8192
    ja failed
    mov cx,ax
    mov dx,offset buffer
    call write
    inc helpid
    cmp helpid,58
    jae all_done
    jmp nexthelp
all_done:
    mov ax,4c00h
    int 21h
failed:
    mov ax,4c01h
    int 21h
TESTCODE ends
end start
