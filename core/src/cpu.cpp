#include "machine.hpp"
#include <bit>
#include <cstdio>
#include <limits>

namespace p86 {
void Machine::fail(const std::string &message) {
    char location[80];
    std::snprintf(location,sizeof(location)," at %04X:%04X (%llu instructions)",instruction_cs,instruction_ip,
                  static_cast<unsigned long long>(instructions));
    fault=message+location;status=P86_FAULT;
}
void Machine::szp(uint32_t value,bool wide) {
    auto v=value&(wide?0xffff:0xff);
    flag(ZF,v==0);flag(SF,v&(wide?0x8000:0x80));
    flag(PF,(std::popcount(unsigned(v&0xff))&1)==0);
}
uint16_t Machine::alu(unsigned op,uint16_t a,uint16_t b,bool wide) {
    uint32_t mask=wide?0xffff:0xff, sign=wide?0x8000:0x80;
    uint32_t lhs=a&mask,rhs=b&mask,v=0,carry=(cpu.flags&CF)?1:0;
    switch(op) {
    case 0: case 2:
        v=lhs+rhs+(op==2?carry:0);flag(CF,v>mask);
        flag(AF,((lhs^rhs^v)&16)!=0);flag(OF,((~(lhs^rhs)&(lhs^v))&sign)!=0);break;
    case 3: case 5: case 7:
        v=lhs-rhs-(op==3?carry:0);flag(CF,lhs<rhs+(op==3?carry:0));
        flag(AF,((lhs^rhs^v)&16)!=0);flag(OF,(((lhs^rhs)&(lhs^v))&sign)!=0);break;
    case 1:v=lhs|rhs;cpu.flags&=~(CF|OF|AF);break;
    case 4:v=lhs&rhs;cpu.flags&=~(CF|OF|AF);break;
    case 6:v=lhs^rhs;cpu.flags&=~(CF|OF|AF);break;
    }
    szp(v,wide);return uint16_t(v&mask);
}
uint16_t Machine::shift(unsigned op,uint16_t value,unsigned count,bool wide) {
    unsigned mask=wide?65535:255, sign=wide?32768:128;
    unsigned v=value&mask;
    if(!count)return uint16_t(v);
    bool last=false;
    for(unsigned i=0;i<count;++i) {
        bool oldCF=cpu.flags&CF;
        switch(op) {
        case 0:last=(v&sign)!=0;v=((v<<1)|unsigned(last))&mask;break;
        case 1:last=v&1;v=(v>>1)|(last?sign:0);break;
        case 2:last=(v&sign)!=0;v=((v<<1)|unsigned(oldCF))&mask;break;
        case 3:last=v&1;v=(v>>1)|(oldCF?sign:0);break;
        case 4:case 6:last=(v&sign)!=0;v=(v<<1)&mask;break;
        case 5:last=v&1;v>>=1;break;
        case 7:last=v&1;v=(v>>1)|(v&sign);break;
        }
        flag(CF,last);
    }
    // OF for counts >1 is undefined; use the final shift's deterministic result.
    if(op==0||op==2||op==4||op==6)flag(OF,((v&sign)!=0)!=last);
    else if(op==1||op==3)flag(OF,((v&sign)!=0)!=((v&(sign>>1))!=0));
    else if(op==5)flag(OF,value&sign);
    else flag(OF,false);
    if(op>=4){szp(v,wide);flag(AF,false);}
    return uint16_t(v);
}
Operand Machine::decode(uint8_t mr,int override) {
    unsigned mod=mr>>6,rm=mr&7;
    if(mod==3)return {true,uint8_t(rm),0,0};
    uint16_t offset=0;bool stack=false;
    switch(rm) {
    case 0:offset=cpu.r[BX]+cpu.r[SI];break;
    case 1:offset=cpu.r[BX]+cpu.r[DI];break;
    case 2:offset=cpu.r[BP]+cpu.r[SI];stack=true;break;
    case 3:offset=cpu.r[BP]+cpu.r[DI];stack=true;break;
    case 4:offset=cpu.r[SI];break;
    case 5:offset=cpu.r[DI];break;
    case 6:if(mod==0)offset=fetch16();else {offset=cpu.r[BP];stack=true;}break;
    case 7:offset=cpu.r[BX];break;
    }
    if(mod==1)offset+=int8_t(fetch8());else if(mod==2)offset+=fetch16();
    return {false,0,cpu.s[override>=0?override:(stack?SS:DS)],offset};
}
uint16_t Machine::get(const Operand &o,bool wide) {
    return o.reg?(wide?cpu.r[o.index]:reg8(o.index)):(wide?word(o.segment,o.offset):byte(o.segment,o.offset));
}
void Machine::put(const Operand &o,bool wide,uint16_t v) {
    if(o.reg){if(wide)cpu.r[o.index]=v;else reg8(o.index,uint8_t(v));}
    else if(wide)word(o.segment,o.offset,v);else byte(o.segment,o.offset,uint8_t(v));
}
bool Machine::condition(unsigned c) const {
    bool cf=cpu.flags&CF,zf=cpu.flags&ZF,sf=cpu.flags&SF,of=cpu.flags&OF,pf=cpu.flags&PF;
    switch(c&14) {
    case 0:return of!=bool(c&1);case 2:return cf!=bool(c&1);
    case 4:return zf!=bool(c&1);case 6:return (cf||zf)!=bool(c&1);
    case 8:return sf!=bool(c&1);case 10:return pf!=bool(c&1);
    case 12:return (sf!=of)!=bool(c&1);default:return (zf||sf!=of)!=bool(c&1);
    }
}
void Machine::interrupt(uint8_t n) {
    push(normalized_flags(cpu.flags));push(cpu.s[CS]);push(cpu.ip);
    cpu.flags&=~(IF|TF);cpu.ip=word(0,n*4);cpu.s[CS]=word(0,n*4+2);cpu.halted=false;
}
void Machine::divide_error() {
    if(cpu286)cpu.ip=instruction_ip;
    interrupt(0);
}
void Machine::step() {
    if(status==P86_FAULT)return;
    instruction_cs=cpu.s[CS];instruction_ip=cpu.ip;
    int seg=-1;uint8_t rep=0,op=0;unsigned prefix_count=0;
    for(;;){
        if(++prefix_count>32){fail("Instruction prefix limit exceeded");return;}
        op=fetch8();
        if(op==0x26){seg=ES;continue;}if(op==0x2e){seg=CS;continue;}
        if(op==0x36){seg=SS;continue;}if(op==0x3e){seg=DS;continue;}
        if(op==0xf2||op==0xf3){rep=op;continue;}if(op==0xf0)continue;
        break;
    }
    ++instructions;
    // Boosted CPUs retain a fixed, conservative I/O bus wait (eight device
    // cycles), rather than accelerating hardware-probe polling loops. The 1x
    // compatibility profile keeps its original four-cycle timing unchanged.
    const bool port_io=(op>=0xe4&&op<=0xe7)||(op>=0xec&&op<=0xef)||(op>=0x6c&&op<=0x6f);
    if(port_io&&cpu_speed>1)cycles+=8;else advance_cpu_cycles(4);
    if(cpu.interrupt_shadow)--cpu.interrupt_shadow;
    if(op<0x40 && (op&7)<=5) {
        unsigned fn=op>>3;bool wide=op&1;uint16_t a,b,result;
        if((op&7)<4){
            auto mr=fetch8();auto dst=decode(mr,seg);unsigned rn=(mr>>3)&7;
            uint16_t rv=wide?cpu.r[rn]:reg8(rn),mv=get(dst,wide);
            a=(op&2)?rv:mv;b=(op&2)?mv:rv;result=alu(fn,a,b,wide);
            if(fn!=7){if(op&2){if(wide)cpu.r[rn]=result;else reg8(rn,uint8_t(result));}else put(dst,wide,result);}
        }else{a=wide?cpu.r[AX]:reg8(0);b=wide?fetch16():fetch8();result=alu(fn,a,b,wide);
            if(fn!=7){if(wide)cpu.r[AX]=result;else reg8(0,uint8_t(result));}}
        return;
    }
    if(op>=0x40&&op<=0x4f){unsigned n=op&7;auto cf=cpu.flags&CF;
        cpu.r[n]=alu(op<0x48?0:5,cpu.r[n],1,true);flag(CF,cf);return;}
    if(op>=0x50&&op<=0x57){auto n=op&7;push(n==SP&&!cpu286?uint16_t(cpu.r[SP]-2):cpu.r[n]);return;}
    if(op>=0x58&&op<=0x5f){auto value=pop();cpu.r[op&7]=value;return;}
    if(op>=0x70&&op<=0x7f){auto disp=int8_t(fetch8());if(condition(op&15))cpu.ip+=disp;return;}
    if(op>=0x90&&op<=0x97){std::swap(cpu.r[AX],cpu.r[op&7]);return;}
    if(op>=0xb0&&op<=0xb7){reg8(op&7,fetch8());return;}
    if(op>=0xb8&&op<=0xbf){cpu.r[op&7]=fetch16();return;}
    switch(op) {
    case 0x06:push(cpu.s[ES]);break;case 0x07:cpu.s[ES]=pop();break;
    case 0x0e:push(cpu.s[CS]);break;case 0x0f:if(cpu286)fail("80286 system instructions are not implemented");else cpu.s[CS]=pop();break;
    case 0x16:push(cpu.s[SS]);break;case 0x17:cpu.s[SS]=pop();cpu.interrupt_shadow=1;break;
    case 0x1e:push(cpu.s[DS]);break;case 0x1f:cpu.s[DS]=pop();break;
    case 0x27:case 0x2f:{ // DAA / DAS
        uint8_t a=reg8(0),old=a;bool oldCF=cpu.flags&CF,oldAF=cpu.flags&AF;
        flag(CF,false);
        if((a&15)>9||oldAF){
            bool carry=op==0x27?unsigned(a)+6>255:a<6;
            a=uint8_t(op==0x27?a+6:a-6);flag(AF,true);flag(CF,oldCF||carry);
        }else flag(AF,false);
        bool high_adjust=old>unsigned(oldAF&&!cpu286?0x9f:0x99)||oldCF;
        if(high_adjust)a=uint8_t(op==0x27?a+0x60:a-0x60);
        flag(CF,high_adjust);
        reg8(0,a);szp(a,false);break;
    }
    case 0x37:case 0x3f:{bool adjust=(reg8(0)&15)>9||(cpu.flags&AF);
        if(adjust&&cpu286){cpu.r[AX]+=op==0x37?0x106:-0x106;}
        else if(adjust){reg8(0,uint8_t(op==0x37?reg8(0)+6:reg8(0)-6));reg8(4,uint8_t(op==0x37?reg8(4)+1:reg8(4)-1));}
        flag(CF,adjust);flag(AF,adjust);reg8(0,reg8(0)&15);break;}
    case 0x60:{auto sp=cpu.r[SP];for(unsigned i=0;i<8;++i)push(i==SP?sp:cpu.r[i]);break;}
    case 0x61:for(int i=7;i>=0;--i){auto v=pop();if(i!=SP)cpu.r[i]=v;}break;
    case 0x62:{auto mr=fetch8();auto o=decode(mr,seg);if(o.reg){fail("BOUND requires memory");break;}
        auto value=int16_t(cpu.r[(mr>>3)&7]);
        if(value<int16_t(word(o.segment,o.offset))||value>int16_t(word(o.segment,uint16_t(o.offset+2)))){cpu.ip=instruction_ip;interrupt(5);}break;}
    case 0x6c:case 0x6d:case 0x6e:case 0x6f:{
        if(rep&&!cpu.r[CX])break;
        bool wide=op&1;auto port=cpu.r[DX];int delta=(wide?2:1)*((cpu.flags&DF)?-1:1);
        if(op&2){auto source=cpu.s[seg<0?DS:seg];out(port,byte(source,cpu.r[SI]));
            if(wide)out(uint16_t(port+1),byte(source,uint16_t(cpu.r[SI]+1)));cpu.r[SI]+=delta;
        }else{byte(cpu.s[ES],cpu.r[DI],in(port));if(wide)byte(cpu.s[ES],uint16_t(cpu.r[DI]+1),in(uint16_t(port+1)));cpu.r[DI]+=delta;}
        if(rep&&--cpu.r[CX])cpu.ip=instruction_ip;advance_cpu_cycles(8);break;}
    case 0x68:push(fetch16());break;case 0x6a:push(uint16_t(int16_t(int8_t(fetch8()))));break;
    case 0x69:case 0x6b:{auto mr=fetch8();auto o=decode(mr,seg);auto a=int16_t(get(o,true));
        auto b=op==0x69?int16_t(fetch16()):int16_t(int8_t(fetch8()));int32_t result=int32_t(a)*b;
        cpu.r[(mr>>3)&7]=uint16_t(result);bool overflow=result!=int16_t(result);flag(CF,overflow);flag(OF,overflow);break;}
    case 0x80:case 0x81:case 0x82:case 0x83:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;
        auto a=get(o,wide);uint16_t b=op==0x81?fetch16():op==0x83?uint16_t(int16_t(int8_t(fetch8()))):fetch8();
        auto fn=(mr>>3)&7;auto result=alu(fn,a,b,wide);if(fn!=7)put(o,wide,result);break;}
    case 0x84:case 0x85:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;
        alu(4,get(o,wide),wide?cpu.r[(mr>>3)&7]:reg8((mr>>3)&7),wide);break;}
    case 0x86:case 0x87:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;unsigned rn=(mr>>3)&7;
        auto a=get(o,wide);uint16_t b=wide?cpu.r[rn]:reg8(rn);put(o,wide,b);
        if(wide)cpu.r[rn]=a;else reg8(rn,uint8_t(a));break;}
    case 0x88:case 0x89:case 0x8a:case 0x8b:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;auto rn=(mr>>3)&7;
        if(op&2){auto v=get(o,wide);if(wide)cpu.r[rn]=v;else reg8(rn,uint8_t(v));}
        else put(o,wide,wide?cpu.r[rn]:reg8(rn));break;}
    case 0x8c:{auto mr=fetch8();auto o=decode(mr,seg);put(o,true,cpu.s[(mr>>3)&3]);break;}
    case 0x8d:{auto mr=fetch8();auto o=decode(mr,seg);if(o.reg){fail("LEA requires memory operand");break;}cpu.r[(mr>>3)&7]=o.offset;break;}
    case 0x8e:{auto mr=fetch8();auto o=decode(mr,seg);auto sn=(mr>>3)&3;cpu.s[sn]=get(o,true);if(sn==SS)cpu.interrupt_shadow=1;break;}
    case 0x8f:{auto mr=fetch8();auto o=decode(mr,seg);auto v=pop();put(o,true,v);break;}
    case 0x98:cpu.r[AX]=uint16_t(int16_t(int8_t(reg8(0))));break;
    case 0x99:cpu.r[DX]=(cpu.r[AX]&0x8000)?0xffff:0;break;
    case 0x9a:{auto ip=fetch16(),cs=fetch16();push(cpu.s[CS]);push(cpu.ip);cpu.s[CS]=cs;cpu.ip=ip;break;}
    case 0x9b:break;
    case 0x9c:push(normalized_flags(cpu.flags));break;
    case 0x9d:cpu.flags=normalized_flags(pop());break;
    case 0x9e:cpu.flags=(cpu.flags&0xff00)|(reg8(4)&0xd5)|2;break;
    case 0x9f:reg8(4,uint8_t(cpu.flags)|2);break;
    case 0xa0:case 0xa1:{auto offset=fetch16();auto s=cpu.s[seg<0?DS:seg];if(op&1)cpu.r[AX]=word(s,offset);else reg8(0,byte(s,offset));break;}
    case 0xa2:case 0xa3:{auto offset=fetch16();auto s=cpu.s[seg<0?DS:seg];if(op&1)word(s,offset,cpu.r[AX]);else byte(s,offset,reg8(0));break;}
    case 0xa4:case 0xa5:case 0xa6:case 0xa7:case 0xaa:case 0xab:case 0xac:case 0xad:case 0xae:case 0xaf:{
        if(rep&&cpu.r[CX]==0)break;
        bool wide=op&1;int delta=(wide?2:1)*((cpu.flags&DF)?-1:1);auto src=cpu.s[seg<0?DS:seg];
        auto load=[&](uint16_t s,uint16_t o)->uint16_t{return wide?word(s,o):byte(s,o);};
        auto save=[&](uint16_t s,uint16_t o,uint16_t v){if(wide)word(s,o,v);else byte(s,o,uint8_t(v));};
        switch(op&0xfe){
        case 0xa4:save(cpu.s[ES],cpu.r[DI],load(src,cpu.r[SI]));cpu.r[SI]+=delta;cpu.r[DI]+=delta;break;
        case 0xa6:alu(5,load(src,cpu.r[SI]),load(cpu.s[ES],cpu.r[DI]),wide);cpu.r[SI]+=delta;cpu.r[DI]+=delta;break;
        case 0xaa:save(cpu.s[ES],cpu.r[DI],wide?cpu.r[AX]:reg8(0));cpu.r[DI]+=delta;break;
        case 0xac:{auto v=load(src,cpu.r[SI]);if(wide)cpu.r[AX]=v;else reg8(0,uint8_t(v));cpu.r[SI]+=delta;break;}
        case 0xae:alu(5,wide?cpu.r[AX]:reg8(0),load(cpu.s[ES],cpu.r[DI]),wide);cpu.r[DI]+=delta;break;
        }
        if(rep){--cpu.r[CX];bool more=cpu.r[CX]!=0;
            if((op&0xfe)==0xa6||(op&0xfe)==0xae)more=more&&((cpu.flags&ZF)!=0)==(rep==0xf3);
            if(more)cpu.ip=instruction_ip;}
        advance_cpu_cycles(8);break;
    }
    case 0xa8:alu(4,reg8(0),fetch8(),false);break;case 0xa9:alu(4,cpu.r[AX],fetch16(),true);break;
    case 0xc0:case 0xc1:case 0xd0:case 0xd1:case 0xd2:case 0xd3:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;
        unsigned count=op<0xd0?fetch8():(op&2)?reg8(1):1;
        if(cpu286)count&=31;
        auto v=get(o,wide);put(o,wide,shift((mr>>3)&7,v,count,wide));advance_cpu_cycles(count);break;}
    case 0xc2:{auto bytes=fetch16();cpu.ip=pop();cpu.r[SP]+=bytes;break;}
    case 0xc3:cpu.ip=pop();break;
    case 0xc4:case 0xc5:{auto mr=fetch8();auto o=decode(mr,seg);if(o.reg){fail("Far pointer requires memory operand");break;}
        auto offset=word(o.segment,o.offset),segment=word(o.segment,uint16_t(o.offset+2));
        cpu.r[(mr>>3)&7]=offset;cpu.s[op==0xc4?ES:DS]=segment;break;}
    case 0xc6:case 0xc7:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;auto v=wide?fetch16():fetch8();put(o,wide,v);break;}
    case 0xc8:{auto size=fetch16();auto level=fetch8()&31;push(cpu.r[BP]);auto frame=cpu.r[SP];
        if(level){for(unsigned i=1;i<unsigned(level);++i){cpu.r[BP]-=2;push(word(cpu.s[SS],cpu.r[BP]));}push(frame);}cpu.r[BP]=frame;cpu.r[SP]-=size;break;}
    case 0xc9:cpu.r[SP]=cpu.r[BP];cpu.r[BP]=pop();break;
    case 0xca:{auto bytes=fetch16();auto ip=pop(),cs=pop();cpu.ip=ip;cpu.s[CS]=cs;cpu.r[SP]+=bytes;break;}
    case 0xcb:{auto ip=pop(),cs=pop();cpu.ip=ip;cpu.s[CS]=cs;break;}
    case 0xcc:interrupt(3);break;case 0xcd:{auto n=fetch8();interrupt(n);break;}
    case 0xce:if(cpu.flags&OF)interrupt(4);break;
    case 0xcf:{auto ip=pop(),cs=pop(),flags=pop();cpu.ip=ip;cpu.s[CS]=cs;cpu.flags=normalized_flags(flags);break;}
    case 0xd4:{auto base=fetch8();auto a=reg8(0);if(!base){szp(0,false);divide_error();break;}reg8(4,a/base);reg8(0,a%base);szp(reg8(0),false);break;}
    case 0xd5:{auto base=fetch8();auto a=uint8_t(reg8(4)*base+reg8(0));cpu.r[AX]=a;szp(a,false);break;}
    case 0xd6:reg8(0,(cpu.flags&CF)?0xff:0);break;
    case 0xd7:reg8(0,byte(cpu.s[seg<0?DS:seg],uint16_t(cpu.r[BX]+reg8(0))));break;
    case 0xd8:case 0xd9:case 0xda:case 0xdb:case 0xdc:case 0xdd:case 0xde:case 0xdf:
        fail("8087 floating-point instructions are not implemented");break;
    case 0xe0:case 0xe1:case 0xe2:case 0xe3:{auto disp=int8_t(fetch8());bool take;
        if(op==0xe3)take=cpu.r[CX]==0;else{--cpu.r[CX];take=cpu.r[CX]!=0;
            if(op==0xe0)take=take&&!(cpu.flags&ZF);if(op==0xe1)take=take&&(cpu.flags&ZF);}
        if(take)cpu.ip+=disp;break;}
    case 0xe4:case 0xe5:case 0xec:case 0xed:{uint16_t port=(op&8)?cpu.r[DX]:fetch8();auto lo=in(port);
        if(op&1)cpu.r[AX]=lo|(uint16_t(in(port+1))<<8);else reg8(0,lo);break;}
    case 0xe6:case 0xe7:case 0xee:case 0xef:{uint16_t port=(op&8)?cpu.r[DX]:fetch8();out(port,reg8(0));if(op&1)out(port+1,reg8(4));break;}
    case 0xe8:{auto displacement=int16_t(fetch16());push(cpu.ip);cpu.ip+=displacement;break;}
    case 0xe9:{auto displacement=int16_t(fetch16());cpu.ip+=displacement;break;}
    case 0xea:{auto ip=fetch16(),cs=fetch16();cpu.ip=ip;cpu.s[CS]=cs;break;}
    case 0xeb:{auto displacement=int8_t(fetch8());cpu.ip+=displacement;break;}
    case 0xf4:cpu.halted=true;status=P86_HALTED;break;
    case 0xf5:cpu.flags^=CF;break;
    case 0xf6:case 0xf7:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;auto v=get(o,wide);unsigned fn=(mr>>3)&7;
        switch(fn){
        case 0:case 1:alu(4,v,wide?fetch16():fetch8(),wide);break;
        case 2:put(o,wide,uint16_t(~v));break;
        case 3:put(o,wide,alu(5,0,v,wide));break;
        case 4:{uint32_t product=uint32_t(wide?cpu.r[AX]:reg8(0))*v;bool overflow;
            if(wide){cpu.r[AX]=uint16_t(product);cpu.r[DX]=uint16_t(product>>16);overflow=cpu.r[DX]!=0;}
            else{cpu.r[AX]=uint16_t(product);overflow=product>255;}flag(CF,overflow);flag(OF,overflow);break;}
        case 5:{int32_t product=wide?int32_t(int16_t(cpu.r[AX]))*int16_t(v):int32_t(int8_t(reg8(0)))*int8_t(v);
            bool overflow=wide?product!=int16_t(product):product!=int8_t(product);
            cpu.r[AX]=uint16_t(product);if(wide)cpu.r[DX]=uint16_t(uint32_t(product)>>16);flag(CF,overflow);flag(OF,overflow);break;}
        case 6:{uint32_t numerator=wide?(uint32_t(cpu.r[DX])<<16)|cpu.r[AX]:cpu.r[AX];
            if(!v||numerator/v>(wide?65535u:255u)){divide_error();break;}
            auto quotient=numerator/v,remainder=numerator%v;
            if(wide){cpu.r[AX]=uint16_t(quotient);cpu.r[DX]=uint16_t(remainder);}
            else{reg8(0,uint8_t(quotient));reg8(4,uint8_t(remainder));}break;}
        case 7:{int64_t numerator=wide?int32_t((uint32_t(cpu.r[DX])<<16)|cpu.r[AX]):int16_t(cpu.r[AX]);
            int64_t divisor=wide?int16_t(v):int8_t(v);
            if(!divisor){divide_error();break;}auto q=numerator/divisor,r=numerator%divisor;
            // Original 8086 microcode rejects the most-negative quotient and
            // REP prefixes toggle the quotient sign (hardware fixture coverage).
            if(q<(wide?(cpu286?-32768:-32767):(cpu286?-128:-127))||q>(wide?32767:127)){divide_error();break;}
            if(rep&&!cpu286)q=-q;
            if(wide){cpu.r[AX]=uint16_t(q);cpu.r[DX]=uint16_t(r);}else{reg8(0,uint8_t(q));reg8(4,uint8_t(r));}break;}
        }break;}
    case 0xf8:flag(CF,false);break;case 0xf9:flag(CF,true);break;
    case 0xfa:flag(IF,false);break;case 0xfb:flag(IF,true);cpu.interrupt_shadow=1;break;
    case 0xfc:flag(DF,false);break;case 0xfd:flag(DF,true);break;
    case 0xfe:case 0xff:{auto mr=fetch8();auto o=decode(mr,seg);bool wide=op&1;auto fn=(mr>>3)&7;auto v=get(o,wide);
        if(fn<2){auto cf=cpu.flags&CF;put(o,wide,alu(fn==0?0:5,v,1,wide));flag(CF,cf);}
        else if(!wide){fail("Unsupported FE instruction group");}
        else if(fn==2){push(cpu.ip);cpu.ip=v;}
        else if(fn==3||fn==5){if(o.reg){fail("Far branch requires memory operand");break;}
            auto cs=word(o.segment,uint16_t(o.offset+2));if(fn==3){push(cpu.s[CS]);push(cpu.ip);}cpu.ip=v;cpu.s[CS]=cs;}
        else if(fn==4)cpu.ip=v;
        else if(fn==6){if(o.reg&&o.index==SP&&!cpu286)v-=2;push(v);}
        else fail("Unsupported FF instruction group");break;}
    default:{char msg[64];std::snprintf(msg,sizeof(msg),"Unsupported opcode %02X",op);fail(msg);break;}
    }
}
}
