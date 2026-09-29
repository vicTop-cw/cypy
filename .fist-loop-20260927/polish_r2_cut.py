#!/usr/bin/env python3
"""R2-打磨 的删死代码驱动（BUG-42）：先证"这一份从不执行"，再按**唯一锚点**摘除。

用法：python .fist-loop-20260927/polish_r2_cut.py            # 执行
      python .fist-loop-20260927/polish_r2_cut.py --dry-run  # 只验锚点，不落盘

四条纪律（都对应本轮真实踩过的坑）：
1. **生效性先量后删**：用 `类.__dict__[名].__code__.co_firstlineno` 钉住 Python 实际绑定的那一份，
   删的是行号不等于它的那一份；绑定行号与待删行号相等 ⇒ 立即 REFUSE（那是在删活码）。
2. **锚点 count==1 且逐字回读**：块文本由"文件当前行切片"得到，再断言它与预期 needle 集合一致、
   在整档里只出现一次；落盘后二次校验"这段文本确实没了"。
3. **变异必须可证**：`new != src`、同名 def 计数从 2 变 1、`ast.parse` 仍可解析，任一不过即拒绝。
4. **幂等守卫**：待删块不在盘上时**报拒绝**而不是静默成功（防止重跑把"已删"当成"又删了一次"）。
   被删块全文进 evidence（`removed_text`），含唯一逻辑的那份（scope 守卫文案）留档可回放。
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
OUT = ROOT / ".fist-loop-20260927" / "polish_r2_cut.json"
DRY = "--dry-run" in sys.argv[1:]

TARGETS = [
    {
        "id": "bug42_expr_stmt",
        "rel": "cypyc/codegen/cython_generator.py",
        "klass": "CythonGenerator",
        "name": "_visit_ExprStmt",
        "anchor": "表达式语句：解包内部节点并写出",
        # 死份独有：走 _visit 分发；活份独有：宏展开。两者不得混。
        "must_contain": ["getattr(node, 'value', None)", "self._visit(inner)"],
        "must_not_contain": ["_expand_macro", "_is_macro_call"],
        "live_marker": "_expand_macro",
    },
    {
        "id": "bug42_meta_block",
        "rel": "cypyc/analyzer/scope_analyzer.py",
        "klass": "ScopeAnalyzer",
        "name": "_visit_MetaBlock",
        "anchor": "处理 meta 块，确保只能在模块顶级定义",
        "must_contain": [
            'self.current_scope.kind != "module"',
            "meta block can only be defined at module level",
        ],
        "must_not_contain": ["允许前向引用"],
        "live_marker": "允许前向引用",
    },
]

PROBE = """
import json, sys
sys.path.insert(0, r'{root}')
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
CLS = {{'CythonGenerator': CythonGenerator, 'ScopeAnalyzer': ScopeAnalyzer}}
pairs = {pairs}
out = {{}}
for cls_name, meth in pairs:
    fn = CLS[cls_name].__dict__[meth]
    out[meth] = int(fn.__code__.co_firstlineno)
    out[meth + '__module'] = fn.__module__
