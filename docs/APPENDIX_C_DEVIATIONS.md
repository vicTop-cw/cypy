# 附录 C 的形差补注（非冻结面）

本文件是对 `SYNTAX/appendix-C-features.md`《已实现的限制修复》表的**补注**，不是那份表本身。冻结面的措辞改动一律交人工（见文末）。
证据件：`.fist-loop-20260927/verify_r4_appendixC.json`（R4-验证 逐行现写真跑）。

| 附录 C 行号 | 冻结面原文行（逐字引用） | 本轮实测 | 结论 | 出路 |
| --- | --- | --- | --- | --- |
| 1 | `\| 切片语法 `list[a:b]` \| v0.2 \|` | 生成面 .pyx 证据缺 []；类型面把切片表达式的类型判成容器**元素**类型：实测 ['Return type mismatch: expected list[int], got int at 4:1']；仓内自带 DEMO examples/demos/upcoming_features/planned_features.cypy 走 --check-only 得 1 码、4 条诊断 ⇒ 文档「已实现 v0.2」在调用面不成立 | claim-false | 改冻结面（交人工）+ 本文件补注（已完成） |
| 4 | `\| Codegen `_generate_tuple_condition` \| v0.2 \|` | 行为面成立（生成物含 ['isinstance(_match_subject_1, (list, tuple))', 'len(_match_subject_1) == 2']），但文档点名的私有方法 `_generate_tuple_condition` 调用计数为 0 ⇒ 该名字不在活路径上（活路径在 `_pattern_match_info`，把同样的条件就地拼出来） | claim-half-true | 改冻结面（交人工）+ 本文件补注（已完成） |
| 5 | `\| Codegen `_generate_array_condition` \| v0.2 \|` | 行为面成立（生成物含 ['isinstance(_match_subject_1, (list, tuple))', 'len(_match_subject_1) >= 1', 'rest = _match_subject_1[1:]']），但文档点名的私有方法 `_generate_array_condition` 调用计数为 0 ⇒ 该名字不在活路径上（活路径在 `_pattern_match_info`，把同样的条件就地拼出来） | claim-half-true | 改冻结面（交人工）+ 本文件补注（已完成） |
| 6 | `\| Codegen `_generate_dict_condition` \| v0.2 \|` | 行为面成立（生成物含 ['isinstance(_match_subject_1, dict)', "'a' in _match_subject_1"]），但文档点名的私有方法 `_generate_dict_condition` 调用计数为 0 ⇒ 该名字不在活路径上（活路径在 `_pattern_match_info`，把同样的条件就地拼出来） | claim-half-true | 改冻结面（交人工）+ 本文件补注（已完成） |

## 交人工的那一栏（本环不动刀）

- 上表 4 行都在 `SYNTAX/appendix-C-features.md:598` 起的《已实现的限制修复》表里，该行声明「已实现 vX」而调用面实测有偏差。
- 改法有两种（删掉该行 / 把状态改成「部分实现 + 指向本补注」），哪一种都动的是冻结语义 ⇒ 由人裁决，本环只在非冻结面补注。
