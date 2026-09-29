#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T0r258.5.1 自门控探针 —— 语法状态文档与代码实测的一致性核对（只读，幂等）。

核对对象：
  STATUS = SYNTAX_IMPLEMENTATION_STATUS.md
  REVIEW = docs/SYNTAX_CHANGE_REVIEW.md

一致性判据（全部可机检，不靠肉眼）：对每个标 ✅ 的特性，在 cypyc/ 里找它的落点
（lexer 的 KEYWORDS 映射 / parser.py 的 AST 类名 / codegen 的 _visit_X /
Token 字面量 / cli 子命令）；对每个标 ❌ 的特性，验证落点确实不存在，并在进程内
实测该语法能不能被 Lexer+Parser 消化成专属 AST 节点。

规则（X1~X6 过门，X7/X8 只报不门）：
  X1 FALSE_DONE    : 标 ✅ 但 cypyc/ 无任何落点 —— 文档宣称完成，代码里没有
  X2 FALSE_TODO    : 标 ❌ 但已有落点 —— 文档漏报已实现
  X3 CONTRADICTION : 同一语法串在两份文档里一边 ✅ 一边 ❌
  X4 PHANTOM_SPEC  : 被指为某特性规范的文件，对该特性关键字大面积零提及
  X5 PHANTOM_FILE  : 当作「现有/已创建」列出的 test_*.py / *.cypy / NN-xxx.md 不存在
  X6 KEYWORD_CLAIM : 「保留 / 已移除」标记与 lexer 实测相反
  X7 STAT_DELTA    : §1 统计概览数字与实测的偏差（INFO：计数口径写死在探针里）
  X8 PARSE_PROBE   : ❌ 语法的进程内解析实测原文 + duck 阳性对照（INFO）

needle 陷阱（本探针因此不按子串 grep）：字符串 "constraint" 在 cypyc/ 里有 100+ 次
命中，全部是 duck_constraints / _check_return_value_constraints 之类的英文单词，
不是语言关键字；`SUBTYPE` 是运算符 `<:` 的 Token 名，与 `subtype` 声明无关。
所以落点只认「表」：KEYWORDS 字典键、class X(ASTNode)、def _visit_X、
Token(TokenType.X, "字面量")、add_parser("子命令")。

退出码：
  0 = 已修（两份文档与代码实测完全一致）
  1 = 缺陷仍在（任一 X1~X6 命中）
  2 = 判据自身出错（文档或 cypyc/ 缺失，既非实现问题也非探针问题）
  3 = 探针自身异常（harness bug）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                          # pragma: no cover
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DOC_A = ROOT / "SYNTAX_IMPLEMENTATION_STATUS.md"
DOC_B = ROOT / "docs" / "SYNTAX_CHANGE_REVIEW.md"
CYPYC = ROOT / "cypyc"
SYNTAX_DIR = ROOT / "SYNTAX"

SNIPPET = re.compile(r"`([^`]+)`")
FILE_ROW = re.compile(r"^\s*`?([\w.-]+\.(?:md|py|cypy))`?\s*$")
CAMEL = re.compile(r"\b([A-Z][A-Za-z0-9]{2,})\b")
# 语法串里当占位变量用的短词，不能当关键字探针
PLACEHOLDER = {"x", "a", "b", "y", "z", "n", "v", "f", "i", "j", "ts", "self", "name",
               "params", "body", "args", "ret", "value", "dir", "items", "obj", "elem",
               "typeclassdef"}
NOISE_CAMEL = {"Self", "None", "True", "False", "AST", "Tokens", "Codegen", "SIMD", "OK"}


