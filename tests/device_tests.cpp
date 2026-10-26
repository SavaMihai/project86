#include "machine.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <memory>
using namespace p86;

static void idle(Machine &m) {
    m.reset();
    m.cpu.s[CS]=m.cpu.s[SS]=0x1000; m.cpu.ip=0x100; m.cpu.r[SP]=0xfffe; m.cpu.flags=0x202;
    const uint8_t code[]={0xfb,0xf4,0xeb,0xfd};
    std::copy(std::begin(code),std::end(code),m.memory.begin()+0x10100);
}
static void opl(Machine &m,uint8_t reg,uint8_t value) {m.out(0x388,reg);m.out(0x389,value);}
int main() {
    auto handle=std::unique_ptr<P86Machine,decltype(&p86_destroy)>(p86_create(),p86_destroy);
    auto &m=handle->impl;
    // Capability probes issued by SELECT/CASSFAR and the real KEYB driver.
    // A VGA without Convertible/TopView extensions preserves the supplied
    // pointer. Enhanced keyboard support answers KEYB's 92h probe with 80h.
    idle(m);m.cpu.s[DS]=0x1000;
    const uint8_t probes[]={0xb8,0x00,0x15,0x31,0xd2,0x8e,0xc2,0xbf,0x34,0x12,0xcd,0x10,
        0xa3,0x00,0x02,0x8c,0xc0,0xa3,0x02,0x02,
        0xb8,0x22,0xfe,0xba,0x00,0xb8,0x8e,0xc2,0xcd,0x10,
        0xa3,0x04,0x02,0x8c,0xc0,0xa3,0x06,0x02,
        0xb8,0x01,0x92,0xcd,0x16,0xa3,0x08,0x02,0xfa,0xf4};
    std::copy(std::begin(probes),std::end(probes),m.memory.begin()+0x10100);
    p86_run(handle.get(),1000);
    assert(m.status==P86_HALTED&&m.word(0x1000,0x200)==0x1500&&m.word(0x1000,0x202)==0);
    assert(m.word(0x1000,0x204)==0xfe22&&m.word(0x1000,0x206)==0xb800);
    assert(m.word(0x1000,0x208)==0x8001&&m.cpu.r[DI]==0x1234);
    // Serial mouse reset/power sequencing: movement while DTR/RTS are low
    // previously filled RX ahead of the identification byte during DOS boot.
    idle(m);
    for(unsigned n=0;n<100;++n)p86_mouse(handle.get(),1,-1,0);
    assert(m.serial_rx.empty());
    m.out(0x3fc,1);p86_mouse(handle.get(),3,2,1);assert(m.serial_rx.empty());
    m.out(0x3fc,3);assert(m.in(0x3fd)&1);assert(m.in(0x3f8)=='M');
    assert(m.in(0x3f8)==0x40&&m.in(0x3f8)==0&&m.in(0x3f8)==0);
    p86_mouse(handle.get(),0,0,0);assert(m.serial_rx.empty());
    // Polling is valid with interrupts disabled; only the control lines gate
    // mouse traffic. Actual button changes still produce a complete packet.
    p86_mouse(handle.get(),7,-3,1);
    assert(m.serial_rx.size()==3&&m.in(0x3fa)==1&&!(m.pic_request&0x10));
    assert(m.in(0x3f8)==0x6c&&m.in(0x3f8)==7&&m.in(0x3f8)==61);
    p86_mouse(handle.get(),0,0,1);assert(m.serial_rx.empty());
    p86_mouse(handle.get(),0,0,0);assert(m.serial_rx.size()==3);
    while(!m.serial_rx.empty())m.in(0x3f8);
    m.out(0x3fc,0x13);p86_mouse(handle.get(),8,4,0);assert(m.serial_rx.empty());
    m.out(0x3fc,3);assert(m.serial_rx.size()==4&&m.in(0x3f8)=='M');
    assert(m.in(0x3f8)==0x40&&m.in(0x3f8)==0&&m.in(0x3f8)==0);
    m.out(0x3fc,3);assert(m.serial_rx.empty()); // No repeated ID without reset.
    // Faster CPU execution must not accelerate the PIT or audio clock. Include
    // fractional instruction costs and the run_cycles instruction safety bound.
    uint64_t baseline_instructions=0;
    for(unsigned speed:{1u,4u,8u,16u}){
        p86_set_cpu_speed(handle.get(),speed);idle(m);assert(m.cpu_speed==speed);
        const uint8_t busy[]={0x43,0xeb,0xfd};
        std::copy(std::begin(busy),std::end(busy),m.memory.begin()+0x10100);
        p86_enable_audio(handle.get(),1);p86_run_cycles(handle.get(),4772728);
        assert(m.status!=P86_FAULT&&m.cycles>=4772728&&m.cycles<4772744);
        assert(m.word(0x40,0x6c)==18&&m.audio.size()==48000);
        if(speed==1)baseline_instructions=m.instructions;
        else assert(m.instructions>baseline_instructions*speed*99/100&&m.instructions<baseline_instructions*speed*101/100);
    }
    const auto before_speed_change=m.cycles;
    p86_set_cpu_speed(handle.get(),0);assert(m.cpu_speed==1&&m.cycles==before_speed_change);
    p86_set_cpu_speed(handle.get(),100);assert(m.cpu_speed==16);
    p86_set_cpu_speed(handle.get(),1);p86_enable_audio(handle.get(),0);
    p86_set_cpu_speed(handle.get(),8);idle(m);m.cpu.r[DX]=0x3fd;
    std::fill_n(m.memory.begin()+0x10100,8,0xec); // IN AL,DX: fixed bus cost.
    for(unsigned n=0;n<8;++n)m.step();assert(m.cycles==64);
    idle(m);std::fill_n(m.memory.begin()+0x10100,8,0x90);
    for(unsigned n=0;n<8;++n)m.step();assert(m.cycles==4);
    // Guest-style AdLib timer detection uses a bounded port polling loop.
    // Accelerating I/O with the CPU made it expire before the 80 us timer.
    for(unsigned speed:{1u,4u,8u,16u}){
        p86_set_cpu_speed(handle.get(),speed);idle(m);m.cpu.s[DS]=0x1000;
        const uint8_t probe[]={0xba,0x88,3,0xb0,2,0xee,0x42,0xb0,0xff,0xee,0x4a,
            0xb0,4,0xee,0x42,0xb0,0x21,0xee,0x4a,0xb9,100,0,0xec,0xe2,0xfd,
            0xec,0xa2,0,2,0xfa,0xf4};
        std::copy(std::begin(probe),std::end(probe),m.memory.begin()+0x10100);
        p86_run(handle.get(),1000);assert(m.memory[0x10200]==0xc0&&m.status==P86_HALTED);
    }
    p86_set_cpu_speed(handle.get(),1);
    // A real guest IRQ handler must see each scan code once. Reasserting IRQ1
    // while it is already in service previously produced a second phantom key.
    idle(m);
    const uint8_t keyboard[]={0x50,0x1e,0xb8,0x00,0x10,0x8e,0xd8,0xe4,0x60,
        0xfe,0x06,0x00,0x02,0xb0,0x20,0xe6,0x20,0x1f,0x58,0xcf};
    std::copy(std::begin(keyboard),std::end(keyboard),m.memory.begin()+0x10300);
    m.word(0,9*4,0x300);m.word(0,9*4+2,0x1000);
    p86_key(handle.get(),'Z',0x2c,1);p86_run_cycles(handle.get(),10000);
    assert(m.memory[0x10200]==1&&m.scan_codes.empty());
    assert(m.word(0x40,0x1a)==m.word(0x40,0x1c)); // Guest ISR owns input.
    p86_key(handle.get(),0,0x2c,0);p86_key(handle.get(),'A',0x1e,1);
    p86_run_cycles(handle.get(),10000);assert(m.memory[0x10200]==3);

    idle(m);p86_key(handle.get(),'X',0x2d,1);p86_run_cycles(handle.get(),10000);
    assert(m.word(0x40,0x1e)==0x2d58); // Original BIOS handler fills its ring.
    p86_key(handle.get(),0,0x1d,1);p86_run_cycles(handle.get(),10000);assert(m.memory[0x417]&4);
    p86_key(handle.get(),0,0x1d,0);p86_run_cycles(handle.get(),10000);assert(!(m.memory[0x417]&4));

    m.reset();m.video(0x13);
    for(unsigned n=0;n<4;++n)m.write8(0xa0000+n,uint8_t(n+1));
    for(unsigned n=0;n<4;++n)assert(m.planes[n][0]==n+1);
    m.out(0x3c4,4);m.out(0x3c5,6); // Unchained VGA.
    m.out(0x3c4,2);m.out(0x3c5,5);m.write8(0xa0001,0x77);
    assert(m.planes[0][1]==0x77&&m.planes[2][1]==0x77&&m.planes[1][1]==0);
    m.read8(0xa0000);m.out(0x3ce,5);m.out(0x3cf,1); // Copy all four read latches.
    m.out(0x3c4,2);m.out(0x3c5,15);m.write8(0xa0002,0);
    for(unsigned n=0;n<4;++n)assert(m.planes[n][2]==n+1);
    m.crtc[0x0d]=2;uint32_t w=0,h=0;std::vector<uint32_t> frame(64000);
    assert(p86_copy_pixels(handle.get(),frame.data(),frame.size(),&w,&h)==64000&&w==320&&h==200);
    assert(frame[0]==0xffaa0000); // Palette index 1 is blue; RGBA byte order.
    bool horizontal=false,vertical=false,active=false;
    for(unsigned c=0;c<68182;c+=4){m.cycles=c;auto status=m.in(0x3da);horizontal|=(status&9)==1;vertical|=status&8;active|=status==0;}
    assert(horizontal&&vertical&&active);

    idle(m);opl(m,2,255);opl(m,4,1);m.cycles=400;assert((m.opl_status()&0xc0)==0xc0);
    opl(m,4,0x80);assert(m.opl_status()==0);
    idle(m);p86_enable_audio(handle.get(),1);
    opl(m,0x20,1);opl(m,0x23,1);opl(m,0x40,0);opl(m,0x43,0);
    opl(m,0x60,0xf0);opl(m,0x63,0xf0);opl(m,0x80,0x77);opl(m,0x83,0x77);
    opl(m,0xa0,0x98);opl(m,0xb0,0x31);p86_run_cycles(handle.get(),47727);
    bool audible=false;for(float sample:m.audio){assert(std::isfinite(sample)&&std::abs(sample)<=1);audible|=std::abs(sample)>0.001;}
    assert(audible);

    idle(m);m.out(0x226,1);m.out(0x226,0);assert(m.in(0x22a)==0xaa);
    m.out(0x22c,0xe1);assert(m.in(0x22a)==2&&m.in(0x22a)==1);
    m.memory[0x20000]=0;m.memory[0x20001]=64;m.memory[0x20002]=192;m.memory[0x20003]=255;
    m.out(0x0c,0);m.out(2,0);m.out(2,0);m.out(3,3);m.out(3,0);m.out(0x83,2);
    m.out(0x0b,0x49);m.out(0x0a,1);m.out(0x22c,0x14);m.out(0x22c,3);m.out(0x22c,0);
    m.cycles=2000;m.audio_tick();assert(m.dsp_sample==255&&!m.dsp_playing&&(m.pic_request&0x20));
    assert(m.dma[1].masked&&m.dma[1].address==4&&(m.in(8)&2));
    m.in(0x22e);assert(!(m.pic_request&0x20));

    // DMA advances by device time even when the CPU is faster and host audio
    // is muted. At 8 kHz, 10,000 device cycles transfer exactly 16 samples.
    p86_enable_audio(handle.get(),0);
    for(unsigned speed:{1u,8u,16u}){
        p86_set_cpu_speed(handle.get(),speed);idle(m);m.cpu.flags=2;
        const uint8_t busy[]={0x43,0xeb,0xfd};
        std::copy(std::begin(busy),std::end(busy),m.memory.begin()+0x10100);
        m.out(0x0c,0);m.out(2,0);m.out(2,0);m.out(3,99);m.out(3,0);m.out(0x83,2);
        m.out(0x0b,0x49);m.out(0x0a,1);
        m.out(0x22c,0x40);m.out(0x22c,131); // 1,000,000 / 125 = 8,000 Hz.
        m.out(0x22c,0x14);m.out(0x22c,99);m.out(0x22c,0);
        p86_run_cycles(handle.get(),10000);
        assert(m.dma[1].address==16&&m.dsp_remaining==84&&m.audio.empty());
    }
    p86_set_cpu_speed(handle.get(),1);

    p86_set_cpu286(handle.get(),1);idle(m);
    const uint8_t cpu286[]={0xbc,0x00,0x80,0x54,0x58,0xb9,0x20,0,0xd3,0xe0,0x6a,0,0x9d,0x9c,0x5b};
    std::copy(std::begin(cpu286),std::end(cpu286),m.memory.begin()+0x10100);
    for(unsigned n=0;n<9;++n)m.step();assert(m.cpu.r[AX]==0x8000&&m.cpu.r[BX]==2);
    assert(m.status!=P86_FAULT);
    std::cout<<"Device regressions passed: serial mouse power/identification, IRQ delivery, BIOS keyboard, VGA planes/latches/retrace, OPL timer/tone, DSP reset/DMA/IRQ, 286 flags/stack/shifts.\n";
}
