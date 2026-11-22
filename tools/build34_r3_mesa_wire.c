// SPDX-License-Identifier: MIT
#include "build34_r3_mesa_wire.h"
#include "build34_exact_submit_wire.h"

#include <errno.h>
#include <string.h>

_Static_assert(N48N_ABI_VERSION == PHXN_ABI_VERSION && N48N_MAX_IBS == PHXN_MAX_IBS &&
               N48N_WAIT_CAP_NS == PHXN_WAIT_CAP_NS, "submit/wait limits differ");
_Static_assert(sizeof(struct n48n_cs_in) == sizeof(struct phxn_cs_in) &&
               sizeof(struct n48n_cs_ib) == sizeof(struct phxn_cs_ib), "submit element sizes differ");

#define SAME_OFFSET(mesa, native, field) \
   _Static_assert(offsetof(struct mesa, field) == offsetof(struct native, field), #field " offset differs")
SAME_OFFSET(n48n_cs_in, phxn_cs_in, abi);
SAME_OFFSET(n48n_cs_in, phxn_cs_in, ctx_id);
SAME_OFFSET(n48n_cs_in, phxn_cs_in, num_ibs);
SAME_OFFSET(n48n_cs_in, phxn_cs_in, flags);
SAME_OFFSET(n48n_cs_in, phxn_cs_in, fence_handle);
SAME_OFFSET(n48n_cs_in, phxn_cs_in, fence_offset);
SAME_OFFSET(n48n_cs_in, phxn_cs_in, reserved);
SAME_OFFSET(n48n_cs_ib, phxn_cs_ib, _pad);
SAME_OFFSET(n48n_cs_ib, phxn_cs_ib, flags);
SAME_OFFSET(n48n_cs_ib, phxn_cs_ib, va_start);
SAME_OFFSET(n48n_cs_ib, phxn_cs_ib, ib_bytes);
SAME_OFFSET(n48n_cs_ib, phxn_cs_ib, ip_type);
SAME_OFFSET(n48n_cs_ib, phxn_cs_ib, ip_instance);
SAME_OFFSET(n48n_cs_ib, phxn_cs_ib, ring);
#undef SAME_OFFSET

static bool
valid_id(uint64_t value)
{
   return value && value != UINT64_MAX;
}

static bool
valid_receipt(uint64_t owner, const struct acd_exact_receipt *receipt)
{
   return receipt->owner == owner && valid_id(receipt->sequence) && valid_id(receipt->serial) &&
          valid_id(receipt->generation) && receipt->slot < 64 && receipt->queue < 2;
}

static int
wire_call(const struct phx34_mesa_wire *wire, uint32_t selector, const void *input, size_t input_size,
          struct phx34_r3_reply *reply, struct acd_exact_receipt *decoded, bool *no_dispatch)
{
   size_t output_size = sizeof(*reply);
   memset(reply, 0, sizeof(*reply));
   int result = wire->call(wire->ctx, selector, input, input_size, reply, &output_size);
   if (result) {
      if ((uint32_t)result == ACD_KR_BUSY && selector == PHX34_R3_SEL_ACK_RECEIPT)
         return -EBUSY;
      if (no_dispatch && ((uint32_t)result == ACD_KR_BUSY || (uint32_t)result == ACD_KR_NO_RESOURCES)) {
         *no_dispatch = true;
         return -EAGAIN;
      }
      int error = acd_kr_to_errno(selector, result);
      return error == -EBUSY ? -EIO : error;
   }
   if (output_size != sizeof(*reply) || reply->version != PHX34_R3_WIRE_VERSION ||
       reply->size != sizeof(*reply) || reply->reserved0 || reply->reserved)
      return -EPROTO;
   *decoded = (struct acd_exact_receipt){.owner = reply->owner, .serial = reply->serial,
      .sequence = reply->sequence, .generation = reply->generation, .slot = reply->slot, .queue = reply->queue};
   return valid_receipt(wire->owner, decoded) ? 0 : -EPROTO;
}

static int
wire_submit(void *context, const void *packet, size_t size, struct acd_exact_receipt *out, bool *no_dispatch)
{
   const struct phx34_mesa_wire *wire = context;
   struct phx34_r3_submit_request request = {.version = PHX34_R3_WIRE_VERSION,
      .size = sizeof(request), .owner = wire->owner};
   *no_dispatch = true;
   if (!packet || size < sizeof(request.submit) || size > sizeof(request.submit) + sizeof(request.ibs))
      return -EINVAL;
   memcpy(&request.submit, packet, sizeof(request.submit));
   if (request.submit.abi != PHXN_ABI_VERSION || request.submit.reserved ||
       !request.submit.num_ibs || request.submit.num_ibs > PHXN_MAX_IBS ||
       size != sizeof(request.submit) + request.submit.num_ibs * sizeof(request.ibs[0]))
      return -EINVAL;
   if (request.submit.flags || request.submit.fence_handle || request.submit.fence_offset)
      return -EOPNOTSUPP;
   memcpy(request.ibs, (const unsigned char *)packet + sizeof(request.submit), size - sizeof(request.submit));

   struct phx34_r3_reply reply;
   struct acd_exact_receipt receipt;
   *no_dispatch = false;
   int result = wire_call(wire, PHX34_R3_SEL_SUBMIT_RECEIPT, &request, sizeof(request), &reply, &receipt, no_dispatch);
   if (result)
      return result;
   if (reply.status != PHX34_R3_REPLY_SUBMITTED)
      return -EPROTO;
   *out = receipt;
   return 0;
}

static int
wire_receipt(const struct phx34_mesa_wire *wire, uint32_t selector, const struct acd_exact_receipt *receipt,
             uint64_t timeout_ns, struct phx34_r3_reply *reply)
{
   if (!valid_receipt(wire->owner, receipt) || timeout_ns > PHXN_WAIT_CAP_NS)
      return -EINVAL;
   const struct phx34_r3_request request = {.version = PHX34_R3_WIRE_VERSION, .size = sizeof(request),
      .owner = receipt->owner, .serial = receipt->serial, .sequence = receipt->sequence,
      .generation = receipt->generation, .slot = receipt->slot, .queue = receipt->queue, .timeout_ns = timeout_ns};
   struct acd_exact_receipt echo;
   int result = wire_call(wire, selector, &request, sizeof(request), reply, &echo, NULL);
   if (result)
      return result;
   if (echo.serial != receipt->serial || echo.sequence != receipt->sequence ||
       echo.generation != receipt->generation || echo.slot != receipt->slot || echo.queue != receipt->queue)
      return -EPROTO;
   return 0;
}

static int
wire_prefix(void *context, uint64_t target, uint64_t timeout_ns, struct acd_exact_snapshot *out)
{
   const struct phx34_mesa_wire *wire = context;
   if (target == UINT64_MAX || timeout_ns > PHXN_WAIT_CAP_NS || (!target && timeout_ns))
      return -EINVAL;
   struct acd_exact_snapshot snapshot = {0};
   int result = wire->wait_prefix(wire->ctx, target, timeout_ns, &snapshot);
   if (result)
      return result;
   if (snapshot.owner != wire->owner || snapshot.retired == UINT64_MAX)
      return -EPROTO;
   *out = snapshot;
   return 0;
}

static int
wire_wait(void *context, const struct acd_exact_receipt *receipt, uint64_t timeout_ns,
          bool *busy, struct acd_exact_snapshot *out)
{
   struct phx34_r3_reply reply;
   int result = wire_receipt(context, PHX34_R3_SEL_WAIT_RECEIPT, receipt, timeout_ns, &reply);
   if (result)
      return result;
   if (reply.status != PHX34_R3_REPLY_COMPLETE && reply.status != PHX34_R3_REPLY_PENDING)
      return -EPROTO;
   result = wire_prefix(context, 0, 0, out);
   if (result)
      return result;
   *busy = reply.status == PHX34_R3_REPLY_PENDING;
   return 0;
}

static int
wire_ack(void *context, const struct acd_exact_receipt *receipt)
{
   struct phx34_r3_reply reply;
   int result = wire_receipt(context, PHX34_R3_SEL_ACK_RECEIPT, receipt, 0, &reply);
   if (result)
      return result;
   return reply.status == PHX34_R3_REPLY_ACKED ? 0 : -EPROTO;
}

int
phx34_mesa_wire_backend(struct phx34_mesa_wire *wire, struct acd_exact_backend *out)
{
   if (!wire || !out || !valid_id(wire->owner) || !wire->call || !wire->wait_prefix)
      return -EINVAL;
   *out = (struct acd_exact_backend){.ctx = wire, .owner = wire->owner, .submit = wire_submit,
      .wait = wire_wait, .ack = wire_ack, .wait_prefix = wire_prefix};
   return 0;
}
