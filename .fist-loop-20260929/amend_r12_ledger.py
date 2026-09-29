"""给 BUG-129 追加 `### FIXED(R12 …)` 段（同轮确诊同轮修）；134/135 只入账不修，故不写关闭段。

纪律与 R11 收口腿那份一致：标题行与条目正文一字不改，段落戳用写盘瞬间的 UTC，
`--refresh` 只回收自己写的那段，收尾自证分两档（首装：开口数少 N／FIXED 段多 N；
回收重写：这两项都不动——换掉的是自己那段而不是新关一单；两档都要求抬头数不变、
本件段数==N、原标题与 summary 逐字留存），任一条不符就不落盘并留下 tmp 与备份待查。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
MARK = "FIXED(R12 声明界在使用侧"

SECTION = """
### {mark} {ts}）— 追加留档（本单正文与标题行的 `OPEN` 一字未改）
- 修法：把「使用侧类型实参要过声明界」收进**一处**共用件 `TypeChecker._check_declared_bounds`
  （`cypyc/analyzer/type_checker.py`），三处使用位各接一行：
  ① 注解位 `_visit_GenericType`（元数判定之后，与 `Type argument count mismatch` 并存不互相遮蔽）；
  ② 显式类型实参构造位 `_bind_explicit_type_args`（只对 class/struct 生效 —— 函数由 `_visit_Call`
  里那份统一判，否则同一条界会得到两条账）；
  ③ 结构体字面量位 `_visit_StructLiteral`：**摘掉**原来自带的那份窄复制
  （它只认 `getattr(ast,'id')` 的单名界，`T: int | float` 取到 None ⇒ 静默放行），改调共用件。
  三类界（联合／单名／特质／typeclass）都落到既有 `_check_generic_constraint`，本轮不新增消息合成点。
- 半径先测后开门（不是"改完看看"）：`.fist-loop-20260929/measure_r12_constraint_radius.py`
  改动前快照 `r12_radius_before.json` 与改动后 `r12_radius_after.json` 同集合逐文件比错误集合，
  结论 `CONCLUSION phase=after new_red_sources=0 gone_red_sources=0 ... real_crashes=0`
  —— 口径：改动前 206 份源（106 份盘面 `.cypy` + 100 对既有 corpus，历轮 `.fist-loop-*` scratch 树排除），
  其中 {CONS_SRC} 份含约束声明、共 {CONS_DECL} 处 ⇒ 开门不牵连任何既有源。
- 判据：新增 Ω-spec `corpus/cypy.generic.bounds.json`（{CASES} 对，指纹 `{FP}`，
  生成件 `.fist-loop-20260929/make_corpus_r12.py` 落盘前逐条走 `execute + judge`，一条不符就拒写 ——
  本轮它拒了 3 次：`stage` 取值猜成 `check`（实测是 `ok`）、trait 实现忘写 `impl Show for Impl:`、
  typeclass 语法写成 `typeclass Number for T:`（实际是 `typeclass Number:` + `impl typeclass Number for int:`））；
  回归锁 `tests/test_generic_bounds_r12.py`（{LOCKS} 支，含「字面量位不许长回窄复制」的源码针与
  「诊断行列指向注解位」的按源反解针）。台账地板同批上调 `FLOOR_SPECS 5→6`、`FLOOR_CASES 100→{CASES}`。
- 手册：`SYNTAX/11-generics.md` 新增「声明界在使用侧的判定」规则 1-4，
  其中规则 4 明确写出**不判的一面**（构造位不写类型实参时不做推断），
  并把这一面另立 BUG-135、把违界诊断的 `in call to '<unknown>'` 误导文案另立 BUG-134 ⇒ 不遮挡本单关闭。
- 未随本单关闭的相邻面：BUG-120（`-> T:` 无体签名形态）、BUG-121（`f[T](x)` 方括号形态）、
  BUG-122（类型实参存在性）、BUG-128（struct 方法不代入，与 BUG-135 同一推断层）。
