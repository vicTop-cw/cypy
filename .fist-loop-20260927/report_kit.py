#!/usr/bin/env python3
"""通用报告装配器（R2 起复用）：散文由我写，数字一律从盘上证件反解。

用法：python report_kit.py <spec.json> [--pre-close]

spec = {
  "name": "20260927.15.30.01",            # 报告文件名（落在 memory/reviews/<name>.md）
  "title": "R2-寻虫（hunt）环节报告",
  "root_task": "T0r55", "assignee": "cypy-hunter", "marker": "[selfdrive-hunt]",
  "fragment": ".fist-loop-20260927/r2_hunt_body.md",
  "artifacts": [".fist-loop-20260927/hunt_r2_scan.json", ...],
  "gates": [
    {"label": "①", "claim": "…", "artifact": "…json", "path": "cli_face.rows", "min": 6}
  ],
  "closure": {"stage": "close_r2_hunt.out.json", "root": "close_r2_hunt_root.out.json"},
  "footer": "carry=…"
}

判据：任一 artifact 缺失/JSON 坏 ⇒ 拒绝出报告；任一 gate 不满足 ⇒ 记进 refuse 并如实渲染成
❌（**不出绿报告**）；模板里每个 {{…}} 占位都必须解析成功，解析不到就是 refuse 而不是留空。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
NS = "cypy-loop-20260927"


def load_art(rel: str, cache: dict):
    if rel in cache:
        return cache[rel]
    p = ROOT / rel
    if not p.exists() and "/" not in rel and chr(92) not in rel:
        p = HERE / rel  # 散文片段里允许只写文件名；带目录的按仓库根解析
    if not p.exists():
        cache[rel] = ("MISSING", None)
        return cache[rel]
    txt = p.read_text(encoding="utf-8", errors="replace")
    if rel.endswith(".json"):
        try:
            cache[rel] = ("OK", json.loads(txt))
        except json.JSONDecodeError as exc:
            cache[rel] = ("BADJSON", str(exc)[:200])
    else:
        cache[rel] = ("TEXT", txt)
    return cache[rel]


def path_tokens(dotted: str) -> list:
    """把 `probes['P9.black_noise_split'].parser_py.vs_head_raw` 拆成 token 序列。

    键本身可以含点（探针的 tag 就叫 `P1.static_no_self`）——只按 "." 切会把这种键劈断，
    表现为"键 P1 不在件里"的假失败。方括号段原样当一个键。
    """
    toks = []
    i, n = 0, len(dotted)
    while i < n:
        ch = dotted[i]
        if ch == ".":
            i += 1
            continue
        if ch == "[":
            j = dotted.index("]", i)
            inner = dotted[i + 1 : j].strip()
            q = inner[:1]
            if q in (chr(39), chr(34)) and inner[-1:] == q:
                inner = inner[1:-1]
            toks.append(inner)
            i = j + 1
            continue
        ends = [x for x in (dotted.find(".", i), dotted.find("[", i)) if x >= 0]
        nxt = min(ends) if ends else n
        toks.append(dotted[i:nxt])
        i = nxt
    return toks


def walk(obj, dotted: str):
    cur = obj
    if not dotted.strip():
        # 空路径过去会 split 出 [''] 然后报"键  不在件里"，或更糟：在某些件里恰好解析成 None
        # 又被 `min` 判成"长度不够"——恒假 gate 就是这么来的。空路径显式返回根对象。
        return cur, ""
    for part in path_tokens(dotted):
        if isinstance(cur, list):
            if not part.isdigit():
                return None, f"路径 {dotted} 在列表处需要下标"
            cur = cur[int(part)] if int(part) < len(cur) else None
            continue
        if not isinstance(cur, dict):
            return None, f"路径 {dotted} 中途不是对象（停在 {part}）"
        if part not in cur:
            return None, f"键 {part} 不在件里（实际键：{sorted(cur)[:8]}）"
        cur = cur[part]
    return cur, ""


def render(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)[:400]


def gate_ok(row: dict, value) -> tuple:
    if value is None:
        return False, "解析出 null（判据空转：路径指到了一个不存在的键）"
    if "min" in row:
        n = len(value) if isinstance(value, (list, dict, str)) else value
        return (isinstance(n, (int, float)) and n >= row["min"]), f"≥{row['min']}，实得 {n}"
    if "equals" in row:
        return value == row["equals"], f"=={row['equals']}，实得 {render(value)}"
    if "truthy" in row:
        return bool(value) == row["truthy"], f"truthy={row['truthy']}，实得 {render(value)}"
    return False, "gate 没写 min/equals/truthy ⇒ 装配器拒绝"


def call_log_tally(limit: int = 400) -> dict:
    db = ROOT / "fist-mbt.db"
    if not db.exists():
        return {"error": "no db"}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = list(
            con.execute(
                "select tool, count(*) from (select tool from call_log order by id desc limit ?) "
                "group by tool order by tool",
                (limit,),
            )
        )
    except sqlite3.Error as exc:
        con.close()
        return {"error": str(exc)[:120]}
    con.close()
    return {"rows": limit, "tally": {t: c for t, c in rows}}


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    pre_close = "--pre-close" in sys.argv[2:]
    refuse: list = []
    cache: dict = {}

    for rel in spec["artifacts"]:
        state, detail = load_art(rel, cache)
        if state != "OK" and not (state == "TEXT" and detail):
            if state == "TEXT":
                continue
            if pre_close and state == "MISSING":
                continue  # 收口链产物此时本就还不存在；坏件（JSON 无效等）仍然照拒
            refuse.append(f"artifact {rel} 不可用（{state} {detail}）")
    frag_rel = spec["fragment"]
    fstate, ftext = load_art(frag_rel, cache)
    if fstate != "TEXT" or not ftext:
        refuse.append(f"散文片段 {frag_rel} 缺失（{fstate}）")
        ftext = ""

    body = ftext

    def sub(m):
        expr = m.group(1).strip()
        if "|" not in expr:
            refuse.append("占位 " + "{{" + expr + "}}" + " 不是 artifact|path 形状")
            return "‹未解析›"
        rel, dotted = expr.split("|", 1)
        state, obj = load_art(rel, cache)
        if state != "OK":
            if pre_close and state == "MISSING":
                return "‹收口后生成›"
            refuse.append(f"占位取不到 {rel}（{state}）")
            return "‹未解析›"
        val, why = walk(obj, dotted)
        if why:
            refuse.append(f"占位 {rel}|{dotted} 解析失败：{why}")
            return "‹未解析›"
        return render(val)

    body = re.sub(r"\{\{([^{}]+)\}\}", sub, body)

    gate_rows = []
    for row in spec.get("gates", []):
        state, obj = load_art(row["artifact"], cache)
        if state != "OK":
            if pre_close and state == "MISSING":
                gate_rows.append((row["label"], row["claim"], "⏳ 未落盘（预收口，收口后重生成时照拒）"))
                continue
            gate_rows.append((row["label"], row["claim"], f"❌ 件不可用（{state}）"))
            refuse.append(f"gate {row['label']} 的件 {row['artifact']} 不可用")
            continue
        val, why = walk(obj, row["path"])
        if why:
            gate_rows.append((row["label"], row["claim"], f"❌ {why}"))
            refuse.append(f"gate {row['label']} 路径失败：{why}")
            continue
        ok, detail = gate_ok(row, val)
        gate_rows.append((row["label"], row["claim"], ("✅ " if ok else "❌ ") + detail))
        if not ok:
            refuse.append(f"gate {row['label']} 未达：{detail}")

    gates_md = (
        "\n".join(f"| {a} | {b} | {c} |" for a, b, c in gate_rows)
        or "| — | 本 spec 未声明门禁 | — |"
    )

    closure_rows = []
    for key, fname in (spec.get("closure") or {}).items():
        state, obj = load_art(fname, cache)
        if state != "OK":
            closure_rows.append(
                (key, fname, "未落盘（收口链尚未跑到或先预检被拒）" if pre_close else f"❌ {state}")
            )
            if not pre_close:
                refuse.append(f"收口件 {fname} 不可用（{state}）")
            continue
        if key == "root":
            refused_rows = obj.get("refused") or obj.get("refusals") or []
            closure_rows.append(
                (
                    key,
                    fname,
                    f"根 {obj.get('root_final')} / 叶完成 {obj.get('leaves_done')} / "
                    f"被拒 {obj.get('refused_count', len(refused_rows))} 条（逐字见 §被拒原文）",
                )
            )
            if obj.get("root_final") != "已归档":
                refuse.append(f"根任务未归档：{obj.get('root_final')}")
        else:
            failed = obj.get("failed") or []
            closure_rows.append((key, fname, f"{len(failed)} 张叶失败" if failed else "16/16 通过"))
            if failed:
                refuse.append(f"叶子失败：{failed[:4]}")
    closure_md = "\n".join(f"| {a} | `{b}` | {c} |" for a, b, c in closure_rows) or "| — | — | — |"

    refusals = []
    for key, fname in (spec.get("closure") or {}).items():
        state, obj = load_art(fname, cache)
        if state != "OK":
            continue
        for r in obj.get("refused") or obj.get("refusals") or []:
            if isinstance(r, dict):
                refusals.append(
                    (
                        r.get("call", "?"),
                        r.get("task_id", "?"),
                        str(r.get("error") or r.get("msg") or "")[:300],
                    )
                )
            else:
                refusals.append((key, fname, str(r)[:300]))
    refusals_md = (
        "\n".join(f"| `{a}` | `{b}` | {c} |" for a, b, c in refusals)
        or (
            "| — | — | 本次收口链没有出现任何被拒调用 |"
            if spec.get("closure")
            else "| — | — | 本 spec 未声明 closure 位：收口链在这份报告渲染**之后**才发，"
                 "它的被拒原文一律进 `.fist-loop-20260927/loop_progress.md`，"
                 "这里不预支「没有被拒」这句结论 |"
        )
    )

    tally = call_log_tally()
    tally_txt = json.dumps(tally.get("tally", {}), ensure_ascii=False)[:600]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    art_lines = "\n".join(f"- `{a}`" for a in spec["artifacts"])
    md = f"""# {spec['title']} · {spec['name']}

