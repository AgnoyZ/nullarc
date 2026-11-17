// SPDX-License-Identifier: MIT
// CPU-only IOKit boundary for the actual probe + real Mesa core/CS/transport.
#include <assert.h>
#include <stdlib.h>
#include <string>
#include <sys/utsname.h>
#include <unistd.h>
struct CpuHold {};
static int cpu_pause() { throw CpuHold{}; }
static int cpu_sleep(useconds_t delay) { assert(delay == 250000); return 0; }
static int cpu_uname(struct utsname *);
#define pause cpu_pause
#define usleep cpu_sleep
#define uname cpu_uname
#define main actual_probe_main
#include "../tools/upstream34_layout/radv_ib_tail_probe.cpp"
#undef main
#undef uname
#undef usleep
#undef pause

static std::string fault;
static bool tailMode;
static unsigned iter, allocated, mapped, gpuMapped, submitted, waited, freed, unmapped;
static unsigned payloadHandle, tailHandle;
static uint64_t gpuVA[3], seq;
static size_t sizes[3];
alignas(4096) static uint8_t backing[3][16384];
static bool is(const char *s) { return fault == s; }
static int cpu_uname(struct utsname *host) {
    strcpy(host->sysname, "Darwin"); strcpy(host->machine, is("host-arm") ? "arm64" : "x86_64");
    strcpy(host->release, is("host-old") ? "24.0" : "25.1"); return 0;
}
mach_port_t mach_task_self() { return 1; }
CFMutableDictionaryRef IOServiceMatching(const char *s) { assert(!strcmp(s,"PhxBringup")); return reinterpret_cast<void *>(1); }
kern_return_t IOServiceGetMatchingServices(mach_port_t, CFMutableDictionaryRef, io_iterator_t *out) { *out=10; return 0; }
io_object_t IOIteratorNext(io_iterator_t i) { assert(i==10); return iter++<(is("ambiguous")?2u:1u)?11:0; }
kern_return_t IORegistryEntryGetParentEntry(io_registry_entry_t i,const char *,io_registry_entry_t *out) { assert(i==11);*out=21;return 0; }
bool IOObjectConformsTo(io_object_t i,const char *) { assert(i==21);return !is("non-pci"); }
struct FakeCF { uint8_t data[4]; };
static FakeCF property;
CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t,CFStringRef key,CFAllocatorRef,uint32_t) {
    uint32_t value=!strcmp(key,"vendor-id")?0x1002:is("wrong-pci")?0x1901:0x1900;
    for(unsigned i=0;i<4;++i)property.data[i]=value>>(i*8); return &property;
}
CFTypeID CFGetTypeID(CFTypeRef) { return 1; }
CFTypeID CFDataGetTypeID() { return 1; }
CFTypeID CFNumberGetTypeID() { return 2; }
CFIndex CFDataGetLength(CFDataRef) { return 4; }
const UInt8 *CFDataGetBytePtr(CFDataRef p) { return p->data; }
bool CFNumberGetValue(CFNumberRef,int,void *) { assert(false);return false; }
void CFRelease(CFTypeRef) {}
kern_return_t IOObjectRelease(io_object_t) { return 0; }
kern_return_t IOServiceOpen(io_service_t i,mach_port_t task,uint32_t type,io_connect_t *out) {
    assert(i==11&&task==1&&type==N48N_UC_TYPE);*out=99;return 0;
}
kern_return_t IOServiceClose(io_connect_t c) { assert(c==99);return 0; }
kern_return_t IOConnectMapMemory64(io_connect_t c,uint32_t h,mach_port_t,mach_vm_address_t *out,mach_vm_size_t *n,unsigned) {
    assert(c==99&&h>0&&h<=allocated);++mapped; *out=reinterpret_cast<uintptr_t>(backing[h]);
    *n=is("map-short")?sizes[h]-1:sizes[h];return 0;
}
kern_return_t IOConnectUnmapMemory64(io_connect_t c,uint32_t h,mach_port_t,mach_vm_address_t a) {
    assert(c==99&&a==reinterpret_cast<uintptr_t>(backing[h]));++unmapped;return 0;
}
kern_return_t IOConnectCallMethod(io_connect_t c,uint32_t sel,const uint64_t *sin,uint32_t nsin,
    const void *stin,size_t stinsz,uint64_t *sout,uint32_t *nsout,void *stout,size_t *stoutsz) {
    assert(c==99);
    switch(sel) {
    case ACD_SEL_HELLO:
        assert(nsin==2&&sin[0]==1&&*nsout==4);
        sout[0]=1ull|(uint64_t)(is("minor")?11:12)<<16;
        sout[1]=is("build41")?41:is("build42")?42:34;sout[2]=64;sout[3]=8;return 0;
    case ACD_SEL_QUERY_INFO: {
        assert(*stoutsz==sizeof(n48n_info));n48n_info info{};
        info.abi_version=1;info.kext_build=34;info.flags=N48N_INFO_NATIVE_BOOT|N48N_INFO_S1B_POSITIVE;
        if(is("hung"))info.flags|=N48N_INFO_HUNG;
        info.vmid=8;info.gc_version=(11u<<16)|1;info.max_ibs=64;info.reserved[2]=12;
        info.va_low_first=0x10000;info.va_low_last=0x7fffffffffff;info.va_high_first=0xffff800000000000ull;
        info.va_high_last=UINT64_MAX;memcpy(stout,&info,sizeof(info));return 0;
    }
    case PHX_SEL_TOPOLOGY: return ACD_KR_UNSUPPORTED;
    case ACD_SEL_READ_REGS:
        assert(nsin==3&&sin[0]==ACD_GB_ADDR_CONFIG_REG&&sin[1]==1&&*stoutsz==4);
        *static_cast<uint32_t *>(stout)=0x00000242;return 0;
    case ACD_SEL_CTX: {
        const n48n_ctx *ctx=static_cast<const n48n_ctx *>(stin);assert(stinsz==sizeof(*ctx));
        n48n_ctx result{};
        if(ctx->op==N48N_CTX_OP_ALLOC)result.op=is("ctx-zero")?0:1;
        else assert(ctx->op==N48N_CTX_OP_FREE&&ctx->ctx_id==1&&submitted==2);
        if(is("ctx-flags"))result.flags=1;
        memcpy(stout,&result,sizeof(result));return 0;
    }
    case ACD_SEL_BO_CREATE: {
        const n48n_gem_create_in *create=static_cast<const n48n_gem_create_in *>(stin);
        assert(stinsz==sizeof(*create)&&create->domains==N48N_GEM_DOMAIN_GTT&&allocated<2);
        ++allocated;sizes[allocated]=create->bo_size;
        if(create->bo_size==4096){assert(tailMode&&!tailHandle);tailHandle=allocated;}
        else{assert(create->bo_size==16384&&!payloadHandle);payloadHandle=allocated;}
        memset(backing[allocated],0,sizeof(backing[allocated]));
        sout[0]=allocated;sout[1]=is("create-size")?32768:create->bo_size;sout[2]=N48N_GEM_DOMAIN_GTT;
        sout[3]=N48N_PLACED_ZEROED|N48N_PLACED_CPU_MAPPABLE;return 0;
    }
    case ACD_SEL_GEM_VA: {
        const n48n_gem_va *map=static_cast<const n48n_gem_va *>(stin);
        assert(stinsz==sizeof(*map)&&map->handle>0&&map->handle<=allocated&&map->map_size==sizes[map->handle]);
        if(map->operation==N48N_VA_OP_MAP){++gpuMapped;gpuVA[map->handle]=map->va_address;}
        else{assert(map->operation==N48N_VA_OP_UNMAP&&map->handle==payloadHandle&&submitted==2);gpuVA[map->handle]=0;}
        return 0;
    }
    case ACD_SEL_SUBMIT: {
        ++submitted;assert(submitted<=2);const n48n_cs_in *h=static_cast<const n48n_cs_in *>(stin);
        assert(h->abi==1&&h->ctx_id==1&&h->num_ibs==(tailMode?2u:1u)&&!h->flags);
        assert(stinsz==sizeof(*h)+h->num_ibs*sizeof(n48n_cs_ib));
        n48n_cs_ib ib[2]{};memcpy(ib,static_cast<const uint8_t *>(stin)+sizeof(*h),h->num_ibs*sizeof(*ib));
        const uint64_t va=gpuVA[payloadHandle];assert(ib[0].va_start==va+0x1000&&ib[0].ib_bytes==320&&ib[0].ip_type==AMDGPU_HW_IP_COMPUTE);
        if(tailMode){assert(ib[1].va_start==gpuVA[tailHandle]&&ib[1].ib_bytes==32&&ib[1].ip_type==AMDGPU_HW_IP_COMPUTE);
            const uint32_t nop[8]={0xc0061000u,0,0,0,0,0,0,0};assert(!memcmp(backing[tailHandle],nop,sizeof(nop)));}
        unsigned pass=submitted-1;
        const uint32_t pattern[4]={0x7800c0deu^pass,0x13579bdfu+pass,0x2468ace0u^(pass<<16),0xc001d00du-pass};
        uint32_t packets[80]{};assert(phxGfx11DispatchCommands(packets,80,va,va+0x2010,pattern)==PHX_SHADER_DISPATCH_DWORDS);
        packets[78]=packets[79]=0xffff1000u;assert(!memcmp(backing[payloadHandle]+0x1000,packets,sizeof(packets)));
        if((is("submit-first")&&submitted==1)||(is("submit-second")&&submitted==2))return ACD_KR_ABORTED;
        // CPU oracle writes expected bytes; this is NOT an ISA/coherency model.
        for(unsigned i=0;i<256;++i){uint32_t value=is("stale")&&pass?(i%4==0?0x7800c0deu:pattern[i&3]):pattern[i&3];
            memcpy(backing[payloadHandle]+0x2010+i*4,&value,4);}
        if(pass&&fault.rfind("corrupt-",0)==0){size_t offset=strtoul(fault.c_str()+8,nullptr,0);assert(offset<16384);backing[payloadHandle][offset]^=1;}
        sout[0]=++seq;return 0;
    }
    case ACD_SEL_WAIT_SEQ:
        ++waited;assert(nsin==3&&sin[0]==seq&&nsout&&*nsout==3);
        if(is("wait-error"))return ACD_KR_TIMEOUT;
        sout[0]=is("wait-busy")?1:sin[1]==0;
        sout[1]=is("wait-retired")?0:seq;sout[2]=seq;return 0;
    case ACD_SEL_BO_FREE:
        assert(nsin==1&&sin[0]==payloadHandle&&submitted==2);++freed;return 0;
    default: assert(false);return ACD_KR_UNSUPPORTED;
    }
}
int main(int argc,char **argv) {
    assert(argc==3);fault=argv[1];tailMode=!strcmp(argv[2],"tail");
    unsetenv("RADV_DARWIN_BUILD34_IB_TAIL");
    char name[]="cpu-probe",mode[32];strcpy(mode,is("check")?"--check":is("args")?"--wrong":tailMode?"--run-tail":"--run-single");
    char *args[]={name,mode,nullptr};int rc=-1;bool held=false;
    try{rc=actual_probe_main(2,args);}catch(const CpuHold &){held=true;}
    const bool admission=is("host-arm")||is("host-old")||is("wrong-pci")||is("non-pci")||is("ambiguous")||
        is("build41")||is("build42")||is("minor")||is("hung");
    if(is("ok")){assert(!held&&rc==0&&submitted==2&&allocated==(tailMode?2u:1u)&&freed==1&&closes==1);}
    else if(is("check")){assert(!held&&rc==0&&!submitted&&!allocated&&closes==1);}
    else if(is("args")){assert(!held&&rc==64&&!opens&&!submitted&&!allocated);}
    else if(admission){assert(!submitted&&!allocated);assert(held||rc==4);}
    else{assert(held&&!freed&&!closes);if(is("stale")||fault.rfind("corrupt-",0)==0)assert(submitted==2);}
    printf("CPU-PROBE-PASS %s %s submitted=%u held=%u\n",argv[2],fault.c_str(),submitted,held?1u:0u);
    return 0;
}