# --------------------------------------------------------------------- code index
class CodeIndex:
    """cypyc/ 的真实落点索引（只读一次，不写任何东西）。"""

    def __init__(self):
        files = sorted(p for p in CYPYC.rglob("*.py"))
        blob = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
        all_text = "\n".join(blob.values())
        lexer = blob.get(CYPYC / "parser" / "lexer.py", "")
        parser = blob.get(CYPYC / "parser" / "parser.py", "")
        cli = blob.get(CYPYC / "cli.py", "")
        gen = blob.get(CYPYC / "codegen" / "cython_generator.py", "")

        kw = re.search(r"KEYWORDS\s*=\s*\{(.*?)\n\s*\}", lexer, re.S)
        self.keywords = (set(re.findall(r'"([a-zA-Z_0-9]+)":\s*TokenType\.', kw.group(1)))
                         if kw else set())
        self.ast_classes = set(re.findall(r"^class (\w+)\b", parser, re.M))
        self.visitors = set(re.findall(r"def _visit_(\w+)", gen))
        self.token_members = set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]*)\s*=\s*\"", lexer, re.M))
        self.token_literals = set(re.findall(
            r"""Token\(TokenType\.\w+,\s*["']([^"']+)["']""", lexer))
        self.subcommands = set(re.findall(r'add_parser\(\s*\n?\s*"([\w-]+)"', cli))
        self.token_uses = {t: len(re.findall(r"TokenType\.%s\b" % t, all_text))
                           for t in self.token_members}
        self.stats = {
            "tokentype 定义": len(self.token_members),
            "keywords 映射": len(self.keywords),
            "ast 节点类": len(re.findall(r"^class \w+\(ASTNode\)", parser, re.M)),
            "codegen _visit_ 方法": len(self.visitors),
        }

    def landing(self, words, nodes, operators):
        for w in words:
            if w in self.keywords:
                return True, "lexer KEYWORDS 有 %r" % w
            if w in self.subcommands:
                return True, "cli 子命令 cypyc %s" % w
        for c in nodes:
            if c in self.ast_classes:
                return True, "parser.py 有 class %s" % c
            if c in self.visitors:
                return True, "codegen 有 _visit_%s" % c
        for op in operators:
            if op in self.token_literals:
                return True, "lexer 产出字面量 %r 的 Token" % op
        return False, ("无落点（KEYWORDS/AST 类/_visit_/Token 字面量/cli 子命令 "
                       "五张表均未命中：words=%s nodes=%s ops=%s）"
                       % (words or "-", nodes or "-", operators or "-"))


# ------------------------------------------------------------------ markdown scan
def split_cells(line: str):
    """按 | 切单元格，但反引号内的 | 与转义的 \\| 不算分隔符。"""
    cells, buf, in_code = [], [], False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
        elif ch == "|" and not in_code:
            cells.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return [c.strip() for c in cells[1:-1]] if line.startswith("|") else []


def iter_rows(path: Path):
    """产出 (当前小节标题, 单元格列表, 行号)。跳过表头与分隔行。"""
    heading = ""
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        h = re.match(r"^#{1,4}\s+(.*)", raw)
        if h:
            heading = h.group(1).strip()
            continue
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = split_cells(line)
        if len(cells) < 2 or all(set(c) <= set("-: ") for c in cells):
            continue
        if all(not re.search(r"[✅❌⚠]|[A-Za-z_\u4e00-\u9fff]", c) or
               re.fullmatch(r"(状态|实现状态|特性|语法|AST ?节点|类别|数量|文档|关键字|Token|"
                            r"功能|文件|建议|测试类别|需补充内容|覆盖范围|计划版本|说明|处理方式|"
                            r"内容|需更新|现有测试|问题?说明|文档位置|语法|测试文件|文档状态)", c)
               for c in cells):
            continue                      # 表头行
        yield heading, cells, no


def probes_from(cell: str):
    """一个「语法/特性」单元格 -> (关键字候选, 运算符候选, AST 名候选)。

    语法的第一个 token 决定这条构造的探针类型：
      - `cypyc <子命令>` -> cli 子命令；
      - 单元占位符（A/B/x/a，如 `A | B`、`x |> f(args)`）-> 运算符字面量；
      - 大写开头的标识符（`StructField`）-> AST 类名；
      - 其余小写词 -> lexer 关键字。
    """
    words, operators, nodes = [], [], []
    for s in SNIPPET.findall(cell):
        s = s.strip()
        if not s or FILE_ROW.match(s):
            continue
        head = re.match(r"([A-Za-z_][A-Za-z_0-9]*)", s)
        if not head:
            operators += re.findall(r"[^\w\s]+", s)
            continue
        tok = head.group(1)
        low = tok.lower()
        if low == "cypyc":                       # `cypyc build <dir>`
            nxt = re.findall(r"[A-Za-z_][A-Za-z_0-9]*", s)[1:2]
            if nxt:
                words.append(nxt[0].lower())
        elif len(tok) == 1 or low in PLACEHOLDER:
            operators += re.findall(r"[^\w\s]+", s)   # 占位符打头 = 运算符式构造
        elif tok[0].isupper():
            if tok not in NOISE_CAMEL:
                nodes.append(tok)
        elif len(low) > 1:
            words.append(low)
        else:
            operators += re.findall(r"[^\w\s]+", s)
    return words, operators, nodes


