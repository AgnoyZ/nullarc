# SPDX-License-Identifier: MIT
"""Derive a checked mesboot pair without changing the production boot path."""

from build34_exact_raw_handoff import stage_bootstrap as prior_bootstrap
from build34_exact_submit import once
from test_build34_exact_ownership import method


def change(source, signature, *replacements):
    original = method(source, signature)
    updated = original
    for old, new in replacements:
        updated = once(updated, old, new)
    return once(source, original, updated)


def check_sentinel(source, signature, scratch, target, marker, writeback):
    ready = f'rd({scratch}) == 0xDEADBEEF && vr({target}) == {marker}'
    return change(source, signature,
                  (writeback, f'   if (phx34CheckedBoot && (rd({scratch}) != 0xCAFEDEAD || vr({target}) != 0)) return;\n'
                   + writeback),
                  (f'   for (int i = 0; i < 50; i++) {{ usleep(10000); if ({ready}) break; }}',
                   '   bool reached = false;\n'
                   f'   for (int i = 0; i < 50; i++) {{ usleep(10000); if ({ready}) {{ reached = true; break; }} }}'),
                  ('      phx34DeferAdoption(in);',
                   '      if (phx34CheckedBoot && !reached) return;\n      phx34DeferAdoption(in);'))


def stage_bootstrap(source):
    source = prior_bootstrap(source)
    source = once(source, 'static unsigned phx34AdoptionPending, phx34AdoptionFault;\n',
                  'static unsigned phx34AdoptionPending, phx34AdoptionFault;\nstatic bool phx34CheckedBoot;\n')
    source = change(source, 'static int phx34CommitAdoptions(',
                    ('   if (phx34AdoptionFault) return 74;',
                     '   if (phx34AdoptionFault || (phx34CheckedBoot && phx34AdoptionPending != 3u)) return 74;'))
    source = change(source, 'static int mes_submit(',
                    ('   *(uint64_t *)((char *)pkt + api_status_off) = status_va;\n'
                     '   *(uint64_t *)((char *)pkt + api_status_off + 8) = 1;',
                     '   // MES packets are packed on four-byte boundaries.\n'
                     '   const struct MES_API_STATUS status = {status_va, 1};\n'
                     '   memcpy((char *)pkt + api_status_off, &status, sizeof(status));'),
                    ('   vw(SCH_WB + 16, sch_wptr);',
                     '   // MES can poll the write pointer before the doorbell.\n'
                     '   if (phx34CheckedBoot && (vr(SCH_WB + 32) != (uint32_t)(sch_seq - 1) || vr(SCH_WB + 64) != 0)) return 1;\n'
                     '   vw(SCH_WB + 16, sch_wptr);'),
                    ('   for (int t = 0; t < 400; t++) {',
                     '   bool reached = false;\n   for (int t = 0; t < 400; t++) {'),
                    ('      if (vr(SCH_WB + 32) == (uint32_t)sch_seq) break;',
                     '      if (vr(SCH_WB + 32) == (uint32_t)sch_seq) { reached = true; break; }'),
                    ('   return !(f == sch_seq && st);',
                     '   return !(f == sch_seq && st && (!phx34CheckedBoot || reached));'),
                    ('(f == sch_seq && st) ? "OK" : "TIMEOUT"',
                     '(f == sch_seq && st && (!phx34CheckedBoot || reached)) ? "OK" : "TIMEOUT"'))
    source = check_sentinel(source, 'static void compute_via_mes(', 'SEG1(0x2040)', 'TESTBUF', '0xFEEDF00D',
                            '   vw(CMP_WB + 16, 8); vw(CMP_WB + 20, 0);')
    source = check_sentinel(source, 'static void gfx_via_mes(void)\n', 'SEG1(0x2041)', 'TESTBUF + 0x40',
                            '0x6F7A6F7A', '   vw(GFX_WB + 16, w); vw(GFX_WB + 20, 0);')
    source = change(source, 'static void sched_test(void)\n',
                    ('   mes_submit(&r, sizeof(r), offsetof(union MESAPI_SET_HW_RESOURCES, api_status), "SET_HW_RESOURCES");',
                     '   if (mes_submit(&r, sizeof(r), offsetof(union MESAPI_SET_HW_RESOURCES, api_status), "SET_HW_RESOURCES") && phx34CheckedBoot) return;'),
                    ('   mes_submit(&q, sizeof(q), offsetof(union MESAPI__QUERY_MES_STATUS, api_status), "QUERY_SCHED_STATUS");',
                     '   if (mes_submit(&q, sizeof(q), offsetof(union MESAPI__QUERY_MES_STATUS, api_status), "QUERY_SCHED_STATUS") && phx34CheckedBoot) return;'),
                    ('   if (env_on("MESBOOT_GFX")) gfx_via_mes();',
                     '   if (phx34CheckedBoot && (phx34AdoptionFault || phx34AdoptionPending != 1u)) return;\n'
                     '   if (env_on("MESBOOT_GFX")) gfx_via_mes();'))
    return change(source, 'int main(',
                  ('   if (open_kext()) return 1;',
                   '   if (env_on("ADOPT") || env_on("ADOPT_GFX")) {\n'
                   '      if (argc != 2 || strcmp(argv[1], "kiqsched") || !env_on("ADOPT") || !env_on("ADOPT_GFX") ||\n'
                   '          !env_on("MESBOOT_CS") || !env_on("MESBOOT_GFX") || !getenv("MESBOOT_MC") ||\n'
                   '          *getenv("MESBOOT_MC") != \'1\' || env_on("NO_CSB")) return 74;\n'
                   '      phx34CheckedBoot = true;\n'
                   '   }\n   if (open_kext()) return 1;'))
