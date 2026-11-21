# SPDX-License-Identifier: MIT
"""Derive per-command MES status slots for the checked build34 bootstrap."""

from build34_exact_bootstrap_progress import change, stage_bootstrap as previous_bootstrap


SUBMIT = 'static int mes_submit('


def stage_bootstrap(source):
    return change(previous_bootstrap(source), SUBMIT,
                  ('   uint64_t status_va = VA(SCH_WB + 64);\n'
                   '   for (int i = 0; i < 4; i++) vw(SCH_WB + 64 + i * 4, 0);',
                   '''   uint64_t status = SCH_WB + 64;
   if (phx34CheckedBoot) {
      // sched_init cleared these four slots. Stop before the contexts at +128.
      // Never clear or reuse a slot after MES has started consuming the ring.
      if (sch_seq >= 4) return 1;
      status += sch_seq * 16;
      for (unsigned i = 0; i < 4; ++i) if (vr(status + i * 4)) return 1;
   } else {
      for (int i = 0; i < 4; i++) vw(status + i * 4, 0);
   }
   const uint64_t status_va = VA(status);'''),
                  ('   const struct MES_API_STATUS status = {status_va, 1};\n'
                   '   memcpy((char *)pkt + api_status_off, &status, sizeof(status));',
                   '   const struct MES_API_STATUS completion = {status_va, 1};\n'
                   '   memcpy((char *)pkt + api_status_off, &completion, sizeof(completion));'),
                  ('   if (phx34CheckedBoot && (vr(SCH_WB + 32) != (uint32_t)(sch_seq - 1) || vr(SCH_WB + 64) != 0)) return 1;',
                   '   if (phx34CheckedBoot) {\n'
                   '      if (vr(SCH_WB + 32) != (uint32_t)(sch_seq - 1)) return 1;\n'
                   '      for (unsigned i = 0; i < 4; ++i) if (vr(status + i * 4)) return 1;\n'
                   '   }'),
                  ('   uint32_t f = vr(SCH_WB + 32), st = vr(SCH_WB + 64);\n'
                   '   printf("mes %s: fence=%u (want %llu) status=%u -> %s\\n", what, f, (unsigned long long)sch_seq, st, '
                   '(f == sch_seq && st && (!phx34CheckedBoot || reached)) ? "OK" : "TIMEOUT");\n'
                   '   return !(f == sch_seq && st && (!phx34CheckedBoot || reached));',
                   '   uint32_t f = vr(SCH_WB + 32), st = vr(status);\n'
                   '   const bool complete = f == sch_seq && (phx34CheckedBoot ? reached && st == 1u : st != 0);\n'
                   '   printf("mes %s: fence=%u (want %llu) status=%u -> %s\\n", what, f, (unsigned long long)sch_seq, st, '
                   'complete ? "OK" : "TIMEOUT");\n'
                   '   return !complete;'))
