"""把指挥官亲笔的第三趟（BUG-90 调用方接线 + BUG-91 转义）并入车道台账。

verbatim 一律从盘上的件里现读再逐字贴（fix_r5_baselines.out / fix_r5_book91.json），
不手打红字；prose 里每个数都对着件说。只追加一条车道，不动别人家的回执。
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANES = HERE / "r5_fix_lanes.json"
BS_OUT = HERE / "fix_r5_baselines.out"
BOOK = HERE / "fix_r5_book91.json"
SUITE_RED = "    ✗ codegen_module_magic_attrs: failed"
SUITE_RED_MSG = "      Message: generated Cython lacks `__name__ = ...` assignment"


def red_lines_from_book() -> list:
    """BUG-91 的两条红字：直接取件里存的原文，按行拆。"""
    doc = json.loads(BOOK.read_text(encoding="utf-8"))
    out = []
    for node, blob in doc["measurement"]["red_while_removed"].items():
        for ln in blob.splitlines():
            ln = ln.strip()
            if ln.startswith(("E ", "assert", "FAILED", "tests\\")):
                out.append(ln[:220])
        out.append(f"（节点 {node.split('::')[-1]}，摘除态实测）")
    return out


def baseline_lines() -> list:
    txt = BS_OUT.read_text(encoding="utf-8")
    if "46/47" not in txt:
        return [f"（{BS_OUT.name} 里没有 46/47 那趟的记录，此条待补）"]
    got = json.loads(txt.split("BASELINES_EXIT")[0])
    return [
        *got["refuse"],
        f"\"three_systems_green\": {json.dumps(got['three_systems_green'])}",
        f"\"suite\": {json.dumps(got['suite'], ensure_ascii=False)}",
        f"BASELINES_EXIT={txt.strip().splitlines()[-1].split('=')[-1]}",
    ]


def main() -> int:
    doc = json.loads(LANES.read_text(encoding="utf-8"))
    names = [lane["lane"] for lane in doc["lanes"]]
    lane = {
        "lane": "lane-commander-identity",
        "status": "completed",
        "scope_declared": [
            "BUG-90 的另一半：调用方把源路径交给生成器（hook + project 两个入口）",
            "BUG-91：接上真路径之后产物头注里的反斜杠没转义 ⇒ Cython 就地语法错误（本环新入账）",
        ],
        "cards": [90, 91],
        "files_reported": [
            "cypyc/codegen/cython_generator.py",
            "cypy_hook/hook.py",
            "cypyc/project/project_compiler.py",
            "tests/codegen/test_r5_fix_codegen.py",
        ],
        "verbatim": baseline_lines() + red_lines_from_book(),
        "red_log": ".fist-loop-20260927/fix_r5_book91.json",
        "corrections": [
            "起因不是「套件坏了一条」而是 BUG-90 只修了一半：卡片机制栏自己写着"
            "「CythonGenerator(source_file=None) 的默认值从未被任何调用方覆盖」，"
            "而 codegen 车道的锁全部直接构造生成器（`_lower(..., source_file=...)`），"
            "打不到 hook/project 这两个真入口 ⇒ 删掉伪造之后，走文件入口的产物直接没有身份常量",
            "接线之后又暴露一条：产物头注把 Windows 路径原文写进模块 docstring，"
            "单反斜杠被读成 unicode 转义，项目模式 cythonize 就地 CompileError（新单 BUG-91，同环已修）",
            f"当场套件红字（本会话内实测，非盘上件）：{SUITE_RED} / {SUITE_RED_MSG}",
            "认领表按法①「从盘上反解」重跑一次：planned_ids 21→22（只多 91），"
            "ring_new_ids 仍是寻虫环那 13 个键，12/12 自证零红；重跑前的件留在 "
            "fix_r5_snap/intake_before_rerun.json",
            "BUG-91 不是寻虫环 13 张里的：report_bug 返回 BUG-91，账本 90→91 条、"
            "sqlite bugs 树 +1、call_log report_bug +1（三向见件 fix_r5_book91.json）",
        ],
        "measured_by_commander": [
            "双向 A/B（件里存着三段全文）：摘除前两条锁都绿 → 摘除后两条都红 → 装回后都绿，"
            "生成器按字节还原 sha256 前 12 位与件里 generator_sha 一致",
            "自研套件 codegen 档：接线前 9 项 1 failed（codegen_module_magic_attrs），接线后 9/9",
            "项目模式实测：临时工程 main.cypy 走 build() → SUCCESS True / COMPILED ['main']，"
            "产物头注是成对反斜杠、`__name__ = 'main'`、`__file__ = '<真路径>'`"
            "（探针 .fist-loop-20260927/fix_r5_snap/probe_project_identity.py）",
            "lint：cypy_hook/hook.py 违例 122→116（只减不增），"
            "cypyc/project/project_compiler.py 本趟新增 0 条（既存 12 条是环内他趟留下的），"
            "锁文件新增行 0 违例；产品码只做定点改动，未整档重排",
            "BUG-90 的两条既有锁（hook 无路径不伪造 / 有路径真身份）与新增两条同档跑过：7 passed",
        ],
        "style_note": "三个产品文件在 HEAD 就非 black-clean；black 想重排的锁文件 274/424 行是"
        "本轮他趟留下的既存形，本趟未顺手改",
    }
    if lane["lane"] in names:
        print(json.dumps({"refuse": [f"车道已存在：{names}"]}, ensure_ascii=False))
        return 1
    missing = [f for f in lane["files_reported"] if not (HERE.parent / f).exists()]
    if missing:
        print(json.dumps({"refuse": [f"自报的文件盘上没有：{missing}"]}, ensure_ascii=False))
        return 1
    doc["lanes"].append(lane)
    LANES.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "lanes": [x["lane"] for x in doc["lanes"]],
                "files_this_lane": len(lane["files_reported"]),
                "verbatim_lines": len(lane["verbatim"]),
                "cards": lane["cards"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    main()
