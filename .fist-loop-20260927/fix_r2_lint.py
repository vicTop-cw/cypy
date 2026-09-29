#!/usr/bin/env python3
"""R2-修复：只判**本轮亲笔行**的 black/flake8，不拿整档存量债当本轮违例。

为什么不能整档跑：`cypyc/` 与 `cypy_hook/` 里 W293 有数千条（BUG-40/41 已入账的存量债），
按整档判 ⇒ 恒红，等于没有判据。这里按**行文本**钉住本轮插入/替换的物理行：

1. 每条亲笔行必须在目标文件里出现（`count>=1`）——不出现就是锚点自己写错了，直接 REFUSE；
2. black：整档 `format_str`，只要本轮任一亲笔行在 black 结果里**原样消失**就记违例
   （别人的行 black 想改不算，那是存量债）；
3. flake8：`--max-line-length=100`（pyproject 声明口径），只保留**行文本等于**某条亲笔行的结果。

刻意不收 `try:` / `return result` 这类通用行：它们在全仓多发，按文本匹配会把别人的债记到我头上。
对照（判据必须会红）：`--selftest` 用一条已知违例行（120 列）证明第 3 步真的在拦东西。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import black

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")

GENERATOR = "cypyc/codegen/cython_generator.py"
PARSER = "cypyc/parser/parser.py"
HOOK = "cypy_hook/hook.py"
CLI = "cypyc/cli.py"
PKG = "cypy_hook/__init__.py"
MACRO_EXP = "cypyc/parser/macro_expander.py"
TESTS = "tests/test_loop_20260927_fix_r2.py"

AUTHORED = {
    GENERATOR: [
        "    def _decorator_names(self, node: FuncDef) -> List[str]:",
        '            getattr(decorator.name, "id", str(decorator.name))',
        '            for decorator in (getattr(node, "decorators", None) or [])',
        "    def _is_selfless_method(self, node: FuncDef) -> bool:",
        '        return any(name in ("staticmethod", "classmethod")'
        " for name in self._decorator_names(node))",
        "    def _param_default_str(self, param) -> str:",
        '        if getattr(default, "id", None) == "__implicit_default__":',
        "            owner = self._type_to_str(param.type_annotation)",
        '            return f"{owner}.__implicit_default__()"',
        "        return self._expr_to_str(default)",
        '                param_str = f"{param_str}={self._param_default_str(param)}"',
        "        # @staticmethod/@classmethod 不绑定实例：视作「已带 self」以跳过自动注入（struct 路径）",
        "        selfless = self._is_selfless_method(node)",
        '        has_self = (bool(node.params) and node.params[0].name == "self") or selfless',
        "                # 在访问方法之前添加优化装饰器；binding(False) 只对绑定方法有意义（BUG-44）",
        "                if not self._is_selfless_method(method):",
    ],
    PARSER: [
        '                        getattr(default_value, "id", None) == "__implicit_default__"',
        "                        and type_annotation is None",
        '                            "__implicit_default__ default needs a parameter type'
        ' to desugar to, "',
        '                            f"found at {name_token.line}:{name_token.col}"',
        "        token = self._consume(TokenType.RETURN)",
        '        self._require_function_scope("return", token)',
        "    def __init__(self, tokens: Iterator[Token], body_scope: bool = False):",
        "        self._body_scope = body_scope",
        "        if not (self._in_function or self._body_scope):",
        "        saved_body_scope = self._body_scope",
        "        self._body_scope = True",
        "        self._body_scope = saved_body_scope",
    ],
    MACRO_EXP: ["            parser = Parser(tokens, body_scope=True)"],
    HOOK: [
        '                with open(source_path, "r", encoding="utf-8") as f:',
        "            except OSError as read_err:",
        '                result.errors.append(f"读取文件错误: {read_err}")',
    ],
    CLI: [
        '            print("[OK] Cypy import hook registered for the current process")',
        '            print("  Nothing is written to disk: the hook dies with this process.")',
        '            print("  To enable it in your own process, call'
        ' cypy_hook.install_hook() at startup.")',
        '            print("[OK] Cypy import hook unregistered for the current process")',
        '                print("[OK] Cypy import hook is active in the current process")',
        '                print("[INFO] Cypy import hook is not active in the current process")',
        '                print("  Cypy writes no persistent registration:")',
        '                print("  the hook lives or dies with the process that installed it.")',
    ],
    PKG: [
        "from .hook import CypyHook, install_hook, is_hook_installed, uninstall_hook",
        '__all__ = ["CypyHook", "install_hook", "uninstall_hook", "is_hook_installed"]',
    ],
}
WHOLE_FILE = [TESTS]

SCAN_TARGETS = sorted(set(list(AUTHORED) + WHOLE_FILE))


def main() -> int:
    selftest = "--selftest" in sys.argv
    refuse = []
    mode = black.Mode(line_length=100)

    texts = {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in SCAN_TARGETS}
    for rel, lines in AUTHORED.items():
        for ln in lines:
            if texts[rel].count(ln) < 1:
                refuse.append({"missing_authored_line": ln[:80], "file": rel})

    black_hits = []
    for rel in SCAN_TARGETS:
        text = texts[rel]
        mine = list(AUTHORED.get(rel, []))
        if rel in WHOLE_FILE:
            mine = [ln for ln in text.splitlines() if ln.strip()]
        try:
            after = black.format_str(text, mode=mode).splitlines()
        except Exception as exc:  # noqa: BLE001 - 报错本身就是判据内容
            refuse.append({"file": rel, "black_error": str(exc)[:200]})
            continue
        for ln in mine:
            if ln.strip() and ln not in after:
                black_hits.append({"file": rel, "text": ln.strip()[:90]})
    if black_hits:
        refuse.append({"black_would_change_authored_lines": black_hits})

    args = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "flake8",
        "--max-line-length=100",
        "--extend-ignore=E203,W503,E731",
        "--format=%(path)s|%(row)s|%(code)s",
        "--",
    ] + SCAN_TARGETS
    if selftest:
        probe = HERE / "fix_r2_lint_selfprobe.py"
        probe.write_text("x = " + repr("y" * 120) + "\n", encoding="utf-8", newline="\n")
        args = args[: -len(SCAN_TARGETS)] + [str(probe)]

    r = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    out = (r.stdout or "") + (r.stderr or "")
    log = HERE / ("fix_r2_lint_selfprobe.txt" if selftest else "fix_r2_lint.flake8.txt")
    log.write_text(out, encoding="utf-8", newline="\n")

    # flake8 的 %(text)s 是**诊断文案**不是源码行；物理行只能按 row 自己回读。
    def mine_of(rel):
        rel = rel.replace("\\", "/").lstrip("./")
        if rel in WHOLE_FILE or (ROOT / rel).name in WHOLE_FILE:
            return {x for x in texts.get(rel, "").splitlines() if x.strip()}
        return set(AUTHORED.get(rel, ()))

    flake_hits = []
    matched_any = False
    probe_rows = set()
    if selftest:
        probe_text = (HERE / "fix_r2_lint_selfprobe.py").read_text(encoding="utf-8")
        probe_rows = {i + 1 for i, x in enumerate(probe_text.splitlines()) if x.strip()}
    for ln in out.splitlines():
        parts = ln.split("|")
        if len(parts) != 3:
            continue
        path, row_txt, code = parts
        rel = path.replace("\\", "/").lstrip("./")
        try:
            row = int(row_txt)
        except ValueError:
            continue
        if selftest:
            if rel.endswith("fix_r2_lint_selfprobe.py") and code == "E501" and row in probe_rows:
                matched_any = True
                flake_hits.append({"file": rel, "code": code, "row": row})
            continue
        body = texts.get(rel)
        if body is None:
            continue
        lines = body.splitlines()
        physical = lines[row - 1] if 1 <= row <= len(lines) else None
        if physical is not None and physical in mine_of(rel):
            matched_any = True
            flake_hits.append(
                {"file": rel, "code": code, "row": row, "text": physical.strip()[:80]}
            )
    if selftest:
        verdict = "selfprobe-caught" if matched_any else "SELFTEST-REFUSE(E501 未被抓到)"
        doc = {
            "selftest": verdict,
            "hits": flake_hits,
            "probe": "120 列赋值行（必然违例）",
            "expected": "E501 被抓到才算判据会红",
        }
        (HERE / "fix_r2_lint_selftest.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0 if matched_any else 1
    if flake_hits:
        refuse.append({"flake8_on_authored_lines": flake_hits})

    doc = {
        "refuse": refuse,
        "authored_lines_checked": sum(len(v) for v in AUTHORED.values())
        + len([x for x in texts[TESTS].splitlines() if x.strip()]),
        "files_scanned": SCAN_TARGETS,
        "flake8_raw_lines": len(out.splitlines()),
        "flake8_rc": r.returncode,
    }
    (HERE / "fix_r2_lint.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
