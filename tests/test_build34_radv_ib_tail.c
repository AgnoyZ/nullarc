/* SPDX-License-Identifier: MIT
 * CPU test of the ACTUAL patched Mesa marshaller. No IOKit or GPU backend.
 */
#include "ac_darwin_kext.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { __atomic_add_fetch(&checks, 1, __ATOMIC_RELAXED); if (!(x)) { fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); abort(); } } while (0)
static unsigned checks;
enum fault { NONE, HELLO_ERROR, HELLO_SHAPE, BAD_ABI, BAD_MINOR, BAD_BUILD, BAD_MAX,
   BAD_VMID, INFO_ERROR, INFO_SHAPE, INFO_ABI, INFO_MINOR, INFO_BUILD, INFO_VMID,
   INFO_GC, INFO_MAX, INFO_HUNG, INFO_NOT_NATIVE, INFO_NOT_READY, BAD_LOW_RANGE,
   CREATE_ERROR, CREATE_SHAPE, CREATE_HANDLE, CREATE_SIZE, CREATE_DOMAIN,
   CREATE_BITS, MAP_ERROR, MAP_NULL, MAP_ALIGNMENT, MAP_SIZE, UNMAP_ERROR,
   GEMVA_ERROR, SUBMIT_ERROR, SUBMIT_SHAPE, SUBMIT_ZERO, SUBMIT_LAST, SUBMIT_STALE,
   RETIRE_ERROR, RETIRE_BUSY, RETIRE_LOW, RETIRE_LAST, RETIRE_EMITTED_LOW, RETIRE_EMITTED_LAST };

struct fake {
   _Alignas(4096) unsigned char page[4096];
   enum fault fault;
   unsigned hello, info, create, map, unmap, gemva, submit, wait, close;
   unsigned payload, consumed, capacity, fail_at;
   bool tail, fence, threaded;
   uint64_t seq;
};
static const uint64_t tail_va = 0x20000;
static struct n48n_cs_ib payload_ib(unsigned i) {
   return (struct n48n_cs_ib){ .flags = i & 1 ? N48N_IB_FLAG_EMIT_MEM_SYNC : 0,
      .va_start = 0x100000ull + (uint64_t)i * 4096, .ib_bytes = 320,
      .ip_type = AMDGPU_HW_IP_COMPUTE };
}
int acd_kext_open_iokit(struct acd_kext **out) { *out = NULL; return -ENOTSUP; }

