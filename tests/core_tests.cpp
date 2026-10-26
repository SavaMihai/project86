#include "project86.h"
#include <array>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <vector>
using Handle=std::unique_ptr<P86Machine,decltype(&p86_destroy)>;
static P86CPUState state(P86Machine *m){P86CPUState s{};p86_get_cpu(m,&s);return s;}
static void program(P86Machine *m,std::initializer_list<uint8_t> bytes,P86CPUState s={}){
    p86_reset(m);s.cs=0x1000;s.ip=0x100;s.ss=0x2000;if(!s.sp)s.sp=0xfffe;if(!s.flags)s.flags=0xf002;
    uint32_t a=0x10100;for(auto b:bytes)p86_write_memory(m,a++,b);p86_set_cpu(m,&s);
}
static void steps(P86Machine *m,unsigned n){for(unsigned i=0;i<n;++i)assert(p86_step_cpu(m)!=P86_FAULT);}
int main(){
    Handle handle(p86_create(),p86_destroy);assert(handle);auto *m=handle.get();
    program(m,{0xb8,0xff,0x7f,0x05,1,0});steps(m,2);auto s=state(m);assert(s.ax==0x8000&&(s.flags&0x800)&&!(s.flags&1));
    program(m,{0xb8,0xff,0xff,0xf9,0x15,0,0});steps(m,3);s=state(m);assert(s.ax==0&&(s.flags&0x41)==0x41);
    program(m,{0xb8,0,0,0x2d,1,0});steps(m,2);s=state(m);assert(s.ax==65535&&(s.flags&0x91)==0x91);
    program(m,{0xf9,0x40,0x48});steps(m,3);assert(state(m).flags&1);
    program(m,{0xbc,0,1,0x54,0x58});steps(m,3);s=state(m);assert(s.ax==0xfe&&s.sp==0x100); // 8086 PUSH SP semantics
    program(m,{0x26,0x8b,0x07},{.bx=0x1234,.es=0x3000});p86_write_memory(m,0x31234,0x34);p86_write_memory(m,0x31235,0x12);steps(m,1);assert(state(m).ax==0x1234);
    program(m,{0x8b,0x46,0},{.bp=0x1234});p86_write_memory(m,0x21234,0xcd);p86_write_memory(m,0x21235,0xab);steps(m,1);assert(state(m).ax==0xabcd);
    program(m,{0xa1,0xff,0xff},{.ds=0xffff});p86_write_memory(m,0x0ffef,0x12);p86_write_memory(m,0xffff0,0x34);steps(m,1);assert(state(m).ax==0x3412);
    program(m,{0xa0,0x10,0},{.ds=0xffff});p86_write_memory(m,0,0x42);steps(m,1);assert(state(m).ax==0x42);
    program(m,{0xe8,0,0},{.sp=1});steps(m,1);assert(state(m).sp==0xffff&&p86_read_memory(m,0x20000)==1);
    program(m,{0xe8,1,0,0xf4,0xb8,0x55,0xaa,0xc3});steps(m,3);assert(state(m).ip==0x103&&state(m).ax==0xaa55);
    program(m,{0x31,0xc0,0x74,2,0xb0,1,0xb3,2});steps(m,3);assert(state(m).ax==0&&state(m).bx==2);
    program(m,{0xf3,0xa4},{.cx=3,.si=0x200,.di=0x300,.es=0x1000,.ds=0x1000});
    for(unsigned i=0;i<3;++i)p86_write_memory(m,0x10200+i,uint8_t(i+1));steps(m,3);assert(state(m).cx==0&&state(m).ip==0x102);assert(p86_read_memory(m,0x10302)==3);
    program(m,{0x31,0xc0,0xf7,0xf0});steps(m,2);s=state(m);assert(s.cs==0xf000&&s.ip==0x1000&&s.sp==0xfff8); // division trap
    program(m,{0xc6,0x06,0x07,0x01,0x2a,0xb0,0,0});steps(m,2);assert(state(m).ax==0); // write next immediate, then execute it
    program(m,{0xc6,0x06,0x06,0x01,0x2a,0xb0,0},{.ds=0x1000});steps(m,2);assert(state(m).ax==42);
    program(m,{0x66});assert(p86_step_cpu(m)==P86_FAULT);P86Snapshot snapshot{};p86_get_snapshot(m,&snapshot);assert(std::string(snapshot.message).find("1000:0100")!=std::string::npos);
    p86_load_demo(m);assert(p86_run(m,10000)==P86_WAITING_KEY);p86_key(m,'Z',0x2c,1);assert(p86_run(m,10000)==P86_WAITING_KEY);
    std::array<uint8_t,4000> text{};assert(p86_copy_text(m,text.data(),text.size())==4000);bool found=false;for(unsigned i=0;i<2000;++i)found|=text[i*2]=='Z';assert(found);
    p86_reset(m);p86_write_port(m,0x3fb,0x80);p86_write_port(m,0x3f8,96);p86_write_port(m,0x3f9,0);assert(p86_read_port(m,0x3f8)==96);
    p86_write_port(m,0x3fb,2);p86_write_port(m,0x3fc,3);assert(p86_read_port(m,0x3f8)=='M');
    assert(p86_read_port(m,0x3f8)==0x40&&p86_read_port(m,0x3f8)==0&&p86_read_port(m,0x3f8)==0);
    p86_mouse(m,-3,4,1);assert(p86_read_port(m,0x3f8)==0x63);assert(p86_read_port(m,0x3f8)==61);assert(p86_read_port(m,0x3f8)==4);
    p86_write_port(m,0x43,0xb6);p86_write_port(m,0x42,0x34);p86_write_port(m,0x42,0x12);p86_write_port(m,0x61,3);
    p86_enable_audio(m,1);p86_run_cycles(m,20000);
    std::array<float,128> sound{};assert(p86_read_audio(m,sound.data(),sound.size())==128);bool audible=false;for(auto v:sound){assert(std::isfinite(v)&&std::abs(v)<=0.12f);audible|=v!=0;}assert(audible);
    assert(!p86_attach_floppy(m,"/this/file/does/not/exist",0));
    std::cout<<"Core regressions passed: arithmetic, flags, addressing, flow, stack, strings, traps, self-modifying code, BIOS input, serial mouse, speaker, errors.\n";
}
