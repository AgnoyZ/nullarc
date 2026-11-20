// SPDX-License-Identifier: MIT
// Pure CPU arithmetic/state tests: no device load, mapping or GPU simulation.
#include "build34_exact_fence32.h"
#include <cstdio>
#include <cstdlib>

static uint64_t checks;
#define CHECK(v) do { ++checks; if (!(v)) { std::fprintf(stderr,"failed %s:%d: %s\n",__FILE__,__LINE__,#v); std::abort(); } } while (0)
using phx34_exact::FenceWindow32;
static constexpr uint64_t M = uint64_t{1} << 32;

static void identityAndRefusal() {
    FenceWindow32 f; uint64_t out=777;
    CHECK(!f.observe(1,0,out) && out==777);
    CHECK(!f.submit(1,1) && !f.canSubmit(1,1));
    CHECK(!f.seed(0,0) && !f.seed(UINT64_MAX,0) && !f.seed(1,UINT64_MAX));
    CHECK(f.seed(1,0));
    CHECK(!f.seed(2,0)); // a live generation cannot be overwritten
    CHECK(!f.canSubmit(1,0) && !f.canSubmit(2,1));
    CHECK(f.canSubmit(1,100) && f.submit(1,100));
    CHECK(!f.submit(1,100) && !f.submit(1,99));
    CHECK(!f.observe(2,100,out) && out==777);
    CHECK(!f.observe(1,101,out) && out==777);
    CHECK(f.observe(1,0,out) && out==0);
    CHECK(f.observe(1,100,out) && out==100);
    out=777; CHECK(!f.observe(1,99,out) && out==777);
    CHECK(!f.submit(1,UINT64_MAX));
    f.invalidate();
    CHECK(!f.observe(1,100,out) && out==777 && !f.submit(1,101));
    CHECK(!f.seed(1,100) && !f.seed(0,0));
    CHECK(f.seed(3,1000));
    CHECK(!f.observe(1,1000,out) && out==777);
    CHECK(f.observe(3,1000,out) && out==1000);
}
static void wrappingAndHoles() {
    FenceWindow32 f; uint64_t out=777;
    CHECK(f.seed(1,M-2) && f.submit(1,M+3));
    CHECK(f.observe(1,UINT32_MAX,out) && out==M-1);
    CHECK(f.observe(1,0,out) && out==M);
    CHECK(f.observe(1,3,out) && out==M+3);
    out=777; CHECK(!f.observe(1,2,out) && out==777);
    CHECK(f.submit(1,2*M+2)); // maximum unambiguous span is 2^32-1
    CHECK(!f.canSubmit(1,2*M+3) && !f.submit(1,2*M+3));
    CHECK(f.observe(1,2,out) && out==2*M+2);
    CHECK(f.submit(1,3*M+1) && f.observe(1,1,out) && out==3*M+1);
    CHECK(!f.submit(1,4*M+1));
    CHECK(f.observe(1,1,out) && out==3*M+1); // refused submit left upper bound intact
    // Distances are global sequence gaps, not a count of this queue's jobs.
    FenceWindow32 gap; CHECK(gap.seed(1,7));
    CHECK(!gap.submit(1,M+7) && !gap.submit(1,2*M+7));
    CHECK(gap.observe(1,7,out) && out==7);
    out=777; CHECK(!gap.observe(1,8,out) && out==777);
}
static void exhaustion() {
    FenceWindow32 f; uint64_t out=777;
    CHECK(f.seed(UINT64_MAX-1,UINT64_MAX-4));
    CHECK(f.submit(UINT64_MAX-1,UINT64_MAX-2));
    CHECK(f.observe(UINT64_MAX-1,static_cast<uint32_t>(UINT64_MAX-2),out) && out==UINT64_MAX-2);
    CHECK(f.submit(UINT64_MAX-1,UINT64_MAX-1));
    CHECK(f.observe(UINT64_MAX-1,static_cast<uint32_t>(UINT64_MAX-1),out) && out==UINT64_MAX-1);
    CHECK(!f.submit(UINT64_MAX-1,UINT64_MAX) && !f.submit(UINT64_MAX-1,0));
    f.invalidate(); CHECK(!f.seed(UINT64_MAX-1,0) && !f.seed(UINT64_MAX,0) && !f.seed(1,0));
}
static void queueIndependence() {
    FenceWindow32 compute,gfx; uint64_t a=777,b=888;
    CHECK(compute.seed(1,99) && gfx.seed(1,99));
    CHECK(compute.submit(1,100) && gfx.submit(1,101));
    CHECK(compute.observe(1,99,a) && a==99);
    CHECK(gfx.observe(1,101,b) && b==101 && a==99);
    gfx.invalidate();
    CHECK(!gfx.observe(1,101,b) && b==101);
    CHECK(compute.observe(1,100,a) && a==100);
}
// Enumerate the mathematical interval literally instead of duplicating the
// modular decoder. Every raw bit-pattern has at most one preimage within it.
template<unsigned Bits> static void exhaustive() {
    const uint64_t modulus=uint64_t{1}<<Bits;
    for(uint64_t base=0;base<3*modulus;++base) {
        for(uint64_t span=0;span<modulus;++span) {
            for(uint32_t raw=0;raw<=modulus;++raw) {
                phx34_exact::FenceWindow<Bits> f;
                CHECK(f.seed(1,base));
                if(span) CHECK(f.submit(1,base+span));
                uint64_t expected=777,count=0,out=888;
                for(uint64_t v=base;v<=base+span;++v)
                    if(v%modulus==raw) { ++count; expected=v; }
                CHECK(count<=1);
                CHECK(!f.canSubmit(1,base+modulus));
                CHECK(f.observe(1,raw,out)==(count==1));
                CHECK(out==(count==1 ? expected : 888));
                if(count) {
                    CHECK(f.observe(1,raw,out) && out==expected);
                    CHECK(f.canSubmit(1,expected+modulus)==false);
                }
                f.invalidate(); CHECK(!f.observe(1,raw,out));
                CHECK(f.seed(2,base));
                CHECK(!f.observe(1,raw,out));
            }
        }
    }
}
static void sustainedWraps() {
    FenceWindow32 f; uint64_t base=0,out=777;
    CHECK(f.seed(1,0));
    for(unsigned i=0;i<20000;++i) {
        base+=1000003;
        CHECK(f.submit(1,base));
        CHECK(f.observe(1,static_cast<uint32_t>(base),out) && out==base);
    }
}
static void missingCoherencyCounterexample() {
    // A correct decoder cannot distinguish a genuine M+1 sample from a stale
    // dword '1' left from a whole earlier wrap. Real non-regressing device
    // reads are a PRECONDITION, not established by this arithmetic test.
    FenceWindow32 f; uint64_t out=777;
    CHECK(f.seed(1,M-2) && f.submit(1,M+3));
    CHECK(f.observe(1,1,out) && out==M+1);
}
int main() {
    identityAndRefusal(); wrappingAndHoles(); exhaustion(); queueIndependence();
    exhaustive<2>(); exhaustive<3>(); exhaustive<4>(); sustainedWraps(); missingCoherencyCounterexample();
    std::printf("PASS fence32 window: %llu checks; exhaustive widths 2/3/4; 20000 sustained steps; GPU_executed=false\n",static_cast<unsigned long long>(checks));
}
