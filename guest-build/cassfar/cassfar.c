/* Project86 replacement for the ten CASSFAR interfaces called by SELECT.
 * All memory, keyboard, video and file operations execute in the DOS guest.
 * Large-model C, no CRT startup, heap allocation or host-side UI shortcuts.
 */
#include "layout.h"
typedef unsigned char B;
typedef unsigned U;
typedef B far *F;
/* SELECT owns one synchronous help session. A bounded work area permits
 * in-place wrapping even when the caller owns all remaining DOS memory. */
static B wrap_work[8192];
typedef struct { U ax,bx,cx,dx,si,di,ds,es,flags; } Regs;
extern void far cass_int(U number, Regs far *r);
extern void far cass_tone(U frequency, U duration);
#define W(p,n) (*(U far *)((p)+(n)))
#define V(p,n) ((p)[n])
static F ptr(U seg,U off) { return (F)(((unsigned long)seg<<16)|off); }
static U seg(F p) { return (U)((unsigned long)p>>16); }
static U off(F p) { return (U)(unsigned long)p; }
static F pair(F p,U n) { return ptr(W(p,n+2),W(p,n)); }
static void zero(F p,U n) { while(n--) *p++=0; }
static void copy(F d,F s,U n) { while(n--) *d++=*s++; }
static U min(U a,U b) { return a<b?a:b; }
static void reset(Regs far *r) { zero((F)r,sizeof(*r)); }
static F screen(void) { F b=ptr(0x40,0); return ptr(b[0x49]==7?0xb000:0xb800,W(b,0x4e)); }
static void cell(F video,U row,U col,B ch,B attr) {
    U width=W(ptr(0x40,0),0x4a),i;
    if(!row||!col||row>25||col>width) return;
    i=((row-1)*width+col-1)*2;video[i]=ch;video[i+1]=attr;
}
static B color(F table,U index,U role) {
    if(!table||!index||role>11) return 7;
    return table[(index-1)*12+role];
}
static F vector(F table,U count,U id) {
    if(!id||id>count) return 0;
    table+=(id-1)*4;return ptr(W(table,0),W(table,2));
}
static U queued(F q,U count,U id) { U i;for(i=0;i<count;i++)if(W(q,i*8)==id)return 1;return 0; }
static U key(U wait) {
    Regs r;reset(&r);r.ax=0x100;cass_int(0x16,&r);
    if(!wait&&(r.flags&64)) return 0xffff;
    reset(&r);cass_int(0x16,&r);
    return (r.ax&255)?r.ax&255:r.ax;
}
static U keyfind(F text,U size,U wanted) {
    U i=0,start,k;
    while(i<size) {start=i;k=text[i++];if(!k&&i<size)k=(U)text[i++]<<8;if(k==wanted)return start+1;}
    return 0;
}
static U instr(F p) {
    F s=pair(p,INS_SOFF),f=pair(p,INS_FOFF);U i,j,n=W(p,INS_SLEN),len=W(p,INS_FLEN);
    W(p,INS_RSLT)=0;
    if(W(p,INS_OPT)&INS_FKS) {W(p,INS_RSLT)=keyfind(s,n,W(p,INS_KS));return 0;}
    i=W(p,INS_SPOFF);if(i)i--;
    for(;i<=n&&len<=n-i;i++) {for(j=0;j<len&&s[i+j]==f[j];j++);if(j==len){W(p,INS_RSLT)=i+1;break;}}
    return 0;
}
static U incha(F p) {
    U k=key(W(p,INC_OPT)&INC_KWAIT);W(p,INC_STAT)=0;
    if(k==0xffff)return 0;
    if((W(p,INC_OPT)&INC_AMONO)&&k>='a'&&k<='z')k-=32;
    W(p,INC_KS)=k;W(p,INC_STAT)=INC_KFND;return 0;
}
static U gvido(F p) {
    Regs r;F b=ptr(0x40,0);U i,cols=W(b,0x4a),mode=b[0x49],base=mode==7?0xb000:0xb800;
    zero(p,GV_RESERVED);W(p,GV_STAT1)=mode==7?16:0x242;W(p,GV_STAT2)=mode==7?0:0x10;
    /* Use BIOS capability declarations, not speculative reads of absent
     * adapter ports. VGA provides the EGA-compatible 256 KiB display here. */
    reset(&r);r.ax=0x1a00;cass_int(0x10,&r);
    if((r.ax&255)==0x1a&&((r.bx&255)==7||(r.bx&255)==8)){
        reset(&r);r.ax=0x1200;r.bx=0x10;cass_int(0x10,&r);
        W(p,GV_STAT1)=0x24|(0x400U<<(r.bx&3));
    }
    W(p,GV_SCRWIDTH)=cols*2;W(p,GV_SCRLEN)=cols*50;
    p[GV_CURPAGENUM]=b[0x62];p[GV_VIDMODE]=(B)mode;
    W(p,GV_BASE_6845)=W(b,0x63);W(p,GV_STAT_6845)=W(b,0x63)+6;
    W(p,GV_PHYOFFPAGE)=W(b,0x4e);W(p,GV_PHYSEG)=base;
    W(p,GV_OSLOGOFF)=W(p,GV_APLOGOFF)=W(b,0x4e);W(p,GV_OSLOGSEG)=W(p,GV_APLOGSEG)=base;
    W(p,GV_CSH)=16;W(p,GV_CSW)=8;W(p,GV_NUMLINES)=25;
    for(i=0;i<8;i++){W(p,GV_CURPOS0+i*2)=W(b,0x50+i*2);W(p,GV_CURMOD0+i*2)=W(b,0x60);}
    i=W(b,0x50+b[0x62]*2);W(p,GV_CURROW)=i>>8;W(p,GV_CURCOL)=i&255;
    W(p,GV_CURSTART)=b[0x61];W(p,GV_CUREND)=b[0x60];W(p,GV_CURWIDTH)=1;
    reset(&r);r.ax=0x800;r.bx=(U)b[0x62]<<8;cass_int(0x10,&r);W(p,GV_CURATTR)=r.ax>>8;
    return 0;
}

