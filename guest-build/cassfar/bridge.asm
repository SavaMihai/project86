; Project86 adapters: SELECT's ES:DI far-call ABI to large-model C.
.8086
_DATA segment word public 'DATA'
_DATA ends
CONST segment word public 'CONST'
CONST ends
_BSS segment word public 'BSS'
_BSS ends
DGROUP group CONST,_BSS,_DATA
CASSFAR_TEXT segment byte public 'CODE'
extrn _cass_entry:far
CASSFAR_TEXT ends
P86CAS segment para public 'CODE'
assume cs:P86CAS
entry macro symbol,number
public symbol
symbol proc far
    pushf
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov bp,sp
    push es
    push di
    mov ax,number
    push ax
    mov ax,DGROUP
    mov ds,ax
    cld
    call _cass_entry
    add sp,6
    if number eq 5
        mov ss:[bp+16],ax
    endif
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    popf
    ret
symbol endp
endm
entry DISPQ,0
entry GVIDO,1
entry INSTRN,2
entry MBEEP,3
entry SLCTP,4
entry PANEL,5
entry HLPRD,6
entry INPUT,7
entry INCHA,8
entry WWRAP,9

public _cass_int
_cass_int proc far
    push bp
    mov bp,sp
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    lds bx,[bp+8]
    push word ptr [bx+12]
    mov es,[bx+14]
    mov si,[bx+8]
    mov di,[bx+10]
    mov cx,[bx+4]
    mov dx,[bx+6]
    mov ax,[bx]
    mov bx,[bx+2]
    pop ds
    cmp word ptr ss:[bp+6],10h
    je video_call
    cmp word ptr ss:[bp+6],16h
    je key_call
    int 21h
    jmp short saved
video_call:
    int 10h
    jmp short saved
key_call:
    int 16h
saved:
    pushf
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov bx,sp
    les di,ss:[bp+8]
    mov ax,ss:[bx+14]
    mov es:[di],ax
    mov ax,ss:[bx+12]
    mov es:[di+2],ax
    mov ax,ss:[bx+10]
    mov es:[di+4],ax
    mov ax,ss:[bx+8]
    mov es:[di+6],ax
    mov ax,ss:[bx+6]
    mov es:[di+8],ax
    mov ax,ss:[bx+4]
    mov es:[di+10],ax
    mov ax,ss:[bx+2]
    mov es:[di+12],ax
    mov ax,ss:[bx]
    mov es:[di+14],ax
    mov ax,ss:[bx+16]
    mov es:[di+16],ax
    add sp,18
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    pop bp
    ret
_cass_int endp

public _cass_tone
_cass_tone proc far
    push bp
    mov bp,sp
    push ax
    push bx
    push cx
    push dx
    push ds
    mov bx,[bp+6]
    cmp bx,20
    jb tone_done
    mov dx,12h
    mov ax,34deh
    div bx
    mov bx,ax
    mov al,0b6h
    out 43h,al
    mov ax,bx
    out 42h,al
    mov al,ah
    out 42h,al
    in al,61h
    mov cl,al
    or al,3
    out 61h,al
    mov ax,40h
    mov ds,ax
    mov bx,ds:[6ch]
    mov dx,ss:[bp+8]
    cmp dx,18
    jbe tone_wait
    mov dx,18
tone_wait:
    mov ax,ds:[6ch]
    sub ax,bx
    cmp ax,dx
    jb tone_wait
    mov al,cl
    out 61h,al
tone_done:
    pop ds
    pop dx
    pop cx
    pop bx
    pop ax
    pop bp
    ret
_cass_tone endp
P86CAS ends
end
