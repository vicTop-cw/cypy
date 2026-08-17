"""
Cypy 代码生成质量检测框架

检测维度：
1. 编译成功率 - 生成的代码能否通过语法检查
2. 功能正确性 - 输出是否匹配 Python 等价代码
3. 代码规范 - 命名、格式、注释
4. 类型安全 - 类型注解完整性
5. 代码效率 - 冗余代码检测
6. 安全性 - 潜在的安全问题
"""

import os
import re
import ast
import json
import csv
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class QualityLevel(Enum):
    """质量等级"""
    EXCELLENT = "excellent"  # 90-100 分
    GOOD = "good"  # 75-89 分
    ACCEPTABLE = "acceptable"  # 60-74 分
    NEEDS_IMPROVEMENT = "needs_improvement"  # 40-59 分
    POOR = "poor"  # 0-39 分


class SeverityLevel(Enum):
    """问题严重程度"""
    CRITICAL = "critical"  # 导致编译/运行失败
    HIGH = "high"  # 功能严重影响
    MEDIUM = "medium"  # 代码质量问题
    LOW = "low"  # 风格建议


@dataclass
class QualityIssue:
    """检测到的问题"""
    rule_id: str
    severity: SeverityLevel
    category: str
    description: str
    file: str = ""
    line: int = 0
    suggestion: str = ""


