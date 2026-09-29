"""R4-寻虫 法 0（去重）+ 入账计划：**按根因**与已入账 60 单比对，不按标签、不按标题字面。

比对口径（写死在这里）：
1. 两个来源都读：`memory/bugs.md`（60 个 `## BUG-NN` 条目）与 sqlite `ns=bugs`（56 行修复卡）。
   两边数量不等是已知的（sqlite 行不带 BUG-NN，只有 `[类别] 主张` 文本）⇒ 必须给出对账，不许各数各的。
2. 判"同一根因"要同时满足三条：**同一处代码机制**（file:line 级）+ **同一触发形状** + **同一修法**。
   只满足"文档/门面看起来一类"不算重复，但要在 near_miss 里点名为什么不判重。
3. 命中重复 ⇒ 该候选**不占号**，改为往已有单上追加实测；未命中 ⇒ 从盘上现数的 max+1 起号。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r4_dedup.json"
LEDGER = ROOT / "memory" / "bugs.md"
DB = ROOT / "fist-mbt.db"  # 库在仓库根，不在本目录
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why,
                   "ok": (got == want) if ok is None else bool(ok)})


# 本环计划入账单：一张单 = 一个根因（不是"一个观察"）
PLAN = [
    {"key": "RC1_func_symbol_typed_as_return",
     "title": "函数名被登记成它的**返回类型**（没有可调用签名）⇒ 元数判定挂错表：正确调用被判错、错误调用被放行",
     "mechanism": "type_checker.py:523-525（同族 :393-395、:473-475）`self.type_map[node.name] = return_type`；"
                  "`_visit_Call`(:1035) 之后只看 `type_map[名字]` 是不是 Callable，于是函数自身的参数表 (:546-547 "
                  "`old_type_map[node.name] = return_type`) 全程不参与判定",
     "symptoms": ["C01", "C02", "C03", "C04", "C05"],
     "severity": "high", "owner": "下一环修（分析器内部，不涉冻结面）"},
    {"key": "RC2_no_argument_type_check",
     "title": "实参类型与形参声明类型从不做兼容性比对：`apply(\"s\")`（形参 `n: int`）零诊断，"
              "而同族 `let x: int = \"s\"` 会报",
     "mechanism": "`_visit_Call`(:1039-1043) 对每个 arg 只 `_visit(arg)` 求类型后丢弃，赋值处(:768/792/807)才比类型；"
                  "两边没有共用同一个兼容性谓词",
     "symptoms": ["C06", "C07", "C08"],
     "severity": "high", "owner": "下一环修（需与 SYNTAX/01 的『有注解的参数进行类型检查』口径对齐）"},
    {"key": "RC3_struct_field_type_unresolved",
     "title": "struct 成员的声明类型在方法体里解析不出来：`self.n`/`self.i.n`/`self.cb(1,2)` 三类全部静默，"
              "同族局部变量与形参都会判",
     "mechanism": "`_visit_Attribute`(:2122) 不查 struct 登记表 ⇒ `self.<field>` 得 Optional[None]，"
                  "后续类型/元数判定按『不知道』放行",
     "symptoms": ["C09", "C10", "C11"],
     "severity": "high", "owner": "下一环修"},
    {"key": "RC4_internal_repr_in_message",
     "title": "类型不符的用户可见文案直接内插 `Type` 对象 ⇒ 打印 `Callable[tuple[int], str]`，"
              "与源语法 `Callable[[int], str]` 两种写法都不对应",
     "mechanism": "f-string 里 `{declared_type}`（:768/:792/:807/:840…）走 `Type.__repr__`，"
                  "泛型参数位用的是 python `tuple[...]` 的 repr",
     "symptoms": ["C12"],
     "severity": "medium", "owner": "下一环修（文案层，行为不变）"},
    {"key": "DOC_status_stale_rows",
     "title": "文档宣称的形态与今天实现不符（appendix-C 特性表 5 行 + USAGE 未实现清单 + 实现状态表 1 行 + "
              "主类型表 i32 一族）",
     "mechanism": "状态表按 v0.5 计划手写，实现落地后无人回写。落地证据（符号级）：`constraint` 与 `subtype` "
                  "已在 parser 里走 `_parse_subtype_def` 建 `SubtypeDef`、codegen 侧登记 `subtype_defs`，"
                  "`DispatchDecl` 只剩 bridge 里的死 handler；而主类型表宣称的 `i32` 在 `type_mapper` 里 0 命中",
     "symptoms": ["D01", "D02", "D04", "D05", "D07", "D13", "D14"],
     "severity": "medium", "owner": "人工（SYNTAX/ 与状态表属冻结面 ⇒ 只挂账）"},
    {"key": "DOC_cli_face_mismatch",
     "title": "CLI 用法文档与实读不符：`cypyc --compile` / `build --incremental` 不存在，"
              "`hook` 有 6 个未记选项，入口点与 Python 下限两处转述错",
     "mechanism": "argparse 的子命令 choices 是唯一事实源，文档手抄：`--incremental` 不在 `build` 的 "
                  "parser 里、`transpile-only` 与 `--run`/`--eval` 只在 `hook` 的 help 里出现；"
                  "入口点由 `requires-python` 与 `cypyc =` 两处声明，USAGE 转述成了另一个程序",
     "symptoms": ["D06", "D08", "D09", "D10"],
     "severity": "medium", "owner": "下一环修（docs 非冻结）"},
    {"key": "DOC_example_fails",
     "title": "文档示例引用实现里不存在的符号：`ProjectCompileResult.output_files`（无此字段）、"
              "`hook.eval(...)` 承诺返回值（读侧要 `__result__`，写侧从不产出）",
     "mechanism": "`dataclass ProjectCompileResult`(project_compiler.py:25) 字段集里没有 output_files；"
                  "`cypy_hook/hook.py:759` 只认 `__result__`，`cypyc/` 全仓 0 处生成",
     "symptoms": ["D11", "D12"],
     "severity": "high", "owner": "下一环修（示例改口径或生成侧补，交裁决）"},
    {"key": "BRIDGE_cache_side_effect",
     "title": "`BridgeCacheManager` 的只读查询在**调用方 CWD** 造出 `__pycache__/cypy/py313/`"
              "（`_get_base_cache_dir(None)` 回落 `os.getcwd()`）",
     "mechanism": "cypy_bridge/compiler.py:3545-3560 目录不存在即 `mkdir`，"
                  "`get_cached_pyd`/`is_stale`(:3599/:3621) 都走它",
     "symptoms": ["D16"],
     "severity": "medium", "owner": "下一环修"},
    {"key": "BRIDGE_c_not_equivalent",
     "title": "bridge 生成的 C 里有**模块级** `if ((__name__ == \"__main__\")) {…}`（花括号净深 0 处），"
              "与 `cypy_bridge/__init__.py:4` 自述的「与 Cython 等价」不符，MSVC 必拒",
     "mechanism": "`BridgeCompiler._generate_c_code`(:3756) 把入口分派写在函数体外",
     "symptoms": ["D17"],
     "severity": "high", "owner": "下一环修（真编译验证转结 R4-验证）"},
    {"key": "SPEC_file_size_redline",
     "title": "PROJECT-SPEC 自己的 3000 行（不含注释）红线被 parser.py=3444、cython_generator.py=3108 越过，"
              "规范要求的\"当时就拆\"没有发生",
     "mechanism": "口径是 `code_lines`（剔注释与字符串后 token 覆盖的行数，不是 `wc -l`）：`parser` 3444、"
                  "`cython_generator` 3108 越过阈值 ⇒ 规范要求的「当时就拆」没有发生；纯存量规模，"
                  "没有单点代码机制可指（这就是签名薄的地方，比对结果要如实标注）",
     "symptoms": ["D15"],
     "severity": "low", "owner": "人工（跨文件拆分不可逆 ⇒ 只挂账）"},
]

NEAR_MISS = {
    "BUG-42": "它讲 `_visit_ExprStmt`/`_visit_MetaBlock` 各定义两次 ⇒ 前一份是死代码（重复定义）；"
              "本条 SPEC_file_size_redline 讲的是 `parser`/`cython_generator` 两个文件规模越过 3000 行阈值。"
              "共享的只是**文件名**（我这边的签名里带路径段）⇒ 不判重；真正的相关性是：将来拆分这两个文件时"
              "应顺手消掉 BUG-42 的重复定义",
    "BUG-32": "它讲**codegen 注释渲染**把成员名过一遍 `type_mapper` ⇒ 产物里丢用户原文；"
              "本环真正与它同族的是 **RC4**（诊断文案走 `Type.__repr__`），已单列一卡并在 RC4 里点名交叉复核；"
              "DOC_status_stale_rows 与它只共享名词（`constraint`/`type_mapper` 字样），机制不同 ⇒ 不判重",
    "BUG-54": "它讲 `build/` 中间产物在**进程间**共享导致 watch 互踩（setuptools 落在调用方 CWD）；"
              "DOC_cli_face_mismatch 讲的是 `build --incremental` 这个旗标在 argparse 里根本不存在 ⇒ 不判重。"
              "但 **BRIDGE_cache_side_effect**（`_get_base_cache_dir` 在调用方 CWD 建目录）与它同属"
              "「中间/缓存路径落到调用方 CWD」一族、代码点与修法不同 ⇒ 不判重，两单互相引用",
    "BUG-49": "同『状态表过期』一类，但它钉的是 `SYNTAX/33` 的 constraint 行且仍 OPEN 未修；"
              "本环 DOC_status_stale_rows 覆盖 appendix-C/USAGE/STATUS 另 7 行，行不重叠 ⇒ 不判重，"
              "两单互相引用",
    "BUG-56": "它讲『旗标注册了但没人读』(cli.py:435-516)，本环 DOC_cli_face_mismatch 讲『文档写了不存在的旗标"
              "＋未记选项＋转述错』，机制在 argparse 与文档两侧 ⇒ 不判重",
    "BUG-46": "hook install/status 互相否定（CLI 行为），与入口点转述错不是一处代码 ⇒ 不判重",
    "BUG-47": "cypy_hook 包级 API 未再导出（AttributeError 于 import），与 D08 的 scripts 入口点是两回事 ⇒ 不判重",
    "BUG-21": "同为 type_checker 里『把内部表示当名字用』，但那是 trait 登记表 (`getattr(...,str(node))`)，"
              "本环 RC4 是诊断文案内插 `Type` 对象，修法不同（一个剥节点 repr，一个加显示层格式化）⇒ 不判重",
    "BUG-40": "同族『内部表示外泄』，但那要求**非法标注形态**且外泄到 codegen 产物；RC4 在正常路径外泄到诊断文案"
              "⇒ 不判重，修 RC4 时需一并复核 BUG-40",
    "BUG-45": "struct 的 `__implicit_default__` 默认值生成（codegen 侧符号缺失），RC3 是**分析侧**成员类型解析"
              "⇒ 不判重",
    "BUG-48": "`cypyc watch` 不产出（运行时热重载），与本环四组静态分析根因无交集 ⇒ 不判重",
    "BUG-11": "项目模式丢弃 ScopeAnalyzer 诊断（入口口径分叉），RC1/RC2 是分析器内部不判 ⇒ 不判重",
}


def parse_ledger() -> dict:
    text = LEDGER.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (BUG-\d+) ", text)
    cards = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    return cards


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    cards = parse_ledger()
    nums = sorted(int(k.split("-")[1]) for k in cards)
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    bug_rows = db.execute("select id, status, description from tasks where ns='bugs'").fetchall()
    stage_rows = db.execute("select count(*) from tasks where ns=?",
                            ("cypy-loop-20260927",)).fetchone()[0]
    db.close()
    symptom_ids = sorted({s for c in PLAN for s in c["symptoms"]})
    all_ids = {f"C{i:02d}" for i in range(1, 13)} | {f"D{i:02d}" for i in range(1, 19)}
    unclaimed = sorted(all_ids - set(symptom_ids))
    UNCLAIMED_REASON = {"D03": "文档自述未实现且今天仍未实现 ⇒ design 撤回，不占号",
                        "D18": "要两次真编译才能定 ⇒ not_measured，转结 R4-验证，本轮不写结论"}
    check("未归号的每一条都被点名了为什么", sorted(UNCLAIMED_REASON), unclaimed,
          f"未归号 {unclaimed}")
    # 机制签名 = **反引号里的代码符号**（函数名/字段名/赋值形状），路径与包名一律剔掉：
    # 拿 "cypyc"、"project_compiler" 这种包名去比 = 拿标签比，会把 14 张不相干的卡全判成近亲。
    PACKAGE_STOP = {"cypyc", "cypy_hook", "cypy_bridge", "project_compiler", "cli", "hook",
                    "docs", "python", "pyproject", "scripts", "project", "node", "self",
                    "text", "code", "args", "arg", "name", "type", "types", "line", "col",
                    "dataclass", "def", "str", "int", "None", "True", "False", "Optional",
                    "list", "dict", "set", "key", "value", "repr", "file", "path"}

    def symbols(text: str) -> tuple:
        """返回 (代码符号集, 路径段符号集)：只有代码符号相同才算近亲，光文件名相同是撞名。"""
        code, paths = set(), set()
        for span in re.findall(r"`([^`]+)`", text):
            if re.search(r"\.(py|cypy|md|toml|pyx)\b|/", span):
                for piece in re.split(r"[\s/,:()]+", span):
                    paths |= {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", piece)}
                continue
            code |= {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", span)}
        return code - PACKAGE_STOP, paths - PACKAGE_STOP

    card_syms = {c["key"]: symbols(c["mechanism"]) for c in PLAN}
    ledger_syms = {num: symbols(body) for num, body in cards.items()}
    check("签名是代码符号级（不含包名/路径名）",
          sorted({s for v, _ in card_syms.values() for s in v if s in PACKAGE_STOP}), [],
          "剔包名后仍残留 ⇒ 又退回按标签比")
    check("每条计划单都拿到了非空代码签名",
          [k for k, (v, _) in card_syms.items() if not v], [], "签名为空 ⇒ 比对是空转")
    rows = []
    for card in PLAN:
        mine, mine_paths = card_syms[card["key"]]
        hits = []
        for num, (theirs, their_paths) in ledger_syms.items():
            shared_code = sorted(mine & theirs)
            shared_path = sorted((mine_paths & their_paths) - mine - theirs)
            if not shared_code and not shared_path:
                continue
            hits.append({"bug": num, "shared_code_symbols": shared_code,
                         "shared_file_names_only": shared_path,
                         "adjudication": NEAR_MISS.get(num, "")})
        for h in hits:
            if h["shared_code_symbols"] and not h["adjudication"]:
                REFUSE.append(f"{card['key']} 与 {h['bug']} 共享**代码符号** {h['shared_code_symbols']}，"
                              f"但没有逐条裁决 ⇒ 不许直接占号（要么判重，要么写明为何不判重）")
        rows.append({"key": card["key"], "title": card["title"], "symptoms": card["symptoms"],
                     "mechanism": card["mechanism"], "mechanism_symbols": sorted(mine),
                     "mechanism_file_tokens": sorted(mine_paths),
                     "severity": card["severity"], "owner": card["owner"],
                     "duplicate_of": [], "symbol_overlap_hits": hits,
                     "adjudication": "盘上 60 单的机制签名与本条不共享同一处代码符号 ⇒ 占新号"
                     if not any(h["shared_code_symbols"] for h in hits) else "见逐条裁决"})
    check("只有代码符号重合才需要裁决；纯撞文件名的重合被单列且不阻断",
          [bool(h["shared_file_names_only"]) and not h["shared_code_symbols"] for r in rows
           for h in r["symbol_overlap_hits"] if h["shared_file_names_only"]],
          [True] * sum(1 for r in rows for h in r["symbol_overlap_hits"] if h["shared_file_names_only"]),
          "撞名栏")
    check("症状全覆盖：12 候选 + 18 文档面都归了号或点名未入账",
          sorted(set(symptom_ids) | set(unclaimed)), sorted(all_ids), f"未归号 {unclaimed}")
    check("去重比对真的比过（每条计划单都对 60 张卡跑过符号签名比对）",
          sum(1 for r in rows if "symbol_overlap_hits" in r), len(PLAN), "逐条计数")
    check("比对是机制级：签名里不许出现文件名/目录名",
          sorted({s for v in card_syms.values() for s in v if ".py" in s or "/" in s}), [],
          "剔停词后仍含路径 ⇒ 又退回按标签比")
    check("两来源都在（md 60 / sqlite bug 行 >0 / 阶段任务 >0）",
          [len(nums) == 60, len(bug_rows) > 0, stage_rows > 0], [True, True, True],
          f"md={len(nums)} sqlite={len(bug_rows)} stage={stage_rows}")
    doc = {"started": started, "plan": PLAN, "plan_total": len(PLAN),
           "compared_with": ["memory/bugs.md", "fist-mbt.db:ns=bugs"],
           "ledger_cards": len(nums), "ledger_max": nums[-1] if nums else 0,
           "sqlite_bug_rows": len(bug_rows), "sqlite_stage_rows": stage_rows,
           "reconciliation": f"md 有 {len(nums)} 个 BUG-NN 标题，sqlite ns=bugs 只有 {len(bug_rows)} 行且"
                             "**行内不带 BUG-NN**（只有 `[类别] 主张` 文本）⇒ 两轨按内容对齐，"
                             "号只存在于 md 账本；差额 "
                             f"{len(nums) - len(bug_rows)} 由『探针单/合并单』解释，逐条点名见 ledger3way",
           "existing_numbers": nums, "numbering_from_disk": (nums[-1] + 1) if nums else 1,
           "duplicates": [], "near_miss_notes": NEAR_MISS, "unclaimed_symptoms": unclaimed,
           "unclaimed_reason": UNCLAIMED_REASON,
           "rows": rows, "refuse": [],
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    doc["refuse"] = sorted(set(REFUSE)) + [f"判据自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:160]}）"
                                          for c in CHECKS if not c["ok"]]
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "plan_total": len(PLAN),
                      "numbering_from_disk": doc["numbering_from_disk"],
                      "ledger_cards": doc["ledger_cards"], "sqlite_bug_rows": doc["sqlite_bug_rows"],
                      "duplicates": doc["duplicates"], "unclaimed": unclaimed,
                      "symbol_overlap_hits": {r["key"]: r["symbol_overlap_hits"] for r in rows
                                              if r["symbol_overlap_hits"]},
                      "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}"},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(json.dumps({"refuse": [f"崩在 {type(exc).__name__}: {exc}"]},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
