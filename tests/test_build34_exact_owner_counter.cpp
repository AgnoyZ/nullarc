// SPDX-License-Identifier: MIT
// Controlled CAS failures exercise the actual header's finite retry policy.
// This is separate from its real-atomic/real-thread identity tests.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static unsigned calls,failures,checks;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
static bool competingCompare(uint64_t *p,uint64_t *expected,uint64_t desired,bool,int,int) {
    CHECK(++calls<=32);
    if(calls<=failures) { *p=++*expected; return false; } // another modeled taker won
    CHECK(*p==*expected && desired==*expected+1); *p=desired; return true;
}
#define __atomic_compare_exchange_n competingCompare
#include "build34_exact_ownership.h"
#undef __atomic_compare_exchange_n
using namespace phx34_exact;
int main() {
    uint64_t out=12345; OwnerEpochs blocked;
    calls=0; failures=32; CHECK(!blocked.take(out) && calls==32 && out==12345);
    calls=0; failures=0; CHECK(blocked.take(out) && calls==1 && out==33);
    OwnerEpochs lastTry; calls=0; failures=31;
    CHECK(lastTry.take(out) && calls==32 && out==32);
    OwnerEpochs exhausted(UINT64_MAX-2); calls=0; failures=1; out=12345;
    CHECK(!exhausted.take(out) && calls==1 && out==12345);
    calls=0; failures=0; CHECK(!exhausted.take(out) && !calls && out==12345);
    std::printf("PASS owner counter controlled contention: %u checks; 32-attempt cap; GPU_executed=false\n",checks);
}
