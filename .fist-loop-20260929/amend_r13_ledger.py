r"""R13 的台账腿：给 BUG-137/138/139 各追一段 `### FIXED(...)`，并给 BUG-136 追一段 `### 改判(...)`。

沿用 R12 那份的门（段落戳用写盘瞬间的 UTC、派生数必须逐字落进段落、我要写的那段必须逐字落盘、
`--refresh` 只回收自己那段、抬头与 summary 一字不改），两处按本轮事实改动：

 · 本轮段落里**有合法花括号**（`{"a": "b"}` 这种源码片段、代码里的元组字面量），
   所以 R12 那条「本件段落的 `[{}]` 计数为 0」的脏检必须换成「未插值占位 `\{标识符\}` 为 0」——
   同一形状的过宽针在 `file_r13_container_bugs.py` 上已经拦掉过一条正常正文，别再让它挡路；
 · `### 改判(...)` 不是关闭标记：BUG-136 的 (f)（带界别名形态）与 (d)（类型实参存在性）仍未合上，
   所以它必须继续算开口，只在正文里改正机制并指向 137/138/139 ⇒ 开口数只随 3 段 FIXED 变化。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
CORPUS = ROOT / "corpus" / "cypy.container.elements.json"
LOCKS_FILE = ROOT / "tests" / "test_container_elements_r13.py"
PROBE_BEFORE = HERE / "logs" / "r13_alias_paired_a1.json"
PROBE_AFTER = HERE / "logs" / "r13_container_probe_b2.json"
FIXED_MARKS = ("FIXED(R13 容器元素位判定", "FIXED(R13 别名展开到底", "FIXED(R13 联合形态别名代入")
AMEND_MARK = "改判(R13 机制更正"
CLOSING = r"(?m)^### (FIXED|DUPLICATE)"


def read_json(p: Path) -> dict:
    if not p.exists():
        raise SystemExit(f"证据件缺失：{p.name} ⇒ 不落盘（派生数不许凭记忆）")
    return json.loads(p.read_text(encoding="utf-8"))


def derived() -> dict:
    spec = read_json(CORPUS)
    locks = LOCKS_FILE.read_text(encoding="utf-8")
    before, after = read_json(PROBE_BEFORE), read_json(PROBE_AFTER)
    # 探针件里混着"本来就该静默"的正向对照（`A03_alias_ok`/`A08_alias_in_param` 等），
    # 把它们算进"仍静默 ⇒ 属别单"是给台账掺水 ⇒ 判定集合从探针件反解，不在这份里手抄。
    import importlib.util

    pspec = importlib.util.spec_from_file_location(
        "probe_r13_container", HERE / "probe_r13_container.py"
    )
    probe = importlib.util.module_from_spec(pspec)
    pspec.loader.exec_module(probe)
    should_be_green = set(probe.MUST_GREEN)
    silent_before = {k for k, v in before.items() if v["stage"] == "ok" and v["n"] == 0}
    flipped = sorted(
        k for k in silent_before if k in after and after[k]["stage"] == "ok" and after[k]["n"] > 0
    )
    still = sorted(
        k
        for k in silent_before
        if k in after
        and after[k]["stage"] == "ok"
        and after[k]["n"] == 0
        and k not in should_be_green
    )
    kept_green = sorted(
        k for k in should_be_green if k in silent_before and k in after and after[k]["n"] == 0
    )
    tc_src = (ROOT / "cypyc" / "analyzer" / "type_checker.py").read_text(encoding="utf-8")
    let_line = next(
        i
        for i, ln in enumerate(tc_src.splitlines(), 1)
        if "self._check_container_elements(declared_type" in ln
    )
    return {
        "CASES": len(spec["tests"]),
        "FP": spec["fingerprint"],
        "LOCKS": len(re.findall(r"(?m)^def test_", locks)),
        "PROBE_CASES": len(after),
        "FLIPPED": len(flipped),
        "FLIPPED_LIST": "、".join(f"`{k}`" for k in flipped),
        "STILL_SILENT": len(still),
        "STILL_LIST": "、".join(f"`{k}`" for k in still),
        "KEPT_GREEN": len(kept_green),
        "LET_LINE": let_line,
        "SPECS": len(list((ROOT / "corpus").glob("*.json"))),
    }


D = derived()

SECTIONS = [
    {
        "bid": "137",
        "mark": FIXED_MARKS[0],
        "body": """
- 修法：把「同名容器即放行」收窄成它自己注释点名的占位形态。新增三个助手在
  `cypyc/analyzer/type_checker.py`：`_slot_incompatible`（单位纯判定）／`_first_bad_element`
  （逐位扫描）／`_check_container_elements`（唯一记帐出口，整串去重），
  赋值位 `:{LET_LINE}` 与返回位（`_visit_ReturnStmt` 的 `target_name == value_type.name` 那支）
  各接一行 ⇒ 两边走同一份判定，不许一边判一边不判。
