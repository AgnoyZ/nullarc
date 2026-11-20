// SPDX-License-Identifier: MIT
// Independent fixed-offset little-endian C peer; no IOKit/Mesa runtime.
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "build34_exact_receipt_wire.h"

static void put32(uint8_t *p, uint32_t value)
{
    for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(value>>(8*i));
}
static void put64(uint8_t *p, uint64_t value)
{
    for (unsigned i=0;i<8;i++) p[i]=(uint8_t)(value>>(8*i));
}
void phx34_receipt_encode(uint8_t *p,uint64_t owner,uint64_t serial,uint64_t sequence,
                          uint64_t generation,uint32_t slot,uint32_t queue,uint64_t timeout)
{
    memset(p,0,64);
    put32(p,1); put32(p+4,64); put64(p+8,owner); put64(p+16,serial);
    put64(p+24,sequence); put64(p+32,generation); put32(p+40,slot);
    put32(p+44,queue); put64(p+48,timeout);
}
bool phx34_receipt_reply(const uint8_t *reply,const uint8_t *request,uint32_t status)
{
    uint8_t expected[64]={0};
    put32(expected,1); put32(expected+4,64); put32(expected+8,status);
    memcpy(expected+16,request+8,32); memcpy(expected+48,request+40,8);
    return memcmp(reply,expected,64)==0;
}
