#include "machine.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <filesystem>
#include <system_error>
#include <fcntl.h>
#include <unistd.h>

namespace p86 {
void Machine::reset() {
    cpu=CPU{};cpu.flags=normalized_flags(cpu.flags);memory.fill(0);fault.clear();status=P86_RUNNING;raw_cpu_mode=false;
    instructions=cycles=cpu_cycle_remainder=0;next_tick=262144;keys.clear();scan_codes.clear();scan_ascii.clear();serial_rx.clear();audio.clear();blocking_key=false;
    pic_mask=pic_request=pic_service=pic_init=pic_read=0;pic_base=8;port61=0;
    pit_reload={0,0,0};pit_control=0x36;pit_phase=pit_latch_phase=0;
    uart_lcr=uart_ier=uart_mcr=0;uart_divisor=96;mouse_buttons=0;audio_fraction=speaker_phase=0;
    dma={};dma_high=false;dma_status=0;opl.fill(0);fm={};opl_address=0;opl_timer_start=0;
    dsp_command=dsp_needed=dsp_reset=dsp_test=0;dsp_sample=128;dsp_arguments.clear();dsp_response.clear();
    dsp_rate=11025;dsp_block=65536;dsp_remaining=0;dsp_playing=dsp_auto=dsp_speaker=false;dsp_fraction=0;audio_last_cycle=0;
    unknown_port_count=0;last_unknown_port=0;
    // Original Project86 ROM: service trampolines end in a real guest IRET.
    for(unsigned i=0;i<256;++i){word(0,uint16_t(i*4),uint16_t(0x1000+i*8));word(0,uint16_t(i*4+2),0xf000);memory[0xf1000+i*8]=memory[0xf1001+i*8]=0xcf;}
    memory[0xffff0]=0xf4;memory[0xffffe]=0xfc;
    const char date[]="10/25/26";std::copy(date,date+8,memory.begin()+0xffff5);
    word(0x40,0,0x3f8);word(0x40,0x10,0x0221);word(0x40,0x13,640);
    word(0x40,0x1a,0x1e);word(0x40,0x1c,0x1e);word(0x40,0x80,0x1e);word(0x40,0x82,0x3e);
    // Fixed guest clock makes boot and regression runs reproducible.
    word(0x40,0x6c,0);word(0x40,0x6e,0);memory[0x475]=hard_disk.bytes.empty()?0:1;
    // Floppy parameter table consumed by the original DOS boot sector.
    const uint8_t disk_table[]={0xdf,2,0x25,2,18,0x1b,0xff,0x6c,0xf6,15,8};
    std::copy(std::begin(disk_table),std::end(disk_table),memory.begin()+0xf2000);
    word(0,0x1e*4,0x2000);word(0,0x1e*4+2,0xf000);
    const uint8_t config[]={8,0,0xfc,0,1,0x20,0,0,0,0};
    std::copy(std::begin(config),std::end(config),memory.begin()+0xf2100);
    if(!hard_disk.bytes.empty()) {
        word(0,0x41*4,0x2200);word(0,0x41*4+2,0xf000);
        auto table=memory.data()+0xf2200;
        table[0]=uint8_t(hard_disk.cylinders);table[1]=uint8_t(hard_disk.cylinders>>8);
        table[2]=uint8_t(hard_disk.heads);table[5]=table[6]=0xff;
        table[12]=uint8_t(hard_disk.cylinders);table[13]=uint8_t(hard_disk.cylinders>>8);table[14]=uint8_t(hard_disk.sectors);
    }
    video(3);cpu.s[CS]=0xf000;cpu.ip=0xfff0;
}
uint8_t Machine::read8(uint32_t a) {
    a&=0xfffff;
    if(!raw_cpu_mode&&a>=0xa0000&&a<0xb0000&&video_mode>7){
        unsigned off=a-0xa0000;bool chained=sequencer[4]&8;if(chained)off>>=2;
        for(unsigned p=0;p<4;++p)latches[p]=planes[p][off];
        if(chained)return latches[a&3];
        if(graphics[5]&8){uint8_t result=0xff;for(unsigned p=0;p<4;++p)if(graphics[7]&(1<<p))result&=(graphics[2]&(1<<p))?latches[p]:uint8_t(~latches[p]);return result;}
        return latches[graphics[4]&3];
    }
    return memory[a];
}
void Machine::write8(uint32_t a,uint8_t v) {
    a&=0xfffff;
    if(!raw_cpu_mode&&a>=0xa0000&&a<0xb0000&&video_mode>7){
        unsigned off=a-0xa0000,rotate=graphics[3]&7;bool chained=sequencer[4]&8;if(chained)off>>=2;
        uint8_t rotated=uint8_t((v>>rotate)|(v<<(8-rotate)));
        for(unsigned p=0;p<4;++p){if(!(sequencer[2]&(1<<p))||(chained&&p!=(a&3)))continue;
            uint8_t src=rotated,mask=graphics[8];unsigned mode=graphics[5]&3;
            if(mode==1){planes[p][off]=latches[p];continue;}
            if(mode==2)src=(v&(1<<p))?0xff:0;
            else if(mode==3){src=(graphics[0]&(1<<p))?0xff:0;mask&=rotated;}
            else if(graphics[1]&(1<<p))src=(graphics[0]&(1<<p))?0xff:0;
            switch((graphics[3]>>3)&3){case 1:src&=latches[p];break;case 2:src|=latches[p];break;case 3:src^=latches[p];break;}
            planes[p][off]=(src&mask)|(latches[p]&~mask);
        }return;
    }
    // ROM is immutable to guest writes. Initialization writes the backing array directly.
    if(raw_cpu_mode||a<0xf0000)memory[a]=v;
}
void Machine::video(uint8_t mode) {
    bool preserve=mode&0x80;mode&=0x7f;video_mode=mode;active_page=cursor_row=cursor_col=0;
    memory[0x449]=mode;word(0x40,0x4a,(mode==0||mode==1)?40:80);word(0x40,0x4c,0x1000);
    word(0x40,0x4e,0);word(0x40,0x63,mode==7?0x3b4:0x3d4);memory[0x484]=24;word(0x40,0x85,16);
    sequencer.fill(0);graphics.fill(0);crtc.fill(0);attribute.fill(0);
    sequencer[2]=15;sequencer[4]=(mode==0x13)?8:6;graphics[8]=255;crtc[0x13]=40;
    if(!preserve){for(auto &p:planes)p.fill(0);std::fill(memory.begin()+0xa0000,memory.begin()+0xc0000,0);
        for(unsigned i=0;i<80*25;++i){memory[0xb8000+i*2]=' ';memory[0xb8000+i*2+1]=7;}}
    for(unsigned i=0;i<256;++i){palette[i]={uint8_t(((i>>2)&1)*42+((i>>5)&1)*21),uint8_t(((i>>1)&1)*42+((i>>4)&1)*21),uint8_t((i&1)*42+((i>>3)&1)*21)};}
    const uint8_t colors[16][3]={{0,0,0},{0,0,42},{0,42,0},{0,42,42},{42,0,0},{42,0,42},{42,21,0},{42,42,42},{21,21,21},{21,21,63},{21,63,21},{21,63,63},{63,21,21},{63,21,63},{63,63,21},{63,63,63}};
    for(unsigned i=0;i<16;++i){palette[i]={colors[i][0],colors[i][1],colors[i][2]};attribute[i]=uint8_t(i);}
    for(unsigned p=0;p<8;++p)word(0x40,uint16_t(0x50+p*2),0);
}
void Machine::scroll(unsigned top,unsigned left,unsigned bottom,unsigned right,int lines,uint8_t attr) {
    unsigned cols=word(0x40,0x4a);if(!cols||cols>80)cols=80;
    top=std::min(top,24u);bottom=std::min(bottom,24u);left=std::min(left,cols-1);right=std::min(right,cols-1);
    if(top>bottom||left>right)return;
    unsigned base=(video_mode==7?0xb0000:0xb8000)+active_page*0x1000;
    int height=int(bottom-top+1);if(!lines||std::abs(lines)>height)lines=height;
    for(int n=0;n<height;++n){int row=lines>0?int(top)+n:int(bottom)-n,source=row+lines;
        for(unsigned col=left;col<=right;++col){unsigned dst=base+unsigned(row)*cols*2+col*2;
            if(source>=int(top)&&source<=int(bottom)){unsigned src=base+unsigned(source)*cols*2+col*2;memory[dst]=memory[src];memory[dst+1]=memory[src+1];}
            else{memory[dst]=' ';memory[dst+1]=attr;}}
    }
}
void Machine::teletype(uint8_t c,uint8_t color) {
    unsigned cols=word(0x40,0x4a);if(!cols||cols>80)cols=80;
    auto pos=word(0x40,uint16_t(0x50+active_page*2));cursor_row=pos>>8;cursor_col=pos&255;
    switch(c){
    case 7:break;case 8:if(cursor_col)--cursor_col;break;
    case 13:cursor_col=0;break;case 10:++cursor_row;break;
    default:{unsigned a=(video_mode==7?0xb0000:0xb8000)+active_page*0x1000+(cursor_row*cols+cursor_col)*2;
        if(a+1<memory.size()){memory[a]=c;if(video_mode>7)memory[a+1]=color;}
        if(++cursor_col>=cols){cursor_col=0;++cursor_row;}break;}}
    if(cursor_row>=25){scroll(0,0,24,cols-1,1,7);cursor_row=24;}
    word(0x40,uint16_t(0x50+active_page*2),uint16_t((cursor_row<<8)|cursor_col));
}
void Machine::bios_flags(uint16_t mask,bool value) {
    auto f=word(cpu.s[SS],uint16_t(cpu.r[SP]+4));f=value?f|mask:f&~mask;
    word(cpu.s[SS],uint16_t(cpu.r[SP]+4),f);flag(mask,value);
}
bool Machine::bios() {
    if(cpu.s[CS]!=0xf000||cpu.ip<0x1000||cpu.ip>=0x1800||(cpu.ip&7))return true;
    auto n=(cpu.ip-0x1000)/8;auto ah=reg8(4),al=reg8(0);
    switch(n){
    case 0x08:{uint32_t ticks=word(0x40,0x6c)|(uint32_t(word(0x40,0x6e))<<16);++ticks;
        if(ticks>=0x1800b0){ticks=0;memory[0x470]=1;}word(0x40,0x6c,uint16_t(ticks));word(0x40,0x6e,uint16_t(ticks>>16));pic_service&=~1;
        // INT 1Ch is a real guest hook, including the DOS-installed handler.
        if(word(0,0x1c*4)!=0x1000+0x1c*8||word(0,0x1c*4+2)!=0xf000){cpu.ip++;interrupt(0x1c);}break;}
    case 0x09:if(!scan_codes.empty()){bios_key(scan_ascii.empty()?0:scan_ascii.front(),scan_codes.front());scan_codes.pop_front();if(!scan_ascii.empty())scan_ascii.pop_front();}pic_service&=~2;break;
    case 0x0b:case 0x0c:pic_service&=~uint8_t(1<<(n-8));break;
    case 0x10:
        switch(ah){
        case 0:if(al==0||al==1||al==2||al==3||al==7||al==0x0d||al==0x0e||al==0x10||al==0x12||al==0x13)video(al);else fail("Unsupported BIOS video mode");break;
        case 1:word(0x40,0x60,cpu.r[CX]);break;
        case 2:word(0x40,uint16_t(0x50+(reg8(7)&7)*2),cpu.r[DX]);break;
        case 3:cpu.r[DX]=word(0x40,uint16_t(0x50+(reg8(7)&7)*2));cpu.r[CX]=word(0x40,0x60);break;
        case 5:active_page=al&7;memory[0x462]=active_page;word(0x40,0x4e,active_page*0x1000);break;
        case 6:case 7:scroll(reg8(5),reg8(1),reg8(6),reg8(2),ah==6?al:-int(al),reg8(7));break;
        case 8:{auto pos=word(0x40,uint16_t(0x50+(reg8(7)&7)*2));auto a=0xb8000+(reg8(7)&7)*0x1000+((pos>>8)*80+(pos&255))*2;cpu.r[AX]=memory[a]|(uint16_t(memory[a+1])<<8);break;}
        case 9:case 10:{auto pos=word(0x40,uint16_t(0x50+(reg8(7)&7)*2));auto start=(pos>>8)*80+(pos&255);
            for(unsigned i=0;i<cpu.r[CX]&&start+i<2000;++i){auto a=0xb8000+(reg8(7)&7)*0x1000+(start+i)*2;memory[a]=al;if(ah==9)memory[a+1]=reg8(3);}break;}
        case 0x0b:break;
        case 0x0e:teletype(al,reg8(3));break;
        case 0x0f:reg8(0,video_mode);reg8(4,uint8_t(word(0x40,0x4a)));reg8(7,active_page);break;
        case 0x10:
            if(al==0){attribute[reg8(3)&31]=reg8(7);}
            else if(al==0x10){palette[cpu.r[BX]&255]={uint8_t(reg8(6)&63),uint8_t(reg8(5)&63),uint8_t(reg8(1)&63)};}
            else if(al==0x12){for(unsigned i=0;i<cpu.r[CX]&&i<256;++i)for(unsigned c=0;c<3;++c)palette[(cpu.r[BX]+i)&255][c]=byte(cpu.s[ES],uint16_t(cpu.r[DX]+i*3+c))&63;}
            else if(al==3){}else {fail("Unsupported VGA palette BIOS function");}break;
        case 0x11:if(al==0x30){cpu.s[ES]=0xf000;cpu.r[BP]=0x3000;cpu.r[CX]=16;reg8(2,24);}break;
        case 0x12:if(reg8(3)==0x10){cpu.r[BX]=3;cpu.r[CX]=0;}break;
        // IBM Convertible-only display table probe. Our VGA has no such
        // table; preserve the caller's null ES rather than claiming a device.
        case 0x15:break;
        // No TopView/DESQview virtual screen manager is installed. The input
        // physical video-buffer pointer remains the buffer applications use.
        case 0xfe:break;
        case 0x1a:reg8(0,0x1a);cpu.r[BX]=8;break;
        default:fail("Unsupported BIOS video service");break;
        }break;
    case 0x11:cpu.r[AX]=word(0x40,0x10);break;
    case 0x12:cpu.r[AX]=word(0x40,0x13);break;
    case 0x13:{
        bool hard=reg8(2)==0x80;auto &disk=hard?hard_disk:floppy;
        auto error=[&](uint8_t code){reg8(4,code);memory[hard?0x474:0x441]=code;bios_flags(CF,code!=0);};
        if((reg8(2)!=0&&!hard)||disk.bytes.empty()){error(0x80);break;}
        if(ah==0){error(0);break;}if(ah==1){error(memory[hard?0x474:0x441]);break;}
        if(ah==2||ah==3||ah==4){unsigned cylinder=reg8(5)|((reg8(1)&0xc0)<<2),sector=reg8(1)&63,head=reg8(6),count=al;
            uint64_t lba=(uint64_t(cylinder)*disk.heads+head)*disk.sectors+(sector?sector-1:0);
            if(!sector||sector>disk.sectors||head>=disk.heads||!count||(lba+count)*512>disk.bytes.size()){error(4);break;}
            if(unsigned(cpu.r[BX])+count*512>65536){error(9);break;}
            if(ah==3&&!disk.writable){error(3);break;}
            for(unsigned i=0;i<count*512;++i){auto a=address(cpu.s[ES],uint16_t(cpu.r[BX]+i));
                if(ah==2)write8(a,disk.bytes[lba*512+i]);else if(ah==3)disk.bytes[lba*512+i]=read8(a);}
            if(ah==3)disk.dirty=true;error(0);reg8(0,uint8_t(count));break;}
        if(ah==8){unsigned c=disk.cylinders-1;reg8(5,uint8_t(c));reg8(1,uint8_t(disk.sectors|((c>>2)&0xc0)));reg8(6,uint8_t(disk.heads-1));reg8(2,1);
            if(!hard){reg8(3,4);cpu.s[ES]=0xf000;cpu.r[DI]=0x2000;}error(0);break;}
        if(ah==0x15){error(0);reg8(4,hard?3:1);if(hard){cpu.r[CX]=uint16_t((disk.bytes.size()/512)>>16);cpu.r[DX]=uint16_t(disk.bytes.size()/512);}break;}
        if(ah==0x16){error(0);break;}
        if(ah==0x18){cpu.s[ES]=0xf000;cpu.r[DI]=0x2000;error(0);break;}
        error(1);break;
    }
    case 0x14:if(ah==0)cpu.r[AX]=0x6000;else if(ah==3)cpu.r[AX]=0x6000;else {reg8(4,0x80);}break;
    case 0x15:
        if(ah==0xc0){cpu.s[ES]=0xf000;cpu.r[BX]=0x2100;reg8(4,0);bios_flags(CF,false);}
        else if(ah==0x88){cpu.r[AX]=0;bios_flags(CF,false);}
        else{reg8(4,0x86);bios_flags(CF,true);}break;
    case 0x16:{
        blocking_key=false;
        auto head=word(0x40,0x1a),tail=word(0x40,0x1c);
        if(ah==0||ah==0x10){
            if(head==tail){blocking_key=true;flag(IF,true);status=P86_WAITING_KEY;return false;}
            cpu.r[AX]=word(0x40,head);head+=2;if(head>=0x3e)head=0x1e;word(0x40,0x1a,head);
        }else if(ah==1||ah==0x11){bios_flags(ZF,head==tail);if(head!=tail)cpu.r[AX]=word(0x40,head);else status=P86_WAITING_KEY;}
        else if(ah==2){reg8(0,memory[0x417]);}
        else if(ah==5){auto next=uint16_t(tail+2);if(next>=0x3e)next=0x1e;if(next==head)reg8(0,1);else{word(0x40,tail,cpu.r[CX]);word(0x40,0x1c,next);reg8(0,0);}}
        else if(ah==0x12)cpu.r[AX]=memory[0x417]|(uint16_t(memory[0x418])<<8);
        // KEYB's documented enhanced-keyboard probe: an invalid 92h request
        // returns AH minus 12h when services 10h..12h are supported.
        else if(ah==0x92)reg8(4,0x80);
        else if(ah!=3)fail("Unsupported BIOS keyboard service");break;
    }
    case 0x17:reg8(4,0x90);break;
    case 0x18:fail("No bootable operating system");break;
    case 0x19:boot();return false;
    case 0x1a:
        switch(ah){
        case 0:cpu.r[CX]=word(0x40,0x6e);cpu.r[DX]=word(0x40,0x6c);reg8(0,memory[0x470]);memory[0x470]=0;break;
        case 1:word(0x40,0x6e,cpu.r[CX]);word(0x40,0x6c,cpu.r[DX]);break;
        case 2:cpu.r[CX]=0x1200;cpu.r[DX]=0;bios_flags(CF,false);break;
        case 4:cpu.r[CX]=0x2026;cpu.r[DX]=0x1025;bios_flags(CF,false);break;
        case 3:case 5:bios_flags(CF,false);break;
        default:bios_flags(CF,true);break;
        }break;
    case 0x1b:case 0x1c:break;
    case 0x05:case 0x1d:break;
    default:{char msg[90];std::snprintf(msg,sizeof(msg),"Uninstalled interrupt %02Xh, AX=%04X",n,cpu.r[AX]);fail(msg);break;}
    }
    return status!=P86_FAULT;
}
void Machine::bios_key(uint8_t ascii,uint8_t scan) {
    unsigned modifier=0;
    switch(scan&0x7f){case 0x2a:modifier=2;break;case 0x36:modifier=1;break;case 0x1d:modifier=4;break;case 0x38:modifier=8;break;}
    if(modifier){if(scan&128)memory[0x417]&=~modifier;else memory[0x417]|=modifier;return;}
    if(scan&128)return;
    auto head=word(0x40,0x1a),tail=word(0x40,0x1c),next=uint16_t(tail+2);if(next>=0x3e)next=0x1e;
    if(next!=head){word(0x40,tail,uint16_t(ascii)|(uint16_t(scan)<<8));word(0x40,0x1c,next);}
}
void Machine::tick() {
    audio_tick();
    if(!scan_codes.empty()&&!(pic_service&2))pic_request|=2;
    if(!serial_rx.empty()&&(uart_ier&1)&&(uart_mcr&8)&&!(pic_service&0x10))pic_request|=0x10;
    if(cycles>=next_tick){pic_request|=1;next_tick=cycles+uint64_t(pit_reload[0]?pit_reload[0]:65536)*4;}
    if((cpu.flags&IF)&&!cpu.interrupt_shadow){
        uint8_t pending=pic_request&~pic_mask;
        for(unsigned n=0;n<8;++n){if(pic_service&(1<<n))break;if(pending&(1<<n)){pic_request&=~(1<<n);pic_service|=1<<n;interrupt(pic_base+n);status=P86_RUNNING;break;}}
    }
}
uint8_t Machine::in(uint16_t p) {
    if(p<=7){auto &channel=dma[p/2];auto value=(p&1)?channel.count:channel.address;uint8_t result=uint8_t(value>>(dma_high?8:0));dma_high=!dma_high;return result;}
    switch(p){
    case 8:{auto v=dma_status;dma_status=0;return v;}
    case 0x20:return pic_read==0x0b?pic_service:pic_request;case 0x21:return pic_mask;
    case 0x40:case 0x41:case 0x42:{unsigned channel=p-0x40;uint16_t count=uint16_t((pit_reload[channel]?pit_reload[channel]:65536)-((cycles/4)&0xffff));auto v=uint8_t(count>>(pit_latch_phase?8:0));pit_latch_phase^=1;return v;}
    case 0x60:if(scan_codes.empty())return 0;else {auto v=scan_codes.front();scan_codes.pop_front();if(!scan_ascii.empty())scan_ascii.pop_front();return v;}
    case 0x61:return port61|uint8_t((cycles>>5)&0x20);case 0x62:return 0;case 0x64:return scan_codes.empty()?0x14:0x15;
    case 0x70:return cmos_index;
    case 0x71:switch(cmos_index&127){case 0xa:return 0x26;case 0xb:return 2;case 0xd:return 0x80;case 0x10:return 0x40;case 0x14:return 0x21;case 0x15:return 0x80;case 0x16:return 2;default:return 0;}
    case 0x201:return 0xff;case 0x3ba:case 0x3da:attr_data=false;return uint8_t((cycles%68182>=62000?8:0)|((cycles%152>=120||cycles%68182>=61000)?1:0));
    case 0x388:case 0x228:case 0x220:return opl_status();
    case 0x22a:if(dsp_response.empty())return 0xff;else{auto v=dsp_response.front();dsp_response.pop_front();return v;}
    case 0x22c:return 0;
    case 0x22e:pic_request&=~0x20;return dsp_response.empty()?0:0x80;
    case 0x3c1:return attribute[attr_index&31];case 0x3c4:return sequencer_index;case 0x3c5:return sequencer[sequencer_index];
    case 0x3c7:return 0;case 0x3c8:return dac_index;
    case 0x3c9:{auto v=palette[dac_read_index][dac_read_component++];if(dac_read_component==3){dac_read_component=0;++dac_read_index;}return v;}
    case 0x3cc:return 0x63;case 0x3ce:return graphics_index;case 0x3cf:return graphics[graphics_index];
    case 0x3b4:case 0x3d4:return crtc_index;case 0x3b5:case 0x3d5:return crtc[crtc_index];
    case 0x3f8:if(uart_lcr&128)return uint8_t(uart_divisor);else if(serial_rx.empty())return 0;else{auto v=serial_rx.front();serial_rx.pop_front();return v;}
    case 0x3f9:return (uart_lcr&128)?uint8_t(uart_divisor>>8):uart_ier;
    case 0x3fa:return (!serial_rx.empty()&&(uart_ier&1))?4:1;
    case 0x3fb:return uart_lcr;case 0x3fc:return uart_mcr;case 0x3fd:return 0x60|(!serial_rx.empty()?1:0);
    case 0x3fe:return (uart_mcr&16)?uint8_t(((uart_mcr&2)<<3)|((uart_mcr&1)<<5)|((uart_mcr&4)<<4)|((uart_mcr&8)<<4)):0xb0;
    case 0x3ff:return uart_scratch;
    case 0x3f4:return 0x80;case 0x3f5:return 0;
    case 0xa1:return 0xff;case 0x80:return 0;
    default:++unknown_port_count;last_unknown_port=p;if(strict_io)fail("Unsupported I/O port read");return 0xff;
    }
}
void Machine::out(uint16_t p,uint8_t v) {
    if(p<=7){auto &channel=dma[p/2];auto &target=(p&1)?channel.count:channel.address;target=dma_high?uint16_t((target&255)|(uint16_t(v)<<8)):uint16_t((target&0xff00)|v);
        if(p&1)channel.base_count=target;else channel.base_address=target;dma_high=!dma_high;return;}
    switch(p){
    case 0x0a:dma[v&3].masked=v&4;break;
    case 0x0b:dma[v&3].mode=v;break;
    case 0x0c:dma_high=false;break;
    case 0x0d:dma={};dma_high=false;dma_status=0;break;
    case 0x0e:for(auto &channel:dma)channel.masked=false;break;
    case 0x0f:for(unsigned i=0;i<4;++i)dma[i].masked=v&(1<<i);break;
    case 0x87:dma[0].page=v;break;case 0x83:dma[1].page=v;break;case 0x81:dma[2].page=v;break;case 0x82:dma[3].page=v;break;
    case 0x20:if(v&0x10){pic_init=1;pic_mask=0;pic_service=0;}
        else if(v&0x20){if(v&0x40)pic_service&=~(1<<(v&7));else for(unsigned i=0;i<8;++i)if(pic_service&(1<<i)){pic_service&=~(1<<i);break;}}
        else pic_read=v;break;
    case 0x21:if(pic_init){if(pic_init==1)pic_base=v&0xf8;if(++pic_init==4)pic_init=0;}else pic_mask=v;break;
    case 0x40:case 0x41:case 0x42:{unsigned channel=p-0x40,access=(pit_control>>4)&3;
        if(access==1)pit_reload[channel]=(pit_reload[channel]&0xff00)|v;
        else if(access==2)pit_reload[channel]=(pit_reload[channel]&255)|(uint16_t(v)<<8);
        else if(!pit_phase){pit_reload[channel]=(pit_reload[channel]&0xff00)|v;pit_phase=1;}
        else{pit_reload[channel]=(pit_reload[channel]&255)|(uint16_t(v)<<8);pit_phase=0;}
        if(channel==0)next_tick=cycles+uint64_t(pit_reload[0]?pit_reload[0]:65536)*4;break;}
    case 0x43:pit_control=v;pit_phase=pit_latch_phase=0;break;
    case 0x60:if(v==0xed||v==0xf4){scan_codes.push_back(0xfa);scan_ascii.push_back(0);}break;
    case 0x61:port61=v;break;case 0x64:break;case 0x70:cmos_index=v;break;case 0x71:break;
    case 0x3c0:if(!attr_data)attr_index=v&31;else attribute[attr_index]=v;attr_data=!attr_data;break;
    case 0x388:case 0x228:case 0x220:opl_address=v;break;
    case 0x389:case 0x229:case 0x221:opl[opl_address]=v;if(opl_address==4)opl_timer_start=cycles;break;
    case 0x226:if(dsp_reset&&v==0){dsp_response.clear();dsp_response.push_back(0xaa);dsp_playing=false;dsp_needed=0;}dsp_reset=v;break;
    case 0x22c:dsp_write(v);break;
    case 0x3c2:case 0x3c6:case 0x3d8:case 0x3d9:break;
    case 0x3c4:sequencer_index=v;break;case 0x3c5:sequencer[sequencer_index]=v;break;
    case 0x3c7:dac_read_index=v;dac_read_component=0;break;case 0x3c8:dac_index=v;dac_component=0;break;
    case 0x3c9:palette[dac_index][dac_component++]=v&63;if(dac_component==3){dac_component=0;++dac_index;}break;
    case 0x3ce:graphics_index=v;break;case 0x3cf:graphics[graphics_index]=v;break;
    case 0x3b4:case 0x3d4:crtc_index=v;break;case 0x3b5:case 0x3d5:crtc[crtc_index]=v;break;
    case 0x3f8:if(uart_lcr&128)uart_divisor=(uart_divisor&0xff00)|v;break;
    case 0x3f9:if(uart_lcr&128)uart_divisor=(uart_divisor&255)|(uint16_t(v)<<8);else uart_ier=v;break;
    case 0x3fa:if(v&2)serial_rx.clear();break;case 0x3fb:uart_lcr=v;break;
    case 0x3fc:
        if((v&0x13)==3&&(uart_mcr&0x13)!=3){
            // Identify, then report the reset state before accepting motion.
            // Keep this sequence contiguous: motion bytes can otherwise be
            // mistaken for optional model-identification characters ('3'/'Z').
            serial_rx.insert(serial_rx.end(),{'M',0x40,0,0});mouse_buttons=0;
        }
        uart_mcr=v;break;
    case 0x3ff:uart_scratch=v;break;
    // Explicitly model inactive DMA/floppy setup registers. BIOS handles block I/O.
    case 0x08:case 0x09:case 0x80:case 0xa0:case 0xa1:case 0x3f2:case 0x3f5:case 0x3f7:break;
    default:++unknown_port_count;last_unknown_port=p;if(strict_io)fail("Unsupported I/O port write");break;
    }
    if(!serial_rx.empty()&&(uart_ier&1)&&(uart_mcr&8)&&!(pic_service&0x10))pic_request|=0x10;
}
bool Machine::attach(const char *path,bool writable,bool hard) {
    if(!path){fault="Missing disk image path";return false;}
    if(!flush())return false;
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    if(!f){fault="Cannot open disk image";return false;}auto size=f.tellg();
    struct Geometry{size_t size;uint16_t cylinders,heads,sectors;};
    const Geometry geometries[]={{163840,40,1,8},{184320,40,1,9},{327680,40,2,8},{368640,40,2,9},{737280,80,2,9},{1228800,80,2,15},{1474560,80,2,18},{2949120,80,2,36}};
    Geometry hd{};const Geometry *g=nullptr;
    if(hard&&size>0&&size<=std::streamoff(64*1024*1024)&&size%(4*32*512)==0){hd={size_t(size),uint16_t(size/(4*32*512)),4,32};g=&hd;}
    if(!hard)for(const auto &item:geometries)if(size==std::streamoff(item.size))g=&item;
    if(!g){fault=hard?"Hard disk must be <=64 MiB, aligned to 64 KiB (4 heads, 32 sectors)":"Unsupported raw floppy size (use 160K–2.88M images)";return false;}
    Disk next;next.bytes.resize(g->size);f.seekg(0);if(!f.read(reinterpret_cast<char*>(next.bytes.data()),std::streamsize(next.bytes.size()))){fault="Cannot read disk image";return false;}
    next.path=path;next.writable=writable;next.cylinders=g->cylinders;next.heads=g->heads;next.sectors=g->sectors;
    if(hard)hard_disk=std::move(next);else floppy=std::move(next);fault.clear();return true;
}
bool Machine::flush() {
    return flush(floppy)&&flush(hard_disk);
}
bool Machine::flush(Disk &disk) {
    if(!disk.dirty)return true;
    if(!disk.writable){fault="Disk is read-only";return false;}
    std::string pattern=disk.path+".p86-XXXXXX";std::vector<char> name(pattern.begin(),pattern.end());name.push_back(0);
    int fd=mkstemp(name.data());if(fd<0){fault="Cannot create disk checkpoint";return false;}
    size_t written=0;bool ok=true;
    while(written<disk.bytes.size()){auto n=::write(fd,disk.bytes.data()+written,disk.bytes.size()-written);if(n<=0){ok=false;break;}written+=size_t(n);}
    if(ok&&fsync(fd)!=0)ok=false;if(close(fd)!=0)ok=false;
    if(ok&&std::rename(name.data(),disk.path.c_str())!=0)ok=false;
    if(!ok){std::remove(name.data());fault="Disk checkpoint failed; in-memory changes retained";return false;}
    disk.dirty=false;return true;
}
bool Machine::boot() {
    if(floppy.bytes.size()<512){fault="Attach a raw DOS boot floppy first";status=P86_FAULT;return false;}
    if(floppy.bytes[510]!=0x55||floppy.bytes[511]!=0xaa){fault="Disk has no boot-sector signature";status=P86_FAULT;return false;}
    if(!flush()){status=P86_FAULT;return false;}reset();
    std::copy_n(floppy.bytes.begin(),512,memory.begin()+0x7c00);cpu.s[CS]=0;cpu.ip=0x7c00;cpu.r[SP]=0x7c00;cpu.r[DX]=0;cpu.flags=normalized_flags(0x202);
    memory[0xf2004]=uint8_t(floppy.sectors);return true;
}
void Machine::demo() {
    reset();cpu.s[CS]=cpu.s[DS]=cpu.s[ES]=cpu.s[SS]=0x1000;cpu.ip=0x100;cpu.r[SP]=0xfffe;cpu.flags=normalized_flags(0x202);
    // Hand-assembled original 8086 program: print greeting, then BIOS keyboard echo.
    const uint8_t program[]={0xbe,0x20,0x01,0xac,0x08,0xc0,0x74,0x09,0xb4,0x0e,0xbb,0x07,0x00,0xcd,0x10,0xeb,0xf2,
        0x31,0xc0,0xcd,0x16,0xb4,0x0e,0xcd,0x10,0xeb,0xf6};
    std::copy(std::begin(program),std::end(program),memory.begin()+0x10100);
    const char *message="Project86 - independent x86 on ARM\r\nOur CPU, BIOS and devices. No JIT.\r\n\r\nKeyboard echo test - type here:\r\n";
    std::copy(message,message+std::strlen(message)+1,memory.begin()+0x10120);
}
}
