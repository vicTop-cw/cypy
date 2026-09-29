#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 04.

Target: cypy_hook/hook.py:345  (and its consumers at :346-347, :402-404, :448)

Claim: the built extension's filename is computed as
        f"{module_name}.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd"
i.e. the platform tag `win_amd64` and the `.pyd` suffix are string literals.
Nothing in cypy_hook/, cypyc/ or cypy_bridge/ ever reads
sysconfig.get_config_var('EXT_SUFFIX') / importlib.machinery.EXTENSION_SUFFIXES,
so the name is independent of the ABI tag the toolchain actually used.  It
coincides only on CPython x64 Windows non-free-threaded builds.  On Linux /
macOS (`.cpython-31X-<triplet>.so`), on win32, and on a free-threaded
`3.13t` build (`.cp313t-win_amd64.pyd`) the resulting file is never the name
CPython's ExtensionFileLoader will accept -> the extension is never found.
Consequences inside the hook: :347 `is_locked` is always False for the real
artifact, :402-404 copies the produced file to the wrong name, and the
module-name regex at :448 cannot parse any non-`cp<XY>-<tag>` filename, so
run_module()/CypyLoader.exec_module() derive a garbage module name.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import importlib.machinery
import os
import re
import shutil
import subprocess
import sys
import sysconfig

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)
SCRATCH = os.path.join(HERE, "scratch", "codegen", "hook04")

HOOK_PY = os.path.join(REPO, "cypy_hook", "hook.py")

if hasattr(sys.stdout, "reconfigure"):                       # console may be GBK
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def z(b):
    """Decode subprocess output and make it print-safe on any console codepage."""
    if isinstance(b, bytes):
        for enc in ("utf-8", "gbk", "cp936"):
            try:
                t = b.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            t = b.decode("utf-8", "replace")
    else:
        t = b or ""
    return t.encode("ascii", "replace").decode("ascii")


# Realistic CPython extension filenames per platform/ABI, taken from CPython's
# own naming scheme (sysconfig EXT_SUFFIX on each target).
FOREIGN = [
    ("Linux glibc x86_64, 3.13",      "hello.cpython-313-x86_64-linux-gnu.so"),
    ("Linux glibc aarch64, 3.13",     "hello.cpython-313-aarch64-linux-gnu.so"),
    ("Linux musl x86_64, 3.12",       "hello.cpython-312-x86_64-linux-musl.so"),
    ("macOS arm64, 3.12",             "hello.cpython-312-darwin.so"),
    ("free-threaded 3.13t win_amd64", "hello.cp313t-win_amd64.pyd"),
    ("free-threaded 3.13t linux",     "hello.cp313t-x86_64-linux-gnu.so"),
    ("Windows 32-bit 3.11",           "hello.cp311-win32.pyd"),
    ("stable ABI 3.12 win_amd64",     "hello.abi3.pyd"),
]


def hook_formula(module_name, major, minor):
    """Re-execute the exact expression from hook.py:345.

    HARNESS-FIX(T0r61.4.2): 修复后的 hook 不再拼平台字面量，而是由解释器自己的
    EXT_SUFFIX 推导产物名。这里优先调用真正的实现；导入不到时才退回历史的字面量
    公式（那样本单元仍然像修复前一样判为复现）。
    """
    try:
        sys.path.insert(0, REPO)
        from cypy_hook.hook import extension_filename
        return extension_filename(module_name)
    except Exception:
        return "%s.cp%s%s-win_amd64.pyd" % (module_name, major, minor)