static int fake_call(void *opaque, uint32_t sel, const uint64_t *sin, uint32_t nsin,
   const void *stin, size_t stinsz, uint64_t *sout, uint32_t *nsout, void *stout, size_t *stoutsz) {
   struct fake *f = opaque;
   switch (sel) {
   case ACD_SEL_HELLO:
      ++f->hello; CHECK(nsin == 2 && sin[0] == 1 && sin[1] == N48N_HELLO_F_MINOR);
      CHECK(*nsout == 4);
      if (f->fault == HELLO_ERROR) return ACD_KR_NOT_READY;
      sout[0] = (f->fault == BAD_ABI ? 2 : 1) | (uint64_t)(f->fault == BAD_MINOR ? 11 : 12) << 16;
      sout[1] = f->fault == BAD_BUILD ? 41 : 34;
      sout[2] = f->fault == BAD_MAX ? 63 : N48N_MAX_IBS;
      sout[3] = f->fault == BAD_VMID ? 9 : 8;
      *nsout = f->fault == HELLO_SHAPE ? 3 : 4; return 0;
   case ACD_SEL_QUERY_INFO: {
      ++f->info; CHECK(!nsin && !stin && !stinsz && *stoutsz == sizeof(struct n48n_info));
      if (f->fault == INFO_ERROR) return ACD_KR_ABORTED;
      struct n48n_info info = { .abi_version = 1, .kext_build = 34,
         .flags = N48N_INFO_NATIVE_BOOT | N48N_INFO_S1B_POSITIVE, .vmid = 8,
         .gc_version = (11u << 16) | 1, .max_ibs = N48N_MAX_IBS,
         .va_low_first = 0x10000, .va_low_last = 0x7fffffffffff, .reserved = {[2] = 12} };
      if (f->fault == INFO_ABI) info.abi_version = 2;
      if (f->fault == INFO_MINOR) info.reserved[2] = 11;
      if (f->fault == INFO_BUILD) info.kext_build = 42;
      if (f->fault == INFO_VMID) info.vmid = 9;
      if (f->fault == INFO_GC) info.gc_version = 12 << 16;
      if (f->fault == INFO_MAX) info.max_ibs = 63;
      if (f->fault == INFO_HUNG) info.flags |= N48N_INFO_HUNG;
      if (f->fault == INFO_NOT_NATIVE) info.flags &= ~N48N_INFO_NATIVE_BOOT;
      if (f->fault == INFO_NOT_READY) info.flags &= ~N48N_INFO_S1B_POSITIVE;
      if (f->fault == BAD_LOW_RANGE) info.va_low_last = 0x800000000000;
      memcpy(stout, &info, sizeof(info));
      *stoutsz = f->fault == INFO_SHAPE ? sizeof(info) - 1 : sizeof(info); return 0;
   }
   case ACD_SEL_BO_CREATE: {
      ++f->create; CHECK(stinsz == sizeof(struct n48n_gem_create_in));
      const struct n48n_gem_create_in expected = {4096,4096,N48N_GEM_DOMAIN_GTT,N48N_GEM_CPU_ACCESS_REQUIRED};
      CHECK(!memcmp(stin, &expected, sizeof(expected))); CHECK(*nsout == 4);
      if (f->fault == CREATE_ERROR) return ACD_KR_NO_MEMORY;
      sout[0] = f->fault == CREATE_HANDLE ? 0 : 17;
      sout[1] = f->fault == CREATE_SIZE ? 8192 : 4096;
      sout[2] = f->fault == CREATE_DOMAIN ? N48N_GEM_DOMAIN_VRAM : N48N_GEM_DOMAIN_GTT;
      sout[3] = f->fault == CREATE_BITS ? 0 : N48N_PLACED_ZEROED | N48N_PLACED_CPU_MAPPABLE;
      *nsout = f->fault == CREATE_SHAPE ? 3 : 4; return 0;
   }
   case ACD_SEL_GEM_VA: {
      ++f->gemva; CHECK(f->unmap == 1 && stinsz == sizeof(struct n48n_gem_va));
      const struct n48n_gem_va expected = { .handle = 17, .operation = N48N_VA_OP_MAP,
         .flags = N48N_VM_PAGE_READABLE | N48N_VM_PAGE_EXECUTABLE,
         .va_address = tail_va, .map_size = 4096 };
      CHECK(!memcmp(stin, &expected, sizeof(expected)));
      return f->fault == GEMVA_ERROR ? ACD_KR_NO_RESOURCES : 0;
   }
   case ACD_SEL_SUBMIT: {
      ++f->submit; CHECK(stinsz >= sizeof(struct n48n_cs_in));
      if (f->threaded && f->consumed == f->payload) f->consumed = 0;
      struct n48n_cs_in hdr; memcpy(&hdr, stin, sizeof(hdr));
      unsigned n = f->payload - f->consumed;
      if (n > f->capacity) n = f->capacity;
      CHECK(hdr.abi == 1 && hdr.ctx_id == 7 && hdr.num_ibs == n + f->tail);
      CHECK(hdr.num_ibs <= N48N_MAX_IBS && stinsz == sizeof(hdr) + hdr.num_ibs * sizeof(struct n48n_cs_ib));
      const bool last = f->consumed + n == f->payload;
      CHECK(hdr.flags == (last && f->fence ? N48N_CS_HAS_FENCE : 0));
      CHECK(hdr.fence_handle == (last && f->fence ? 31 : 0));
      CHECK(hdr.fence_offset == (last && f->fence ? 24 : 0));
      CHECK(hdr.reserved == 0);
      const unsigned char *ibs = (const unsigned char *)stin + sizeof(hdr);
      for (unsigned i = 0; i < n; ++i) {
         struct n48n_cs_ib expected = payload_ib(f->consumed + i);
         CHECK(!memcmp(ibs + i * sizeof(expected), &expected, sizeof(expected)));
      }
      if (f->tail) {
         const struct n48n_cs_ib expected = { .va_start = tail_va, .ib_bytes = 32, .ip_type = AMDGPU_HW_IP_COMPUTE };
         CHECK(!memcmp(ibs + n * sizeof(expected), &expected, sizeof(expected)));
         const uint32_t nop[8] = {0xc0061000u,0,0,0,0,0,0,0};
         CHECK(!memcmp(f->page, nop, sizeof(nop)));
         for (unsigned i = sizeof(nop); i < 4096; ++i) CHECK(f->page[i] == 0);
      }
      f->consumed += n;
      if (f->submit == f->fail_at) {
         if (f->fault == SUBMIT_ERROR) return ACD_KR_ABORTED;
         if (f->fault == SUBMIT_SHAPE) { *nsout = 0; return 0; }
         if (f->fault == SUBMIT_ZERO) { sout[0] = 0; return 0; }
         if (f->fault == SUBMIT_LAST) { sout[0] = N48N_SEQ_LAST; return 0; }
         if (f->fault == SUBMIT_STALE) { sout[0] = f->seq; return 0; }
      }
      sout[0] = ++f->seq; *nsout = 1; return 0;
   }
   case ACD_SEL_WAIT_SEQ:
      ++f->wait; CHECK(nsin == 3 && sin[0] == f->seq && sin[1] == N48N_WAIT_CAP_NS && !sin[2]);
      if (f->fault == RETIRE_ERROR) return ACD_KR_TIMEOUT;
      sout[0] = f->fault == RETIRE_BUSY;
      sout[1] = f->fault == RETIRE_LOW ? f->seq - 1 : f->fault == RETIRE_LAST ? N48N_SEQ_LAST : f->seq;
      sout[2] = f->fault == RETIRE_EMITTED_LOW ? f->seq - 1 : f->fault == RETIRE_EMITTED_LAST ? N48N_SEQ_LAST : f->seq;
      *nsout = 3; return 0;
   case PHX_SEL_TOPOLOGY: return ACD_KR_UNSUPPORTED;
   case ACD_SEL_READ_REGS:
      CHECK(nsin == 3 && sin[0] == ACD_GB_ADDR_CONFIG_REG && sin[1] == 1 && *stoutsz == 4);
      *(uint32_t *)stout = ACD_GB_ADDR_CONFIG_GFX1201; return 0;
   default: CHECK(!"unexpected selector (including early free/unmap)"); return ACD_KR_UNSUPPORTED;
   }
}
static int fake_map(void *opaque, uint32_t handle, void **addr, size_t *size) {
   struct fake *f = opaque; ++f->map; CHECK(handle == 17);
   if (f->fault == MAP_ERROR) return ACD_KR_NO_MEMORY;
   *addr = f->fault == MAP_NULL ? NULL : f->page + (f->fault == MAP_ALIGNMENT ? 1 : 0);
   *size = f->fault == MAP_SIZE ? 8192 : 4096; return 0;
}
static int fake_unmap(void *opaque, uint32_t handle, void *addr) {
   struct fake *f = opaque; ++f->unmap; CHECK(handle == 17 && addr == f->page);
   const uint32_t nop[8] = {0xc0061000u,0,0,0,0,0,0,0}; CHECK(!memcmp(addr, nop, sizeof(nop)));
   return f->fault == UNMAP_ERROR ? ACD_KR_ABORTED : 0;
}
static void fake_close(void *opaque) { struct fake *f = opaque; ++f->close; }
static struct acd_kext *make(struct fake *f, bool enable) {
   const struct acd_kext_ops ops = {.call=fake_call,.map=fake_map,.unmap=fake_unmap,.close=fake_close};
   struct acd_kext *k = acd_kext_create(&ops, f); CHECK(k);
   f->tail = enable; f->capacity = N48N_MAX_IBS - enable;
   if (enable) CHECK(!acd_kext_enable_build34_ib_tail(k, tail_va));
   return k;
}
static int submit(struct acd_kext *k, struct fake *f, unsigned n, bool fence, uint64_t *seq) {
   struct n48n_cs_ib *ibs = calloc(n ? n : 1, sizeof(*ibs)); CHECK(ibs);
   for (unsigned i=0;i<n;++i) ibs[i]=payload_ib(i);
   const struct acd_cs_plan plan = {.ctx_id=7,.ibs=ibs,.n_ibs=n,.has_fence=fence,.fence_handle=31,.fence_offset=24};
   f->payload=n; f->consumed=0; f->fence=fence;
   int r=acd_kext_submit(k,&plan,seq); free(ibs); return r;
}
static void *thread_submits(void *opaque) {
   struct acd_kext *k = opaque;
   struct n48n_cs_ib ibs[64];
   for (unsigned i=0;i<64;++i) ibs[i]=payload_ib(i);
   const struct acd_cs_plan plan = {.ctx_id=7,.ibs=ibs,.n_ibs=64};
   uint64_t previous=0;
   for (unsigned i=0;i<16;++i) {
      uint64_t seq=0; CHECK(!acd_kext_submit(k,&plan,&seq) && seq>previous && !(seq&1));
      previous=seq;
   }
   return NULL;
}
int main(int argc, char **argv) {
   /* Only a fake CPU backend runs here. The Python parent independently checks
    * HOLD subprocesses stay alive without close, then terminates that mock. */
   if (argc == 3 && !strcmp(argv[1], "--hold")) {
      struct fake f={0}; struct acd_kext *k=make(&f,true); uint64_t seq=123;
      f.fault=(enum fault)atoi(argv[2]);
      f.fail_at=2;
      int r=submit(k,&f,64,false,&seq);
      if (f.fault>=SUBMIT_ERROR && f.fault<=SUBMIT_STALE) {
         CHECK(r<0 && seq==123 && f.submit==2);
         unsigned previous=f.submit; CHECK(submit(k,&f,1,false,&seq)==-EIO && f.submit==previous);
      } else CHECK(!r);
      acd_kext_destroy(k); CHECK(!"HOLD returned");
   }
   CHECK(argc==1);
   for (unsigned tail=0;tail<2;++tail) for (unsigned fence=0;fence<2;++fence) {
      for (unsigned n=1;n<=257;++n) {
         struct fake f={0}; struct acd_kext *k=make(&f,tail); uint64_t seq=0;
         CHECK(!submit(k,&f,n,fence,&seq));
         unsigned calls=n/f.capacity+(n%f.capacity!=0);
         CHECK(f.submit==calls && seq==calls && f.consumed==n);
         acd_kext_destroy(k); CHECK(f.close==1 && f.wait==tail);
      }
   }
   for (enum fault fault=HELLO_ERROR;fault<=GEMVA_ERROR;++fault) {
      struct fake f={.fault=fault}; struct acd_kext *k=make(&f,false);
      CHECK(acd_kext_enable_build34_ib_tail(k,tail_va)<0);
      CHECK(!f.submit && !f.close);
      if (fault<=BAD_LOW_RANGE) CHECK(!f.create);
      uint64_t seq=73; CHECK(submit(k,&f,1,false,&seq)==-EIO && seq==73 && !f.submit);
      CHECK(acd_kext_enable_build34_ib_tail(k,tail_va)==-EINVAL);
      acd_kext_destroy(k); CHECK(f.close==1 && !f.wait);
   }
   const uint64_t bad_va[]={0,1,0x10001,0x8000,0x800000000000ull,UINT64_MAX,0xfffffffffffff000ull};
   for (unsigned i=0;i<sizeof(bad_va)/sizeof(*bad_va);++i) {
      struct fake f={0}; struct acd_kext *k=make(&f,false);
      CHECK(acd_kext_enable_build34_ib_tail(k,bad_va[i])<0 && !f.create);
      acd_kext_destroy(k); CHECK(f.close==1);
   }
   for (unsigned which=0;which<3;++which) {
      struct fake f={0}; struct acd_kext *k=make(&f,true); struct n48n_cs_ib ibs[64];
      for (unsigned i=0;i<64;++i) ibs[i]=payload_ib(i);
      if (!which) ibs[63].ip_type=AMDGPU_HW_IP_GFX;
      if (which==1) ibs[63].ip_instance=1;
      if (which==2) ibs[63].ring=1;
      struct acd_cs_plan p={.ctx_id=7,.ibs=ibs,.n_ibs=64}; uint64_t seq=99;
      CHECK(acd_kext_submit(k,&p,&seq)==-EINVAL && !f.submit && seq==99);
      acd_kext_destroy(k); CHECK(f.close==1);
   }
   { struct fake f={0}; struct acd_kext *k=make(&f,false); uint64_t seq=0;
     CHECK(!submit(k,&f,1,false,&seq)); CHECK(acd_kext_enable_build34_ib_tail(k,tail_va)==-EINVAL);
     CHECK(!f.hello); acd_kext_destroy(k); CHECK(f.close==1); }
   { struct fake f={0}; struct acd_kext *k=make(&f,true); uint64_t seq=99;
     CHECK(acd_kext_enable_build34_ib_tail(k,tail_va)==-EINVAL && f.create==1);
     CHECK(submit(k,&f,0,false,&seq)==-EINVAL && !f.submit && seq==99);
     CHECK(acd_kext_submit(k,NULL,&seq)==-EINVAL && !f.submit);
     acd_kext_destroy(k); CHECK(f.close==1); }
   { struct fake f={0}; struct acd_kext *k=make(&f,true);
     f.threaded=true; f.payload=64;
     pthread_t threads[2];
     for (unsigned i=0;i<2;++i) CHECK(!pthread_create(&threads[i],NULL,thread_submits,k));
     for (unsigned i=0;i<2;++i) CHECK(!pthread_join(threads[i],NULL));
     CHECK(f.submit==64 && f.seq==64);
     acd_kext_destroy(k); CHECK(f.close==1 && f.wait==1); }
   printf("PASS actual Mesa transport: %u checks; 1028 split/fence cases; admission, ownership and validation\n",checks);
   return 0;
}
