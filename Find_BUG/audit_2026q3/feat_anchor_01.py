#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T0r258.4.1 自门控探针 —— e2e golden 判据「约束厚度」审计（只读，幂等，不落状态）。

背景：`bash scripts/e2e_golden.sh` 今天报 PASS=22 FAIL=0 UNREG/RUNFAIL=0 WARN=1，
一片绿。但「全绿」与「判据到位」是两件事：本探针把「这条 PASS 到底约束了多少东西」
变成可机检的事实，并在空转/中毒锚点仍存在时以 exit 1 咬住。

厚度判据（全部为可机检规则，不靠肉眼）：
  记 P = 源文件中「运行时真会执行」的输出语句数（print/printf/echo 调用点数，
      剔除整行注释、并剔除 if __name__ 守卫内的调用——cypyc run 通过 import 加载
      .pyd 再调 main()，守卫永不成立）
      G = golden 的非空白行数，B = golden 字节数
  R1  UNREG      : golden 文件不存在
  R2  CORRUPT    : 源文件含 NUL 字节或 UTF-8 BOM（不是干净文本，编译诊断会被当成输出）
  R3  POISONED   : golden 里是 CLI 的失败横幅/Python 回溯/编译器诊断，而不是程序 stdout
  R4  PATH_LEAK  : golden 里含机器绝对路径（换机器/换目录必然失配，基准不可移植）
  R5  EMPTY      : B<=1 或 G==0 —— 空基准，程序改成什么都不报红
  R6  NOOP       : G<=1 且 P>=2 —— 有多个可观察操作却只约束 0~1 行
  R7  THIN       : 1 < G < P —— 每个输出语句至少该落一行，缺了就是没跑全
  R8  ORPHAN     : P==0 且 G>1 —— 源文件根本不出输出，golden 不可能是它的产物
  R9  DUP        : 与别的 golden 逐字节相同（且本文件自身 P 与 G 不相等）—— 一份基准喂多个锚点
  R10 GUARD-TRAPPED: 输出语句全在 __main__ 守卫内且无 main()/run() 入口 —— 结构上取不到输出
  有效（有约束力）= 以上全不命中，且 P>=1 且 G>=P。

退出码：
  0 = 缺陷已修（所有 golden 达到阈值，全部判定为「有效」）
  1 = 缺陷仍在（存在任一 R1~R9 命中）
  2 = 判据自身出错（examples/ 缺失或配对数骤降，既非实现问题也非探针问题）
  3 = 探针自身异常（harness bug）

只读保证：只 read_bytes/read_text，最多跑 `git ls-files`（只读子命令）；不写任何文件，
不跑编译器，不改 examples/、scripts/、cypyc/。
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                          # pragma: no cover
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                     # Find_BUG/audit_2026q3 -> repo root
EXAMPLES = ROOT / "examples"
MIN_PAIRS = 15                                # 配对数低于此说明判据自身出了问题

# needle 里没有 `echo`：Cypy 没有内建 `echo`（`grep -rn "'echo'" cypyc/ --include=*.py` 无命中，
# 也不在 `Lexer.KEYWORDS`），而按调用点计数会把用户函数 `echo(...)` 当成输出语句 ——
# 实测 `print(echo("flattened"))` 记成 2 条（它只输出一行），虚增 p 会让 R6/R7 把好示例判成 THIN。
PRINT_SITE = re.compile(r"(?<![\w.])(print|printf)\s*\(")
DEF_LINE = re.compile(r"^\s*(?:async\s+)?def\s")
DEF_SITE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.M)
COMMENT_ONLY = re.compile(r"^\s*#")
MAIN_GUARD = re.compile(r"^\s*if\s+__name__\s*==")
ENTRY_FUNC = re.compile(r"^\s*def\s+(main|run)\s*\(", re.M)
TEST_PREFIX = "test_"

# golden 里出现这些就是「编译/运行失败诊断」，不是程序 stdout
POISON_MARKERS = [
    (r"\[FAIL\] Execution failed", "CLI 失败横幅 [FAIL] Execution failed"),
    (r"Traceback \(most recent call last\)", "Python 回溯"),
    (r"^\s*-\s+.*(编译错误|运行错误|转译错误|Compile error)", "CLI 错误项"),
    (r"^\s*-\s+Undefined name ", "编译器诊断 Undefined name"),
    (r"^(AttributeError|TypeError|ValueError|NameError|ImportError|"
     r"ModuleNotFoundError|SyntaxError|RecursionError|IndexError):", "未捕获异常行"),
]
PATH_LEAK = re.compile(r"[A-Za-z]:\\|/home/[^ ]*/|/Users/[^ ]*/")


