"""语料扫描器：对指定树根下的每个 `.cypy` 跑「解析 + 静态分析」，逐档输出错误清单。

被 `advance_r3_lockproof.py` 在同一棵快照树的**两种状态**下各调一次（摘掉元数判定 / 复原），
两份输出逐档对表才叫"零新增红"。输出走 stdout 的 TSV，调用方按行解析并自证行数。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    tag = sys.argv[2] if len(sys.argv) > 2 else "state"
    sys.path.insert(0, str(root))
    from cypy_hook.hook import CypyHook  # noqa: E402  按传入树取模块，不碰工作区

    hook = CypyHook()
    dirs = [d for d in ("examples", "tests", "cypyc", "cypy_hook", "cypy_bridge", "docs", "scripts")
            if (root / d).exists()]
    rows = []
    for d in dirs:
        for path in sorted((root / d).rglob("*.cypy")):
            if "__pycache__" in set(path.parts):
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                _, errors = hook.analyze_only(text)
                rows.append({"file": rel, "errors": list(errors), "n": len(errors)})
            except Exception as exc:  # 扫描器不许把崩溃吞掉：如实记成 error
                rows.append({"file": rel, "errors": [f"SCAN-EXC {type(exc).__name__}: {exc}"],
                             "n": 1})
    print(json.dumps({"tag": tag, "root": str(root), "files": len(rows), "rows": rows},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
