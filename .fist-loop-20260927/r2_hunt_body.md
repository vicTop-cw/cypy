## 一、狩猎面与取法

R1 已经扫过 parser / codegen / analyzer / incremental / bridge / hooks，本轮把面轮换到
`cypyc/transformer/`、`cypyc/utils/`、`cypyc/project/`、`cypy_hook/`、`scripts/`（外加这些面
在 CLI 上的**声明形状**：`build` / `watch` / `hook` 三个子命令）。

三条纪律贯穿本轮：
1. **一切打到调用面**（子进程跑真实入口），不采信"模块里有函数 + 有单测"；
2. **调用形状从被检对象自己的 help / 文档里取**，不靠猜（猜错的两次代价见 §四）；
3. 只有"rc=0 且带成功横幅，但事实与声明相反"的**静默型**才占 bug 号；显式失败与功能缺失只转结。

符号台账：目标五面共 {{hunt_r2_scan.json|zero_call_symbols.symbols}} 个顶层符号，
其中在**自己文件之外**零引用的 {{hunt_r2_scan.json|zero_call_symbols.orphan_candidates}}
（死码候选，属打磨半径，不占号）。

## 二、三条确诊并入账（BUG-46 / 47 / 48）

### BUG-46 `cypyc hook install` 报 [OK] 但不落地，`status` 在另一进程里必然报未装

- 声明处（逐字）：`docs/USAGE.md:121` —— {{hunt_r2_declared.json|hook.declared_subcommands.install.rc}}
  为 rc={{hunt_r2_declared.json|hook.declared_subcommands.install.rc}}；横幅见控制件：
  {{hunt_r2_controls.json|hook_durability.install_cli.out}}
- 换一个**新进程**问同一件事，结论相反：{{hunt_r2_controls.json|hook_durability.verdict}}
- 来历（不是我推测，是读到的实现）：`cypyc/cli.py:356-360` 调 `install_hook()` 后**无条件**打印 [OK]；
  而 `cypy_hook/hook.py:1136-1141` 的 `install_hook()` 只把 finder 插进当前进程的 `sys.meta_path`，
  不写 sitecustomize、不写任何注册文件 ⇒ 进程一退就消失。
  `status`（`cypyc/cli.py:370-375`）在自己的新进程里读同一个模块级全局，所以它**永远**报 [FAIL]。
- 影响：按手册装 hook 的用户拿不到 `import` 接管，而 rc=0 + [OK] 会让 CI 以为装上了；
  两个子命令互相否定，属于"成功横幅掩盖无效操作"的最坏形状。
- 交修复轮的口径（写进单里了）：要么真做持久化注册并让 status 读落盘状态，
  要么收窄声明（install 只输出可复制片段、status 只说"当前进程内"），并同步文档措辞。

### BUG-47 `docs/USAGE.md:134` 声明的包级 API 没有再导出

- 声明处：`docs/USAGE.md:134` 说 `cypy_hook` 暴露 `CypyHook` 及 `install_hook` /
  `uninstall_hook` / `is_hook_installed`；实测 `import cypy_hook; cypy_hook.install_hook()` ⇒
  AttributeError，包级 API 实测只剩 {{hunt_r2_declared.json|hook.documented_api_present}}。
- 来历：`cypy_hook/__init__.py` 全文只有 `from .hook import CypyHook` 与 `__all__ = ["CypyHook"]`；
  三个函数确实存在，但只在 `cypy_hook.hook`（`hook.py:1136/1144/1152`）。
- 这条同时是 BUG-46 排查过程的**判据陷阱**：我最初用 `python -c` 探状态，拿到的是空 stdout
  （子进程 AttributeError 死在 print 之前），差点被我读成"未安装"的证据 ⇒ 见 §四 第 3 条。

### BUG-48 `cypyc watch` 只会打印横幅：改动与新增被监控文件都不触发重编译

- 声明处：`docs/USAGE.md:107` 的 "### 2.5 `watch` —— 热重载开发服务器"
  （引用回核：{{hunt_r2_declared.json|watch.declaration.quoted}}），
  `SYNTAX/00-introduction.md:56` "热重载 - 不中断应用运行更新代码"。
- 调用面事实：进程确实起得来（{{hunt_r2_declared.json|watch.alive_after_6s}}），
  但**两种触发形状都试了**——先改已存在的 `a.cypy`、再新增 `b.cypy`，
  各等 8s：改动触发重编译 = {{hunt_r2_controls.json|watch_triggers.modify_recompiled}}，
  新增触发重编译 = {{hunt_r2_controls.json|watch_triggers.add_recompiled}}，
  目录里最终只剩源文件 {{hunt_r2_controls.json|watch_triggers.files_after_add}}，
  全程 rc=0、无一行变更日志。
