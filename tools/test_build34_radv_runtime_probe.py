#!/usr/bin/env python3
"""Run the actual complete Vulkan probe with CPU platform ops and an explicit output oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from upstream34_layout import radv_ib_tail_runtime_probe as builder

ROOT=Path(__file__).resolve().parents[1]


def test(runtime,output,glslang):
    output=Path(output).resolve(); output.relative_to((ROOT/'build').resolve())
    if output.exists():raise ValueError('Fresh ignored output required')
    output.mkdir(parents=True,mode=0o700)
    own_bytes=Path(__file__).read_bytes()
    record=builder.prepare(runtime,output/'compiled',glslang,ROOT/'tests/build34_radv_runtime_platform.cpp')
    if record['CPU_platform'] is not True:raise RuntimeError('Only CPU platform processes may be run/terminated by this harness')
    binary=output/'compiled/build34-radv-runtime-probe'
    library=output/'compiled/libvulkan_radeon.dylib'
    for name,digest in record['binaries_sha256'].items():
        if builder.sha(output/'compiled'/name)!=digest:raise RuntimeError('CPU binary drift')
    cases={'ok':(2,2),'missing-pci':(0,0),'build41':(0,0),'build42':(0,0),'minor':(0,0),'hung':(0,0),
           'bo-error':(0,0),'bo-size':(0,0),'submit-first':(1,0),'submit-second':(2,1),'zero-sequence':(1,0),
           'wait-error':(1,0),'bad-retirement':(1,0),'stale':(2,1),'guard-byte':(2,1)}
    results={}
    for name,(submits,passes) in cases.items():
        stdout,stderr=output/(name+'.stdout'),output/(name+'.stderr')
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(output/'compiled/home'),'LANG':'C','LC_ALL':'C','NULLARC_CPU_CASE':name}
        with stdout.open('xb') as out,stderr.open('xb') as err:
            process=subprocess.Popen([str(binary),'--run-tail',str(library)],env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
            held=False
            try:
                end=time.monotonic()+45
                while time.monotonic()<end:
                    code=process.poll()
                    text=stderr.read_text()
                    if 'CPU-FIXTURE-HOLD:' in text:
                        held=True; break
                    if code is not None:break
                    time.sleep(.05)
                if name=='ok':
                    if held or process.poll()!=0:raise RuntimeError('Complete Vulkan CPU probe did not pass; inspect '+name+' logs')
                    text=stdout.read_text()
                    match=re.search(r'RUNTIME-PASS: real Vulkan compute path; opens=1 closes=1 submits=2 arena_passes=2 tail=1 reused_changed_IB=1 CPU_platform=1 first_IB_bytes=(\d+) second_IB_bytes=(\d+); no desktop/FPS acceptance\n$',text)
                    if not match or min(int(match[1]),int(match[2]))<=0:raise RuntimeError('Missing complete CPU-only runtime evidence')
                    reused_sizes={'first':int(match[1]),'second':int(match[2])}
                    rows=[json.loads(line) for line in text.splitlines() if line.startswith('{')]
                    if len(rows)!=2 or [row['arena_pass'] for row in rows]!=[0,1] or any(row['whole_bytes']!=16384 for row in rows):
                        raise RuntimeError('Incomplete CPU arena verification')
                    if any(type(row['last_sequence']) is not int or type(row['retired_sequence']) is not int or
                           not 0 < row['last_sequence'] <= row['retired_sequence'] for row in rows) or rows[1]['last_sequence']<=rows[0]['last_sequence']:
                        raise RuntimeError('Incomplete positive native retirement evidence')
                else:
                    if not held or process.poll() is not None:raise RuntimeError('Fault did not retain the CPU fixture process: '+name)
                    match=re.search(r'CPU-FIXTURE-HOLD: opens=(\d+) closes=(\d+) fake_submits=(\d+) arena_passes=(\d+)\n',text)
                    if not match or int(match[2])!=0 or int(match[3])!=submits or int(match[4])!=passes:
                        raise RuntimeError('Incorrect fault boundary: '+name)
                results[name]={'passed':True,'CPU_hold':held,'fake_native_submissions':submits,'whole_arena_passes':passes}
            finally:
                # Only this hash-verified build with every platform op replaced by
                # CPU fixtures is terminated. Never use this for a native GPU probe.
                if process.poll() is None:
                    process.terminate();process.wait(timeout=5)
    if Path(__file__).read_bytes()!=own_bytes:raise RuntimeError('CPU harness input drift')
    for name,digest in record['binaries_sha256'].items():
        if builder.sha(output/'compiled'/name)!=digest:raise RuntimeError('CPU binary changed during cases')
    report={'result':'passed','CPU_cases':results,'real_full_Vulkan_probe':True,'ASan_UBSan_on_probe_guard_and_platform':True,
            'reused_IB_bytes':reused_sizes,
            'release_RADV_sanitizer_instrumented':False,'platform_faked':True,'output_oracle_not_GPU_ISA_or_coherency_simulation':True,
            'GPU_executed':False,'installed':False,'preparation':record,
            'harness_sha256':hashlib.sha256(own_bytes).hexdigest()}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'result':'passed','CPU_cases':len(results),'actual_Vulkan_probe':True,'GPU_executed':False}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--glslang',type=Path,required=True)
    args=parser.parse_args();test(args.runtime,args.out,args.glslang)
