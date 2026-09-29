"""R4-推进 法③：把「已声明未实现 / 已声明但实现错」的运算子与类型面**量成一张表**，逐条给去向。

判据的规格来自文档自己的等价式，不是我另写的期望：`SYNTAX/12-operators.md` 的复合赋值行第 4 格
写着 `x = x <op> 3` ⇒ 夹具用 `5`，把规格里的数换成 5 与产物里的那一行逐字比。
于是三态可判且都能红：`ok`（产物 == 规格）、`rejected`（CLI 非零、响亮拒绝）、
`silent_wrong`（CLI 零但产物 != 规格 —— 静默产错码，最坏的一态）。

`silent_wrong` 集合钉成"恰好 `^=` 一条"：修好了这一格会红，逼人来关账，而不是让尺子静默变宽。
分类器自己配一红一绿两支对照（合成一行"产物丢了运算符"必被判 silent_wrong、真实正确行必不被误判），
否则这张表可能只是恒绿装饰。
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import advance_r4_lib as LIB  # noqa: E402
from loop_kit import record  # noqa: E402

OUT = HERE / "advance_r4_scope_face.json"
DOC = "SYNTAX/12-operators.md"
SRC = LIB.TMP / "scope_face"
AUG_OPS = ["+=", "-=", "*=", "/=", "//=", "%=", "**=", "<<=", ">>=", "&=", "|=", "^="]
BIN_EXPRS = [("a & b", "&"), ("a | b", "|"), ("a ^ b", "^"), ("a << 2", "<<"),
             ("a >> 1", ">>"), ("a / 2", "/"), ("a // 2", "//"), ("a % 2", "%"),
             ("a ** 2", "**"), ("~a", "~")]
OTHER_FACES = [("pointer_char_type", "a4_ptr_char.cypy", "PROJECT-SPEC/SYNTAX 声明的 *char 指针返回"),
               ("let_reassign_accepted", "a4_let_reassign.cypy", "let 的不可变语义")]
# 已知缺陷的钉住集合（修法要么补词位要么改赋值路径，会碰 `^:`/`~:` 冻结构建块符号 ⇒ 本环不修）
PINNED_SILENT_WRONG = ["^="]
PINNED_REJECTED_DECLARED = ["**=", "&=", "|=", "^", "~"]
CHECKS: list = []
REFUSE: list = []


def op_rows() -> dict:
    """从运算符表反解「符号 → 行号 + 等价式」，只认第一格是反引号包住的符号的行。"""
    text = (ROOT / DOC).read_text(encoding="utf-8", errors="replace").splitlines()
    out = {}
    for i, ln in enumerate(text, 1):
        m = re.match(r"^\|\s*`([^`]+)`\s*\|", ln)
        if not m:
            continue
        sym = m.group(1).replace("\\|", "|").strip()
        formula = None
        for cell in re.findall(r"`([^`]+)`", ln):
            if re.fullmatch(r"x\s*=\s*x\s*\S+\s*3", cell.strip()):
                formula = cell.strip()
        out.setdefault(sym, {"doc": DOC, "line": i, "formula": formula,
                             "row": ln.strip()[:100]})
    return out


def classify(op: str, spec: str, rc: int, pyx_assign: str) -> str:
    """三态分类：产物与规格逐字相等才叫 ok。"""
    if rc != 0:
        return "rejected"
    if spec and pyx_assign == spec:
        return "ok"
    return "silent_wrong"


def fixture(name: str, body: str) -> Path:
    f = SRC / (name + ".cypy")
    f.write_text("def main() -> int:\n" + body + "    return 0\n", encoding="utf-8")
    return f


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if SRC.exists():
        shutil.rmtree(SRC)
    SRC.mkdir(parents=True)
    rows = op_rows()
    tree = LIB.build_tree(LIB.AFTER_TREE, revert=False)
    ident = LIB.identity_probe(LIB.AFTER_TREE)
    if not ident["inside"]:
        REFUSE.append(f"身份探针失败：{ident.get('scope')}")

    aug, binary = [], []
    for i, op in enumerate(AUG_OPS):
        nm = "aug%02d" % i
        f = fixture(nm, f"    let x: int = 1\n    x {op} 5\n    print(x)\n")
        got = run(f, nm)
        declared = op in rows
        spec = (rows[op]["formula"] or "").replace(" 3", " 5") if declared else None
        assign = next((ln.strip() for ln in got["pyx_lines"]
                       if re.match(r"x\s*[:=]", ln.strip()) and "int" not in ln), "")
        state = classify(op, spec or "", got["rc"], assign)
        aug.append({"op": op, "declared_in_doc": declared,
                    "declared_at": f"{rows[op]['doc']}:{rows[op]['line']}" if declared else None,
                    "spec_formula": spec, "generated": assign, "rc": got["rc"], "state": state,
                    "error_tail": got["err"]})

    for idx, (expr, sym) in enumerate(BIN_EXPRS):
        nm = "bin%02d" % idx
        f = fixture(nm, f"    let a: int = 6\n    let b: int = 3\n    print({expr})\n")
        got = run(f, nm)
        declared = sym in rows
        printed = [ln.strip() for ln in got["pyx_lines"] if f"print({expr})" in ln]
        state = "rejected" if got["rc"] != 0 else ("ok" if printed else "silent_wrong")
        binary.append({"expr": expr, "op": sym, "declared_in_doc": declared,
                       "declared_at": (f"{rows[sym]['doc']}:{rows[sym]['line']}"
                                       if declared else None),
                       "generated": printed, "rc": got["rc"], "state": state,
                       "error_tail": got["err"]})

    others = []
    for key, fname, label in OTHER_FACES:
        got = run(LIB.PROBE / fname, "of_" + key)
        others.append({"face": key, "fixture": f".fist-loop-20260927/advance_r4_probe/{fname}",
                       "claim": label, "rc": got["rc"], "error_tail": got["err"],
                       "undefined_names": got["undef"]})

    silent_wrong = sorted([r["op"] for r in aug + binary if r["state"] == "silent_wrong"])
    declared_rejected = sorted([r["op"] for r in aug + binary
                                if r["declared_in_doc"] and r["state"] == "rejected"])
    queue = adjudication(aug, binary, others, silent_wrong, declared_rejected)
    for item in queue:
        if not item["disposition"]:
            REFUSE.append(f"挂账项没有去向：{item['key']}")
        if item["state"] == "silent_wrong" and not item["bug_card"]:
            REFUSE.append(f"静默产错码必须挂到缺陷卡：{item['key']}")

    record(CHECKS, REFUSE, "silent_wrong 集合必须逐字等于钉住的已知缺陷（修好了会红，逼人来关账）",
           silent_wrong, sorted(PINNED_SILENT_WRONG), f"实得 {silent_wrong}")
    record(CHECKS, REFUSE, "declared 但被响亮拒绝的集合也要逐字点名（不许静默扩面）",
           declared_rejected, sorted(PINNED_REJECTED_DECLARED), f"实得 {declared_rejected}")

    # 分类器自己的成对对照：合成违例必被抓、真实正确行必不被误抓
    fake = classify("+=", "x = x + 5", 0, "x = 5")
    real_ok = next(r for r in aug if r["op"] == "+=")
    clean = classify("+=", real_ok["spec_formula"], real_ok["rc"], real_ok["generated"])
    record(CHECKS, REFUSE, "分类器对照：产物丢运算符的合成行必被判 silent_wrong",
           fake, "silent_wrong", "否则这张表是恒绿装饰")
    record(CHECKS, REFUSE, "分类器对照：真实正确行不得被误判", clean, "ok",
           f"实得 {clean}（产物 {real_ok['generated']}）")
    record(CHECKS, REFUSE, "规格来自文档自己的等价式，不是手抄：12 条复合赋值行都要反解到 formula",
           sum(1 for r in aug if r["spec_formula"]), len(AUG_OPS),
           f"实得 {sum(1 for r in aug if r['spec_formula'])}/{len(AUG_OPS)}")
    LIB.cleanup()

    doc = {"started": started,
           "law": "已声明未实现/实现错的运算子与类型面逐条量化并给去向（本环不修，只挂账）",
           "doc_source": DOC, "doc_rows_total": len(rows),
           "augmented_matrix": aug, "binary_matrix": binary, "other_faces": others,
           "silent_wrong": silent_wrong, "declared_rejected": declared_rejected,
           "adjudication_queue": queue,
           "pinned": {"silent_wrong": PINNED_SILENT_WRONG,
                      "declared_rejected": PINNED_REJECTED_DECLARED},
           "trees": {"before_not_used": "本件只测工作区语义面，改前态由法①②承担",
                     "after": tree, "identity": ident},
           "not_edited_this_ring": ["二元 ^ 与一元 ~（词位与 `^:`/`~:` 冻结构建块冲突）",
                                    "**= / &= / |=（同一赋值路径）", "*char 指针类型面",
                                    "let 不可变（既有语义面，改动会动既有测试）"],
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "silent_wrong": silent_wrong,
                      "declared_rejected": declared_rejected,
                      "aug": {r["op"]: [r["state"], r["rc"]] for r in aug},
                      "bin": {r["op"]: [r["state"], r["rc"]] for r in binary},
                      "queue": [q["key"] for q in queue]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


def run(src: Path, tag: str) -> dict:
    """统一走「复制进树内 + 相对路径喂 CLI」这一条路（绝对路径形状不参与结论）。"""
    d = LIB.AFTER_TREE / "scope_face"
    d.mkdir(parents=True, exist_ok=True)
    dst = d / (tag + ".cypy")
    dst.write_bytes(src.read_bytes())
    out = LIB.TMP / ("sf_" + tag)
    r = LIB.transpile(dst.relative_to(LIB.AFTER_TREE), LIB.AFTER_TREE, out)
    pyx = LIB.pyx_of(out)
    err = [ln.strip() for ln in r["stdout_tail"] if "错误" in ln or "FAIL" in ln]
    return {"rc": r["rc"], "pyx_lines": pyx.splitlines(), "err": err[:1],
            "undef": r["undefined_names"]}


def adjudication(aug, binary, others, silent_wrong, declared_rejected) -> list:
    """去向表：每条要么本环修（不修就得点名为什么），静默产错码必须挂缺陷卡。"""
    cards = {"^=": "BUG-74", "^": "BUG-75", "~": "BUG-75"}
    items = []
    for r in aug + binary:
        if r["state"] == "ok":
            continue
        key = r["op"]
        items.append({
            "key": key, "state": r["state"],
            "declared_at": r["declared_at"],
            "disposition": ("挂缺陷卡，交 R5-修复" if r["state"] == "silent_wrong"
                            else "挂账：修法要碰 `^:`/`~:` 冻结构建块词位，超出本环半径"),
            "bug_card": cards.get(key, ""),
            "why_not_this_ring": ("本环只补名称表（零 codegen 改动）；词位消歧会动解析器与冻结语法面"
                                  if r["state"] != "ok" else "")})
    for o in others:
        items.append({"key": o["face"], "state": "rejected" if o["rc"] else "accepted_unchecked",
                      "declared_at": o["claim"],
                      "disposition": ("挂账：需要类型/内存语义设计，本环不修"
                                      if o["face"] != "let_reassign_accepted"
                                      else "挂账：既有 let 重赋值语义未强制，动它会撞既有测试"),
                      "bug_card": "", "why_not_this_ring": "越出「名称表补齐」的安全半径"})
    return items


if __name__ == "__main__":
    sys.exit(main())