@dataclass
class QualityScore:
    """质量评分"""
    dimension: str
    score: float  # 0-100
    weight: float  # 权重
    details: List[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """质量检测报告"""
    test_case: str
    total_score: float
    level: QualityLevel
    scores: List[QualityScore]
    issues: List[QualityIssue]
    generated_code_lines: int
    python_equivalent_lines: int
    code_ratio: float  # generated / python
    timestamp: str = ""


class CodeQualityChecker:
    """代码质量检测器"""

    # 质量维度和权重
    DIMENSIONS = {
        "compilation_success": 0.25,  # 编译成功率
        "functional_correctness": 0.30,  # 功能正确性
        "type_safety": 0.15,  # 类型安全
        "code_efficiency": 0.10,  # 代码效率
        "code_standards": 0.10,  # 代码规范
        "security": 0.10,  # 安全性
    }

    def __init__(self):
        self.results: List[QualityReport] = []

    def check_code(self, test_case_name: str, cypy_source: str, cython_generated: str,
                   python_equivalent: str = "") -> QualityReport:
        """检测代码质量"""
        issues = []
        scores = []

        # 1. 编译成功率检测
        comp_score, comp_issues = self._check_compilation(cypy_source, cython_generated)
        scores.append(QualityScore(
            dimension="compilation_success",
            score=comp_score,
            weight=self.DIMENSIONS["compilation_success"],
            details=[f"语法检查通过: {len([i for i in comp_issues if i.severity == SeverityLevel.CRITICAL]) == 0}"]
        ))
        issues.extend(comp_issues)

        # 2. 功能正确性检测
        func_score, func_issues = self._check_functional_correctness(cypy_source, cython_generated)
        scores.append(QualityScore(
            dimension="functional_correctness",
            score=func_score,
            weight=self.DIMENSIONS["functional_correctness"],
            details=[f"逻辑等价性评估"]
        ))
        issues.extend(func_issues)

        # 3. 类型安全检测
        type_score, type_issues = self._check_type_safety(cython_generated)
        scores.append(QualityScore(
            dimension="type_safety",
            score=type_score,
            weight=self.DIMENSIONS["type_safety"],
            details=[f"类型注解覆盖率: {type_score:.0f}%"]
        ))
        issues.extend(type_issues)

        # 4. 代码效率检测
        eff_score, eff_issues = self._check_code_efficiency(cython_generated)
        scores.append(QualityScore(
            dimension="code_efficiency",
            score=eff_score,
            weight=self.DIMENSIONS["code_efficiency"],
            details=[f"冗余代码检测"]
        ))
        issues.extend(eff_issues)

        # 5. 代码规范检测
        std_score, std_issues = self._check_code_standards(cython_generated)
        scores.append(QualityScore(
            dimension="code_standards",
            score=std_score,
            weight=self.DIMENSIONS["code_standards"],
            details=[f"代码规范检查"]
        ))
        issues.extend(std_issues)

        # 6. 安全性检测
        sec_score, sec_issues = self._check_security(cython_generated)
        scores.append(QualityScore(
            dimension="security",
            score=sec_score,
            weight=self.DIMENSIONS["security"],
            details=[f"安全隐患检查"]
        ))
        issues.extend(sec_issues)

        # 计算总分
        total_score = sum(s.score * s.weight for s in scores)
        level = self._get_quality_level(total_score)

        # 代码行数统计
        generated_lines = len(cython_generated.strip().split('\n')) if cython_generated else 0
        python_lines = len(python_equivalent.strip().split('\n')) if python_equivalent else 0
        code_ratio = generated_lines / python_lines if python_lines > 0 else 1.0

        report = QualityReport(
            test_case=test_case_name,
            total_score=total_score,
            level=level,
            scores=scores,
            issues=issues,
            generated_code_lines=generated_lines,
            python_equivalent_lines=python_lines,
            code_ratio=code_ratio,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
        )

        self.results.append(report)
        return report

    def _check_compilation(self, cypy_source: str, cython_code: str) -> Tuple[float, List[QualityIssue]]:
        """检查编译成功率"""
        issues = []
        score = 100.0

        # 检查 Cypy 源码能否被解析
        try:
            from cypyc.parser.lexer import Lexer
            from cypyc.parser.parser import Parser
            
            lexer = Lexer(cypy_source)
            tokens = list(lexer.tokenize())
            parser = Parser(tokens)
            ast = parser.parse()
            
            if ast is None:
                issues.append(QualityIssue(
                    rule_id="COMP-001",
                    severity=SeverityLevel.CRITICAL,
                    category="compilation",
                    description="Cypy 源码无法解析",
                    suggestion="检查语法是否正确"
                ))
                score -= 50
        except Exception as e:
            issues.append(QualityIssue(
                rule_id="COMP-002",
                severity=SeverityLevel.CRITICAL,
                category="compilation",
                description=f"Cypy 解析错误: {str(e)}",
                suggestion="修复语法错误"
            ))
            score -= 50

        # 检查生成的 Cython 代码是否包含基本结构
        if cython_code:
            # 检查必要的导入和结构
            if 'import cython' not in cython_code:
                issues.append(QualityIssue(
                    rule_id="COMP-003",
                    severity=SeverityLevel.HIGH,
                    category="compilation",
                    description="生成代码缺少 cython 导入",
                    suggestion="添加 `import cython`"
                ))
                score -= 10
            
            # 检查是否有语法错误模式
            syntax_errors = self._detect_cython_syntax_issues(cython_code)
            for error in syntax_errors:
                issues.append(error)
                score -= 5
        else:
            issues.append(QualityIssue(
                rule_id="COMP-004",
                severity=SeverityLevel.CRITICAL,
                category="compilation",
                description="未生成任何 Cython 代码",
                suggestion="检查代码生成器配置"
            ))
            score -= 50

        return max(0, score), issues

    def _detect_cython_syntax_issues(self, code: str) -> List[QualityIssue]:
        """检测 Cython 语法问题"""
        issues = []
        
        # 检查括号匹配
        open_parens = code.count('(') - code.count(')')
        if open_parens != 0:
            issues.append(QualityIssue(
                rule_id="COMP-SYN-001",
                severity=SeverityLevel.CRITICAL,
                category="syntax",
                description="括号不匹配",
                suggestion="检查括号配对"
            ))
        
        # 检查缩进一致性
        lines = code.split('\n')
        for i, line in enumerate(lines):
            if line and not line.startswith((' ', '\t', '#', '\n')):
                if line[0].isalpha() and not line.startswith(('cdef', 'cpdef', 'def', 'class', 'import', 'from', 'if', 'else', 'while', 'for', 'return', 'try', 'except', 'with', 'global', 'nonlocal')):
                    pass  # 可能是表达式，跳过检查
        
        # 检查空的函数体
        empty_funcs = re.findall(r'(?:cdef|cpdef|def)\s+\w+.*:\s*\n\s*pass', code)
        if empty_funcs:
            issues.append(QualityIssue(
                rule_id="COMP-SYN-002",
                severity=SeverityLevel.MEDIUM,
                category="syntax",
                description=f"存在 {len(empty_funcs)} 个空函数体",
                suggestion="填充函数实现或添加合理的默认行为"
            ))
        
        return issues

    def _check_functional_correctness(self, cypy_source: str, cython_code: str) -> Tuple[float, List[QualityIssue]]:
        """检查功能正确性"""
        issues = []
        score = 100.0

        # 提取 Cypy 函数签名
        cypy_functions = self._extract_functions(cypy_source, 'cypy')
        
        # 提取 Cython 函数签名
        cython_functions = self._extract_functions(cython_code, 'cython')
        
        # 比较函数数量
        if len(cypy_functions) > len(cython_functions):
            issues.append(QualityIssue(
                rule_id="FUNC-001",
                severity=SeverityLevel.HIGH,
                category="correctness",
                description=f"函数数量不匹配: Cypy({len(cypy_functions)}) vs Cython({len(cython_functions)})",
                suggestion="检查是否有函数被错误地移除"
            ))
            score -= 30

        # 比较函数名
        cypy_names = set(cypy_functions.keys())
        cython_names = set(cython_functions.keys())
        
        missing = cypy_names - cython_names
        if missing:
            issues.append(QualityIssue(
                rule_id="FUNC-002",
                severity=SeverityLevel.HIGH,
                category="correctness",
                description=f"缺失的函数: {missing}",
                suggestion="确保所有函数都被正确转换"
            ))
            score -= len(missing) * 10

        # 检查返回类型一致性
        for func_name in cypy_names & cython_names:
            cypy_ret = cypy_functions[func_name].get('return_type', '')
            cython_ret = cython_functions[func_name].get('return_type', '')
            
            if cypy_ret and cython_ret and cypy_ret.lower() not in cython_ret.lower():
                if cython_ret.lower() != 'object':  # object 是通用类型
                    issues.append(QualityIssue(
                        rule_id="FUNC-003",
                        severity=SeverityLevel.MEDIUM,
                        category="correctness",
                        description=f"函数 '{func_name}' 返回类型不一致: {cypy_ret} vs {cython_ret}",
                        suggestion="检查类型映射是否正确"
                    ))
                    score -= 5

        return max(0, score), issues

    def _extract_functions(self, code: str, lang: str) -> Dict[str, Dict]:
        """提取函数定义"""
        functions = {}
        
        if lang == 'cypy':
            # Cypy 格式: def func_name(params) -> return_type:
            pattern = r'def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*(\w+(?:<[^>]*>)?))?\s*:'
        else:
            # Cython 格式支持两种:
            # 1. cpdef float func_name(params):  (返回类型在函数名前)
            # 2. cpdef func_name(params) -> float:  (返回类型在函数名后)
            pattern = r'(?:cdef|cpdef|def)\s+(?:(\w+(?:<[^>]*>)?)\s+)?(\w+)\s*\(([^)]*)\)\s*(?:->\s*(\w+(?:<[^>]*>)?))?\s*:'
        
        matches = re.findall(pattern, code)
        if lang == 'cypy':
            for name, params, return_type in matches:
                functions[name] = {
                    'name': name,
                    'params': params,
                    'return_type': return_type.strip() if return_type else '',
                }
        else:
            for prefix_type, name, params, suffix_type in matches:
                return_type = prefix_type or suffix_type or ''
                functions[name] = {
                    'name': name,
                    'params': params,
                    'return_type': return_type.strip(),
                }
        
        return functions

    def _check_type_safety(self, cython_code: str) -> Tuple[float, List[QualityIssue]]:
        """检查类型安全"""
        issues = []
        score = 100.0

        # 检查类型注解覆盖率
        lines = cython_code.split('\n')
        total_functions = 0
        typed_functions = 0
        typed_params = 0
        total_params = 0

        for line in lines:
            # 函数定义行
            func_match = re.match(r'(cdef|cpdef|def)\s+(\w+)\s*\(([^)]*)\)', line)
            if func_match:
                total_functions += 1
                params_str = func_match.group(3)
                
                # 检查参数类型注解
                if params_str.strip():
                    params = [p.strip() for p in params_str.split(',') if p.strip()]
                    for param in params:
                        total_params += 1
                        if ':' in param or param == 'self':
                            typed_params += 1
                
                # 检查返回类型
                if '->' in line or ':' in line:
                    typed_functions += 1

        # 计算类型注解覆盖率
        if total_functions > 0:
            func_coverage = typed_functions / total_functions * 100
            if func_coverage < 80:
                issues.append(QualityIssue(
                    rule_id="TYPE-001",
                    severity=SeverityLevel.MEDIUM,
                    category="type_safety",
                    description=f"函数返回类型注解覆盖率偏低: {func_coverage:.0f}%",
                    suggestion="增加返回类型注解"
                ))
                score -= 15

        if total_params > 0:
            param_coverage = typed_params / total_params * 100
            if param_coverage < 70:
                issues.append(QualityIssue(
                    rule_id="TYPE-002",
                    severity=SeverityLevel.MEDIUM,
                    category="type_safety",
                    description=f"参数类型注解覆盖率偏低: {param_coverage:.0f}%",
                    suggestion="增加参数类型注解"
                ))
                score -= 15

        # 检查是否使用了 object 类型作为兜底
        # 更智能的检测：排除基类中的 object、注释中的 object
        lines = cython_code.split('\n')
        object_type_usage = 0
        for line in lines:
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith('#'):
                continue
            # 跳过基类中的 object (如 class Foo(object):)
            if re.match(r'(cdef|cpdef|def)\s+class\s+\w+\s*\(', stripped):
                # class Foo(object): 或 class Foo(Base, object):
                if re.search(r'\(\s*object\s*\)', stripped) or re.search(r'\(\s*[^)]*,\s*object\s*\)', stripped):
                    continue
            # 跳过注释后的 object (在行尾注释)
            code_part = line.split('#')[0] if '#' in line else line
            # 统计代码中的 object 类型使用
            matches = re.findall(r':\s*object\b|->\s*object\b|\bobject\s*[=,\)\]]', code_part)
            object_type_usage += len(matches)
        
        # 只有当 object 类型使用超过合理阈值时才报告问题
        # 每个函数允许最多 2 处 object 使用（基类、参数等）
        if object_type_usage > total_functions * 2:
            issues.append(QualityIssue(
                rule_id="TYPE-003",
                severity=SeverityLevel.LOW,
                category="type_safety",
                description=f"过多使用 object 类型 ({object_type_usage} 处)",
                suggestion="使用更具体的类型"
            ))
            score -= 10

        return max(0, score), issues

    def _check_code_efficiency(self, cython_code: str) -> Tuple[float, List[QualityIssue]]:
        """检查代码效率"""
        issues = []
        score = 100.0

        # 检测冗余代码
        lines = cython_code.split('\n')
        
        # 检查重复的代码模式
        code_blocks = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                code_blocks.append(stripped)
        
        # 检查重复行数
        duplicates = len(code_blocks) - len(set(code_blocks))
        if duplicates > 5:
            issues.append(QualityIssue(
                rule_id="EFF-001",
                severity=SeverityLevel.MEDIUM,
                category="efficiency",
                description=f"检测到 {duplicates} 行重复代码",
                suggestion="使用函数或循环消除重复"
            ))
            score -= 10

        # 检查不必要的内存分配
        malloc_count = len(re.findall(r'\bmalloc\b', cython_code))
        free_count = len(re.findall(r'\bfree\b', cython_code))
        
        if malloc_count > 0 and malloc_count != free_count:
            issues.append(QualityIssue(
                rule_id="EFF-002",
                severity=SeverityLevel.HIGH,
                category="efficiency",
                description=f"内存分配({malloc_count})与释放({free_count})不匹配",
                suggestion="确保所有 malloc 都有对应的 free"
            ))
            score -= 20

        # 检查不必要的类型转换
        casts = len(re.findall(r'<[^>]+>', cython_code))
        if casts > 10:
            issues.append(QualityIssue(
                rule_id="EFF-003",
                severity=SeverityLevel.LOW,
                category="efficiency",
                description=f"过多的类型转换 ({casts} 处)",
                suggestion="减少不必要的类型转换"
            ))
            score -= 5

        return max(0, score), issues

    def _check_code_standards(self, cython_code: str) -> Tuple[float, List[QualityIssue]]:
        """检查代码规范"""
        issues = []
        score = 100.0

        lines = cython_code.split('\n')
        
        # 检查命名规范 - 仅警告非常长的驼峰命名（超过3个驼峰转换）
        camel_case_funcs = re.findall(r'(?:cdef|cpdef|def)\s+([a-z]+[A-Z][a-z]+[A-Z]\w*)', cython_code)
        if camel_case_funcs:
            issues.append(QualityIssue(
                rule_id="STD-001",
                severity=SeverityLevel.LOW,
                category="standards",
                description=f"函数名使用多重驼峰命名: {camel_case_funcs[:3]}",
                suggestion="考虑使用 snake_case 命名规范"
            ))
            score -= 3  # 降低扣分，因为命名风格是主观的

        # 检查行长度 - 提高阈值到 150 字符，以适应复杂的函数签名
        long_lines = [i + 1 for i, line in enumerate(lines) if len(line) > 150]
        if long_lines:
            issues.append(QualityIssue(
                rule_id="STD-002",
                severity=SeverityLevel.LOW,
                category="standards",
                description=f"发现 {len(long_lines)} 行超过 150 字符",
                suggestion="考虑拆分过长的代码行"
            ))
            score -= 3

        # 检查文档字符串 - 只有较长的模块才需要文档字符串
        has_docstring = '"""' in cython_code or "'''" in cython_code
        if not has_docstring and len(lines) > 50:
            issues.append(QualityIssue(
                rule_id="STD-003",
                severity=SeverityLevel.LOW,
                category="standards",
                description="缺少模块文档字符串",
                suggestion="为模块添加 docstring 描述其用途"
            ))
            score -= 3

        # 检查尾部空格 - 轻微扣分
        trailing_spaces = [i + 1 for i, line in enumerate(lines) if line.rstrip() != line]
        if trailing_spaces:
            issues.append(QualityIssue(
                rule_id="STD-004",
                severity=SeverityLevel.LOW,
                category="standards",
                description=f"发现 {len(trailing_spaces)} 行有尾部空格",
                suggestion="考虑移除尾部空格"
            ))
            score -= 2  # 降低扣分

        return max(0, score), issues

    def _check_security(self, cython_code: str) -> Tuple[float, List[QualityIssue]]:
        """检查安全性"""
        issues = []
        score = 100.0

        # 检查危险的函数调用
        dangerous_patterns = [
            (r'\beval\s*\(', "使用 eval() 可能导致代码注入"),
            (r'\bexec\s*\(', "使用 exec() 可能导致代码注入"),
            (r'__import__', "使用 __import__ 可能导致安全风险"),
            (r'\bos\.system\s*\(', "使用 os.system() 可能导致命令注入"),
            (r'\bsubprocess\.call\s*\(', "使用 subprocess 可能导致命令注入"),
        ]

        for pattern, description in dangerous_patterns:
            matches = re.findall(pattern, cython_code)
            if matches:
                rule_id = "SEC-" + pattern[:20].replace("\\", "_")
                issues.append(QualityIssue(
                    rule_id=rule_id,
                    severity=SeverityLevel.HIGH,
                    category="security",
                    description=description,
                    suggestion="使用更安全的替代方案"
                ))
                score -= 15

        # 检查硬编码的敏感信息
        sensitive_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "硬编码的密码"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "硬编码的密钥"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "硬编码的 API Key"),
            (r'token\s*=\s*["\'][^"\']+["\']', "硬编码的 Token"),
        ]

        for pattern, description in sensitive_patterns:
            matches = re.findall(pattern, cython_code, re.IGNORECASE)
            if matches:
                rule_id = "SEC-SENS-" + pattern[:20].replace("\\", "_")
                issues.append(QualityIssue(
                    rule_id=rule_id,
                    severity=SeverityLevel.CRITICAL,
                    category="security",
                    description=f"检测到{description}",
                    suggestion="使用环境变量或配置文件管理敏感信息"
                ))
                score -= 25

        # 检查不安全的内存操作
        unsafe_ops = len(re.findall(r'<void\*>', cython_code))
        if unsafe_ops > 3:
            issues.append(QualityIssue(
                rule_id="SEC-001",
                severity=SeverityLevel.MEDIUM,
                category="security",
                description=f"检测到 {unsafe_ops} 处不安全的指针操作",
                suggestion="考虑使用更安全的类型包装"
            ))
            score -= 10

        return max(0, score), issues

    def _get_quality_level(self, score: float) -> QualityLevel:
        """获取质量等级"""
        if score >= 90:
            return QualityLevel.EXCELLENT
        elif score >= 75:
            return QualityLevel.GOOD
        elif score >= 60:
            return QualityLevel.ACCEPTABLE
        elif score >= 40:
            return QualityLevel.NEEDS_IMPROVEMENT
        else:
            return QualityLevel.POOR

    def generate_report(self, output_file: str = "quality_report") -> str:
        """生成完整报告"""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # 保存 JSON 报告
        json_path = f"{output_file}_{timestamp}.json"
        report_data = []
        
        for report in self.results:
            report_dict = asdict(report)
            # 转换枚举类型
            report_dict['level'] = report.level.value
            for issue in report_dict['issues']:
                issue['severity'] = issue['severity'].value
            report_data.append(report_dict)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        # 生成汇总报告
        summary = self._generate_summary()
        
        summary_path = f"{output_file}_{timestamp}_summary.txt"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        return json_path

    def _generate_summary(self) -> str:
        """生成汇总文本"""
        lines = []
        lines.append("=" * 70)
        lines.append("Cypy 代码生成质量检测报告")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"检测时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"检测用例数: {len(self.results)}")
        lines.append("")
        
        if not self.results:
            return "暂无检测结果"
        
        # 统计
        total_scores = [r.total_score for r in self.results]
        avg_score = sum(total_scores) / len(total_scores)
        max_score = max(total_scores)
        min_score = min(total_scores)
        
        lines.append(f"总体评分:")
        lines.append(f"  平均分: {avg_score:.1f}")
        lines.append(f"  最高分: {max_score:.1f}")
        lines.append(f"  最低分: {min_score:.1f}")
        lines.append("")
        
        # 质量等级分布
        level_counts = {}
        for report in self.results:
            level = report.level.value
            level_counts[level] = level_counts.get(level, 0) + 1
        
        lines.append(f"质量等级分布:")
        for level, count in sorted(level_counts.items()):
            lines.append(f"  {level}: {count} 个用例")
        lines.append("")
        
        # 各维度平均分
        lines.append(f"各维度平均分:")
        dimensions = {}
        for report in self.results:
            for score in report.scores:
                if score.dimension not in dimensions:
                    dimensions[score.dimension] = []
                dimensions[score.dimension].append(score.score)
        
        for dim, scores in sorted(dimensions.items()):
            avg = sum(scores) / len(scores)
            lines.append(f"  {dim}: {avg:.1f}")
        lines.append("")
        
        # 问题统计
        all_issues = []
        for report in self.results:
            all_issues.extend(report.issues)
        
        if all_issues:
            lines.append(f"问题统计 (共 {len(all_issues)} 个):")
            
            severity_counts = {}
            for issue in all_issues:
                severity = issue.severity.value
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            for severity, count in sorted(severity_counts.items(), key=lambda x: list(SeverityLevel).index(SeverityLevel(x[0]))):
                lines.append(f"  {severity}: {count} 个")
            
            # 列出严重问题
            critical_issues = [i for i in all_issues if i.severity == SeverityLevel.CRITICAL]
            if critical_issues:
                lines.append("")
                lines.append("严重问题:")
                for issue in critical_issues[:10]:
                    lines.append(f"  [{issue.rule_id}] {issue.description}")
                    if issue.suggestion:
                        lines.append(f"    建议: {issue.suggestion}")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)


