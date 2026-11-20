// SPDX-License-Identifier: MIT
// Actual ioctl/planner/marshaller/provider, controlled CPU transport only.
#include <errno.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ac_darwin_drm.c"

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"check failed %d: %s\n",__LINE__,#x); abort(); } } while (0)
struct fixture {
   struct acd_core core;
   struct acd_device dev;
   unsigned calls, waits, mixed, closes;
   uint64_t next, done;
   bool dependency_done;
   uint32_t engines[4];
};
int acd_kext_open_iokit(struct acd_kext **out) { (void)out; CHECK(false); return -ENOSYS; }
static int wait_seq(void *ctx,uint64_t seq,uint64_t ns,bool *busy,uint64_t *retired)
{
   struct fixture *f=ctx; CHECK(ns<=20000000ull); ++f->waits;
   if(seq==10 && ns) f->dependency_done=true; // keep a broken guard finite
   *busy=seq!=f->done && !(seq==10 && f->dependency_done);
   *retired=9; return 0;
}
static int call(void *ctx,uint32_t sel,const uint64_t *sin,uint32_t nsin,
                const void *stin,size_t size,uint64_t *sout,uint32_t *nsout,
                void *stout,size_t *stoutsz)
{
   struct fixture *f=ctx;
   CHECK(sel==ACD_SEL_SUBMIT && !sin && !nsin && !stout && !stoutsz && stin);
   const struct n48n_cs_in *h=stin;
   const struct n48n_cs_ib *ib=(const void *)((const char *)stin+sizeof(*h));
   CHECK(h->abi==N48N_ABI_VERSION && h->ctx_id==1 && h->num_ibs>0 && h->num_ibs<=N48N_MAX_IBS);
   CHECK(size==sizeof(*h)+h->num_ibs*sizeof(*ib) && sout && nsout && *nsout==1);
   CHECK(f->calls<4); f->engines[f->calls++]=ib[0].ip_type;
   for(unsigned i=0;i<h->num_ibs;++i) {
      CHECK(ib[i].ib_bytes==4 && ib[i].va_start>=0x20000 && !ib[i]._pad);
      if(ib[i].ip_type!=ib[0].ip_type) ++f->mixed;
   }
   sout[0]=f->next++; return 0;
}
static void close_fake(void *ctx) { ++((struct fixture *)ctx)->closes; }
static void initialize(struct fixture *f,bool exact,bool clone)
{
   memset(f,0,sizeof(*f)); f->next=20;
   CHECK(pthread_mutex_init(&f->core.bo_lock,NULL)==0);
   const struct acd_kext_ops ops={.call=call,.close=close_fake};
   f->core.kext=acd_kext_create(&ops,f); CHECK(f->core.kext);
   const struct acd_sync_backend be={.wait_seq=wait_seq,.ctx=f,.exact_completion=exact};
   f->core.sync=acd_sync_provider_create(&be); CHECK(f->core.sync);
   f->dev.core=&f->core;
   f->dev.sync=clone ? f->core.sync->clone(f->core.sync) : f->core.sync; CHECK(f->dev.sync);
}
static void finalize(struct fixture *f)
{
   if(f->dev.sync!=f->core.sync) f->dev.sync->finalize(f->dev.sync);
   f->core.sync->finalize(f->core.sync); acd_kext_destroy(f->core.kext);
   CHECK(f->closes==1 && pthread_mutex_destroy(&f->core.bo_lock)==0);
}
static uint32_t create(struct fixture *f)
{
   uint32_t h=0; CHECK(f->core.sync->create(f->core.sync,0,&h)==0 && h); return h;
}
static bool ready(struct fixture *f,uint32_t h)
{
   int r=f->core.sync->wait(f->core.sync,&h,1,0,0,NULL);
   CHECK(!r || (r==-1 && errno==ETIME)); return r==0;
}
// Profile 1 mixes engines at the last IB, 2/3 are unknown first/last engines,
// 4/5 use nonzero instance/ring, 6 is uniformly unknown (not merely mixed).
// Ordinary payload/address validation is native.
static int submit(struct fixture *f,unsigned count,unsigned engine,unsigned profile,
                  uint32_t dependency,uint32_t signal,uint64_t *seq)
{
   CHECK(count<=129);
   struct drm_amdgpu_cs_chunk_ib ibs[129];
   struct drm_amdgpu_cs_chunk chunks[131]; uint64_t pointers[131]; unsigned n=count;
   for(unsigned i=0;i<count;++i) {
      ibs[i]=(struct drm_amdgpu_cs_chunk_ib){.va_start=0x20000+4*i,.ib_bytes=4,.ip_type=engine};
      if(profile==1 && i==count-1) ibs[i].ip_type=engine==AMDGPU_HW_IP_GFX ? AMDGPU_HW_IP_COMPUTE : AMDGPU_HW_IP_GFX;
      if((profile==2 && i==0) || (profile==3 && i==count-1)) ibs[i].ip_type=99;
      if(profile==6) ibs[i].ip_type=99;
      if(profile==4 && i==count-1) ibs[i].ip_instance=1;
      if(profile==5 && i==count-1) ibs[i].ring=1;
      chunks[i]=(struct drm_amdgpu_cs_chunk){.chunk_id=AMDGPU_CHUNK_ID_IB,
         .length_dw=sizeof(ibs[i])/4,.chunk_data=(uintptr_t)&ibs[i]};
      pointers[i]=(uintptr_t)&chunks[i];
   }
   struct drm_amdgpu_cs_chunk_sem in={.handle=dependency},out={.handle=signal};
   if(dependency) {
      chunks[n]=(struct drm_amdgpu_cs_chunk){.chunk_id=AMDGPU_CHUNK_ID_SYNCOBJ_IN,
         .length_dw=sizeof(in)/4,.chunk_data=(uintptr_t)&in}; pointers[n]=(uintptr_t)&chunks[n]; ++n;
   }
   if(signal) {
      chunks[n]=(struct drm_amdgpu_cs_chunk){.chunk_id=AMDGPU_CHUNK_ID_SYNCOBJ_OUT,
         .length_dw=sizeof(out)/4,.chunk_data=(uintptr_t)&out}; pointers[n]=(uintptr_t)&chunks[n]; ++n;
   }
   union drm_amdgpu_cs cs={.in={.ctx_id=1,.num_chunks=n,.chunks=(uintptr_t)pointers}};
   unsigned char before[sizeof(cs)]; memcpy(before,&cs,sizeof(cs));
   int r=acd_ioctl(&f->dev,DRM_AMDGPU_CS,&cs,sizeof(cs));
   if(r) CHECK(memcmp(before,&cs,sizeof(cs))==0);
   if(!r && seq) *seq=cs.out.handle;
   return r;
}
#ifdef HAVE_EXACT_CS_SHAPE
static void unattached(struct fixture *f,uint32_t h)
{
   uint32_t copy=create(f);
   CHECK(f->core.sync->transfer(f->core.sync,copy,0,h,0,0)==-1 && errno==EINVAL);
   CHECK(f->core.sync->destroy(f->core.sync,copy)==0);
}
static void supported(void)
{
   const unsigned sizes[]={1,2,63,64};
   for(unsigned engine=0;engine<2;++engine) for(unsigned i=0;i<4;++i) {
      struct fixture f; initialize(&f,true,i%2); uint32_t out=create(&f),other=create(&f);
      CHECK(acd_sync_cs_attach(f.core.sync,other,0,10)==0);
      uint64_t seq=777; CHECK(submit(&f,sizes[i],engine,0,0,out,&seq)==0 && seq==20);
      CHECK(f.calls==1 && !f.waits && !f.mixed && f.engines[0]==engine);
      CHECK(!ready(&f,out)); f.done=20; CHECK(ready(&f,out));
      CHECK(!ready(&f,other)); finalize(&f);
   }
}
static void rejected(void)
{
   const unsigned sizes[]={2,64,65,66,128,129};
   for(unsigned engine=0;engine<2;++engine) for(unsigned i=0;i<6;++i) for(unsigned profile=0;profile<7;++profile) {
      if(!profile && sizes[i]<=64) continue;
      struct fixture f; initialize(&f,true,i%2); uint32_t dep=create(&f),out=create(&f);
      CHECK(acd_sync_cs_attach(f.core.sync,dep,0,10)==0);
      uint64_t seq=777;
      CHECK(submit(&f,sizes[i],engine,profile,dep,out,&seq)==-EOPNOTSUPP && seq==777);
      CHECK(!f.calls && !f.waits && !f.mixed);
      unattached(&f,out); CHECK(!ready(&f,out)); finalize(&f);
   }
   struct fixture f; initialize(&f,true,false); uint64_t seq=777;
   CHECK(submit(&f,0,0,0,0,0,&seq)==-EINVAL && seq==777 && !f.calls && !f.waits); finalize(&f);
}
static void legacy(void)
{
   struct fixture f; initialize(&f,false,false); uint64_t seq=777;
   CHECK(submit(&f,65,AMDGPU_HW_IP_COMPUTE,1,0,0,&seq)==0 && seq==21);
   CHECK(f.calls==2 && !f.waits && f.engines[0]==AMDGPU_HW_IP_COMPUTE && f.engines[1]==AMDGPU_HW_IP_GFX);
   finalize(&f);
}
#endif
int main(void)
{
   unsetenv("RADV_DARWIN_TRACE");
#ifdef HAVE_EXACT_CS_SHAPE
   supported(); rejected(); legacy();
   printf("PASS actual Mesa exact CS shape: %u checks; 8 accepted and 80 refused shapes; empty and legacy; GPU_executed=false\n",checks);
#else
   struct fixture f; initialize(&f,true,false); uint32_t out=create(&f); uint64_t seq=777;
   CHECK(submit(&f,65,AMDGPU_HW_IP_COMPUTE,1,0,out,&seq)==0 && seq==21);
   CHECK(f.calls==2 && f.engines[0]==AMDGPU_HW_IP_COMPUTE && f.engines[1]==AMDGPU_HW_IP_GFX);
   f.done=21; CHECK(ready(&f,out)); CHECK(f.done!=20); finalize(&f);
   initialize(&f,true,false); CHECK(submit(&f,2,AMDGPU_HW_IP_GFX,1,0,0,&seq)==0 && f.calls==1 && f.mixed==1); finalize(&f);
   printf("PASS 0005-only CS shape counterexamples: mixed plans reach single-queue packets; split result omits earlier pending sequence; GPU_executed=false\n");
#endif
}
