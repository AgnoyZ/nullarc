// Downstream host-testable allocation policy. No hardware or IOKit access.
#ifndef PHX_BO_POLICY_HPP
#define PHX_BO_POLICY_HPP
#include <stdint.h>
namespace phx780m {
inline bool boPageSize(uint64_t requested, uint64_t *rounded) {
    if (!rounded || !requested || requested > UINT64_MAX - 4095) return false;
    *rounded = (requested + 4095) & ~uint64_t(4095);
    return true;
}
constexpr bool boBudgetFits(uint64_t used, uint64_t bytes, uint64_t budget) {
    return bytes != 0 && used <= budget && bytes <= budget - used;
}
}
#endif
