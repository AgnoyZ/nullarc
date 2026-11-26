// nvmtl_upload_ring.h: bounded circular staging ring allocator for asynchronous texture uploads.
//
// Pure state machine so wrap-around, slot retirement, out-of-order completion, and full-ring
// reclamation invariants are unit-tested without a GPU. The Vulkan layer backs the ring with a
// single persistent HOST_VISIBLE|HOST_COHERENT GTT buffer and submits per-slot fences.

#ifndef NVMTL_UPLOAD_RING_H
#define NVMTL_UPLOAD_RING_H

#include <stddef.h>
#include <stdint.h>

#define NVMTL_UPRING_ALIGN     256u
#define NVMTL_UPRING_MAX_SLOTS 64u

typedef struct {
    uint8_t  in_use;
    uint8_t  done;
    size_t   offset;
    size_t   length;
    uint64_t seq;
    uint64_t tag;
} nvmtl_upring_slot;

typedef struct {
    size_t            capacity;
    size_t            head;
    size_t            tail;
    size_t            used;
    uint32_t          slot_head;
    uint32_t          slot_tail;
    uint32_t          slot_count;
    uint64_t          next_seq;
    nvmtl_upring_slot slots[NVMTL_UPRING_MAX_SLOTS];
} nvmtl_upring;

static inline size_t nvmtl_upring_align_up(size_t n)
{
    const size_t mask = (size_t)NVMTL_UPRING_ALIGN - 1u;
    if (n > SIZE_MAX - mask) return 0;
    return (n + mask) & ~mask;
}

static inline void nvmtl_upring_init(nvmtl_upring *r, size_t capacity)
{
    if (!r) return;
    r->capacity = capacity & ~((size_t)NVMTL_UPRING_ALIGN - 1u);
    r->head = 0;
    r->tail = 0;
    r->used = 0;
    r->slot_head = 0;
    r->slot_tail = 0;
    r->slot_count = 0;
    r->next_seq = 1;
    for (uint32_t i = 0; i < NVMTL_UPRING_MAX_SLOTS; i++) {
        r->slots[i].in_use = 0;
        r->slots[i].done = 0;
        r->slots[i].offset = 0;
        r->slots[i].length = 0;
        r->slots[i].seq = 0;
        r->slots[i].tag = 0;
    }
}

// Advance tail across any contiguous completed slots from the oldest end of the ring.
static inline void nvmtl_upring_advance_tail(nvmtl_upring *r)
{
    if (!r) return;
    while (r->slot_count > 0) {
        nvmtl_upring_slot *s = &r->slots[r->slot_tail];
        if (!s->done) break;
        r->tail = (s->offset + s->length) % r->capacity;
        r->used -= s->length;
        s->in_use = 0;
        s->done = 0;
        s->offset = 0;
        s->length = 0;
        s->seq = 0;
        s->tag = 0;
        r->slot_tail = (r->slot_tail + 1u) % NVMTL_UPRING_MAX_SLOTS;
        r->slot_count--;
    }
    if (r->slot_count == 0) {
        r->head = 0;
        r->tail = 0;
        r->used = 0;
    }
}

// Try to reserve a contiguous aligned range in the ring without blocking.
// Returns 0 on success (filling *out_slot, *out_offset, *out_seq), or -1 if the caller must
// reclaim the oldest in-flight slot first (or fall back if size > capacity).
static inline int nvmtl_upring_try_alloc(nvmtl_upring *r, size_t size, uint64_t tag,
                                         uint32_t *out_slot, size_t *out_offset, uint64_t *out_seq)
{
    if (!r || !size || !r->capacity || !out_slot || !out_offset || !out_seq) return -1;
    const size_t aligned = nvmtl_upring_align_up(size);
    if (!aligned || aligned > r->capacity) return -1;
    nvmtl_upring_advance_tail(r);
    if (r->slot_count >= NVMTL_UPRING_MAX_SLOTS) return -1;

    size_t offset = 0;
    size_t charge = aligned;
    if (r->slot_count == 0) {
        offset = 0;
        charge = aligned;
    } else if (r->head >= r->tail) {
        const size_t right_free = r->capacity - r->head;
        if (aligned <= right_free) {
            offset = r->head;
            charge = aligned;
        } else if (aligned <= r->tail) {
            // Wrap to offset 0; account the skipped tail-end pad inside this slot's charge
            // so r->used stays exact and tail advances cleanly on retirement.
            offset = 0;
            charge = right_free + aligned;
        } else {
            return -1;
        }
    } else {
        const size_t mid_free = r->tail - r->head;
        if (aligned <= mid_free) {
            offset = r->head;
            charge = aligned;
        } else {
            return -1;
        }
    }

    const uint32_t idx = r->slot_head;
    nvmtl_upring_slot *s = &r->slots[idx];
    s->in_use = 1;
    s->done = 0;
    s->offset = offset;
    s->length = charge;
    s->seq = r->next_seq++;
    s->tag = tag;
    r->head = (offset + aligned) % r->capacity;
    r->used += charge;
    r->slot_head = (r->slot_head + 1u) % NVMTL_UPRING_MAX_SLOTS;
    r->slot_count++;

    *out_slot = idx;
    *out_offset = offset;
    *out_seq = s->seq;
    return 0;
}

// Mark a previously allocated slot as completed and reclaim any contiguous completed prefix.
// Returns 1 if the slot matched and was marked done, 0 otherwise.
static inline int nvmtl_upring_mark_done(nvmtl_upring *r, uint32_t slot, uint64_t seq)
{
    if (!r || slot >= NVMTL_UPRING_MAX_SLOTS || !seq) return 0;
    nvmtl_upring_slot *s = &r->slots[slot];
    if (!s->in_use || s->seq != seq || s->done) return 0;
    s->done = 1;
    nvmtl_upring_advance_tail(r);
    return 1;
}

// Peek the oldest not-yet-done slot so the caller can wait on its fence outside the ring lock.
// Returns 1 if an active oldest slot exists, 0 if the ring is empty.
static inline int nvmtl_upring_oldest_active(nvmtl_upring *r, uint32_t *out_slot,
                                             uint64_t *out_seq, uint64_t *out_tag)
{
    if (!r) return 0;
    nvmtl_upring_advance_tail(r);
    if (r->slot_count == 0) return 0;
    const nvmtl_upring_slot *s = &r->slots[r->slot_tail];
    if (out_slot) *out_slot = r->slot_tail;
    if (out_seq) *out_seq = s->seq;
    if (out_tag) *out_tag = s->tag;
    return 1;
}

#endif
