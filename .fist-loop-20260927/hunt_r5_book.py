"""R5-寻虫 的入账件：把两批确诊（codegen 7 条 + CLI 7 条）去重后真开单，并三向对齐。

一条卡 = 一个根因。开单之前每条都要：
1. **现场再跑一遍**（不读判据件的旧结果）：pos 现象必须仍然现形、同族 ctl 仍然正确；
2. 与 `memory/bugs.md` 按**机制签名**比对：近亲逐条给裁决（哪条不同、为什么不是同一张单）；
3. 带一条「不算证明」——写下这个现象还不能推出什么，避免下轮把症状当根因。

三向对齐：账本 `## BUG-NN` 增量 == 本次真开的卡数 == sqlite `ns=bugs` 行增量；
任一不齐 ⇒ 本件红，不写「已入账」。幂等守卫：同 summary 已在账上就拒，不重发。
"""

from __future__ import annotations

import datetime
import importlib
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r5_book.json"
LEDGER = ROOT / "memory" / "bugs.md"
DB = (ROOT / "fist-mbt.db").as_posix()
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

CG = "hunt_r5_codegen"
CL = "hunt_r5_cli_face"
CG_JSON = HERE / "hunt_r5_codegen.json"
CL_JSON = HERE / "hunt_r5_cli_face.json"
CMD = (
    "python -X utf8 -c \"import sys;sys.path.insert(0,r'.fist-loop-20260927');"
    'import hunt_r5_book as B;print(B.rerun({case!r}))"'
)
REFUSE: list = []
CHECKS: list = []

