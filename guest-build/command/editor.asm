; Project86 interactive COMMAND.COM editor. Assembled by the original MASM.
; All input, filesystem searches and output execute in the DOS guest. No TSR,
; host service or kernel patch. Called only from REGCOM, with DS=ES=TRANGROUP.
TRANCODE ENDS
DATARES SEGMENT PUBLIC BYTE
EXTRN P86HCOUNT:BYTE, P86HNEXT:BYTE, P86HISTORY:BYTE
EXTRN P86HDTA:DWORD, P86HDTAON:BYTE
DATARES ENDS
TRANSPACE SEGMENT PUBLIC BYTE
EXTRN P86LEN:WORD, P86POS:WORD, P86OLD:WORD, P86ANCHOR:WORD
EXTRN P86COLS:WORD, P86ROWS:WORD, P86PAGE:BYTE, P86ATTR:BYTE
EXTRN P86INSERT:BYTE, P86AGE:BYTE, P86DRAFTLEN:WORD, P86DRAFTPOS:WORD
EXTRN P86TEMPLEN:WORD, P86DRAFT:BYTE, P86TEMPLATE:BYTE, P86ACTIVE:BYTE
EXTRN P86BASE:WORD, P86TAIL:WORD, P86TAILSIZE:WORD, P86PATTERN:BYTE
EXTRN P86SAVED:BYTE, P86DTA:BYTE, P86NEWLEN:WORD
TRANSPACE ENDS
TRANCODE SEGMENT PUBLIC BYTE
ASSUME CS:TRANGROUP, DS:TRANGROUP, ES:RESGROUP, SS:TRANGROUP

P86READ PROC NEAR
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov es,[RESSEG]
    cmp es:[P86HDTAON],0
    je p86cleanentry
    call p86restoredta
p86cleanentry:
    ; Only console handles with the standard input/output device identity.
    ; Redirection, NUL and non-console devices keep DOS's original line input.
    xor bx,bx
    mov ax,4400h
    int 21h
    jc p86fallback
    and dx,81h
    cmp dx,81h
    jne p86fallback
    inc bx
    mov ax,4400h
    int 21h
    jc p86fallback
    and dx,82h
    cmp dx,82h
    jne p86fallback
    ; The editor moves single-byte characters. Preserve DOS DBCS editing when
    ; active lead-byte ranges exist, instead of splitting a multi-byte name.
    push ds
    mov ax,6300h
    int 21h
    cmp word ptr [si],0
    pop ds
    jne p86fallback
    mov ah,0fh
    int 10h
    cmp al,3
    jbe p86text
    cmp al,7
    jne p86fallback
p86text:
    xor al,al
    xchg al,ah
    mov [P86COLS],ax
    mov [P86PAGE],bh
    push es
    mov ax,40h
    mov es,ax
    xor ax,ax
    mov al,es:[84h]
    inc ax
    cmp ax,25
    jae p86rowsok
    mov ax,25
p86rowsok:
    mov [P86ROWS],ax
    pop es
    mov ah,08h
    int 10h
    mov [P86ATTR],ah
    call p86getanchor
    jmp p86init
p86fallback:
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    mov ah,0ah
    int 21h
    ret
p86init:
    push cs
    pop es
    xor ax,ax
    mov [P86LEN],ax
    mov [P86POS],ax
    mov [P86OLD],ax
    mov [P86AGE],al
    mov [P86ACTIVE],al
    mov [P86TEMPLEN],ax
    mov [P86INSERT],1
    ; F1/F3 retain the most recent interactive command as their template.
    mov es,[RESSEG]
    cmp es:[P86HCOUNT],0
    je p86notemplate
    mov al,es:[P86HNEXT]
    dec al
    and ax,15
    mov cl,7
    shl ax,cl
    mov si,ax
    add si,OFFSET RESGROUP:P86HISTORY
    xor cx,cx
    mov cl,es:[si]
    mov [P86TEMPLEN],cx
    inc si
    mov di,OFFSET TRANGROUP:P86TEMPLATE
p86templatecopy:
    jcxz p86notemplate
    mov al,es:[si]
    mov [di],al
    inc si
    inc di
    loop p86templatecopy
p86notemplate:
    push cs
    pop es
p86key:
    mov ah,08h
    int 21h
    cmp al,9
    jne p86nottab
    call p86complete
    jmp p86drawkey
p86nottab:
    mov [P86ACTIVE],0
    or al,al
    jnz p86ascii
    mov ah,08h
    int 21h
    jmp p86extended