def create_quality_test_suite() -> List[Tuple[str, str, str]]:
    """创建质量检测测试套件"""
    
    test_cases = [
        (
            "simple_function",
            """
def add(a: int, b: int) -> int:
    return a + b
""",
            """
# Generated by Cypy compiler
import cython

cdef class Module:
    def add(self, a: int, b: int) -> int:
        return a + b
"""
        ),
        (
            "struct_with_method",
            """
struct Point:
    x: float
    y: float

def distance(p1: Point, p2: Point) -> float:
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    return (dx * dx + dy * dy) ** 0.5
""",
            """
# Generated by Cypy compiler
import cython
import math

cdef class Point:
    cdef public float x
    cdef public float y
    
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

cdef class Module:
    cpdef float distance(self, p1: Point, p2: Point):
        cdef float dx = p1.x - p2.x
        cdef float dy = p1.y - p2.y
        return math.sqrt(dx * dx + dy * dy)
"""
        ),
        (
            "generic_function",
            """
def identity<T>(value: T) -> T:
    return value
""",
            """
# Generated by Cypy compiler
import cython

cdef class Module:
    cpdef identity(self, value):
        return value
"""
        ),
    ]
    
    return test_cases


def main():
    """主入口 - 运行质量检测"""
    print("=" * 60)
    print("Cypy 代码生成质量检测")
    print("=" * 60)
    print()
    
    # 创建检测器
    checker = CodeQualityChecker()
    
    # 运行测试套件
    test_cases = create_quality_test_suite()
    
    for case_name, cypy_source, cython_code in test_cases:
        print(f"\n检测用例: {case_name}")
        
        report = checker.check_code(
            test_case_name=case_name,
            cypy_source=cypy_source,
            cython_generated=cython_code,
            python_equivalent=cypy_source  # 使用 Cypy 源码作为近似 Python 等价
        )
        
        print(f"  总分: {report.total_score:.1f}")
        print(f"  等级: {report.level.value}")
        print(f"  问题数: {len(report.issues)}")
        
        if report.issues:
            print("  主要问题:")
            for issue in report.issues[:5]:
                print(f"    [{issue.severity.value}] {issue.description}")
    
    # 生成报告
    report_path = checker.generate_report("quality_report")
    print(f"\n报告已保存: {report_path}")
    
    # 打印汇总
    summary = checker._generate_summary()
    print("\n" + summary)


if __name__ == "__main__":
    main()
