#define _GNU_SOURCE
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <pthread.h>
static int write_fault, read_fault, sync_fault, rename_fault;
static ssize_t test_write(int fd, const void *p, size_t n) {
    if (write_fault == 1) { write_fault = 4; errno = EINTR; return -1; }
    if (write_fault == 2) return 0;
    if (write_fault == 3) { errno = EIO; return -1; }
    return write(fd, p, write_fault == 4 && n > 3 ? 3 : n);
}
static ssize_t test_read(int fd, void *p, size_t n) {
    if (read_fault == 1) { read_fault = 4; errno = EINTR; return -1; }
    if (read_fault == 2) return 0;
    if (read_fault == 3) { errno = EIO; return -1; }
    return read(fd, p, read_fault == 4 && n > 3 ? 3 : n);
}
static int test_sync(int fd) { if (sync_fault) { errno = EIO; return -1; } return fsync(fd); }
static int test_rename(const char *a, const char *b) { if (rename_fault) { errno = EACCES; return -1; } return rename(a, b); }
#define NVMTL_CACHE_WRITE test_write
#define NVMTL_CACHE_READ test_read
#define NVMTL_CACHE_SYNC test_sync
#define NVMTL_CACHE_RENAME test_rename
#include "nvmtl_cache_io.h"
static const char old[] = "previous complete payload", fresh[] = "replacement complete payload";
static void hit(const char *path, const void *expected, size_t n) {
    void *p = NULL; size_t size = 0;
    assert(nvmtl_cache_load(path, NVMTL_CACHE_SPIRV, 4096, &p, &size) == 0);
    assert(size == n && !memcmp(p, expected, n)); free(p);
}
static void miss(const char *path, unsigned kind, size_t limit) {
    void *p = (void *)(uintptr_t)1; size_t n = 99;
    assert(nvmtl_cache_load(path, kind, limit, &p, &n) != 0 && p == NULL && n == 0);
}
static void put(const char *path) { assert(nvmtl_cache_store(path, NVMTL_CACHE_SPIRV, old, sizeof old) == 0); }
static void change(const char *path, off_t offset) {
    int fd = open(path, O_RDWR); assert(fd >= 0);
    unsigned char b; assert(pread(fd, &b, 1, offset) == 1); b ^= 0x55;
    assert(pwrite(fd, &b, 1, offset) == 1); assert(close(fd) == 0);
}
static void *writer_thread(void *arg) {
    const int which = (int)(uintptr_t)arg;
    const char *p = which & 1 ? old : fresh; size_t n = which & 1 ? sizeof old : sizeof fresh;
    for (int i = 0; i < 60; ++i) {
        assert(nvmtl_cache_store("entry", 1, p, n) == 0);
        void *data; size_t size; assert(nvmtl_cache_load("entry", 1, 4096, &data, &size) == 0);
        assert((size == sizeof old && !memcmp(data, old, size)) || (size == sizeof fresh && !memcmp(data, fresh, size))); free(data);
    }
    return NULL;
}
int main(int argc, char **argv) {
    assert(argc == 2 && chdir(argv[1]) == 0); const char *path = "entry";
    miss(path, 1, 4096); put(path); hit(path, old, sizeof old);
    struct stat st; assert(stat(path, &st) == 0 && (st.st_mode & 0777) == 0600);
    miss(path, 2, 4096); miss(path, 1, sizeof old - 1);
    const off_t corrupt[] = {0, 7, 8, 16, 24, 32, 32 + sizeof old - 1};
    for (unsigned i = 0; i < sizeof corrupt / sizeof *corrupt; ++i) { put(path); change(path, corrupt[i]); miss(path, 1, 4096); }
    for (size_t n = 0; n < 32 + sizeof old; ++n) { put(path); assert(truncate(path, (off_t)n) == 0); miss(path, 1, 4096); }
    put(path); assert(truncate(path, 33 + sizeof old) == 0); miss(path, 1, 4096);
    put(path); assert(truncate(path, (off_t)(256u << 20) + 33) == 0); miss(path, 1, SIZE_MAX);
    assert(unlink(path) == 0); put("target"); assert(symlink("target", path) == 0); miss(path, 1, 4096);
    put(path); hit(path, old, sizeof old); hit("target", old, sizeof old);
    assert(unlink(path) == 0); assert(mkfifo(path, 0600) == 0); miss(path, 1, 4096); assert(unlink(path) == 0);
    assert(mkdir(path, 0700) == 0); miss(path, 1, 4096);
    assert(nvmtl_cache_store(path, 1, old, sizeof old) != 0); assert(rmdir(path) == 0);
    assert(nvmtl_cache_store(NULL, 1, old, sizeof old) != 0);
    assert(nvmtl_cache_store(path, 1, NULL, 10) != 0);
    assert(nvmtl_cache_store(path, 1, old, 0) != 0);
    assert(nvmtl_cache_store(path, 1, old, (256u << 20) + 1) != 0);
    assert(nvmtl_cache_store(path, 0, old, sizeof old) != 0);
    put(path); write_fault = 1; assert(nvmtl_cache_store(path, 1, fresh, sizeof fresh) == 0); write_fault = 0;
    read_fault = 1; hit(path, fresh, sizeof fresh); read_fault = 0;
    for (int f = 2; f <= 3; ++f) {
        put(path); write_fault = f; assert(nvmtl_cache_store(path, 1, fresh, sizeof fresh) != 0); write_fault = 0; hit(path, old, sizeof old);
        read_fault = f; miss(path, 1, 4096); read_fault = 0; hit(path, old, sizeof old);
    }
    sync_fault = 1; assert(nvmtl_cache_store(path, 1, fresh, sizeof fresh) != 0); sync_fault = 0; hit(path, old, sizeof old);
    rename_fault = 1; assert(nvmtl_cache_store(path, 1, fresh, sizeof fresh) != 0); rename_fault = 0; hit(path, old, sizeof old);
    pid_t children[4];
    for (int c = 0; c < 4; ++c) {
        children[c] = fork(); assert(children[c] >= 0);
        if (!children[c]) {
            for (int i = 0; i < 60; ++i) {
                const char *p = c & 1 ? old : fresh; size_t n = c & 1 ? sizeof old : sizeof fresh;
                assert(nvmtl_cache_store(path, 1, p, n) == 0);
                void *data; size_t size; assert(nvmtl_cache_load(path, 1, 4096, &data, &size) == 0);
                assert((size == sizeof old && !memcmp(data, old, size)) || (size == sizeof fresh && !memcmp(data, fresh, size))); free(data);
            }
            _exit(0);
        }
    }
    for (int c = 0; c < 4; ++c) { int status; assert(waitpid(children[c], &status, 0) == children[c]); assert(WIFEXITED(status) && WEXITSTATUS(status) == 0); }
    pthread_t threads[4];
    for (int c = 0; c < 4; ++c) assert(pthread_create(&threads[c], NULL, writer_thread, (void *)(uintptr_t)c) == 0);
    for (int c = 0; c < 4; ++c) assert(pthread_join(threads[c], NULL) == 0);
    DIR *dir = opendir("."); assert(dir); struct dirent *entry;
    while ((entry = readdir(dir))) assert(strstr(entry->d_name, ".tmp.") == NULL);
    closedir(dir); unlink(path); unlink("target");
    puts("{\"io_contract\": true, \"concurrent_writes\": 480, \"hardware_executed\": false}");
}
