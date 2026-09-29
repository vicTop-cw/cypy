"""R4-验证 法⑤：转结的两件真编译实测（BUG-69 / D18）。

寻虫环在 BUG-69 上留了半句「真编译验证本轮未跑」，R4-修复 把它转结到这里；D18（文档说
`transpile_file` / `compile_to_pyd` 默认增量编译、源未变会复用 `.pyd`）当时被标成
`not_measured`。本件把两条都打到**真编译器**面前测：

· 编译器先在场上自证（能编一个合法 C；不能编就把「打不到」写成主张，别往下结论）；
· 所有产物落 `.fist-loop-20260927/verify_r4_tmp/compile/`，工作树与 `tests/golden` 前后逐字比 sha；
· 合成违例（模块级 `if`）与合法对照成对出现——只有合成违例被抓、合法对照不被抓，
  「编译器拒绝了生成物里的模块级 if」这句才成立。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRATCH = HERE / "verify_r4_tmp" / "compile"
OUT = HERE / "verify_r4_compile.json"
GOLDEN_SH = ROOT / "scripts" / "e2e_golden.sh"
CHECKS: list = []
REFUSE: list = []
SRC_CYPY = ('def hello() -> str:\n    return "hi"\n\n'
            'if __name__ == "__main__":\n    print(hello())\n')

CACHE_DRIVER = r'''
import json, os, sys, time
sys.path.insert(0, %(root)r)
from cypy_hook.hook import CypyHook, CypyCacheManager
OUT = %(out)r
SRC = %(src)r
hook = CypyHook()
cm = CypyCacheManager()
os.makedirs(OUT, exist_ok=True)


def snap():
    names = sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []
    mtime = {n: os.stat(os.path.join(OUT, n)).st_mtime_ns
             for n in names if n.endswith((".pyd", ".c", ".pyx"))}
    return {"cwd": os.getcwd(), "pyd": names, "pyd_mtime_ns": mtime,
            "is_stale": cm.is_stale(SRC), "cached": cm.get_cached_pyd(SRC),
            "caller_cwd_cache": os.path.isdir(os.path.join(os.getcwd(), "__pycache__"))}


def res(r):
    return {"success": r.success, "pyd_path": getattr(r, "pyd_path", None),
            "pyd_attrs_on_result": sorted(k for k in vars(r) if "pyd" in k.lower()),
            "errors": list(r.errors or [])[:3]}


before = snap()
t0 = time.perf_counter()
r1 = hook.compile_to_pyd(SRC, output_dir=OUT, force_recompile=False)
d1 = time.perf_counter() - t0
mid = snap()
t2 = time.perf_counter()
r2 = hook.compile_to_pyd(SRC, output_dir=OUT, force_recompile=False)
d2 = time.perf_counter() - t2
after = snap()
print(json.dumps({"before": before, "mid": mid, "after": after,
                  "first": res(r1), "second": res(r2),
                  "dur_first": round(d1, 3), "dur_second": round(d2, 3)},
                 ensure_ascii=False))
'''


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def decode(data: bytes) -> str:
    for enc in ("utf-8", "cp936", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def tree_fingerprint(paths: list) -> dict:
    """把 golden 面拍成一个 sha 清单：改动（含删文件）一律看得见。"""
    files = {}
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    files[str(f.relative_to(ROOT)).replace("\\", "/")] = \
                        hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        elif p.is_file():
            files[str(p.relative_to(ROOT)).replace("\\", "/")] = \
                hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return {"files_total": len(files), "digest": hashlib.sha256(
        json.dumps(files, sort_keys=True).encode()).hexdigest()[:16], "files": files}


def golden_paths() -> list:
    """golden 面 = `examples/*.out`（e2e_golden.sh 就按这个配对）+ 脚本本身。"""
    return sorted((ROOT / "examples").glob("*.out")) + [GOLDEN_SH]


def untracked(paths: list) -> list:
    """被看住的目录里现在有哪些未跟踪文件（前后各数一次，差集就是本轮造的东西）。"""
    r = subprocess.run(["git", "status", "--porcelain", "--", *paths], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return sorted(ln[3:] for ln in r.stdout.splitlines() if ln.startswith("??"))


def cl_compile(c_path: Path, include_dirs: list, label: str) -> dict:
    cl = shutil.which("cl") or shutil.which("cl.exe")
    args = [cl, "/nologo", "/c", "/Tc", str(c_path)] + [f"/I{d}" for d in include_dirs]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run(args, cwd=str(c_path.parent), capture_output=True, env=env, timeout=300)
    text = decode(p.stdout or b"") + decode(p.stderr or b"")
    errs = [ln for ln in text.splitlines() if "error" in ln.lower()]
    return {"id": label, "command_verbatim": " ".join(args), "rc": p.returncode,
            "error_lines": errs[:8], "banner": next((ln for ln in text.splitlines()
                                                     if "Microsoft (R) C/C++" in ln), ""),
            "text_tail": text[-500:]}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    golden_before = tree_fingerprint(golden_paths())
    watched = ["tests/golden", "cypyc", "cypy_bridge", "cypy_hook", "scripts", "PROJECT-SPEC",
               "SYNTAX", "docs"]
    untracked_before = untracked(watched)

    cl = shutil.which("cl") or shutil.which("cl.exe")
    py_inc = sysconfig.get_paths()["include"]
    attempts = []

    # ① 工具链自证：合法 C 必须编得过，否则后面的「编译器拒了」一句不成立
    ok_c = SCRATCH / "canary_valid.c"
    ok_c.write_text("int add(int a, int b) { return a + b; }\n", encoding="utf-8")
    a1 = cl_compile(ok_c, [], "canary-valid-c")
    attempts.append(a1)
    check("工具链自证：合法 C 必须编得过", a1["rc"], 0, a1["text_tail"][-200:])

    # ② 合成违例：模块级 if 必须被拒（与③同形，但这是我手写的，不来自产品）
    bad_c = SCRATCH / "canary_module_if.c"
    bad_c.write_text("int x;\nif ((x == 1)) {\n  x = 2;\n}\n", encoding="utf-8")
    a2 = cl_compile(bad_c, [], "canary-module-level-if")
    attempts.append(a2)
    caught = a2["rc"] != 0 and any("C2059" in e or "if" in e for e in a2["error_lines"])
    check("合成违例必须被编译器抓住（否则拒判是空的）", caught, True,
          f"rc={a2['rc']} errs={a2['error_lines']}")

    # ③ 产品生成物：bridge 的 C 里那个模块级 if（BUG-69 的现场）
    drv = SCRATCH / "gen_c.py"
    drv.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from cypyc.parser.lexer import Lexer\n"
        "from cypyc.parser.parser import Parser\n"
        "from cypy_bridge.compiler import CCodeGenerator\n"
        "from pathlib import Path\n"
        f"src = Path({str(SCRATCH / 'probe69.cypy')!r}).read_text(encoding='utf-8')\n"
        "ast = Parser(list(Lexer(src).tokenize())).parse()\n"
        "code = CCodeGenerator().generate(ast, 'probe69')\n"
        f"Path({str(SCRATCH / 'probe69.c')!r}).write_text(code, encoding='utf-8', newline="
        "'\\n')\n"
        "print(json.dumps({'len': len(code)}))\n",
        encoding="utf-8", newline="\n")
    (SCRATCH / "probe69.cypy").write_text(SRC_CYPY, encoding="utf-8", newline="\n")
    gen = subprocess.run([sys.executable, "-X", "utf8", str(drv), str(SCRATCH / "probe69.cypy")],
                         cwd=str(SCRATCH), capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                         timeout=300)
    c_path = SCRATCH / "probe69.c"
    structural = {}
    if c_path.exists():
        lines = c_path.read_text(encoding="utf-8").splitlines()
        module_ifs = [(i + 1, ln) for i, ln in enumerate(lines)
                      if re.match(r"^if\s*\(", ln)]
        structural = {"c_lines": len(lines), "module_level_if_lines": module_ifs}
    a3 = cl_compile(c_path, [py_inc], "bridge-generated-c") if c_path.exists() else {
        "id": "bridge-generated-c", "rc": None, "error_lines": [],
        "command_verbatim": "(未生成 C)", "text_tail": (gen.stderr or gen.stdout)[-400:]}
    attempts.append(a3)
    if not c_path.exists():
        REFUSE.append(f"bridge 的 C 没落盘，BUG-69 的真编译无从谈起：{a3['text_tail'][:200]}")
    else:
        check("生成物必须含模块级 if（这是 BUG-69 的现场）",
              bool(structural["module_level_if_lines"]), True, str(structural)[:200])
        rejected_at_if = a3["rc"] != 0 and any(
            f"({ln}):" in e or f"line {ln}" in e for ln, _ in structural["module_level_if_lines"]
            for e in a3["error_lines"])
        if not rejected_at_if:
            REFUSE.append(f"BUG-69 主张「MSVC 必拒」但这次没在模块级 if 那一行被打回："
                          f"rc={a3['rc']} errs={a3['error_lines'][:4]}")

    # ④ D18：两次真编译测缓存命中（`compile_to_pyd` 默认增量、源未变复用 .pyd）
    drv2 = SCRATCH / "cache_probe.py"
    drv2.write_text(CACHE_DRIVER % {"root": str(ROOT),
                                    "out": str(SCRATCH / "pyd_out"),
                                    "src": str(SCRATCH / "probe69.cypy")},
                    encoding="utf-8", newline="\n")
    cache = subprocess.run([sys.executable, "-X", "utf8", str(drv2)], cwd=str(SCRATCH),
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), timeout=900)
    cache_doc = {}
    try:
        cache_doc = json.loads(cache.stdout.strip().splitlines()[-1])
    except Exception:
        cache_doc = {"error": (cache.stderr or cache.stdout)[-600:]}

    def round_pyd(k: str) -> str:
        return str(cache_doc.get(k, {}).get("pyd_path") or "")

    same_pyd = bool(round_pyd("first")) and round_pyd("first") == round_pyd("second")
    pyd_written_twice = (cache_doc.get("mid", {}).get("pyd_mtime_ns")
                         != cache_doc.get("after", {}).get("pyd_mtime_ns"))
    reuse_claim = ("cached-reuse" if cache_doc.get("second", {}).get("success") and same_pyd
                   and not pyd_written_twice else
                   ("no-reuse" if pyd_written_twice else
                    ("reused-artifact" if cache_doc else "not-measured")))
    d18 = {"claim": "docs/USAGE.md:406「源未变会复用 .pyd」", "measure": cache_doc,
           "same_pyd_path": same_pyd, "pyd_rewritten_between_calls": pyd_written_twice,
           "verdict": reuse_claim,
           "rc": cache.returncode,
           "stderr_tail": (cache.stderr or "")[-300:]}
    if cache_doc.get("error"):
        d18["verdict"] = "not-measured"
        REFUSE.append(f"D18 缓存实测没跑起来（不许写成结论）：{cache_doc['error'][:200]}")
    check("D18 必须先看到 .pyd 真落盘（否则没资格谈复用）",
          bool(cache_doc.get("mid", {}).get("pyd_mtime_ns")), True,
          f"mid={cache_doc.get('mid', {}).get('pyd')}")
    check("D18 两轮都必须编译成功（失败的一轮不能拿来谈缓存）",
          [cache_doc.get("first", {}).get("success"), cache_doc.get("second", {}).get("success")],
          [True, True], "见 measure")
    d18["artifacts_on_disk"] = sorted(cache_doc.get("mid", {}).get("pyd_mtime_ns", {}))
    d18["pyd_attrs_on_result"] = cache_doc.get("first", {}).get("pyd_attrs_on_result")
    d18["pyd_path_empty_while_artifact_exists"] = [
        k for k in ("first", "second")
        if not round_pyd(k) and cache_doc.get(k, {}).get("success")
        and d18["artifacts_on_disk"]]

    golden_after = tree_fingerprint(golden_paths())
    scratch_only = str(SCRATCH).startswith(str(HERE))
    repo_new_files = sorted(set(untracked(watched)) - set(untracked_before))

    check("golden 面（examples/*.out 与 e2e_golden.sh）前后必须逐字相等",
          golden_before["digest"] == golden_after["digest"], True,
          f"before={golden_before['digest']} after={golden_after['digest']}")
    check("golden 面必须真数到基准文件（空指纹不算自证）",
          golden_before["files_total"] >= 10, True, f"files={golden_before['files_total']}")
    check("golden 文件数不得变化（新增/删除都算动过基准）",
          golden_before["files_total"], golden_after["files_total"], "files_total 前后")
    check("被看住的目录里本轮不得新增未跟踪文件", repo_new_files, [], "见 repo_new_files")
    check("编译产物必须全在 scratch（仓库源码树之外）", scratch_only, True, str(SCRATCH))

    doc = {"started": started, "toolchain": {"cl": cl, "python_include": py_inc,
                                             "banner": a1["banner"]},
           "attempts": attempts, "structural": structural, "d18_cache": d18,
           "scratch_outside_repo": scratch_only, "scratch_dir": str(SCRATCH),
           "watched_dirs": watched, "repo_new_files": repo_new_files,
           "untracked_before_total": len(untracked_before),
           "golden_face_files": sorted(str(f.relative_to(ROOT)).replace("\\", "/")
                                       for f in golden_paths()),
           "golden_untouched": {"before": golden_before["digest"],
                                "after": golden_after["digest"],
                                "files_before": golden_before["files_total"],
                                "files_after": golden_after["files_total"],
                                "equal": golden_before == golden_after,
                                "regenerate_called": False},
           "note": "本件不调用任何 golden 注册入口（`e2e_golden.sh` 只按 sha 比，不跑）；"
                   "所有编译产物落 verify_r4_tmp/compile/，仓库源码树零新增",
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"attempts": len(attempts),
                      "rcs": [a["rc"] for a in attempts],
                      "module_level_if_lines": structural.get("module_level_if_lines"),
                      "d18_verdict": d18["verdict"],
                      "d18_durs": [cache_doc.get("dur_first"), cache_doc.get("dur_second")],
                      "golden_equal": doc["golden_untouched"]["equal"],
                      "golden_files": doc["golden_untouched"]["files_after"],
                      "refuse": doc["refuse"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
