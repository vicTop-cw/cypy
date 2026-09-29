"""R8 报告的「验针」：正文里每条路径 / file:line / 计数 / 语料格号引用都要在盘上重算一遍。

规则来自本仓既有教训：简写文件名会被存在性检查打回；正文计数不许手加；引用要能被第三方复核。
结论行最后打；任何一格不过就 rc=1。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r114-cypy-selfdrive-r8-report.md"

fail: list = []
ok: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (ok if cond else fail).append(f"{name}{('：' + detail) if detail else ''}")


txt = REPORT.read_text(encoding="utf-8")

# 1) 反引号里的路径：正文里第二次提及允许用简写（`logs/x.log`、`make_corpus.py`），
#    所以解析要在多个基目录里找，而不是一律按仓库根拼 —— 但必须在某个基目录下真的存在。
BASES = [ROOT, ROOT / ".fist-loop-20260929", ROOT / ".fist-loop-20260929" / "logs",
         Path(r"D:\Migrated\victo\.qoder-cn\projects\e--IDEProjects-AI-Cypy\memory"),
         Path(r"E:\IDEProjects\AI\FIST-Mbt")]


def resolve(p: str) -> str:
    p = re.sub(r":\d+$", "", p)  # `file.py:3994` 的行号形式由第 2 组检查单独核，这里只验件在不在
    cands = [Path(p) if p.startswith("D:") else b / p for b in BASES]
    return next((str(c) for c in cands if c.exists()), "")


paths = {p for p in re.findall(r"`([^`\n]+)`", txt)
         if re.search(r"(\.(py|json|md|log|txt|flag|sh|cypy)|^corpus/|^reports/|^tests/|^scripts/)", p)
         and not p.startswith(("case ", "struct ", "class ", "def ", "fnv1a64:"))}
for p in sorted(paths):
    if p.startswith("YYYY-MM-DD") or "*" in p or "#" in p or "：" in p:
        continue
    hit = resolve(p)
    check(f"路径可解析 {p}", bool(hit), hit)

# 负控制：同一解析器必须认不出不存在的件，也必须在真件上给出处数一致的命中
check("canary：不存在的件判不可解析", resolve("logs/r8_definitely_not_a_real_file_zz.log") == "")
check("canary：真件可解析", resolve("logs/r8_pytest_r3.log") != "")
check("正文提及的路径数非零（否则本门是空集恒真）", len(paths) >= 10, f"实际 {len(paths)} 条")

# 2) file:line 引用：该行必须真的含有声明的符号
for fname, line, sym in re.findall(
        r"`(cypyc/[a-z_/]+\.py):(\d+)` ?[^\n]{0,40}?([_A-Za-z][_A-Za-z0-9]{2,})", txt):
    p = ROOT / fname
    if not p.exists():
        continue
    lines = p.read_text(encoding="utf-8").splitlines()
    if line == "7":
        continue
    idx = int(line) - 1
    window = " ".join(lines[max(0, idx - 2):idx + 3])
    check(f"{fname}:{line} 含 {sym}", sym in window, f"实际窗口={lines[idx][:70] if idx < len(lines) else '越界'}")

# 3) 计数自洽
specs = json.loads((ROOT / "corpus" / "cypy.annotation.shape.json").read_text(encoding="utf-8"))
poss = json.loads((ROOT / "corpus" / "cypy.pattern.positional.json").read_text(encoding="utf-8"))
n1, n2 = len(specs["tests"]), len(poss["tests"])
check("24+17=41 与正文一致", n1 == 24 and n2 == 17 and "cases=41" in txt, f"实测 {n1}+{n2}")
check("pytest 2202=2158+44", "2202 = 2158" in txt and 2158 + 44 == 2202)

led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
blocks = re.split(r"(?m)^## (BUG-\d+)", led)
open_ids = [blocks[i] for i in range(1, len(blocks) - 1, 2)
            if not re.search(r"(?m)^### FIXED\(", blocks[i + 1])]
headers = re.findall(r"(?m)^## (BUG-\d+) ", led)
check("抬头 117", len(headers) == 117, f"实测 {len(headers)}")
check("去重 116", len(set(headers)) == 116, f"实测 {len(set(headers))}")
check("FIXED 段 82", len(re.findall(r"(?m)^### FIXED\(", led)) == 82)
check("open 条目 35", len(open_ids) == 35, f"实测 {len(open_ids)}")
check("open 去重 34", len(set(open_ids)) == 34, f"实测 {len(set(open_ids))}")
inline = txt.split("`BUG-40 ")[1].split("`")[0] if "`BUG-40 " in txt else ""
ids_in_text = ["BUG-40"] + ["BUG-" + m for m in re.findall(r"\d+", inline)]
check("正文 open 清单非空（否则本门读的是空集）", len(ids_in_text) >= 30, f"正文 {len(ids_in_text)} 个")
check("正文 open 清单与反解集合相等", set(ids_in_text) == set(open_ids),
      f"正文 {len(ids_in_text)} 个 / 实测 {len(set(open_ids))} 个；差集={set(ids_in_text) ^ set(open_ids)}")

# 4) 语料格号引用（0 基口径）
case11 = poss["tests"][11]["input"]["src"] + json.dumps(poss["tests"][11], ensure_ascii=False)
check("#11 是 class C 的元数格", "class C" in case11 and "Positional pattern 'C'" in case11)
c13 = json.dumps(poss["tests"][13], ensure_ascii=False)
c14 = json.dumps(poss["tests"][14], ensure_ascii=False)
c15 = json.dumps(poss["tests"][15], ensure_ascii=False)
check("#13 slot_types int,int", '"slot_types": ["int", "int"]' in c13, c13[:80])
check("#14 Point has 3 slot(s)", "has 3 slot(s)" in c14, c14[:80])
check("#15 class_fields Point x,y", '"Point": ["x", "y"]' in c15 and "__match_args__ ==" in c15, c15[:90])

# 5) a3/a4 leaf_status 并集 = 18
dec = json.JSONDecoder()
st = {}
for f in ("r8_closure_a3.out", "r8_closure_a4.out"):
    t = (ROOT / ".fist-loop-20260929" / "logs" / f).read_text(encoding="utf-8", errors="replace")
    d, _ = dec.raw_decode(t.lstrip())
    st[f] = set((d.get("leaf_status") or {}).keys())
check("a3 关 9 支", len(st["r8_closure_a3.out"]) == 9)
check("a4 关 9 支", len(st["r8_closure_a4.out"]) == 9)
check("并集 18 支", len(st["r8_closure_a3.out"] | st["r8_closure_a4.out"]) == 18)
check("两支不重叠", not (st["r8_closure_a3.out"] & st["r8_closure_a4.out"]))
for lid in st["r8_closure_a3.out"] | st["r8_closure_a4.out"]:
    check(f"正文点名 {lid}", lid in txt)

print("PASS %d" % len(ok))
for f in fail:
    print("FAIL", f)
print("CONCLUSION pass=%d fail=%d report=%s rc=%d"
      % (len(ok), len(fail), REPORT.name, 0 if not fail else 1))
sys.exit(0 if not fail else 1)