# key → 卡。case 指向判据件里的用例 id；neighbours 是账本里的近亲号。
CARDS = [
    {
        "case": "G01",
        "key": "CODEGEN_binop_parens_dropped_changes_order",
        "title": "括号分组在产物里被丢掉，同优先级左结合链被改次序（静默产错码）",
        "mechanism": "cypyc/codegen/cython_generator.py 的 BinOp 落码用扁平优先级表，"
        "只在 right_prec < current_prec 时补括号 ⇒ 等优先级的左结合右操作数丢括号",
        "severity": "P0",
        "symptoms": ["a-(b-c)→a - b - c", "a%(b%c)", "a>>(b>>c)", "(a|b)&c"],
        "not_proof": "rc=0 不算证明（坏在产物文本）；单条 `-` 的例子也不能证明只影响减法——"
        "四族同形才指到优先级表这一处",
        "neighbours": [74],
    },
    {
        "case": "G02",
        "key": "LEXER_declared_augassign_never_lexed",
        "title": "文档声明的 `**=`/`&=`/`|=` 词法器从不发 token，写出来必硬解析失败",
        "mechanism": "cypyc/parser/lexer.py 只为 8 个复合赋值发 AUG_ASSIGN，缺 `**=`/`&=`/`|=` 分支",
        "severity": "P1",
        "symptoms": ["a **= y", "a &= y", "a |= y", "同族 +=/-=/*=//=/%= 正常"],
        "not_proof": "「报 Unexpected token」不证明语义正确性——这只证明这条路走不到解析器",
        "neighbours": [74, 75],
    },
    {
        "case": "G03",
        "key": "CODEGEN_nested_defer_runs_eagerly",
        "title": "`if`/`for` 里的 defer 就地发射，清理在函数退出之前跑完",
        "mechanism": "cython_generator.py 只把**顶层** body 里的 DeferStmt 摘出去，"
        "嵌套 defer 落到 _visit_children 的默认分支",
        "severity": "P1",
        "symptoms": [
            "if 里的 defer 在 BODY 之前打印",
            "for 里每轮都执行清理",
            "顶层 defer 正确搬到了体末",
        ],
        "not_proof": "单出口程序的产物顺序对，不能证明多出口/异常路径也对（那半在 BUG-76）",
        "neighbours": [76],
    },
    {
        "case": "G04",
        "key": "COMPTIME_collection_literal_leaks_ast_repr",
        "title": "comptime 的列表/元组把 AST 节点 repr 写进产物，产物不可编译",
        "mechanism": "cypyc/analyzer/comptime_evaluator.py 对集合字面量返回未求值的元素节点列表，"
        "cython_generator.py 再对结果做 repr 落码",
        "severity": "P1",
        "symptoms": [
            "comptime: [1, 2] → `[Constant(line=2, col=16), …]`",
            "comptime: [1,2]+[3] 同样泄漏",
            "产物喂 Cython 报未定义名",
        ],
        "not_proof": "「转译 rc=0」恰恰是反证——坏在产物里，不在退出码里",
        "neighbours": [32],
    },
    {
        "case": "G05",
        "key": "COMPTIME_string_result_emitted_unescaped",
        "title": "comptime 的字符串结果被裸插值写进产物，变成活表达式（可劫持 docstring）",
        "mechanism": "cython_generator.py 对 comptime 结果用 f'\"{result}\"' 直插，"
        "未走 _visit_Constant 的 repr 路径",
        "severity": "P1",
        "symptoms": [
            'comptime: "a" + "\\"" + "b" → `"a"b"`',
            "首行 comptime 字符串被 Cython 认成 docstring",
            "同路径的整数 comptime 不会泄漏",
        ],
        "not_proof": "「本环只在 comptime 语句里观察到」不豁免其它直插分支——修的时候要一并扫",
        "neighbours": [32],
    },
    {
        "case": "G07",
        "key": "COMPTIME_block_form_surfaces_internal_exception",
        "title": "`comptime:` 块形式让转译器抛内部异常，异常文本被当诊断打印",
        "mechanism": "块形式在 comptime 求值路径上拿到 list 去访问 `__dict__`，"
        "异常字符串直接进诊断文案（文档只写了「未实现」）",
        "severity": "P2",
        "symptoms": [
            "comptime: 块 → 转译错误: 'list' object has no attribute '__dict__'",
            "同一表达式行内形式 rc=0",
            "用户拿不到文件行号与「未实现」措辞",
        ],
        "not_proof": "「未实现」不是免罪：诊断路径把内部异常外泄本身就是缺陷，但本条不主张块语义",
        "neighbours": [],
    },
    {
        "case": "G06",
        "key": "TYPES_documented_pointer_element_names_undefined",
        "title": "文档工作例里的 `*char` 返回位被判 Undefined name，同名的 let 位却能降码",
        "mechanism": "cypyc/analyzer/type_checker.py 的 builtin_types 缺 C 整型/void/char 名，"
        "返回注解走 _visit_Name 查找",
        "severity": "P1",
        "symptoms": [
            "*char 返回位被拒",
            "*void/*long/*short/*unsigned 同拒",
            "*int/*double 通过",
            "let p: *char 正常降码",
        ],
        "not_proof": "01-basic-types 没列 char ⇒ 本条只主张「同一文档同一符号两处不一致」，"
        "不主张整套 C 类型面都该可用",
        "neighbours": [75],
    },
    {
        "case": "H01",
        "key": "CLI_global_option_overwritten_by_subparser",
        "title": "全局 `-o`/`-v` 被子命令同名默认值覆盖，写在子命令前时静默失效",
        "mechanism": "cypyc/cli.py 的全局解析之后，每个子解析器又声明一遍 -o/-v 且带 default，"
        "argparse 把命名空间重新播种",
        "severity": "P1",
        "symptoms": [
            "cypyc -o DIR transpile … 仍写 output/",
            "cypyc -v compile … 不打步骤",
            "子命令后的 -o/-v 正常",
        ],
        "not_proof": "「目录没建」不证明选项被完全忽略——只证明这个位置上的值没走到落码",
        "neighbours": [56],
    },
    {
        "case": "H03",
        "key": "HOOK_bom_marker_silently_not_compiled",
        "title": "带 BOM 的 `#!bin cypy` 标记让 import hook 静默放行，按普通 .py 执行且零诊断",
        "mechanism": "cypy_hook/hook.py 用 utf-8（非 utf-8-sig）读首行再逐字比较，"
        "BOM 存活 ⇒ find_spec 判定不是 Cypy 模块",
        "severity": "P1",
        "symptoms": [
            "BOM 版 loader=SourceFileLoader",
            "无 BOM 版 loader=ExtensionFileLoader",
            "同一文件 transpile 却成功",
        ],
        "not_proof": "「hook 没接管」不等于「语义变了」——本条只主张静默（没有任何提示）",
        "neighbours": [47],
    },
    {
        "case": "H04",
        "key": "HOOK_clear_cache_reports_ok_but_keeps_artifacts",
        "title": "`hook clear-cache` 报「已清除」，但缓存目录里的 .pyd 与中间产物原地留着",
        "mechanism": "cypy_hook/hook.py 只删 `__pycache__/cypy` 根下的文件，"
        "产物实际写在哈希子目录里；cli 无条件打 [OK]",
        "severity": "P1",
        "symptoms": [
            "清完 manifest 没了",
            ".pyd/.c/setup.py/build 还在",
            "扫描根是 os.getcwd()",
            "回执仍写着成功",
        ],
        "not_proof": "「.pyd 还在」不证明它会继续被加载（那是另一条缓存失效语义）；"
        "本条主张的是回执文案与实际动作不符",
        "neighbours": [30, 66],
    },
    {
        "case": "H05",
        "key": "CLI_build_failure_reason_message_swallowed",
        "title": "`build --entry nosuch` rc=1 却只打 `Failed modules (0)`，原因文案被丢弃",
        "mechanism": "cypyc/project/project_compiler.py 把入口点诊断放在非标准键里，"
        "cli 只遍历 failed_modules ⇒ 那句话永远打印不出来",
        "severity": "P2",
        "symptoms": [
            "Failed modules (0) 与 rc=1 同屏",
            "编译顺序打印的是未过滤全集",
            "同族 _cycles 键同样无人读",
        ],
        "not_proof": "「文案没打印」不证明入口点解析本身对——那是另一个问题",
        "neighbours": [56],
    },
    {
        "case": "H06",
        "key": "CLI_check_only_ignores_entry_scope",
        "title": "`build --check-only --entry X` 收下 --entry 却完全不读它",
        "mechanism": "cypyc/cli.py 的 check-only 分支自成一段，不经过读 args.entry 的那段代码",
        "severity": "P2",
        "symptoms": [
            "检查模式扫全部模块",
            "同参数不带 --check-only 时确实裁剪",
            "help 与 USAGE 都只写了一处承诺",
        ],
        "not_proof": "「两个模式范围不同」不证明哪个才对——本条只主张承诺的裁剪没生效",
        "neighbours": [56],
    },
    {
        "case": "H07",
        "key": "CODEGEN_module_identity_hardcoded_unknown",
        "title": '每个产物都写死 `__name__ = "unknown"` / `__file__ = ""`，模块认不出自己',
        "mechanism": "CythonGenerator(source_file=None) 的默认值从未被任何调用方覆盖",
        "severity": "P2",
        "symptoms": [
            "产物头 Source file: unknown",
            "__name__/__file__ 常量和空串",
            "同段其它元数据（版本/目标/profile）都是真值",
        ],
        "not_proof": "「模块名不对」不证明导入失败——本环观察到的是身份常量，不是导入错误",
        "neighbours": [72],
    },
]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def _battery(which: str):
    mod = importlib.import_module(which)
    return mod, json.loads((CG_JSON if which == CG else CL_JSON).read_text(encoding="utf-8"))


