#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include "build34_r3_mesa_wire.h"
#include "build34_exact_progress_wire.h"
#include "build34_dcn_writer_wire.h"
#ifdef TEST_PRESENT_OFFER
#include "build34_dcn_present_wire.h"
#endif

uint64_t acd_kext_now_ns(struct acd_kext *transport)
{
   assert(transport);
   return 0;
}

int acd_kr_to_errno(uint32_t selector, int result)
{
   assert(selector && result);
   return -EIO;
}

#include "staged_exact_complete.inc"

static const struct build34_dcn_writer_nomination candidate = {{0x20000, 32, 0}, {0x30000, 8192, 9, 0}};

struct peer {
   uint32_t flags, prefix_flags;
   uint64_t sequence, retired;
   unsigned short_submits, extended_submits, dispatches, waits, acks;
   bool accept, busy, ack_busy, full_once, raw_failure, bad_queue, bad_full;
#ifdef TEST_PRESENT_OFFER
   unsigned offers;
#endif
};

static int peer_call(void *context, uint32_t selector, const void *input, size_t input_size,
                     void *output, size_t *output_size)
{
   struct peer *peer = context;
   const uint64_t owner = 19, generation = 23;
   if (selector == PHX34_R3_SEL_SESSION || selector == PHX34_R3_SEL_PREFIX) {
      const struct phx34_r3_progress_request *request = input;
      assert(input_size == sizeof(*request) && request->size == input_size);
      assert(request->owner == (selector == PHX34_R3_SEL_SESSION ? 0 : owner));
      assert(request->version == PHX34_R3_WIRE_VERSION);
      assert(*output_size == sizeof(struct phx34_r3_progress_reply));
      *(struct phx34_r3_progress_reply *)output = (struct phx34_r3_progress_reply){
         .version = PHX34_R3_WIRE_VERSION, .size = *output_size, .owner = owner,
         .build = PHX34_R3_PROGRESS_BUILD, .target = request->target, .retired = peer->retired,
         .flags = selector == PHX34_R3_SEL_SESSION ? peer->flags : peer->prefix_flags,
      };
      return 0;
   }

#ifdef TEST_PRESENT_OFFER
   if (selector == BUILD34_DCN_SEL_OFFER) {
      const struct build34_dcn_present_offer *offer = input;
      assert(peer->flags == PHX34_R3_DCN_PRESENT_FLAGS && !output && !output_size && input_size == sizeof(*offer));
      assert(offer->surface == 17 && offer->native.owner == owner && offer->native.sequence == peer->sequence);
      assert(!memcmp(&offer->range, &candidate.range, sizeof(offer->range)));
      ++peer->offers;
      return 0;
   }
#endif
   assert(*output_size == sizeof(struct phx34_r3_reply));
   struct phx34_r3_reply *reply = output;
   *reply = (struct phx34_r3_reply){.version = PHX34_R3_WIRE_VERSION, .size = sizeof(*reply), .owner = owner};
   if (selector == PHX34_R3_SEL_SUBMIT_RECEIPT) {
      const struct phx34_r3_submit_request *request = input;
      assert(request->size == input_size && request->version == PHX34_R3_WIRE_VERSION && request->owner == owner);
      assert(!request->reserved[0] && !request->reserved[1] && request->submit.ctx_id == 17 && request->submit.num_ibs == 1);
      const bool extended = input_size == sizeof(struct build34_dcn_writer_request);
      if (extended) {
         const struct build34_dcn_writer_request *envelope = input;
         assert((peer->flags & PHX34_R3_CAP_DCN_WRITER) && build34_dcn_matches_writer_ib(request, &envelope->writer));
         assert(!memcmp(&envelope->writer, &candidate, sizeof(candidate)));
         ++peer->extended_submits;
      } else {
         assert(input_size == sizeof(*request));
         ++peer->short_submits;
      }
      if (peer->raw_failure)
         return (int)ACD_KR_BUSY;
      if (peer->full_once) {
         peer->full_once = false;
         reply->status = PHX34_R3_REPLY_RECEIPT_FULL;
         if (peer->bad_full)
            ++reply->owner;
         return 0;
      }
      ++peer->dispatches;
      reply->status = peer->accept ? PHX34_R3_REPLY_WRITER_SUBMITTED : PHX34_R3_REPLY_SUBMITTED;
      reply->serial = reply->sequence = ++peer->sequence;
      reply->generation = generation;
      reply->queue = peer->bad_queue ? 0 : 1;
      return 0;
   }

   const struct phx34_r3_request *receipt = input;
   assert(input_size == sizeof(*receipt) && receipt->size == input_size && receipt->owner == owner);
   assert(receipt->sequence && receipt->sequence <= peer->sequence && receipt->serial == receipt->sequence &&
          receipt->generation == generation && !receipt->slot && receipt->queue == 1);
   reply->serial = receipt->serial;
   reply->sequence = receipt->sequence;
   reply->generation = receipt->generation;
   reply->queue = receipt->queue;
   if (selector == PHX34_R3_SEL_WAIT_RECEIPT) {
      ++peer->waits;
      reply->status = peer->busy ? PHX34_R3_REPLY_PENDING : PHX34_R3_REPLY_COMPLETE;
   } else {
      assert(selector == PHX34_R3_SEL_ACK_RECEIPT && !receipt->timeout_ns);
      ++peer->acks;
      if (peer->ack_busy)
         return (int)ACD_KR_BUSY;
      reply->status = PHX34_R3_REPLY_ACKED;
   }
   return 0;
}

