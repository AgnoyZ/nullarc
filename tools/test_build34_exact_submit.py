#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CPU-only actual native submit integration experiment; no kernel build or GPU."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_submit import stage
from test_build34_exact_ownership import ROOT, DRIVER, PINNED, method, sha

FIXTURE = 'tests/test_build34_exact_submit.cpp'
TRANSFORM = 'tools/build34_exact_submit.py'
RUNNER = 'tools/test_build34_exact_submit.py'


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored build path ending -private')
    paths = [*PINNED, FIXTURE, TRANSFORM, RUNNER, 'tools/test_build34_exact_ownership.py',
             'tools/build34_exact_ownership.h', 'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    if any(sha(inputs[name]) != digest for name, digest in PINNED.items()):
        raise ValueError('Accepted build34 driver/ABI/topology drift')
    protected_names = subprocess.check_output(['git','ls-files','src','tools/phxctl','tools/build_kext.py'],
                                              cwd=ROOT,text=True,timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in protected_names}
    source = inputs[DRIVER].decode()
    staged = stage(source)
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 source is admissible')
    for sig in ['uint64_t PhxBringup::gpuRetired(', 'uint64_t PhxBringup::queueFence(',
                'IOReturn IOAccelPhxNativeClient::doWaitSeq(']:
        if method(source,sig) != method(staged,sig):
            raise ValueError('Legacy retirement/wait drift')
    out.mkdir(parents=True,mode=0o700)
    frozen = out / 'frozen'
    for name,blob in inputs.items():
        p=frozen/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(blob)
    staged_path=out/'source'/DRIVER; staged_path.parent.mkdir(parents=True)
    staged_path.write_text(staged)
    (staged_path.parent/'build34_exact_ownership.h').write_bytes(inputs['tools/build34_exact_ownership.h'])
    (out/'source-experiment.diff').write_text(''.join(difflib.unified_diff(
        source.splitlines(True),staged.splitlines(True),fromfile='a/'+DRIVER,tofile='b/'+DRIVER)))

    def run(args,label,expect_failure=False):
        p=subprocess.run([str(x) for x in args],cwd=out,stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(p.stdout); (out/(label+'.stderr')).write_bytes(p.stderr)
        if expect_failure:
            if p.returncode==0 or b'failed ' not in p.stderr:
                raise ValueError(label+' did not detect the intended callsite defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label+' failed; see private logs')
        return p.stdout.decode()

    signatures=['IOReturn PhxBringup::gpuSubmit(', 'IOReturn IOAccelPhxNativeClient::doSubmit(',
                'IOReturn PhxBringup::adoptQueue(', 'uint64_t PhxBringup::queueFence(', 'uint64_t PhxBringup::gpuRetired(']
    template=inputs[FIXTURE].decode()
    if template.count('// PHX34_EXACT_SUBMIT_METHODS')!=1 or template.count('// PHX34_EXACT_SUBMIT_DECLARATION')!=1:
        raise ValueError('Fixture extraction marker drift')
    declaration=re.findall(r'^    IOReturn gpuSubmit\([^;]+;',staged,re.M)
    if len(declaration)!=1: raise ValueError('Internal declaration drift')
    cc=['/usr/bin/xcrun','clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
        '-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer',
        '-I'+str(frozen/'src/phxbringup'),'-I'+str(frozen/'tools')]

    def exercise(label,code,broken=False):
        target=out/(label+'.cpp')
        target.write_text(template.replace('// PHX34_EXACT_SUBMIT_METHODS','\n'.join(method(code,s) for s in signatures))
                         .replace('// PHX34_EXACT_SUBMIT_DECLARATION',declaration[0]))
        binary=out/(label+'-CPU-only'); dep=out/(label+'.d')
        run([*cc,'-MMD','-MF',dep,target,'-o',binary],label+'-compile')
        dependencies=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        allowed={str((frozen/name).resolve()) for name in inputs}|{str(target.resolve())}
        if not dependencies or any(str(Path(n).resolve()) not in allowed for n in dependencies):
            raise ValueError('Unfrozen compilation dependency')
        linked=run(['/usr/bin/otool','-L',binary],label+'-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel',linked,re.I): raise ValueError('Device runtime linked')
        return run([binary],label+'-test',broken)

    result=exercise('exact-submit',staged)
    match=re.fullmatch(r'PASS actual staged native submit: (\d+) checks; (\d+) cases; CPU_only=true; GPU_executed=false\n',result)
    if not match: raise ValueError('Incomplete native submit suite')
    # Sensitivity tests mutate actual callsites, not the registry model.
    mutants={
        'wrong-actual-queue': ('const uint32_t actualQueue = qp == &gq[1] ? 1u : 0u;',
                               'const uint32_t actualQueue = gfx ? 1u : 0u;'),
        'missing-publication': ('if (exact && exact->publish(ticket,', 'if (false && exact && exact->publish(ticket,'),
        'missing-overflow-guard': ('if (exact && gSeq >= UINT64_MAX - 1)', 'if (false && exact && gSeq >= UINT64_MAX - 1)'),
        'missing-adoption-epoch': ('++exactQueueGeneration[qi];','/* removed adoption epoch */'),
    }
    for label,(before,after) in mutants.items():
        if staged.count(before)!=1: raise ValueError('Mutation anchor drift')
        exercise(label,staged.replace(before,after,1),True)
    early = staged.replace('    gSeq = seq;\n', '', 1).replace(
        '    uint32_t k = 0;\n', '    gSeq = seq;\n    uint32_t k = 0;\n', 1)
    exercise('early-global-sequence', early, True)
    if any((ROOT/name).read_bytes()!=blob or (frozen/name).read_bytes()!=blob for name,blob in inputs.items()):
        raise ValueError('Source input drift')
    if protected!={name:sha((ROOT/name).read_bytes()) for name in protected_names}:
        raise ValueError('Production input drift')
    report=dict(status='passed-CPU-only-staged-native-submit-integration',kernel_build=34,
                actual_methods_extracted=len(signatures),checks=int(match[1]),cases=int(match[2]),
                asan_ubsan=True,detected_callsite_mutations=[*mutants,'early-global-sequence'],
                actual_queue_captured_after_retry=True,receipt_published_before_first_ring_write=True,
                full_registry_refuses_submission=True,implicit_receipt_eviction=False,
                exact_sequence_wrap_refused=True,adoption_epoch_wrap_refused=True,
                registry_retained_after_history_reuse=True,legacy_global_retirement_unchanged=True,
                global_sequence_update_site_preserved=True,interleaved_actual_two_client_submits=True,
                new_actual_thread_concurrency_or_TSan_testing=False,
                legacy_WAITSEQ_and_native_ABI_unchanged=True,vm_bind_can_have_register_side_effects=True,
                protected_production_file_count=len(protected),production_inputs_unchanged=True,
                input_sha256={name:sha(blob) for name,blob in inputs.items()},staged_driver_sha256=sha(staged.encode()),
                internal_exact_pointer_has_production_allocator=False,native_capability_negotiation_implemented=False,
                complete_lifecycle_generation_implemented=False,coherent_hardware_fence_read_implemented=False,
                native_teardown_drain_implemented=False,automatic_receipt_reclamation_implemented=False,
                native_kernel_compiled=False,installed=False,loaded=False,GPU_executed=False,
                R3_hardware_accepted=False,R4_R6_started=False,physical_FPS_measured=False,public_binary_upload=False)
    (out/'result-private.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    test(parser.parse_args().out)