p86ascii:
    cmp al,13
    jne p86notenter
    jmp p86accept
p86notenter:
    cmp al,27
    je p86clear
    cmp al,24
    je p86clear
    cmp al,8
    je p86backspace
    cmp al,127
    je p86backspace
    cmp al,10
    je p86key
    cmp al,32
    jae p86character
    cmp al,26
    je p86character
    jmp p86key
p86character:
    call p86put
    jmp p86drawkey
p86clear:
    xor ax,ax
    mov [P86LEN],ax
    mov [P86POS],ax
    mov [P86AGE],al
    jmp p86drawkey
p86backspace:
    cmp [P86POS],0
    je p86key
    dec [P86POS]
    call p86delete
p86drawkey:
    call p86draw
    jmp p86key
p86extended:
    cmp al,48h
    jne p86notup
    call p86up
    jmp p86drawkey
p86notup:
    cmp al,50h
    jne p86notdown
    call p86down
    jmp p86drawkey
p86notdown:
    cmp al,4bh
    jne p86notleft
    cmp [P86POS],0
    je p86drawkey
    dec [P86POS]
    jmp p86drawkey
p86notleft:
    cmp al,4dh
    jne p86notright
    mov ax,[P86POS]
    cmp ax,[P86LEN]
    jae p86f1
    inc [P86POS]
    jmp p86drawkey
p86notright:
    cmp al,47h
    jne p86nothome
    mov [P86POS],0
    jmp p86drawkey
p86nothome:
    cmp al,4fh
    jne p86notend
    mov ax,[P86LEN]
    mov [P86POS],ax
    jmp p86drawkey
p86notend:
    cmp al,53h
    jne p86notdelete
    call p86delete
    jmp p86drawkey
p86notdelete:
    cmp al,52h
    jne p86notinsert
    xor [P86INSERT],1
    jmp p86key
p86notinsert:
    cmp al,3bh
    je p86f1
    cmp al,3dh
    je p86f3
    cmp al,3ch
    je p86f2
    cmp al,3eh
    je p86f4
    cmp al,3fh
    jne p86notf5
    jmp p86f5
p86notf5:
    cmp al,40h
    jne p86unknown
    mov al,26
    jmp p86character
p86unknown:
    jmp p86key
p86f1:
    mov bx,[P86POS]
    cmp bx,[P86TEMPLEN]
    jae p86unknown
    mov al,[P86TEMPLATE+bx]
    call p86put
    jmp p86drawkey
p86f3:
    mov bp,[P86TEMPLEN]
    jmp p86copyuntil
p86f2:
    mov ah,08h
    int 21h
    or al,al
    jz p86consumeextended
    cmp al,27
    je p86unknown
    mov bx,[P86POS]
p86findtemplate:
    cmp bx,[P86TEMPLEN]
    jae p86f3
    cmp al,[P86TEMPLATE+bx]
    je p86foundtemplate
    inc bx
    jmp p86findtemplate
p86foundtemplate:
    mov bp,bx
p86copyuntil:
    mov bx,[P86POS]
    cmp bx,bp
    jae p86copied
    cmp [P86LEN],127
    jae p86copied
    mov al,[P86TEMPLATE+bx]
    call p86put
    jmp p86copyuntil
p86copied:
    jmp p86drawkey
p86consumeextended:
    mov ah,08h
    int 21h
    jmp p86key
p86f4:
    mov ah,08h
    int 21h
    or al,al
    jz p86consumeextended
    cmp al,27
    je p86copied
    mov bp,ax
p86f4loop:
    mov bx,[P86POS]
    cmp bx,[P86LEN]
    jae p86copied
    mov ax,bp
    cmp al,[UCOMBUF+2+bx]
    je p86copied
    call p86delete
    jmp p86f4loop
p86f5:
    mov cx,[P86LEN]
    mov [P86TEMPLEN],cx
    mov si,OFFSET TRANGROUP:UCOMBUF+2
    mov di,OFFSET TRANGROUP:P86TEMPLATE
    rep movsb
    mov al,13
    call p86out
    mov al,10
    call p86out
    call p86getanchor
    mov [P86OLD],0
    jmp p86clear

p86accept:
    mov ax,[P86LEN]
    mov [P86POS],ax
    call p86draw
    mov bx,[P86LEN]
    mov [UCOMBUF+1],bl
    mov byte ptr [UCOMBUF+2+bx],13
    call p86savehistory
    mov al,13
    call p86out
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
P86READ ENDP