def read_pair(src: Path):
    """返回 (源文本, golden 字节, golden 文本)；golden 缺失时后两者为 None。"""
    raw = src.read_bytes()
    gpath = src.with_suffix(".out")
    if not gpath.exists():
        return raw, None, None
    gbytes = gpath.read_bytes()
    return raw, gbytes, gbytes.decode("utf-8", "replace")


def count_sites(line: str) -> int:
    """一行里的输出语句调用点；`def print(self)` 这类定义行不算调用。"""
    if DEF_LINE.match(line):
        return 0
    return len(PRINT_SITE.findall(line))


def metrics(src_text: str, gbytes, gtext) -> dict:
    lines = src_text.splitlines()
    code_lines = [l for l in lines
                  if l.strip() and not COMMENT_ONLY.match(l)]
    # cypyc run 走 import 路径：__main__ 守卫里的 print 永远不会执行
    in_guard, guard_indent = False, 0
    guard_prints = 0
    for l in lines:
        if not l.strip() or COMMENT_ONLY.match(l):
            continue
        indent = len(l) - len(l.lstrip())
        if MAIN_GUARD.match(l):
            in_guard, guard_indent = True, indent
        elif in_guard and indent <= guard_indent:
            in_guard = False
        if in_guard:
            guard_prints += count_sites(l)
    funcs = DEF_SITE.findall(src_text)
    m = {
        "src_lines": len(lines),
        "code_lines": len(code_lines),
        "funcs": len(funcs),
        "test_funcs": len([f for f in funcs if f.startswith(TEST_PREFIX)]),
        "prints": sum(count_sites(l) for l in code_lines),
        "guard_prints": guard_prints,
        "entry_func": bool(ENTRY_FUNC.search(src_text)),
        "nul_bytes": src_text.count("\x00"),
        "bom": src_text.startswith("\ufeff"),
    }
    m["live_prints"] = m["prints"] - m["guard_prints"]
    if gbytes is None:
        m.update(golden_bytes=0, golden_lines=0, golden_nonblank=0, md5="-")
    else:
        glines = (gtext or "").splitlines()
        m.update(golden_bytes=len(gbytes),
                 golden_lines=len(glines),
                 golden_nonblank=len([l for l in glines if l.strip()]),
                 md5=hashlib.md5(gbytes).hexdigest()[:10])
    return m


def classify(name: str, m: dict, gtext: str, dup_groups) -> list:
    """返回命中的规则列表 [(code, detail), ...]；空列表 == 该锚点有约束力。"""
    hits = []
    g, p = m["golden_nonblank"], m["live_prints"]
    if m["nul_bytes"] or m["bom"]:
        hits.append(("R2 CORRUPT",
                     "源文件含 NUL=%d BOM=%s（非干净文本）" % (m["nul_bytes"], m["bom"])))
    if m["guard_prints"] and not m["entry_func"]:
        hits.append(("R10 GUARD-TRAPPED",
                     "%d 处 print 全在 if __name__ 守卫内且无 main()/run() 入口，"
                     "cypyc run 走 import -> 结构上不可能有输出" % m["guard_prints"]))
    if gtext is None:
        hits.append(("R1 UNREG", "golden 未注册"))
        return hits
    for pat, why in POISON_MARKERS:
        if re.search(pat, gtext, re.M):
            hits.append(("R3 POISONED", "golden 是失败诊断：" + why))
            break
    leaked = PATH_LEAK.findall(gtext)
    if leaked:
        hits.append(("R4 PATH_LEAK", "golden 含机器绝对路径 %s" % leaked[0]))
    if m["golden_bytes"] <= 1 or g == 0:
        hits.append(("R5 EMPTY", "golden 非空白行数=0（%d 字节）" % m["golden_bytes"]))
    if g <= 1 and p >= 2:
        hits.append(("R6 NOOP", "源有 %d 个可执行输出语句，golden 只 %d 行" % (p, g)))
    if 1 < g < p:
        hits.append(("R7 THIN", "golden %d 行 < 输出语句 %d 处" % (g, p)))
    if p == 0 and g > 1:
        hits.append(("R8 ORPHAN",
                     "源文件 0 个可执行输出语句却有 %d 行 golden（不可能是本程序的产物）" % g))
    if name in dup_groups and dup_groups[name]:
        others = ", ".join(sorted(dup_groups[name]))
        if g != p:
            hits.append(("R9 DUP", "与其它示例逐字节相同的 golden: %s" % others))
    return hits


