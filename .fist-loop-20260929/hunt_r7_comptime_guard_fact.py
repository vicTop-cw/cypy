"""M4 判据的事实核：全语料里有没有「kind == ComptimeStmt 且携带 type_annotation」的节点。

有 ⇒ `_validate_annotation_shapes` 的跳过条件承重；一个都没有 ⇒ 该条件是死代码，
删掉它不改变任何行为（并把结论逐字记进报告，不留下一个「看着像在防什么」的守卫）。
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402


def walk(node, acc):
    acc.append(node)
    for value in vars(node).values():
        if isinstance(value, (list, tuple)):
            for v in value:
                if hasattr(v, "kind"):
                    walk(v, acc)
        elif hasattr(value, "kind"):
            walk(value, acc)
    return acc


def main() -> int:
    files = sorted(glob.glob(str(ROOT / "examples" / "**" / "*.cypy"), recursive=True))
    files += sorted(glob.glob(str(ROOT / ".fist-loop-*" / "hunts" / "*.cypy")))
    parsed = skipped = comptime = hits = 0
    for f in files:
        try:
            ast = Parser(list(Lexer(Path(f).read_text(encoding="utf-8")).tokenize())).parse()
        except Exception:  # noqa: BLE001  对抗语料本来就故意写坏，解析不了的不计入分母
            skipped += 1
            continue
        parsed += 1
        for node in walk(ast, []):
            if getattr(node, "kind", None) == "ComptimeStmt":
                comptime += 1
                if getattr(node, "type_annotation", None) is not None:
                    hits += 1
                    print("HIT", Path(f).relative_to(ROOT).as_posix())
    print(f"CONCLUSION files={len(files)} parsed={parsed} unparsable={skipped} "
          f"ComptimeStmt_nodes={comptime} with_type_annotation={hits}")
    return 0 if parsed else 1


if __name__ == "__main__":
    sys.exit(main())
