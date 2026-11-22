"""Stage explicit DRM publication and drain the sync backend before transport close."""

from build34_exact_submit import once


INIT = '''int
acd_device_initialize(uint32_t *drm_major, uint32_t *drm_minor, acd_device_handle *out)
{
'''
MODE = '''static int
acd_device_initialize_mode(bool exact, mach_port_t *connection, uint32_t *drm_major,
                           uint32_t *drm_minor, acd_device_handle *out)
{
   if (!drm_major || !drm_minor || !out || (connection && !MACH_PORT_VALID(*connection)))
      return -EINVAL;
'''
LEGACY_INIT = '''   int r = 0;
   if (dev->host_bo) {
      r = acd_core_create(dev->canned, true, &dev->core); /* private, no kext */
   } else {
      pthread_mutex_lock(&g_core_lock);
      if (g_core) {
         g_core->refcount++;
         dev->core = g_core;
      } else {
         r = acd_core_create(dev->canned, false, &g_core);
         if (r == 0) {
            g_core->shared = true;
            dev->core = g_core;
         }
      }
      pthread_mutex_unlock(&g_core_lock);
   }
   if (r) {
      free(dev);
      return r;
   }

   dev->sync = dev->core->sync->clone(dev->core->sync);
   if (!dev->sync) {
      acd_device_deinitialize(dev);
      return -ENOMEM;
   }
'''
PUBLISH = '''   int r = 0;
   struct acd_core *unpublished = NULL;
   pthread_mutex_lock(&g_core_lock);
   if (g_core_closing || (g_core && (connection || acd_sync_has_exact_completion(g_core->sync) != exact))) {
      r = -EBUSY;
   } else if (g_core) {
      dev->core = g_core;
   } else if (exact && !connection) {
      r = -ENODEV;
   } else {
      r = acd_core_create(dev->canned, false, connection, &unpublished);
      dev->core = unpublished;
   }
   if (!r) {
      dev->sync = dev->core->sync->clone(dev->core->sync);
      if (!dev->sync)
         r = -ENOMEM;
      else if (unpublished) {
         unpublished->shared = true;
         g_core = unpublished;
      } else {
         g_core->refcount++;
      }
   }
   if (r && unpublished)
      g_core_closing = true;
   pthread_mutex_unlock(&g_core_lock);

   if (r) {
      if (unpublished)
         acd_close_shared_core(unpublished);
      free(dev);
      return r;
   }
'''
WRAPPERS = INIT + '''   return acd_device_initialize_mode(false, NULL, drm_major, drm_minor, out);
}

int
acd_device_initialize_exact_iokit(mach_port_t *connection, uint32_t *drm_major, uint32_t *drm_minor,
                                 acd_device_handle *out)
{
   return acd_device_initialize_mode(true, connection, drm_major, drm_minor, out);
}

'''


def stage_drm(source):
    source = once(source, '#include "ac_darwin_drm.h"\n',
                  '#include "ac_darwin_drm.h"\n#include "build34_r3_mesa_drm.h"\n'
                  '#include "build34_r3_mesa_iokit.h"\n')
    source = once(source, 'static struct acd_core *g_core;\n',
                  'static struct acd_core *g_core;\nstatic bool g_core_closing;\n')
    source = once(source, 'acd_core_create(const struct amdgpu_device *canned, bool host_bo, struct acd_core **out)',
                  'acd_core_create(const struct amdgpu_device *canned, bool host_bo, mach_port_t *connection,\n'
                  '                struct acd_core **out)')
    source = once(source, '      int r = acd_kext_open(&c->kext);\n',
                  '      int r = connection ? acd_kext_adopt_exact_iokit(connection, &c->kext) : acd_kext_open(&c->kext);\n')
    source = once(source, '   const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = c->kext};\n',
                  '   const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = c->kext,\n'
                  '                                       .exact_completion = connection != NULL};\n')
    source = once(source, 'acd_core_destroy(struct acd_core *c)\n{\n',
                  'acd_core_destroy(struct acd_core *c)\n{\n   acd_sync_detach_backend(c->sync);\n')
    source = once(source, INIT, '''static void
acd_close_shared_core(struct acd_core *c)
{
   acd_core_destroy(c);
   pthread_mutex_lock(&g_core_lock);
   g_core_closing = false;
   pthread_mutex_unlock(&g_core_lock);
}

''' + MODE)
    source = once(source, LEGACY_INIT, PUBLISH)
    source = once(source, 'void\nacd_device_deinitialize(', WRAPPERS + 'void\nacd_device_deinitialize(')
    source = once(source, '      if (last)\n         g_core = NULL;\n',
                  '      if (last) {\n         g_core = NULL;\n         g_core_closing = true;\n      }\n')
    return once(source, '   if (last)\n      acd_core_destroy(c);\n',
                '   if (last) {\n      if (c->shared)\n         acd_close_shared_core(c);\n'
                '      else\n         acd_core_destroy(c);\n   }\n')


