#include "machine.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <new>
#include <limits>

using namespace p86;
extern "C" {
P86Machine *p86_create(void){try{auto *m=new P86Machine;m->impl.reset();return m;}catch(...){return nullptr;}}
void p86_destroy(P86Machine *m){if(m){m->impl.flush();delete m;}}
void p86_set_cpu286(P86Machine *m,int enabled){if(m){m->impl.cpu286=enabled!=0;m->impl.cpu.flags=m->impl.normalized_flags(m->impl.cpu.flags);}}
void p86_set_cpu_speed(P86Machine *m,uint32_t multiplier){if(m){m->impl.cpu_speed=std::clamp(multiplier,1u,16u);m->impl.cpu_cycle_remainder=0;}}
void p86_reset(P86Machine *m){if(m){if(m->impl.flush())m->impl.reset();else m->impl.status=P86_FAULT;}}
void p86_load_demo(P86Machine *m){if(m){if(m->impl.flush())m->impl.demo();else m->impl.status=P86_FAULT;}}
int p86_attach_floppy(P86Machine *m,const char *p,int w){return m&&m->impl.attach(p,w!=0);}
int p86_attach_hard_disk(P86Machine *m,const char *p,int w){return m&&m->impl.attach(p,w!=0,true);}
int p86_flush_disks(P86Machine *m){return m&&m->impl.flush();}
int p86_boot(P86Machine *m){return m&&m->impl.boot();}
P86Status p86_run(P86Machine *handle,uint64_t budget){
    if(!handle)return P86_FAULT;auto &m=handle->impl;
    if(m.status==P86_FAULT)return m.status;
    if(m.status==P86_WAITING_KEY)m.status=P86_RUNNING;
    for(uint64_t i=0;i<budget;++i){
        if(m.cpu.halted){if(!(m.cpu.flags&IF))return P86_HALTED;m.cycles=std::max(m.cycles,m.next_tick);m.tick();if(m.cpu.halted)return P86_HALTED;}
        m.tick();if(!m.bios())break;if(m.status==P86_FAULT)break;
        m.step();if(m.status==P86_FAULT||m.status==P86_WAITING_KEY)break;
    }
    return m.status;
}
P86Status p86_run_cycles(P86Machine *handle,uint64_t budget){
    if(!handle)return P86_FAULT;auto &m=handle->impl;if(m.status==P86_FAULT)return m.status;
    auto end=m.cycles+std::min<uint64_t>(budget,4772728);
    uint64_t iterations=0;
    while(m.cycles<end&&++iterations<=std::min<uint64_t>(budget,4772728)*m.cpu_speed/4+1){
        // Deliver queued IRQs before fast-forwarding an idle CPU to a timer edge.
        m.tick();
        if(m.cpu.halted||(m.status==P86_WAITING_KEY&&m.blocking_key)){
            m.cycles=std::min(end,std::max(m.cycles+1,m.next_tick));m.tick();
            if(m.cycles>=end)return m.status;
            if(m.cpu.halted)continue;
        }
        m.status=P86_RUNNING;m.tick();if(!m.bios()){if(m.status==P86_FAULT)return m.status;continue;}
        m.step();if(m.status==P86_FAULT)return m.status;
    }
    m.audio_tick();return m.status;
}
void p86_enable_audio(P86Machine *handle,int enabled){if(!handle)return;auto &m=handle->impl;m.audio_enabled=enabled!=0;m.audio.clear();m.audio_fraction=0;m.audio_last_cycle=m.cycles;}
void p86_get_cpu(const P86Machine *m,P86CPUState *s){if(!m||!s)return;const auto &c=m->impl.cpu;
    *s={c.r[AX],c.r[CX],c.r[DX],c.r[BX],c.r[SP],c.r[BP],c.r[SI],c.r[DI],c.s[ES],c.s[CS],c.s[SS],c.s[DS],c.ip,c.flags};}
void p86_set_cpu(P86Machine *m,const P86CPUState *s){if(!m||!s)return;auto &c=m->impl.cpu;
    c.r={s->ax,s->cx,s->dx,s->bx,s->sp,s->bp,s->si,s->di};c.s={s->es,s->cs,s->ss,s->ds};c.ip=s->ip;c.flags=s->flags;c.halted=false;c.interrupt_shadow=0;
    m->impl.status=P86_RUNNING;m->impl.fault.clear();m->impl.raw_cpu_mode=true;}
P86Status p86_step_cpu(P86Machine *m){if(!m)return P86_FAULT;m->impl.raw_cpu_mode=true;m->impl.step();return m->impl.status;}
void p86_get_snapshot(const P86Machine *m,P86Snapshot *s){if(!m||!s)return;*s={};p86_get_cpu(m,&s->cpu);
    s->instructions=m->impl.instructions;s->cycles=m->impl.cycles;s->status=m->impl.status;s->video_mode=m->impl.video_mode;
    if(!m->impl.fault.empty())std::snprintf(s->message,sizeof(s->message),"%s",m->impl.fault.c_str());
    else if(m->impl.unknown_port_count)std::snprintf(s->message,sizeof(s->message),"Unimplemented I/O: %llu accesses, last port %04Xh",static_cast<unsigned long long>(m->impl.unknown_port_count),m->impl.last_unknown_port);
}
uint8_t p86_read_memory(const P86Machine *m,uint32_t a){return m?m->impl.memory[a&0xfffff]:0;}
void p86_write_memory(P86Machine *m,uint32_t a,uint8_t v){if(m)m->impl.memory[a&0xfffff]=v;}
void p86_key(P86Machine *handle,uint8_t ascii,uint8_t scan,int pressed){
    if(!handle)return;auto &m=handle->impl;
    if(scan){if(m.scan_codes.size()<64){m.scan_codes.push_back(pressed?scan:uint8_t(scan|128));m.scan_ascii.push_back(pressed?ascii:0);}m.pic_request|=2;}
    else if(pressed)m.bios_key(ascii,0);
    if(m.status==P86_WAITING_KEY)m.status=P86_RUNNING;
}
void p86_mouse(P86Machine *handle,int dx,int dy,uint8_t buttons){
    if(!handle)return;auto &m=handle->impl;
    // DTR/RTS power/reset the serial mouse. Loopback disconnects the external
    // device. Host events during that interval must not precede its ID byte.
    if((m.uart_mcr&0x13)!=3)return;
    if(!dx&&!dy&&buttons==m.mouse_buttons)return;
    if(m.serial_rx.size()>256)return;
    do{int x=std::clamp(dx,-128,127),y=std::clamp(dy,-128,127);dx-=x;dy-=y;
        uint8_t ux=uint8_t(x),uy=uint8_t(y);
        m.serial_rx.push_back(uint8_t(0x40|((buttons&1)?0x20:0)|((buttons&2)?0x10:0)|((uy>>4)&12)|((ux>>6)&3)));
        m.serial_rx.push_back(ux&63);m.serial_rx.push_back(uy&63);
    }while((dx||dy)&&m.serial_rx.size()<256);
    m.mouse_buttons=buttons;if((m.uart_ier&1)&&(m.uart_mcr&8))m.pic_request|=0x10;
}
size_t p86_copy_text(const P86Machine *m,uint8_t *dest,size_t capacity){
    if(!m||!dest||capacity<4000)return 0;unsigned base=(m->impl.video_mode==7?0xb0000:0xb8000)+m->impl.active_page*0x1000;
    std::copy_n(m->impl.memory.begin()+base,4000,dest);return 4000;
}
size_t p86_copy_pixels(const P86Machine *handle,uint32_t *dest,size_t capacity,uint32_t *width,uint32_t *height){
    if(!handle||!width||!height)return 0;const auto &m=handle->impl;
    if(m.video_mode<=7){*width=*height=0;return 0;}
    *width=(m.video_mode==0x13||m.video_mode==0x0d)?320:640;
    *height=m.video_mode==0x12?480:m.video_mode==0x10?350:200;
    size_t count=size_t(*width)*(*height);if(!dest||capacity<count)return count;
    for(unsigned y=0;y<*height;++y)for(unsigned x=0;x<*width;++x){unsigned index;
        if(m.video_mode==0x13){unsigned start=(unsigned(m.crtc[0x0c])<<8)|m.crtc[0x0d];unsigned stride=std::max(1u,unsigned(m.crtc[0x13])*2);
            unsigned off=(start+y*stride+x/4)&65535;index=m.planes[x&3][off];}
        else {unsigned off=(y*(*width/8)+x/8)&65535;index=0;for(unsigned p=0;p<4;++p)index|=((m.planes[p][off]>>(7-(x&7)))&1)<<p;index=m.attribute[index]&63;}
        auto rgb=m.palette[index];auto r=uint32_t(rgb[0])*255/63,g=uint32_t(rgb[1])*255/63,b=uint32_t(rgb[2])*255/63;
        dest[y*(*width)+x]=r|(g<<8)|(b<<16)|0xff000000;
    }
    return count;
}
size_t p86_read_audio(P86Machine *handle,float *dest,size_t capacity){
    if(!handle||!dest)return 0;auto &m=handle->impl;
    auto count=std::min(capacity,m.audio.size());for(size_t i=0;i<count;++i){dest[i]=m.audio.front();m.audio.pop_front();}
    std::fill(dest+count,dest+capacity,0.f);return count;
}
uint8_t p86_read_port(P86Machine *m,uint16_t p){return m?m->impl.in(p):0xff;}
void p86_write_port(P86Machine *m,uint16_t p,uint8_t v){if(m)m->impl.out(p,v);}
const char *p86_version(void){return "Project86 0.1.0-dev (independent interpreter)";}
}
