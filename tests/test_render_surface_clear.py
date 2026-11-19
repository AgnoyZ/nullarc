"""CPU replay of the actual render preparation branches; never opens a GPU.

Adapted from luuumi-dev/nullarc commit 531bac34989f32b861c77f5788290b9b6615405d.
The backing and partial clear are models, not a Vulkan/WindowServer replay.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def preparation(source, start):
    begin = source.index('if (sr->_surf) {', start)
    tail = source.index('else if (sr->_bufCopy)', begin)
    end = source.index('}', tail) + 1
    return source[begin:end]


class RenderSurfaceClear(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'src/nmplugin/NVMTLObjects.m').read_text()
        secondary = preparation(source, source.index('if (i) {', source.index('uint32_t load = 0')))
        primary = preparation(source, source.index('- (id<MTLRenderCommandEncoder>)renderCommandEncoderWithDescriptor:'))
        code = r'''
#include <cstdio>
#include <cstdlib>
struct Texture { bool _surf, _bufCopy; int cpu[4]={1,2,3,4}; int gpu[4]={9,9,9,9}; };
struct Buffer { bool overwritten=false; };
struct Attachment { int loadAction; };
struct Descriptor { Attachment colorAttachments[1]; };
constexpr int MTLLoadActionClear=2;
void nvmtl_surface_in_for_cb(Buffer *cb, Texture *t) {
    if (!cb->overwritten) for (int i=0;i<4;i++) t->gpu[i]=t->cpu[i];
}
void nvmtl_surface_overwrite_recorded(Buffer *cb, Texture *) { cb->overwritten=true; }
void nvmtl_surf_dirty(Buffer *, Texture *) {}
'''
        code += 'void secondary(Buffer *cb, Texture *sr, Attachment ca) {\n' + secondary + '\n}\n'
        code += 'void primary(Buffer *self, Texture *sr, Descriptor d) {\n' + primary + '\n}\n'
        code += r'''
int main(int argc, char **argv) {
    if (argc != 4) return 64;
    const bool primaryPath = std::atoi(argv[1]), surface = std::atoi(argv[2]);
    const int action = std::atoi(argv[3]);
    Texture texture{surface,!surface}; Buffer cb; Descriptor d{{{action}}};
    if (primaryPath) primary(&cb,&texture,d); else secondary(&cb,&texture,d.colorAttachments[0]);
    // Model a pass whose render area covers only the first pixel of the root.
    if (action==MTLLoadActionClear) texture.gpu[0]=0;
    for (int i=0;i<4;i++) {
        const int expected = (action==MTLLoadActionClear && i==0) ? 0 : texture.cpu[i];
        if (texture.gpu[i] != expected) {
            std::fprintf(stderr, "pixel %d: got %d, expected %d\n", i, texture.gpu[i], expected);
            return 1;
        }
    }
    if (cb.overwritten) {
        std::fputs("partial render marked the entire backing overwritten\n", stderr);
        return 2;
    }
}
'''
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name) / 'test.cpp'
        path.write_text(code)
        cls.binary = Path(cls.temp.name) / 'test'
        result = subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-parameter', '-fsanitize=address,undefined',
                                 '-fno-sanitize-recover=all', str(path), '-o', str(cls.binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def check_action(self, action):
        for primary in (False, True):
            for surface in (False, True):
                with self.subTest(primary=primary, iosurface=surface, action=action):
                    result = subprocess.run([str(self.binary), str(int(primary)),
                                             str(int(surface)), str(action)],
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_clear_preserves_untouched_pixels(self):
        self.check_action(2)

    def test_load_preserves_existing_contents(self):
        self.check_action(1)


if __name__ == '__main__':
    unittest.main()
