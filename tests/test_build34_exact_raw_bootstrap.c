/* SPDX-License-Identifier: MIT
 * Actual main, adoption blocks and deferred handoff helper. All setup and IOKit
 * calls below are CPU trace doubles; never a boot/GPU/IOKit execution test.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdbool.h>
static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"failed %d: %s\n",__LINE__,#x); exit(86); } } while(0)
static int quiet_printf(const char *format,...){(void)format;return 0;}
#define printf quiet_printf
typedef int kern_return_t;
static int conn;
#define SEL_DBG_ADOPTQ 112
#define CMP_RING 0x2540000ull
#define CMP_WB 0x2541000ull
#define GFX_RING 0x2570000ull
#define GFX_RDW 2048u
#define GFX_WB 0x2574000ull
#define GFX_DB 0x116u
#define VRAM_MC 0x8000000000ull
#define FB_PA 0
#define SCH_WB 0
static uint64_t sch_wptr,sch_seq;
static int use_mc,use_db,skip_hqd;
static struct {struct {uint64_t bytes,aperture;}geometry;uint64_t tablePhysical,defaultPhysical,tmrPhysical;unsigned systemHigh;}phx34_live;
static unsigned cs,gfx,adopt_compute,adopt_gfx,raw_count,raw_after_handoff,calls,fail_call,accepted;
static uint64_t recorded[2][6];
static int open_kext(void){return 0;} /* CPU only, does not open anything */
static int IOServiceClose(int ignored){(void)ignored;return 0;}
static int env_on(const char *s){if(!strcmp(s,"MESBOOT_CS"))return cs;if(!strcmp(s,"MESBOOT_GFX"))return gfx;if(!strcmp(s,"ADOPT"))return adopt_compute;if(!strcmp(s,"ADOPT_GFX"))return adopt_gfx;return 0;}
static kern_return_t IOConnectCallScalarMethod(int c,unsigned selector,const uint64_t *in,unsigned n,void *out,void *count){
    (void)c;(void)out;(void)count;CHECK(selector==SEL_DBG_ADOPTQ&&n==6);++calls;
    if(calls==fail_call)return 5;
    unsigned qi=in[5]&1u;CHECK(!(accepted&(1u<<qi)));memcpy(recorded[qi],in,sizeof(recorded[qi]));accepted|=1u<<qi;return 0;
}
// PHX34_BOOTSTRAP_HELPERS
static void raw_action(void){++raw_count;if(accepted)++raw_after_handoff;}
static void compute_via_mes(void){
    raw_action();
// PHX34_COMPUTE_ADOPTION
}
static void gfx_via_mes(void){
    unsigned w=55;raw_action();
// PHX34_GFX_ADOPTION
}
static void sched_test(void){
    raw_action();
// PHX34_SCHED_TAIL
}
static void kiq_init_only(void){raw_action();}
static void mesdump(void){}static void gart(void){raw_action();}static void mes_start(void){raw_action();}
static void kiq_test(void){raw_action();}static void sdma_sys_test(void){raw_action();}static void kiqreg_test(void){raw_action();}static void mec_test(void){raw_action();}
static unsigned vr(uint64_t a){(void)a;return 0;}
static int db(uint64_t a,uint64_t b){(void)a;(void)b;raw_action();return 0;}
// PHX34_MAIN
static void reset(void){
    cs=gfx=adopt_compute=adopt_gfx=1;raw_count=raw_after_handoff=calls=fail_call=accepted=0;
    use_mc=use_db=skip_hqd=0;memset(recorded,0,sizeof(recorded));
    phx34AdoptionPending=phx34AdoptionFault=0;memset(phx34Adoption,0,sizeof(phx34Adoption));
}
static int call(const char *s){char app[]="mesboot";char name[32];snprintf(name,sizeof(name),"%s",s);char *argv[]={app,name,NULL};return mesboot_main(2,argv);}
int main(int argc,char **argv){
    (void)argv;reset();
    if(argc>1){CHECK(call("kiqsched")==0&&calls==2&&accepted==3&&raw_after_handoff>0);puts("PASS prior bootstrap has raw GFX setup after compute adoption; GPU_executed=false");return 0;}
    CHECK(call("kiqsched")==0&&calls==2&&accepted==3&&raw_count==4&&!raw_after_handoff&&!phx34AdoptionPending);
    CHECK(recorded[0][0]==CMP_RING&&recorded[0][1]==1024&&recorded[0][2]==CMP_WB&&recorded[0][3]==24&&recorded[0][4]==8&&recorded[0][5]==0x2550000);
    CHECK(recorded[1][0]==GFX_RING&&recorded[1][1]==GFX_RDW&&recorded[1][2]==GFX_WB&&recorded[1][3]==GFX_DB*4&&recorded[1][4]==55&&recorded[1][5]==0x2580001);
    CHECK(phx34CommitAdoptions()==0&&calls==2); /* completed metadata never resubmits */
    reset();gfx=adopt_gfx=0;CHECK(call("sched")==0&&calls==1&&accepted==1&&!raw_after_handoff);
    reset();cs=adopt_compute=0;CHECK(call("gfx")==0&&calls==1&&accepted==2&&!raw_after_handoff);
    reset();adopt_compute=adopt_gfx=0;CHECK(call("kiqsched")==0&&!calls&&!accepted&&!raw_after_handoff);
    for(unsigned failure=1;failure<=2;++failure){
        reset();fail_call=failure;CHECK(call("kiqsched")==74&&calls==failure&&!raw_after_handoff&&phx34AdoptionFault);
        CHECK(accepted==(failure==1?0u:1u));CHECK(phx34CommitAdoptions()==74&&calls==failure);
    }
    reset();uint64_t in[6]={0x2540000,1024,0x2541000,24,8,0x2550000};
    phx34DeferAdoption(in);in[0]=123;CHECK(!calls&&phx34Adoption[0][0]==0x2540000);
    phx34DeferAdoption(in);CHECK(phx34AdoptionFault&&phx34CommitAdoptions()==74&&!calls);
    reset();CHECK(phx34CommitAdoptions()==0&&!calls);
    printf("ignored");
#undef printf
    printf("PASS deferred bootstrap: %u checks; actual main and adoption blocks; GPU_executed=false\n",checks);
}
