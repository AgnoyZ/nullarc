#pragma once

#include "build34_dcn_native_submit.h"

struct build34_dcn_part_target {
   const void *image, *view, *memory, *host;
   uint64_t import_bytes, bind_bytes, pitch;
   uint32_t width, height;
};

struct build34_dcn_part_writer {
   struct build34_dcn_native_submit native;
   uint64_t recording, map_generation, phx_va, page_bytes;
   uint32_t bo_handle;
};
