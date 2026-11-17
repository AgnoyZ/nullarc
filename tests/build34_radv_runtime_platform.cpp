/* SPDX-License-Identifier: MIT */
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include "navi48_native_abi.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct FakeBO { void *data; uint64_t size; unsigned maps; };
static FakeBO bos[N48N_MAX_BOS];
static unsigned opened, closed, next_handle=1, context_count, submissions;
static uint64_t sequence, retired_sequence;
static uint8_t *arena;
static bool fault(const char *name) { const char *f=getenv("NULLARC_CPU_CASE"); return f && !strcmp(f,name); }
static void require(bool okay) { if (!okay) { fputs("FAIL: CPU-only runtime platform model\n",stderr); exit(79); } }
extern "C" io_service_t phx34_cpu_match(void) { require(!opened); return fault("missing-pci") ? 0 : 0x3456; }
extern "C" kern_return_t phx34_cpu_open(io_service_t service,task_port_t task,uint32_t type,io_connect_t *out)
{
    require(service==0x3456 && task==mach_task_self() && type==N48N_UC_TYPE && !opened && out);
    ++opened; *out=0x789a; return KERN_SUCCESS;
}
extern "C" kern_return_t phx34_cpu_close(io_connect_t client)
{
    require(client==0x789a && opened==1 && !closed && !context_count && submissions==2);
    for (unsigned h=1;h<next_handle;++h) { require(!bos[h].maps); free(bos[h].data); bos[h]={}; }
    ++closed; return KERN_SUCCESS;
}
static kern_return_t cpu_release(io_object_t object) { require(object==0x3456); return KERN_SUCCESS; }
extern "C" kern_return_t phx34_cpu_map(io_connect_t client,uint32_t h,task_port_t task,
    mach_vm_address_t *address,mach_vm_size_t *size,IOOptionBits options)
{
    require(client==0x789a && opened==1 && !closed && task==mach_task_self() && h && h<next_handle &&
            bos[h].data && !bos[h].maps && options==kIOMapAnywhere && address && size);
    ++bos[h].maps; *address=(uintptr_t)bos[h].data; *size=bos[h].size; return KERN_SUCCESS;
}
extern "C" kern_return_t phx34_cpu_unmap(io_connect_t client,uint32_t h,task_port_t task,mach_vm_address_t address)
{
    require(client==0x789a && task==mach_task_self() && h && h<next_handle && bos[h].maps==1 &&
            address==(uintptr_t)bos[h].data); --bos[h].maps; return KERN_SUCCESS;
}
extern "C" void phx34_cpu_arena(void *address,size_t bytes)
{
    require(!arena && address && bytes==16384 && !submissions); arena=(uint8_t *)address;
}
extern "C" kern_return_t phx34_cpu_call(mach_port_t client,uint32_t sel,const uint64_t *input,uint32_t input_count,
    const void *structure,size_t structure_size,uint64_t *output,uint32_t *output_count,void *result,size_t *result_size)
{
    require(client==0x789a && opened==1 && !closed);
    switch(sel) {
    case N48N_SEL_HELLO:
        require(input_count==2 && input[0]==1 && input[1]==N48N_HELLO_F_MINOR && *output_count==4);
        output[0]=1 | ((fault("minor") ? 11ull : 12ull)<<16); output[1]=fault("build41")?41:fault("build42")?42:34;
        output[2]=64; output[3]=8; return KERN_SUCCESS;
    case N48N_SEL_QUERYINFO: {
        require(result && result_size && *result_size==sizeof(n48n_info)); n48n_info info={};
        info.abi_version=1; info.kext_build=34; info.flags=N48N_INFO_NATIVE_BOOT | N48N_INFO_S1B_POSITIVE;
        if(fault("hung"))info.flags|=N48N_INFO_HUNG;
        info.vmid=8; info.gb_addr_config=0x242; info.gc_version=(11u<<16)|1; info.ring_size_dw=4096; info.max_ibs=64;
        info.vram_vis_total=info.vram_vis_free=256ull<<20; info.vram_hi_total=info.vram_hi_free=768ull<<20;
        info.gtt_cap=512ull<<20; info.gtt_max_bo=64ull<<20; info.pt_cap=16ull<<20;
        info.va_low_first=0x10000; info.va_low_last=0x7fffffffffff; info.va_high_first=0xffff800000000000ull; info.va_high_last=UINT64_MAX;
        info.max_bos=N48N_MAX_BOS; info.fence_slots=N48N_FENCE_SLOTS; info.reserved[2]=12;
        info.seq_emitted=sequence; info.seq_retired=retired_sequence; memcpy(result,&info,sizeof(info)); return KERN_SUCCESS;
    }
    case 30: return kIOReturnUnsupported;
    case N48N_SEL_READREGS:
        require(input_count==3 && input[1]<=16 && result_size && *result_size==input[1]*4);
        memset(result,0,*result_size); return KERN_SUCCESS;
    case N48N_SEL_BOCREATE: {
        require(structure_size==sizeof(n48n_gem_create_in) && *output_count==4 && next_handle<N48N_MAX_BOS);
        const n48n_gem_create_in *in=(const n48n_gem_create_in *)structure;
        require(in->bo_size && in->bo_size<=(64ull<<20));
        if(fault("bo-error"))return kIOReturnNoMemory;
        unsigned h=next_handle++; uint64_t size=(in->bo_size+4095)&~4095ull;
        require(!posix_memalign(&bos[h].data,4096,size)); memset(bos[h].data,0,size); bos[h].size=size;
        output[0]=h; output[1]=fault("bo-size")?size+4096:size;
        output[2]=in->domains & N48N_GEM_DOMAIN_VRAM ? N48N_GEM_DOMAIN_VRAM:N48N_GEM_DOMAIN_GTT;
        output[3]=N48N_PLACED_ZEROED | N48N_PLACED_CPU_MAPPABLE; return KERN_SUCCESS;
    }
    case N48N_SEL_BOFREE: {
        require(input_count==1 && input[0] && input[0]<next_handle);
        FakeBO &b=bos[input[0]]; require(b.data && !b.maps); free(b.data); b={}; return KERN_SUCCESS;
    }
    case N48N_SEL_GEMVA: require(structure_size==sizeof(n48n_gem_va)); return KERN_SUCCESS;
    case N48N_SEL_CTX: {
        require(structure_size==sizeof(n48n_ctx) && *result_size==sizeof(n48n_ctx));
        const n48n_ctx *in=(const n48n_ctx *)structure; n48n_ctx out={};
        if(in->op==N48N_CTX_OP_ALLOC){require(!context_count);out.op=++context_count;}
        else if(in->op==N48N_CTX_OP_FREE){require(context_count==1 && in->ctx_id==1);--context_count;}
        else require(in->op==N48N_CTX_OP_QUERY_STATE2);
        memcpy(result,&out,sizeof(out)); return KERN_SUCCESS;
    }
    case N48N_SEL_SUBMIT: {
        require(arena && submissions<2 && *output_count==1 && structure_size>=sizeof(n48n_cs_in));
        unsigned pass=submissions++;
        if((!pass && fault("submit-first")) || (pass && fault("submit-second")))return kIOReturnAborted;
        const uint32_t pattern[4]={0x7800c0deu^pass,0x13579bdfu+pass,0x2468ace0u^(pass<<16),0xc001d00du-pass};
        for(unsigned i=0;i<256;++i){uint32_t value=pattern[i&3];if(pass && fault("stale") && !(i&3))value=0x7800c0deu;
            memcpy(arena+0x2010+4*i,&value,4);}
        if(pass && fault("guard-byte"))arena[0x100]^=1;
        const n48n_cs_in *h=(const n48n_cs_in *)structure;
        ++sequence; retired_sequence=sequence;
        if(h->flags & N48N_CS_HAS_FENCE){require(h->fence_handle && h->fence_handle<next_handle && h->fence_offset+8<=bos[h->fence_handle].size);
            memcpy((uint8_t *)bos[h->fence_handle].data+h->fence_offset,&sequence,8);}
        output[0]=fault("zero-sequence")?0:sequence; return KERN_SUCCESS;
    }
    case N48N_SEL_WAITSEQ:
        require(input_count==3 && *output_count==3 && input[0] && input[0]<=sequence);
        if(fault("wait-error"))return kIOReturnTimeout;
        output[0]=0; output[1]=fault("bad-retirement")?0:retired_sequence; output[2]=sequence; return KERN_SUCCESS;
    default: fprintf(stderr,"FAIL: unmodeled CPU platform selector %u\n",sel); exit(79);
    }
}
__attribute__((used)) static const struct { const void *replace,*original; }
release_pair __attribute__((section("__DATA,__interpose"))) =
{(const void *)(uintptr_t)&cpu_release,(const void *)(uintptr_t)&IOObjectRelease};