- 收紧的是实现宽于意图：两条分支的原注释只说「空容器构造器 / 嵌套无参 / 含 None-object 参数」该放行，
  实际把元素类型不同也吞了。四类占位在本轮全部复验仍为 0 诊断（Ω-spec `expected/errors=0` 半边）。
- 保守集（规则 5）是刻意的：只有两侧元素名都落在闭合标量表（`bool int long float double char str bytes`）
  才允许报「名字不同即不兼容」；用户类/trait/subtype 一律放行 ⇒ `list<Speak> = [Dog()]` 至今静默，
  这一面钉在 `tests/test_container_elements_r13.py::test_trait_element_is_lenient_by_design`
  而不是删掉不写。`dict` 键值位不生效（字典字面量不推断类型，规则 6）。
- 判据：新增 Ω-spec `corpus/cypy.container.elements.json`（{CASES} 对，指纹 `{FP}`，
  生成件 `.fist-loop-20260929/make_corpus_r13.py` 只封自己这份并证明其余 {SPECS} 份字节未变）；
  回归锁 `tests/test_container_elements_r13.py`（{LOCKS} 支，含「两个调用点各一根源码针」
  与「手册闭合标量表 ↔ 代码常量」双向对表）。台账地板同批上调 FLOOR_SPECS 6→{SPECS}、FLOOR_CASES 123→151。
- 半径实测：`.fist-loop-20260929/probe_r13_container.py`（{PROBE_CASES} 形，自带 must_be_red /
  must_stay_green / 不许 crash 三组门）改动前后各跑一次，转红 {FLIPPED} 形（{FLIPPED_LIST}），
  仍静默 {STILL_SILENT} 形（{STILL_LIST}）⇒ 这几条是别单（BUG-122 类型实参存在性、
  dict 字面量不推断、`_type_in_union` 只比成员名），不冒充本单关闭；
  另有 {KEPT_GREEN} 形是**按设计该静默**的正向对照（`A03_alias_ok`/`A08_alias_in_param` 这类），
  与上面的"仍静默"分栏计，不混进同一句话里凑数。
- 手册：`SYNTAX/02-type-annotations.md` 新增「容器元素位判定（R13 补）」规则 1-6，
  规则 4/5/6 明写**不判的一面**，与既往轮「先写承诺再动实现」同形。
""",
    },
    {
        "bid": "138",
        "mark": FIXED_MARKS[1],
        "body": """
- 修法：`_substitute_type` 增加 `_expand_nested_alias` —— 别名右端里出现的**其它别名**展开到底，
  带 `_alias_stack` 名链守卫：`type Loop<T> = Loop<T>` 这类自指停在原地返回 `Loop[int]`，
  不递归成 RecursionError；实参个数不符仍交回 `_substitute_generic_alias` 既有的 arity 诊断（不叠账）。
- 这一单的原始形态是**假阳性**：`type Triple<T> = Pair<Pair<T>>` 之后
  `let ok: Triple<int> = ((1, 2), (3, 4))` 被判 `Type mismatch: expected Pair[Pair[int]], got tuple<…>`。
  身份隔离见 `.fist-loop-20260929/logs/r13_nested_alias_fp_a1.json`：把本轮新加的容器判定
  monkeypatch 成空操作再跑同一形状，诊断逐字不变 ⇒ 假阳性早于本轮改动存在，不是新 bug 冒充旧账。
- 验证：`N01_nested_alias_ok` 由红转绿（正确程序不再被拒），
  `N02_nested_alias_wrong` 由粗报文转成精确的 `Element 2 type mismatch: expected int, got str`，
  `N03_scalar_alias_in_alias`（标量别名嵌在别名右端里）与 `N04_self_alias_no_hang` 同批进锁
  （`tests/test_container_elements_r13.py` 的 4 支 nested/loop 用例）。
- 未随本单关闭：`type Num<T: int | float> = …` 这种**带界别名**仍解析失败
  （`Expected IDENTIFIER, got COLON`），留在 BUG-136 的 (f) 面，不在这里冒充已修。
""",
    },
    {
        "bid": "139",
        "mark": FIXED_MARKS[2],
        "body": """
- 修法：`_substitute_type` 补 `UnionType` 分支，与 `_get_type_from_node` 的联合分支同形
  （`Type("object", union_members=[…])`），成员先各自代入再交给既有 `_type_in_union` ⇒
  不再出现「代入返回 None ⇒ 声明类型为空 ⇒ 任意值登记通过」。