static struct phx34_mesa_wire wire_for(struct peer *peer)
{
   return (struct phx34_mesa_wire){.ctx = peer, .call = peer_call};
}

static void attach(struct acd_kext *transport, struct phx34_mesa_wire *wire)
{
   struct acd_exact_backend backend = {0};
   assert(!phx34_mesa_wire_backend(wire, &backend));
   assert((backend.submit_writer != NULL) == !!(wire->flags & PHX34_R3_CAP_DCN_WRITER));
   assert(!acd_kext_set_exact_backend(transport, &backend));
}

static void finish(struct acd_kext *transport)
{
   assert(!pthread_mutex_destroy(&transport->exact->submit_mtx));
   free(transport->exact);
   assert(!pthread_mutex_destroy(&transport->mtx));
}

static int nominate(struct acd_kext *transport, const struct build34_dcn_writer_nomination *writer,
                    struct build34_dcn_native_submit *out)
{
   struct n48n_cs_ib ib = {.ip_type = AMDGPU_HW_IP_GFX, .va_start = candidate.ib.va, .ib_bytes = candidate.ib.bytes};
   struct acd_exact_receipt receipt = {0};
   const struct acd_cs_plan plan = {.ctx_id = 17, .ibs = &ib, .n_ibs = 1, .receipt_out = &receipt, .dcn_nomination = writer};
   uint64_t sequence = 0;
   int result = acd_exact_submit(transport, transport->exact, &plan, &sequence);
   *out = (struct build34_dcn_native_submit){0};
   if (!result && receipt.sequence) {
      assert(receipt.sequence == sequence);
      *out = (struct build34_dcn_native_submit){receipt.sequence, receipt.owner, receipt.serial,
         receipt.generation, receipt.slot, receipt.queue, plan.ctx_id};
   }
   return result;
}

static void expect_poll(struct acd_kext *transport, const struct build34_dcn_native_submit *writer, int result, bool pending)
{
   bool busy = false;
   assert(acd_kext_dcn_poll(transport, writer, &busy) == result && busy == pending);
}

static void negotiated_writer(void)
{
   struct peer peer = {.flags = PHX34_R3_DCN_FLAGS, .prefix_flags = PHX34_R3_DCN_FLAGS, .accept = true};
   struct acd_kext transport = {.mtx = PTHREAD_MUTEX_INITIALIZER};
   struct phx34_mesa_wire wire = wire_for(&peer);
   attach(&transport, &wire);
   struct build34_dcn_native_submit writer;
   assert(!nominate(&transport, &candidate, &writer) && writer.sequence == 1 && writer.context == 17);
   assert(peer.extended_submits == 1 && !peer.short_submits && peer.dispatches == 1);

   peer.retired = writer.sequence;
   peer.ack_busy = true;
   bool busy = true;
   assert(!acd_exact_prefix(&transport, transport.exact, 0, 0, &busy, NULL) && !busy);
   assert(peer.acks == 1 && !peer.waits);
   transport.exact->dcn_writer->acknowledging = true;
   expect_poll(&transport, &writer, -EAGAIN, true);
   transport.exact->dcn_writer->acknowledging = false;
   peer.busy = true;
   expect_poll(&transport, &writer, 0, true);
   peer.busy = false;
   expect_poll(&transport, &writer, 0, false);
   expect_poll(&transport, &writer, 0, false);
   assert(peer.acks == 1 && peer.waits == 2);
   peer.ack_busy = false;
   assert(!acd_exact_prefix(&transport, transport.exact, 0, 0, &busy, NULL) && !busy);
   expect_poll(&transport, &writer, 0, false);
   assert(peer.acks == 2 && peer.waits == 2);

   struct build34_dcn_native_submit next;
   assert(!nominate(&transport, &candidate, &next) && next.sequence == 2);
   peer.full_once = true;
   assert(!nominate(&transport, &candidate, &next) && next.sequence == 3);
   assert(peer.extended_submits == 4 && !peer.short_submits && peer.dispatches == 3);
   assert(peer.acks == 3 && peer.waits == 3);
   expect_poll(&transport, &writer, -ENOENT, true);

   peer.accept = false;
   assert(!nominate(&transport, &candidate, &next) && !next.sequence);
   assert(peer.extended_submits == 5 && peer.dispatches == 4 && !transport.exact->dcn_writer);
   struct build34_dcn_writer_nomination malformed = candidate;
   ++malformed.range.bytes;
   assert(!nominate(&transport, &malformed, &next) && !next.sequence);
   assert(peer.extended_submits == 5 && peer.short_submits == 1 && peer.dispatches == 5);

   peer.prefix_flags = PHX34_R3_PRESSURE_FLAGS;
   assert(acd_exact_prefix(&transport, transport.exact, 0, 0, &busy, NULL) == -EPROTO);
   assert(transport.exact->poisoned);
   finish(&transport);
}

