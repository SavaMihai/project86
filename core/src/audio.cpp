#include "machine.hpp"
#include <algorithm>
#include <cmath>

namespace p86 {
namespace {constexpr double clock_hz=4772728.0, sample_rate=48000.0, tau=6.2831853071795864769;}

uint8_t Machine::opl_status() const {
    auto control=opl[4];if(control&0x80)return 0;
    double micros=double(cycles-opl_timer_start)*1000000.0/clock_hz;uint8_t result=0;
    if((control&1)&&!(control&0x40)&&micros>=double(256-opl[2])*80)result|=0xc0;
    if((control&2)&&!(control&0x20)&&micros>=double(256-opl[3])*320)result|=0xa0;
    return result;
}

void Machine::dsp_write(uint8_t v) {
    if(dsp_needed){
        dsp_arguments.push_back(v);if(dsp_arguments.size()<dsp_needed)return;
        switch(dsp_command){
        case 0x10:dsp_sample=v;break;
        case 0x14:case 0x91:dsp_block=uint32_t(dsp_arguments[0])+(uint32_t(v)<<8)+1;dsp_remaining=dsp_block;dsp_auto=false;dsp_playing=true;break;
        case 0x40:dsp_rate=1000000u/(256u-v);break;
        case 0x41:case 0x42:dsp_rate=std::max(1u,(unsigned(dsp_arguments[0])<<8)|v);break;
        case 0x48:dsp_block=uint32_t(dsp_arguments[0])+(uint32_t(v)<<8)+1;break;
        case 0xe0:dsp_response.push_back(uint8_t(~v));break;
        case 0xe4:dsp_test=v;break;
        default:break;
        }
        dsp_needed=0;dsp_arguments.clear();return;
    }
    dsp_command=v;dsp_arguments.clear();
    switch(v){
    case 0x10:case 0x40:case 0xe0:case 0xe4:dsp_needed=1;break;
    case 0x14:case 0x41:case 0x42:case 0x48:case 0x91:dsp_needed=2;break;
    case 0x1c:case 0x90:dsp_remaining=dsp_block;dsp_auto=true;dsp_playing=true;break;
    case 0xd0:dsp_playing=false;break;case 0xd4:dsp_playing=dsp_remaining!=0;break;
    case 0xd1:dsp_speaker=true;break;case 0xd3:dsp_speaker=false;break;
    case 0xd8:dsp_response.push_back(dsp_speaker?0xff:0);break;
    case 0xda:dsp_auto=false;break;
    case 0xe1:dsp_response.push_back(2);dsp_response.push_back(1);break;
    case 0xe8:dsp_response.push_back(dsp_test);break;
    case 0xf2:pic_request|=0x20;break;
    default:fail("Unsupported Sound Blaster DSP command");break;
    }
}

double Machine::fm_operator(unsigned slot,double frequency,double modulation,bool key) {
    static constexpr unsigned offsets[18]={0,3,1,4,2,5,8,11,9,12,10,13,16,19,17,20,18,21};
    static constexpr double multipliers[16]={0.5,1,2,3,4,5,6,7,8,9,10,10,12,12,15,15};
    auto offset=offsets[slot];auto &state=fm[slot];auto characteristics=opl[0x20+offset];
    if(key&&!state.key){state.stage=1;state.phase=0;state.envelope=0;}
    if(!key&&state.key)state.stage=4;state.key=key;
    unsigned attack=opl[0x60+offset]>>4,decay=opl[0x60+offset]&15,release=opl[0x80+offset]&15;
    double sustain=std::pow(10.0,-double(opl[0x80+offset]>>4)*3.0/20.0);
    // Functional FM synthesis. Rates are intentionally approximate, not a
    // transistor-level or bit-exact recreation of Yamaha's envelope generator.
    auto rate=[](unsigned value){return value?std::pow(2.0,double(value)-5.0)/sample_rate:0.0;};
    switch(state.stage){
    case 1:state.envelope+=(1.01-state.envelope)*rate(attack)*8;if(state.envelope>=1){state.envelope=1;state.stage=2;}break;
    case 2:state.envelope-=rate(decay);if(state.envelope<=sustain){state.envelope=sustain;state.stage=3;}break;
    case 3:if(!(characteristics&0x20))state.envelope-=rate(release);break;
    case 4:state.envelope-=rate(release);break;
    default:break;
    }
    state.envelope=std::clamp(state.envelope,0.0,1.0);
    state.phase+=frequency*multipliers[characteristics&15]/sample_rate;state.phase-=std::floor(state.phase);
    double phase=state.phase*tau+modulation,wave=std::sin(phase);
    unsigned waveform=(opl[1]&0x20)?opl[0xe0+offset]&3:0;
    if(waveform==1)wave=std::max(0.0,wave);else if(waveform==2)wave=std::abs(wave);
    else if(waveform==3)wave=std::sin(phase)>=0?std::abs(std::sin(phase*2)):0;
    double level=std::pow(10.0,-double(opl[0x40+offset]&63)*0.75/20.0);
    return wave*state.envelope*level;
}

float Machine::audio_sample() {
    double value=0;
    speaker_phase+=1193182.0/(pit_reload[2]?pit_reload[2]:65536)/sample_rate;speaker_phase-=std::floor(speaker_phase);
    if((port61&3)==3)value+=speaker_phase<0.5?0.12:-0.12;
    for(unsigned channel=0;channel<9;++channel){
        auto high=opl[0xb0+channel];bool key=high&0x20;
        if(!key&&fm[channel*2].envelope==0&&fm[channel*2+1].envelope==0)continue;
        double number=opl[0xa0+channel]|((high&3)<<8);
        double frequency=number*49716.0/std::pow(2.0,20.0-double((high>>2)&7));
        unsigned modulator=channel*2,carrier=modulator+1;unsigned feedback=(opl[0xc0+channel]>>1)&7;
        double mod=fm_operator(modulator,frequency,feedback?fm[modulator].previous*std::pow(2.0,double(feedback)-4.0):0,key);
        fm[modulator].previous=mod;
        bool additive=opl[0xc0+channel]&1;
        value+=0.08*(fm_operator(carrier,frequency,additive?0:mod*4,key)+(additive?mod:0));
    }
    if(dsp_speaker)value+=(double(dsp_sample)-128)/128*0.30;
    return float(std::clamp(value,-1.0,1.0));
}

void Machine::audio_tick() {
    uint64_t elapsed=cycles-audio_last_cycle;audio_last_cycle=cycles;
    // DMA and IRQs run even with host sound muted.
    if(dsp_playing){
        dsp_fraction+=double(elapsed)*dsp_rate/clock_hz;
        while(dsp_fraction>=1&&dsp_playing){
            dsp_fraction-=1;auto &channel=dma[1];if(channel.masked)break;
            dsp_sample=memory[((uint32_t(channel.page)<<16)|channel.address)&0xfffff];
            channel.address+=((channel.mode&0x20)?-1:1);
            bool terminal=channel.count--==0;
            if(terminal){dma_status|=2;if(channel.mode&0x10){channel.address=channel.base_address;channel.count=channel.base_count;}else channel.masked=true;}
            if(dsp_remaining&&--dsp_remaining==0){pic_request|=0x20;if(dsp_auto)dsp_remaining=dsp_block;else dsp_playing=false;}
        }
        if(dma[1].masked)dsp_fraction=0;
    }
    if(!audio_enabled)return;
    audio_fraction+=double(elapsed)*sample_rate/clock_hz;
    while(audio_fraction>=1){audio_fraction-=1;if(audio.size()>=48000)audio.pop_front();audio.push_back(audio_sample());}
}
}