"""


def counts(text: str) -> dict:
    blocks = [b for b in re.split(r"(?m)^(?=## BUG-)", text) if b.startswith("## BUG-")]
    open_blocks = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)]
    return {
        "headers": len(blocks),
        "open": len(open_blocks),
        "fixed": len(re.findall(r"(?m)^### FIXED", text)),
        "mine": text.count(MARK),
    }


def main() -> int:
    refresh = "--refresh" in sys.argv
    src = LEDGER.read_text(encoding="utf-8")
    before = counts(src)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    spec = json.loads((ROOT / "corpus" / "cypy.generic.bounds.json").read_text(encoding="utf-8"))
    lock_src = (ROOT / "tests" / "test_generic_bounds_r12.py").read_text(encoding="utf-8")
    radius = json.loads((HERE / "r12_radius_after.json").read_text(encoding="utf-8"))["snapshot"]
    seg = SECTION.format(
        mark=MARK,
        ts=ts,
        CASES=len(spec["tests"]),
        FP=spec["fingerprint"],
        LOCKS=len(re.findall(r"(?m)^def test_", lock_src)),
        CONS_SRC=radius["n_with_cons_decl"],
        CONS_DECL=radius["cons_decl_total"],
    )
    # 未插值占位（`{{X}}` 在 str.format 里是转义字面量 ⇒ 会原样落进台账）与歪斜时间戳都要当场拦；
    # 上一版就是带着 `{CASES}`/`{FP}` 字面串和 `2026-09-29T2026-09-29T…ZZ` 落了盘的，自证只数段落数看不出来。
    residue = re.findall(r"\{[A-Za-z_]+\}", seg)
    stamp = re.findall(r"(?m)^### " + re.escape(MARK) + r" (\S+?)）", seg)
    derived = [
        f"（{len(spec['tests'])} 对",
        spec["fingerprint"],
        f"{len(re.findall(r'(?m)^def test_', lock_src))} 支",
        f"其中 {radius['n_with_cons_decl']} 份含约束声明",
    ]
    if (
        residue
        or len(stamp) != 1
        or not re.fullmatch(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp[0])
    ):
        raise SystemExit(f"段落自身不合格 ⇒ 不落盘：residue={residue} stamp={stamp}")
    for d in derived:
        if d not in seg:
            raise SystemExit(f"派生数没落进段落（查 {d!r}）⇒ 不落盘")
    out, touched = src, []
    for bid in ("129",):
        head = re.search(r"(?ms)^## BUG-" + bid + r" .*?(?=\n## BUG-|\Z)", out)
        if not head:
            raise SystemExit(f"账上查无 BUG-{bid} ⇒ 先取号再写台账，拒绝凭空插段")
        block = head.group(0)
        pat = re.compile(r"(?ms)(?<=\n)### " + re.escape(MARK) + r".*?(?=\n## BUG-|\Z)")
        already = pat.search(block)
        if already and not refresh:
            print(f"SKIP BUG-{bid}：本件那段已在账上（覆盖用 --refresh）")
            continue
        if already:
            removed = block[already.start() : already.end()]
            if MARK not in removed:
                raise SystemExit(f"BUG-{bid} 要回收的区段不含本件标记 ⇒ 停手不动账")
            new_block = (
                block[: already.start()]
                + seg.lstrip("\n").rstrip("\n")
                + "\n"
                + block[already.end() :]
            )
        else:
            new_block = block.rstrip("\n") + "\n" + seg.rstrip("\n") + "\n"
        out = out.replace(block, new_block, 1)
        touched.append(bid)
    if not touched:
        print("CONCLUSION touched=0（已在账，幂等）")
        return 0
    LEDGER.with_name("bugs.md.pre_r12_ledger").write_text(src, encoding="utf-8", newline="\n")
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    after_text = tmp.read_text(encoding="utf-8")
    after = counts(after_text)
    old_block = re.search(r"(?ms)^## BUG-129 .*?(?=\n## BUG-|\Z)", src).group(0)
    keep = [
        ln
        for ln in old_block.splitlines()
        if ln.startswith("## BUG-") or ln.startswith("- summary:")
    ]
    preserved = all(k in after_text for k in keep)
    # 首装：开口少 N、FIXED 多 N；回收重写：两者都不动（换掉的是自己那段，不是新关一单）
    if refresh:
        delta = {"headers": 0, "open": 0, "fixed": 0}
    else:
        delta = {"headers": 0, "open": -len(touched), "fixed": len(touched)}
    # 脏检分双口径：门只钉本件亲笔那段（拿别轮的坏戳当门 ⇒ 本件永红且看不见自己合不合格），
    # 整档计数当读数印出来。上一版正是整档扫把 R11 的 4 个坏戳顶到了本件脸上。
    # "本件那段"按整档 `### ` 切块会越过 `## BUG-` 边界吃到别单的正文（实测多出 2 个花括号），
    # 所以这里直接用"我要写的段落是否逐字落进去了"当门——它同时挡住 CRLF 改写与半截写。
    landed = after_text.count(seg.rstrip("\n"))
    own_stamps = re.findall(r"(?m)^### " + re.escape(MARK) + r" (\S+?)）", after_text)
    dirty = {
        "own_chars": len(re.findall(r"[{}]", seg)),
        "own_residue": len(re.findall(r"\{(?:CASES|FP|LOCKS|CONS_SRC|CONS_DECL)\}", seg)),
        "own_badstamp": len(
            [s for s in own_stamps if not re.fullmatch(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", s)]
        ),
    }
    sweep = {
        "ledger_residue_lines": len(
            re.findall(r"(?m)^.*\{(?:CASES|FP|LOCKS|CONS_SRC|CONS_DECL)\}.*$", after_text)
        ),
        "ledger_dblstamp_lines": len(
            re.findall(r"(?m)^.*20\d\d-\d\d-\d\dT20\d\d-\d\d-\d\dT.*$", after_text)
        ),
    }
    ok = (
        after["headers"] == before["headers"] + delta["headers"]
        and after["open"] == before["open"] + delta["open"]
        and after["fixed"] == before["fixed"] + delta["fixed"]
        and after["mine"] == len(touched)
        and preserved
        and landed == len(touched)
        and len(own_stamps) == len(touched)
        and not dirty["own_residue"]
        and not dirty["own_badstamp"]
        and not dirty["own_chars"]
    )
    print("LANDED", landed, "OF", len(touched), "DIRTY_OWN", dirty, "SWEEP_WHOLE_LEDGER", sweep)
    print("BEFORE", before, "AFTER", after, "TOUCHED", touched, "SUMMARY_KEPT", preserved)
    if not ok:
        raise SystemExit("自证不符 ⇒ 不落盘，tmp 与备份留在 .fist-loop-20260929/ 待查")
    tmp.replace(LEDGER)
    print(
        f"CONCLUSION touched={len(touched)} ids=BUG-129 headers={after['headers']} "
        f"open={after['open']} fixed={after['fixed']} refresh={refresh}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