static void refusal_cases(void)
{
   for (unsigned fault = 0; fault < 5; ++fault) {
      struct peer peer = {.flags = PHX34_R3_DCN_FLAGS, .prefix_flags = PHX34_R3_DCN_FLAGS, .accept = true};
      if (fault < 2) {
         peer.flags = peer.prefix_flags = PHX34_R3_PRESSURE_FLAGS;
         peer.accept = fault == 1;
      }
      peer.bad_queue = fault == 2;
      peer.raw_failure = fault == 3;
      peer.full_once = peer.bad_full = fault == 4;
      struct acd_kext transport = {.mtx = PTHREAD_MUTEX_INITIALIZER};
      struct phx34_mesa_wire wire = wire_for(&peer);
      attach(&transport, &wire);
      struct build34_dcn_native_submit writer;
      const int expected = !fault ? 0 : fault == 3 ? -EIO : -EPROTO;
      assert(nominate(&transport, &candidate, &writer) == expected);
      assert(!writer.sequence && !transport.exact->dcn_writer);
      assert(peer.short_submits == (fault < 2) && peer.extended_submits == (fault >= 2));
      assert(peer.dispatches == (fault < 3));
      assert(transport.exact->poisoned == (fault != 0));
      finish(&transport);
   }
}

#ifdef TEST_PRESENT_OFFER
static void present_offer(void)
{
   struct peer peer = {.flags = PHX34_R3_DCN_PRESENT_FLAGS, .prefix_flags = PHX34_R3_DCN_PRESENT_FLAGS, .accept = true};
   struct acd_kext transport = {.mtx = PTHREAD_MUTEX_INITIALIZER};
   struct phx34_mesa_wire wire = wire_for(&peer);
   attach(&transport, &wire);
   struct build34_dcn_present_offer offer = {.version = BUILD34_DCN_PRESENT_VERSION, .size = sizeof(offer),
      .surface = 17, .range = candidate.range};
   assert(!nominate(&transport, &candidate, &offer.native));
   assert(acd_kext_dcn_offer(&transport, &offer) == -ENOENT && !peer.offers);
   expect_poll(&transport, &offer.native, 0, false);
   assert(!pthread_mutex_lock(&transport.exact->submit_mtx));
   assert(acd_kext_dcn_offer(&transport, &offer) == -EAGAIN && !peer.offers);
   assert(!pthread_mutex_unlock(&transport.exact->submit_mtx));
   assert(!acd_kext_dcn_offer(&transport, &offer) && peer.offers == 1);
   --offer.range.bytes;
   assert(acd_kext_dcn_offer(&transport, &offer) == -EINVAL && peer.offers == 1);
   ++offer.range.bytes;
   struct build34_dcn_native_submit replaced;
   assert(!nominate(&transport, &candidate, &replaced));
   assert(acd_kext_dcn_offer(&transport, &offer) == -ENOENT && peer.offers == 1);
   finish(&transport);
}
#endif

int main(void)
{
   struct peer unknown = {.flags = PHX34_R3_DCN_FLAGS | (1u << 5)};
   struct phx34_mesa_wire wire = wire_for(&unknown);
   struct acd_exact_backend backend = {0};
   assert(phx34_mesa_wire_backend(&wire, &backend) == -EPROTO && !wire.owner && !backend.submit_writer);
   negotiated_writer();
   refusal_cases();
#ifdef TEST_PRESENT_OFFER
   present_offer();
#endif
   return 0;
}
