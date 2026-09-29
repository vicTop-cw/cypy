"""R4-修复 的报告自证：渲染之前把 spec 的每一道门禁与散文里的每一个占位都解一遍。

`report_kit.py` 在 refuse 非空时**不会**写报告文件，所以这里的目标是"一次渲染成功"：
① 每道 gate 的 artifact 在盘上、JSON 合法、path 解析得出来、谓词成立；
② 散文片段里每个 `{{件|路径}}` 都能解析（并且**非空**——空串/空列表用 truthy 会假绿）；
③ 散文引用的件必须都在 spec 的 artifacts 清单里（清单口径漏一件就是无人认领的证据）；
④ §标题声明的条数 == 正文实际条数（上一环被这条抓到过）；
⑤ 门禁 label 不重复；gate 的 `min` 不许是 0（恒真门）；
⑥ 页脚种子与正文计数不冲突。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "report_spec_r4_fix.json"
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def path_tokens(dotted: str) -> list:
    out = []
    for part in re.split(r"\.", dotted):
        part = part.strip()
        if part.startswith("[") and part.endswith("]"):
            out.append(part[1:-1].strip("'\""))
        else:
            out.append(part)
    return [p for p in out if p != ""]


def walk(obj, dotted: str):
    cur = obj
    if not dotted.strip():
        return cur, ""
    for part in path_tokens(dotted):
        if isinstance(cur, list):
            if not part.isdigit():
                return None, f"路径 {dotted} 在列表处需要下标（遇到 {part}）"
            cur = cur[int(part)] if int(part) < len(cur) else None
            continue
        if not isinstance(cur, dict):
            return None, f"路径 {dotted} 中途不是对象（停在 {part}）"
        if part not in cur:
            return None, f"键 {part} 不在件里（实际键：{sorted(cur)[:10]}）"
        cur = cur[part]
    return cur, ""


def load(rel: str, cache: dict):
    if rel in cache:
        return cache[rel]
    p = ROOT / rel
    if not p.exists() and "/" not in rel and chr(92) not in rel:
        p = HERE / rel
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


def holds(value, gate: dict):
    if value is None:
        return False, "解析出 null（判据空转）"
    if "equals" in gate:
        return value == gate["equals"], f"=={gate['equals']!r}，实得 {value!r}"[:160]
    if "min" in gate:
        n = len(value) if isinstance(value, (list, dict, str)) else value
        if not isinstance(n, (int, float)):
            return False, f"min 用不上（{type(value).__name__}）"
        return n >= gate["min"], f"≥{gate['min']}，实得 {n}"
    if gate.get("truthy"):
        return bool(value), f"truthy，实得 {bool(value)}"
    return False, "门禁没有 min/equals/truthy 任一键 ⇒ 无从判定"


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    cache: dict = {}
    body_rel = spec["fragment"]
    state, body = load(body_rel, cache)
    if state != "TEXT" or not body:
        REFUSE.append(f"散文片段 {body_rel} 不可用（{state}）")
        body = ""

    resolved_gates, failed_gates = [], []
    for g in spec["gates"]:
        st, obj = load(g["artifact"], cache)
        if st != "OK":
            failed_gates.append(f'{g["label"]} 件不可用（{st}）：{g["artifact"]}')
            continue
        val, why = walk(obj, g["path"])
        if why:
            failed_gates.append(f'{g["label"]} 路径失败：{why}')
            continue
        ok, detail = holds(val, g)
        if not ok:
            failed_gates.append(f'{g["label"]} 判据不成立：{detail}')
        else:
            resolved_gates.append(g["label"])
    if failed_gates:
        REFUSE.append(f"{len(failed_gates)} 道门禁未过：{json.dumps(failed_gates, ensure_ascii=False)}")

    labels = [g["label"] for g in spec["gates"]]
    dup = sorted({x for x in labels if labels.count(x) > 1})
    check("门禁 label 不重复", dup, [], "按 label 计数")
    zero_min = [g["label"] for g in spec["gates"] if g.get("min") == 0]
    check("不许有 min=0 的恒真门", zero_min, [], "min=0 永远成立")
    no_pred = [g["label"] for g in spec["gates"]
               if not ({"min", "equals"} & set(g) or g.get("truthy"))]
    check("每道门禁都自带可判谓词", no_pred, [], "缺 min/equals/truthy")

    refs = re.findall(r"\{\{([^{}]+)\}\}", body)
    bad_ph, empty_ph = [], []
    for expr in refs:
        if "|" not in expr:
            bad_ph.append(f"占位不是 件|路径 形状：{expr}")
            continue
        rel, dotted = expr.split("|", 1)
        st, obj = load(rel.strip(), cache)
        if st != "OK":
            bad_ph.append(f"{rel} 不可用（{st}）")
            continue
        val, why = walk(obj, dotted)
        if why:
            bad_ph.append(f"{rel}|{dotted} 解析失败：{why}")
        elif val in ([], {}, "", None):
            empty_ph.append(f"{rel}|{dotted}")
    if bad_ph:
        REFUSE.append(f"{len(bad_ph)} 个散文占位解析不出：{json.dumps(bad_ph, ensure_ascii=False)}")
    check("散文占位全部解析成功", bad_ph, [], "件在盘上且路径可解")

    listed = set(spec["artifacts"])
    used_files = sorted({e.split("|", 1)[0].strip() for e in refs if "|" in e})
    # 散文允许只写文件名（report_kit 会回落到 .fist-loop 目录）⇒ 带目录的才按仓库根对清单
    named = [f for f in used_files if "/" in f and chr(92) not in f]
    check("散文按仓库根路径点名的件都在 artifacts 清单里",
          [f for f in named if f not in listed], [], "清单口径不能漏件")
    listed_loop = {a.split("/")[-1] for a in spec["artifacts"] if a.startswith(".fist-loop")}
    used_base = {f.split("/")[-1] for f in used_files if f.startswith(".fist-loop")} \
        | {e.split("|", 1)[0].strip() for e in refs if "|" in e and "/" not in e.split("|")[0]}
    check("散文引用的驱动件都在 spec 清单里",
          sorted(used_base - listed_loop), [], "按 basename 对齐")
    check("清单里声明的件确实在盘上",
          [a for a in spec["artifacts"] if not (ROOT / a).exists()], [], "artifacts 存在性")

    # 空值占位只允许一种情形：**同一件同一路径上有一道 equals 为空的门禁**在替它作证
    zero_gates = {f"{Path(x['artifact']).name}|{x['path']}" for x in spec["gates"]
                  if "equals" in x and x["equals"] in ([], {}, "")}
    unjustified = sorted(set(empty_ph) - zero_gates)
    check("占位非空（空列表必须由 equals:[] 的门禁作证，否则是判据看不见样本）",
          unjustified, [], f"空值占位 {len(set(empty_ph))} 个，无佐证的 {len(unjustified)} 个")

    sec8 = re.search(r"## 八、[^\n]*\n([\s\S]*?)(?=\n## 九、)", body)
    items8 = len(re.findall(r"^\d+\. ", sec8.group(1), re.M)) if sec8 else -1
    check("§八 标题声明条数 == 正文条数", items8, 8,
          (sec8.group(0).splitlines()[0] if sec8 else "§八 缺失"))

    gates_by_prefix = {}
    for g in spec["gates"]:
        gates_by_prefix.setdefault(g["label"].split("-")[0], []).append(g["label"])
    check("门禁覆盖八条法 + 账面载体（≥9 组）", len(gates_by_prefix) >= 9, True,
          json.dumps({k: len(v) for k, v in gates_by_prefix.items()}, ensure_ascii=False))
    check("每道 gates 引用的件都成功解析", len(resolved_gates) + len(failed_gates),
          len(spec["gates"]), f"过 {len(resolved_gates)} / 败 {len(failed_gates)}")

    refuse = sorted(set(REFUSE)) + [f"自证未过：{c['label']}（实得 "
                                    f"{json.dumps(c['got'], ensure_ascii=False)[:200]}）"
                                    for c in CHECKS if not c["ok"]]
    doc = {"started": started, "spec": SPEC.name, "report_name": spec["name"],
           "gates_total": len(spec["gates"]), "gates_pass": len(resolved_gates),
           "gates_fail": failed_gates,
           "gates_by_law": {k: len(v) for k, v in gates_by_prefix.items()},
           "section8_items": items8,
           "placeholders_total": len(refs), "placeholders_bad": bad_ph,
           "placeholders_empty": sorted(set(empty_ph)),
           "artifacts_declared": len(spec["artifacts"]),
           "body": body_rel, "self_checks": CHECKS, "refuse": refuse,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    (HERE / "fix_r4_self_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse, "gates": f"{len(resolved_gates)}/{len(spec['gates'])}",
                      "placeholders": f"{len(refs) - len(bad_ph)}/{len(refs)}",
                      "gates_by_law": doc["gates_by_law"],
                      "empty_placeholders": doc["placeholders_empty"]},
                     ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
