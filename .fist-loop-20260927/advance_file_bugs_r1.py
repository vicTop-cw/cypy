"""R1-推进：把两条**静默型**缺口入账（report_bug），解析型缺口不入账只转结。

口径（写死在这里，免得后面替自己找理由）：
 - `gap-parse`（解析就报错）= 文档声明了但没实现，**失败是显式的** ⇒ 属功能缺失，交转结清单，
   不占 bug 号（历史教训：把「覆盖少/未实现」当缺陷上报，一轮里被撤回 5 条）；
 - `gap-silent`（rc=0 但产物是废码/丢语义）= 用户拿到"看起来成功"的错结果 ⇒ 真缺陷，入账。

证据都指向可复跑件 `.fist-loop-20260927/advance_verify_r1.json`（每条候选带 CLI rc、
产物路径、文档行号与成对对照），文案里的引用一律用「」，不嵌 ASCII 双引号。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

D44 = """调用面实测（`.fist-loop-20260927/advance_verify_r1.json` 候选 #3，可复跑 `advance_verify_r1.py`）：

  SYNTAX/06d-builtin-magic-traits.md:49 在 struct 里声明了 @staticmethod，
  最小用例 `struct Point: x: int` + `@staticmethod def origin() -> Point` 走
  `python -m cypyc transpile` 得到 rc=0 与「[OK] Transpiled successfully」，
  但产物是 `cdef class Point:` 里的

      @staticmethod
      def origin(self):
          return Point(x=0)

  ⇒ 声明是无参静态方法，产物却保留 self（Cython 会照编译过去，调用 Point.origin() 时 TypeError）。
  同一份生成器在 class 路径上是对的，只有 struct 路径把 self 注进去：
  cypyc/codegen/cython_generator.py:2267 给 struct 方法整体置 is_struct_method=True，
  而 _visit 的签名装配只看这个标志，不看装饰器。

为什么这比解析报错严重：CLI 的成功横幅与产物文件都在，用户看不出任何异常。
判据面（本单的 want/neg 成对对照在 advance_verify_r1.py 的 match() 里）用的是
「产物里有没有 `def origin()` 空参形状」，而不是「产物里有没有 staticmethod 字样」——
后者第一版就恒绿了（产物确实含 @staticmethod），是它自己的对照把这轮打回的。

修法（交修复轮）：struct 方法签名装配处读取 FuncDef 的装饰器，遇 staticmethod/classmethod 不注 self；
改完须重跑 25 份端到端基准（struct 方法在 demo 里用得多，产物面会变）。"""

D45 = """调用面实测（`.fist-loop-20260927/advance_verify_r1.json` 候选 #4，可复跑）：

  SYNTAX/06d-builtin-magic-traits.md:53 声明「__implicit_default__ 提供隐式默认值填充，
  当参数未提供时自动使用」，并给出 `def process(data: str, cfg: Config = __implicit_default__)`。
  同形状最小用例 transpile rc=0，产物是

      def process(cfg=__implicit_default__):

  ⇒ 默认值是一个**裸名字**，模块作用域里没有这个符号（它只作为类方法存在一次，且签名还错保留 self），
  Python/Cython 求值默认参数是在 def 执行时 ⇒ import 该模块即 NameError。文档承诺的
  「未提供参数时自动用隐式默认填充」在产物里没有任何等价的填充逻辑。

同上一条的判据口径：want 是「产物里出现 __implicit_default__ 的**调用形**」（`(...)`），
neg 是修复前的裸名形状 ⇒ 不会因为产物里出现该字样就恒绿。

修法（交修复轮）：把 `= __implicit_default__` 脱糖成 `Type.__implicit_default__()` 调用，
并把 #44 的 self 问题一并解决（否则调用点仍错）。两者同文件同域，建议修复轮一起做。"""

# tools/list 实测：report_bug 的必填是 summary/detail/severity/project_dir/reported_by/now
# （不是 title——上一轮的账本形状记的是 title，参数名也会过期，见 gotcha #57 同一类）。
ITEMS = [
    ("struct 里的 @staticmethod 生成时仍注入 self，产物签名与声明不符且调用必炸", D44),
    (
        "struct 的 __implicit_default__ 默认值生成成裸名字，导入即 NameError，声明的自动填充没有落地",
        D45,
    ),
]


def main() -> int:
    c = lfist_lib.Client(timeout=120)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    c._recv(1, 60)
    out = []
    for title, detail in ITEMS:
        r = c.call(
            "report_bug",
            {
                "summary": title,
                "detail": detail,
                "severity": "high",
                "project_dir": ".",
                "reported_by": "cypy-advancer",
                "now": lfist_lib.utc_now(),
            },
        )
        out.append({"title": title[:40], "resp": r})
        print(json.dumps({"filed": r.get("id") or r, "title": title[:60]}, ensure_ascii=False))
    bl = c.call("bug_list", {"project_dir": ".", "limit": 60, "now": lfist_lib.utc_now()})
    rows = bl.get("bugs") or bl.get("items") or bl
    ids = []
    if isinstance(rows, list):
        for b in rows:
            head = b.get("summary") or b.get("title") or ""
            ids.append(f"{b.get('id')}|{b.get('status')}|{head[:46]}")
    print(
        json.dumps(
            {"bug_list_tail": ids[-8:], "filed_count": len(out)}, ensure_ascii=False, indent=1
        )
    )
    (HERE / "advance_file_bugs_r1.json").write_text(
        json.dumps({"filed": out, "bug_list_tail": ids}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
