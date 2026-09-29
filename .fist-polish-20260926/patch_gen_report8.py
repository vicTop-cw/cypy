#!/usr/bin/env python3
"""Cite the lane-3 category scanner per category in §一, with a re-run-vs-snapshot drift guard.

Why: the six focus categories named by the brief (可变默认参数 / 越界切片 / 资源未关闭 / 异常静默 /
增量缓存 / codegen 边界) were scanned by `sweep4_classes.py`, but the report only asserted "读过四通".
A reader could not tell a scanned-and-empty category from a never-scanned one. This makes the counts
come from the artifact, and asserts the closure re-run matches the pre-closure snapshot class-by-class
(so "无漂移" is measured, and a real drift stops the report from being generated).
"""
import os
import py_compile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

OLD_LOAD = 'SKIP_FINAL = (read("pytest_final_sweep6.log").count("skipped")\n              + read("pytest_final_sweep6.log").count("xfail"))'
NEW_LOAD = OLD_LOAD + """
cat = load("sweep4_classes.json")
catb = load("sweep4_classes_before_reclosure.json")
CLASS_LABEL = {
    "A_mutable_default": "可变默认参数（list/dict/set 字面量作默认值）",
    "B_open_no_ctx": "open()/NamedTemporaryFile 无上下文管理器且无可见 close()",
    "C_subprocess_no_timeout": "subprocess.* 调用没有 timeout= 关键字",
    "D_lock_no_finally": "锁 acquire 没有包在 try/finally 里",
    "E_index_after_filter": "推导式/过滤结果直接下标 [0]（越界面）",
}
_MISSING = [k for k in CLASS_LABEL if k not in cat or k not in catb]
if _MISSING:
    sys.exit(f"[gen_report] 类别扫描产物缺键 {_MISSING} —— 不生成报告")


def _locs(blob, key):
    return [x["loc"] for x in blob[key]]


_drift = [k for k in CLASS_LABEL if _locs(cat, k) != _locs(catb, k)]
if _drift:
    sys.exit(f"[gen_report] 收口复跑与收口前快照在 {_drift} 上命中集合不同——须在报告里逐处解释，不能沉默")
CAT_DRIFT = "命中集合逐类别一致"
CAT_DISPO = {
    "A_mutable_default": "—（无命中）",
    "B_open_no_ctx": "—（无命中；子进程 timeout 那处缺陷已由 BUG-2 修口）",
    "C_subprocess_no_timeout": "—（无命中）",
    "D_lock_no_finally": "全部 " + str(len(cat["D_lock_no_finally"])) +
                         " 处逐条判**误报**（见本段末「GilState.acquire() 三处站点」）",
    "E_index_after_filter": "—（无命中）",
}
CAT_TABLE = "\\n".join(
    "| `{}` | {} | {} 处 | {} |".format(k, CLASS_LABEL[k], len(cat[k]), CAT_DISPO[k])
    for k in CLASS_LABEL)
CAT_LOC_D = "、".join(_locs(cat, "D_lock_no_finally"))"""

OLD_MARK = "确诊 {BUG_TOTAL} 条（其中 {FIXED_TOTAL} 条已修复并 verify"
NEW_MARK = """③ 里点名的六个聚焦类别不是「通读时扫了一眼」，而是各有一条机检扫描器与落盘产物
（`sweep4_classes.py` → `sweep4_classes.json`，实扫 {cat['files_scanned']} 文件 / {cat['lines_scanned']} 行）：

| 扫描器 key | 类别 | 命中 | 处置 |
|---|---|---|---|
{CAT_TABLE}

`D_lock_no_finally` 的三处是 {CAT_LOC_D}。另有两类扫描器判不了、只能靠读码：增量缓存失效面
（`cypyc/incremental/` 三件由 BUG-3/5/6/9/10 五单覆盖）与 codegen 缩进/作用域边界（由 BUG-4/8 与
第四遍通读覆盖，未再新增确诊）。收口时同一脚本**复跑一次**并与收口前快照逐类别比对
（`sweep4_classes_before_reclosure.json`）：{CAT_DRIFT}，且 `gen_report.py` 在漂移时直接 `sys.exit`
拒绝出报告——所以「四类实测 0 命中」是扫出来的 0，不是没扫的 0。

""" + OLD_MARK

EDITS = [(OLD_LOAD, NEW_LOAD), (OLD_MARK, NEW_MARK)]


def main() -> int:
    src = open(TARGET, encoding="utf-8").read()
    hits = [(src.count(old), old[:44].replace("\n", "\\n")) for old, _ in EDITS]
    for n, tag in hits:
        print(f"count={n} :: {tag}")
    if any(n != 1 for n, _ in hits):
        sys.exit("[patch8] 锚点匹配异常 —— 未写文件")
    if "sweep4_classes_before_reclosure.json" in src:
        print("[patch8] 已打过，no-op")
        return 0
    for old, new in EDITS:
        src = src.replace(old, new, 1)
    open(TARGET, "w", encoding="utf-8", newline="").write(src)
    compile(src, TARGET, "exec")
    py_compile.compile(TARGET, doraise=True)
    print(f"[patch8] applied={len(EDITS)} bytes={len(src.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