def build_dup_map(pairs) -> dict:
    by_md5 = {}
    for name, m in pairs:
        if m["md5"] != "-":
            by_md5.setdefault(m["md5"], []).append(name)
    groups = {}
    for members in by_md5.values():
        if len(members) > 1:
            for name in members:
                groups[name] = set(members) - {name}
    return groups


def criteria_health() -> list:
    """判据自身的健康检查：报告但不过门（本探针无权改 scripts/ 与 cypyc/）。"""
    notes = []
    main_py = ROOT / "cypyc" / "__main__.py"
    if main_py.exists():
        t = main_py.read_text(encoding="utf-8", errors="replace")
        if "sys.exit(main())" in t or "raise SystemExit(main" in t:
            notes.append(("LINK-1 退出码", "OK：cypyc/__main__.py 传递了 main() 的退出码"))
        else:
            notes.append(("LINK-1 退出码",
                          "缺陷：cypyc/__main__.py 只有裸 main()（丢弃返回值）-> run_run 返回 1 "
                          "也不会让 `python -m cypyc` 变红 -> scripts/e2e_golden.sh 的 RUNFAIL "
                          "分支只对「进程自身死亡」（段错误/未捕获异常）有反应，对「编译/运行失败但"
                          "正常返回」恒为 exit 0，所以 summary 里的 UNREG/RUNFAIL=0 几乎无信息量"))
    judge = ROOT / "scripts" / "e2e_golden.sh"
    if judge.exists():
        t = judge.read_text(encoding="utf-8", errors="replace")
        strip_block = re.search(r"strip_debug\(\)\s*\{(.*?)\n\}", t, re.S)
        body = strip_block.group(1) if strip_block else ""
        # 判「能力」而不是判措辞，且 needle 只取**代码**、不取注释（注释里有
        # `[FAIL] Execution failed:` 的字样，拿它当 needle 会自己命中自己）。
        # 加固后的写法：strip_debug 从行首 `[FAIL] ` 横幅处截断 + 主循环在比对
        # 与 --update 之前先用 BANNER_RE 拦一次。
        truncates = bool(re.search(r"/\^\[\[]FAIL", body)) or "Execution failed" in body
        pos_update = t.find('"$UPDATE" -eq 1')
        guarded = pos_update > 0 and any(
            0 < m.start() < pos_update for m in re.finditer(r'-e\s*"\$BANNER_RE"', t))
        if truncates and guarded:
            notes.append(("LINK-2 剥离", "OK：strip_debug 在行首 [FAIL] 横幅处截断，"
                                        "且 BANNER_RE 在比对/--update 之前就拦一次"))
        else:
            notes.append(("LINK-2 剥离",
                          "回归：判据不再从行首 `[FAIL] ` 横幅截断（truncates=%s guarded=%s）"
                          " -> CLI 失败诊断会被当作「程序 stdout」写进 golden 并判 PASS"
                          % (truncates, guarded)))
        upd_block = re.search(r'if \[ "\$UPDATE" -eq 1 \]; then(.*?)\n  fi\n', t, re.S)
        cmp_block = re.search(r'if \[ "\$actual" = "\$expected" \]; then(.*?)\n  fi', t, re.S)
        refuses_blank = bool(upd_block) and "is_blank_text" in upd_block.group(1)
        blank_not_green = bool(cmp_block) and "is_blank_text" in cmp_block.group(1)
        if refuses_blank and blank_not_green:
            notes.append(("LINK-3 空基准", "OK：空输出拒绝 --update 写盘，空 golden 比对通过也不算绿"))
        else:
            notes.append(("LINK-3 空基准",
                          "回归：空/纯空白基准仍可写盘或仍算绿（拒写=%s 不算绿=%s）"
                          % (refuses_blank, blank_not_green)))
        gates = re.findall(r'\[\s*"\$(\w+)"\s*-eq\s*0\s*\]\s*\|\|\s*exit\s+1', t)
        if {"fail", "runfail", "warn"} <= set(gates):
            notes.append(("LINK-4 末行门控", "OK：fail/runfail/warn 任一非零都让判据非 0 退出"))
        else:
            notes.append(("LINK-4 末行门控",
                          "回归：末行门控只拦 %s —— UNREG/RUNFAIL/WARN 仍可能 exit 0" % gates))
    # golden 是否进了版本库（只读子命令）
    try:
        out = subprocess.run(["git", "ls-files", "examples"], capture_output=True,
                             text=True, cwd=str(ROOT), timeout=30)
        tracked = [l for l in out.stdout.splitlines() if l.endswith(".out")]
        srcs = [l for l in out.stdout.splitlines() if l.endswith(".cypy")]
        if not tracked and srcs:
            notes.append(("LINK-5 基准入库",
                          "缺陷：examples/*.out 全部未纳入 git（.out 未被 ignore，"
                          "ls-files 命中 0 / .cypy 命中 %d）-> 基准只活在本地工作树，"
                          "--update 可无痕改写" % len(srcs)))
        else:
            notes.append(("LINK-5 基准入库",
                          "OK：examples/*.out 已入库（%d 个）" % len(tracked)))
    except Exception as e:                                  # pragma: no cover
        notes.append(("LINK-5 基准入库", "无法核查（%s）" % e))
    return notes


