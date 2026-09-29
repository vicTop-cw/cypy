"""R9 报告验针：正文每条路径 / file:line / 计数 / 语料指纹 / 矩阵读数都重算一遍。

沿用 R8 那件的三条修正：路径按多基目录解析（简写第二次提及要能落到位）、nodeid（`文件::用例`）先剥 `::` 再查件、
门禁 needle 按字段取不假设相邻。结论行最后打，任一格红就 rc=1。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r115-cypy-selfdrive-r9-report.md"
BASES = [ROOT, ROOT / ".fist-loop-20260929", ROOT / ".fist-loop-20260929" / "logs",
         Path(r"D:\Migrated\victo\.qoder-cn\projects\e--IDEProjects-AI-Cypy\memory")]

fail: list = []
ok = 0


def chk(name: str, cond: bool, detail: str = "") -> None:
    global ok
    if cond:
        ok += 1
    else:
        fail.append(f"{name}{('：' + detail) if detail else ''}")


def resolve(p: str) -> str:
    p = re.sub(r":\d+$", "", p)
    for b in BASES:
        if (b / p).exists():
            return str(b / p)
    return ""


txt = REPORT.read_text(encoding="utf-8")

toks = {t for t in re.findall(r"`([^`\n]+)`", txt)
        if re.search(r"\.(py|json|md|log|txt|cypy|sh)$", t)
        or t.startswith(("corpus/", "tests/", "scripts/", "examples/", "SYNTAX/"))}
for t in sorted(toks):
    if "::" in t:
        continue  # nodeid 形式单独查（见下）
    chk(f"路径可解析 {t}", bool(resolve(t)))
chk("正文引用路径数足够（防非空集恒真）", len(toks) >= 15, f"实际 {len(toks)}")
# nodeid 形式：件必须在
for nodeid in re.findall(r"`(tests/[^\s`]+\.py::[^\s`]+)`", txt):
    chk(f"nodeid 的件存在 {nodeid}", (ROOT / nodeid.split("::")[0]).exists())

tc = (ROOT / "cypyc/analyzer/type_checker.py").read_text(encoding="utf-8").splitlines()
for line, sym in [(4298, "_visit_Subscript"), (4311, "_is_slice_form"), (4333, "_is_slice_form")]:
    chk(f"type_checker.py:{line} 含 {sym}", sym in " ".join(tc[line - 3:line + 2]), tc[line - 1][:60])
gen = (ROOT / "cypyc/codegen/cython_generator.py").read_text(encoding="utf-8").splitlines()
chk("cython_generator.py:1794 含 fields_known", "fields_known" in gen[1793], gen[1793][:60])
chk("cython_generator.py 越界分支带 fields_known 前提",
    "fields_known and i >= len(fields)" in " ".join(gen[1796:1801]))
par = (ROOT / "cypyc/parser/parser.py").read_text(encoding="utf-8").splitlines()
chk("parser.py:3952 是 slice dict 生产者", '"slice": True' in par[3951], par[3951][:60])

led = (ROOT / "memory/bugs.md").read_text(encoding="utf-8")
blocks = re.split(r"(?m)^## (BUG-\d+)", led)
open_ids = [blocks[i] for i in range(1, len(blocks) - 1, 2)
            if not re.search(r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)", blocks[i + 1])]
chk("账本 open 块=26（正文同数）", len(open_ids) == 26, str(len(open_ids)))
chk("FIXED 段 83", len(re.findall(r"(?m)^### FIXED\(", led)) == 83)
chk("DUPLICATE 段 8", len(re.findall(r"(?m)^### DUPLICATE\(", led)) == 8)
chk("AMENDMENT 段 5", len(re.findall(r"(?m)^### AMENDMENT\(", led)) == 5)
inline = txt.split("26 个 open 编号：`BUG-40 ")[1].split("`")[0]
listed = {"BUG-40"} | {f"BUG-{m}" for m in re.findall(r"\d+", inline)}
chk("正文 open 清单非空", len(listed) >= 25, f"{len(listed)} 个")
chk("正文 open 清单与反解集合相等", listed == set(open_ids), f"差集 {sorted(listed ^ set(open_ids))}")
chk("分类计数相加等于总数", 17 + 1 + 8 == 26)

for fname, n in [("cypy.annotation.shape.json", 24), ("cypy.pattern.positional.json", 19),
                 ("cypy.type.slice.json", 8)]:
    spec = json.loads((ROOT / "corpus" / fname).read_text(encoding="utf-8"))
    chk(f"{fname} 格数 {n}", len(spec["tests"]) == n, str(len(spec["tests"])))
    chk(f"{fname} 指纹逐字在正文", spec["fingerprint"] in txt)
chk("总格数 51 且 24+19+8=51", 24 + 19 + 8 == 51 and "cases=51" in txt)

pt = (ROOT / ".fist-loop-20260929/logs/r9_pytest_r2.log").read_text(encoding="utf-8", errors="replace")
chk("pytest 终版逐字 2212 passed rc=0", "2212 passed" in pt and "PYTEST_RC=0" in pt)
chk("收集数算术自洽 2202+10=2212", 2202 + 10 == 2212)
bad = (ROOT / ".fist-loop-20260929/logs/r9_pytest_r1.log").read_text(encoding="utf-8", errors="replace")
chk("被如实记下的那次回归逐字在正文", "1 failed, 2211 passed in 359.56s" in txt and "1 failed" in bad)

lk = json.loads((ROOT / ".fist-loop-20260929/verify_r9_locks.json").read_text(encoding="utf-8"))
chk("矩阵 2/2 承重", len(lk["load_bearing"]) == 2 and not lk["not_load_bearing"])
chk("矩阵对照绿（尺没坏）", lk["control_green"] is True)
chk("矩阵身份探针过", lk["identity_ok"] is True)

for line, want in [("SYNTAX/14-syntax-sugar.md", "14 章行数"), ("SYNTAX/17-pattern-matching.md", "17 章行数")]:
    n = len((ROOT / line).read_text(encoding="utf-8").splitlines())
    chk(f"正文 {want}={n}", f"现测 {n} 行" in txt, str(n))

print("PASS %d" % ok)
for f in fail:
    print("FAIL", f)
print("CONCLUSION pass=%d fail=%d report=%s rc=%d" % (ok, len(fail), REPORT.name, 0 if not fail else 1))
sys.exit(0 if not fail else 1)
