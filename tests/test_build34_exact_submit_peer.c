// SPDX-License-Identifier: MIT
// Independently encoded byte offsets; CPU fixture, not the Mesa adapter.
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "build34_exact_submit_wire.h"
static void put32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i)); }
static void put64(uint8_t *p,uint64_t v) { for(unsigned i=0;i<8;i++) p[i]=(uint8_t)(v>>(8*i)); }
static uint64_t get64(const uint8_t *p) { uint64_t v=0; for(unsigned i=0;i<8;i++) v|=(uint64_t)p[i]<<(8*i); return v; }
void phx34_submit_encode(uint8_t *p,uint64_t owner,unsigned count,bool gfx)
{
    memset(p,0,2112); put32(p,1); put32(p+4,2112); put64(p+8,owner);
    put32(p+32,1); put32(p+36,1); put32(p+40,count);
    for(unsigned i=0;i<count && i<64;i++) {
        uint8_t *ib=p+64+32*i;
        put64(ib+8,0x10000+64*i); put32(ib+16,64); put32(ib+20,gfx ? 0 : 1);
    }
}
bool phx34_submit_reply(const uint8_t *p,uint64_t owner,uint64_t seq,uint64_t generation,unsigned queue)
{
    uint8_t expected[64]={0}; put32(expected,1); put32(expected+4,64); put32(expected+8,3);
    put64(expected+16,owner); put64(expected+24,get64(p+24)); put64(expected+32,seq); put64(expected+40,generation);
    memcpy(expected+48,p+48,4); put32(expected+52,queue);
    return get64(p+24)>0 && get64(p+24)!=UINT64_MAX && p[48]<64 &&
           p[49]==0 && p[50]==0 && p[51]==0 && memcmp(expected,p,64)==0;
}
