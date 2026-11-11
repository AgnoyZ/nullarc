"""Reproduce pinned upstream PR builds on Intel macOS; never install or load drivers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

BASE = "8aba872560a3c9b7dc7a0ddebfad001c6dddf315"
HEADS = {
    6: "55764a0b69658a92870fc2b75e0be3a695382e38",
    7: "394f162ae7bf5cc9d57bb673a9a6b326c46c325e",
    8: "5a8a088011946c8089bb27e10d0dba117bf1b48e",
    9: "c9da802a8dbf3753fa15b5cd903934712c3c80f6",
}
VARIANTS = {
    "baseline": [], "pr6": [6], "pr7": [7], "pr8": [8], "pr9": [9],
    "pr6-7": [6, 7], "pr6-7-8": [6, 7, 8], "pr6-7-8-9": [6, 7, 8, 9],
}
SDK = "3f750085caa17ec3a7880f11c11bf4f48cd6a164"
VULKAN = "6802bb4733b63ed5efd3adb308a6c885ef180ea1"
RESOLVABLE = {".github/workflows/ci.yml", "Makefile", "src/nmplugin/NVMTLObjects.m"}
SANITIZERS = "-std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer"


class CommandFailure(RuntimeError):
    def __init__(self, args, code, output):
        super().__init__(f"Command failed ({code}): {args[0]}")
        self.code, self.output = code, output


def run(args, cwd, env=None):
    print("RUN " + " ".join(map(str, args)), flush=True)
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    print(result.stdout, end="", flush=True)
    if result.returncode:
        raise CommandFailure(args, result.returncode, result.stdout)
    return result.stdout


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True,
                                   encoding="utf-8").strip()


def resolve_additions(path, relative):
    """Resolve only the reviewed additive conflicts; reject any other shape."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^<<<<<<< [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*\n?",
                         re.MULTILINE | re.DOTALL)
    count = 0

    def both(match):
        nonlocal count
        count += 1
        left, right = match.group(1), match.group(2)
        if relative == "src/nmplugin/NVMTLObjects.m":
            allowed = {'#import "nvmtl_sampler_key.h"', '#import "nvmtl_surface_key.h"'}
            lines = (left + right).splitlines()
            if not lines or any(line not in allowed for line in lines):
                raise RuntimeError("Unexpected production-code merge conflict")
            return "\n".join(dict.fromkeys(lines)) + "\n"
        # These branches only append separate test jobs/targets at the same EOF.
        if relative == "Makefile":
            if not left.lstrip().startswith((".PHONY:", "$(TEST_BIN_DIR)/test_panel_timing:")):
                raise RuntimeError("Unexpected Makefile conflict")
            if not right.lstrip().startswith((".PHONY:", "$(TEST_BIN_DIR)/test_panel_timing:")):
                raise RuntimeError("Unexpected Makefile conflict")
        else:
            raise RuntimeError("Unreviewed conflict path")
        return left.rstrip("\n") + "\n\n" + right

    text = pattern.sub(both, text)
    if not count or re.search(r"^(<<<<<<<|=======|>>>>>>>)", text, re.MULTILINE):
        raise RuntimeError(f"Unresolved conflict: {relative}")
    path.write_text(text, encoding="utf-8", newline="\n")
    return count