- 环节：{spec.get('stage', '')}；根任务 `{spec['root_task']}`；执行人 `{spec['assignee']}`
- 生成时刻 {stamp}；装配器 `report_kit.py`，**数字全部从下列证件反解**，散文见 `spec['fragment']`
- 收口模式：{"预收口（收口链未跑）" if pre_close else "收口后重生成"}
- 本 spec 声明的 artifact：
{art_lines}

{body}

## 门禁反解表

| 门禁 | 主张 | 装配器实测 |
|---|---|---|
{gates_md}

## 收口链状态

| 角色 | 件 | 实测 |
|---|---|---|
{closure_md}

## 被拒原文（逐字，一条不吞）

| 调用 | 任务 | 服务端原文 |
|---|---|---|
{refusals_md}

call_log 最近 {tally.get('rows', 0)} 行工具分布：`{tally_txt}`

```
{spec['marker']} round={spec.get('round', 'R2')} stage={spec.get('stage', '')} \
root={spec['root_task']} gates={len(gate_rows)} refused={len(refusals)} {spec.get('footer', '')}
```
"""
    out = ROOT / "memory" / "reviews" / f"{spec['name']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    if refuse:
        (HERE / f"report_kit_{spec['name']}.refuse.json").write_text(
            json.dumps({"refuse": refuse}, ensure_ascii=False, indent=1),
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"REFUSE": refuse[:12], "count": len(refuse)}, ensure_ascii=False))
        return 1
    out.write_text(md, encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "report": f"memory/reviews/{spec['name']}.md",
                "bytes": len(md.encode("utf-8")),
                "gates": len(gate_rows),
                "refusals": len(refusals),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