; Insert or overwrite AL at the logical cursor. The DOS 0Ah limit includes CR.
p86put PROC NEAR
    mov bx,[P86POS]
    cmp bx,[P86LEN]
    jae p86insertchar
    cmp [P86INSERT],0
    je p86storechar
p86insertchar:
    cmp [P86LEN],127
    jae p86bell
    mov si,[P86LEN]
p86shiftchar:
    cmp si,bx
    jbe p86shifted
    mov dl,[UCOMBUF+1+si]
    mov [UCOMBUF+2+si],dl
    dec si
    jmp p86shiftchar
p86shifted:
    inc [P86LEN]
p86storechar:
    mov [UCOMBUF+2+bx],al
    inc [P86POS]
    ret
p86put ENDP
p86bell PROC NEAR
    mov al,7
    call p86out
    ret
p86bell ENDP
p86delete PROC NEAR
    mov bx,[P86POS]
    cmp bx,[P86LEN]
    jae p86deleted
    dec [P86LEN]
p86delshift:
    cmp bx,[P86LEN]
    jae p86deleted
    mov al,[UCOMBUF+3+bx]
    mov [UCOMBUF+2+bx],al
    inc bx
    jmp p86delshift
p86deleted:
    ret
p86delete ENDP

p86up PROC NEAR
    mov es,[RESSEG]
    mov al,[P86AGE]
    cmp al,es:[P86HCOUNT]
    jae p86historydone
    or al,al
    jnz p86older
    push cs
    pop es
    mov cx,[P86LEN]
    mov [P86DRAFTLEN],cx
    mov ax,[P86POS]
    mov [P86DRAFTPOS],ax
    mov si,OFFSET TRANGROUP:UCOMBUF+2
    mov di,OFFSET TRANGROUP:P86DRAFT
    rep movsb
p86older:
    inc [P86AGE]
    jmp p86recall
p86up ENDP
p86down PROC NEAR
    cmp [P86AGE],0
    je p86historydone
    dec [P86AGE]
    jnz p86recall
    mov cx,[P86DRAFTLEN]
    mov [P86LEN],cx
    mov ax,[P86DRAFTPOS]
    mov [P86POS],ax
    mov si,OFFSET TRANGROUP:P86DRAFT
    mov di,OFFSET TRANGROUP:UCOMBUF+2
    rep movsb
    ret
p86down ENDP
p86recall PROC NEAR
    mov es,[RESSEG]
    xor ax,ax
    mov al,es:[P86HNEXT]
    sub al,[P86AGE]
    and ax,15
    mov cl,7
    shl ax,cl
    mov si,ax
    add si,OFFSET RESGROUP:P86HISTORY
    xor cx,cx
    mov cl,es:[si]
    mov [P86LEN],cx
    mov [P86POS],cx
    inc si
    mov di,OFFSET TRANGROUP:UCOMBUF+2
p86recallcopy:
    jcxz p86historydone
    mov al,es:[si]
    mov [di],al
    inc si
    inc di
    loop p86recallcopy
p86historydone:
    push cs
    pop es
    ret
p86recall ENDP
p86savehistory PROC NEAR
    ; Empty/whitespace-only lines and consecutive duplicates consume no slot.
    mov cx,[P86LEN]
    mov si,OFFSET TRANGROUP:UCOMBUF+2
p86nonblank:
    jcxz p86historydone
    lodsb
    cmp al,' '
    jne p86checkduplicate
    loop p86nonblank
    jmp p86historydone
p86checkduplicate:
    mov es,[RESSEG]
    cmp es:[P86HCOUNT],0
    je p86saveentry
    xor ax,ax
    mov al,es:[P86HNEXT]
    dec al
    and ax,15
    mov cl,7
    shl ax,cl
    mov di,ax
    add di,OFFSET RESGROUP:P86HISTORY
    mov cx,[P86LEN]
    cmp cl,es:[di]
    jne p86saveentry
    inc di
    mov si,OFFSET TRANGROUP:UCOMBUF+2
    repe cmpsb
    je p86historydone
p86saveentry:
    xor ax,ax
    mov al,es:[P86HNEXT]
    mov cl,7
    shl ax,cl
    mov di,ax
    add di,OFFSET RESGROUP:P86HISTORY
    mov cx,[P86LEN]
    mov al,cl
    stosb
    mov si,OFFSET TRANGROUP:UCOMBUF+2
    rep movsb
    inc es:[P86HNEXT]
    and es:[P86HNEXT],15
    cmp es:[P86HCOUNT],16
    jae p86savedentry
    inc es:[P86HCOUNT]