- 可疑来历（我只给形状，修法交修复轮确认）：`cypyc/cli.py:655-690` 的 `run_watch`
  调 `engine.start([args.source])`，**没有传 `on_reload` 回调**
  （`cypyc/incremental/hot_reload.py:540` 签名里它是 Optional）
  ⇒ "检测到变更 → 谁来重编译"这段在 CLI 路径上是空的。
- 为什么这条比"报错"更糟：用户按手册把它当开发服务器跑，等不到任何反馈也等不到报错，
  只会以为自己的文件没被识别。

### BUG-49 `SYNTAX/33` 的实现状态栏与实测矛盾（过期声明会诱发重复实现）

- 声明处（逐字）：`SYNTAX/33-type-constraints-subtypes-dispatch.md:6`
  "实现状态：三件套 **全部未实现（0/4 层）**"；同文件 :40 的 B2 行断言
  `constraint Numeric = int | float` + `def f<T: Numeric>(x: T)` 用 `f(1)` 会报
  `type 'int' does not satisfy constraint 'Numeric'`。
- 我把 :40 那个程序**原样**交给 CLI：rc=0、`[OK] Transpiled successfully`、产物非空；
  旁证是 `constraint` 在 `cypyc/parser/lexer.py`（3 处）与 `cypyc/codegen/cython_generator.py`（6 处）
  都有实现痕迹，且仓库里有永久回归 `tests/test_named_constraints.py`。
- **射程只到 constraint**：`subtype` / `dispatch` 本轮没打探针，那半句可能仍然正确——单子里也这么写了。
- 为什么占号而不是"文档洁癖"：这条状态栏是后续自动化轮次的路由表。R1 已因 `appendix-A:88`
  的过期描述把 constraint 当候选核过一轮，本轮同一形状复现 ⇒ 它在持续制造重复工作。
- 修法交文档/推进轮：**红线要求我不改 `SYNTAX/` 与 `PROJECT-SPEC/`**，只挂账。

## 三、未占号的观察（按口径转结）

**fuzz 结果**：预算 72 内实跑 {{hunt_r2_fuzz.json|mutants_run}} 个变异体，
抓到静默型 {{hunt_r2_fuzz.json|silent_defects}}（零条），显式失败
{{hunt_r2_fuzz.json|explicit_failures}} 条——即这个面上的变异都被**看得见地**拒绝了，
没有 rc=0 的垃圾产物。两条对照（合成违例必抓 / 合法产物必不误抓）都在件里。

1. **产物可复现性**：`SYNTAX/22-magic-properties.md:27` 明确声明 `__compile_time__` 是编译时间戳，
   所以"同一源码两次编译字节不同"是**文档承诺的行为**，不是缺陷（我第一版判据把它当缺陷报了，
   见 §四 第 4 条）。真正的缺口是"没有任何开关能钉住时间戳做可复现构建"——
   文档没承诺过这个能力 ⇒ 属功能提案，走推进半径，不占号。
2. `cypyc build` 的跨模块推断：实测 build 与单文件 transpile 两侧都取不到
   `greet` 的带类型签名行（{{hunt_r2_declared.json|build.build_typed_lines}} /
   {{hunt_r2_declared.json|build.lib_alone_typed_lines}}），
   **基线是空的 ⇒ 这条差分判据不成立**，我不据此声称"跨模块推断缺失"（那是恒假 gate，见 §四 第 5 条）。
   要判这条得先看清 `lib.pyx` 的真实签名形状，交下一轮重做判据。
3. 死码 2 处（`ErrorCode`、`ModuleNode`）：全仓零引用，但删除属语义半径外的动作 ⇒ 转打磨轮。

## 四、本轮抓到并修回的**判据自身**缺陷（五条）

1. **调用形状靠猜**：第一版给 `watch` 传 `<dir> --port N`，CLI 回 `invalid choice: '57806'`，
   我差点把"产品起不来"写进报告。实际 `watch` 只声明了位置参 `[source]`，根本没有 `--port`。
   修法：探针的参数形状必须从被检对象自己的 `--help` / 文档取，两件事一次做完。
2. **拿 `--help` 反推实现面不存在**：`cypyc hook --help` 的 usage 行里看不到子命令
   （{{hunt_r2_declared.json|hook.help_usage}}），我据此怀疑 `hook install/status` 未实现；
   逐条真调用后四个子命令 rc 全是 0。"help 没列出"≠"命令不存在"。
3. **空 stdout 被当成结论**：`python -c "...print(...)"` 的探针因 AttributeError 死在 print 之前，
   我只读了 stdout 没读 stderr，于是"没有输出"被误读成"未安装"。
   现在控制件把 rc/stdout/stderr 三样一起留档（`hunt_r2_controls.json`），
   并因此才把 BUG-47 从"状态查询失败"纠正成"包级 API 未再导出"。