- 影响面不是纸上的：`examples/demos/data_structures/type_alias_demo.cypy:34-36` 三份泛型别名
  （`Optional<T> = T | None`、`ListOrSet<T> = list<T> | set<T>`）过去整条不判，
  :49-50 两处使用是「因为什么都不判所以通过」；本轮之后 `Maybe<int> = "s"` 报
  `Type mismatch: expected Union[int, None], got str`，而 demo 自己的 `ListOrSet<int> = [1,2,3]`
  仍 0 诊断（成员名对上即放行）。
- 未随本单关闭（原样入账不粉饰）：`ListOrSet<int> = ["s"]` **仍静默** ——
  `_type_in_union` 只比成员 `.name`，元素位不参与判定；这条要动 `_type_in_union` 的语义，
  半径明显大于本单其余面，钉在
  `tests/test_container_elements_r13.py::test_union_member_element_positions_are_still_open`
  等扩面那天先红。BUG-122（类型实参不判存在性）同批未合。
- 判据：Ω-spec `corpus/cypy.container.elements.json` 的 3 支 Maybe/联合成员用例（正反例齐）
  + 回归锁 4 支（`test_union_shaped_alias_*` / `test_union_of_containers_*`）。
""",
    },
    {
        "bid": "136",
        "mark": AMEND_MARK,
        "body": """
- 机制更正（本单抬头 `OPEN` 与正文一字不改，改判只追在这里）：正文「机制」栏写的
  「别名展开时不建绑定 ⇒ `T` 没有替换点 ⇒ 参数从不代入」**是错的**。实测反证三条：
  ① `Result<int, int>` 报 `Type alias 'Result' expects 1 generic parameter(s), but got 2`
  ⇒ 参数表在读；② `type My = int` + `let bad: My = "s"` 报 `Type mismatch: expected int, got str`
  ⇒ 非泛型别名会展开；③ `type Triple<T> = Pair<Pair<T>>` 的错字面量本来就报类型不符
  ⇒ 泛型别名代入了一层。真正让 (a)(b)(c) 静默的是**容器元素位整条不判**（BUG-137，
  非别名路径的 `let bad: tuple<bool, int> = (True, "x")` 同样 errors=0 ⇒ 与别名无关），
  加上别名套别名没展开（BUG-138）与联合形态别名不代入（BUG-139）。
- 逐形改判：(a)(b)(c) 关闭面转给 BUG-137/138（本轮实测已红）；(d) 类型实参不存在
  ⇒ 与 BUG-122 同形，仍静默、不重复入账；(e) 裸用 `Pair` 得 0 诊断**是既有测试钉住的行为**
  （`tests/test_new_features_boundary.py:167 test_generic_type_alias_without_params` 断言 errors==0），
  不是本单可主张的缺陷 —— 半径实测时才发现，记在这里免得下一轮又当新 bug 报；
  (f) 带界别名 `type Num<T: int | float> = …` 解析失败 ⇒ **本单唯一仍开的面**。
- 取证件：`.fist-loop-20260929/probe_r13_container.py`（成对形状 + 三组自门）与
  `logs/r13_alias_paired_a1.json`（改动前基线）、`logs/r13_container_probe_b2.json`（改动后）。
- 账面一致性：`SYNTAX_IMPLEMENTATION_STATUS.md` 的 02/12 两行随本轮改写，
  「✅ 完整/无」不再覆盖别名面。