p86savedentry:
    jmp p86historydone
p86savehistory ENDP

; BIOS cursor positioning plus ordinary DOS character output. Redraw spans
; wrapped rows. Pre-scroll before writing the last cell so the anchor stays valid.
p86getanchor PROC NEAR
    mov bh,[P86PAGE]
    mov ah,3
    int 10h
    mov cx,dx
    xor ch,ch
    xor ax,ax
    mov al,dh
    mul [P86COLS]
    add ax,cx
    mov [P86ANCHOR],ax
    ret
p86getanchor ENDP
p86cursor PROC NEAR
    xor dx,dx
    div [P86COLS]
    mov dh,al
    mov bh,[P86PAGE]
    mov ah,2
    int 10h
    ret
p86cursor ENDP
; Width of first CX input bytes in AX, rendering control-Z as ^Z.
p86width PROC NEAR
    xor ax,ax
    mov si,OFFSET TRANGROUP:UCOMBUF+2
p86widthloop:
    jcxz p86widthdone
    inc ax
    cmp byte ptr [si],32
    jae p86widthone
    inc ax
p86widthone:
    inc si
    loop p86widthloop
p86widthdone:
    ret
p86width ENDP
p86draw PROC NEAR
    mov cx,[P86LEN]
    call p86width
    mov bp,ax
    cmp ax,[P86OLD]
    jae p86maxwidth
    mov ax,[P86OLD]
p86maxwidth:
    push ax
    add ax,[P86ANCHOR]
    xor dx,dx
    div [P86COLS]
    sub ax,[P86ROWS]
    jb p86noscroll
    inc ax
    push ax
    mov ah,6
    mov bh,[P86ATTR]
    xor cx,cx
    mov dx,[P86COLS]
    dec dl
    mov ax,[P86ROWS]
    dec al
    mov dh,al
    pop ax
    push ax
    mov ah,6
    int 10h
    pop ax
    mul [P86COLS]
    sub [P86ANCHOR],ax
p86noscroll:
    mov ax,[P86ANCHOR]
    call p86cursor
    mov cx,[P86LEN]
    mov si,OFFSET TRANGROUP:UCOMBUF+2
p86drawloop:
    jcxz p86blanktail
    lodsb
    cmp al,32
    jae p86drawplain
    push ax
    mov al,'^'
    call p86out
    pop ax
    add al,64
p86drawplain:
    call p86out
    loop p86drawloop
p86blanktail:
    pop cx
    sub cx,bp
    mov al,' '
p86blankloop:
    jcxz p86drawend
    call p86out
    loop p86blankloop
p86drawend:
    mov [P86OLD],bp
    mov cx,[P86POS]
    call p86width
    add ax,[P86ANCHOR]
    call p86cursor
    ret
p86draw ENDP
p86out PROC NEAR
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    mov dl,al
    mov ah,2
    int 21h
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
p86out ENDP

; Completion uses a private DOS DTA and restores the caller's DTA before return.
; A Tab sequence keeps its original prefix/tail and enumerates matches, wrapping
; after the last match. Any other key ends the sequence. No filesystem writes.
p86complete PROC NEAR
    cmp [P86ACTIVE],0
    je p86newpattern
    jmp p86searchnext
p86newpattern:
    mov cx,[P86LEN]
    mov si,OFFSET TRANGROUP:UCOMBUF+2
    mov di,OFFSET TRANGROUP:P86SAVED
    rep movsb
    ; Find token boundaries around the cursor. Quotes and wildcards are left
    ; unchanged; DOS 4 short names do not require quoted long-name handling.
    mov bx,[P86POS]
    mov dx,bx
p86tokenleft:
    or bx,bx
    jz p86tokenstart
    mov al,[P86SAVED+bx-1]
    call p86delimiter
    jz p86tokenstart
    dec bx
    jmp p86tokenleft
p86tokenstart:
    mov si,bx
    mov di,OFFSET TRANGROUP:P86PATTERN
    mov [P86BASE],bx
    xor bp,bp
p86prefix:
    cmp bx,dx
    jae p86prefixdone
    mov al,[P86SAVED+bx]
    cmp al,'"'
    je p86completionabort
    cmp al,'*'
    je p86completionabort
    cmp al,'?'
    je p86completionabort
    cmp al,32
    jb p86completionabort
    stosb
    inc bx
    cmp al,'\'
    je p86pathseparator
    cmp al,':'
    je p86pathseparator
    cmp al,'.'
    jne p86prefix
    mov bp,1
    jmp p86prefix
