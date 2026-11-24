#include <assert.h>
#include "build34_dcn_radv_clear.h"

static const int stream, alternate_stream, view, alternate_view, bo, alternate_bo;
static const struct radv_dcn_render_binding binding = {.map = {.generation = 8, .handle = 12}, .width = 64};

static void
assert_refused(struct radv_dcn_recorded_clear clear)
{
   assert(clear.phase == RADV_DCN_CLEAR_REJECTED && clear.serial == 0);
   assert(!clear.view && !clear.stream && !clear.bo && !clear.binding.map.generation);
}

int main(void)
{
   struct radv_dcn_recorded_clear clear = {0};
   radv_dcn_clear_close(&clear, &stream, &view, &bo, 8);
   radv_dcn_clear_finalize(&clear, &stream, 1);
   assert(clear.phase == RADV_DCN_CLEAR_EMPTY && !clear.serial);
   radv_dcn_clear_record(&clear, binding, &stream, &view, &bo);
   assert(clear.phase == RADV_DCN_CLEAR_OPEN && !clear.serial);
   assert(clear.binding.map.handle == 12 && clear.binding.width == 64 && clear.bo == &bo);
   radv_dcn_clear_close(&clear, &stream, &view, &bo, 8);
   assert(clear.phase == RADV_DCN_CLEAR_CLOSED && !clear.serial);
   radv_dcn_clear_finalize(&clear, &stream, UINT64_MAX);
   assert(clear.phase == RADV_DCN_CLEAR_CLOSED && clear.serial == UINT64_MAX);

   radv_dcn_clear_finalize(&clear, &stream, 1);
   assert_refused(clear);

   for (unsigned test = 0; test < 11; ++test) {
      clear = (struct radv_dcn_recorded_clear){0};
      const struct radv_dcn_render_binding actual = test == 0 ? (struct radv_dcn_render_binding){0} : binding;
      radv_dcn_clear_record(&clear, actual, test == 1 ? 0 : &stream, test == 2 ? 0 : &view, test == 3 ? 0 : &bo);
      if (test == 4)
         radv_dcn_clear_reject(&clear);
      if (test == 5)
         radv_dcn_clear_record(&clear, binding, &stream, &view, &bo);
      if (test != 6)
         radv_dcn_clear_close(&clear, test == 7 ? &alternate_stream : &stream,
                              test == 8 ? &alternate_view : &view, test == 9 ? &alternate_bo : &bo,
                              test == 10 ? 9 : 8);
      radv_dcn_clear_finalize(&clear, &stream, 1);
      assert_refused(clear);
   }

   for (unsigned test = 0; test < 3; ++test) {
      clear = (struct radv_dcn_recorded_clear){0};
      radv_dcn_clear_record(&clear, binding, &stream, &view, &bo);
      radv_dcn_clear_close(&clear, &stream, &view, &bo, 8);
      if (test == 0)
         radv_dcn_clear_record(&clear, binding, &stream, &view, &bo);
      radv_dcn_clear_finalize(&clear, test == 1 ? &alternate_stream : &stream, test == 2 ? 0 : 1);
      assert_refused(clear);
   }
   return 0;
}
