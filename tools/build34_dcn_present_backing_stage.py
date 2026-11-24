"""Observe the descriptor used by the existing build34 copy, without changing present."""

import hashlib


ACCEL = "src/phxaccel/accel/nvrm-accel.cpp"
ACCEL_SHA256 = "4855ecaf223a64f3da747d43f81d29e43b1066d7a72c11b5500c97609dff0335"


def stage(accelerator):
    if hashlib.sha256(accelerator).hexdigest() != ACCEL_SHA256:
        raise ValueError("Build34 DCN present backing source drift")
    source = accelerator.decode()

    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError("Build34 DCN present backing anchor drift: " + old[:90])
        source = source.replace(old, new)

    replace("class IOSurface {\n", '#include "build34_dcn_present_backing.h"\n\nclass IOSurface {\n')
    anchor = "IOReturn NVDisplayPipe::performTransaction(IOAccelDisplayPipeTransaction2 *txn)\n"
    replace(anchor, """static void (*nvAccelObserveDcnCopyBacking)(const build34::dcn::PresentCopyBacking &){nullptr};
""" + anchor)
    replace("    const volatile unsigned int *src = nullptr; unsigned w = 0, h = 0, pitch = 0; bool fromRes = false, l10r = false;\n",
            "    const volatile unsigned int *src = nullptr; unsigned w = 0, h = 0, pitch = 0; bool fromRes = false, l10r = false;\n"
            "    IOMemoryDescriptor *copyDescriptor = nullptr;\n")
    replace("        w = (unsigned)W; h = (unsigned)H; pitch = (unsigned)P;\n",
            "        w = (unsigned)W; h = (unsigned)H; pitch = (unsigned)P;\n"
            "        copyDescriptor = md;\n")
    replace("    nvAccelIopHome(fb, head);\n    const unsigned words =",
            """    if (nvAccelObserveDcnCopyBacking && copyDescriptor && !fromRes && !l10r &&
        txn->getPlaneIOSurface(0, 0) == s && s->getMemoryDescriptor() == copyDescriptor &&
        s->getWidth() == w && s->getHeight() == h && s->getBytesPerRow() == pitch) {
        const auto observed = build34::dcn::observePreparedCopyBacking(txn, s, copyDescriptor,
            s->getPixelFormat(), w, h, pitch, q.width, q.height);
        if (observed.preparation)
            nvAccelObserveDcnCopyBacking(observed);
    }
    nvAccelIopHome(fb, head);
    const unsigned words =""")
    return source
