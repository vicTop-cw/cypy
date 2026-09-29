#!/usr/bin/env python3
"""Seventh-pass intake: 15 confirmed defects from the three discovery lanes.

Lanes: (a) my own review of cypyc/utils + the marker/pattern面, (b) bridge/hook/project/cli
candidates re-proven by repro_pass7.py, (c) parser/lexer/incremental candidates re-proven by
repro_pass7b.py, (d) codegen/analyzer candidates re-proven by repro_pass7c.py plus the live
A15/A14 probes. A candidate the probes could not reproduce (match-pattern arity counting
methods as fields) is NOT filed here -- it is carried as a lead in the report.

Same ledger contract as passes 1-6: server cwd is the Cypy root, project_dir=".",
publish_task=True so each entry also publishes its fix ticket.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

FINDINGS = [
 {"sev": "high", "summary": "[lexer-truncation] cypyc/parser/lexer.py:538 三反引号判定用 2 字符切片 "
  "`source[pos:pos+2]==\"``\"` 却连推 3 个字符，源文件里任意一对游离反引号会把其后整段吞成一个 "
  "BACKTICK_BLOCK，其后的定义全部消失且零报错",
  "detail": "现象: 源码 `def a() -> int: return 1` + 一行 `` `` `` + `def b() ...` → 词法尾部只剩 "
  "['BACKTICK_BLOCK','EOF']，生成的 Cython 里只有 def a，def b 整段蒸发，parse 不报任何错（repro_pass7b "
  "lex_backtick）。机制: lexer.py:538 判 `self.source[self.pos:self.pos+2] == \"``\"`（只看了两个反引号），"
  "随后 :542-544 连 `_advance()` 三次并按 ``` 或 EOF 找终止符，即判定条件与消费长度差一个字符。"
  "定性: [真缺陷] —— 静默截断用户代码，不是设计：三反引号宏捕获的口径写在同文件注释里（:537 "
  "「检查是否是三反引号」）。危害面: 用户少打一个反引号 ⇒ 后半份文件不编译且没有任何诊断，"
  "与已修的 BUG-3/8/10 同族（丢代码不报错）。建议: 判定改为 `source[pos:pos+3] == \"```\"`，"
  "不满足时按单反引号分支处理并让 parse 自然报错；不动三反引号块的既有语义。"},

 {"sev": "high", "summary": "[parser-decorators] cypyc/parser/parser.py:1375 成员级 `decorators = []` "
  "重绑了 :1326 形参持有的结构体自身装饰器列表，`@value struct` 只要含一个被装饰的成员就丢掉 @value，"
  "并把成员装饰器挂到 struct 上",
  "detail": "现象（repro 实跑）: `@value struct Config:` 只有一个 `let w: int` 时生成物含 `__eq__`；"
  "再加一个 `@python def label()` 成员，生成物里 `__eq__` 消失（值语义没了），而 StructDef.decorators "
  "变成 `[Decorator(line=3, col=13)]` —— 那是成员自己的 `@python`。机制: parser.py:1326 "
  "`_parse_struct_def(self, decorators=None)` 的形参装着 struct 级装饰器，:1375 在成员循环里 "
  "`decorators = []` 就地重绑同名局部变量，:1380 用它给 method 传参，:1407 又把同一个变量交给 "
  "StructDef。定性: [真缺陷]，与 SYNTAX/05-struct.md 的 @value 承诺直接冲突（codegen 侧 "
  "cython_generator.py:2122-2131 明确按 decorators 决定是否 `_generate_value_methods`）。"
  "危害面: 结构体等值/哈希/repr 语义随「有没有装饰方法」而变，用户无从预期。建议: 成员装饰器改用独立"
  "局部名 `member_decorators`，struct 级 `decorators` 不被覆写；本修复让实现回到冻结文档口径，"
  "不改语言语义。"},

 {"sev": "medium", "summary": "[diagnostics] cypyc/project/project_compiler.py:666 `_pick_extension` "
  "名字全不匹配时 `return sorted(candidates)[0]`，把别的模块（或历史残留）的 .pyd 当成本次该模块的产物回报，"
  "「No .pyd file generated」永不触发",
  "detail": "现象（repro 实跑）: `_pick_extension(['<tmp>/other_module.cp313-win_amd64.pyd'], \"mymod\", "
  "<tmp>)` 返回那个 foreign 路径而不是 None。机制: :658-665 的挑选循环只在 base 名等于/前缀于 stem 时返回，"
  "全部不匹配时兜底 `sorted(candidates)[0]`。而本函数自己的 docstring（:643-648）写着旧实现取 `pyd_files[0]` "
  "的毛病是「遍历顺序决定结果，目录里残留的历史产物也可能被当成本次产物回报」——兜底行把这条毛病原地保留了下来。"
  "定性: [真缺陷]（假成功/错产物，同 BUG-1/BUG-7 一族）。兄弟口径见 tests/test_hook.py:126 对同类挑选断言 "
  "assertIsNone。危害面: `cypyc build` 报出 `mymod -> other_module.pyd`，后续加载导入到错误模块，"
  "或把「没产出」伪装成「产出了」。建议: 全不匹配时返回 None，让上层走既有的「No .pyd file generated」分支。"},

 {"sev": "high", "summary": "[cache-invalidation] cypyc/incremental/incremental_manager.py:311-320 "
  "「检查导入模块是否变化」只看 `is_cached()`（缓存条目存不存在），从不比对依赖的 file_hash，"
  "改了被 import 的 .cypy 仍判缓存有效并复用陈旧 .pyd",
  "detail": "现象: `_check_imported_modules_changed` 注释写「检查模块的缓存是否失效」，实现是 "
  "`if not self.is_cached(module_file): return True`（:318）——条目存在即视为没失效。机制: 依赖模块自己的"
  "缓存在它被重编译时会被覆盖写回，所以对「 importer 未变、依赖已变」这一最常见形态，该函数恒返回 False，"
  "cypy_hook/hook.py:333 的 `check_cache_validity` 据此报「缓存完全有效」、跳过编译、导入旧二进制。"
  "定性: [真缺陷]，增量正确性缺陷（本轮扫描面点名的 incremental 缓存失效高发区）。危害面: 用户改 A.py 后"
  "导入它的 B 仍跑旧代码，必须手工清缓存才生效——最难排查的一类。建议: 取依赖条目的 file_hash 与该文件"
  "当前摘要比对（同文件 :248 已有 `file_hash` 比对口径可复用），不相等即判定 changed。"},

 {"sev": "medium", "summary": "[codegen-directives] cypyc/codegen/cython_generator.py:1287 "
  "`_ensure_owned_import` 用 `output.insert(0, ...)` 把 pointer import 插到整段 `# cython:` 指令之前，"
  "而本文件 :299 的注释规定指令必须在最顶部否则被忽略",
  "detail": "现象（repro 实跑）: 含 `owned p = malloc(8)` 的源生成的文件第 1 行是 "
  "`from cypy_bridge.pointer import ...`，`# cython: language_level=3 / boundscheck=False / "
  "wraparound=False / nonecheck=False` 被挤到第 2-6 行；同文档字符串也不再是首语句（`__doc__` 变 None）。"
  "机制: :1285-1287 无条件 insert(0)。定性: [真缺陷]——判据依据是文件自己的注释 :299"
  "「Cython 编译指令必须位于文件最顶部（在任何语句/文档字符串之前），否则会被忽略」。"
  "危害面: 一处 owned 绑定就让整份产物的指令集失效，边界检查/回绕检查行为随是否用过 owned 而不同，"
  "且文档字符串丢失。建议: 插入点定位到「开头连续的注释/指令行块之后」，不再插到第 0 行。"},

 {"sev": "medium", "summary": "[comptime] cypyc/analyzer/comptime_evaluator.py:455-461 `_get_func_name` "
  "对 `x.upper()` 这类 Attribute 调用退回 `str(node)`（得到 \"Attribute(line=.., col=..)\"），"
  "于是 :188-276 整张字符串/列表方法表永不命中，comptime 语句静默消失",
  "detail": "机制: evaluate() 在 Call 分支（:158-161）用 `_get_func_name(node.func)` 查表；func 是 Attribute "
  "时三个分支全不中（不是 Name、没有 .id），落到 :461 `return str(func_node)`，返回一个带行列号的节点 repr，"
  "永远不可能等于 `self.functions`/`builtin_funcs` 的键 ⇒ `_evaluate_attribute_access`（模块 docstring 规则 "
  "5-6 承诺的 .upper()/.append()/.split() 等）整段不可达，evaluate_comptime 返回 None。"
  "后果: codegen（cython_generator.py:2395）只留下 `# comptime: 'abc'.upper()` 注释，语句从产物中消失；"
  "若它是某函数体唯一语句，生成出的 def 体只剩注释 ⇒ Cython/CPython 报 expected an indented block。"
  "定性: [真缺陷]（计算结果被静默丢弃，与 BUG-8/11 同族）。建议: Attribute 取 `func.attr` 作为函数名并"
  "保留接收者求值，使既有方法表可达；查不到时按既有的「无法求值」路径给诊断而非静默。"},

 {"sev": "medium", "summary": "[type-checker] cypyc/analyzer/type_checker.py:432（同族 :1283、:2008）"
  "用 `getattr(stmt.for_type,'id',str(stmt.for_type))` 取 impl 的目标类型名，`impl Show for Box<T>` 注册成 "
  "\"GenericType(line=5, col=15)\" 这种节点 repr，codegen 侧 :482-486 却正确剥掉泛型 —— 两份 trait 登记表口径分叉",
  "detail": "现象（repro 实跑）: 源 `impl Show for Box<T>` 使 `tc.trait_impls == {'Show': "
  "['GenericType(line=5, col=15)']}`。机制: GenericType 节点带 `.name` 而没有 `.id`，getattr 默认分支 "
  "`str(node)` 把整颗节点 repr 当成类型名登记。定性: [真缺陷]。危害面: 为泛型类型写的 trait 实现在约束检查里"
  "永远匹配不上 ⇒ 误报 `Generic constraint violation: type ... does not implement trait ...`；"
  "同文件另外两处（:1283、:2008）是同一写法，examples/demos/traits_duck/trait_basic.cypy:104 也在产垃圾键。"
  "建议: 统一按「Name→.id / GenericType→.name / 其余→getattr 'name' 兜底」取名字，"
  "与 cython_generator.py:482-486 的既有剥泛型口径对齐（只收紧垃圾键，不改判定规则）。"},

 {"sev": "low", "summary": "[lexer] cypyc/parser/lexer.py:651-652 f-string 前缀判定集合是 "
  "(`\"`, `'`, f, F)，注释 :650 声称支持 f/F/rf/fr，实际 `fr\"...\"` 因第二字符 'r' 不在集合内被拆成 "
  "IDENTIFIER `fr` + STRING，`rf\"...\"` 却正常",
  "detail": "现象: `let s = fr\"{x}\"` → `Expected NEWLINE, got STRING`；同义写法 `rf\"{x}\"` 解析通过。"
  "机制: :652 `if char in ('f','F','r','R') and self._peek_ahead(1) in ('\"',\"'\",'f','F')` —— "
  "'r'/'R' 作为第二字符未被接受，而 :654 的组合前缀分支只处理 `rf` 不处理 `fr`。"
  "定性: [真缺陷]（注释/文档声称支持的形态实际不支持，且报错点离因由很远）。建议: 第二字符集合补 'r','R' "
  "并按两字符实际组合归一 prefix，使 fr/rf 同权。"},

 {"sev": "medium", "summary": "[pointer] cypy_bridge/pointer.py:322 `addr()` 先判 `hasattr(obj,'value')`，"
  "而每个 c_void_p 都有 `.value`，:327 的 `elif isinstance(obj, ctypes.c_void_p): return obj.value` 成死代码 —— "
  "对空指针也返回非零堆地址",
  "detail": "现象（repro 实跑）: `addr(ctypes.c_void_p(4096))` 返回 2081110748568（那个 ctypes 盒子自己的地址），"
  "不是 4096；`addr(ctypes.c_void_p(0))` 返回非零 ⇒ 用户拿它判 NULL 永远不成立。机制: 分支次序问题，"
  "c_void_p 被前一个 hasattr 分支吃掉。定性: [真缺陷]。危害面: 指针语义错误 + 空指针检查失效"
  "（本模块 docstring 对该分支的意图就是「返回指针的值」）。建议: 把 `isinstance(obj, c_void_p)` 提到 "
  "hasattr 之前；`c_int` 等标量仍走 addressof 不变（现有 tests/test_bridge_library.py:332 只断言 int 类型，不受影响）。"},

 {"sev": "medium", "summary": "[cache] cypy_hook/hook.py:1020-1024 `clear_cache()` 无参分支走 "
  "`os.walk(os.getcwd())` 却要求 `os.path.dirname(root)==\"__pycache__\"`，绝对路径下永不相等，"
  "删了 0 个文件仍由 cli.py:384 打印 [OK] cache cleared",
  "detail": "现象（repro 实跑）: 临时目录下造 `__pycache__/cypy/manifest.json` 后 chdir 调用 "
  "`CypyCacheManager().clear_cache()`，文件原样存活；walk 到的 root 是绝对路径，"
  "`os.path.dirname(root)` 是 `<tmp>\\__pycache__` 而非 `__pycache__`。机制: 判据拿整段目录路径比basename。"
  "定性: [真缺陷]（假成功，且与同文件 :1007-1016 的单文件分支行为不一致）。兄弟实现 "
  "compiler.py:3680 的 BridgeCacheManager 遍历是对的。危害面: 用户按文档清缓存后仍旧导入旧 .pyd。"
  "建议: 判据改 `os.path.basename(os.path.dirname(root))==\"__pycache__\"`，"
  "并把「清了几个文件」回报给调用方，0 个时不得报 [OK]。"},

 {"sev": "medium", "summary": "[encoding] cypy_bridge/compiler.py:3766 与 :3807 把生成的 .c 和 setup.py 用 "
  "`open(path,'w')` 按本地编码写盘（本机 cp936），含非 cp936 字符的源码直接 UnicodeEncodeError，"
  "读源码侧却是 encoding=\"utf-8\"",
  "detail": "现象（repro 子进程实测，未开 UTF-8 模式）: `preferred=cp936`，"
  "`open(p,'w').write('/* \\u0e01 */')` → `UnicodeEncodeError: 'gbk' codec can't encode character '\\u0e01'`。"
  "机制: 这两处是三包里仅有的不带 encoding 的文本写盘（其余全仓 pin utf-8），写出的字节随机器 ANSI 代码页变化；"
  "同一函数 :3819 还特意用 utf-8/replace 解子进程输出（注释原因就是 GBK）。定性: [真缺陷]。"
  "危害面: 同一份 .cypy 在不同代码页机器上产物字节不同（中文在 cp936 与 cp1252 机器上表现不一致），"
  "非本地字符直接编译失败；MSVC 收到的源编码与生成器假定不一致。建议: 两处补 `encoding=\"utf-8\"`，"
  "与读入侧统一。"},

 {"sev": "low", "summary": "[portability] cypy_bridge/compiler.py:3833 编译产物扫描只认 `endswith('.pyd')`，"
  "而 :3704-3707 的 `_detect_compiler` 明确支持 linux/gcc 与 darwin/clang，"
  "非 Windows 上即便编译成功也抛 \"Failed to find generated .pyd file\"",
  "detail": "机制: 产物发现循环只匹配 .pyd；同文件 :3683（BridgeCacheManager）已经在用 "
  "`.pyd`/`.so` 的口径，cypy_hook/hook.py:542 用 `sysconfig` 的 `extension_suffixes()`，"
  "project_compiler.py:624 用 (\".pyd\", \".so\", \".dll\") —— 四处三套口径。定性: [真缺陷]（跨平台假失败）。"
  "危害面: Linux/macOS 上 CCodeGenerator 这条路全量失败，错误信息还把用户指向「编译器没产出」。"
  "建议: 与兄弟站点统一为 `sysconfig.get_config_var('EXT_SUFFIX')` + (\".so\", \".dll\") 元组。"},

 {"sev": "low", "summary": "[hot-reload] cypyc/incremental/hot_reload.py:530 `set.union(*[...])` 在 "
  "results 为空（纯删除批次）时抛 TypeError，被 :535 的 except 打成 \"Callback error\"，"
  "用户回调其实一次都没跑",
  "detail": "机制: `set.union(...)` 是未绑定方法，空参数即 TypeError；异常落在把「合并结果 + 调用回调」"
  "整段包住的 try 里，:536 打印 `Callback error: <原始异常>`。定性: [真缺陷]。危害面: 删除文件的"
  "热重载批次里用户的 _on_reload 从不触发，而日志把矛头指向用户回调（本模块 API 用法，"
  "CLI `watch` 未传回调所以现场不易见）。建议: 改 `set().union(*[...])`，并把合并与回调调用拆开，"
  "使「回调报错」只可能来自回调本身。"},

 {"sev": "medium", "summary": "[reformat] cypyc/utils/indent_detector.py:30-34 detect() 观测到多种缩进宽度时"
  "一律取 4（没有取公因数），:56-58 再以 `// indent_size` 换算层数，2 空格风格源码经 normalize() 后 "
  "函数体被压到 0 列，块结构直接毁坏",
  "detail": "现象（repro 实跑）: 输入 2 空格缩进的 `def f(): / let a / if a: / let b`，"
  "`detect()` 报 ('spaces', 4)，`normalize()` 输出 `def f():\\nlet a = 1\\nif a:\\n    let b = 2` —— "
  "第一层体被削到 0 列（函数变空壳），第二层反而留在原地。定性: [真缺陷]：该类是本轮参数卡点名的"
  "「越界切片/算术边界」一族，且 `cypyc/utils/__init__.py:2` 把它作为包 API 导出。"
  "现状说明（不夸大本轮影响面）: 三包内暂无产品代码调用 normalize（同 BUG-6 的口径），"
  "现有 tests/test_boundary_comprehensive.py:530-584 只覆盖 tab 与 4 空格，非 4 空格风格是覆盖盲区。"
  "建议: detect() 取观测宽度的最大公约数（{2,4}→2、{3,6}→3、{4,8}→4），单值情形保持不变。"},

 {"sev": "low", "summary": "[cli-diagnostics] cypy_hook/hook.py:836 对可能为 None 的 "
  "`parsed_args.source` 直接 `os.path.isfile(...)`，`cypyc hook` 不带文件名时抛裸 TypeError traceback "
  "而不是用法提示（cypyc/cli.py:408 的那道守卫排在 hook 分支 return 之后，护不到这里）",
  "detail": "现象（repro 实跑）: `python -m cypyc hook` → 退出码 1，stderr 末行 "
  "`TypeError: _path_isfile: path should be string, bytes, os.PathLike or integer, not NoneType`。"
  "机制: cli.py 的 hook 分支把参数转成 hook_args 后 `return hook.run_cli(hook_args)`，"
  "source 位置参数缺省即 None；:836 未判空。定性: [真缺陷]（诊断面：崩溃栈代替用户可读提示）。"
  "建议: 先判 `parsed_args.source` 为空即打印 usage 并 return 1，`isfile` 只在有值时调用。"},
]


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake7", "version": "1"}})

    def rows():
        return (c.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []

    before = rows()
    known = {(r.get("summary") or "").strip(): (r.get("bug_id") or r.get("id")) for r in before}
    mapping, failures = [], []
    for spec in FINDINGS:
        s = spec["summary"]
        if s in known:
            mapping.append({"bug_id": known[s], "task_id": None, "summary": s,
                            "fired": False, "note": "already in ledger"})
            continue
        out = c.call("report_bug", {"project_dir": ".", "summary": s, "detail": spec["detail"],
                                    "severity": spec["sev"], "publish_task": True,
                                    "reported_by": "cypy-polisher", "now": utc_now()})
        if not isinstance(out, dict) or not (out.get("bug_id") or out.get("id")):
            failures.append({"summary": s[:60], "reply": out})
            continue
        mapping.append({"bug_id": out.get("bug_id") or out.get("id"),
                        "task_id": out.get("task_id"), "summary": s, "severity": spec["sev"],
                        "fired": True})
    after = rows()
    c.close()
    got = {(r.get("summary") or "").strip() for r in after}
    missing = [f["summary"] for f in FINDINGS if f["summary"] not in got]
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map7.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} {m.get('severity',''):6s} fired={m['fired']} "
              f"{m['summary'][:52]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
