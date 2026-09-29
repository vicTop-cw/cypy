#!/usr/bin/env python3
"""Prove the 24 regression cases actually lock their defects: today's tests against HEAD's product code.

Gate ② claims "每个修复单有能锁死该缺陷的回归测试". Passing today proves nothing about whether a case
would catch a regression. So: extract HEAD's tracked tree into a throwaway directory (product code as
of 17d68b4 = before this round's fixes), overlay the *current* `tests/` directory, and run
tests/test_polish_20260926.py there. A case that still passes against pre-fix code is not a lock.

Nothing in the working tree is touched — the temp tree is created under this driver dir and removed at
the end (only the JSON log stays). Cases that error for reasons unrelated to the fix (missing feature
from the uncommitted R2 work, toolchain) are kept as their own status so they are not miscounted as
locks.
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TMP = os.path.join(HERE, "_lockproof_head")
TEST_FILE = "tests/test_polish_20260926.py"
STATUS_RE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+)")
# 反附带伤害对照：这类用例修复前后都该是绿的（它盯的是「别把本职行为削掉」），
# 所以它不计入锁死证据；HEAD 上一旦变红，说明该对照本身另有问题。
CONTROLS = {"test_bug12_gilstate_exit_still_restores_state": "GilState 退出恢复 GIL 的本职行为对照"}
# HEAD 红、但成因里混进了本轮之外的差异（未提交的 R2 特性码），不能单独充当锁死证据。
CONFOUNDS = {"test_bug11_type_level_name_collision_is_reported":
             "HEAD 的 parser/scope_analyzer 里 subtype 出现 0 次（未提交的 R2 特性），"
             "该用例在 HEAD 上以 'No AST for module' 变红 = 混因"}
LOCK_RE = re.compile(r"^test_bug(\d+)_")


def sh(cmd, cwd, shell=False):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", shell=shell)


def build_tmp():
    if os.path.exists(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP)
    r = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT,
                       capture_output=True, text=False)
    if r.returncode != 0:
        sys.exit(f"[lockproof] git archive 失败：{r.stderr[:300]!r}")
    p = subprocess.run(["tar", "-x", "-C", TMP], input=r.stdout, text=False)
    if p.returncode != 0:
        sys.exit(f"[lockproof] tar 解包失败 rc={p.returncode}")
    for pkg in ("cypyc", "cypy_bridge", "cypy_hook"):
        if not os.path.isdir(os.path.join(TMP, pkg)):
            sys.exit(f"[lockproof] HEAD 树缺 {pkg}/，对照不成立")
    # overlay today's tests (they are untracked/modified, so HEAD's copy is not the one under proof)
    dst = os.path.join(TMP, "tests")
    if not os.path.isdir(dst):
        sys.exit("[lockproof] HEAD 树里没有 tests/，覆盖不成立")
    shutil.rmtree(dst)
    shutil.copytree(os.path.join(ROOT, "tests"), dst,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    if not os.path.exists(os.path.join(TMP, TEST_FILE)):
        sys.exit("[lockproof] 覆盖后仍找不到测试文件，对照作废")
    head = sh(["git", "rev-parse", "--short", "HEAD"], ROOT).stdout.strip()
    return head


def parse(out):
    res = {}
    for ln in out.splitlines():
        m = STATUS_RE.match(ln.strip())
        if m:
            res[m.group(2).split("::")[-1]] = m.group(1)
    lines = [ln.strip() for ln in out.splitlines()
             if re.match(r"^(FAILED|E |_{5,}|tests/)", ln.strip()) and ".py:" in ln]
    return res, lines


def identity_probe():
    """钉死「跑的是 HEAD 的产品码」：模块 __file__ 必须落在临时树，且临时树与工作区确实不同。"""
    code = ("import json,sys,cypyc,importlib;m=importlib.import_module('cypy_bridge.nogil');"
            "print(json.dumps({'cypyc':cypyc.__file__,'nogil':m.__file__,"
            "'nogil_is_module':isinstance(m,type(sys))}))")
    r = sh([sys.executable, "-c", code], TMP)
    try:
        paths = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        sys.exit(f"[lockproof] 身份探针没吐出 JSON：rc={r.returncode} out={r.stdout[:200]!r} "
                 f"err={r.stderr[-400:]!r}")
    if paths.get("nogil_is_module") is not True:
        sys.exit(f"[lockproof] cypy_bridge.nogil 取到的不是模块（被包内同名对象遮蔽？）：{paths}")
    real = os.path.realpath(TMP)
    bad = {k: v for k, v in paths.items()
           if not k.endswith("_is_module")
           and not os.path.realpath(v or "").startswith(real + os.sep)}
    if bad:
        sys.exit(f"[lockproof] 这些模块不是临时树里的 HEAD 副本，对照作废：{bad}")
    diffs = 0
    for pkg in ("cypyc", "cypy_bridge", "cypy_hook"):
        for root, _, files in os.walk(os.path.join(TMP, pkg)):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                a = os.path.join(root, fn)
                b = os.path.join(ROOT, os.path.relpath(a, TMP))
                if not os.path.exists(b) or open(a, "rb").read() != open(b, "rb").read():
                    diffs += 1
    return paths, diffs


def confound_evidence():
    """核对「混因」声明还成立吗：HEAD 侧确实没有 subtype 解析，工作区侧才有。"""
    def cnt(base, rel):
        p = os.path.join(base, rel)
        if not os.path.exists(p):
            return -1
        return open(p, encoding="utf-8", errors="replace").read().count("subtype")
    rel = ["cypyc/parser/parser.py", "cypyc/analyzer/scope_analyzer.py"]
    head = {r: cnt(TMP, r) for r in rel}
    work = {r: cnt(ROOT, r) for r in rel}
    if CONFOUNDS and sum(head.values()) > 0:
        sys.exit(f"[lockproof] HEAD 侧已有 subtype 解析（{head}），混因声明失效，重新研判这些用例")
    if CONFOUNDS and sum(work.values()) <= 0:
        sys.exit(f"[lockproof] 工作区侧反而没有 subtype（{work}），判据本身有问题")
    return {"head": head, "worktree": work}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    head = build_tmp()
    print(f"[lockproof] HEAD={head} 临时树={TMP}")
    paths, diffs = identity_probe()
    print(f"[lockproof] 身份探针: {paths}")
    if diffs == 0:
        sys.exit("[lockproof] 临时树与工作区的产品码逐字节相同 —— 没有差异可证，对照作废")
    print(f"[lockproof] HEAD 与工作区产品码不同的 .py 文件数 = {diffs}")
    conf = confound_evidence()
    print(f"[lockproof] 混因依据: HEAD subtype 计数 {conf['head']} / 工作区 {conf['worktree']}")
    r = sh([sys.executable, "-m", "pytest", TEST_FILE, "-q", "-p", "no:cacheprovider",
            "--tb=line", "-rA"], TMP)
    # 临时树最后会被删掉，追溯失败原因只能靠这份日志
    with open(os.path.join(HERE, "lockproof_head.log"), "w", encoding="utf-8") as f:
        f.write(r.stdout)
        f.write("\n===STDERR===\n")
        f.write(r.stderr)
    tail = [ln for ln in r.stdout.splitlines() if " passed" in ln or " failed" in ln
            or "error" in ln]
    print("[lockproof] 汇总行:", tail[-1] if tail else "(无)")
    statuses, notes = parse(r.stdout)
    if not statuses:
        print(r.stdout[-3000:])
        sys.exit("[lockproof] 一个用例状态都没解析到 —— 对照本身坏了，不产出结论")
    by_ticket = {}
    for case, st in statuses.items():
        m = LOCK_RE.match(case)
        bid = f"BUG-{int(m.group(1))}" if m else "(非按单命名)"
        by_ticket.setdefault(bid, []).append(
            {"case": case, "on_head": st,
             "role": ("control" if case in CONTROLS
                      else "confound" if case in CONFOUNDS else "lock")})
    rows = []
    for bid in sorted(by_ticket, key=lambda x: (x.startswith("("), int(x.split("-")[1]) if "-" in x else 0)):
        cs = sorted(by_ticket[bid], key=lambda c: c["case"])
        locks = [c for c in cs if c["role"] == "lock"]
        red = [c for c in locks if c["on_head"] in ("FAILED", "ERROR")]
        green = [c for c in locks if c["on_head"] == "PASSED"]
        ctl = [c for c in cs if c["role"] == "control"]
        con = [c for c in cs if c["role"] == "confound"]
        rows.append({"bug": bid, "cases": len(cs),
                     "distinct_functions": len({c["case"].split("[")[0] for c in cs}),
                     "lock_cases": len(locks),
                     "red_on_head": len(red), "green_on_head": len(green),
                     "controls_red": [c["case"] for c in ctl if c["on_head"] != "PASSED"],
                     "confounded_red": [c["case"] for c in con if c["on_head"] != "PASSED"],
                     "locks": len(red) > 0, "lock_case": red[0]["case"] if red else None,
                     "unexplained_green": [c["case"] for c in green], "detail": cs})
    print("\nbug       用例  锁死例  HEAD 红  判定   锁死用例")
    for x in rows:
        print(f"{x['bug']:8s} {x['cases']:5d} {x['lock_cases']:7d} {x['red_on_head']:8d}   "
              f"{'YES' if x['locks'] else 'NO '}   {x['lock_case'] or '-'}"
              + (f"   绿而未释: {x['unexplained_green']}" if x["unexplained_green"] else "")
              + (f"   对照变红: {x['controls_red']}" if x["controls_red"] else "")
              + (f"   混因红(不计锁): {x['confounded_red']}" if x["confounded_red"] else ""))
    no_lock = [x["bug"] for x in rows if not x["locks"]]
    out = {"head": head, "summary_line": tail[-1] if tail else None,
           "module_paths": paths, "product_py_differing": diffs,
           "collected": len(statuses), "rows": rows, "no_lock": no_lock,
           "controls": CONTROLS, "confounds": CONFOUNDS,
           "subtype_confound_evidence": conf,
           "returncode": r.returncode,
           "one_line_tracebacks": notes[:40],
           "stderr_tail": r.stderr[-400:]}
    json.dump(out, open(os.path.join(HERE, "lockproof_head.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    shutil.rmtree(TMP, ignore_errors=False)
    print(f"\n[lockproof] 收集 {len(statuses)} 例；判为「未锁死」的单：{no_lock or '无'}")
    print(f"[lockproof] 临时树已删除，lockproof_head.json 留存")
    return 0


if __name__ == "__main__":
    sys.exit(main())