def nodes_from(cell: str):
    return [c for c in CAMEL.findall(cell or "") if c not in NOISE_CAMEL]


def marker_of(cells):
    for c in cells[1:]:
        if "✅" in c:
            return "DONE"
        if "❌" in c:
            return "TODO"
        if "⚠" in c:
            return "PART"
    return None


def norm_key(cell: str):
    sn = SNIPPET.findall(cell)
    base = sn[0] if sn else cell
    return re.sub(r"\s+", " ", base).strip().lower()


# ------------------------------------------------------------------------ checks
def check_markers(idx: CodeIndex, path: Path, tag: str, claims, findings):
    for heading, cells, no in iter_rows(path):
        state = marker_of(cells)
        if state is None:
            continue
        fm = FILE_ROW.match(cells[0])
        loc = "%s:%d" % (path.name, no)
        if fm:                                   # 文件行：查存在性，不查落点
            name = fm.group(1)
            exists = (SYNTAX_DIR / name).exists() or (ROOT / name).exists() \
                or any(p.name == name for p in ROOT.rglob(name))
            claims.append((tag, norm_key(cells[0]), state, loc))
            if state == "DONE" and not exists:
                findings.append(("X5 PHANTOM_FILE", loc,
                                 "表格（%s）把 %s 标成 ✅ 完整/已创建，但仓库里没有该文件"
                                 % (heading[:24], name)))
            continue
        words, operators, snodes = probes_from(cells[0])
        names = snodes + nodes_from(cells[1] if len(cells) > 1 else "")
        hit, why = idx.landing(words, names, operators)
        claims.append((tag, norm_key(cells[0]), state, loc))
        detail = " | ".join(cells)[:96]
        if state == "DONE" and not hit:
            findings.append(("X1 FALSE_DONE", loc,
                             "标 ✅ 但 %s\n        行: %s" % (why, detail)))
        elif state == "TODO" and hit:
            findings.append(("X2 FALSE_TODO", loc,
                             "标 ❌ 但已存在落点 -> %s\n        行: %s" % (why, detail)))


def check_contradictions(claims, findings):
    by_key = {}
    for tag, key, state, loc in claims:
        by_key.setdefault(key, []).append((tag, state, loc))
    for key, entries in sorted(by_key.items()):
        states = {s for _t, s, _l in entries}
        if {"DONE", "TODO"} <= states:
            findings.append(("X3 CONTRADICTION", key,
                             "同一语法两份文档互相打架: "
                             + ", ".join("%s=%s@%s" % e for e in entries)))


def check_specs(findings):
    """(a) 被指为某特性规范的文件是否真写着那个特性；(b) 列为待建的文件是否早已存在。"""
    docs = {}
    for path in (DOC_A, DOC_B):
        docs[path] = path.read_text(encoding="utf-8")
    for path, text in docs.items():
        heading = ""
        for no, line in enumerate(text.splitlines(), 1):
            h = re.match(r"^#{1,4}\s+(.*)", line)
            if h:
                heading = h.group(1)
            targets = re.findall(r"(\d\d-[a-z0-9-]+\.md)", line)
            if not targets:
                continue
            claimed = sorted({w.lower() for w in re.findall(r"`([a-z_]{4,})`", line)
                              if w.lower() not in ("code", "self", "true", "name")})
            loc = "%s:%d" % (path.name, no)
            for t in targets:
                f = SYNTAX_DIR / t
                exists = f.exists()
                # (b) 「需要新增」小节里列为待建，却早已存在，且同文档没有 已创建 记录
                if ("新增" in heading and exists
                        and not re.search(r"%s.*已创建|已创建.*%s" % (t, t), text)):
                    findings.append(("X4 PHANTOM_SPEC", loc,
                                     "%s 在「%s」里仍列为待新建，但 SYNTAX/%s 已存在（%d 行）"
                                     "—— 该小节未跟进" % (t, heading[:24], t,
                                                    len(f.read_text(encoding='utf-8')
                                                        .splitlines()))))
                if not exists:
                    if re.search(r"已创建|✅", line):
                        findings.append(("X4 PHANTOM_SPEC", loc,
                                         "宣称已创建 %s，但 SYNTAX/%s 不存在" % (t, t)))
                    continue
                # (a) 指向性：该文件是否真写着被指派的特性
                body = f.read_text(encoding="utf-8", errors="replace")
                counts = {w: body.count(w) for w in claimed}
                absent = [w for w, c in counts.items() if c == 0]
                if claimed and len(absent) * 2 >= len(claimed):
                    findings.append(("X4 PHANTOM_SPEC", loc,
                                     "%s 被 %s 指为 %s 的规范文件，但逐词实测 %s；"
                                     "该文件全文 %d 行，实际内容是 duck 约束（'duck' 出现 %d 次）"
                                     % (t, path.name, "/".join(claimed),
                                        ", ".join("%s=%d" % kv for kv in sorted(counts.items())),
                                        len(body.splitlines()), body.count("duck"))))


