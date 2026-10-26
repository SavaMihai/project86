#include "project86.h"
#include <array>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

static std::string screen(P86Machine *m){std::array<uint8_t,4000> cells{};p86_copy_text(m,cells.data(),cells.size());std::string out;
    for(unsigned row=0;row<25;++row){std::string line;for(unsigned col=0;col<80;++col){auto c=cells[(row*80+col)*2];line+=c>=32&&c<127?char(c):' ';}
        auto end=line.find_last_not_of(' ');if(end!=std::string::npos)line.resize(end+1);else line.clear();out+=line+'\n';}return out;}
int main(int argc,char **argv){
    std::string disk,hard_disk,input,until,screenshot;uint64_t limit=10000000;bool writable=false,trace=false,demo=false,progress=false,cpu286=true;
    for(int i=1;i<argc;++i){std::string arg=argv[i];
        if(arg=="--8086")cpu286=false;else if(arg=="--disk"&&i+1<argc)disk=argv[++i];else if(arg=="--hard-disk"&&i+1<argc)hard_disk=argv[++i];else if(arg=="--write")writable=true;
        else if(arg=="--demo")demo=true;else if(arg=="--trace")trace=true;else if(arg=="--progress")progress=true;
        else if(arg=="--limit"&&i+1<argc)limit=std::stoull(argv[++i]);
        else if(arg=="--until"&&i+1<argc)until=argv[++i];
        else if(arg=="--screenshot"&&i+1<argc)screenshot=argv[++i];
        else if(arg=="--command"&&i+1<argc){input+=argv[++i];input+='\r';}
        else if(arg=="--script"&&i+1<argc){std::ifstream f(argv[++i]);if(!f){std::cerr<<"Cannot read script\n";return 2;}std::string line;while(std::getline(f,line)){if(!line.empty()&&line.back()=='\r')line.pop_back();input+=line+'\r';}}
        else{std::cerr<<"Usage: p86 [--demo | --disk IMAGE] [--write] [--command TEXT | --script FILE] [--limit N] [--trace]\n";return 2;}}
    std::unique_ptr<P86Machine,decltype(&p86_destroy)> m(p86_create(),p86_destroy);if(!m)return 2;
    p86_set_cpu286(m.get(),cpu286);
    if(!hard_disk.empty()&&!p86_attach_hard_disk(m.get(),hard_disk.c_str(),writable)){P86Snapshot s{};p86_get_snapshot(m.get(),&s);std::cerr<<s.message<<'\n';return 2;}
    if(demo||disk.empty())p86_load_demo(m.get());else if(!p86_attach_floppy(m.get(),disk.c_str(),writable)||!p86_boot(m.get())){P86Snapshot s{};p86_get_snapshot(m.get(),&s);std::cerr<<s.message<<'\n';return 2;}
    size_t at=0;uint64_t spent=0;unsigned idle=0;P86Status status=P86_RUNNING;P86Snapshot snapshot{};
    std::string previous;
    auto checkpoint=std::chrono::steady_clock::now();
    while(spent<limit){uint64_t batch=trace?1:std::min<uint64_t>(10000,limit-spent);
        if(trace){p86_get_snapshot(m.get(),&snapshot);std::fprintf(stderr,"%04X:%04X AX=%04X BX=%04X CX=%04X DX=%04X DS=%04X ES=%04X SI=%04X DI=%04X SS:SP=%04X:%04X F=%04X ",snapshot.cpu.cs,snapshot.cpu.ip,snapshot.cpu.ax,snapshot.cpu.bx,snapshot.cpu.cx,snapshot.cpu.dx,snapshot.cpu.ds,snapshot.cpu.es,snapshot.cpu.si,snapshot.cpu.di,snapshot.cpu.ss,snapshot.cpu.sp,snapshot.cpu.flags);
            for(unsigned j=0;j<8;++j)std::fprintf(stderr,"%02X ",p86_read_memory(m.get(),(snapshot.cpu.cs<<4)+uint16_t(snapshot.cpu.ip+j)));std::fprintf(stderr,"\n");}
        p86_get_snapshot(m.get(),&snapshot);auto before=snapshot.instructions;
        status=p86_run(m.get(),batch);p86_get_snapshot(m.get(),&snapshot);spent+=std::max<uint64_t>(1,snapshot.instructions-before);
        if(progress&&std::chrono::steady_clock::now()-checkpoint>std::chrono::seconds(5)){
            std::cerr<<"Executed "<<snapshot.instructions<<" instructions at "<<std::hex<<snapshot.cpu.cs<<':'<<snapshot.cpu.ip<<std::dec<<'\n';
            if(!p86_flush_disks(m.get())){std::cerr<<"Checkpoint failed\n";return 3;}checkpoint=std::chrono::steady_clock::now();}
        if(status==P86_FAULT)break;
        if(status==P86_WAITING_KEY){if(at<input.size()){auto c=uint8_t(input[at++]);p86_key(m.get(),c,c==13?0x1c:0,1);idle=0;}else {
            auto current=screen(m.get());auto last=current.find_last_not_of(" \r\n");
            bool prompt=last!=std::string::npos&&current[last]=='>';
            bool blocking=snapshot.cpu.cs==0xf000&&snapshot.cpu.ip==0x10b0;
            bool eligible=until.empty()?(prompt||blocking):(current.find(until)!=std::string::npos);
            if(current!=previous||!eligible){previous=current;idle=0;}else if(++idle>64)break;}}
        else if(status==P86_HALTED){p86_get_snapshot(m.get(),&snapshot);if(!(snapshot.cpu.flags&0x200))break;}
        else idle=0;
    }
    std::cout<<screen(m.get());p86_get_snapshot(m.get(),&snapshot);
    std::cerr<<p86_version()<<"\nStatus="<<snapshot.status<<" instructions="<<snapshot.instructions<<" CS:IP="<<std::hex<<snapshot.cpu.cs<<':'<<snapshot.cpu.ip<<std::dec<<'\n';
    if(snapshot.message[0])std::cerr<<snapshot.message<<'\n';
    if(!screenshot.empty()){
        uint32_t width=0,height=0;auto count=p86_copy_pixels(m.get(),nullptr,0,&width,&height);
        if(count){std::vector<uint32_t> pixels(count);p86_copy_pixels(m.get(),pixels.data(),count,&width,&height);
            std::ofstream image(screenshot,std::ios::binary);image<<"P6\n"<<width<<' '<<height<<"\n255\n";
            for(auto pixel:pixels){char rgb[]={char(pixel&255),char((pixel>>8)&255),char((pixel>>16)&255)};image.write(rgb,3);}
            if(!image){std::cerr<<"Could not write screenshot\n";return 3;}}
        else std::cerr<<"No graphics framebuffer active\n";
    }
    if(!p86_flush_disks(m.get())){p86_get_snapshot(m.get(),&snapshot);std::cerr<<snapshot.message<<'\n';return 3;}
    return status==P86_FAULT?1:spent>=limit?4:0;
}
