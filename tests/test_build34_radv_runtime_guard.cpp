/* SPDX-License-Identifier: MIT */
#define PHX34_RUNTIME_GUARD_CPU
#include "../tools/upstream34_layout/radv_ib_tail_runtime_guard.cpp"

static const char *test_case;
static bool is(const char *name) { return !strcmp(test_case,name); }
static void call(uint32_t sel,const uint64_t *in,uint32_t ni,const void *s,size_t n,
                 uint64_t *out,uint32_t *no,void *r,size_t *nr)
{
    require(guard_call(client,sel,in,ni,s,n,out,no,r,nr)==KERN_SUCCESS,"unit fake call");
}
static void handshake(void)
{
    const uint64_t input[2]={1,N48N_HELLO_F_MINOR}; uint64_t out[4]={}; uint32_t no=4;
    call(N48N_SEL_HELLO,input,2,nullptr,0,out,&no,nullptr,nullptr);
    n48n_info info={};size_t n=sizeof(info);call(N48N_SEL_QUERYINFO,nullptr,0,nullptr,0,nullptr,nullptr,&info,&n);
}
static uint32_t create_bo(uint64_t size)
{
    n48n_gem_create_in in={size,4096,N48N_GEM_DOMAIN_GTT,N48N_GEM_CPU_ACCESS_REQUIRED};
    uint64_t out[4]={};uint32_t no=4;call(N48N_SEL_BOCREATE,nullptr,0,&in,sizeof(in),out,&no,nullptr,nullptr);return out[0];
}
static void *map_bo(uint32_t h)
{
    mach_vm_address_t p=0;mach_vm_size_t size=0;
    require(guard_map(client,h,mach_task_self(),&p,&size,kIOMapAnywhere)==KERN_SUCCESS,"unit CPU map");return (void *)p;
}
static void gpu_map(uint32_t h,uint64_t va,uint64_t size,uint32_t flags,uint32_t operation=N48N_VA_OP_MAP)
{
    n48n_gem_va in={};in.handle=h;in.va_address=va;in.map_size=size;in.flags=flags;in.operation=operation;
    call(N48N_SEL_GEMVA,nullptr,0,&in,sizeof(in),nullptr,nullptr,nullptr,nullptr);
}
static void wait_sequence(void)
{
    uint64_t input[3]={counts.last_sequence,0,1},out[3]={};uint32_t no=3;
    call(N48N_SEL_WAITSEQ,input,3,nullptr,0,out,&no,nullptr,nullptr);
}
int main(int argc,char **argv)
{
    require(argc==2,"unit argument");test_case=argv[1];unsetenv("NULLARC_CPU_CASE");
    require(!setenv("RADV_DARWIN_BUILD34_IB_TAIL","1",1),"unit policy");
    io_connect_t denied=0;require(guard_open(0,mach_task_self(),0,&denied)==kIOReturnNotPermitted && !denied,"unit disabled gate");
    phx34_runtime_arm();
    const char *service=is("proxy")?"NMXAccel":"PhxBringup";
    io_service_t svc=guard_match(kIOMainPortDefault,IOServiceMatching(service));
    io_connect_t connection=0;guard_open(svc,mach_task_self(),N48N_UC_TYPE,&connection);
    if(is("second-open"))guard_open(svc,mach_task_self(),N48N_UC_TYPE,&connection);
    if(is("matching-retry"))guard_match(kIOMainPortDefault,IOServiceMatching("PhxBringup"));
    if(is("alternate-enumeration")){io_iterator_t it=0;guard_matches(kIOMainPortDefault,IOServiceMatching("PhxBringup"),&it);}
    handshake();handshake();
    if(is("third-Hello"))handshake();
    const uint32_t tail=create_bo(4096);uint32_t *tail_cpu=(uint32_t *)map_bo(tail);
    const uint32_t nop[8]={0xc0061000u,0,0,0,0,0,0,0};memcpy(tail_cpu,nop,sizeof(nop));
    if(is("tail-bytes"))tail_cpu[1]=1;
    if(is("tail-padding"))tail_cpu[8]=1;
    guard_unmap(client,tail,mach_task_self(),(uintptr_t)tail_cpu);
    if(is("tail-remap"))map_bo(tail);
    gpu_map(tail,0x10000,4096,N48N_VM_PAGE_READABLE | N48N_VM_PAGE_EXECUTABLE | (is("tail-writeable")?N48N_VM_PAGE_WRITEABLE:0));
    const uint32_t payload=create_bo(16384);uint32_t *data=(uint32_t *)map_bo(payload);
    memcpy((uint8_t *)data+0x1000,nop,sizeof(nop));
    const uint64_t va=is("high-canonical")?0xffff800000020000ull:0x20000;
    gpu_map(payload,is("noncanonical")?0x800000020000ull:va,16384,N48N_VM_PAGE_READABLE | N48N_VM_PAGE_EXECUTABLE);
    if(is("overlap"))gpu_map(payload,va,4096,N48N_VM_PAGE_EXECUTABLE);
    phx34_runtime_bind_arena(data,16384);
    n48n_ctx alloc={N48N_CTX_OP_ALLOC,0,0,0},ctx={};size_t nr=sizeof(ctx);
    call(N48N_SEL_CTX,nullptr,0,&alloc,sizeof(alloc),nullptr,nullptr,&ctx,&nr);const uint32_t context=ctx.op;
    struct {n48n_cs_in h;n48n_cs_ib ibs[2];} submit={};
    submit.h.abi=1;submit.h.ctx_id=context;submit.h.num_ibs=2;
    submit.ibs[0].va_start=va+0x1000;submit.ibs[0].ib_bytes=32;submit.ibs[0].ip_type=1;
    submit.ibs[1].va_start=0x10000;submit.ibs[1].ib_bytes=32;submit.ibs[1].ip_type=1;
    if(is("graphics"))submit.ibs[0].ip_type=0;
    if(is("wrong-tail"))submit.ibs[1].va_start+=4096;
    if(is("missing-IB-map"))submit.ibs[0].va_start=0x40000;
    if(is("too-many-IBs"))submit.h.num_ibs=65;
    if(is("scanout"))call(N48N_SEL_SCAN_ACQUIRE,nullptr,0,nullptr,0,nullptr,nullptr,nullptr,nullptr);
    uint64_t sequence_out=0;uint32_t no=1;
    call(N48N_SEL_SUBMIT,nullptr,0,&submit,sizeof(submit),is("missing-submit-output")?nullptr:&sequence_out,&no,nullptr,nullptr);
    if(is("close-inflight"))guard_close(client);
    if(is("CPU-unmap-inflight"))guard_unmap(client,payload,mach_task_self(),(uintptr_t)data);
    if(is("GPU-unmap-inflight"))gpu_map(payload,va,16384,0,N48N_VA_OP_UNMAP);
    if(is("free-inflight")){uint64_t h=payload;call(N48N_SEL_BOFREE,&h,1,nullptr,0,nullptr,nullptr,nullptr,nullptr);}
    wait_sequence();phx34_runtime_verify_pass(0);
    if(!is("unchanged-IB"))data[0x1000/4+1]^=1;
    no=1;call(N48N_SEL_SUBMIT,nullptr,0,&submit,sizeof(submit),&sequence_out,&no,nullptr,nullptr);
    wait_sequence();phx34_runtime_verify_pass(1);
    if(is("third-submit")){no=1;call(N48N_SEL_SUBMIT,nullptr,0,&submit,sizeof(submit),&sequence_out,&no,nullptr,nullptr);}
    require(is("ok") || is("high-canonical"),"unit expected rejection did not occur");
    guard_unmap(client,payload,mach_task_self(),(uintptr_t)data);gpu_map(payload,va,16384,0,N48N_VA_OP_UNMAP);
    uint64_t h=payload;call(N48N_SEL_BOFREE,&h,1,nullptr,0,nullptr,nullptr,nullptr,nullptr);
    n48n_ctx release={N48N_CTX_OP_FREE,0,context,0};nr=sizeof(ctx);call(N48N_SEL_CTX,nullptr,0,&release,sizeof(release),nullptr,nullptr,&ctx,&nr);
    guard_close(client);phx34_runtime_finish();
    printf("CPU-GUARD-PASS %s; no GPU\n",test_case);return 0;
}
