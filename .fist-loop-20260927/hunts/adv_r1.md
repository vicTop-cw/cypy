# R1 路 1 对抗样例实跑

用例 20 条；候选：未声明异常逃逸 5；带诊断产出 5；静默成功 10

分类口径：只有「带行列的诊断文案 / 已声明异常 / 正常产物」算正当结局；裸 traceback 一律候选，文案像诊断的 ValueError 单列「待研判」而不默认放过。

- `adv_01_empty` → **静默成功**（诊断 0 条，产物 721 字节）
- `adv_02_comments_only` → **静默成功**（诊断 0 条，产物 721 字节）
- `adv_03_unterminated_string` → **静默成功**（诊断 0 条，产物 774 字节）
- `adv_04_non_utf8_bytes` → **静默成功**（诊断 0 条，产物 752 字节）
- `adv_05_deep_nesting` → **候选：未声明异常逃逸**（RecursionError: maximum recursion depth exceeded）
    `  File "E:\IDEProjects\AI\Cypy\cypyc\parser\parser.py", line 3314, in _parse_call`
    `    func = self._parse_primary()`
    `RecursionError: maximum recursion depth exceeded`
- `adv_06_dup_def` → **带诊断产出**（诊断 1 条，产物 773 字节）
- `adv_07_subtype_vs_class` → **候选：未声明异常逃逸**（ValueError: subtype declaration 'Meter' expects '<:' before its base type, e.g. 'subtype Meter <: float' at 1:9）
    `    ...<2 lines>...`
    `        % (name_token.value, name_token.value, name_token.line, name_token.col))`
    `ValueError: subtype declaration 'Meter' expects '<:' before its base type, e.g. 'subtype Meter <: float' at 1:9`
- `adv_08_type_vs_constraint` → **带诊断产出**（诊断 1 条，产物 772 字节）
- `adv_09_empty_struct` → **静默成功**（诊断 0 条，产物 780 字节）
- `adv_10_slice_step_zero` → **静默成功**（诊断 0 条，产物 815 字节）
- `adv_11_const_div_zero` → **静默成功**（诊断 0 条，产物 786 字节）
- `adv_12_huge_int_literal` → **静默成功**（诊断 0 条，产物 789 字节）
- `adv_13_undefined_name` → **带诊断产出**（诊断 2 条，产物 761 字节）
- `adv_14_cast_to_nontype` → **带诊断产出**（诊断 1 条，产物 787 字节）
- `adv_15_include_missing` → **带诊断产出**（诊断 2 条，产物 791 字节）
- `adv_16_defer_top_level` → **候选：未声明异常逃逸**（ValueError: defer must be used inside a function, found at 1:7）
    `  File "E:\IDEProjects\AI\Cypy\cypyc\parser\parser.py", line 880, in _require_function_scope`
    `    raise ValueError(f"{construct_name} must be used inside a function, found at {token.line}:{token.col}")`
    `ValueError: defer must be used inside a function, found at 1:7`
- `adv_17_pipe_to_nonfunc` → **静默成功**（诊断 0 条，产物 767 字节）
- `adv_18_nested_fstring` → **候选：未声明异常逃逸**（ValueError: Expected RPAREN, got IDENTIFIER at 2:17）
    `  File "E:\IDEProjects\AI\Cypy\cypyc\parser\parser.py", line 901, in _consume`
    `    raise ValueError(f"Expected {expected_type}, got {token.type} at {token.line}:{token.col}")`
    `ValueError: Expected RPAREN, got IDENTIFIER at 2:17`
- `adv_19_negative_index_const` → **静默成功**（诊断 0 条，产物 794 字节）
- `adv_20_unbalanced_bracket` → **候选：未声明异常逃逸**（ValueError: Expected RBRACKET, got NEWLINE at 3:5）
    `  File "E:\IDEProjects\AI\Cypy\cypyc\parser\parser.py", line 901, in _consume`
    `    raise ValueError(f"Expected {expected_type}, got {token.type} at {token.line}:{token.col}")`
    `ValueError: Expected RBRACKET, got NEWLINE at 3:5`
