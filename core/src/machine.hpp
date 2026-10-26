#pragma once
#include "project86.h"
#include <array>
#include <cstdint>
#include <deque>
#include <string>
#include <vector>

namespace p86 {
enum Register { AX, CX, DX, BX, SP, BP, SI, DI };
enum Segment { ES, CS, SS, DS };
enum Flag : uint16_t { CF=1, PF=4, AF=16, ZF=64, SF=128, TF=256, IF=512, DF=1024, OF=2048 };
struct CPU {
    std::array<uint16_t,8> r{};
    std::array<uint16_t,4> s{};
    uint16_t ip=0, flags=0xf002;
    bool halted=false;
    unsigned interrupt_shadow=0;
};
struct Disk {
    std::vector<uint8_t> bytes;
    std::string path;
    bool writable=false, dirty=false;
    uint16_t cylinders=80, heads=2, sectors=18;
};
struct Operand { bool reg=false; uint8_t index=0; uint16_t segment=0, offset=0; };
struct DMAChannel {
    uint16_t address=0,base_address=0,count=0xffff,base_count=0xffff;
    uint8_t page=0,mode=0;
    bool masked=true;
};
struct FMOperator { double phase=0, envelope=0, previous=0;uint8_t stage=0;bool key=false; };
struct Machine {
    CPU cpu;
    std::array<uint8_t,1<<20> memory{};
    Disk floppy, hard_disk;
    P86Status status=P86_RUNNING;
    std::string fault;
    uint64_t instructions=0, cycles=0, next_tick=262144;
    uint32_t cpu_speed=1;
    uint64_t cpu_cycle_remainder=0;
    bool blocking_key=false;
    uint8_t video_mode=3, cursor_row=0, cursor_col=0, active_page=0;
    std::deque<uint16_t> keys;
    std::deque<uint8_t> scan_codes, serial_rx;
    std::deque<uint8_t> scan_ascii;
    uint8_t pic_mask=0, pic_request=0, pic_service=0, pic_base=8;
    uint8_t pic_init=0, pic_read=0, port61=0, cmos_index=0;
    uint8_t pit_control=0x36, pit_phase=0, pit_latch_phase=0;
    std::array<uint16_t,3> pit_reload{0,0,0};
    uint8_t uart_lcr=0, uart_ier=0, uart_mcr=0, mouse_buttons=0;
    uint16_t uart_divisor=96;
    uint8_t uart_scratch=0;
    uint8_t dac_index=0, dac_component=0, dac_read_index=0, dac_read_component=0;
    uint8_t sequencer_index=0, graphics_index=0, crtc_index=0, attr_index=0;
    bool attr_data=false;
    std::array<uint8_t,256> sequencer{}, graphics{}, crtc{}, attribute{};
    std::array<std::array<uint8_t,3>,256> palette{};
    std::array<std::array<uint8_t,65536>,4> planes{};
    std::array<uint8_t,4> latches{};
    std::deque<float> audio;
    double speaker_phase=0, audio_fraction=0;
    std::array<DMAChannel,4> dma{};
    bool dma_high=false;
    uint8_t dma_status=0;
    std::array<uint8_t,256> opl{};
    std::array<FMOperator,18> fm{};
    uint8_t opl_address=0;
    uint64_t opl_timer_start=0;
    uint8_t dsp_command=0,dsp_needed=0,dsp_reset=0,dsp_test=0,dsp_sample=128;
    std::vector<uint8_t> dsp_arguments;
    std::deque<uint8_t> dsp_response;
    uint32_t dsp_rate=11025,dsp_block=65536,dsp_remaining=0;
    bool dsp_playing=false,dsp_auto=false,dsp_speaker=false;
    double dsp_fraction=0;
    bool audio_enabled=false;
    uint64_t audio_last_cycle=0;
    uint16_t instruction_cs=0, instruction_ip=0;
    uint64_t unknown_port_count=0;
    uint16_t last_unknown_port=0;
    bool strict_io=false;
    bool raw_cpu_mode=false;
    bool cpu286=false;
    uint16_t normalized_flags(uint16_t f) const { return (f&0x0fd5)|(cpu286?2:0xf002); }
    void divide_error();
    void reset();
    void advance_cpu_cycles(uint64_t amount) {
        if(cpu_speed==1){cycles+=amount;return;}
        amount+=cpu_cycle_remainder;cycles+=amount/cpu_speed;cpu_cycle_remainder=amount%cpu_speed;
    }
    uint32_t address(uint16_t seg,uint16_t off) const {return ((uint32_t(seg)<<4)+off)&0xfffff;}
    uint8_t read8(uint32_t address);
    void write8(uint32_t address,uint8_t value);
    uint8_t byte(uint16_t seg,uint16_t off) {return read8(address(seg,off));}
    uint16_t word(uint16_t seg,uint16_t off) {return byte(seg,off)|(uint16_t(byte(seg,uint16_t(off+1)))<<8);}
    void byte(uint16_t seg,uint16_t off,uint8_t value) {write8(address(seg,off),value);}
    void word(uint16_t seg,uint16_t off,uint16_t value) {byte(seg,off,uint8_t(value));byte(seg,uint16_t(off+1),uint8_t(value>>8));}
    uint8_t fetch8() {auto v=byte(cpu.s[CS],cpu.ip);++cpu.ip;return v;}
    uint16_t fetch16() {auto lo=fetch8();return uint16_t(lo)|(uint16_t(fetch8())<<8);}
    uint8_t reg8(unsigned n) const {return uint8_t(cpu.r[n&3]>>((n&4)?8:0));}
    void reg8(unsigned n,uint8_t v) {auto &r=cpu.r[n&3];r=(n&4)?uint16_t((r&0xff)|(uint16_t(v)<<8)):uint16_t((r&0xff00)|v);}
    void push(uint16_t v) {cpu.r[SP]-=2;word(cpu.s[SS],cpu.r[SP],v);}
    uint16_t pop() {auto v=word(cpu.s[SS],cpu.r[SP]);cpu.r[SP]+=2;return v;}
    void flag(uint16_t mask,bool v) {cpu.flags=v?(cpu.flags|mask):(cpu.flags&~mask);}
    void szp(uint32_t value,bool wide);
    uint16_t alu(unsigned operation,uint16_t lhs,uint16_t rhs,bool wide);
    uint16_t shift(unsigned operation,uint16_t value,unsigned count,bool wide);
    Operand decode(uint8_t modrm,int segment_override);
    uint16_t get(const Operand &o,bool wide);
    void put(const Operand &o,bool wide,uint16_t value);
    bool condition(unsigned condition) const;
    void interrupt(uint8_t number);
    void fail(const std::string &message);
    void step();
    bool bios();
    void tick();
    void bios_key(uint8_t ascii, uint8_t scan);
    void audio_tick();
    float audio_sample();
    double fm_operator(unsigned slot,double frequency,double modulation,bool key);
    void dsp_write(uint8_t value);
    uint8_t opl_status() const;
    void video(uint8_t mode);
    void teletype(uint8_t c,uint8_t color=7);
    void scroll(unsigned top,unsigned left,unsigned bottom,unsigned right,int lines,uint8_t attr);
    void bios_flags(uint16_t mask,bool value);
    uint8_t in(uint16_t port);
    void out(uint16_t port,uint8_t value);
    bool attach(const char *path,bool writable,bool hard=false);
    bool flush();
    bool flush(Disk &disk);
    bool boot();
    void demo();
};
}
struct P86Machine { p86::Machine impl; };
