#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include "ac_darwin_kext.h"
#include "build34_dcn_native_submit.h"

uint64_t acd_kext_now_ns(struct acd_kext *transport)
{
   assert(transport);
   return 0;
}

#include "staged_exact_complete.inc"

struct backend_fixture {
   struct acd_kext *transport;
   struct build34_dcn_native_submit invalidate;
   struct acd_exact_receipt accepted;
   uint64_t retired;
   unsigned submits, waits, acks;
   int submit_error, wait_error;
   bool pending, wrong_owner;
};

static int backend_submit(void *context, const void *packet, size_t size,
                          struct acd_exact_receipt *out, bool *no_dispatch)
{
   struct backend_fixture *fixture = context;
   struct n48n_cs_in header;
   assert(size == sizeof(header) + sizeof(struct n48n_cs_ib));
   memcpy(&header, packet, sizeof(header));
   assert(header.ctx_id == 17 && header.num_ibs == 1 && !header.flags);
   ++fixture->submits;
   *no_dispatch = fixture->submit_error == -EINVAL;
   if (fixture->submit_error)
      return fixture->submit_error;
   *out = fixture->accepted;
   return 0;
}

static int backend_prefix(void *context, uint64_t sequence, uint64_t timeout, struct acd_exact_snapshot *out)
{
   struct backend_fixture *fixture = context;
   assert(!sequence && !timeout);
   *out = (struct acd_exact_snapshot){fixture->accepted.owner + fixture->wrong_owner, fixture->retired};
   return 0;
}

static int backend_wait(void *context, const struct acd_exact_receipt *writer, uint64_t timeout,
                        bool *busy, struct acd_exact_snapshot *out)
{
   struct backend_fixture *fixture = context;
   assert(!timeout && writer->sequence == fixture->accepted.sequence && writer->owner == fixture->accepted.owner &&
          writer->serial == fixture->accepted.serial && writer->slot == fixture->accepted.slot &&
          writer->queue == fixture->accepted.queue && writer->generation == fixture->accepted.generation);
   ++fixture->waits;
   if (fixture->invalidate.sequence)
      acd_kext_dcn_discard(fixture->transport, &fixture->invalidate);
   *busy = fixture->pending;
   return fixture->wait_error ? fixture->wait_error : backend_prefix(context, 0, 0, out);
}

static int backend_ack(void *context, const struct acd_exact_receipt *writer)
{
   struct backend_fixture *fixture = context;
   assert(writer->owner == fixture->accepted.owner);
   ++fixture->acks;
   return 0;
}

static int submit_one(struct backend_fixture *fixture, bool watch, uint32_t ip,
                      struct build34_dcn_native_submit *writer)
{
   struct n48n_cs_ib ib = {.ip_type = ip};
   struct acd_exact_receipt observed = {0};
   const struct acd_cs_plan plan = {.ctx_id = 17, .n_ibs = 1, .ibs = &ib,
                                    .receipt_out = watch ? &observed : NULL};
   uint64_t sequence = 0;
   const int result = acd_exact_submit(fixture->transport, fixture->transport->exact, &plan, &sequence);
   if (!result && writer) {
      assert(observed.sequence == sequence);
      *writer = (struct build34_dcn_native_submit){observed.sequence, observed.owner, observed.serial,
         observed.generation, observed.slot, observed.queue, plan.ctx_id};
   }
   return result;
}

static void expect_poll(struct backend_fixture *fixture, struct build34_dcn_native_submit writer,
                        int expected, bool expected_busy)
{
   bool busy = false;
   assert(acd_kext_dcn_poll(fixture->transport, &writer, &busy) == expected && busy == expected_busy);
}

