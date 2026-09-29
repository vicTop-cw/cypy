#!/usr/bin/env python3
"""把 `close_*_root.out.json` 的被拒清单**按作用域分栏**——通用件，后续 8 个环节复用。

为什么要分栏而不是数总数（R2-打磨 的实测结论）：
 - 根任务上的 6 条是**既定语义**：description 不带 `[omega:required]` ⇒ omega 三连被拒；
   叶级联把根推到 `待验收` ⇒ claim/execute/submit 各被拒一次；
 - **枝干**上每出现一条（`omega_spec_create` 已通过审核 / `omega_spec_review` 非待审核 /
   `verify` 需先 submit）都意味着上卷驱动被重跑过——那不是服务端语义，是操作记录。
只看总数会把这两类混成一类，进而把"我重跑了驱动"洗成"服务端本来就这样"。

用法：python root_refusal_split.py <close_X_root.out.json> <out.json> [根任务号]
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path


def scope(task_id: str, root_task: str) -> str:
    if task_id == root_task or "." not in task_id:
        return "root"
    return "branch" if task_id.count(".") == 1 else "leaf"


def main() -> int:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    d = json.loads(src.read_text(encoding="utf-8"))
    root_task = sys.argv[3] if len(sys.argv) > 3 else d.get("root_task") or ""
    refused = [r for r in (d.get("refused") or []) if isinstance(r, dict)]
    by_scope = collections.Counter(scope(r.get("task_id", ""), root_task) for r in refused)
    # 三个作用域**恒定出现**（0 也要写出来）：Counter 会整个省掉零键，
    # 于是"枝干没有重跑"这条断言在盘上无从查起——缺席不能被读成"零"，也可能是"根本没统计"。
    for _s in ("root", "branch", "leaf"):
        by_scope.setdefault(_s, 0)
    by_call = collections.Counter(r.get("call", "?") for r in refused)
    shapes = collections.Counter(
        (scope(r.get("task_id", ""), root_task), r.get("call", "?"), str(r.get("error", ""))[:40])
        for r in refused
    )
    out = {
        "source": src.as_posix(),
        "root_task": root_task,
        "root_final": d.get("root_final"),
        "leaves_done": d.get("leaves_done"),
        "refused_total": len(refused),
        "by_scope": dict(by_scope),
        "by_call": dict(by_call),
        "distinct_shapes": [f"{s}/{c}: {e} ×{n}" for (s, c, e), n in sorted(shapes.items(), key=lambda kv: -kv[1])],
        "reading": "root 那 6 条是既定语义；branch 上任何一条都说明上卷驱动被重跑过。",
    }
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"total": out["refused_total"], "by_scope": out["by_scope"],
                      "root_final": out["root_final"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