def check_files(findings):
    """当作「现有 / 已创建」列出的 test_*.py / *.cypy。"""
    for path in (DOC_A, DOC_B):
        heading = ""
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            h = re.match(r"^#{1,4}\s+(.*)", line)
            if h:
                heading = h.group(1)
            if not re.search(r"已创建|已执行|现有|覆盖范围", line + " " + heading):
                continue
            for f in sorted(set(re.findall(r"`((?:test_)?[\w-]+\.(?:py|cypy))`", line))):
                found = [p for p in ROOT.rglob(Path(f).name)
                         if ".git" not in p.parts and "__pycache__" not in p.parts
                         and "node_modules" not in p.parts]
                if not found:
                    findings.append(("X5 PHANTOM_FILE", "%s:%d" % (path.name, no),
                                     "小节「%s」把 %s 当作现有/已创建，仓库里不存在"
                                     % (heading[:28], f)))


def check_keyword_claims(idx: CodeIndex, findings):
    """REVIEW §7.1 的「保留 / 已移除」标记 vs lexer 实测。"""
    for no, line in enumerate(
            DOC_B.read_text(encoding="utf-8").splitlines(), 1):
        m = re.search(r"`([A-Za-z_][A-Za-z_0-9]*)`\s*(关键字)?\s*(?:Token)?\s*[-–]\s*"
                      r"(?:✅|❌)\s*\*\*(.+?)\*\*", line)
        if not m:
            continue
        name, claim = m.group(1), m.group(3)
        if name.isupper():
            present = name in idx.token_members and idx.token_uses.get(name, 0) > 1
            real = "TokenType.%s 成员=%s，全仓引用 %d 处" % (
                name, name in idx.token_members, idx.token_uses.get(name, 0))
        else:
            present = name.lower() in idx.keywords
            real = "lexer KEYWORDS 有 %r = %s" % (name.lower(), present)
        loc = "%s:%d" % (DOC_B.name, no)
        if "移除" in claim and present:
            findings.append(("X6 KEYWORD_CLAIM", loc,
                             "宣称 %s 已移除，实测 %s" % (name, real)))
        elif "保留" in claim and not present:
            findings.append(("X6 KEYWORD_CLAIM", loc,
                             "宣称 %s 保留（%s），实测 %s" % (name, claim, real)))


def _walk_names(node, out):
    out.add(type(node).__name__)
    for v in getattr(node, "__dict__", {}).values():
        for item in (v if isinstance(v, list) else [v]):
            if hasattr(item, "__dict__"):
                _walk_names(item, out)


def parse_probe_evidence():
    """X8：❌ 语法的进程内解析实测 + duck 阳性对照。"""
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
    except Exception as e:                                  # pragma: no cover
        return ["import cypyc.parser 失败: %s（本项 INFO，不过门）" % e]
    cases = [
        ("constraint Name = A | B", "ConstraintDef"),
        ("subtype A <: B", "SubtypeDecl"),
        ("dispatch name(x: int) -> int", "DispatchDecl"),
        ("meta:\n    duck Num:\n        a + b -> Self", "DuckDef/MetaBlock（阳性对照）"),
    ]
    out = []
    for src, want in cases:
        expected = {w.strip("（）") for w in re.split(r"[/（]", want) if w.strip("（）")}
        try:
            ast = Parser(Lexer(src).tokenize()).parse()
            names = set()
            for n in getattr(ast, "body", []):
                _walk_names(n, names)
            top = sorted({type(n).__name__ for n in getattr(ast, "body", [])})
            hit = sorted(n for n in names if n in expected or any(
                e in n for e in expected if len(e) > 6))
            out.append("%-30r 解析通过 body=%s；AST 全集含 %s -> 专属节点 %s"
                       % (src.splitlines()[0], top, sorted(names)[:6],
                          hit or "无"))
        except Exception as e:
            out.append("%-30r 解析抛 %s: %s"
                       % (src.splitlines()[0], type(e).__name__, e))
    return out


