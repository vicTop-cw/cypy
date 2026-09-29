# R1 — 变异模糊 + 不变量/差分（fuzz & differential）

执行时间：2026-09-27 10:55–11:07（本地）。全部产物只在 `.fist-loop-20260927/` 下；未改动任何源码/用例/golden。

## 参数

- 随机种子：`SEED = 20260927`（`random.Random(SEED)` 单次实例化，逐条确定性生成；harness 见 `.fist-loop-20260927/fuzz/fuzz_r1.py`）
- 种子语料：`examples/*.cypy` 25 个（排除 `_pending_*`）
- 变异算子（14 种，轮转分配）：`del_char / del_sigil / repl_char / dup_line / dup_block / flip_quote / truncate / truncate_eol / ins_bracket / ins_indent / kw_surgery / ins_ctrl_char / swap_lines / dedent`；25% 概率叠加第二次同种变异；每第 6 个文本变异额外派生一个字节级 `nonutf8_*`（在截断处追加 `ff fe 80 c0 af`）
- 入口：in-process 复刻 `CypyHook._parse_and_analyze` + `CythonGenerator.generate`，**去掉** hook 的兜底 `except Exception`，以便暴露内部崩溃；`sys.setrecursionlimit(1000)` 与 CLI 一致；看门狗 5s（`os._exit` + JSONL 断点续跑）
- 计划条目 120 = 25 基线（未变异）+ 95 变异体（82 文本 + 13 nonutf8）

## 分类计数（仅 95 个变异体）

| 类 | 含义 | 数量 |
|---|---|---|
| a | 带位置信息的用户级诊断（ValueError/SyntaxError + line:col） | 48 |
| b | 逃逸的 Python 异常 | 14（1 例真实内部崩溃 + 13 例读文件阶段 UnicodeDecodeError） |
| c | 无诊断且成功产出 Cython 文本 | 33 |
| d | 挂起 >5s | 0 |
| e | 产物阶段失败 | 0（fuzz 阶段未调 C 编译器；`fuzz_02` 在复核时由 c 升为 e） |

基线 25/25 为 c（预期）。原始日志 `fuzz/fuzz_r1.log`、逐条记录 `fuzz/results_r1.jsonl`、被保存变异体 `fuzz/mutants/`（仅 b/d 类）。

## CANDIDATES

| id | 现象 | 最小复现文件 | 复现命令 | 期望 vs 实际 | 初判 | 命中位置 |
|---|---|---|---|---|---|---|
| fuzz_01 | 源文件以空格/Tab 结尾（无换行）时词法分析器抛 `TypeError`；诊断被错标为“读取文件错误”，无 file:line | `hunts/fuzz_01.cypy`（10 字节：`let x = 1 `） | `python -m cypyc transpile .fist-loop-20260927/hunts/fuzz_01.cypy -o .fist-loop-20260927/fuzz/cli_out` | 期望：语法通过（该行合法）或给出 `file:line` 诊断 / 实际：exit=1，`- 读取文件错误: 'in <string>' requires string as left operand, not NoneType` | 真缺陷 | `cypyc/parser/lexer.py:278`（`_skip_whitespace`，被 `tokenize` 于 `:510` 调用）；错标处 `cypy_hook/hook.py:412` |
| fuzz_02 | 顶层 `return`（缩进移出函数体）被静默接受并原样写进 .pyx，产物在真实 Cython 前端编译失败 | `hunts/fuzz_02.cypy`（4 行） | `python -m cypyc transpile .fist-loop-20260927/hunts/fuzz_02.cypy -o .fist-loop-20260927/fuzz/cli_out && python -m cython -3 .fist-loop-20260927/fuzz/cli_out/fuzz_02.pyx -o .fist-loop-20260927/fuzz/cli_out/fuzz_02.c` | 期望：编译期报“return 必须在函数内” / 实际：`[OK] Transpiled successfully`，随后 `.fist-loop-20260927\fuzz\cli_out\fuzz_02.pyx:31:0: Return not inside a function body` | 真缺陷（c→e） | `cypyc/parser/parser.py:1671` `_parse_return_stmt` 未调用守卫 `_require_function_scope`（定义 `:877`，仅用于 defer/guard/spawn/go）；codegen 侧亦无校验 |
| fuzz_03 | 非 UTF-8 字节序列：编译期无 traceback 逃逸，但诊断类别被错标为“读取文件错误”且不含文件名/行 | `hunts/fuzz_03.cypy`（`let x = 1 ` + `ff fe 80`） | `python -m cypyc transpile .fist-loop-20260927/hunts/fuzz_03.cypy -o .fist-loop-20260927/fuzz/cli_out` | 期望：明确的编码错误（含文件路径、偏移） / 实际：`- 读取文件错误: 'utf-8' codec can't decode byte 0xff in position 10: invalid start byte`，exit=1 | 疑似（诊断质量问题，非崩溃） | `cypy_hook/hook.py:412`（`except Exception` 统一贴“读取文件错误”标签） |
| fuzz_04 | 幂等性破裂：同一源两次 transpile 产出字节不同（`__compile_time__` 内嵌墙上时钟，秒级） | `hunts/fuzz_04.cypy`；实测 `examples/*.cypy` 25/25 全中 | `python -m cypyc transpile .fist-loop-20260927/hunts/fuzz_04.cypy -o .fist-loop-20260927/fuzz/cli_out`（间隔 >1s 跑两次后 `fc` 对比） | 期望 source→Cython 为纯函数、字节一致 / 实际：`-__compile_time__ = "2026-09-27T11:04:44"` vs `+...T11:04:47`，其余逐字节相同 | 真缺陷（差分构建/golden/缓存抖动的根源） | `cypyc/codegen/cython_generator.py:620`（另 `:326` 的 `__generated_at__` 是运行期表达式，不破坏文本幂等） |
| fuzz_05 | `CythonGenerator` 实例复用时跨模块状态泄漏：`__all__` 累加上一模块的符号 | `hunts/fuzz_05.cypy` + `examples/hello.cypy` | 见 `hunts/fuzz_05.txt` 的 `python -c` 一行式 | 期望与新建实例一致（`__all__ = ["greet", "main"]`）/ 实际：`__all__ = ["a", "greet", "main"]` | 疑似（潜在 API 陷阱；当前生产路径每模块新建实例，未触达） | `cypyc/codegen/cython_generator.py:91-92`（`generate()` 只重置 `self.output`，`type_aliases/_class_fields/...` 不清空） |

