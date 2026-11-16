/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * Isolated user-helper experiment; not a kernel or desktop acceptance result.
 * Register values/order reference nullarc PR #14 at
 * 9f37791bb816092df580f3cb62a9db1e2357fb8f. Implementation is downstream.
 * Include after the pinned helper's checked wr()/rd() and before sched_test().
 */
#ifndef PHX_MEC_DOORBELL_RANGE_TRIAL_H
#define PHX_MEC_DOORBELL_RANGE_TRIAL_H
#ifndef PHX34_MEC_RANGE_TRIAL
#error "Choose PHX34_MEC_RANGE_TRIAL=0 (control) or 1 (range trial) explicitly"
#endif
#if PHX34_MEC_RANGE_TRIAL != 0 && PHX34_MEC_RANGE_TRIAL != 1
#error "PHX34_MEC_RANGE_TRIAL must be 0 or 1"
#endif

static void phx34_mec_range_init(void)
{
#if PHX34_MEC_RANGE_TRIAL
   /* Dword register offsets; the range values are byte offsets, not doorbell indices.
    * Upper first, then lower, as in the reviewed PR. No queue submission between them.
    * Failure is terminal; do not attempt live rollback of partially changed GPU state.
    */
   const uint32_t range[][2] = {{SEG0(0x1dfd), 0x450}, {SEG0(0x1dfc), 0}};
   for (unsigned i = 0; i < sizeof(range) / sizeof(range[0]); ++i) {
      const uint32_t immediate = wr(range[i][0], range[i][1]);
      if (immediate != range[i][1]) {
         fprintf(stderr, "mec-range trial: step=%u register=0x%08x requested=0x%08x write-readback=0x%08x; stopping\n",
                 i + 1, range[i][0], range[i][1], immediate);
         exit(75);
      }
      const uint32_t observed = rd(range[i][0]);
      if (observed != range[i][1]) {
         fprintf(stderr, "mec-range trial: step=%u register=0x%08x requested=0x%08x readback=0x%08x; stopping\n",
                 i + 1, range[i][0], range[i][1], observed);
         exit(75);
      }
   }
#endif
}
#endif