def hr(title):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> int:
    hr("T0r258.5.1  语法状态文档 vs 代码实测")
    for p in (DOC_A, DOC_B):
        if not p.exists():
            print("[docs] 缺少 %s —— 判据自身出错" % p)
            return 2
    if not CYPYC.is_dir():
        print("[docs] 缺少 cypyc/ —— 判据自身出错")
        return 2

    idx = CodeIndex()
    print("cypyc/ 实测落点索引：")
    print("  KEYWORDS 关键字        %4d 个" % len(idx.keywords))
    print("  parser.py class 总数   %4d 个（其中 ASTNode 子类 %d）"
          % (len(idx.ast_classes), idx.stats["ast 节点类"]))
    print("  codegen _visit_ 方法   %4d 个" % len(idx.visitors))
    print("  TokenType 成员         %4d 个" % len(idx.token_members))
    print("  Token 字面量           %4d 个" % len(idx.token_literals))
    print("  cli 子命令             %s" % sorted(idx.subcommands))
    print("  三条 ❌ 目标词实测：constraint=%s subtype=%s dispatch=%s（KEYWORDS 命中与否）"
          % ("constraint" in idx.keywords, "subtype" in idx.keywords,
             "dispatch" in idx.keywords))
    print("  同名 AST 类实测：ConstraintDef/SubtypeDecl/DispatchDecl 存在 = %s/%s/%s"
          % tuple(c in idx.ast_classes for c in
                  ("ConstraintDef", "SubtypeDecl", "DispatchDecl")))

    findings, claims = [], []
    check_markers(idx, DOC_A, "STATUS", claims, findings)
    check_markers(idx, DOC_B, "REVIEW", claims, findings)
    check_contradictions(claims, findings)
    check_specs(findings)
    check_files(findings)
    check_keyword_claims(idx, findings)

    hr("标记核对明细（%d 条 ✅/❌/文件 断言）" % len(claims))
    for tag, key, state, loc in claims:
        print("  %-6s %-4s %-34s %s" % (tag, state, key[:34], loc))

    info = []
    hr("X7 §1 统计概览 vs 实测（INFO，不过门）")
    seen = set()
    for _h, cells, no in iter_rows(DOC_A):
        label = re.sub(r"\s+", " ", cells[0].replace("`", " ").strip().lower())
        if label in seen or not re.fullmatch(r"\d+", cells[-1].strip()):
            continue
        real = idx.stats.get(label)
        if real is None:
            continue
        seen.add(label)
        claimed = int(cells[-1].strip())
        print("  %-22s 文档=%-4d 实测=%-4d %s  (%s:%d)"
              % (cells[0].replace("`", "").strip(), claimed, real,
                 "一致" if real == claimed else "偏差", DOC_A.name, no))
        if real != claimed:
            info.append("%s 文档=%d 实测=%d" % (cells[0].replace("`", "").strip(),
                                               claimed, real))

    hr("X8 ❌ 语法进程内实测（INFO，不过门）")
    for line in parse_probe_evidence():
        print("  " + line)

    hr("一致性判定")
    tally = {}
    for code, _l, _m in findings:
        tally[code] = tally.get(code, 0) + 1
    for code, loc, msg in findings:
        print("  [%s] %s\n        %s" % (code, loc, msg))
    print("\n  过门规则命中: " + (", ".join("%s=%d" % kv for kv in sorted(tally.items()))
                                or "无"))
    if info:
        print("  INFO（不过门）: " + "; ".join(info))

    hr("VERDICT")
    if findings:
        print("REPRODUCED —— 文档标记与代码实测不一致 %d 处（X1~X6）。" % len(findings))
        return 1
    print("NOT-REPRODUCED —— 两份文档的 ✅/❌ 标记、规范文件指向与关键字存废均与代码实测一致。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:                                           # noqa: BLE001
        import traceback
        traceback.print_exc()
        sys.exit(3)