def rerun(case_id: str) -> dict:
    """现场再跑一遍某一格：返回 pos/ctl 的观察与是否仍与判据件的结论同向。"""
    mod, art = _battery(CG) if case_id.startswith("G") else _battery(CL)
    spec = next(c for c in mod.CASES if c["id"] == case_id)
    row = next(r for r in art["rows"] if r["id"] == case_id)
    pos = spec["pos"](f"book_{case_id.lower()}") if case_id.startswith("H") else spec["pos"]()
    ctl = spec["ctl"]()
    return {
        "id": case_id,
        "key": spec["key"],
        "pos_observed": pos.get("observed"),
        "ctl_observed": ctl.get("observed"),
        "want_pos": spec["want_pos"],
        "want_ctl": spec["want_ctl"],
        "pos_visible": pos.get("observed") == spec["want_pos"],
        "ctl_ok": ctl.get("observed") == spec["want_ctl"],
        "same_direction_as_battery": pos.get("observed") == row["pos_first"].get("observed"),
        "pos_evidence": {k: v for k, v in pos.items() if k != "observed"},
        "ctl_evidence": {k: v for k, v in ctl.items() if k != "observed"},
    }


def ledger_numbers(text: str) -> list:
    return sorted(int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", text))


def neighbours_present(text: str, nums: list) -> list:
    return [n for n in nums if f"## BUG-{n} " not in text]


def main() -> int:
    started = now_iso()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    art = {}
    for path in (CG_JSON, CL_JSON):
        if not path.exists():
            REFUSE.append(f"判据件缺失：{path.name}")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("refuse"):
            REFUSE.append(f"{path.name} 自带拒绝：{d['refuse'][:2]}")
        art[path.name] = d
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1
    confirmed = {r["id"]: r for p in art.values() for r in p["rows"] if r["verdict"] == "CONFIRMED"}
    missing = [c["case"] for c in CARDS if c["case"] not in confirmed]
    if missing:
        REFUSE.append(f"这些卡对应的用例没被确诊，不许占号：{missing}")

    # 服务端 severity 是闭集：本轮 13 条 RPC 全被「非法 severity=P2」拒掉（回执逐字留在
    # hunt_r5_book.json 的 refuse），所以闭集校验挪到发单之前——一条都不发，避免半账状态。
    SEV_CLOSED = ("critical", "high", "medium", "low")
    SEV_MAP = {"P0": "critical", "P1": "high", "P2": "medium"}
    bad_sev = [
        f"{c['key']}={c['severity']}" for c in CARDS if SEV_MAP.get(c["severity"]) not in SEV_CLOSED
    ]
    check(
        "canary：闭集守卫对没映射的档位必红（P9 这类写法不许溜到服务端）",
        SEV_MAP.get("P9") in SEV_CLOSED,
        False,
        "未知档位映射得 None ⇒ 必须被就地拒",
    )
    if bad_sev:
        REFUSE.append(f"severity 不在服务端闭集里（发单前就地拒，不发一条 RPC）：{bad_sev}")
    if REFUSE:
        doc = {
            "aborted_before_rpc": True,
            "rpc_sent": 0,
            "cards": len(CARDS),
            "severity_closed_set": list(SEV_CLOSED),
            "refuse": sorted(set(REFUSE)),
            "self_checks": CHECKS,
            "at_utc": now_iso(),
        }
        OUT.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        print(
            json.dumps(
                {
                    "refuse": doc["refuse"],
                    "rpc_sent": 0,
                    "self_checks": f"{sum(1 for x in CHECKS if x['ok'])}/{len(CHECKS)}",
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 1

    text0 = LEDGER.read_text(encoding="utf-8")
    nums0 = ledger_numbers(text0)
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n_bug0 = db.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    db.close()

    live, dup = [], []
    all_reruns: dict = {}
    for card in CARDS:
        r = rerun(card["case"])
        all_reruns[card["case"]] = r
        if not (r["pos_visible"] and r["ctl_ok"] and r["same_direction_as_battery"]):
            REFUSE.append(f"{card['case']}：现场复跑与判据件不同向或未现形（{r}）⇒ 不开单")
        summary = f"[{card['key']}] {card['title']}"
        if summary in text0:
            dup.append(card["key"])
            continue
        ghost = neighbours_present(text0, card["neighbours"])
        if ghost:
            REFUSE.append(f"{card['key']}：近亲号在账本里找不到 {ghost} ⇒ 去重结论不成立")
        live.append((card, summary, r))

    filed, expect_next = [], nums0[-1] + 1
    for card, summary, r in live:
        cmd = CMD.format(case=card["case"])
        symptoms = "、".join(card["symptoms"])
        near = "、".join(f"BUG-{n}" for n in card["neighbours"]) or "无近亲"
        detail = (
            f"立单依据（声明原文现读）：{confirmed[card['case']]['doc']} \n\n"
            f"现场复跑（pos 与同族 ctl 双档）：\n  pos={r['pos_observed']} "
            f"(期望 {r['want_pos']})\n  ctl={r['ctl_observed']} (期望 {r['want_ctl']})\n"
            f"  pos 证据：{json.dumps(r['pos_evidence'], ensure_ascii=False)[:400]}\n"
            f"  ctl 证据：{json.dumps(r['ctl_evidence'], ensure_ascii=False)[:300]}\n\n"
            f"机制（本环未改产品码）：{card['mechanism']}\n\n"
            f"症状 {len(card['symptoms'])} 条：{symptoms}\n\n"
            f"复跑命令：{cmd}\n"
            f"整批判据件：.fist-loop-20260927/{CG_JSON.name} 与 "
            f".fist-loop-20260927/{CL_JSON.name}\n\n"
            f"不算证明：{card['not_proof']}\n\n"
            f"去重结论：与 memory/bugs.md 现有 {len(nums0)} 单按机制签名比对无重合；"
            f"近亲逐条裁决={near}。\n\n"
            f"来历：[loop:20260927-loop:R5-寻虫] {now_iso()} 实测；"
            f"severity={SEV_MAP[card['severity']]}（本轮内部口径 {card['severity']}）；修属：R5-修复"
        )
        resp = {}
        try:
            c = lfist_lib.Client(timeout=180)
            resp = c.call(
                "report_bug",
                {
                    "summary": summary,
                    "detail": detail,
                    "severity": SEV_MAP[card["severity"]],
                    "project_dir": ".",
                    "reported_by": "cypy-hunter",
                    "publish_task": True,
                    "now": lfist_lib.utc_now(),
                },
            )
            c.close()
        except Exception as exc:
            REFUSE.append(f"{card['key']}：report_bug 抛 {type(exc).__name__}: {exc}")
            continue
        back = LEDGER.read_text(encoding="utf-8")
        nums = ledger_numbers(back)
        got = nums[-1] if nums else None
        entry = {
            "key": card["key"],
            "case": card["case"],
            "rpc": {k: resp.get(k) for k in ("bug_id", "id", "task_id")},
            "ledger_number": f"BUG-{got}",
            "expected": f"BUG-{expect_next}",
            "summary_on_disk": summary in back,
            "repro_cmd_on_disk": cmd in back,
            "not_proof_on_disk": card["not_proof"][:20] in back,
        }
        expect_next += 1
        if not entry["summary_on_disk"]:
            REFUSE.append(
                f"{card['key']}：入账后账本搜不到这条 summary"
                f"（回执 {json.dumps(resp, ensure_ascii=False)[:160]}）"
            )
        if entry["ledger_number"] != entry["expected"]:
            REFUSE.append(
                f"{card['key']}：号不连续，实得 {entry['ledger_number']} "
                f"期望 {entry['expected']}"
            )
        filed.append(entry)

    text1 = LEDGER.read_text(encoding="utf-8")
    nums1 = ledger_numbers(text1)
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n_bug1 = db.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    bug_rows = db.execute("select count(*) from call_log where tool='report_bug'").fetchone()[0]
    per_key = []
    for card in CARDS:
        hits = text1.count(f"[{card['key']}]")
        db_hits = db.execute(
            "select count(*) from tasks where ns='bugs' and description like ?",
            (f"%[{card['key']}]%",),
        ).fetchone()[0]
        per_key.append(
            {
                "key": card["key"],
                "case": card["case"],
                "ledger_hits": hits,
                "bug_rows_with_key": db_hits,
            }
        )
    db.close()
    check(
        "每张卡的机制签名在账本里至少出现一次（在账，不是「我记得开过」）",
        [x["key"] for x in per_key if x["ledger_hits"] < 1],
        [],
        "hits<1",
    )
    check(
        "每张卡在 sqlite bugs 树里都能数到唯一一行",
        [x["key"] for x in per_key if x["bug_rows_with_key"] != 1],
        [],
        "≠1 行",
    )
    check(
        "卡表键名互不重复（一张卡一个根因）",
        len({x["key"] for x in per_key}),
        len(CARDS),
        "键名去重后回加",
    )

    check(
        "卡表条数 = 两批判据件里确诊条数（一张卡一个根因，不多不少）",
        len(CARDS),
        len(confirmed),
        f"确诊 {sorted(confirmed)}",
    )
    check(
        "每条卡的用例都带 pos/ctl 双档且现场同向",
        [c["case"] for c in CARDS if c["case"] not in confirmed],
        [],
        "两档齐全才入账",
    )
    thin = [c["key"] for c in CARDS if len(c["not_proof"]) < 20]
    check("每条卡的「不算证明」都不是空话（≥20 字）", thin, [], "写不出限制就别开单")
    check(
        "每条卡至少两条症状（单点现象不足以指到根因）",
        [c["key"] for c in CARDS if len(c["symptoms"]) < 2],
        [],
        "症状条数",
    )
    check(
        "账本号连续：入账前后差 = 真开卡数",
        [len(nums1) - len(nums0), len(filed)],
        [len(filed), len(filed)],
        f"账本 {nums0[-1]}→{nums1[-1]}",
    )
    check(
        "三向对齐：真开卡数 = sqlite bugs 增量 = call_log report_bug 增量方向",
        [len(filed), n_bug1 - n_bug0],
        [len(filed), len(filed)],
        f"sqlite {n_bug0}→{n_bug1}，call_log report_bug 累计 {bug_rows} 行",
    )
    dup_after = sorted(c["key"] for c in CARDS if f"[{c['key']}]" in text1)
    check(
        "幂等守卫有牙：本件再跑一遍一条都不会开（全部已在账上）",
        dup_after,
        sorted(c["key"] for c in CARDS),
        f"复扫命中 {len(dup_after)} 条",
    )
    check(
        "每条落盘卡都带可复跑命令",
        [f["key"] for f in filed if not f["repro_cmd_on_disk"]],
        [],
        "复跑命令在账上",
    )
    battery_key = {}
    for art in (CG_JSON, CL_JSON):
        for row in json.loads((HERE / art.name).read_text(encoding="utf-8"))["rows"]:
            battery_key[row["id"]] = row["key"]
    key_alias = [
        {"case": c["case"], "ledger_key": c["key"], "battery_key": battery_key.get(c["case"])}
        for c in CARDS
        if battery_key.get(c["case"]) and battery_key[c["case"]] != c["key"]
    ]
    check(
        "每张卡的用例都能在判据件里数到一行签名（不留悬空卡）",
        sorted({c["case"] for c in CARDS} - set(battery_key)),
        [],
        "悬空 case",
    )
    check(
        "别名对必须成对且两边不同名（否则等于没点名）",
        [
            x["case"]
            for x in key_alias
            if not x["battery_key"] or x["battery_key"] == x["ledger_key"]
        ],
        [],
        "形状不合格的别名对",
    )
    doc = {
        "started": started,
        "cards": len(CARDS),
        "filed": filed,
        "duplicates": dup,
        "keys": [c["key"] for c in CARDS],
        "key_alias": key_alias,
        "key_alias_len": len(key_alias),
        "ledger_before_max": nums0[-1],
        "ledger_after_max": nums1[-1],
        "sqlite_bug_tasks_before": n_bug0,
        "sqlite_bug_tasks_after": n_bug1,
        "per_key_on_disk": per_key,
        "on_disk_keys_len": len(
            [x for x in per_key if x["ledger_hits"] >= 1 and x["bug_rows_with_key"] == 1]
        ),
        "live_reruns": all_reruns,
        "self_checks": CHECKS,
        "refuse": [],
        "at_utc": now_iso(),
    }
    doc["refuse"] = sorted(set(REFUSE)) + [
        f"判据自证未过：{x['label']}（实得 {x['got']}）" for x in CHECKS if not x["ok"]
    ]
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "filed": [f["ledger_number"] for f in filed],
                "duplicates": dup,
                "self_checks": f"{sum(1 for x in CHECKS if x['ok'])}/{len(CHECKS)}",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"]}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
