#!/usr/bin/env python3
"""Gate-② substance check: every pass-7 regression test must be RED on pre-fix code.

"Tests exist and pass" only proves the fix is self-consistent. This rebuilds a throwaway tree
whose product code has each fix reverted (new->old, driven by the same EDITS tables that wrote
them), copies the test file in, and runs pytest inside that tree so imports resolve there.

Reported per ticket: how many of its own tests go red on the reverted tree. A ticket whose tests
all stay green means the test does not lock the defect. Because several unrelated pre-pass-7
edits also exist in the working tree, the revert is anchored strictly on this pass's own
replacement strings -- the resulting red set is attributable to this pass, not to HEAD drift.

Method (since pass 9): **one ticket reverted at a time**, all others left fixed. Reverting
everything at once is not sound -- two reverts can cancel and fake a green. That happened for
real: with BUG-14's `type_mapper` also reverted, BUG-32's constraint-echo test passed on the
"prefix" tree (the mapper no longer renames float) while its *control* went red instead. The
all-at-once run is kept only as a cross-check, never as the gate.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")
TREE = HERE / "_prefix_tree"


# 三处在后续 Edit 里被改过文本（BUG-15 加了注释、BUG-20 加了 ValueError 兜底、
# BUG-22 收紧成「组合前缀必须紧跟引号」），补丁脚本里的 old/new 已经过期。
# 这里给出**当前文件文本**的回退配方，语义与 EDITS 相同：(rel, old=修复前, new=当前)。
OVERRIDES = [
    # 裁决落地自己引入的缺陷 BUG-32：把约束成员的渲染退回「过一遍 type_mapper」。
    ("cypyc/codegen/cython_generator.py",
     "        members = \" | \".join(self._type_to_str(m) for m in getattr(node, 'members', []) or [])",
     "        members = \" | \".join(self._constraint_member_name(m)\n"
     "                             for m in getattr(node, 'members', []) or [])", "BUG-32"),
    # 裁决单 BUG-14：把 type_mapper 的 cython 表退回 C float（与 c 表重新分叉）。
    ("cypyc/codegen/type_mapper.py",
     '            "float": "float",',
     '            # BUG-14 裁决（2026-09-26）：float 跟随 Python 双精度。此前本表出 C float（32 位）、\n'
     '            # cypy_to_c 出 double，同一个声明类型在一次产物里两种宽度。\n'
     '            "float": "double",', "BUG-14"),
    # 裁决单 BUG-13：把摘要判据退回墙钟（阈值不许被顺手改动，故 new/old 只差量纲）。
    ("tests/test_incremental.py",
     "        differ = ASTDiffer()\n"
     "        started = time.perf_counter()\n"
     "        for stmt in large_ast.body:\n"
     "            differ._compute_definition_hash(stmt)\n"
     "        digest_elapsed = time.perf_counter() - started",
     "        differ = ASTDiffer()\n"
     "        # BUG-13 裁决（2026-09-26）：摘要代价用 CPU 时间判，阈值量级不变。\n"
     "        # 墙钟测的是「本进程当时有多少堆要扫」——实测同一份产品码 CPU 恒 0.39–0.47s，\n"
     "        # 而墙钟随收集顺序在 0.51s 与 3.385s 之间翻面，把门禁变成了抛硬币。\n"
     "        started = time.process_time()\n"
     "        for stmt in large_ast.body:\n"
     "            differ._compute_definition_hash(stmt)\n"
     "        digest_elapsed = time.process_time() - started", "BUG-13"),
    ("cypyc/parser/lexer.py",
     '                if self.source[self.pos:self.pos+2] == "``":',
     '                if self.source[self.pos:self.pos+3] == "```":', "BUG-15"),
    ("cypyc/analyzer/comptime_evaluator.py",
     "        if isinstance(node, Call):\n"
     "            func_name = self._get_func_name(node.func)\n"
     "            args = [self.evaluate(arg) for arg in node.args]\n"
     "            return self._evaluate_call(func_name, args)",
     "        if isinstance(node, Call):\n"
     "            # BUG-20: func 是 Attribute（\"abc\".upper()）时 _get_func_name 退回\n"
     "            # str(node)，得到带行列号的节点 repr，永远查不进任何表 —— 于是\n"
     "            # :188-276 整张字符串/列表方法表不可达，语句被静默丢成注释。\n"
     "            # 按 _evaluate_attribute_access 的契约取回已绑定接收者的方法再调用。\n"
     "            receiver = getattr(node.func, \"value\", None)\n"
     "            attr = getattr(node.func, \"attr\", None)\n"
     "            args = [self.evaluate(arg) for arg in node.args]\n"
     "            if receiver is not None and attr:\n"
     "                obj_val = self.evaluate(receiver)\n"
     "                if obj_val is None:\n"
     "                    return None\n"
     "                try:\n"
     "                    method = self._evaluate_attribute_access(obj_val, attr)\n"
     "                except ValueError:\n"
     "                    return None          # 表里没有该方法：沿用「无法求值」的既有降级口径\n"
     "                if callable(method):\n"
     "                    try:\n"
     "                        return method(*args)\n"
     "                    except TypeError:\n"
     "                        return None\n"
     "                return method\n"
     "            func_name = self._get_func_name(node.func)\n"
     "            return self._evaluate_call(func_name, args)",
     "BUG-20"),
    ("cypyc/parser/lexer.py",
     "                # 检查是否是 f-string 前缀 (支持 f, F, rf, fr)\n"
     "                if char in ('f', 'F', 'r', 'R') and self._peek_ahead(1) in ('\"', \"'\", 'f', 'F'):\n"
     "                    prefix_chars = char\n"
     "                    # 检查组合前缀 (rf, fr)\n"
     "                    if self._peek_ahead(1) in ('f', 'F'):\n"
     "                        prefix_chars += self._peek_ahead(1)\n"
     "                        self._advance()  # 消费第一个字符\n"
     "                        self._advance()  # 消费第二个字符 (f/F)\n"
     "                    else:\n"
     "                        self._advance()  # 消费单个前缀字符",
     "                # 检查是否是 f-string 前缀 (支持 f, F, rf, fr)\n"
     "                # BUG-22: 第二字符集合里没有 r/R，注释承诺的 `fr\"...\"` 实际被拆成\n"
     "                # IDENTIFIER `fr` + STRING（`rf\"...\"` 却能过），报错点远在 parse。\n"
     "                # 组合前缀只承认 rf/fr 两种，且**必须紧跟引号** —— 否则 `free(`、\n"
     "                # `readfile` 这类普通标识符会被当成前缀吞掉（第一版修复就踩了这个坑）。\n"
     "                _nxt = self._peek_ahead(1)\n"
     "                _combo = ((_nxt in ('r', 'R') and char in ('f', 'F')) or\n"
     "                          (_nxt in ('f', 'F') and char in ('r', 'R'))) and \\\n"
     "                    self._peek_ahead(2) in ('\"', \"'\")\n"
     "                if char in ('f', 'F', 'r', 'R') and (_nxt in ('\"', \"'\") or _combo):\n"
     "                    prefix_chars = char\n"
     "                    # 检查组合前缀 (rf, fr)\n"
     "                    if _combo:\n"
     "                        prefix_chars += _nxt\n"
     "                        self._advance()  # 消费第一个字符\n"
     "                        self._advance()  # 消费第二个字符 (f/F/r/R)\n"
     "                    else:\n"
     "                        self._advance()  # 消费单个前缀字符",
     "BUG-22"),
]


def load_edits():
    out = []
    for script in ("fixes_pass7.py", "fixes_pass7b.py"):
        spec = importlib.util.spec_from_file_location(script[:-3], HERE / script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)          # module body is data-only; main() is guarded
        out.extend(mod.EDITS)
    overridden = {o[3] for o in OVERRIDES}
    out = [e for e in out if e[4] not in overridden]        # 过期配方让位给 OVERRIDES
    out.extend((rel, old, new, 1, ticket) for rel, old, new, ticket in OVERRIDES)
    return out


def build_tree():
    if TREE.exists():
        shutil.rmtree(TREE)
    TREE.mkdir(parents=True)
    for pkg in ("cypyc", "cypy_bridge", "cypy_hook"):
        shutil.copytree(ROOT / pkg, TREE / pkg,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (TREE / "tests").mkdir()
    shutil.copy2(ROOT / "tests" / "test_polish_20260926_pass7.py",
                 TREE / "tests" / "test_polish_20260926_pass7.py")
    # BUG-13 的锁读 tests/test_incremental.py、BUG-14 的锁读 examples/subtype_units.cypy：
    # 不一起复制的话这两条会因「文件不存在」而红 —— 那是假红（缺件 ≠ 缺陷复现）。
    shutil.copy2(ROOT / "tests" / "test_incremental.py", TREE / "tests" / "test_incremental.py")
    (TREE / "examples").mkdir()
    shutil.copy2(ROOT / "examples" / "subtype_units.cypy", TREE / "examples" / "subtype_units.cypy")


def revert(edits):
    """把若干「修复」退回旧写法，返回 {相对路径: 回退前字节} 供还原。"""
    touched, miss = {}, []
    for rel, old, new, _want, ticket in edits:
        path = TREE / rel
        if rel not in touched:
            touched[rel] = path.read_bytes()
        text = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in text
        o, n = (old.replace("\n", "\r\n"), new.replace("\n", "\r\n")) if crlf else (old, new)
        if n not in text:
            miss.append(f"{ticket} {rel}: 新文本不在树里，无法回退")
            continue
        path.write_bytes(text.replace(n, o, 1).encode("utf-8"))
    return touched, miss


def restore(touched):
    for rel, raw in touched.items():
        (TREE / rel).write_bytes(raw)


def run_tree():
    env = tree_env()
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest",
                        "tests/test_polish_20260926_pass7.py", "-q", "--no-header", "-rA",
                        "-p", "no:cacheprovider"],
                       cwd=TREE, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=1800)
    return r


def main() -> int:
    try:
        return _run()
    finally:
        # 「临时树跑完即删」必须是行为而不是正文：删完再实测一次不存在，残留即红。
        if TREE.exists():
            shutil.rmtree(TREE, ignore_errors=True)
        if TREE.exists():
            print(f"REFUSE — 临时树没删掉，仍在 {TREE}")
            return 4


def tree_env():
    return {str(k): str(v) for k, v in {**os.environ,
                                        "PYTHONPATH": str(TREE),
                                        "PYTHONDONTWRITEBYTECODE": "1"}.items()}


def identity_probe():
    """证明「导入的就是临时树那份 cypyc」——已安装/相邻副本静默顶掉源码树是本项目踩过的坑。"""
    code = ("import cypyc, pathlib, sys\n"
            "p = pathlib.Path(cypyc.__file__).resolve()\n"
            "print(p)\n"
            "sys.exit(0 if str(p).startswith(str(pathlib.Path(%r).resolve())) else 3)" % str(TREE))
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], cwd=TREE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=tree_env(), timeout=120)
    if r.returncode != 0:
        raise SystemExit(f"REFUSE — 身份探针没通过（导入的不是临时树）: {r.stdout}{r.stderr}")
    print("identity:", r.stdout.strip())


def _statuses(r):
    """pytest -rA 的逐条结果 -> (通过 def 集, 失败 def 集)。"""
    # 参数化用例的行尾带 [id]；正则若不容它，这些条目会整条看不见（盲点）。
    got = re.findall(r"^(PASSED|FAILED|ERROR) (\S+::(\w+)(?:\[[^\]]*\])?)", r.stdout, re.M)
    if not got:
        raise SystemExit(f"REFUSE — 没解析出任何逐条结果，原文尾部:\n{r.stdout[-1200:]}")
    seen = {t.split("[")[0] for _, _, t in got}
    declared = set(re.findall(r"(?m)^def (test_bug\w+)", (ROOT / "tests" / "test_polish_20260926_pass7.py")
                              .read_text(encoding="utf-8")))
    if seen != declared:
        raise SystemExit(f"REFUSE — 解析到 {len(seen)} 个 def 的结果，文件里声明 {len(declared)} 个，"
                         f"差集 {sorted(seen ^ declared)}：解析面漏了")
    ok = {t.split("[")[0] for s, _, t in got if s == "PASSED"}
    bad = {t.split("[")[0] for s, _, t in got if s in ("FAILED", "ERROR")}
    return ok, bad


def _run() -> int:
    edits = load_edits()
    build_tree()
    identity_probe()
    src = (ROOT / "tests" / "test_polish_20260926_pass7.py").read_text(encoding="utf-8")
    per = {}
    for name in re.findall(r"(?m)^def (test_bug\w+)", src):
        per.setdefault("BUG-" + re.match(r"test_bug(\d+)_", name).group(1), []).append(name)
    log_chunks = []

    # 0) 基线：当前码在临时树里必须全绿，否则「回退后转红」无从谈起。
    r_base = run_tree()
    ok, bad = _statuses(r_base)
    log_chunks.append("=== baseline (current code) ===\n" + r_base.stdout)
    if bad:
        print(f"REFUSE — 当前码在临时树里就有红条: {sorted(bad)}")
        return 2
    print(f"baseline: {len(ok)} passed / 0 failed（临时树内）")

    # 1) 逐单隔离回退：只回退这一单的修复，其余保持修好。
    #    「所有单一起回退」会让互相抵消的修复伪装成绿（BUG-32 实测就是这样：把 BUG-14 的
    #    type_mapper 一起退回去，约束注释自然又写成 float，于是 BUG-32 的锁在前码上反而绿）。
    rows, weak, miss = [], [], []
    for bug in sorted(per, key=lambda b: int(b.split("-")[1])):
        subset = [e for e in edits if e[4] == bug]
        if not subset:
            miss.append(f"{bug}: 没有回退配方（该单的锁没被证过）")
            continue
        touched, m = revert(subset)
        miss += m
        if m:
            restore(touched)
            continue
        r = run_tree()
        log_chunks.append(f"=== revert only {bug} ===\n{r.stdout}")
        ok_b, bad_b = _statuses(r)
        restore(touched)
        tests = per[bug]
        reds = [t for t in tests if t in bad_b]
        must = [t for t in tests if not re.search(r"unchanged|still|control|untouched|_prefers_", t)]
        red_must = [t for t in must if t in bad_b]
        if not red_must:
            weak.append(bug)
        rows.append({"bug": bug, "tests": len(tests),
                     "red_on_prefix_code": red_must or reds,
                     "red_controls": [t for t in tests if t not in must and t in bad_b],
                     "green_on_prefix_code": [t for t in tests if t not in bad_b]})
        print(f"{bug:8s} tests={len(tests)} red={len(reds)} "
              f"red_must={len(red_must)} red_controls={len(rows[-1]['red_controls'])}")
    if miss:
        print("REFUSE — 回退锚点/配方有问题:\n  " + "\n  ".join(miss))
        return 2

    # 2) 交叉参照：全部一起回退（旧口径），只记录不作为门禁。
    touched, _m = revert(edits)
    r_all = run_tree()
    log_chunks.append("=== revert everything (cross-check) ===\n" + r_all.stdout)
    _ok_a, bad_a = _statuses(r_all)
    restore(touched)
    all_at_once = {"failed_count": len(bad_a), "tail": r_all.stdout.strip().splitlines()[-1]}

    (HERE / "lockproof_pass7.log").write_text("\n".join(log_chunks), encoding="utf-8",
                                              newline="\n")
    json.dump({"method": "per-ticket isolated revert（每次只回退一单的修复），"
                         "外加一次全部回退作交叉参照",
               "reverted_sites": [{"ticket": e[4], "file": e[0]} for e in edits],
               "rows": rows, "tickets_without_a_red": weak,
               "all_at_once": all_at_once,
               "baseline_passed": len(ok)},
              open(HERE / "lockproof_pass7.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("all-at-once cross-check:", all_at_once)
    print(f"tickets_with_no_red={weak or 'none'}")
    return 1 if weak else 0


if __name__ == "__main__":
    sys.exit(main())