print(json.dumps(out))
""".strip()


def bound_lines() -> dict:
    """子进程里重导产品码，取 Python 实际绑定的那份的首行号（含 __module__ 反查身份）。"""
    pairs = "[" + ",".join('("%s", "%s")' % (t["klass"], t["name"]) for t in TARGETS) + "]"
    script = PROBE.format(root=str(ROOT), pairs=pairs)
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError("binding probe rc=%s err=%s" % (proc.returncode, proc.stderr[-400:]))
    return json.loads(proc.stdout.strip().splitlines()[-1])


def def_lines(lines: list, name: str) -> list:
    """类体内 `def <name>(` 的行号（1 基）；只认 4 空格缩进，避免误抓嵌套函数。"""
    needle = "def %s(" % name
    return [i + 1 for i, ln in enumerate(lines) if ln.startswith("    ") and needle in ln[4 : 4 + len(needle) + 1]]


def block_slice(lines: list, start_idx: int) -> tuple:
    """从 def 行下标向下取到"块尾 + 紧随的一个空行"。

    块边界用缩进而非行号：语句行缩进 > 4；空行只在"后面还接深缩进"时算块内。
    """
    i = start_idx
    j = i + 1
    last_stmt = i
    while j < len(lines):
        ln = lines[j]
        if ln.strip() == "":
            k = j + 1
            if k < len(lines) and lines[k].startswith("        "):
                j += 1
                continue
            break
        if ln.startswith("        "):
            last_stmt = j
            j += 1
            continue
        break
    tail = last_stmt + 1
    swallowed_blank = False
    if tail < len(lines) and lines[tail].strip() == "":
        swallowed_blank = True
        tail += 1
    return i, tail, swallowed_blank


def main() -> int:
    refuse: list = []
    measures: dict = {}

    try:
        bound = bound_lines()
    except Exception as exc:  # 探针坏了就整体拒绝，不能退回"按我看顺眼的那份"
        print(json.dumps({"refuse": ["生效性探针失败：%s" % exc], "dry_run": DRY}, ensure_ascii=False))
        return 1

    for target in TARGETS:
        rel, name, klass = target["rel"], target["name"], target["klass"]
        path = ROOT / rel
        rec = {"rel": rel, "qualified": "%s.%s" % (klass, name), "bound_line": bound.get(name)}
        if not path.exists():
            refuse.append("%s 文件不在盘上" % rel)
            measures[target["id"]] = rec
            continue
        src = path.read_text(encoding="utf-8")
        lines = src.split("\n")
        defs = def_lines(lines, name)
        rec["def_lines_before"] = defs
        if len(defs) != 2:
            refuse.append("%s 期望 2 处同名 def，实测 %s ⇒ 幂等守卫：本目标已不处于待删状态" % (rel, defs))
            measures[target["id"]] = rec
            continue
        dead_line = defs[0]  # 类体内后定义覆盖前定义 ⇒ 第一份是死码
        if dead_line == bound.get(name):
            refuse.append("%s 待删行号 %s 正是绑定行号 ⇒ 不敢删活码" % (rel, dead_line))
            measures[target["id"]] = rec
            continue
        if defs[1] != bound.get(name):
            refuse.append(
                "%s 绑定行号 %s 既不是第一份也不是第二份 %s ⇒ 身份前提破了" % (rel, bound.get(name), defs)
            )
            measures[target["id"]] = rec
            continue

        i, tail, swallowed = block_slice(lines, dead_line - 1)
        block = "\n".join(lines[i:tail])
        if target["anchor"] not in block:
            refuse.append("%s 块内找不到锚点 %r" % (rel, target["anchor"]))
        for needle in target["must_contain"]:
            if needle not in block:
                refuse.append("%s 死份块内缺独有语句 %r" % (rel, needle))
        for needle in target["must_not_contain"]:
            if needle in block:
                refuse.append("%s 死份块里出现了活份标记 %r ⇒ 切片越界" % (rel, needle))
        if target["live_marker"] not in "\n".join(lines[tail:]):
            refuse.append("%s 切片之后的剩余文本里没有活份标记 ⇒ 活份被切掉了" % rel)
        if src.count(block) != 1:
            refuse.append("%s 块文本在整档出现 %s 次（要 1 次）" % (rel, src.count(block)))
        rec.update(
            {
                "removed_range": [dead_line, tail],
                "removed_lines": tail - i,
                "swallowed_trailing_blank": swallowed,
                "removed_sha8": hashlib.sha256(block.encode("utf-8")).hexdigest()[:8],
                "removed_chars": len(block),
                "removed_text": block,
            }
        )
        measures[target["id"]] = rec
        if refuse:
            continue

        new = "\n".join(lines[:i] + lines[tail:])
        if new == src:
            refuse.append("%s 变异后与原文逐字相同 ⇒ 没删掉任何东西" % rel)
            continue
        try:
            ast.parse(new)
        except SyntaxError as exc:
            refuse.append("%s 删除后语法破裂：%s" % (rel, str(exc)[:160]))
            continue
        after_defs = def_lines(new.split("\n"), name)
        if len(after_defs) != 1:
            refuse.append("%s 删除后同名 def 计数 %s（要 1）" % (rel, after_defs))
            continue
        if block in new:
            refuse.append("%s 删除后块文本仍在盘上" % rel)
            continue
        if not DRY:
            path.write_text(new, encoding="utf-8")
            verify = path.read_text(encoding="utf-8")
            if verify != new:
                refuse.append("%s 落盘回读与期望不一致" % rel)
            if block in verify:
                refuse.append("%s 回读仍能匹配到被删块" % rel)
        rec["after_def_lines"] = after_defs
        rec["after_bound_line"] = None
        rec["applied"] = not DRY

    post = {} if DRY else bound_lines()
    for target in TARGETS:
        rec = measures.get(target["id"]) or {}
        if rec.get("applied"):
            rec["after_bound_line"] = post.get(target["name"])
            if rec["after_bound_line"] is None:
                refuse.append("%s 删除后绑定探针取不到 %s" % (target["rel"], target["name"]))
            elif rec["after_bound_line"] in rec.get("def_lines_before", []):
                refuse.append(
                    "%s 删除后绑定行号 %s 落在删除前的旧行号里 ⇒ 行号未上移，怀疑没生效"
                    % (target["rel"], rec["after_bound_line"])
                )
    out = {"dry_run": DRY, "bound_lines": bound, "post_bound_lines": post, "measures": measures, "refuse": refuse}
    if not DRY:
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "dry_run": DRY,
        "bound_lines_before": bound,
        "bound_lines_after": post,
        "removed_lines": {t["id"]: (measures.get(t["id"]) or {}).get("removed_lines") for t in TARGETS},
        "refuse": refuse,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not refuse else 1


if __name__ == "__main__":
    raise SystemExit(main())