def main():
    os.makedirs(SCRATCH, exist_ok=True)
    reproduced = []
    text = open(HOOK_PY, encoding="utf-8").read()
    lines = text.splitlines()

    print("=" * 74)
    print("PART 1 - the naming expression is a platform literal (cypy_hook/hook.py)")
    print("=" * 74)
    m = re.search(r"target_pyd_name\s*=\s*f\"([^\"]*)\"", text)

    # HARNESS-FIX(T0r61.4.2): 原来用写死的行号 lines[344]/lines[401] 取证，
    # 任何编辑都会让它指到无关行；改为按语句内容锚定。
    for label, pattern in (
        ("naming statement", r"target_pyd_name\s*="),
        ("target path", r"target_pyd_path\s*="),
        ("lock probe", r"is_locked\s*="),
        ("artifact walk", r"for root, dirs, files in os\.walk\(search_dir\)"),
        ("reported path", r"result\.pyd_path\s*=\s*(produced|dest|target_pyd_path)"),
    ):
        idx = next((i for i, ln in enumerate(lines) if re.search(pattern, ln)), None)
        print("  hook.py:%s [%s] | %s" % (
            (idx + 1) if idx is not None else "?", label,
            lines[idx].strip() if idx is not None else "(not found)"))

    print("  literal format string extracted: %r" % (m.group(1) if m else None))
    print("  inputs to the name: {module_name, sys.version_info.major, "
          "sys.version_info.minor} + the literals '-win_amd64' and '.pyd'")
    if m and "win_amd64" in m.group(1) and "pyd" in m.group(1):
        reproduced.append("hook.py:345 embeds the literal platform tag 'win_amd64' and "
                          "suffix '.pyd' in the built-extension filename")

    print()
    print("  independence from sysconfig: occurrences of 'sysconfig' / 'EXT_SUFFIX' "
          "in the compiler packages")
    total = {}
    for pkg in ("cypy_hook", "cypyc", "cypy_bridge"):
        d = os.path.join(REPO, pkg)
        hits = 0
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for f in files:
                if f.endswith(".py"):
                    t = open(os.path.join(root, f), encoding="utf-8",
                             errors="replace").read()
                    hits += len(re.findall(r"\bsysconfig\b|\bEXT_SUFFIX\b", t))
        total[pkg] = hits
    print("    %s" % total)
    if sum(total.values()) == 0:
        reproduced.append("zero references to sysconfig/EXT_SUFFIX anywhere in "
                          "cypy_hook/, cypyc/, cypy_bridge/ -> the tag cannot track "
                          "the interpreter's real ABI suffix")
    print("  this interpreter's authoritative answers:")
    print("    sysconfig.get_config_var('EXT_SUFFIX') = %s"
          % sysconfig.get_config_var("EXT_SUFFIX"))
    print("    importlib.machinery.EXTENSION_SUFFIXES = %s"
          % importlib.machinery.EXTENSION_SUFFIXES)
    print("    sysconfig.get_platform()               = %s" % sysconfig.get_platform())

    print()
    print("=" * 74)
    print("PART 2 - hook formula vs. the name CPython would actually load")
    print("=" * 74)
    print("  %-30s | %-34s | %-38s | loadable" % ("target", "hook.py:345 computes", "required EXT_SUFFIX name"))
    cur = hook_formula("hello", sys.version_info.major, sys.version_info.minor)
    ext = sysconfig.get_config_var("EXT_SUFFIX")
    print("  %-30s | %-34s | %-38s | %s"
          % ("THIS interpreter", cur, "hello" + ext, cur == "hello" + ext))
    for label, required in FOREIGN:
        # what the hook would emit for the same module on that build
        mm = re.search(r"cp(\d)(\d+)", required)
        maj, mino = (mm.group(1), mm.group(2)) if mm else ("3", "13")
        emitted = hook_formula("hello", maj, mino)
        loadable = emitted == required
        print("  %-30s | %-34s | %-38s | %s" % (label, emitted, required, loadable))
        if not loadable:
            pass
    n_bad = sum(1 for _, req in FOREIGN if hook_formula("hello", 3, 13) != req)
    # HARNESS-FIX(T0r61.4.2): 这里的 reproduced.append(...) 原来是 **无条件** 执行的，
    # 于是无论产品代码怎么改，本单元都只能判为“复现”，永远给不出 exit 0。
    # 断言改为审计的真实命题：hook 推导出的名字必须等于本解释器 EXT_SUFFIX 要求的名字；
    # 平台不同的 FOREIGN 行只是说明（这台机器上没有对应解释器可跑，见结尾 NOTE）。
    if cur != "hello" + ext or hook_formula("hello", sys.version_info.major,
                                           sys.version_info.minor) != "hello" + ext:
        reproduced.append("the hook derives %r while this interpreter requires %r "
                          "(%d/%d realistic non-Windows-x64 / free-threaded / win32 / "
                          "abi3 targets produce a filename the hook never searches)"
                          % (hook_formula("hello", sys.version_info.major,
                                          sys.version_info.minor), "hello" + ext,
                             n_bad, len(FOREIGN)))

    print()
    print("=" * 74)
    print("PART 3 - the module-name extraction at hook.py:448 on real filenames")
    print("=" * 74)
    rx_src = re.search(r"match\s*=\s*re\.match\(r'(\^\S+?)',", text)
    pattern = rx_src.group(1) if rx_src else r"^([a-zA-Z_][a-zA-Z0-9_]*)(\.cp\d+-\w+)?$"
    print("  regex taken from hook.py:448: r'%s'" % pattern)
    rx = re.compile(pattern)
    print("  %-46s | %s" % ("basename of produced file", "module_name derived by :448-452"))
    bad = 0
    for _, req in FOREIGN + [("this windows build", cur)]:
        stem = re.sub(r"\.(pyd|so)$", "", req)
        mm = rx.match(stem)
        got = mm.group(1) if mm else stem
        okflag = "OK" if got == "hello" else "*** WRONG ***"
        if got != "hello":
            bad += 1
        print("  %-46s | %-22s %s" % (req, got, okflag))
    if bad:
        reproduced.append("hook.py:448 regex fails to strip the tag for %d filenames "
                          "(all Linux/macOS/musl/free-threaded/abi3 shapes) -> "
                          "run_module()/CypyLoader get a dotted junk module name" % bad)

    print()
    print("=" * 74)
    print("PART 4 - real build through cypy_hook (examples/hello.cypy -> scratch)")
    print("=" * 74)
    src = os.path.join(REPO, "examples", "hello.cypy")
    outdir = os.path.join(SCRATCH, "out")
    os.makedirs(outdir, exist_ok=True)
    code = (
        "import os, sys, json\n"
        "sys.path.insert(0, r'%s')\n"
        "from cypy_hook.hook import CypyHook\n"
        "r = CypyHook().compile_to_pyd(r'%s', output_dir=r'%s')\n"
        "print(json.dumps({'success': r.success, 'pyd_path': r.pyd_path,\n"
        "                  'errors': r.errors[:3], 'steps': r.steps[-3:]}))\n"
        % (REPO, src, outdir))
    p = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                       capture_output=True, timeout=290)
    txt = z((p.stdout or b"") + (p.stderr or b"")).strip()
    print("  hook subprocess exit %s" % p.returncode)
    for ln in txt.splitlines()[-8:]:
        print("   " + ln)

    produced_by_toolchain, reported = None, None
    if os.path.isdir(outdir):
        found = []
        for root, dirs, files in os.walk(outdir):
            for f in files:
                if f.endswith((".pyd", ".so")):
                    found.append(os.path.join(root, f))
        print("  extension files present after the build:")
        for f in sorted(found):
            rel = os.path.relpath(f, outdir).replace(os.sep, "/")
            print("     %s" % rel)
            if "/build/" in "/" + rel:
                produced_by_toolchain = rel
            else:
                reported = rel
        print("  produced by the compiler (distutils/setuptools, EXT_SUFFIX-derived): %s"
              % produced_by_toolchain)
        print("  reported by hook.py:404 as result.pyd_path ......................... %s"
              % reported)
        print("  hook.py:345 formula for the same module ............................ %s"
              % hook_formula("hello", sys.version_info.major, sys.version_info.minor))

    # Decisive: an extension whose filename does not use THIS interpreter's
    # EXT_SUFFIX is not importable, which is what a Linux/macOS/free-threaded
    # build of the same source would leave behind.
    real = os.path.join(outdir, "hello.cp313-win_amd64.pyd")
    if os.path.exists(real):
        for alias in ("hello.cp313t-win_amd64.pyd",
                      "hello.cpython-313-x86_64-linux-gnu.so"):
            ap = os.path.join(outdir, alias)
            if not os.path.exists(ap):
                import shutil as _sh
                _sh.copy2(real, ap)
            probe = ("import sys; sys.path.insert(0, r'%s')\n"
                     "import importlib.util as u\n"
                     "spec = u.spec_from_file_location('hello', r'%s')\n"
                     "print('loader=', None if spec is None or spec.loader is None else "
                     "type(spec.loader).__name__)\n"
                     "try:\n"
                     "    m = u.module_from_spec(spec); spec.loader.exec_module(m)\n"
                     "    print('IMPORTED OK')\n"
                     "except Exception as e:\n"
                     "    print('IMPORT FAILED:', type(e).__name__, str(e)[:120])\n"
                     % (outdir, ap))
            q = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                               timeout=120, cwd=outdir)
            r = z((q.stdout or b"") + (q.stderr or b"")).strip()
            print("  loading the same bytes under the name hook.py:345 would produce on a "
                  "foreign ABI\n    %s -> %s" % (alias, " / ".join(r.splitlines()[-2:])))
            # HARNESS-FIX(T0r61.4.2): 只有当这个别名本身就是“本解释器会接受的名字”时，
            # 加载失败才说明 hook 命名有错；把 Windows 上的 .so 判成命名缺陷是平台常量
            # （CPython 在 Windows 的 EXTENSION_SUFFIXES 里没有 .so），只能作为说明。
            loadable_here = any(alias.endswith(s) for s in
                                importlib.machinery.EXTENSION_SUFFIXES)
            if loadable_here and ("IMPORT FAILED" in r or "loader= None" in r):
                reproduced.append("file named %s (what the hook's tag formula yields on "
                                  "that platform) cannot be loaded by this interpreter"
                                  % alias)
    else:
        print("  (real build artifact not present; PART 4 conclusions rest on 1-3)")

    print()
    print("=" * 74)
    print("PART 5 - name-based lookup: is a foreign-tag filename ever FOUND by import?")
    print("=" * 74)
    print("  (an explicit-path spec_from_file_location ignores the tag, so the real")
    print("   test is what `import hello` - and therefore the meta-path finder - sees)")
    probe_dir = os.path.join(SCRATCH, "lookup")
    if os.path.isdir(probe_dir):
        shutil.rmtree(probe_dir, ignore_errors=True)
    os.makedirs(probe_dir, exist_ok=True)
    if os.path.exists(real):
        # ONLY a foreign-tag file is present, exactly as a Linux/macOS/free-threaded
        # build placed there by hook.py:402-404 while reporting its own path.
        for alias in ("hello.cpython-313-x86_64-linux-gnu.so",
                      "hello.cpython-313-darwin.so",
                      "hello.cp313t-win_amd64.pyd"):
            dst = os.path.join(probe_dir, alias)
            _sh_copy = __import__("shutil").copy2
            _sh_copy(real, dst)
            code = ("import sys; sys.path.insert(0, r'%s')\n"
                    "try:\n"
                    "    import hello\n"
                    "    print('import hello -> FOUND', hello.__file__)\n"
                    "except ModuleNotFoundError as e:\n"
                    "    print('import hello -> NOT FOUND:', e)\n" % probe_dir)
            q = subprocess.run([sys.executable, "-c", code], capture_output=True,
                               timeout=120, cwd=probe_dir)
            r = z((q.stdout or b"") + (q.stderr or b"")).strip()
            print("   present: %-40s | %s" % (alias, r.splitlines()[-1]))
            # HARNESS-FIX(T0r61.4.2): 只有 “本解释器会接受的那个确切文件名却仍然找不到”
            # 才是命名缺陷。在 Windows 上 `import hello` 找不到 Linux/macOS 或自由线程
            # 标签的文件是平台常量（FileFinder 只接受 hello+EXT_SUFFIX/.pyd/.dll），
            # 不能当作产品结论。
            name_here = any(alias == "hello" + s
                            for s in importlib.machinery.EXTENSION_SUFFIXES)
            if "NOT FOUND" in r and name_here:
                reproduced.append("with only %s on sys.path `import hello` raises "
                                  "ModuleNotFoundError - a built extension named "
                                  "independently of EXT_SUFFIX is never found" % alias)
            os.remove(dst)
        # control: the correct name IS found
        __import__("shutil").copy2(
            real, os.path.join(probe_dir, "hello" + ext))
        code = ("import sys; sys.path.insert(0, r'%s')\n"
                "import hello; print('import hello -> FOUND', "
                "hello.__file__.split(os.sep)[-1])" % probe_dir)
        q = subprocess.run([sys.executable, "-c", "import os;" + code],
                           capture_output=True, timeout=120, cwd=probe_dir)
        print("   control, correct name %-18s | %s"
              % ("hello" + ext,
                 z((q.stdout or b"") + (q.stderr or b"")).strip().splitlines()[-1]))

    print()
    print("=" * 74)
    print("NOTE: no Linux/macOS interpreter is available on this machine, so the "
          "cross-platform\n"
          "      conclusion is established at the emitted-filename / loadability "
          "level, not by\n"
          "      running a foreign-ABI build.")
    if reproduced:
        print("RESULT: REPRODUCED (%d confirmations)" % len(reproduced))
        for r in reproduced:
            print("  * " + r)
        return 1
    print("RESULT: NOT REPRODUCED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        sys.stderr.write("HARNESS ERROR\n" + traceback.format_exc())
        sys.exit(3)
