#pragma once

#include "build34_dcn_radv_binding.h"

enum radv_dcn_clear_phase {
   RADV_DCN_CLEAR_EMPTY,
   RADV_DCN_CLEAR_OPEN,
   RADV_DCN_CLEAR_CLOSED,
   RADV_DCN_CLEAR_REJECTED,
};

struct radv_dcn_recorded_clear {
   struct radv_dcn_render_binding binding;
   const void *stream;
   const void *view;
   const void *bo;
   uint64_t serial;
   enum radv_dcn_clear_phase phase;
};

static inline void
radv_dcn_clear_reject(struct radv_dcn_recorded_clear *clear)
{
   *clear = (struct radv_dcn_recorded_clear){.phase = RADV_DCN_CLEAR_REJECTED};
}

static inline void
radv_dcn_clear_record(struct radv_dcn_recorded_clear *clear, struct radv_dcn_render_binding binding,
                      const void *stream, const void *view, const void *bo)
{
   if (clear->phase != RADV_DCN_CLEAR_EMPTY || !binding.map.generation || !stream || !view || !bo) {
      radv_dcn_clear_reject(clear);
      return;
   }
   *clear = (struct radv_dcn_recorded_clear){binding, stream, view, bo, 0, RADV_DCN_CLEAR_OPEN};
}

static inline void
radv_dcn_clear_close(struct radv_dcn_recorded_clear *clear, const void *stream, const void *view, const void *bo,
                     uint64_t generation)
{
   if (clear->phase != RADV_DCN_CLEAR_OPEN)
      return;
   if (stream != clear->stream || view != clear->view || bo != clear->bo || generation != clear->binding.map.generation) {
      radv_dcn_clear_reject(clear);
      return;
   }
   clear->phase = RADV_DCN_CLEAR_CLOSED;
}

static inline void
radv_dcn_clear_finalize(struct radv_dcn_recorded_clear *clear, const void *stream, uint64_t serial)
{
   if (clear->phase == RADV_DCN_CLEAR_EMPTY)
      return;
   if (clear->phase != RADV_DCN_CLEAR_CLOSED || stream != clear->stream || !serial || clear->serial) {
      radv_dcn_clear_reject(clear);
      return;
   }
   clear->serial = serial;
}