""",
    },
]


def counts(text: str) -> dict:
    blocks = [b for b in re.split(r"(?m)^(?=## BUG-)", text) if b.startswith("## BUG-")]
    open_blocks = [b for b in blocks if not re.search(CLOSING, b)]
    return {
        "headers": len(blocks),
        "open": len(open_blocks),
        "fixed": len(re.findall(r"(?m)^### FIXED", text)),
        "amend": len(re.findall(r"(?m)^### 改判", text)),
    }


def build(seg_mark: str, body: str, ts: str) -> str:
    seg = "\n### " + seg_mark + " " + ts + "）— 追加留档（本单正文与标题行一字未改）\n" + body
    seg = seg.format(mark=seg_mark, ts=ts, **D)
    residue = re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", seg)
    stamps = re.findall(r"(?m)^### " + re.escape(seg_mark) + r" (\S+?)）", seg)
    if (
        residue
        or len(stamps) != 1
        or not re.fullmatch(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamps[0])
    ):
        raise SystemExit(f"段落不合格 ⇒ 不落盘：{seg_mark} residue={residue} stamps={stamps}")
    for key in (
        "CASES",
        "FP",
        "LOCKS",
        "PROBE_CASES",
        "FLIPPED",
        "STILL_SILENT",
        "KEPT_GREEN",
        "SPECS",
        "LET_LINE",
    ):
        want = f"{D[key]}" if key != "FP" else D["FP"]
        if key in body and want not in seg:
            raise SystemExit(f"派生数没落进段落（{seg_mark} 查 {key}={want!r}）⇒ 不落盘")
    return seg


def main() -> int:
    refresh = "--refresh" in sys.argv
    src = LEDGER.read_text(encoding="utf-8")
    before = counts(src)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, touched = src, []
    for item in SECTIONS:
        seg = build(item["mark"], item["body"], ts).rstrip("\n") + "\n"
        head = re.search(r"(?ms)^## BUG-" + item["bid"] + r" .*?(?=\n## BUG-|\Z)", out)
        if not head:
            raise SystemExit(f"账上查无 BUG-{item['bid']} ⇒ 先取号再写台账，拒绝凭空插段")
        block = head.group(0)
        pat = re.compile(r"(?ms)(?<=\n)### " + re.escape(item["mark"]) + r".*?(?=\n## BUG-|\Z)")
        already = pat.search(block)
        if already and not refresh:
            print(f"SKIP BUG-{item['bid']}：本件那段已在账上（覆盖用 --refresh）")
            continue
        if already:
            if item["mark"] not in block[already.start() : already.end()]:
                raise SystemExit(f"BUG-{item['bid']} 要回收的区段不含本件标记 ⇒ 停手不动账")
            new_block = block[: already.start()] + seg + block[already.end() :]
        else:
            new_block = block.rstrip("\n") + "\n" + seg
        out = out.replace(block, new_block, 1)
        touched.append(item["bid"])
    if not touched:
        print("CONCLUSION touched=0（已在账，幂等）")
        return 0
    LEDGER.with_name("bugs.md.pre_r13_ledger").write_text(src, encoding="utf-8", newline="\n")
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    after_text = tmp.read_text(encoding="utf-8")
    after = counts(after_text)
    keep = []
    for item in SECTIONS:
        old = re.search(r"(?ms)^## BUG-" + item["bid"] + r" .*?(?=\n## BUG-|\Z)", src).group(0)
        keep += [
            ln for ln in old.splitlines() if ln.startswith("## BUG-") or ln.startswith("- summary:")
        ]
    preserved = all(k in after_text for k in keep)
    n_fixed = len([t for t in touched if t != "136"])
    n_amend = len([t for t in touched if t == "136"])
    delta = (
        {"headers": 0, "open": 0, "fixed": 0, "amend": 0}
        if refresh
        else {"headers": 0, "open": -n_fixed, "fixed": n_fixed, "amend": n_amend}
    )
    landed = sum(
        after_text.count(build(i["mark"], i["body"], ts).rstrip("\n"))
        for i in SECTIONS
        if i["bid"] in touched
    )
    own_stamps = [
        s
        for i in SECTIONS
        for s in re.findall(r"(?m)^### " + re.escape(i["mark"]) + r" (\S+?)）", after_text)
    ]
    own_residue = [
        m
        for m in re.findall(
            r"(?m)^.*\{(?:CASES|FP|LOCKS|PROBE_CASES|FLIPPED|STILL_SILENT|STILL_LIST|KEPT_GREEN|SPECS|LET_LINE|CONS_SRC|CONS_DECL)\}.*$",
            after_text,
        )
    ]
    # 整档扫描只当**读数**印出来，不当门：R12 的教训是拿别轮的坏戳/占位当本件的门，
    # 会让本件永红且看不见自己合不合格。本件合格性由 `build()`（占位为 0、戳唯一且形状合法）
    # 与下面的 `landed`/`own_stamps` 逐段认领。
    whole = {
        "residue_lines": len(own_residue),
        "dblstamp_lines": len(
            re.findall(r"(?m)^.*20\d\d-\d\d-\d\dT20\d\d-\d\d-\d\dT.*$", after_text)
        ),
    }
    ok = (
        after["headers"] == before["headers"] + delta["headers"]
        and after["open"] == before["open"] + delta["open"]
        and after["fixed"] == before["fixed"] + delta["fixed"]
        and after["amend"] == before["amend"] + (0 if refresh else n_amend)
        and preserved
        and landed == len(touched)
        and len(own_stamps) == len(touched)
    )
    print("LANDED", landed, "OF", len(touched), "SWEEP_WHOLE_LEDGER", whole)
    print("BEFORE", before, "AFTER", after, "TOUCHED", touched, "SUMMARY_KEPT", preserved)
    if not ok:
        raise SystemExit("自证不符 ⇒ 不落盘，tmp 与备份留在 .fist-loop-20260929/ 待查")
    tmp.replace(LEDGER)
    print(
        f"CONCLUSION r13_ledger touched={len(touched)} ids={touched} "
        f"headers={after['headers']} open={after['open']} fixed={after['fixed']} "
        f"amend={after['amend']} refresh={refresh} derived=D"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
