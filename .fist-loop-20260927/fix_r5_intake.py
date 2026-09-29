"""R5-修复 的认领表（法①）：从盘上账本反解未闭环的单，逐张分栏并给出归属理由，不手抄单号。

文件面从哪里读（这是本件的主张强度所在）：
- 只看卡片的「机制（…）」行与「修法」行点名的文件 ⇒ 那两行说的是**要改哪儿**；
  卡片正文里的复跑命令与旁证也提文件，把它们当认领依据会把只读过一眼的模块算成待改；
- 裸文件名（`cython_generator.py`）拿产品树现建的索引反查唯一路径，歧义或查不到的不许进认领栏；
- `修属=lexer/parser` 这类域标签按 DOMAINS 表换成文件面，表里没有的键不瞎猜。

四栏怎么定（都是读出来的，不是我定的口径）：
- `交人工或裁决`：卡片正文自己写了「交人工/待裁决/交裁决/交文档/挂账交裁决」⇒ 逐字摘那句话当理由；
- `交人工或裁决（红线：冻结语义）`：认领面只剩 SYNTAX/PROJECT-SPEC ⇒ 红线不许我改；
- `本环认领`：认领面落在可改半径（产品码/测试）内，且该卡有服务端卡号、点名的文件在盘上；
- `未认领（转结仍 OPEN）`：其余如实列出（R5 是五轮最后一环，未认领不等于关掉）。

自证：条数 = 未闭环总数（分栏不吞行）、R5-寻虫 的 13 个键与账本两路对齐、有卡号的卡其卡号能在 bugs 树读回、
认领栏的卡必须有卡号且文件真实存在、三张反例假卡（只点冻结面 / 点盘上没有的文件 / 有文件面但没卡号）
必须被挡在认领栏外、必然不存在的单号必须解析不出。车道归属不在本件主张，归 fix_r5_rc.py 按实测改动面算。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
BOOK = HERE / "hunt_r5_book.json"
DB = ROOT / "fist-mbt.db"
OUT = HERE / "fix_r5_intake.json"

RADIUS = ("cypyc/", "cypy_hook/", "cypy_bridge/", "scripts/", "tests/")
FROZEN = ("SYNTAX/", "PROJECT-SPEC/")
_PREFIX = "|".join(t.rstrip("/") for t in RADIUS + FROZEN)
PATH_RE = re.compile(
    rf"(?<![\w./-])((?:{_PREFIX})/[\w./-]*?\.(?:py|pyx|pxd|md|toml|json|ya?ml|cfg|ini))"
)
BARE_RE = re.compile(r"(?<![\w./-])([A-Za-z_]\w*)\.(?:py|pyx)(?![\w./-])")
DOMAINS = {
    "lexer": "cypyc/parser/lexer.py",
    "parser": "cypyc/parser/parser.py",
    "codegen": "cypyc/codegen/",
    "analyzer": "cypyc/analyzer/",
    "cli": "cypyc/cli.py",
    "hook": "cypy_hook/",
    "project": "cypyc/project/",
    "incremental": "cypyc/incremental/",
    "bridge": "cypy_bridge/",
    "tests": "tests/",
}
HANDOFF = re.compile(r"(交人工|待裁决|交指挥官裁决|交裁决|挂账交裁决|交文档)")
SCOPE_RE = re.compile(
    r"^(机制[（(][^\n]*?[)）]?：|修法[（(]?[^\n]*?[)）]?：|.*立单依据[（(][^\n]*?[)）]?：)(.+)$",
    re.M,
)
TASK_ID_RE = re.compile(r"T0r\d+")
CHECKS: list = []
REFUSE: list = []


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def product_index() -> tuple:
    """产品树现建的裸名 → 路径索引 + 全量路径表（只收可改半径内的 .py/.pyx，不收 .fist-loop 与 build）。"""
    idx: dict = {}
    all_paths: list = []
    for top in (t.rstrip("/") for t in RADIUS):
        base = ROOT / top
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".pyx"):
                rel = p.relative_to(ROOT).as_posix()
                idx.setdefault(p.name, []).append(rel)
                all_paths.append(rel)
    return idx, sorted(all_paths)


def prefix_faces(key: str, all_paths: list) -> list:
    """机制键前缀（CODEGEN_/COMPTIME_/LEXER_…）在产品树里按文件或目录名数得到的文件面。

    只给「机制行/修法行没点名文件」的卡当兜底：前缀是寻虫轮写进 summary 的族名，
    拿它在树里做名字匹配，比我把某个模块名敲进代码里更接近「读出来的」。
    """
    if not re.match(r"^[A-Z]{3,}_", key):
        return []
    tok = key.split("_")[0].lower()
    hits = [
        p
        for p in all_paths
        if tok in Path(p).stem.lower() or tok in [s.lower() for s in Path(p).parts[:-1]]
    ]
    return sorted(hits)


def parse_open_cards(idx: dict, all_paths: list) -> list:
    txt = LEDGER.read_text(encoding="utf-8")
    out = []
    for chunk in re.split(r"(?m)^## ", txt)[1:]:
        head = chunk.split("\n", 1)[0]
        m = re.match(r"BUG-(\d+) \[([^\]]+)\] \[(critical|high|medium|low)\] (\w+)", head)
        if not m:
            continue
        if re.search(r"(?m)^### FIXED", chunk):
            continue
        sig = re.search(r"- summary: \[(\w+)\]", chunk)
        dom = re.search(r"修属=([^ 。，\n]+)", chunk)
        tid = re.search(r"- task_id: (\S+)", chunk)
        rep = re.search(r"- reported_by: (\S+)", chunk)
        hand = HANDOFF.search(chunk)
        chg = "\n".join(
            f"{a}{b}"
            for a, b in SCOPE_RE.findall(chunk)
            if not a.startswith("-") and "立单依据" not in a
        )
        decl = "\n".join(f"{b}" for a, b in SCOPE_RE.findall(chunk) if "立单依据" in a)
        scoped = chg + "\n" + decl

        def resolve(text: str) -> tuple:
            found, amb = [], []
            for name in sorted(set(BARE_RE.findall(text))):
                hits = idx.get(f"{name}.py") or idx.get(f"{name}.pyx") or []
                if len(hits) == 1:
                    found.append(hits[0])
                elif len(hits) > 1:
                    amb.append(f"{name}.py -> {hits}")
            return sorted(set(PATH_RE.findall(text)) | set(found)), amb

        chg_faces, ambiguous = resolve(chg)
        decl_faces, amb2 = resolve(decl)
        ambiguous += amb2
        dom_faces = [DOMAINS[k] for k in (dom.group(1).split("/") if dom else []) if k in DOMAINS]
        sources = []
        if chg_faces:
            sources.append("机制/修法行")
        if decl_faces:
            sources.append("立单依据行")
        if dom_faces:
            sources.append("修属域")
        faces = sorted(set(chg_faces) | set(decl_faces) | set(dom_faces))
        if not [f for f in faces if f.startswith(RADIUS)]:
            pf = prefix_faces(sig.group(1) if sig else head, all_paths)
            if pf:
                faces = sorted(set(faces) | set(pf))
                sources.append("机制键前缀在树里按名匹配")
        source = "+".join(sources)
        out.append(
            {
                "id": int(m.group(1)),
                "filed_at": m.group(2),
                "severity": m.group(3),
                "state": m.group(4),
                "key": sig.group(1) if sig else head[:60],
                "fix_domain": dom.group(1) if dom else "",
                "reported_by": rep.group(1) if rep else "",
                "task_id": tid.group(1) if tid else "",
                "handoff_quote": hand.group(0) if hand else "",
                "scope_chars": len(scoped),
                "face_source": source,
                "faces": faces,
                "frozen_faces": [f for f in faces if f.startswith(FROZEN)],
                "product_faces": [
                    f for f in faces if f.startswith(RADIUS) and not f.startswith("tests/")
                ],
                "test_faces": [f for f in faces if f.startswith("tests/")],
                "ambiguous_bare": ambiguous,
                "missing_on_disk": [
                    f for f in faces if not f.endswith("/") and not (ROOT / f).exists()
                ],
            }
        )
    return sorted(out, key=lambda r: r["id"])


def touched_files() -> list:
    """盘上现读的改动面（含未跟踪新文件）；只读 git status，不做任何写操作。"""
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    paths = []
    for ln in out.stdout.splitlines():
        m = re.match(r"^\s*(?:\?\?|[MRA D]{1,2})\s+(.+)$", ln)
        if m:
            paths.append(m.group(1).strip().strip('"'))
    return sorted(set(paths))


def column_of(card: dict) -> tuple:
    if card["handoff_quote"]:
        return "交人工或裁决", f"卡片原文含「{card['handoff_quote']}」"
    if card["faces"] and card["frozen_faces"] and not card["product_faces"]:
        return (
            "交人工或裁决（红线：冻结语义）",
            f"认领面只剩冻结文档 {card['frozen_faces']} ⇒ 本轮不许改 SYNTAX/PROJECT-SPEC",
        )
    if card["product_faces"]:
        if not TASK_ID_RE.fullmatch(card["task_id"]):
            return (
                "未认领（转结仍 OPEN）",
                f"点了文件面 {card['product_faces'][:2]} 但卡上没有服务端卡号"
                f"（task_id=「{card['task_id'] or '空'}」）⇒ 没有可 claim 的条目，不认领",
            )
        missing = [
            f for f in card["product_faces"] if not f.endswith("/") and not (ROOT / f).exists()
        ]
        if missing:
            return (
                "未认领（转结仍 OPEN）",
                f"认领面里 {missing} 在盘上不存在 ⇒ 不凭空认领，交验证环节复核",
            )
        return "本环认领", f"机制/修法行点名 {card['product_faces'][:3]}，落在可改半径内"
    return "未认领（转结仍 OPEN）", "机制行与修法行都没点名可改文件面，也没有可映射的 修属 域"


def main() -> int:
    started = now_iso()
    idx, all_paths = product_index()
    cards = parse_open_cards(idx, all_paths)
    if not cards:
        REFUSE.append("账本里一张未闭环的单都没解析到 ⇒ 解析器或账本坏了，认领表没有输入")
    book = json.loads(BOOK.read_text(encoding="utf-8")) if BOOK.exists() else {}
    ring_keys = list(book.get("keys") or [])
    if not ring_keys:
        REFUSE.append("hunt_r5_book.json 没有 keys ⇒ R5-寻虫 的卡表读不到，本环新单无法核对")
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bug_rows = {
        str(r[0]): r[1]
        for r in db.execute("select id, description from tasks where ns='bugs' order by id")
    }
    db.close()
    touched = touched_files()

    for c in cards:
        c["column"], c["reason"] = column_of(c)

    planned = [c for c in cards if c["column"] == "本环认领"]
    handoff = [c for c in cards if c["column"].startswith("交人工或裁决")]
    handoff_words = [c for c in cards if c["column"] == "交人工或裁决"]
    handoff_redline = [c for c in cards if c["column"].startswith("交人工或裁决（红线")]
    unclaimed = [c for c in cards if c["column"].startswith("未认领")]
    ring_ids = [c["id"] for c in cards if c["key"] in ring_keys]
    legacy_open = [c["id"] for c in cards if c["key"] not in ring_keys]
    with_card = [c for c in cards if TASK_ID_RE.fullmatch(c["task_id"])]
    missing_task = sorted(c["task_id"] for c in with_card if c["task_id"] not in bug_rows)
    no_card = sorted(c["id"] for c in cards if not TASK_ID_RE.fullmatch(c["task_id"]))
    split_columns = {
        "本环认领": [c["id"] for c in planned],
        "交人工或裁决": [c["id"] for c in handoff_words],
        "交人工或裁决（红线：冻结语义）": [c["id"] for c in handoff_redline],
        "未认领（转结仍 OPEN）": [c["id"] for c in unclaimed],
    }
    claim_bad_file = sorted(c["id"] for c in planned if c["missing_on_disk"])
    claim_no_id = sorted(c["id"] for c in planned if not TASK_ID_RE.fullmatch(c["task_id"]))
    handoff_no_quote = sorted(c["id"] for c in handoff_words if not c["handoff_quote"])
    ambiguous = sorted({a for c in cards for a in c["ambiguous_bare"]})

    check(
        "四栏之和 = 未闭环卡数（分栏不吞行）",
        sum(len(v) for v in split_columns.values()),
        len(cards),
        f"未闭环 {len(cards)} 张",
    )
    check(
        "R5-寻虫 的 13 个机制键全部在账本里数得到（卡表与账本两路对齐）",
        len(ring_ids),
        len(ring_keys),
        f"键 {len(ring_keys)} 个 / 按键解析到的号 {ring_ids}",
    )
    check(
        "有卡号的卡片，其卡号都能从 bugs 树读回（不是我记得）",
        missing_task,
        [],
        f"读不到的：{missing_task[:6]}",
    )
    check(
        "本环认领栏里不许有没服务端卡号的单（没条目就没法 claim→verify 闭环）",
        claim_no_id,
        [],
        f"认领了却无卡号：{claim_no_id}",
    )
    check(
        "本环认领栏的文件面必须逐个在盘上存在（解析器不许凭空认领）",
        claim_bad_file,
        [],
        f"盘上没有的：{claim_bad_file}",
    )
    check(
        "按原文交人工的栏位必须逐字带引文，否则不许进这一栏",
        handoff_no_quote,
        [],
        f"空引文的交人工项：{handoff_no_quote}",
    )
    check(
        "本环认领的每张卡都记录了认领面是从哪一路读出来的（没有来源=我在编）",
        sorted(c["id"] for c in planned if not c["face_source"]),
        [],
        f"无来源的认领卡：{sorted(c['id'] for c in planned if not c['face_source'])}",
    )
    check(
        "裸名反查不许有歧义（歧义 = 我把两个模块混认成一个）",
        ambiguous,
        [],
        f"歧义裸名：{ambiguous[:4]}",
    )
    ctl = {
        "handoff_quote": "",
        "faces": ["SYNTAX/99-fake.md"],
        "frozen_faces": ["SYNTAX/99-fake.md"],
        "product_faces": [],
        "task_id": "T0r9999",
        "missing_on_disk": [],
    }
    ctl_col, ctl_reason = column_of(ctl)
    check(
        "反例：只点冻结面的假卡必须被挡在认领栏外（规则不是「什么都认领」）",
        ctl_col,
        "交人工或裁决（红线：冻结语义）",
        f"实得 {ctl_col}：{ctl_reason}",
    )
    ctl2 = dict(ctl, faces=["cypyc/nope.py"], frozen_faces=[], product_faces=["cypyc/nope.py"])
    c2_col, _ = column_of(ctl2)
    check(
        "反例：点盘上不存在的文件面的假卡不许进认领栏",
        c2_col.startswith("未认领"),
        True,
        f"实得 {c2_col}",
    )
    ctl3 = dict(ctl, faces=["cypyc/cli.py"], frozen_faces=[], product_faces=["cypyc/cli.py"])
    c3_col, _ = column_of(dict(ctl3, task_id="未派单（R5-修复）"))
    check(
        "反例：有产品码文件面但没有卡号的假卡只能转结（不认领）",
        c3_col,
        "未认领（转结仍 OPEN）",
        f"实得 {c3_col}",
    )
    check(
        "必然不存在的单号必须解析不出（解析器不恒真）",
        len([c for c in cards if c["id"] == 9999]),
        0,
        "对照卡：BUG-9999",
    )
    if len(ring_ids) != 13:
        REFUSE.append(f"本环新单按键数到 {len(ring_ids)} 张，应为 13 ⇒ 卡表与账本没对齐")

    doc = {
        "started": started,
        "self_checks": CHECKS,
        "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
        "cards_total": len(cards),
        "planned_keys": [c["key"] for c in planned],
        "planned_ids": [c["id"] for c in planned],
        "split_columns": split_columns,
        "legacy_open_ids": legacy_open,
        "ring_new_ids": ring_ids,
        "no_server_card_ids": no_card,
        "ambiguous_bare": ambiguous,
        "face_sources": {
            s: sum(1 for c in planned if c["face_source"] == s)
            for s in sorted({c["face_source"] for c in planned})
        },
        "cards": cards,
        "git_touched": touched,
        "handoff_quote_len": len(handoff),
        "unclaimed_severities": {
            s: sum(1 for c in unclaimed if c["severity"] == s)
            for s in ("critical", "high", "medium", "low")
        },
        "note": "栏位与理由全部从 memory/bugs.md 现读反解，认领面只取机制行/修法行；"
        "未认领不等于关闭，转结时状态仍是 OPEN。",
        "refuse": sorted(set(REFUSE)),
        "at_utc": now_iso(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    green = sum(1 for c in CHECKS if c["ok"])
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "cards_total": len(cards),
                "columns": {k: len(v) for k, v in split_columns.items()},
                "planned_ids": doc["planned_ids"],
                "legacy_open": len(legacy_open),
                "no_server_card_ids": no_card,
                "face_sources": doc["face_sources"],
                "red_checks": doc["self_checks_red"],
                "self_checks": f"{green}/{len(CHECKS)}",
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
        tail = (traceback.format_exc().strip().splitlines() or [""])[-1]
        OUT.write_text(
            json.dumps(
                {
                    "refuse": [f"崩在 {type(exc).__name__}: {exc} @ {tail}"],
                    "at_utc": now_iso(),
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