p86pathseparator:
    mov [P86BASE],bx
    xor bp,bp
    jmp p86prefix
p86completionabort:
    mov [P86ACTIVE],0
    call p86bell
    ret
p86prefixdone:
    mov al,'*'
    stosb
    or bp,bp
    jnz p86endpattern
    mov al,'.'
    stosb
    mov al,'*'
    stosb
p86endpattern:
    xor al,al
    stosb
    ; Remove the untyped remainder of this basename, preserving later arguments.
    mov bx,[P86POS]
p86tokenright:
    cmp bx,[P86LEN]
    jae p86tailfound
    mov al,[P86SAVED+bx]
    call p86delimiter
    jz p86tailfound
    cmp al,'"'
    je p86completionabort
    cmp al,'\'
    je p86completionabort
    cmp al,':'
    je p86completionabort
    inc bx
    jmp p86tokenright
p86tailfound:
    mov [P86TAIL],bx
    mov ax,[P86LEN]
    sub ax,bx
    mov [P86TAILSIZE],ax
    ; Save DTA immediately around searches, never across a blocking key read.
    call p86setdta
    call p86findfirst
    jmp p86searchresult
p86searchnext:
    call p86setdta
    mov ah,4fh
    int 21h
    jnc p86searchresult
    call p86findfirst
p86searchresult:
    jc p86searchfail
    cmp byte ptr [P86DTA+30],'.'
    jne p86match
    mov ah,4fh
    int 21h
    jmp p86searchresult
p86searchfail:
    call p86restoredta
    jmp p86completionabort
p86match:
    mov si,OFFSET TRANGROUP:P86DTA+30
    xor cx,cx
p86namelen:
    cmp byte ptr [si],0
    je p86nameend
    inc si
    inc cx
    jmp p86namelen
p86nameend:
    mov ax,[P86BASE]
    add ax,cx
    ; DOS 4 CD rejects a non-root directory ending in a separator. Complete
    ; only the name; the user types '\' explicitly to continue a nested path.
    mov [P86NEWLEN],ax
    add ax,[P86TAILSIZE]
    cmp ax,127
    ja p86searchfail
    mov [P86LEN],ax
    mov ax,[P86NEWLEN]
    mov [P86POS],ax
    mov cx,[P86BASE]
    mov si,OFFSET TRANGROUP:P86SAVED
    mov di,OFFSET TRANGROUP:UCOMBUF+2
    rep movsb
    mov si,OFFSET TRANGROUP:P86DTA+30
p86copyname:
    lodsb
    or al,al
    jz p86copiedname
    stosb
    jmp p86copyname
p86copiedname:
    mov si,[P86TAIL]
    add si,OFFSET TRANGROUP:P86SAVED
    mov cx,[P86TAILSIZE]
    rep movsb
    mov [P86ACTIVE],1
    call p86restoredta
    ret
p86complete ENDP
p86delimiter PROC NEAR
    cmp al,' '
    je p86delimitdone
    cmp al,9
    je p86delimitdone
    cmp al,'>'
    je p86delimitdone
    cmp al,'<'
    je p86delimitdone
    cmp al,'|'
    je p86delimitdone
    cmp al,'='
    je p86delimitdone
    cmp al,','
    je p86delimitdone
    cmp al,';'
p86delimitdone:
    ret
p86delimiter ENDP
p86setdta PROC NEAR
    mov ah,2fh
    int 21h
    mov dx,es
    mov es,[RESSEG]
    mov word ptr es:[P86HDTA],bx
    mov word ptr es:[P86HDTA+2],dx
    mov es:[P86HDTAON],1
    push cs
    pop es
    mov dx,OFFSET TRANGROUP:P86DTA
    mov ah,1ah
    int 21h
    ret
p86setdta ENDP
p86findfirst PROC NEAR
    mov dx,OFFSET TRANGROUP:P86PATTERN
    mov cx,10h
    mov ah,4eh
    int 21h
    ret
p86findfirst ENDP
p86restoredta PROC NEAR
    push ds
    mov es,[RESSEG]
    lds dx,es:[P86HDTA]
    mov ah,1ah
    int 21h
    pop ds
    mov es,[RESSEG]
    mov es:[P86HDTAON],0
    push cs
    pop es
    ret
p86restoredta ENDP
; Identifies the compiled implementation in provenance validation.
    db 'Project86 command editor v2',0