def prepare(root, variant):
    if git(root, "status", "--porcelain"):
        raise RuntimeError("Candidate checkout must be clean")
    prs = VARIANTS[variant]
    for number in prs:
        if git(root, "merge-base", BASE, HEADS[number]) != BASE:
            raise RuntimeError("PR no longer has the pinned baseline")
    run(["git", "checkout", "--detach", HEADS[prs[0]] if prs else BASE], root)
    resolutions = []
    identity = {**os.environ, "GIT_AUTHOR_NAME": "github-actions[bot]",
                "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                "GIT_COMMITTER_NAME": "github-actions[bot]",
                "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    for position, number in enumerate(prs[1:], 1):
        result = subprocess.run(["git", "-c", "merge.conflictStyle=merge", "merge", "--no-commit", "--no-ff", HEADS[number]],
                                cwd=root, env=identity, capture_output=True, text=True)
        print(result.stdout + result.stderr, flush=True)
        conflicts = git(root, "diff", "--name-only", "--diff-filter=U").splitlines()
        if result.returncode and not conflicts:
            raise RuntimeError("Merge failed without resolvable conflicts")
        for name in conflicts:
            if name not in RESOLVABLE:
                raise RuntimeError(f"Unreviewed merge conflict: {name}")
            if name == ".github/workflows/ci.yml":
                # Git aligns the common checkout steps inside different jobs.
                # Preserve each entire appended job, rather than joining hunks.
                base_ci = git(root, "show", BASE + ":" + name) + "\n"
                combined = base_ci
                for included in prs[:position + 1]:
                    candidate_ci = git(root, "show", HEADS[included] + ":" + name) + "\n"
                    if not candidate_ci.startswith(base_ci):
                        raise RuntimeError("CI changes are no longer append-only")
                    combined += candidate_ci[len(base_ci):]
                (root / name).write_text(combined, encoding="utf-8", newline="\n")
                count = 1
            else:
                count = resolve_additions(root / name, name)
            run(["git", "add", "--", name], root)
            resolutions.append({"pr": number, "path": name, "blocks": count})
        run(["git", "diff", "--cached", "--check"], root)
        run(["git", "commit", "--no-gpg-sign", "-m", f"CI-only integration of PR #{number}"], root, identity)
    return {"baseline": BASE, "prs": {str(n): HEADS[n] for n in prs},
            "source_commit": git(root, "rev-parse", "HEAD"),
            "source_tree": git(root, "rev-parse", "HEAD^{tree}"),
            "conflict_resolutions": resolutions}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--vulkan", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = args.source.resolve()
    if root == Path(__file__).resolve().parents[1]:
        parser.error("Use a separate disposable candidate checkout")
    if not args.prepare_only and (platform.system() != "Darwin" or platform.machine() != "x86_64"):
        parser.error("Native validation requires Intel macOS; Windows preparation is not a build pass")
    report = {"variant": args.variant, "hardware_tested": False, "deployment_performed": False,
              "binary_artifacts_uploaded": False, "phases": [], "failed_tests": [], "status": "failed"}
    try:
        report.update(prepare(root, args.variant))
        if args.prepare_only:
            report["status"] = "prepared-only-not-built"
            print(json.dumps(report, indent=2))
            return
        if not args.sdk or not args.vulkan:
            parser.error("Native validation requires --sdk and --vulkan")
        sdk, vulkan = args.sdk.resolve(), args.vulkan.resolve()
        if git(sdk, "rev-parse", "HEAD") != SDK or git(vulkan, "rev-parse", "HEAD") != VULKAN:
            raise RuntimeError("Build dependency does not match its reviewed pin")
        report.update({"sdk_commit": SDK, "vulkan_headers_commit": VULKAN,
                       "os": run(["sw_vers"], root).strip(), "architecture": platform.machine(),
                       "compiler": run(["xcrun", "clang", "--version"], root).strip()})
        env = {key: value for key, value in os.environ.items() if not key.startswith("NVMTL_")}
        env.update({"REQUIRE_FIXTURES": "1", "CPPFLAGS": "-I" + str(vulkan / "include"),
                    "ASAN_OPTIONS": "halt_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1"})

        def phase(name, command, test=False):
            try:
                text = run(command, root, env)
            except CommandFailure as error:
                if not test:
                    raise
                report["failed_tests"].append({"phase": name, "exit_code": error.code,
                                                "output_sha256": digest(error.output.encode()),
                                                "last_lines": error.output.splitlines()[-8:]})
                return error.output
            report["phases"].append(name)
            return text

        phase("real-firmware-fixtures", ["make", "fixtures"])
        report["firmware_sha256"] = {
            path.name: digest(path.read_bytes()) for path in sorted((root / "tests/fixtures/phoenix").glob("*.bin"))
        }
        phase("unit-tests-asan-ubsan", ["make", "test", "CXX=clang++", "CXXFLAGS=" + SANITIZERS], test=True)
        phase("phoenix-profile", [sys.executable, "tests/test_phx_profile.py"], test=True)
        # make test stops at the existing wait-sequence assertion on this host;
        # execute the already-built timing suite independently as well.
        if 9 in VARIANTS[args.variant]:
            phase("panel-timing-asan-ubsan", ["build/tests/test_panel_timing"], test=True)
        for n, target in ((6, "sampler-key"), (7, "surface-key"), (8, "descriptor-mask")):
            if n in VARIANTS[args.variant]:
                phase(target + "-asan-ubsan", ["make", "test-nmplugin-" + target], test=True)
        plugin_log = phase("native-metal-plugin", ["sh", "src/nmplugin/build.sh", vulkan / "include"])
        warnings = sorted(re.findall(r"warning: (.*)", plugin_log))
        report["plugin_warnings"] = {"count": len(warnings),
                                     "messages_sha256": digest("\n".join(warnings).encode())}
        phase("native-phxbringup", ["sh", "src/phxbringup/build.sh", sdk])
        phase("native-phxaccel", ["sh", "src/phxaccel/build.sh", sdk])
        # Import the downstream binary inspector, but build the exact PR sources above.
        from verify_artifacts import inspect_macho, inspect_kext
        plugin = root / "src/nmplugin/NVMTLDriver.new"
        report["plugin"] = inspect_macho(plugin, 8)
        symbols = phase("exported-symbols", ["nm", "-gjU", plugin]).splitlines()
        report["plugin_exports"] = {"count": len(set(symbols)),
                                    "names_sha256": digest("\n".join(sorted(set(symbols))).encode())}
        for component, identifier in (("PhxBringup", "org.drip.PhxBringup"), ("PhxAccel", "com.luuumi.PhxAccel")):
            bundle = root / "src" / component.lower() / "build" / (component + ".kext")
            phase(component + "-sign", ["codesign", "--force", "--sign", "-", bundle])
            phase(component + "-verify", ["codesign", "--verify", "--strict", bundle])
            report[component] = inspect_kext(bundle, identifier)
        phase("plugin-sign", ["codesign", "--force", "--sign", "-", plugin])
        phase("plugin-signature-verify", ["codesign", "--verify", "--strict", plugin])
        report["plugin"] = inspect_macho(plugin, 8)
        phase("tracked-source-integrity", ["git", "diff", "--exit-code", "HEAD", "--", "src", "tests", "Makefile"])
        report["native_build_status"] = "passed"
        if report["failed_tests"]:
            report["status"] = "native-build-passed-tests-failed"
            raise RuntimeError("Original tests failed; native builds and independent tests completed; see report")
        report["status"] = "passed"
    finally:
        if not args.prepare_only:
            serialized = json.dumps(report, sort_keys=True)
            print("NULLARC_NATIVE_REPORT=" + serialized, flush=True)
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a", encoding="utf-8") as stream:
                    stream.write(f"## {args.variant}: {report['status']}\n\n")
                    stream.write("Native compiler/CPU-test evidence only; no target GPU execution or deployment.\n\n")
                    stream.write("```json\n" + json.dumps(report, indent=2) + "\n```\n")


if __name__ == "__main__":
    main()
