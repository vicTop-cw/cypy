#!/usr/bin/env python3
"""R1 Step 0 — 口径定死：工具在列核对 + report_bug 落点实测（探针原样撤回）+ 定向基线取证。

模板要求「入一条试例 → 查文件落位 → 删试例（账本不留测试行）」。撤回按字节核对：
写入前留存原始字节，撤完把「条目序列」和「原文（尾随空白归一后）」两件事都对上才算过；
任一对不上就把账本按原始字节整体还原并退出——不带脏账本开工，也不允许「删漏一条」被当成成功。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "step0_r1.out.json"
NEED = {
    "publish",
    "task_plan_deep",
    "omega_spec_create",
    "omega_spec_review",
    "omega_result_verify",
    "omega_status",
    "laya_decide",
    "report_bug",
    "bug_list",
    "call_log",
    "issue_scan",
    "output_validate",
    "claim",
    "execute",
    "submit",
    "verify",
    "archive",
    "get",
    "list",
}


def titles(text: str) -> list[str]:
    return re.findall(r"(?m)^## (BUG-\d+)", text)


def norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def main() -> int:
    orig_bytes = LEDGER.read_bytes()
    orig_text = orig_bytes.decode("utf-8")
    orig_titles = titles(orig_text)

    c = lfist_lib.Client(timeout=120)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    frame = c._recv(c._send("tools/list", {}), 90)
    have = {t["name"] for t in (frame or {}).get("result", {}).get("tools", [])}
    missing = sorted(NEED - have)

    bl = c.call("bug_list", {"project_dir": "."})
    resolved = {
        "bug_list_path": bl.get("path"),
        "bug_list_resolved_path": bl.get("resolved_path"),
        "bug_list_count": bl.get("count"),
        "ledger_titles_on_disk": len(orig_titles),
    }

    rb = c.call(
        "report_bug",
        {
            "project_dir": ".",
            "summary": "[落点测试] Step0 探针：report_bug 落点口径实测，随即原样撤回（非缺陷）",
            "detail": "仅用于定死 project_dir 相对 server cwd 的落点口径；不发布修复单，撤回后账本不留痕。",
            "severity": "low",
            "publish_task": False,
            "reported_by": "cypy-loop-step0",
            "now": lfist_lib.utc_now(),
        },
    )
    c.close()

    probed = LEDGER.read_text(encoding="utf-8")
    new_ids = [i for i in titles(probed) if i not in orig_titles]
    ok_probe = len(new_ids) == 1
    if ok_probe:
        pat = re.compile(r"(?ms)^## " + re.escape(new_ids[0]) + r" .*?(?=^## BUG-|\Z)")
        m = pat.search(probed)
        ok_probe = bool(m)
        if m:
            LEDGER.write_text(
                probed[: m.start()] + probed[m.end() :], encoding="utf-8", newline="\n"
            )

    retracted = LEDGER.read_text(encoding="utf-8")
    ids_ok = titles(retracted) == orig_titles
    body_ok = norm(retracted) == norm(orig_text)
    if not (ids_ok and body_ok):
        LEDGER.write_bytes(orig_bytes)  # 整体还原，不留半截
        restored = LEDGER.read_text(encoding="utf-8")
        doc = {
            "verdict": "REFUSE",
            "tools_missing": missing,
            "resolved": resolved,
            "probe_new_ids": new_ids,
            "report_bug": rb,
            "retract_ids_ok": ids_ok,
            "retract_body_ok": body_ok,
            "hard_restore_done": titles(restored) == orig_titles
            and norm(restored) == norm(orig_text),
        }
        OUT.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        print("REFUSE — 探针撤回没回到原状，账本已按原始字节整体还原")
        return 1

    doc = {
        "verdict": "OK",
        "tools_missing": missing,
        "resolved": resolved,
        "probe_new_ids": new_ids,
        "probe_task_id": rb.get("task_id") if isinstance(rb, dict) else None,
        "report_bug_keys": sorted(rb.keys()) if isinstance(rb, dict) else None,
        "retract_ids_ok": ids_ok,
        "retract_body_ok": body_ok,
        "ledger_titles_final": len(titles(LEDGER.read_text(encoding="utf-8"))),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(doc, ensure_ascii=False, indent=1))
    if missing:
        print(f"REFUSE — 工具面缺件: {missing}")
        return 2
    print("OK Step0：project_dir='.' → ./memory/bugs.md（server cwd=Cypy 根）；探针已原样撤回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