int main(void)
{
   struct acd_kext transport = {.mtx = PTHREAD_MUTEX_INITIALIZER};
   struct backend_fixture fixture = {.transport = &transport, .pending = true,
      .accepted = {.sequence = 21, .owner = 37, .serial = 41, .generation = 53, .slot = 6, .queue = 1}};
   const struct acd_exact_backend backend = {.owner = 37, .ctx = &fixture, .submit = backend_submit,
      .wait = backend_wait, .ack = backend_ack, .wait_prefix = backend_prefix};
   struct build34_dcn_native_submit writer = {21, 37, 41, 53, 6, 1, 17};
   expect_poll(&fixture, writer, -EOPNOTSUPP, true);
   assert(!acd_kext_set_exact_backend(&transport, &backend));
   assert(!submit_one(&fixture, true, AMDGPU_HW_IP_GFX, &writer));

   for (unsigned field = 0; field < 7; ++field) {
      struct build34_dcn_native_submit mismatch = writer;
      switch (field) {
      case 0: mismatch.sequence--; break;
      case 1: mismatch.owner++; break;
      case 2: mismatch.serial++; break;
      case 3: mismatch.generation++; break;
      case 4: mismatch.slot++; break;
      case 5: mismatch.queue = 0; break;
      case 6: mismatch.context++; break;
      }
      expect_poll(&fixture, mismatch, field == 5 ? -EINVAL : -ENOENT, true);
   }
   assert(!fixture.waits);
   assert(!pthread_mutex_lock(&transport.exact->submit_mtx));
   expect_poll(&fixture, writer, -EAGAIN, true);
   assert(!pthread_mutex_unlock(&transport.exact->submit_mtx));
   assert(!fixture.waits);
   expect_poll(&fixture, writer, 0, true);
   assert(fixture.waits == 1 && !fixture.acks);
   fixture.wait_error = -EINTR;
   expect_poll(&fixture, writer, -EINTR, true);
   fixture.wait_error = 0;
   fixture.pending = false;
   expect_poll(&fixture, writer, 0, false);
   assert(fixture.waits == 3 && !fixture.acks);

   fixture.retired = writer.sequence;
   bool busy = true;
   assert(!acd_exact_prefix(&transport, transport.exact, 0, 0, &busy, NULL) && !busy);
   assert(fixture.acks == 1 && transport.exact->dcn_writer->acked);
   expect_poll(&fixture, writer, 0, false);
   assert(fixture.waits == 3);
   struct build34_dcn_native_submit hole = writer;
   hole.sequence--;
   assert(!acd_exact_wait(&transport, transport.exact, hole.sequence, 0, &busy, NULL) && !busy);
   expect_poll(&fixture, hole, -ENOENT, true);

   fixture.accepted.sequence += 2;
   fixture.accepted.serial++;
   fixture.accepted.queue = 0;
   assert(!submit_one(&fixture, false, AMDGPU_HW_IP_COMPUTE, NULL));
   expect_poll(&fixture, writer, -ENOENT, true);
   assert(fixture.submits == 2 && fixture.waits == 3);

   fixture.accepted.sequence++;
   fixture.accepted.serial++;
   fixture.accepted.generation++;
   fixture.accepted.queue = 1;
   struct build34_dcn_native_submit next;
   assert(!submit_one(&fixture, true, AMDGPU_HW_IP_GFX, &next));
   acd_kext_dcn_discard(&transport, &writer);
   expect_poll(&fixture, writer, -ENOENT, true);
   fixture.invalidate = next;
   expect_poll(&fixture, next, -ENOENT, true);
   fixture.invalidate = (struct build34_dcn_native_submit){0};
   assert(!transport.exact->dcn_writer && fixture.waits == 4);

   fixture.accepted.sequence++;
   fixture.accepted.serial++;
   assert(!submit_one(&fixture, true, AMDGPU_HW_IP_GFX, &next));
   fixture.submit_error = -EINVAL;
   assert(submit_one(&fixture, false, AMDGPU_HW_IP_COMPUTE, NULL) == -EINVAL);
   fixture.submit_error = 0;
   expect_poll(&fixture, next, -ENOENT, true);

   fixture.accepted.sequence++;
   fixture.accepted.serial++;
   assert(!submit_one(&fixture, true, AMDGPU_HW_IP_GFX, &next));
   fixture.retired = next.sequence;
   assert(!acd_exact_prefix(&transport, transport.exact, 0, 0, &busy, NULL));
   expect_poll(&fixture, next, 0, false);
   assert(transport.exact->dcn_writer->acked && fixture.waits == 4);

   fixture.accepted.sequence++;
   fixture.accepted.serial++;
   assert(!submit_one(&fixture, true, AMDGPU_HW_IP_GFX, &next));
   fixture.wrong_owner = true;
   expect_poll(&fixture, next, -ECANCELED, true);
   fixture.wrong_owner = false;
   expect_poll(&fixture, next, -ECANCELED, true);
   assert(fixture.waits == 5 && fixture.submits == 7);

   assert(!pthread_mutex_destroy(&transport.exact->submit_mtx));
   free(transport.exact);
   assert(!pthread_mutex_destroy(&transport.mtx));
   return 0;
}
