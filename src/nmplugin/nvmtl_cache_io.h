/* Original downstream disposable-cache I/O. Existing component licence applies.
 * Integrity detects accidental corruption, not hostile modification or provenance. */
#ifndef NVMTL_CACHE_IO_H
#define NVMTL_CACHE_IO_H
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#ifndef NVMTL_CACHE_WRITE
#define NVMTL_CACHE_WRITE write
#endif
#ifndef NVMTL_CACHE_READ
#define NVMTL_CACHE_READ read
#endif
#ifndef NVMTL_CACHE_SYNC
#define NVMTL_CACHE_SYNC fsync
#endif
#ifndef NVMTL_CACHE_RENAME
#define NVMTL_CACHE_RENAME rename
#endif
enum { NVMTL_CACHE_SPIRV = 1, NVMTL_CACHE_INDEX = 2, NVMTL_CACHE_LIBKEY = 3 };
static inline uint64_t nvmtl_cache_hash(const void *data, size_t size) {
    const unsigned char *p = (const unsigned char *)data;
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < size; ++i) hash = (hash ^ p[i]) * UINT64_C(1099511628211);
    return hash;
}
static inline void nvmtl_cache_put64(unsigned char *p, uint64_t v) {
    for (unsigned i = 0; i < 8; ++i) p[i] = (unsigned char)(v >> (i * 8));
}
static inline uint64_t nvmtl_cache_get64(const unsigned char *p) {
    uint64_t v = 0; for (unsigned i = 0; i < 8; ++i) v |= (uint64_t)p[i] << (i * 8); return v;
}
static inline int nvmtl_cache_write_all(int fd, const void *data, size_t size) {
    const unsigned char *p = (const unsigned char *)data;
    while (size) {
        ssize_t n = NVMTL_CACHE_WRITE(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0 || (size_t)n > size) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}
static inline int nvmtl_cache_read_all(int fd, void *data, size_t size) {
    unsigned char *p = (unsigned char *)data;
    while (size) {
        ssize_t n = NVMTL_CACHE_READ(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0 || (size_t)n > size) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}
static inline char *nvmtl_cache_temp_name(const char *path) {
    if (!path || !*path) return NULL;
    size_t n = strlen(path); if (n > SIZE_MAX - 12) return NULL;
    char *tmp = (char *)malloc(n + 12);
    if (tmp) { memcpy(tmp, path, n); memcpy(tmp + n, ".tmp.XXXXXX", 12); }
    return tmp;
}
static inline int nvmtl_cache_store(const char *path, unsigned kind, const void *data, size_t size) {
    if (!data || !size || !kind || size > (256u << 20)) return -1;
    char *tmp = nvmtl_cache_temp_name(path); if (!tmp) return -1;
    int fd = mkstemp(tmp);
    if (fd < 0) { free(tmp); return -1; }
    unsigned char header[32] = {'N','V','M','C','A','C','H',1};
    nvmtl_cache_put64(header + 8, kind); nvmtl_cache_put64(header + 16, size);
    nvmtl_cache_put64(header + 24, nvmtl_cache_hash(data, size));
    int ok = fcntl(fd, F_SETFD, FD_CLOEXEC) == 0 &&
        nvmtl_cache_write_all(fd, header, sizeof header) == 0 &&
        nvmtl_cache_write_all(fd, data, size) == 0 && NVMTL_CACHE_SYNC(fd) == 0;
    if (close(fd) != 0) ok = 0;
    if (ok && NVMTL_CACHE_RENAME(tmp, path) == 0) { free(tmp); return 0; }
    unlink(tmp); free(tmp); return -1;
}
static inline int nvmtl_cache_load(const char *path, unsigned kind, size_t max_size, void **data, size_t *size) {
    if (!data || !size) return -1;
    *data = NULL; *size = 0;
    if (!path || !kind || !max_size) return -1;
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return -1;
    struct stat st; unsigned char header[32]; void *payload = NULL; int ok = 0;
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size < 33 ||
        (uint64_t)st.st_size - 32 > max_size || (uint64_t)st.st_size - 32 > (256u << 20)) goto done;
    if (nvmtl_cache_read_all(fd, header, sizeof header) != 0 ||
        memcmp(header, "NVMCACH\1", 8) || nvmtl_cache_get64(header + 8) != kind ||
        nvmtl_cache_get64(header + 16) != (uint64_t)st.st_size - 32) goto done;
    payload = malloc((size_t)st.st_size - 32);
    if (!payload || nvmtl_cache_read_all(fd, payload, (size_t)st.st_size - 32) != 0 ||
        nvmtl_cache_hash(payload, (size_t)st.st_size - 32) != nvmtl_cache_get64(header + 24)) goto done;
    {
        unsigned char extra; ssize_t n;
        do { n = NVMTL_CACHE_READ(fd, &extra, 1); } while (n < 0 && errno == EINTR);
        if (n != 0) goto done;
    }
    ok = 1;
done:
    if (close(fd) != 0) ok = 0;
    if (ok) { *data = payload; *size = (size_t)st.st_size - 32; return 0; }
    free(payload); return -1;
}
#endif