关键 traceback 逐字尾部：

```
File "E:\IDEProjects\AI\Cypy\cypyc\parser\lexer.py", line 510, in tokenize -> self._skip_whitespace()
File "E:\IDEProjects\AI\Cypy\cypyc\parser\lexer.py", line 278, in _skip_whitespace -> while self._peek() in " \t":
TypeError: 'in <string>' requires string as left operand, not NoneType
```
```
    return 1
return 0
.fist-loop-20260927\fuzz\cli_out\fuzz_02.pyx:31:0: Return not inside a function body
```

## TASK B 其余结论（未产生候选的部分照实记录）

- **B1 紧接重复**（同秒内两次生成）：25/25 字节一致，0 失败。**B1 跨秒重复**：25/25 不一致（=fuzz_04）。
- **自格式化/回环路径**：`cypyc/incremental/`、`cypyc/cli.py`、`cypy_hook/` 中不存在 source→source 重写路径（无 `reformat/to_source/round_trip` 类实现），回环不变量无从断言，按指令不臆造。作为纯健壮性探针把生成 .pyx 回喂前端：25/25 得到词法/语法诊断（ValueError 带位置），无内部崩溃。
- **B2 跨模式差分**（同源三路上文本对比：直连管线 / `CypyHook.transpile` / `ProjectCompiler` 生成前缀路径）：25 例中仅 1 例报告差异，且差异行就是 `__compile_time__`（即 fuzz_04），无独立文本不一致。真实 `ProjectCompiler`（discover→parse→dep graph→type registry→`type_check_module`）与单文件诊断集合：0/25 不一致。附带观察（未列候选）：项目模式 `parse_all_modules` 不调用 `Preprocessor`，而单文件模式调用；`examples/` 中无 `#include/#define/#line`，故本次语料上不可见。
- **B3 golden（只读）**：`bash scripts/e2e_golden.sh`（无 `--update`）在 260s 硬超时被终止，`exit=124`，未拿到 summary 行（该脚本把报告缓存在末尾一次性打印，`.fist-loop-20260927/fuzz/e2e_golden_r1.log` 为 0 字节）。**按预算放弃，未产生 golden-drift 候选**；注意脚本内的 `cypyc run` 在其运行期间会向 `output/` 写中间产物（这是该脚本固有行为，未执行任何写基准动作）。

## 备注

- 33 个 class-c 中抽查 20 个：多数落点在字符串字面量/注释内（合法），仅 `m0028`（dedent）暴露为 fuzz_02；未据 class-c 数量单独凑候选。
- 13 个 nonutf8 变体在 CLI 表面全部被捕获（exit=1，无 traceback 逃逸），合并为单条 fuzz_03。

## 产物索引

`fuzz/fuzz_r1.py`（harness，可断点续跑）、`fuzz/fuzz_r1.log` + `fuzz/results_r1.jsonl`（逐条原始记录）、`fuzz/mutants/`（仅 b/d 类变异体）、`fuzz/diff_r1.py` + `fuzz/diff_r1.out.txt`（Task B 全部输出）、`fuzz/cli_out/`（CLI 复核产物与生成的 .pyx）、`hunts/fuzz_01..05.cypy` + 同名 `.txt`（最小复现）。