def hr(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> int:
    hr("T0r258.4.1  golden 约束厚度审计 (examples/*.cypy <-> examples/*.out)")
    if not EXAMPLES.is_dir():
        print("[anchor] examples/ 不存在 —— 判据自身出错")
        return 2
    srcs = [p for p in sorted(EXAMPLES.glob("*.cypy")) if not p.name.startswith("_")]
    pairs = []
    for src in srcs:
        raw, _gbytes, gtext = read_pair(src)
        src_text = raw.decode("utf-8", "replace")
        pairs.append((src.name, metrics(src_text, _gbytes, gtext), gtext))
    if len(pairs) < MIN_PAIRS:
        print("[anchor] 配对数 %d < %d —— 判据自身出错（示例集被大幅增删）"
              % (len(pairs), MIN_PAIRS))
        return 2

    dup_groups = build_dup_map([(n, m) for n, m, _ in pairs])

    print("%-26s %5s %5s %5s %5s %5s %5s %5s | %6s %5s %5s %-10s" %
          ("example", "srcLn", "codeLn", "funcs", "testN", "printP", "guardP", "entry",
           "gBytes", "gLn", "gNB", "md5"))
    print("-" * 108)
    verdicts = {}
    for name, m, gtext in pairs:
        print("%-26s %5d %5d %5d %5d %5d %5d %5s | %6d %5d %5d %-10s" %
              (name, m["src_lines"], m["code_lines"], m["funcs"], m["test_funcs"],
               m["prints"], m["guard_prints"], ("Y" if m["entry_func"] else "N"),
               m["golden_bytes"], m["golden_lines"],
               m["golden_nonblank"], m["md5"]))
        verdicts[name] = classify(name, m, gtext, dup_groups)

    hr("逐锚点判定")
    bad, binding = [], 0
    for name, m, _ in pairs:
        hits = verdicts[name]
        if hits:
            bad.append(name)
            print("  %-28s 无约束/弱约束: %s" % (name, "; ".join(
                "%s(%s)" % (c, d) for c, d in hits)))
        else:
            binding += 1
            print("  %-28s 有效  (P=%d, G=%d)"
                  % (name, m["live_prints"], m["golden_nonblank"]))

    hr("规则命中统计")
    tally = {}
    for name in bad:
        for code, _d in verdicts[name]:
            tally[code] = tally.get(code, 0) + 1
    for code in sorted(tally):
        print("  %-14s %d" % (code, tally[code]))
    print("  %-14s %d / %d" % ("合计命中锚点", len(bad), len(pairs)))
    print("  %-14s %d / %d" % ("有约束力锚点", binding, len(pairs)))

    hr("判据自身健康（不过门，但决定「修好」是否可能）")
    for code, msg in criteria_health():
        print("  %-16s %s" % (code, msg))

    hr("VERDICT")
    if bad:
        print("REPRODUCED —— %d 条 golden 无约束力或约束厚度不足；"
              "e2e_golden.sh 覆盖的 %d 个配对里只有 %d 条真正咬住实现。"
              % (len(bad), len(pairs), binding))
        print("失守锚点: " + ", ".join(bad))
        return 1
    print("NOT-REPRODUCED —— 全部 %d 条 golden 达到厚度阈值（P>=1 且 G>=P，"
          "无中毒/重复/空基准/损坏源）。" % len(pairs))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:                                           # noqa: BLE001
        import traceback
        traceback.print_exc()
        sys.exit(3)