/* Queue records are private to this replacement: id,row,column,color. The
 * published pointers/counts and child-key list retain their SELECT ABI. */
static void queue_edit(F p,U child) {
    U opt=W(p,QM_OPT1),cap=W(p,child?QM_MAXNUMCHD:QM_MAXNUMPAN),i,j,n;
    U count=child?QM_CHDQUENUM:QM_PANQUENUM,location=child?QM_CHDQUEOFF:QM_PANQUEOFF;
    U push=child?QM_PUSHCHD:QM_PUSHPAN,remove=child?QM_RVMCHD:QM_RVMPAN,pop=child?QM_POPCHD:QM_POPPAN;
    U clear=child?QM_CLSCHD:QM_CLSPAN,save=child?QM_PUSHCQU:QM_PUSHPQU,restore=child?QM_POPCQU:QM_POPPQU;
    U depthfield=QM_RESERVED+(child?2:0),stackfield=QM_RESERVED+(child?6:4);
    U depth=W(p,depthfield),maxdepth=W(p,child?QM_MAXCHDQUE:QM_MAXPANQUE),size=2+cap*8;
    F q=pair(p,location),stack=ptr(W(p,QM_BUFSEG),W(p,stackfield));
    n=W(p,count);
    if(opt&save){if(depth>=maxdepth)W(p,QM_ERROR)|=child?8:4;else{W(stack,depth*size)=n;copy(stack+depth*size+2,q,n*8);depth++;}}
    if(opt&restore){if(!depth)W(p,QM_ERROR)|=child?32:16;else{depth--;n=W(stack,depth*size);copy(q,stack+depth*size+2,n*8);}}
    if(opt&clear)n=0;
    if(opt&pop)n=W(p,QM_ID)>n?0:n-W(p,QM_ID);
    if(opt&remove){for(i=0;i<n&&W(q,i*8)!=W(p,QM_ID);i++);if(i==n)W(p,QM_ERROR)|=child?256:128;else{for(j=i;j+1<n;j++)copy(q+j*8,q+(j+1)*8,8);n--;}}
    if(opt&push){if(n>=cap)W(p,QM_ERROR)|=child?2:1;else{W(q,n*8)=W(p,QM_ID);W(q,n*8+2)=W(p,QM_ROWOVER);W(q,n*8+4)=W(p,QM_COLUMOVER);W(q,n*8+6)=W(p,QM_COLOROVER);n++;}}
    W(p,count)=n;W(p,depthfield)=depth;
}
static U dispq(F p) {
    U a,b,pc,cc,ps,cs,used,i,n=0,k;F q,pcb,t,keys;
    W(p,QM_ERROR)=0;
    if(W(p,QM_OPT1)&QM_INIT){
        pc=W(p,QM_MAXNUMPAN);cc=W(p,QM_MAXNUMCHD);ps=2+pc*8;cs=2+cc*8;
        used=pc*8+cc*8+ps*W(p,QM_MAXPANQUE)+cs*W(p,QM_MAXCHDQUE)+128;
        if(used>W(p,QM_BUFLEN)){W(p,QM_ERROR)=QM_ERRBU;return 0;}
        a=W(p,QM_BUFOFF);b=W(p,QM_BUFSEG);zero(ptr(b,a),used);zero(p+QM_RESERVED,66);
        W(p,QM_PANQUEOFF)=a;W(p,QM_PANQUESEG)=b;a+=pc*8;
        W(p,QM_CHDQUEOFF)=a;W(p,QM_CHDQUESEG)=b;a+=cc*8;
        W(p,QM_RESERVED+4)=a;a+=ps*W(p,QM_MAXPANQUE);W(p,QM_RESERVED+6)=a;a+=cs*W(p,QM_MAXCHDQUE);
        W(p,QM_RETKEYSOFF)=a;W(p,QM_RETKEYSSEG)=b;W(p,QM_RETKEYSLEN)=0;
        W(p,QM_PANQUENUM)=W(p,QM_CHDQUENUM)=0;W(p,QM_BUFLEN)=used;return 0;
    }
    queue_edit(p,0);queue_edit(p,1);keys=pair(p,QM_RETKEYSOFF);
    if(W(p,QM_OPT1)&QM_PUSHPAN){pcb=vector(pair(p,QM_PCBVECOFF),W(p,QM_PCBVECNUM),W(p,QM_ID));if(pcb){
        if(W(p,QM_ROWOVER))W(pcb,PCB_UROW)=W(p,QM_ROWOVER);
        if(W(p,QM_COLUMOVER))W(pcb,PCB_UCOL)=W(p,QM_COLUMOVER);
        if(W(p,QM_COLOROVER))W(pcb,PCB_CCBID)=W(p,QM_COLOROVER);}}
    pcb=vector(pair(p,QM_PCBVECOFF),W(p,QM_PCBVECNUM),W(p,QM_ACTIVEPAN));
    if(pcb){t=pair(pcb,PCB_CHILDOFF);for(i=0;i<W(pcb,PCB_CHILDNUM)&&n<124;i++,t+=14){k=W(t,10);if(k&&queued(pair(p,QM_CHDQUEOFF),W(p,QM_CHDQUENUM),W(t,0))){keys[n++]=(B)k;if(!(k&255))keys[n++]=(B)(k>>8);}}}
    W(p,QM_RETKEYSLEN)=n;return 0;
}
static void paint(F p,F pcb,U row,U col,U ci,U childattr) {
    F v=pair(p,PM_LVBOFF),src;U width=W(pcb,PCB_WIDTH),len=W(pcb,PCB_EXPANDLEN),i,step=1;
    B attr=color(pair(p,PM_CCBVECOFF),ci?ci:W(pcb,PCB_CCBID),childattr?childattr-1:0);
    if(!row)row=W(pcb,PCB_UROW);if(!col)col=W(pcb,PCB_UCOL);if(!width)return;
    src=pair(pcb,PCB_EXPANDOFF);
    if(W(pcb,PCB_OPT1)&8){src=pair(pcb,PCB_MIXEDOFF);len=W(pcb,PCB_MIXEDLEN)/2;step=2;}
    if(W(pcb,PCB_OPT1)&1){for(i=0;i<len;i++)cell(v,row+i/width,col+i%width,' ',attr);}
    else for(i=0;i<len;i++)cell(v,row+i/width,col+i%width,src[i*step],step==2?src[i*2+1]:attr);
}
static U panel(F p) {
    U i,id,row,col,ci,j,start=W(p,PM_PANPDQNUM),count=W(p,PM_PANQUENUM);
    F q=pair(p,PM_PANQUEOFF),pcb,t,c,v=pair(p,PM_LVBOFF);
    if(W(p,PM_OPT1)&PM_CL){for(i=0;i<W(p,PM_LVBLEN)/2;i++){v[i*2]=p[PM_BASECHAR];v[i*2+1]=p[PM_BASEATTR];}}
    W(p,PM_ERROR)=0;if(!start)start=1;
    for(i=start;i<=count;i++){
        id=W(q,(i-1)*8);pcb=vector(pair(p,PM_PCBVECOFF),W(p,PM_PCBVECNUM),id);
        if(!pcb){W(p,PM_ERROR)|=PM_PCBVEC;continue;}
        row=W(q,(i-1)*8+2);col=W(q,(i-1)*8+4);ci=W(q,(i-1)*8+6);
        if(!row)row=W(pcb,PCB_UROW);if(!col)col=W(pcb,PCB_UCOL);
        paint(p,pcb,row,col,ci,0);
        if((W(p,PM_OPT1)&PM_DOQ)&&(!(W(p,PM_OPT1)&PM_DOA)||id==W(p,PM_ACTIVEPAN))){
            t=pair(pcb,PCB_CHILDOFF);
            for(j=0;j<W(pcb,PCB_CHILDNUM);j++,t+=14){c=vector(pair(p,PM_PCBVECOFF),W(p,PM_PCBVECNUM),W(t,0));if(c&&queued(pair(p,PM_CHDQUEOFF),W(p,PM_CHDQUENUM),W(t,0)))paint(p,c,W(t,2)+(W(t,12)&1?0:row-1),W(t,4)+(W(t,12)&1?0:col-1),W(t,6),W(t,8));}
        }
        W(p,PM_PANPDQNUM)=i+1;W(p,PM_PANBRKID)=id;
        if(W(p,PM_OPT1)&PM_BK)return 1;
    }
    if(!(W(p,PM_OPT1)&PM_RF))copy(screen(),v,min(W(p,PM_LVBLEN),4000));
    return 0;
}
static F option(F p,U index,U far *len) {
    F s=pair(p,SCB_OAPOFF);U opt=W(p,SCB_OAOPT),i;
    *len=W(p,SCB_OASLEN);
    if(opt&SSC_PTSB){s+=(index-1)*(*len);return s;}
    s+=(index-1)*(opt&SSC_VTE?4:2);
    if(opt&SSC_VTASO)s=ptr(W(s,0),W(s,2));else s=ptr(W(p,SCB_OASSEG),W(s,0));
    if(opt&SSC_SLSB){*len=opt&SSC_TBSL?W(s,0):s[0];s+=opt&SSC_TBSL?2:1;}
    if(opt&SSC_SBTC){for(i=0;i<255&&s[i]!=p[SCB_OASTERMC];i++);*len=i;}
    return s;
}
static U selectable(F p,U ele) {
    F s=pair(p,SCB_SELOFF);U flags;
    if(!s||!(W(p,SCB_OPT2)&SCB_SKIP))return 1;
    flags=W(s,(ele-1)*2);
    return !(flags&SCB_SKIPON)&&((flags&SCB_ACTIVEON)||(W(p,SCB_OPT3)&SCB_SELACT));
}
static void scrollpaint(F p) {
    U i,j,len,ele,row=W(p,SCB_ROW),col=W(p,SCB_COL),top=W(p,SCB_TOPELE),width=W(p,SCB_WIDTH),n=W(p,SCB_NUMLINE),role,flags;
    F s,v=(W(p,SCB_OPT3)&SCB_LVBOVR)?pair(p,SCB_LVBOFF):screen(),table=pair(p,SCB_CCBVECOFF);
    if(W(p,SCB_OPT3)&SCB_RELSCR){row+=W(p,SCB_RELROW)-1;col+=W(p,SCB_RELCOL)-1;}
    for(i=0;i<n;i++){
        ele=top+i;role=ele==W(p,SCB_CURELE)?1:0;s=0;len=0;
        if(ele&&ele<=W(p,SCB_NUMELE))s=option(p,ele,&len);
        for(j=0;j<width;j++)cell(v,row+i,col+j,s&&j+W(p,SCB_CURCOL)-1<len?s[j+W(p,SCB_CURCOL)-1]:' ',color(table,W(p,SCB_CCBID),role));
        if(s&&pair(p,SCB_SELOFF)){
            flags=W(pair(p,SCB_SELOFF),(ele-1)*2);
            if(W(p,SCB_OPT1)&SCB_DACTIVE)for(j=0;j<W(p,SCB_AILEN);j++)cell(v,row+i,col+W(p,SCB_AICOL)-1+j,(flags&SCB_ACTIVEON)?pair(p,SCB_AIOFF)[j]:' ',color(table,W(p,SCB_CCBID),role));
            if(W(p,SCB_OPT1)&SCB_DCHECK)for(j=0;j<W(p,SCB_CILEN);j++)cell(v,row+i,col+W(p,SCB_CICOL)-1+j,(flags&SCB_SELECTON)?pair(p,SCB_CIOFF)[j]:' ',color(table,W(p,SCB_CCBID),role));
        }
    }
    if((W(p,SCB_OPT2)&SCB_UIND)&&W(p,SCB_NUMELE)>n){
        U r,c,k;F indicator;
        for(k=0;k<2;k++){
            r=W(p,k?SCB_DIROW:SCB_UIROW);c=W(p,k?SCB_DICOL:SCB_UICOL);
            if(W(p,SCB_OPT3)&SCB_RELUIND){r+=W(p,SCB_RELROW)-1;c+=W(p,SCB_RELCOL)-1;}
            indicator=pair(p,k?SCB_DIOFF:SCB_UIOFF);
            for(j=0;j<W(p,k?SCB_DILEN:SCB_UILEN);j++)cell(v,r,c+j,
                (k?top+n<=W(p,SCB_NUMELE):top>1)?indicator[j]:' ',color(table,W(p,SCB_CCBID),5));
        }
    }
}
static U slctp(F p) {
    U k,cur=W(p,SCB_CURELE),top=W(p,SCB_TOPELE),n=W(p,SCB_NUMELE),lines=W(p,SCB_NUMLINE),first=1,i,next,delta,max_top;
    F selected=pair(p,SCB_SELOFF);
    if(!cur)cur=1;if(!top)top=1;if(!W(p,SCB_CURCOL))W(p,SCB_CURCOL)=1;if(!lines)lines=1;
    for(;;){
        if(cur<top)top=cur;if(cur>=top+lines)top=cur-lines+1;
        W(p,SCB_CURELE)=cur;W(p,SCB_TOPELE)=top;scrollpaint(p);
        if(W(p,SCB_OPT1)&SCB_RD)return 0;
        k=first&&(W(p,SCB_OPT1)&SCB_UKS)?W(p,SCB_KS):key(1);first=0;W(p,SCB_KS)=k;
        if(keyfind(pair(p,SCB_RLOFF),W(p,SCB_RLLEN),k)||keyfind(pair(p,SCB_REOFF),W(p,SCB_RELEN),k))return 0;
        if(keyfind(pair(p,SCB_SKOFF),W(p,SCB_SKLEN),k)){
            if(selected){if(W(p,SCB_OPT3)&SCB_SELEXC)for(i=0;i<n;i++)W(selected,i*2)&=~1U;W(selected,(cur-1)*2)|=1;}
            return 0;
        }
        max_top=n>lines?n-lines+1:1;delta=lines-((W(p,SCB_OPT2)&SCB_PM1)&&lines>1?1:0);
        if(W(p,SCB_OPT1)&SCB_LL){
            if(k==0x4800){if(top>1)top--;cur=top;continue;}
            if(k==0x5000){top=min(max_top,top+1);cur=top;continue;}
            if(k==0x4900){top=top>delta?top-delta:1;cur=top;continue;}
            if(k==0x5100){top=min(max_top,top+delta);cur=top;continue;}
        }
        if(k==0x4800||k==0x5000){
            next=cur;
            for(i=0;i<n;i++){
                if(k==0x4800){if(next>1)next--;else if(W(p,SCB_OPT1)&SCB_WRAP)next=n;else{if(W(p,SCB_OPT1)&SCB_FRBF)return 0;break;}}
                else{if(next<n)next++;else if(W(p,SCB_OPT1)&SCB_WRAP)next=1;else{if(W(p,SCB_OPT1)&SCB_FRAL)return 0;break;}}
                if(selectable(p,next)){cur=next;break;}
            }
        }
        else if(k==0x4900){cur=cur>delta?cur-delta:1;top=top>delta?top-delta:1;}
        else if(k==0x5100){cur=min(n,cur+delta);top=min(max_top,top+delta);}
        else if(k==0x4700&&!(W(p,SCB_OPT1)&SCB_RUK))cur=1;
        else if(k==0x4f00&&!(W(p,SCB_OPT1)&SCB_RUK))cur=n;
        else if(W(p,SCB_OPT1)&SCB_RUK)return 0;
    }
}
static U accepts(F s,U n,U value) {
    U i=0;
    while(i<n){
        if(s[i]==','&&i+4<n&&s[i+2]=='-'&&s[i+4]==','){
            if(value>=s[i+1]&&value<=s[i+3])return 1;i+=5;
        }else if(s[i]==','&&i+2<n&&s[i+1]==','&&s[i+2]==','){
            if(value==',')return 1;i+=3;
        }else {if(s[i]==value&&s[i]!=',')return 1;i++;}
    }
    return 0;
}
static U input(F p) {
    F c=vector(pair(p,IN_ICBVECOFF),W(p,IN_ICBVECNUM),W(p,IN_ICBID)),field,def,v,table;
    U len,max,pos,k,i,row,col,width,insert=1,start,left=0,first=1,once,cursor;Regs r;
    W(p,IN_ERROR)=0;if(!c){W(p,IN_ERROR)=IN_RANG;return 0;}
    W(p,IN_ICBOFF)=off(c);W(p,IN_ICBSEG)=seg(c);if(W(p,IN_OPT)&IN_LICBX)return 0;
    field=pair(c,ICB_FIELDOFF);def=pair(c,ICB_DEFOFF);max=W(c,ICB_FIELDLEN);width=W(c,ICB_WIDTH);
    if(!max||!width){W(c,ICB_ENDBYTE)=0;return 0;}
    len=min(max,W(c,ICB_DEFLEN));for(i=0;i<max;i++)field[i]=i<len?def[i]:' ';
    pos=W(c,ICB_CURCHAR);pos=pos?min(pos-1,len):len;row=W(c,ICB_ROW);col=W(c,ICB_COL);
    v=(W(p,IN_OPT)&IN_LVBOV)?pair(p,IN_LVBOFF):screen();table=pair(p,IN_CCBVECOFF);
    for(;;){
        cursor=pos==max?pos-1:pos;
        if(W(c,ICB_OPT3)&ICB_HOR){if(cursor<left)left=cursor;if(cursor>=left+width)left=cursor-width+1;}
        W(c,ICB_HRSTART)=left+1;
        start=0;
        if(W(c,ICB_OPT1)&ICB_BEN){
            cell(v,row,col-1,left?p[IN_DELIMITDIR]:p[IN_DELIMITEN],color(table,W(c,ICB_CCBID),0));
            cell(v,row,col+width,((W(c,ICB_OPT3)&ICB_HOR)&&left+width<max)?p[IN_DELIMITDIR+1]:p[IN_DELIMITEN+1],color(table,W(c,ICB_CCBID),0));
        }
        for(i=0;i<width;i++)cell(v,row,col+start+i,i+left<max?field[i+left]:' ',color(table,W(c,ICB_CCBID),0));
        W(c,ICB_ENDBYTE)=len;W(c,ICB_CURCHAR)=pos+1;
        if(W(c,ICB_OPT1)&ICB_OUT)return 0;
        reset(&r);r.ax=0x200;r.dx=((row-1)<<8)|(col+start+min(pos-left,width-1)-1);cass_int(0x10,&r);
        k=key(1);W(c,ICB_KEYRET)=k;
        if(keyfind(pair(c,ICB_RETOFF),W(c,ICB_RETLEN),k))return 0;
        if(k==0x4b00&&pos)pos--;else if(k==0x4d00&&pos<len)pos++;
        else if(k==0x4700)pos=0;else if(k==0x4f00)pos=len;
        else if(k==0x5200)insert=!insert;
        else if(k==8&&pos){pos--;for(i=pos;i+1<len;i++)field[i]=field[i+1];if(len)field[--len]=' ';}
        else if(k==0x5300&&pos<len){for(i=pos;i+1<len;i++)field[i]=field[i+1];field[--len]=' ';}
        else if(k>=32&&k<256){
            if((W(c,ICB_OPT2)&ICB_UPC)&&k>='a'&&k<='z')k-=32;
            once=accepts(pair(c,ICB_ALL1OFF),W(c,ICB_ALL1LEN),k);
            if(W(c,ICB_ALLLEN)&&!accepts(pair(c,ICB_ALLOFF),W(c,ICB_ALLLEN),k)&&!once)continue;
            if(accepts(pair(c,ICB_SKIPOFF),W(c,ICB_SKIPLEN),k))continue;
            if(once){for(i=0;i<len&&field[i]!=k;i++);if(i<len)continue;}
            if(first&&(W(c,ICB_OPT1)&ICB_CLR)){for(i=0;i<max;i++)field[i]=' ';len=pos=left=0;}
            first=0;if(pos>=max)continue;
            if(insert&&len<max){for(i=len;i>pos;i--)field[i]=field[i-1];len++;}
            field[pos++]=(B)k;if(pos>len)len=pos;W(c,ICB_STATUS)|=1;
        }
    }
}
static U seekread(U handle,U hi,U lo,F dest,U size) {
    Regs r;reset(&r);r.ax=0x4200;r.bx=handle;r.cx=hi;r.dx=lo;cass_int(0x21,&r);if(r.flags&1)return r.ax;
    reset(&r);r.ax=0x3f00;r.bx=handle;r.cx=size;r.ds=seg(dest);r.dx=off(dest);cass_int(0x21,&r);
    return r.flags&1?r.ax:r.ax==size?0:5;
}
static U hlprd(F p) {
    Regs r;B h[12];U handle,i,base,count,width,id,length=0,hi=0,lo=0,error;F name=pair(p,HRD_FILSPOFF),buf=pair(p,HRD_BUFOFF);
    W(p,HRD_ERROR)=W(p,HRD_DOSERROR)=0;reset(&r);r.ax=0x3d00;r.ds=seg(name);r.dx=off(name);cass_int(0x21,&r);
    if(r.flags&1){W(p,HRD_DOSERROR)=r.ax;return 0;}handle=r.ax;
    error=seekread(handle,0,0,h,12);if(error)goto doserror;
    if(W(h,0)!=0x1234){W(p,HRD_ERROR)=HRD_NOTCASFILE;goto finish;}
    if(W(h,4)!=0xfe){W(p,HRD_ERROR)=HRD_NOHLPOBJ;goto finish;}base=W(h,8);
    error=seekread(handle,0,base,h,4);if(error)goto doserror;count=W(h,0);width=W(h,2);
    W(p,HRD_TOPICNUM)=count;W(p,HRD_TOPICLEN)=width;
    if(W(p,HRD_OPT1)&HRD_TOPIC){lo=base+4+count*8;length=count*width;W(p,HRD_TOPICOFF)=off(buf);W(p,HRD_TOPICSEG)=seg(buf);}
    else{for(i=0;i<count;i++){error=seekread(handle,0,base+4+i*8,h,8);if(error)goto doserror;if(W(h,0)==W(p,HRD_ID)){hi=W(h,2);lo=W(h,4);length=W(h,6);break;}}
        if(i==count){W(p,HRD_ERROR)=HRD_NOHELPID;goto finish;}}
    if(length>W(p,HRD_BUFLEN)){W(p,HRD_ERROR)=HRD_BUFSIZE;goto finish;}
    error=seekread(handle,hi,lo,buf,length);if(error)goto doserror;
    W(p,HRD_TEXTLEN)=length;W(p,HRD_TEXTOFF)=off(buf);W(p,HRD_TEXTSEG)=seg(buf);goto finish;
doserror:W(p,HRD_DOSERROR)=error;
finish:reset(&r);r.ax=0x3e00;r.bx=handle;cass_int(0x21,&r);return 0;
}
static U wwrap(F p) {
    F src=pair(p,WWP_SRCTXTOFF),dst=pair(p,WWP_DESBUFOFF);
    U n=W(p,WWP_SRCTXTLEN),width=W(p,WWP_WIDTH),limit=W(p,WWP_DESBUFLEN),at=0,out=0,col=0,start,len,i,autowrap=0;
    W(p,WWP_ERROR)=0;if(!width){W(p,WWP_ERROR)=WWP_LONGWORD;return 0;}
    if(W(p,WWP_OPT1)&WWP_SRCBUFFER){dst=src;limit=W(p,WWP_SRCBUFLEN);if(n>sizeof(wrap_work)){W(p,WWP_ERROR)=WWP_BUFSIZE;return 0;}copy(wrap_work,src,n);src=wrap_work;}
    for(i=0;i<limit;i++)dst[i]=' ';
    while(at<n&&out<limit){
        if(src[at]==p[WWP_SPACESYM]||src[at]==13||src[at]==10){at++;out+=width-col;col=0;autowrap=0;continue;}
        if(src[at]==p[WWP_FORMAT]||src[at]==p[WWP_NOFORMAT]){at++;continue;}
        if(src[at]==' '){if(!autowrap||col){out++;col++;if(col==width){col=0;autowrap=1;}}at++;continue;}
        start=at;while(at<n&&src[at]!=' '&&src[at]!=p[WWP_SPACESYM]&&src[at]!=p[WWP_FORMAT]&&src[at]!=p[WWP_NOFORMAT]&&src[at]!=13&&src[at]!=10)at++;len=at-start;
        /* An attached formatting/paragraph marker participates in CAS's
         * word-fit decision, although the marker itself is not displayed. */
        if(col&&len+(at<n&&src[at]!=' '?1:0)>width-col){out+=width-col;col=0;}autowrap=0;
        for(i=0;i<len&&out<limit;i++){dst[out++]=src[start+i];if(++col==width){col=0;autowrap=1;}}
    }
    if(at<n)W(p,WWP_ERROR)=WWP_BUFSIZE;
    W(p,WWP_NUMLINES)=(out+width-1)/width;
    return 0;
}
U far cass_entry(U which,F p) {
    switch(which){case 0:return dispq(p);case 1:return gvido(p);case 2:return instr(p);
    case 3:cass_tone(W(p,MB_FREQUENCY),W(p,MB_DURATION));return 0;
    case 4:return slctp(p);case 5:return panel(p);case 6:return hlprd(p);
    case 7:return input(p);case 8:return incha(p);case 9:return wwrap(p);}
    return 0;
}