def stage_sync(source):
    source = once(source, '#include "ac_darwin_drm.h"\n',
                  '#include "ac_darwin_drm.h"\n#include "build34_r3_mesa_drm.h"\n')
    source = once(source, '   struct acd_sync_backend be;\n',
                  '   struct acd_sync_backend be;\n   uint32_t backend_users;\n   bool backend_closed;\n')
    source = once(source, 'note_completed(struct acd_sync *s, uint64_t seq)\n{\n   pthread_mutex_lock(&s->mtx);\n',
                  'note_completed_locked(struct acd_sync *s, uint64_t seq)\n{\n')
    source = once(source, '   pthread_mutex_unlock(&s->mtx);\n}\n\nstatic int\nbackend_wait(',
                  '''}

void
acd_sync_detach_backend(struct util_sync_provider *provider)
{
   struct acd_sync *s = to_sync(provider);
   pthread_mutex_lock(&s->mtx);
   s->backend_closed = true;
   pthread_cond_broadcast(&s->cond);
   while (s->backend_users)
      pthread_cond_wait(&s->cond, &s->mtx);
   s->be.ctx = NULL;
   pthread_mutex_unlock(&s->mtx);
}

static int
backend_wait(''')
    source = once(source, '   int r = s->be.wait_seq(s->be.ctx, seq, rel_ns, &busy, &retired);\n',
                  '''   pthread_mutex_lock(&s->mtx);
   if (s->backend_closed || s->backend_users == UINT32_MAX) {
      const int result = s->backend_closed ? -ECANCELED : -EAGAIN;
      pthread_mutex_unlock(&s->mtx);
      return result;
   }
   void *context = s->be.ctx;
   s->backend_users++;
   pthread_mutex_unlock(&s->mtx);
   int r = s->be.wait_seq(context, seq, rel_ns, &busy, &retired);
''')
    source = once(source, '''   if (r)
      return r;
   note_retired(s, retired);
   if (!busy && seq > retired)
      note_completed(s, seq);
   return 0;
''', '''   pthread_mutex_lock(&s->mtx);
   if (s->backend_closed)
      r = -ECANCELED;
   if (!r) {
      note_retired(s, retired);
      if (!busy && seq > retired)
         note_completed_locked(s, seq);
   }
   if (--s->backend_users == 0 && s->backend_closed)
      pthread_cond_broadcast(&s->cond);
   pthread_mutex_unlock(&s->mtx);
   return r;
''')
    source = once(source, '   unsigned done = 0, first = 0;\n',
                  '   if (s->backend_closed)\n      return -ECANCELED;\n   unsigned done = 0, first = 0;\n')
    source = once(source, '      pthread_mutex_lock(&s->mtx);\n      for (unsigned i = 0; i < n; i++) {\n',
                  '      pthread_mutex_lock(&s->mtx);\n      if (s->backend_closed) {\n'
                  '         pthread_mutex_unlock(&s->mtx);\n         return SYNC_FAIL(ECANCELED);\n      }\n'
                  '      for (unsigned i = 0; i < n; i++) {\n')
    return once(source, '   for (;;) {\n      struct acd_syncobj *o = lookup(s, handle);\n',
                '   for (;;) {\n      if (s->backend_closed) {\n         pthread_mutex_unlock(&s->mtx);\n'
                '         return -ECANCELED;\n      }\n      struct acd_syncobj *o = lookup(s, handle);\n')