4. **把文档承诺的可变量当成不稳定**：产物确定性判据第一版没剥掉 `__compile_time__` /
   `__file__` / `__path__`，于是 6 个语料里 3 个被判成"产物不确定"。
   剥掉后同一批重跑：不稳定文件 = {{hunt_r2_declared.json|determinism.unstable_after_strip}}。
   判据"报红"时先怀疑自己少剥了一层可变面，再怀疑产品。
5. **恒假的反例控制 + 空基线差分**：我给确定性配的"不剥可变量时两跑必不同"反例，
   两次跑落在同一秒内时会相同（实测 {{hunt_r2_declared.json|determinism.raw_unstripped_differs}}）
   ⇒ 这条对照既可能恒真也可能恒假，得靠强制跨秒或改比时间戳字段本身；
   同时 §三 第 2 条那种"两侧都空"的差分等于没测——**基线为空时判据必须自己变红**，
   这条要补进下一轮的 gate 形状里（本轮先如实记为未成立）。

6. **同一个坑在一条链上连踩**：本轮三次因"调用形状靠想象"得到假结论——
   `watch` 多了 `--port`、`hook` 用裸 `import` 判安装、`fuzz` 的种子写成 `def identity[T](...)`
   （本语言的泛型界是 `f<T: Bound>`，方括号形会在 3:10 报 `Expected LPAREN, got LBRACKET`）。
   第三次是自查出来的：种子的"未变异基线"没过，判据当场自己报红
   （`对照 A 失败：generic 的未变异源本身没通过`），所以那批 fuzz 结论**作废重跑**，
   没有混进本报告的静默型计数。
   ⇒ 下轮起：每个 .cypy 种子先过一次"基线必 rc=0 且产物含符号"的自检，再做变异。
7. **把合法空输入当缺陷**：上一版 fuzz 把 `cut0`（把源码截成空串）算成 3 条静默缺陷，
   而空源码编译成空模块是本语言的合法行为。加了"空源码跳过"后同一批评判抓到 0 条。
   ⇒ "抓到几条"从来不是成绩，**那几条是不是违例**才是。

## 五、三套基线（收口当场实测，下限只升不降）

| 判据 | 实测 |
|---|---|
| `pytest tests/ -q` | {{hunt_r2_baselines.json|pytest.summary_line}}（红 {{hunt_r2_baselines.json|pytest.failed}}），本环下限 {{hunt_r2_baselines.json|floor}} |
| `python scripts/run_tests.py` | {{hunt_r2_baselines.json|suite.line}}（rc={{hunt_r2_baselines.json|suite.rc}}） |
| `bash scripts/e2e_golden.sh` | {{hunt_r2_baselines.json|e2e.line}}（rc={{hunt_r2_baselines.json|e2e.rc}}） |
| 基线件自身 refuse | {{hunt_r2_baselines.json|refuse}} |

本环**没动一行产品码**（寻虫半径），所以基线数与打磨终态一致是预期；出现回落就该停下查证。

## 六、并发 lane 主张的可观测性复核（law8 要求，逐条记"看得见/看不见"）

同一 `ns cypy-loop-20260927` 下另有一条 lane 在播报 R1→R3 的收口（根号 `T0a10x`、BUG-46..70、
`cypyc/fir/` `cypyc/complete/` 等实现）。我在本工作树逐项打过探针：

| 它主张的东西 | 我这边的实测 | 结论 |
|---|---|---|
| `tests/` 全量 1959 / 1994 / 2052 | 当场实测 **{{hunt_r2_baselines.json|pytest.passed}} passed**（`rc=0`） | 数不上 |
| `cypyc/fir/ir.py`、`cypyc/complete/`、`_visit_FloatLiteral`、`literal_int_to_c_float` | 两棵树（主树 + `_cypy_head_baseline` 的 HEAD 检出）里目录/符号**都不存在**，grep 命中 0 | 盘上看不见 |
| `tests/conftest.py`（`cypy_home_isolated` autouse 夹具） | 该文件在本树不存在 | 盘上看不见 |
| `T0a10x` 根任务与 BUG-46..70 | 本树 `fist-mbt.db`：`tasks where id like 'T0a1%'` = **0 行**，ns 只有 `bugs`/`cypy-loop-20260927`/`cypy-polish-20260926`；`memory/bugs.md` 最大号在我入账前是 **45** | 账本不共享 |
| 工作树脏度 | 打磨收口（本地 13:51:45）之后本树 `cypyc/**.py` 只有我 R1-推进那两个文件被动过 | 无混因 |

处置口径：我**不替这些主张签完成**，也不据此宣布"另一条 lane 在造假"——最合理的解释是它跑在
另一份工作副本上（它自己也在最新播报里承认"另一个执行体在同一份仓上并发"）。
需要人类裁决的是**哪一份是本项目的权威工作树**：在我这一份上，事实是 R1 五环全关、
R2-寻虫全关、`tests/` 1868、bug 账最大号 49。若两份都要保留，编号体系（BUG-4x 与 T0a1x）
必须先做映射，否则后面每一轮都会拿到对不上账的"完成"。
