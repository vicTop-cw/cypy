"""提交前称重量：把「将要新加进库」的未跟踪件按顶层目录汇总，并列出大件。

存在的理由：`.fist-loop-*/` 里既有几百 KB 的逐字回执，也有几十 MB 的可再生副本树；
`.gitignore` 改完之后必须**称一遍**才知道排除规则真的生效，而不是看 `git status` 的条目数猜。
"""

import collections
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIST = ROOT / ".qoder_untracked.txt"

tot = 0
bytop = collections.Counter()
byext = collections.Counter()
big = []
missing = []
for ln in LIST.read_text(encoding="utf-8").splitlines():
    ln = ln.strip().replace("\\", "/")
    if not ln:
        continue
    p = ROOT / ln
    if not p.exists():
        missing.append(ln)
        continue
    s = p.stat().st_size
    tot += s
    bytop[p.parts[0]] += s
    byext[p.suffix or "(noext)"] += s
    if s > 200_000:
        big.append((s, ln))

print(f"CONCLUSION clone_check total_mb={tot/1048576:.2f}")
print(f"  listed={len(LIST.read_text(encoding='utf-8').splitlines())} missing={len(missing)}")
for k, v in bytop.most_common(14):
    print(f"  DIR {k:<30} {v/1048576:8.2f} MB")
for k, v in byext.most_common(8):
    print(f"  EXT {k:<12} {v/1048576:8.2f} MB")
print("  BIG (>200KB):")
for s, ln in sorted(big, reverse=True)[:15]:
    print(f"    {s/1024:9.1f} KB  {ln}")
if missing:
    print("  MISSING sample:", missing[:5])
