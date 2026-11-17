#!/usr/bin/env python3
"""Fault-test the actual runtime guard with only compiled CPU platform ops."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test(cpu_probe,runtime,output):
    cpu_probe,runtime,output=(Path(p).resolve() for p in (cpu_probe,runtime,output))
    output.relative_to((ROOT/'build').resolve())
    if output.exists():raise ValueError('Fresh private output required')
    prepared=json.loads((cpu_probe/'preparation.json').read_text())
    parent=json.loads((cpu_probe.parent/'report.json').read_text())
    if prepared['CPU_platform'] is not True or parent['result']!='passed':raise ValueError('Passed all-fake CPU probe required')
    names=('tools/upstream34_layout/radv_ib_tail_runtime_guard.cpp','tools/upstream34_layout/radv_ib_tail_runtime_guard.h',
           'tests/build34_radv_runtime_platform.cpp','tests/test_build34_radv_runtime_guard.cpp',
           'tools/test_build34_radv_runtime_guard.py')
    snapshots={name:(ROOT/name).read_bytes() for name in names}
    for name in names[:3]:
        if sha(ROOT/name)!=prepared['sources_sha256'][name]:raise ValueError('Guard differs from the passed full Vulkan CPU model')
    abi=runtime/'mesa/include/darwin/navi48_native_abi.h'
    if sha(abi)!=prepared['reviewed_header_sha256']['include/darwin/navi48_native_abi.h']:raise ValueError('Native ABI header drift')
    output.mkdir(parents=True,mode=0o700)
    source=output/'source'
    for name,data in snapshots.items():
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    (output/'include').mkdir();shutil.copyfile(abi,output/'include/navi48_native_abi.h')
    env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(output),'LANG':'C','LC_ALL':'C'}
    cc=['/usr/bin/xcrun','clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
        '-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-I'+str(output/'include')]
    objects=[]
    for i,name in enumerate(names[2:4]):
        obj=output/(str(i)+'.o');objects.append(obj)
        p=subprocess.run(cc+['-c',str(source/name),'-o',str(obj)],env=env,capture_output=True,timeout=90)
        (output/('compile-'+str(i)+'.log')).write_bytes(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError('CPU guard unit compilation failed; inspect private logs')
    binary=output/'CPU-runtime-guard'
    p=subprocess.run(cc+list(map(str,objects))+['-framework','IOKit','-framework','CoreFoundation','-o',str(binary)],env=env,capture_output=True,timeout=90)
    (output/'link.log').write_bytes(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError('CPU guard unit link failed')
    binary_hash=sha(binary)
    cases=['ok','high-canonical','proxy','second-open','matching-retry','alternate-enumeration','third-Hello',
           'tail-bytes','tail-padding','tail-remap','tail-writeable','noncanonical','overlap','graphics',
           'wrong-tail','missing-IB-map','too-many-IBs','scanout','missing-submit-output','close-inflight',
           'CPU-unmap-inflight','GPU-unmap-inflight','free-inflight','unchanged-IB','third-submit']
    results={}
    for name in cases:
        stdout,stderr=output/(name+'.stdout'),output/(name+'.stderr')
        with stdout.open('xb') as out,stderr.open('xb') as err:
            process=subprocess.Popen([str(binary),name],env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
            held=False
            try:
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    if 'CPU-FIXTURE-HOLD:' in stderr.read_text():held=True;break
                    if process.poll() is not None:break
                    time.sleep(.05)
                if name in ('ok','high-canonical'):
                    if held or process.poll()!=0 or stdout.read_text()!='CPU-GUARD-PASS '+name+'; no GPU\n':
                        raise RuntimeError('CPU guard positive failed: '+name)
                    expected_submits=2
                else:
                    expected_submits=2 if name in ('unchanged-IB','third-submit') else 1 if name.endswith('inflight') else 0
                    match=re.search(r'CPU-FIXTURE-HOLD: opens=(\d+) closes=0 fake_submits=(\d+) arena_passes=(\d+)\n',stderr.read_text())
                    if not held or process.poll() is not None or not match or int(match[2])!=expected_submits:
                        raise RuntimeError('CPU guard rejection failed: '+name)
                results[name]={'passed':True,'CPU_hold':held,'fake_submits_at_boundary':expected_submits}
            finally:
                # This program has no native platform implementation and is hash
                # pinned. Never terminate a GPU probe through this test harness.
                if process.poll() is None:process.terminate();process.wait(timeout=5)
    if sha(binary)!=binary_hash or any((ROOT/name).read_bytes()!=data for name,data in snapshots.items()):raise RuntimeError('CPU guard test input drift')
    report={'result':'passed','CPU_cases':results,'ASan_UBSan':True,'native_platform_compiled':False,'GPU_executed':False,
            'binary_sha256':binary_hash,'native_ABI_header_sha256':sha(abi),
            'inputs_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in snapshots.items()}}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'result':'passed','CPU_guard_cases':len(results),'GPU_executed':False}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-probe',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();test(args.cpu_probe,args.runtime,args.out)
