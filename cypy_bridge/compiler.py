"""
Cypy Bridge Compiler Module

提供将 Cypy 代码编译为 C 代码并生成动态链接库的功能。
这是自举过程中移除 Cython 依赖的核心组件。

参考 DeepSeek Cython 语法教程：
- cdef: C类型声明
- cpdef: 同时具有C和Python接口的函数
- def: Python函数
- 支持结构体、枚举、指针、内存管理等C特性
"""

import os
import sys
import subprocess
import tempfile
import shutil
from typing import Any, Dict, Optional, List
from .core import BridgeError
from cypyc.parser.parser import BuildBlockExpr, Constant

# 与 cypy_hook/hook.py、cypyc/project/project_compiler.py 的 build_ext 子进程同一口径
BUILD_TIMEOUT = 120


class CompileError(Exception):
    """编译错误类：包含精确定位信息"""
    
    def __init__(self, message: str, line: int = None, col: int = None, 
                 source_file: str = None, source_line: str = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.source_file = source_file
        self.source_line = source_line
    
    def __str__(self):
        parts = []
        if self.source_file:
            parts.append(f"File \"{self.source_file}\"")
        if self.line is not None:
            parts.append(f"line {self.line}")
            if self.col is not None:
                parts.append(f"column {self.col}")
        location = ", ".join(parts)
        if location:
            result = f"{location}:\n"
        else:
            result = ""
        
        if self.source_line:
            result += f"    {self.source_line.strip()}\n"
            if self.col is not None:
                result += f"    {' ' * (self.col - 1)}^\n"
        
        result += f"Error: {self.message}"
        return result


class CompileResult:
    """编译结果封装"""
    
    def __init__(self, success: bool, output_path: str = None, 
                 c_code: str = None, error: str = None, errors: list = None):
        self.success = success
        self.output_path = output_path
        self.c_code = c_code
        self.error = error
        self.errors = errors or []
    
    def __bool__(self):
        return self.success
    
    def __repr__(self):
        if self.success:
            return f"CompileResult(success=True, output={self.output_path})"
        return f"CompileResult(success=False, error={self.error})"


class CCodeGenerator:
    """C 代码生成器：负责将 Cypy AST 转换为 C 代码"""
    
    def __init__(self):
        self.output = []
        self.indent = 0
        self.module_name = ""
        self.functions = []
        self.structs = []
        self.enums = []
        self.traits = []
        self.impls = []
        self.needs_libc = False
        self.needs_python_api = True
        self.needs_simd = False  # 是否需要SIMD支持（按需生成）
        self.current_return_type = "void"
        self.buildblock_counter = 0  # 构建块确定性计数器
        self.yield_state = 0  # 生成器状态机状态计数
        
        # Cypy 类型到 C 类型的映射
        self.type_map = {
            "int": "int",
            "long": "long",
            "long long": "long long",
            "short": "short",
            "char": "char",
            "float": "float",
            "double": "double",
            "bool": "_Bool",
            "size_t": "size_t",
            "ssize_t": "ssize_t",
            "void": "void",
            "str": "const char*",
            "object": "PyObject*",
        }
        
        # C 类型到 Python 解析格式符的映射
        self.parse_format_map = {
            "int": "i",
            "long": "l",
            "long long": "L",
            "short": "h",
            "char": "b",
            "float": "f",
            "double": "d",
            "_Bool": "p",
            "size_t": "n",
            "const char*": "s",
            "PyObject*": "O",
        }
    
    def _write(self, text: str = ""):
        """写入一行代码"""
        if text:
            self.output.append("    " * self.indent + text)
        else:
            self.output.append("")
    
    def _type_to_c(self, node) -> str:
        """将类型节点转换为 C 类型字符串"""
        if node is None:
            return "void"
        
        if hasattr(node, 'id'):
            return self.type_map.get(node.id, node.id)
        
        if hasattr(node, 'base_type'):
            base = self._type_to_c(node.base_type)
            return f"{base}*"
        
        if hasattr(node, 'name') and hasattr(node, 'args'):
            # GenericType: 泛型类型如 List<int>
            name = node.name
            args = ", ".join(self._type_to_c(arg) for arg in node.args)
            # 生成特化类型名，如 List_int
            return f"{name}_{args.replace(', ', '_').replace('*', 'ptr')}"
        
        if hasattr(node, 'element_type') and hasattr(node, 'size'):
            # VecType: SIMD向量类型 vec[ElementType; Size]
            elem_type = self._type_to_c(node.element_type)
            # 使用与SIMD类型定义一致的命名
            if elem_type == "int":
                return f"VecInt32_{node.size}"
            elif elem_type == "float":
                return f"VecFloat32_{node.size}"
            elif elem_type == "double":
                return f"VecFloat64_{node.size}"
            else:
                return f"Vec{elem_type}_{node.size}"
        
        return str(node)
    
    def _type_to_parse_format(self, c_type: str) -> str:
        """将 C 类型转换为 PyArg_ParseTuple 格式符"""
        # 如果是枚举类型（不在标准映射中），返回整数格式符
        if c_type not in self.parse_format_map:
            return "i"
        return self.parse_format_map.get(c_type, "O")
    
    def _get_expr_type(self, expr) -> str:
        """获取表达式的 C 类型（简化版本）"""
        if hasattr(expr, 'kind'):
            kind = expr.kind
            
            # 常量表达式
            if kind == 'Constant':
                value = getattr(expr, 'value', None)
                if isinstance(value, int):
                    return 'int'
                elif isinstance(value, float):
                    return 'float'
                elif isinstance(value, str):
                    return 'const char*'
                else:
                    return 'PyObject*'
            
            # 变量引用（需要查找类型）
            if kind == 'Name':
                return self._get_var_type(expr.id)
            
            # 二元操作（假设返回 int 或 float）
            if kind == 'BinOp':
                left_type = self._get_expr_type(expr.left)
                right_type = self._get_expr_type(expr.right)
                if left_type == 'float' or right_type == 'float':
                    return 'float'
                return 'int'
            
            # 函数调用（默认 PyObject*）
            if kind == 'Call':
                return 'PyObject*'
        
        return 'PyObject*'
    
    def _get_var_type(self, var_name: str) -> str:
        """获取变量的 C 类型（简化版本）"""
        # 检查当前函数参数
        if hasattr(self, '_current_func_params'):
            for param in self._current_func_params:
                if param.name == var_name:
                    return self._type_to_c(param.type_annotation) if param.type_annotation else 'PyObject*'
        
        # 检查当前作用域的 LetStmt 声明（需要遍历当前函数体）
        if hasattr(self, '_current_func_body'):
            for stmt in self._current_func_body:
                if hasattr(stmt, 'kind') and stmt.kind == 'LetStmt' and stmt.name == var_name:
                    if stmt.type_annotation:
                        return self._type_to_c(stmt.type_annotation)
                    # 如果没有类型注解但有值，根据值推断
                    if hasattr(stmt, 'value') and stmt.value:
                        return self._get_expr_type(stmt.value)
        
        # 检查是否是当前模块中定义的函数
        for func_def in getattr(self, 'functions', []):
            if hasattr(func_def, 'name') and func_def.name == var_name:
                # 返回函数的返回类型
                return self._type_to_c(func_def.return_type) if func_def.return_type else 'void'
        
        return 'PyObject*'
    
    def _visit(self, node):
        """访问 AST 节点"""
        method = f"_visit_{node.kind}"
        if hasattr(self, method):
            getattr(self, method)(node)
        else:
            self._visit_children(node)
    
    def _visit_children(self, node):
        """访问子节点"""
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if hasattr(value, 'kind'):
                    self._visit(value)
                elif isinstance(value, list):
                    for item in value:
                        if hasattr(item, 'kind'):
                            self._visit(item)
    
    def _expr_to_str(self, node) -> str:
        """将表达式节点转换为字符串"""
        if node is None:
            return ""
        
        method = f"_expr_{node.kind}"
        if hasattr(self, method):
            return getattr(self, method)(node)
        
        return str(node)
    
    # ============ 表达式处理 ============
    
    def _expr_BinOp(self, node) -> str:
        left = self._expr_to_str(node.left)
        right = self._expr_to_str(node.right)
        return f"({left} {node.op} {right})"
    
    def _expr_UnaryOp(self, node) -> str:
        operand = self._expr_to_str(node.operand)
        return f"{node.op}{operand}"
    
    def _expr_Call(self, node) -> str:
        func = self._expr_to_str(node.func)
        args = ", ".join(self._expr_to_str(arg) for arg in node.args)

        # 调用点的 `<…>` 是类型实参（SYNTAX/11「调用点的类型实参」规则 4：产物必须擦除），
        # 这里过去读 `node.checker` 并生成 `(checker(), f(args))` —— 那等于把类型名当零参函数调用。
        # 解析器已不再产出该字段，故删掉这条分支；留着就是一条无人认领的死码。

        # 特殊处理标准库函数
        if hasattr(node.func, 'id'):
            if node.func.id == 'malloc':
                self.needs_libc = True
                return f"(void*)malloc({args})"
            elif node.func.id == 'free':
                self.needs_libc = True
                return f"free({args})"
            elif node.func.id == 'sizeof':
                return f"sizeof({args})"
            elif node.func.id == 'memset':
                self.needs_libc = True
                return f"memset({args})"
            elif node.func.id == 'memcpy':
                self.needs_libc = True
                return f"memcpy({args})"
            elif node.func.id == 'printf':
                self.needs_libc = True
                return f"printf({args})"
            elif node.func.id == 'fprintf':
                self.needs_libc = True
                return f"fprintf({args})"
            elif node.func.id == 'scanf':
                self.needs_libc = True
                return f"scanf({args})"
            elif node.func.id == 'strcpy':
                self.needs_libc = True
                return f"strcpy({args})"
            elif node.func.id == 'strlen':
                self.needs_libc = True
                return f"strlen({args})"
            elif node.func.id == 'len':
                # 使用PyList_Size获取列表长度
                return f"PyList_Size({args})"
            elif node.func.id == '__import__':
                # 使用 PyImport_ImportModule 导入模块
                # args 已经是 C 字符串字面量，直接传递
                return f"PyImport_ImportModule({args})"
        
        # 检查是否是lambda变量调用
        lambda_vars = getattr(self, '_lambda_vars', set())
        if hasattr(node.func, 'id') and node.func.id in lambda_vars:
            # 使用PyObject_CallObject调用lambda
            # 需要将参数打包成tuple
            if node.args:
                arg_list = ", ".join([f"PyLong_FromLong({self._expr_to_str(arg)})" for arg in node.args])
                return f"PyObject_CallObject({func}, Py_BuildValue(\"({''.join(['i']*len(node.args))})\", {arg_list}))"
            else:
                return f"PyObject_CallObject({func}, NULL)"
        
        # 检查函数表达式的类型
        func_type = self._get_expr_type(node.func)
        
        # 检查是否是用户定义的函数（在 self.functions 中）
        is_user_func = False
        if hasattr(node.func, 'id'):
            for func_def in getattr(self, 'functions', []):
                if hasattr(func_def, 'name') and func_def.name == node.func.id:
                    is_user_func = True
                    break
        
        if func_type == 'PyObject*' and not is_user_func:
            # 使用 PyObject_CallObject 调用 Python 对象
            if node.args:
                # 需要将参数打包成 tuple
                arg_list = []
                format_str = "("
                for arg in node.args:
                    arg_type = self._get_expr_type(arg)
                    if arg_type in ('int', 'long'):
                        arg_list.append(f"PyLong_FromLong({self._expr_to_str(arg)})")
                        format_str += "i"
                    elif arg_type == 'float':
                        arg_list.append(f"PyFloat_FromDouble({self._expr_to_str(arg)})")
                        format_str += "d"
                    else:
                        arg_list.append(self._expr_to_str(arg))
                        format_str += "O"
                format_str += ")"
                return f"PyObject_CallObject({func}, Py_BuildValue(\"{format_str}\", {', '.join(arg_list)}))"
            else:
                return f"PyObject_CallObject({func}, NULL)"
        else:
            # 使用普通的 C 函数调用（用户定义的函数或非PyObject*类型）
            return f"{func}({args})"
    
    def _expr_Name(self, node) -> str:
        name = node.id
        # 在生成器函数中，将局部变量和参数转换为 gen->_var_name 或 gen->_param_name
        if getattr(self, '_in_generator', False):
            if name in self._generator_params:
                return f"gen->_param_{name}"
            elif name in self._generator_locals:
                return f"gen->_var_{name}"
        # 在协程函数中，将局部变量和参数转换为 coro->_var_name 或 coro->_param_name
        if getattr(self, '_in_coroutine', False):
            if name in self._coroutine_params:
                return f"coro->_param_{name}"
            elif name in self._coroutine_locals:
                return f"coro->_var_{name}"
        return name
    
    def _expr_Constant(self, node) -> str:
        if isinstance(node.value, str):
            return f'"{node.value}"'
        elif isinstance(node.value, bool):
            return "1" if node.value else "0"
        elif isinstance(node.value, list):
            # 列表字面量：生成PyList_New和PyList_Append调用
            # 使用静态变量缓存，避免重复创建
            self.list_literal_counter = getattr(self, 'list_literal_counter', 0) + 1
            list_var = f"_list_literal_{self.list_literal_counter}"
            
            # 在当前位置生成列表创建代码
            self._write(f"PyObject* {list_var} = PyList_New({len(node.value)});")
            for i, elem in enumerate(node.value):
                if isinstance(elem, Constant):
                    elem_str = self._expr_Constant(elem)
                    if isinstance(elem.value, int):
                        self._write(f"PyList_SetItem({list_var}, {i}, PyLong_FromLong({elem.value}));")
                    elif isinstance(elem.value, float):
                        self._write(f"PyList_SetItem({list_var}, {i}, PyFloat_FromDouble({elem.value}));")
                    elif isinstance(elem.value, str):
                        self._write(f"PyList_SetItem({list_var}, {i}, PyUnicode_FromString({elem_str}));")
                    else:
                        self._write(f"PyList_SetItem({list_var}, {i}, {elem_str});")
                else:
                    elem_str = self._expr_to_str(elem)
                    self._write(f"PyList_SetItem({list_var}, {i}, {elem_str});")
            
            return list_var
        return repr(node.value)
    
    def _expr_Attribute(self, node) -> str:
        """处理属性访问表达式
        
        如果值是 PyObject*，使用 PyObject_GetAttrString 获取属性
        否则使用 C 的点号访问
        """
        value = self._expr_to_str(node.value)
        value_type = self._get_expr_type(node.value)
        
        if value_type == 'PyObject*':
            # 使用 Python C API 获取属性
            return f"PyObject_GetAttrString({value}, \"{node.attr}\")"
        else:
            # 使用 C 的点号访问
            return f"{value}.{node.attr}"
    
    def _expr_LambdaExpr(self, node) -> str:
        """处理Lambda表达式作为表达式
        
        返回lambda对象（PyObject*），使用PyCFunction_New创建
        """
        # 使用节点上保存的索引获取lambda信息
        lambda_index = getattr(node, '_lambda_index', 0)
        if lambda_index > 0:
            method_name = f"_lambda_method_{lambda_index}"
            return f"PyCFunction_New((PyMethodDef*)&{method_name}, NULL)"
        return "NULL"
    
    def _expr_ListComp(self, node) -> str:
        """处理列表推导式作为表达式"""
        # 调用_visit_ListComp生成列表推导式代码
        self._visit_ListComp(node)
        # 返回结果列表变量名
        return "_listcomp_result"
    
    def _expr_Subscript(self, node) -> str:
        value = self._expr_to_str(node.value)
        slice_val = self._expr_to_str(node.slice)
        return f"{value}[{slice_val}]"
    
    def _expr_DerefExpr(self, node) -> str:
        operand = self._expr_to_str(node.operand)
        return f"*({operand})"
    
    def _expr_VecLiteral(self, node) -> str:
        """处理SIMD向量字面量 - vec![v1, v2, ...] 或 vec![value; Size]"""
        # 判断元素类型（默认float）
        elem_type = "f32"
        if node.elements and hasattr(node.elements[0], 'value'):
            if isinstance(node.elements[0].value, int):
                elem_type = "i32"
            elif isinstance(node.elements[0].value, float):
                elem_type = "f32"
        
        size = node.size or len(node.elements)
        
        if node.size is not None:
            # vec![value; Size] 重复形式
            value = self._expr_to_str(node.elements[0])
            return f"_vec_splat_{elem_type}({value})"
        else:
            # vec![v1, v2, ...] 列表形式
            elements = ", ".join(self._expr_to_str(e) for e in node.elements)
            return f"_vec_make_{elem_type}_{size}({elements})"
    
    def _expr_ComptimeStmt(self, node) -> str:
        """处理编译期表达式 - comptime: expr 作为表达式值使用"""
        expr = node.expr
        
        # 尝试在编译时求值表达式
        try:
            result = self._evaluate_constant(expr)
            if result is not None:
                # 返回编译期求值结果
                if isinstance(result, int):
                    return str(result)
                elif isinstance(result, float):
                    return str(result)
                elif isinstance(result, str):
                    return f'"{result}"'
                else:
                    return str(result)
            else:
                # 无法求值，返回表达式本身
                return self._expr_to_str(expr)
        except Exception:
            # 求值失败，返回表达式本身
            return self._expr_to_str(expr)
    
    def _expr_BacktickBlock(self, node) -> str:
        """处理反引号代码块表达式"""
        # 反引号代码块通常在宏展开时处理，这里返回空字符串
        return ""
    
    def _expr_BuildBlockExpr(self, node) -> str:
        """处理构建块表达式"""
        return "_buildblock_result"
    
    def _expr_BuildValueExpr(self, node) -> str:
        """处理构建值表达式"""
        if node.value:
            return self._expr_to_str(node.value)
        return "NULL"
    
    def _expr_PipeExpr(self, node) -> str:
        """处理管道表达式 - x |> f |> g 转换为 g(f(x))"""
        # 管道表达式：将左侧表达式作为右侧函数的参数
        left = self._expr_to_str(node.left)
        right = self._expr_to_str(node.right)
        return f"{right}({left})"
    
    def _expr_VecType(self, node) -> str:
        """处理向量类型表达式"""
        elem_type = self._type_to_c(node.element_type)
        return f"Vec{elem_type}_{node.size}"
    
    # ============ 辅助方法 ============
    
    def _collect_features(self, node):
        """遍历AST节点，收集需要的特性（如SIMD、lambda）"""
        if hasattr(node, 'kind'):
            if node.kind in ('VecType', 'VecLiteral'):
                self.needs_simd = True
            if node.kind == 'LambdaExpr':
                # 收集lambda表达式
                if not hasattr(self, 'lambda_functions'):
                    self.lambda_functions = []
                self.lambda_counter = getattr(self, 'lambda_counter', 0) + 1
                lambda_index = self.lambda_counter
                # 在节点上保存索引，以便_expr_LambdaExpr能够正确获取
                node._lambda_index = lambda_index
                self.lambda_functions.append({
                    'name': f"_lambda_{lambda_index}",
                    'method_name': f"_lambda_method_{lambda_index}",
                    'obj_name': f"_lambda_obj_{lambda_index}",
                    'params': node.params,
                    'body': node.body,
                    'line': node.line,
                    'col': node.col,
                })
        
        # 递归遍历子节点
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if hasattr(value, 'kind'):
                    self._collect_features(value)
                elif isinstance(value, list):
                    for item in value:
                        if hasattr(item, 'kind'):
                            self._collect_features(item)
    
    def _collect_spawn_funcs(self, node):
        """预收集所有spawn/go语句的包装函数信息
        
        在模块访问开始时调用，这样可以在函数声明阶段就知道所有需要的包装函数
        为每个spawn/go语句分配唯一的函数名并存储在节点的临时属性中
        """
        if hasattr(node, 'kind'):
            if node.kind == 'SpawnStmt':
                # 为spawn语句分配包装函数名
                self.spawn_counter += 1
                if node.body:
                    func_name = f"_spawn_func_{self.spawn_counter}"
                else:
                    func_name = f"_spawn_wrapper_{self.spawn_counter}"
                # 将函数名存储在节点上
                node._wrapper_func_name = func_name
                # 添加声明到spawn_wrapper_decls列表
                self.spawn_wrapper_decls.append(f"static void* {func_name}(void* arg);")
            elif node.kind == 'GoStmt':
                # 为go语句分配包装函数名
                self.go_counter += 1
                if node.body:
                    func_name = f"_go_func_{self.go_counter}"
                else:
                    func_name = f"_go_wrapper_{self.go_counter}"
                # 将函数名存储在节点上
                node._wrapper_func_name = func_name
                # 添加声明到spawn_wrapper_decls列表
                self.spawn_wrapper_decls.append(f"static void* {func_name}(void* arg);")
        
        # 递归遍历子节点
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if hasattr(value, 'kind'):
                    self._collect_spawn_funcs(value)
                elif isinstance(value, list):
                    for item in value:
                        if hasattr(item, 'kind'):
                            self._collect_spawn_funcs(item)
    
    # ============ 语句处理 ============
    
    def _visit_Module(self, node):
        """处理模块"""
        self._write(f"// Generated by Cypy Bridge Compiler")
        self._write(f"// Module: {self.module_name}")
        self._write()
        
        # 写入头文件
        self._write("#include <Python.h>")
        self._write("#include <stdlib.h>")
        self._write("#include <stdio.h>")
        self._write("#include <string.h>")
        
        # 先收集所有spawn语句的包装函数信息（避免函数声明顺序问题）
        self._collect_spawn_funcs(node)
        
        # 检查是否需要SIMD支持（在访问节点后确定）
        # 先收集需要的特性
        self._collect_features(node)
        
        # SIMD支持（按需生成）
        if self.needs_simd:
            self._write("#include <emmintrin.h>")  # SSE2
            self._write("#include <smmintrin.h>")  # SSE4.1
            self._write("#include <immintrin.h>")  # AVX/AVX2
            self._write()
            
            # SIMD向量类型定义和辅助函数
            self._write("// ============ SIMD Vector Types ============")
            self._write()
            
            # 向量类型别名
            self._write("typedef __m128 VecFloat32_4;")
            self._write("typedef __m128i VecInt32_4;")
            self._write("typedef __m128i VecInt16_8;")
            self._write("typedef __m128i VecInt8_16;")
            self._write("typedef __m256 VecFloat32_8;")
            self._write("typedef __m256i VecInt32_8;")
            self._write("typedef __m256i VecInt16_16;")
            self._write("typedef __m256i VecInt8_32;")
        self._write()
        
        # SIMD向量辅助函数（按需生成）
        if self.needs_simd:
            # 向量创建辅助函数
            self._write("// 创建向量（float32 x4）")
            self._write("static VecFloat32_4 _vec_make_f32_4(float v0, float v1, float v2, float v3) {")
            self._write("    return _mm_set_ps(v3, v2, v1, v0);")
            self._write("}")
            self._write()
            
            self._write("// 创建向量（int32 x4）")
            self._write("static VecInt32_4 _vec_make_i32_4(int v0, int v1, int v2, int v3) {")
            self._write("    return _mm_set_epi32(v3, v2, v1, v0);")
            self._write("}")
            self._write()
            
            self._write("// 创建向量（int32 x8）")
            self._write("static VecInt32_8 _vec_make_i32_8(int v0, int v1, int v2, int v3, int v4, int v5, int v6, int v7) {")
            self._write("    return _mm256_set_epi32(v7, v6, v5, v4, v3, v2, v1, v0);")
            self._write("}")
            self._write()
            
            self._write("// 广播值到向量（float32 x4）")
            self._write("static VecFloat32_4 _vec_splat_f32(float v) {")
            self._write("    return _mm_set1_ps(v);")
            self._write("}")
            self._write()
            
            self._write("// 广播值到向量（int32 x4）")
            self._write("static VecInt32_4 _vec_splat_i32(int v) {")
            self._write("    return _mm_set1_epi32(v);")
            self._write("}")
            self._write()
            
            # 向量运算辅助函数
            self._write("// 向量加法（float32）")
            self._write("static VecFloat32_4 _vec_add_f32(VecFloat32_4 a, VecFloat32_4 b) {")
            self._write("    return _mm_add_ps(a, b);")
            self._write("}")
            self._write()
            
            self._write("// 向量减法（float32）")
            self._write("static VecFloat32_4 _vec_sub_f32(VecFloat32_4 a, VecFloat32_4 b) {")
            self._write("    return _mm_sub_ps(a, b);")
            self._write("}")
            self._write()
            
            self._write("// 向量乘法（float32）")
            self._write("static VecFloat32_4 _vec_mul_f32(VecFloat32_4 a, VecFloat32_4 b) {")
            self._write("    return _mm_mul_ps(a, b);")
            self._write("}")
            self._write()
            
            self._write("// 向量加法（int32）")
            self._write("static VecInt32_4 _vec_add_i32(VecInt32_4 a, VecInt32_4 b) {")
            self._write("    return _mm_add_epi32(a, b);")
            self._write("}")
            self._write()
            
            self._write("// 向量减法（int32）")
            self._write("static VecInt32_4 _vec_sub_i32(VecInt32_4 a, VecInt32_4 b) {")
            self._write("    return _mm_sub_epi32(a, b);")
            self._write("}")
            self._write()
            
            self._write("// 向量乘法（int32）")
            self._write("static VecInt32_4 _vec_mul_i32(VecInt32_4 a, VecInt32_4 b) {")
            self._write("    return _mm_mullo_epi32(a, b);")
            self._write("}")
            self._write()
            
            self._write("// 向量点积（float32）")
            self._write("static float _vec_dot_f32(VecFloat32_4 a, VecFloat32_4 b) {")
            self._write("    VecFloat32_4 tmp = _mm_mul_ps(a, b);")
            self._write("    tmp = _mm_hadd_ps(tmp, tmp);")
            self._write("    tmp = _mm_hadd_ps(tmp, tmp);")
            self._write("    return _mm_cvtss_f32(tmp);")
            self._write("}")
            self._write()
            
            self._write("// 向量水平求和（float32）")
            self._write("static float _vec_hsum_f32(VecFloat32_4 v) {")
            self._write("    v = _mm_hadd_ps(v, v);")
            self._write("    v = _mm_hadd_ps(v, v);")
            self._write("    return _mm_cvtss_f32(v);")
            self._write("}")
            self._write()
            
            self._write("// 提取向量元素")
            self._write("static float _vec_extract_f32(VecFloat32_4 v, int idx) {")
            self._write("    float arr[4];")
            self._write("    _mm_storeu_ps(arr, v);")
            self._write("    return arr[idx];")
            self._write("}")
            self._write()
            
            self._write("// 提取向量元素（int32）")
            self._write("static int _vec_extract_i32(VecInt32_4 v, int idx) {")
            self._write("    int arr[4];")
            self._write("    _mm_storeu_si128((__m128i*)arr, v);")
            self._write("    return arr[idx];")
            self._write("}")
            self._write()
            
            self._write("// ============ End SIMD Vector Types ============")
            self._write()
        
        self._write()
        
        # 生成Lambda函数定义（在文件开头，确保被函数内部引用时已定义）
        lambda_functions = getattr(self, 'lambda_functions', [])
        if lambda_functions:
            self._write("// ============ Lambda Functions ============")
            self._write()
            for lambda_info in lambda_functions:
                self._generate_lambda_function(lambda_info)
            self._write("// ============ End Lambda Functions ============")
            self._write()
        
        # 收集结构体、枚举、Trait定义、类型别名、宏定义
        type_aliases = []
        macros = []
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                if stmt.kind == 'StructDef':
                    self.structs.append(stmt)
                elif stmt.kind == 'EnumDef':
                    self.enums.append(stmt)
                elif stmt.kind == 'TraitDef':
                    self.traits.append(stmt)
                elif stmt.kind == 'TypeAlias':
                    type_aliases.append(stmt)
                elif stmt.kind == 'MacroDef':
                    macros.append(stmt)
        
        # 收集Impl语句
        for stmt in node.body:
            if hasattr(stmt, 'kind') and stmt.kind == 'ImplStmt':
                self.impls.append(stmt)
        
        # 生成类型别名
        for alias in type_aliases:
            self._visit_TypeAlias(alias)
        
        # 生成宏定义
        for macro in macros:
            self._visit_MacroDef(macro)
        
        # 生成结构体
        for struct in self.structs:
            self._visit_StructDef(struct)
        
        # 生成枚举
        for enum in self.enums:
            self._visit_EnumDef(enum)
        
        # 生成Trait（函数指针结构体）
        for trait in self.traits:
            self._visit_TraitDef(trait)
        
        # 生成其他顶层语句（如ComptimeStmt）
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                if stmt.kind not in ('StructDef', 'EnumDef', 'TraitDef', 'TypeAlias', 'MacroDef', 'FuncDef', 'ImplStmt'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
        
        # 生成函数声明（包括普通函数和Impl中的方法）
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                if stmt.kind == 'FuncDef':
                    self._visit_FuncDef_Decl(stmt)
                elif stmt.kind == 'ImplStmt':
                    for method in stmt.methods:
                        self._visit_FuncDef_Decl(method)
        
        # 生成spawn/go包装函数声明（在函数声明之后）
        if self.spawn_wrapper_decls:
            for decl in self.spawn_wrapper_decls:
                self._write(decl)
        
        self._write()
        
        # 生成函数定义
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                if stmt.kind == 'FuncDef':
                    self._visit_FuncDef(stmt)
                elif stmt.kind == 'ImplStmt':
                    # 生成Impl中的方法定义
                    for method in stmt.methods:
                        self._visit_FuncDef(method)
        
        # 生成Impl实例（结构体实例初始化）
        for impl in self.impls:
            self._visit_ImplStmt(impl)
        
        # 生成spawn/go包装函数（在函数定义之后、Python模块之前）
        if self.spawn_wrapper_defs:
            self._write("// ============ Spawn/Go Wrapper Functions ============")
            self._write()
            for wrapper_func in self.spawn_wrapper_defs:
                self._write(wrapper_func)
            self._write("// ============ End Spawn/Go Wrapper Functions ============")
            self._write()
        
        # 生成 Python 模块初始化（包含包装函数）
        self._generate_python_module()
    
    def _visit_StructDef(self, node):
        """处理结构体定义，支持泛型参数"""
        # 生成泛型结构体名称，如 Container_T
        struct_name = node.name
        if hasattr(node, 'generic_params') and node.generic_params:
            struct_name = f"{node.name}_{'_'.join(node.generic_params)}"
        
        self._write(f"typedef struct {struct_name} {{")
        self.indent += 1
        for field in node.fields:
            if hasattr(field, 'name'):
                field_type = self._type_to_c(field.type_annotation) if hasattr(field, 'type_annotation') else 'void*'
                self._write(f"{field_type} {field.name};")
        self.indent -= 1
        self._write(f"}} {struct_name};")
        self._write()
    
    def _visit_EnumDef(self, node):
        """处理枚举定义"""
        self._write(f"typedef enum {node.name} {{")
        self.indent += 1
        for variant in node.variants:
            if hasattr(variant, 'name'):
                if variant.value is not None:
                    self._write(f"{node.name}_{variant.name} = {self._expr_to_str(variant.value)},")
                else:
                    self._write(f"{node.name}_{variant.name},")
        self.indent -= 1
        self._write(f"}} {node.name};")
        self._write()
    
    def _visit_TraitDef(self, node):
        """处理Trait定义（转换为函数指针结构体）"""
        self._write(f"// Trait: {node.name}")
        self._write(f"typedef struct {node.name}_VTable {{")
        self.indent += 1
        for method in node.methods:
            return_type = self._type_to_c(method.return_type)
            params = []
            for param in method.params:
                param_type = self._type_to_c(param.type_annotation) if hasattr(param, 'type_annotation') else 'void*'
                params.append(f"{param_type}")
            params_str = ", ".join(params)
            self._write(f"{return_type} (*{method.name})({params_str});")
        self.indent -= 1
        self._write(f"}} {node.name}_VTable;")
        self._write()
        self._write(f"typedef struct {node.name} {{")
        self.indent += 1
        self._write(f"{node.name}_VTable* vtable;")
        self._write(f"void* data;")
        self.indent -= 1
        self._write(f"}} {node.name};")
        self._write()
    
    def _visit_ImplStmt(self, node):
        """处理Impl语句（生成Trait实例）"""
        trait_name = node.trait_name
        for_type = self._type_to_c(node.for_type) if hasattr(node.for_type, 'id') else str(node.for_type)
        impl_name = f"impl_{trait_name}_{for_type}"
        
        # 生成Impl实例
        self._write()
        self._write(f"// Impl {trait_name} for {for_type}")
        self._write(f"static {trait_name}_VTable {impl_name}_vtable = {{")
        self.indent += 1
        for method in node.methods:
            self._write(f".{method.name} = {method.name},")
        self.indent -= 1
        self._write(f"}};")
        self._write()
    
    def _get_func_name(self, node):
        """获取函数名，支持泛型"""
        func_name = node.name
        if hasattr(node, 'generic_params') and node.generic_params:
            # 添加泛型参数后缀，如 add_T_U
            suffix = "_".join(node.generic_params)
            func_name = f"{func_name}_{suffix}"
        return func_name
    
    def _visit_FuncDef_Decl(self, node):
        """生成函数声明"""
        # 跳过async函数和生成器函数的声明（它们的真正入口是create函数）
        is_async = getattr(node, 'is_async', False)
        if is_async:
            return
        
        # 检查是否是生成器函数
        has_yield = any(hasattr(s, 'kind') and s.kind == 'YieldStmt' for s in node.body)
        if has_yield:
            return
        
        return_type = self._type_to_c(node.return_type)
        params = []
        for param in node.params:
            param_type = self._type_to_c(param.type_annotation) if hasattr(param, 'type_annotation') else 'void*'
            params.append(f"{param_type} {param.name}")
        params_str = ", ".join(params)
        func_name = self._get_func_name(node)
        self._write(f"{return_type} {func_name}({params_str});")
    
    def _visit_FuncDef(self, node):
        """处理函数定义"""
        return_type = self._type_to_c(node.return_type)
        params = []
        for param in node.params:
            param_type = self._type_to_c(param.type_annotation) if hasattr(param, 'type_annotation') else 'void*'
            params.append(f"{param_type} {param.name}")
        params_str = ", ".join(params)
        func_name = self._get_func_name(node)
        
        # 收集 defer 语句
        defer_stmts = []
        normal_stmts = []
        for stmt in node.body:
            if hasattr(stmt, 'kind') and stmt.kind == 'DeferStmt':
                defer_stmts.append(stmt)
            else:
                normal_stmts.append(stmt)
        
        # 设置当前函数返回类型（用于 assert/return 语句）
        self.current_return_type = return_type
        
        # 设置当前函数参数和体（用于类型推断）
        self._current_func_params = node.params
        self._current_func_body = normal_stmts
        
        # 检查函数是否包含yield语句（递归检查所有嵌套节点）
        def has_yield_in_node(node):
            if hasattr(node, 'kind') and node.kind == 'YieldStmt':
                return True
            for attr in dir(node):
                if not attr.startswith("_"):
                    value = getattr(node, attr)
                    if hasattr(value, 'kind'):
                        if has_yield_in_node(value):
                            return True
                    elif isinstance(value, list):
                        for item in value:
                            if hasattr(item, 'kind') and has_yield_in_node(item):
                                return True
            return False
        
        has_yield = any(has_yield_in_node(s) for s in normal_stmts)
        
        # 检查函数是否是async函数
        is_async = getattr(node, 'is_async', False)
        
        # 处理装饰器（生成注释标记）
        for decorator in getattr(node, 'decorators', []):
            self._visit_Decorator(decorator, func_name)
        
        if has_yield:
            # 生成器函数：创建迭代器类型和__next__方法
            self._generate_generator_iterator(func_name, return_type, params, params_str, normal_stmts, defer_stmts)
        elif is_async:
            # async函数：创建协程对象
            self._generate_async_coroutine(func_name, return_type, params, params_str, normal_stmts, defer_stmts)
        else:
            # 普通函数
            self._write()
            self._write(f"{return_type} {func_name}({params_str}) {{")
            self.indent += 1
            
            # 在函数体开头添加 checker 调用（如果有）
            params_checker = getattr(node, 'params_checker', None)
            if params_checker:
                self._write(f"{params_checker}();")
                self._write()
            
            # 生成普通语句（处理return时插入defer代码）
            for stmt in normal_stmts:
                if hasattr(stmt, 'kind'):
                    if stmt.kind == 'ReturnStmt' and defer_stmts:
                        # 在return之前生成defer代码
                        self._write()
                        self._write("// defer cleanup")
                        for defer_stmt in reversed(defer_stmts):
                            for s in defer_stmt.body:
                                if hasattr(s, 'kind'):
                                    method = f"_visit_{s.kind}"
                                    if hasattr(self, method):
                                        getattr(self, method)(s)
                                    else:
                                        self._write(self._expr_to_str(s) + ";")
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
            
            # 如果没有return语句，在函数末尾生成defer代码
            has_return = any(hasattr(s, 'kind') and s.kind == 'ReturnStmt' for s in normal_stmts)
            if defer_stmts and not has_return:
                self._write()
                self._write("// defer cleanup")
                for defer_stmt in reversed(defer_stmts):
                    for stmt in defer_stmt.body:
                        if hasattr(stmt, 'kind'):
                            method = f"_visit_{stmt.kind}"
                            if hasattr(self, method):
                                getattr(self, method)(stmt)
                            else:
                                self._write(self._expr_to_str(stmt) + ";")
            
            self.indent -= 1
            self._write("}")
            self._write()
    
    def _generate_generator_iterator(self, func_name, return_type, params, params_str, body_stmts, defer_stmts):
        """生成生成器迭代器类型和相关方法"""
        # 收集函数体中的局部变量
        local_vars = []
        
        def collect_vars(stmts):
            for stmt in stmts:
                if hasattr(stmt, 'kind'):
                    if stmt.kind == 'LetStmt':
                        var_type = self._type_to_c(stmt.type_annotation) if hasattr(stmt, 'type_annotation') and stmt.type_annotation else 'int'
                        local_vars.append((var_type, stmt.name))
                    # 递归收集嵌套块中的变量
                    for attr in ['body', 'orelse', 'cases']:
                        nested = getattr(stmt, attr, None)
                        if isinstance(nested, list):
                            collect_vars(nested)
        
        collect_vars(body_stmts)
        
        # 生成器状态结构体
        gen_struct_name = f"_{func_name}_Generator"
        self._write(f"// Generator iterator struct for {func_name}")
        self._write(f"typedef struct {gen_struct_name} {{")
        self.indent += 1
        self._write("PyObject_HEAD")
        self._write(f"    int _gen_state;")
        self._write(f"    int _finished;")
        # 添加参数作为成员变量（用于状态机恢复）
        for param in params:
            parts = param.split()
            if len(parts) >= 2:
                p_type = " ".join(parts[:-1])
                p_name = parts[-1]
                self._write(f"    {p_type} _param_{p_name};")
        # 添加局部变量作为成员变量（用于状态机恢复）
        for var_type, var_name in local_vars:
            self._write(f"    {var_type} _var_{var_name};")
        self._write(f"    {return_type} _last_value;")
        self.indent -= 1
        self._write(f"}} {gen_struct_name};")
        self._write()
        
        # 先声明函数原型（确保类型对象可以引用）
        gen_return_type = return_type if return_type != "void" else "int"
        self._write(f"// Generator function prototypes")
        self._write(f"static PyObject* {func_name}_create({params_str});")
        self._write(f"static PyObject* {func_name}_iter(PyObject* self);")
        self._write(f"static {gen_return_type} {func_name}_next({gen_struct_name}* gen);")
        self._write(f"static PyObject* {func_name}_next_wrapper(PyObject* self);")
        self._write()
        
        # 生成器对象的类型对象（简化版，在模块初始化时设置必要字段）
        self._write(f"static PyTypeObject {gen_struct_name}_Type = {{")
        self.indent += 1
        self._write("PyVarObject_HEAD_INIT(NULL, 0)")
        self._write(f"    \"{self.module_name}.{func_name}\",")
        self._write(f"    sizeof({gen_struct_name}),")
        self._write("};")
        self._write()
        
        # 生成器创建函数（替代原函数）
        self._write(f"static PyObject* {func_name}_create({params_str}) {{")
        self.indent += 1
        self._write(f"    {gen_struct_name}* gen = PyObject_New({gen_struct_name}, &{gen_struct_name}_Type);")
        self._write("    if (!gen) return NULL;")
        self._write("    gen->_gen_state = 0;")
        self._write("    gen->_finished = 0;")
        # 保存参数
        for param in params:
            parts = param.split()
            if len(parts) >= 2:
                p_name = parts[-1]
                self._write(f"    gen->_param_{p_name} = {p_name};")
        self._write("    return (PyObject*)gen;")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 生成器__iter__方法
        self._write(f"static PyObject* {func_name}_iter(PyObject* self) {{")
        self.indent += 1
        self._write("    Py_INCREF(self);")
        self._write("    return self;")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 生成器状态机核心函数（原函数体）
        # 使用 int 作为返回类型，便于统一处理（实际返回值通过 Python 对象传递）
        gen_return_type = return_type if return_type != "void" else "int"
        
        # 设置生成器上下文标志
        self._in_generator = True
        self._generator_params = {param.split()[-1] for param in params if len(param.split()) >= 2}
        self._generator_locals = {var_name for _, var_name in local_vars}
        
        self._write(f"static {gen_return_type} {func_name}_next({gen_struct_name}* gen) {{")
        self.indent += 1
        
        # 检查是否已完成
        self._write("    if (gen->_finished) {")
        self._write("        PyErr_SetNone(PyExc_StopIteration);")
        self._write("        return 0;")
        self._write("    }")
        
        # 状态机框架
        self._write("    switch(gen->_gen_state) {")
        self.indent += 1
        self._write("    case 0:")
        
        # 重置状态计数
        self.yield_state = 0
        
        # 生成函数体语句（使用 gen->_var_xxx 形式访问变量）
        for stmt in body_stmts:
            if hasattr(stmt, 'kind'):
                if stmt.kind == 'ReturnStmt' and defer_stmts:
                    # 在return之前生成defer代码
                    self._write()
                    self._write("// defer cleanup")
                    for defer_stmt in reversed(defer_stmts):
                        for s in defer_stmt.body:
                            if hasattr(s, 'kind'):
                                method = f"_visit_{s.kind}"
                                if hasattr(self, method):
                                    getattr(self, method)(s)
                                else:
                                    self._write(self._expr_to_str(s) + ";")
                elif stmt.kind == 'YieldStmt':
                    # 特殊处理yield：使用生成器状态
                    value = self._expr_to_str(stmt.value) if stmt.value else "0"
                    self.yield_state += 1
                    next_state = self.yield_state
                    self._write(f"// yield {value}")
                    self._write(f"    gen->_gen_state = {next_state};")
                    self._write(f"    gen->_last_value = {value};")
                    self._write(f"    return {value};")
                    self._write(f"    case {next_state}:")
                elif stmt.kind == 'Assign':
                    # Assign: 使用 _visit_Assign 方法（会自动处理生成器上下文）
                    self._visit_Assign(stmt)
                else:
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
        
        # 如果没有return语句，在函数末尾生成defer代码
        has_return = any(hasattr(s, 'kind') and s.kind == 'ReturnStmt' for s in body_stmts)
        if defer_stmts and not has_return:
            self._write()
            self._write("// defer cleanup")
            for defer_stmt in reversed(defer_stmts):
                for stmt in defer_stmt.body:
                    if hasattr(stmt, 'kind'):
                        method = f"_visit_{stmt.kind}"
                        if hasattr(self, method):
                            getattr(self, method)(stmt)
                        else:
                            self._write(self._expr_to_str(stmt) + ";")
        
        # 函数结束：标记完成
        self._write("    default:")
        self._write("        gen->_finished = 1;")
        self._write("        PyErr_SetNone(PyExc_StopIteration);")
        self._write("        return 0;")
        
        self.indent -= 1
        self._write("    }")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 重置生成器上下文标志
        self._in_generator = False
        self._generator_params = set()
        self._generator_locals = set()
        
        # 生成器__next__方法
        self._write(f"static PyObject* {func_name}_next_wrapper(PyObject* self) {{")
        self.indent += 1
        self._write(f"    {gen_struct_name}* gen = ({gen_struct_name}*)self;")
        self._write(f"    {gen_return_type} result = {func_name}_next(gen);")
        self._write("    if (PyErr_Occurred()) return NULL;")
        
        # 根据返回类型转换为Python对象
        if return_type == "int":
            self._write("    return PyLong_FromLong((long)result);")
        elif return_type == "long":
            self._write("    return PyLong_FromLong(result);")
        elif return_type == "long long":
            self._write("    return PyLong_FromLongLong(result);")
        elif return_type == "float":
            self._write("    return PyFloat_FromDouble((double)result);")
        elif return_type == "double":
            self._write("    return PyFloat_FromDouble(result);")
        elif return_type == "_Bool":
            self._write("    return PyBool_FromLong((long)result);")
        elif return_type == "const char*":
            self._write("    return PyUnicode_FromString(result);")
        elif return_type == "PyObject*":
            self._write("    Py_INCREF(result);")
            self._write("    return result;")
        else:
            self._write("    return PyLong_FromLong((long)result);")
        
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 保存生成器信息用于模块初始化
        if not hasattr(self, 'generators'):
            self.generators = []
        self.generators.append({
            'name': func_name,
            'create_func': f"{func_name}_create",
            'iter_func': f"{func_name}_iter",
            'next_func': f"{func_name}_next_wrapper",
            'params': params,
            'return_type': return_type,
        })
    
    def _generate_async_coroutine(self, func_name, return_type, params, params_str, body_stmts, defer_stmts):
        """生成异步协程类型和相关方法"""
        # 收集函数体中的局部变量
        local_vars = []
        
        def collect_vars(stmts):
            for stmt in stmts:
                if hasattr(stmt, 'kind'):
                    if stmt.kind == 'LetStmt':
                        var_type = self._type_to_c(stmt.type_annotation) if hasattr(stmt, 'type_annotation') and stmt.type_annotation else 'int'
                        local_vars.append((var_type, stmt.name))
                    # 递归收集嵌套块中的变量
                    for attr in ['body', 'orelse', 'cases']:
                        nested = getattr(stmt, attr, None)
                        if isinstance(nested, list):
                            collect_vars(nested)
        
        collect_vars(body_stmts)
        
        # 协程状态结构体
        coro_struct_name = f"_{func_name}_Coroutine"
        self._write(f"// Async coroutine struct for {func_name}")
        self._write(f"typedef struct {coro_struct_name} {{")
        self.indent += 1
        self._write("PyObject_HEAD")
        self._write(f"    int _coro_state;")
        self._write(f"    int _finished;")
        # 添加参数作为成员变量
        for param in params:
            parts = param.split()
            if len(parts) >= 2:
                p_type = " ".join(parts[:-1])
                p_name = parts[-1]
                self._write(f"    {p_type} _param_{p_name};")
        # 添加局部变量作为成员变量
        for var_type, var_name in local_vars:
            self._write(f"    {var_type} _var_{var_name};")
        self._write(f"    PyObject* _last_value;")
        self.indent -= 1
        self._write(f"}} {coro_struct_name};")
        self._write()
        
        # 协程对象的类型对象（简化版，在模块初始化时设置必要字段）
        self._write(f"static PyTypeObject {coro_struct_name}_Type = {{")
        self.indent += 1
        self._write("PyVarObject_HEAD_INIT(NULL, 0)")
        self._write(f"    \"{self.module_name}.{func_name}\",")
        self._write(f"    sizeof({coro_struct_name}),")
        self._write("};")
        self._write()
        
        # 协程创建函数（替代原函数）- 返回一个包装协程的Python函数
        self._write(f"static PyObject* {func_name}_create({params_str}) {{")
        self.indent += 1
        # 先创建底层协程对象
        self._write(f"    {coro_struct_name}* coro = PyObject_New({coro_struct_name}, &{coro_struct_name}_Type);")
        self._write("    if (!coro) return NULL;")
        self._write("    coro->_coro_state = 0;")
        self._write("    coro->_finished = 0;")
        self._write("    coro->_last_value = NULL;")
        # 保存参数
        for param in params:
            parts = param.split()
            if len(parts) >= 2:
                p_name = parts[-1]
                self._write(f"    coro->_param_{p_name} = {p_name};")
        # 返回协程对象（作为Python对象）
        self._write("    return (PyObject*)coro;")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 协程 __await__ 方法（实现协程协议）
        self._write(f"static PyObject* {func_name}_await(PyObject* self) {{")
        self.indent += 1
        self._write("    Py_INCREF(self);")
        self._write("    return self;")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 协程 __repr__ 方法
        self._write(f"static PyObject* {func_name}_repr(PyObject* self) {{")
        self.indent += 1
        self._write(f"    return PyUnicode_FromFormat(\"<{self.module_name}.{func_name} coroutine>\");")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 协程状态机核心函数
        # 设置协程上下文标志
        self._in_coroutine = True
        self._coroutine_params = {param.split()[-1] for param in params if len(param.split()) >= 2}
        self._coroutine_locals = {var_name for _, var_name in local_vars}
        
        self._write(f"static PyObject* {func_name}_resume({coro_struct_name}* coro) {{")
        self.indent += 1
        
        # 检查是否已完成
        self._write("    if (coro->_finished) {")
        self._write("        PyErr_SetNone(PyExc_StopAsyncIteration);")
        self._write("        return NULL;")
        self._write("    }")
        
        # 状态机框架
        self._write("    switch(coro->_coro_state) {")
        self.indent += 1
        self._write("    case 0:")
        
        # 重置状态计数
        self.yield_state = 0
        
        # 生成函数体语句
        for stmt in body_stmts:
            if hasattr(stmt, 'kind'):
                if stmt.kind == 'ReturnStmt' and defer_stmts:
                    # 在return之前生成defer代码
                    self._write()
                    self._write("// defer cleanup")
                    for defer_stmt in reversed(defer_stmts):
                        for s in defer_stmt.body:
                            if hasattr(s, 'kind'):
                                method = f"_visit_{s.kind}"
                                if hasattr(self, method):
                                    getattr(self, method)(s)
                                else:
                                    self._write(self._expr_to_str(s) + ";")
                elif stmt.kind == 'AwaitExpr':
                    # 特殊处理await：保存状态并返回待等待对象
                    value_str = self._expr_to_str(stmt.value) if stmt.value else "NULL"
                    self.yield_state += 1
                    next_state = self.yield_state
                    self._write(f"// await {value_str}")
                    self._write(f"    coro->_coro_state = {next_state};")
                    self._write(f"    PyObject* _await_obj = ({value_str});")
                    self._write("    Py_XINCREF(_await_obj);")
                    self._write("    return _await_obj;")
                    self._write(f"    case {next_state}:")
                elif stmt.kind == 'Assign' and hasattr(stmt.value, 'kind') and stmt.value.kind == 'AwaitExpr':
                    # 特殊处理包含await的赋值语句
                    target_str = self._expr_to_str(stmt.target)
                    value_str = self._expr_to_str(stmt.value.value) if stmt.value.value else "NULL"
                    self.yield_state += 1
                    next_state = self.yield_state
                    self._write(f"// await {value_str} -> {target_str}")
                    self._write(f"    coro->_coro_state = {next_state};")
                    self._write(f"    PyObject* _await_obj = ({value_str});")
                    self._write("    Py_XINCREF(_await_obj);")
                    self._write("    return _await_obj;")
                    self._write(f"    case {next_state}:")
                    self._write(f"    {target_str} = _await_obj;")
                else:
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
        
        # 如果没有return语句，在函数末尾生成defer代码
        has_return = any(hasattr(s, 'kind') and s.kind == 'ReturnStmt' for s in body_stmts)
        if defer_stmts and not has_return:
            self._write()
            self._write("// defer cleanup")
            for defer_stmt in reversed(defer_stmts):
                for stmt in defer_stmt.body:
                    if hasattr(stmt, 'kind'):
                        method = f"_visit_{stmt.kind}"
                        if hasattr(self, method):
                            getattr(self, method)(stmt)
                        else:
                            self._write(self._expr_to_str(stmt) + ";")
        
        # 函数结束：标记完成
        self._write("    default:")
        self._write("        coro->_finished = 1;")
        self._write("        PyErr_SetNone(PyExc_StopAsyncIteration);")
        self._write("        return NULL;")
        
        self.indent -= 1
        self._write("    }")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 重置协程上下文标志
        self._in_coroutine = False
        self._coroutine_params = set()
        self._coroutine_locals = set()
        
        # 保存协程信息用于模块初始化
        if not hasattr(self, 'coroutines'):
            self.coroutines = []
        self.coroutines.append({
            'name': func_name,
            'create_func': f"{func_name}_create",
            'resume_func': f"{func_name}_resume",
            'params': params,
            'return_type': return_type,
        })
    
    def _visit_LetStmt(self, node):
        """处理变量声明"""
        # 如果值是lambda表达式，使用PyObject*类型
        is_lambda = hasattr(node.value, 'kind') and node.value.kind == 'LambdaExpr'
        if is_lambda:
            var_type = 'PyObject*'
            # 记录lambda变量名，在调用时特殊处理
            if not hasattr(self, '_lambda_vars'):
                self._lambda_vars = set()
            self._lambda_vars.add(node.name)
        else:
            var_type = self._type_to_c(node.type_annotation) if node.type_annotation else 'void*'
        
        # 在生成器函数中，变量已经是结构体成员，不需要声明
        if getattr(self, '_in_generator', False):
            if node.value:
                self._write(f"    gen->_var_{node.name} = {self._expr_to_str(node.value)};")
            else:
                self._write(f"    gen->_var_{node.name} = 0;")
        # 在协程函数中，变量已经是结构体成员，不需要声明
        elif getattr(self, '_in_coroutine', False):
            if node.value:
                self._write(f"    coro->_var_{node.name} = {self._expr_to_str(node.value)};")
            else:
                self._write(f"    coro->_var_{node.name} = 0;")
        elif node.value:
            self._write(f"{var_type} {node.name} = {self._expr_to_str(node.value)};")
        else:
            self._write(f"{var_type} {node.name};")
    
    def _visit_Assign(self, node):
        """处理赋值语句"""
        target = self._expr_to_str(node.target)
        value = self._expr_to_str(node.value)
        self._write(f"{target} = {value};")
    
    def _visit_ReturnStmt(self, node):
        """处理返回语句"""
        if node.value:
            self._write(f"return {self._expr_to_str(node.value)};")
        else:
            self._write("return;")
    
    def _visit_IfStmt(self, node):
        """处理条件语句"""
        test = self._expr_to_str(node.test)
        self._write(f"if ({test}) {{")
        self.indent += 1
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                method = f"_visit_{stmt.kind}"
                if hasattr(self, method):
                    getattr(self, method)(stmt)
        self.indent -= 1
        self._write("}")
        
        if node.orelse:
            if isinstance(node.orelse, list) and len(node.orelse) > 0:
                first_orelse = node.orelse[0]
                if hasattr(first_orelse, 'kind') and first_orelse.kind == 'IfStmt':
                    # elif
                    self._write("else ")
                    self._visit_IfStmt(first_orelse)
                else:
                    # else
                    self._write("else {")
                    self.indent += 1
                    for stmt in node.orelse:
                        if hasattr(stmt, 'kind'):
                            method = f"_visit_{stmt.kind}"
                            if hasattr(self, method):
                                getattr(self, method)(stmt)
                    self.indent -= 1
                    self._write("}")
    
    def _visit_WhileStmt(self, node):
        """处理 while 循环"""
        test = self._expr_to_str(node.test)
        self._write(f"while ({test}) {{")
        self.indent += 1
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                method = f"_visit_{stmt.kind}"
                if hasattr(self, method):
                    getattr(self, method)(stmt)
        self.indent -= 1
        self._write("}")
    
    def _visit_ForStmt(self, node):
        """处理 for 循环"""
        target = self._expr_to_str(node.target)
        
        # 检查是否是range调用
        if hasattr(node.iter, 'kind') and node.iter.kind == 'Call':
            func = node.iter.func
            if hasattr(func, 'id') and func.id == 'range':
                # 处理 range(end), range(start, end), 或 range(start, end, step)
                args = node.iter.args
                if len(args) == 1:
                    # range(end) -> for (int i = 0; i < end; i++)
                    end = self._expr_to_str(args[0])
                    self._write(f"for (int {target} = 0; {target} < {end}; {target}++) {{")
                elif len(args) == 2:
                    # range(start, end) -> for (int i = start; i < end; i++)
                    start = self._expr_to_str(args[0])
                    end = self._expr_to_str(args[1])
                    self._write(f"for (int {target} = {start}; {target} < {end}; {target}++) {{")
                elif len(args) >= 3:
                    # range(start, end, step) -> for (int i = start; i < end; i += step)
                    start = self._expr_to_str(args[0])
                    end = self._expr_to_str(args[1])
                    step = self._expr_to_str(args[2])
                    self._write(f"for (int {target} = {start}; {target} < {end}; {target} += {step}) {{")
                else:
                    # 未知形式
                    iter_expr = self._expr_to_str(node.iter)
                    self._write(f"for ({target} : {iter_expr}) {{")
            else:
                iter_expr = self._expr_to_str(node.iter)
                self._write(f"for ({target} : {iter_expr}) {{")
        else:
            iter_expr = self._expr_to_str(node.iter)
            self._write(f"for ({target} : {iter_expr}) {{")
        
        self.indent += 1
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                method = f"_visit_{stmt.kind}"
                if hasattr(self, method):
                    getattr(self, method)(stmt)
        self.indent -= 1
        self._write("}")
    
    def _visit_BreakStmt(self, node):
        """处理 break 语句"""
        self._write("break;")
    
    def _visit_ContinueStmt(self, node):
        """处理 continue 语句"""
        self._write("continue;")
    
    _BUILTIN_EXCEPTION_NAMES = None

    def _builtin_exception_names(self):
        """CPython 内置异常名集合（其 C API 符号为 ``PyExc_<name>``），惰性构建"""
        if CCodeGenerator._BUILTIN_EXCEPTION_NAMES is None:
            import builtins
            names = set()
            for name in dir(builtins):
                obj = getattr(builtins, name, None)
                if isinstance(obj, type) and issubclass(obj, BaseException):
                    names.add(name)
            CCodeGenerator._BUILTIN_EXCEPTION_NAMES = frozenset(names)
        return CCodeGenerator._BUILTIN_EXCEPTION_NAMES

    def _exc_type_to_c(self, exc_type) -> str:
        """except 子句里的异常类型 → C 表达式

        CPython 的内置异常在 C 里的符号是 ``PyExc_<Name>``。旧实现把 ``ValueError``
        直接经 ``_expr_to_str`` 输出成裸 C 标识符，生成的 C 引用了未声明符号
        （MSVC C2065），也就是说任何 ``except ValueError`` 都无法编译。
        模块自身定义了同名类型时保留原样（走 ``_expr_to_str``）。
        """
        if exc_type is None:
            return "PyExc_BaseException"

        name = None
        if isinstance(exc_type, str):
            name = exc_type
        elif getattr(exc_type, 'kind', None) == 'Name':
            name = getattr(exc_type, 'id', None)

        if name and name in self._builtin_exception_names():
            if name not in getattr(self, "_module_type_names", set()):
                return f"PyExc_{name}"

        return self._expr_to_str(exc_type)

    def _visit_TryStmt(self, node):
        """处理 try/except/finally 语句

        使用 Python C API 的 PyErr_Occurred/PyErr_Fetch/PyErr_Restore 实现错误捕获。

        生成的 C 形状（整个构造自带一个 ``{ }`` 作用域，goto 标签按
        ``_try_<n>`` 唯一化，块内局部量靠作用域隔离，因此同一函数里的两个
        同级 try 不会重定义，嵌套 try 也不会互相覆盖挂起异常）::

            {
                PyObject* _exc_type = NULL; PyObject* _exc_value = NULL;
                PyObject* _exc_tb = NULL;
                PyObject* <handler名> = NULL;        // 提升到块作用域，finally 可见
                { <try 体> }
            _try_<n>_except_check: ;
                if (PyErr_Occurred()) {
                    PyErr_Fetch(&_exc_type, &_exc_value, &_exc_tb);
                    if (PyErr_GivenExceptionMatches(_exc_type, PyExc_X)) {
                        <绑定 handler名 + Py_INCREF>
                        <except 体>
                        <Py_DECREF handler名>
                        Py_XDECREF(_exc_type); Py_XDECREF(_exc_value); Py_XDECREF(_exc_tb);
                        _exc_type = NULL; _exc_value = NULL; _exc_tb = NULL;  // 已消费
                    }
                    // 其余 except 子句以 else if 串联
                }
            _try_<n>_finally: ;
                { <finally 体> }
                if (_exc_type != NULL) {            // 未被匹配的异常继续传播
                    PyErr_Restore(_exc_type, _exc_value, _exc_tb);
                    <按函数返回类型 return>
                }
            }

        注意：这里不再输出 ``PyErr_Clear()``。旧实现在每个 try 块头部无条件
        ``PyErr_Clear()``（销毁进入本块前已挂起的异常），并在每个 except 子句的
        if/else 之后无条件 ``PyErr_Clear()``（当非匹配分支 ``goto <内层>_finally``
        落到外层处理器的尾部时，会紧接 ``PyErr_Restore`` 把刚恢复的异常擦掉）。
        新实现用 ``Py_XDECREF`` 三元组消费已匹配的异常，用 ``PyErr_Restore`` 传播
        未匹配的异常，控制流全部靠顺序 fall-through，不再有跳向前端处理器尾部的
        ``goto``。
        """
        try_label = f"_try_{self.buildblock_counter}"
        self.buildblock_counter += 1

        handlers = list(node.handlers or [])
        finally_body = list(node.orelse or [])

        self._write("// try/except/finally block")
        self._write("{")
        self.indent += 1

        # 挂起异常的三段（块作用域：活得比 except 子句长，finally 之后仍能恢复）
        self._write("PyObject* _exc_type = NULL;")
        self._write("PyObject* _exc_value = NULL;")
        self._write("PyObject* _exc_tb = NULL;")

        # except 子句绑定的异常名也提升到块作用域，避免 finally 引用时
        # MSVC C2065（undeclared identifier）；同一块内同名只声明一次。
        bound_names = []
        for _exc_type_node, exc_name, _body in handlers:
            if exc_name and exc_name not in bound_names:
                bound_names.append(exc_name)
        for exc_name in bound_names:
            self._write(f"PyObject* {exc_name} = NULL;")

        # try 块：进入时不清除已有异常（清除会吞掉调用者遗留的错误指示器）
        old_try_label = self.current_try_label
        self.current_try_label = try_label

        self._write("{")
        self.indent += 1
        self._visit_stmts(node.body)
        self.indent -= 1
        self._write("}")

        # 恢复 try 标签：处理体内的 raise 由外层 try 捕获，不被本块再次匹配
        self.current_try_label = old_try_label

        self._write(f"{try_label}_except_check: ;")

        if handlers:
            self._write("if (PyErr_Occurred()) {")
            self.indent += 1
            self._write("PyErr_Fetch(&_exc_type, &_exc_value, &_exc_tb);")
            for i, (exc_type, exc_name, except_body) in enumerate(handlers):
                exc_type_str = self._exc_type_to_c(exc_type)
                # if / else if 链：只匹配第一个命中的子句
                opener = "if" if i == 0 else "} else if"
                self._write(f"{opener} (PyErr_GivenExceptionMatches(_exc_type, {exc_type_str})) {{")
                self.indent += 1
                if exc_name:
                    # 持有自己的引用：_exc_value 随后会被 Py_XDECREF
                    self._write(f"{exc_name} = _exc_value ? _exc_value : Py_None;")
                    self._write(f"Py_INCREF({exc_name});")
                self._visit_stmts(except_body)
                if exc_name:
                    self._write(f"Py_DECREF({exc_name});")
                    self._write(f"{exc_name} = NULL;")
                # 异常已被本次 except 消费
                self._write("Py_XDECREF(_exc_type);")
                self._write("Py_XDECREF(_exc_value);")
                self._write("Py_XDECREF(_exc_tb);")
                self._write("_exc_type = NULL; _exc_value = NULL; _exc_tb = NULL;")
                self.indent -= 1
                if i == len(handlers) - 1:
                    self._write("}")
            self.indent -= 1
            self._write("}")
        elif finally_body:
            # 没有 except 子句时仍要摘走挂起异常，让它穿过 finally 继续传播
            self._write("if (PyErr_Occurred()) {")
            self.indent += 1
            self._write("PyErr_Fetch(&_exc_type, &_exc_value, &_exc_tb);")
            self.indent -= 1
            self._write("}")

        if finally_body:
            self._write(f"{try_label}_finally:")
            self._write("{")
            self.indent += 1
            self._visit_stmts(finally_body)
            self.indent -= 1
            self._write("}")

        # 未被匹配的异常：恢复并传播（绝不能再被 PyErr_Clear 抹掉）
        self._write("if (_exc_type != NULL) {")
        self.indent += 1
        self._write("PyErr_Restore(_exc_type, _exc_value, _exc_tb);")
        self._emit_error_return()
        self.indent -= 1
        self._write("}")

        self.indent -= 1
        self._write("}")

    def _visit_stmts(self, stmts):
        """依次访问语句列表；没有专用 visitor 的语句退回表达式形式输出

        与旧实现保持一致：没有 `kind` 的对象不是语句节点，直接跳过
        （否则会把 AST 的 repr 写进生成的 C）。
        """
        for stmt in stmts or []:
            if not hasattr(stmt, 'kind'):
                continue
            method = f"_visit_{stmt.kind}"
            if hasattr(self, method):
                getattr(self, method)(stmt)
            else:
                self._write(self._expr_to_str(stmt) + ";")

    def _emit_error_return(self):
        """按当前函数返回类型输出一条“已设置异常”的错误返回"""
        if self.current_return_type == "void":
            self._write("return;")
        elif self.current_return_type.startswith("PyObject"):
            self._write("return NULL;")
        else:
            # 基本类型无法用返回值表达失败，异常已置位，包装器会检查 PyErr_Occurred()
            self._write("return 0;")
    
    def _visit_RaiseStmt(self, node):
        """处理 raise 语句
        
        转换规则：
        - raise -> PyErr_SetNone(PyExc_RuntimeError)
        - raise BuiltinExc -> PyErr_SetNone(PyExc_BuiltinExc)
        - raise BuiltinExc("literal") -> PyErr_SetString(PyExc_BuiltinExc, "literal")
        - raise exc -> PyErr_SetObject(type(exc), exc)
        - raise exc from cause -> 设置 __cause__ 属性
        
        如果在try块内，跳转到except检查点；否则直接return
        """
        builtin_exc = self._raise_builtin_to_c(node.exc)
        if builtin_exc:
            self._write(builtin_exc)
        elif node.exc:
            exc_str = self._expr_to_str(node.exc)
            self._write(f"PyErr_SetObject(PyObject_Type({exc_str}), {exc_str});")
        else:
            self._write("PyErr_SetNone(PyExc_RuntimeError);")
        
        # 如果在try块内，跳转到except检查点
        if self.current_try_label:
            self._write(f"goto {self.current_try_label}_except_check;")
        else:
            # 不在try块内，直接return
            self._emit_error_return()

    def _raise_builtin_to_c(self, exc_node):
        """``raise ValueError`` / ``raise ValueError("msg")`` → 完整的 PyErr_Set* 语句

        内置异常在 C 中的符号是 ``PyExc_<Name>``；命中不了的形式返回 None，
        由调用方沿用原有的通用路径。
        """
        if exc_node is None:
            return None

        name = None
        args = None
        kind = getattr(exc_node, 'kind', None)
        if kind == 'Name':
            name = getattr(exc_node, 'id', None)
        elif kind == 'Call':
            func = getattr(exc_node, 'func', None)
            if getattr(func, 'kind', None) == 'Name':
                name = getattr(func, 'id', None)
                args = getattr(exc_node, 'args', None)

        if not name or name not in self._builtin_exception_names():
            return None
        if name in getattr(self, "_module_type_names", set()):
            return None

        if args is None:
            return f"PyErr_SetNone(PyExc_{name});"
        if len(args) == 0:
            return f"PyErr_SetNone(PyExc_{name});"
        if len(args) == 1 and getattr(args[0], 'kind', None) == 'Constant' \
                and isinstance(args[0].value, str):
            return f"PyErr_SetString(PyExc_{name}, {self._expr_to_str(args[0])});"
        return None
    
    def _visit_VecType(self, node):
        """处理 SIMD 向量类型 - vec[ElementType; Size]
        
        转换规则：
        vec[int; 4] -> VecInt32_4 (SSE2 int vector)
        vec[float; 4] -> VecFloat32_4 (SSE float vector)
        vec[float; 8] -> VecFloat32_8 (AVX float vector)
        
        返回与_type_to_c一致的类型名，以便在C代码中正确使用类型别名
        """
        elem_type_str = self._type_to_c(node.element_type)
        size = node.size
        
        # 返回与_type_to_c一致的类型名
        if elem_type_str == "int":
            return f"VecInt32_{size}"
        elif elem_type_str == "float":
            return f"VecFloat32_{size}"
        elif elem_type_str == "double":
            return f"VecFloat64_{size}"
        else:
            return f"Vec{elem_type_str}_{size}"
    
    def _visit_VecLiteral(self, node):
        """处理 SIMD 向量字面量 - vec![value; Size] 或 vec![v1, v2, ...]
        
        转换规则：
        vec![1, 2, 3, 4] -> {1, 2, 3, 4}
        vec![0; 4] -> {0, 0, 0, 0}
        """
        if node.size is not None:
            # 重复形式：vec![value; Size]
            value_str = self._expr_to_str(node.elements[0])
            values = ", ".join([value_str] * node.size)
        else:
            # 枚举形式：vec![v1, v2, ...]
            values = ", ".join(self._expr_to_str(e) for e in node.elements)
        
        self._write(f"({values})")
    
    def _visit_ListComp(self, node):
        """处理列表推导式
        
        将列表推导式转换为等价的循环代码：
        [expr for x in iterable if condition]
        
        转换为：
        PyObject* result = PyList_New(0);
        PyObject* iter = iterable;
        PyObject* iterator = PyObject_GetIter(iter);
        PyObject* x;
        while ((x = PyIter_Next(iterator))) {
            if (condition) {
                PyObject* item = expr;
                PyList_Append(result, item);
                Py_XDECREF(item);
            }
            Py_XDECREF(x);
        }
        Py_XDECREF(iterator);
        """
        list_var = f"_listcomp_result"
        self._write(f"PyObject* {list_var} = PyList_New(0);")
        
        for i, (target, iter_expr, if_expr) in enumerate(node.generators):
            iter_var = f"_listcomp_iter_{i}"
            iter_obj_var = f"_listcomp_iter_obj_{i}"
            
            # 评估可迭代对象
            iter_str = self._expr_to_str(iter_expr)
            self._write(f"PyObject* {iter_var} = {iter_str};")
            self._write(f"PyObject* {iter_obj_var} = PyObject_GetIter({iter_var});")
            self._write(f"Py_XDECREF({iter_var});")
            
            # 循环
            self._write(f"PyObject* {target} = NULL;")
            self._write(f"while (({target} = PyIter_Next({iter_obj_var}))) {{")
            self.indent += 1
            
            # 将循环变量转换为C整数（暂时只支持int类型）
            self._write(f"    int _val_{target} = PyLong_AsLong({target});")
            
            # 可选的if条件
            if if_expr:
                # if_expr 可能是单个表达式或表达式列表（支持多个 if 条件）
                if isinstance(if_expr, list):
                    # 多个 if 条件用 AND 连接
                    if_str_parts = []
                    for expr in if_expr:
                        if_str_parts.append(self._expr_to_str(expr).replace(target, f"_val_{target}"))
                    if_str = " && ".join(if_str_parts)
                else:
                    # 将if条件中的循环变量引用替换为C变量
                    if_str = self._expr_to_str(if_expr).replace(target, f"_val_{target}")
                self._write(f"if ({if_str}) {{")
                self.indent += 1
            
            # 评估元素表达式并添加到列表
            # 将元素表达式中的循环变量引用替换为C变量
            item_var = f"_listcomp_item_{i}"
            elt_str = self._expr_to_str(node.elt).replace(target, f"_val_{target}")
            self._write(f"PyObject* {item_var} = PyLong_FromLong((long)({elt_str}));")
            self._write(f"PyList_Append({list_var}, {item_var});")
            self._write(f"Py_XDECREF({item_var});")
            
            # 关闭if块
            if if_expr:
                self.indent -= 1
                self._write("}")
            
            # 释放循环变量
            self._write(f"Py_XDECREF({target});")
            
            self.indent -= 1
            self._write("}")
            self._write(f"Py_XDECREF({iter_obj_var});")
    
    def _visit_LambdaExpr(self, node):
        """处理 Lambda 表达式
        
        Lambda函数定义已经在文件开头通过_collect_features收集并生成，
        这里不需要再生成函数定义。
        """
        pass
    
    def _visit_WithStmt(self, node):
        """处理 with 语句（上下文管理器）
        
        使用 Python C API 的 PyObject_CallMethodObjArgs 调用 __enter__ 和 __exit__：
        - with expr as var: body
          展开为：
          manager = expr
          var = manager.__enter__()
          try:
              body
          finally:
              manager.__exit__(...)
        """
        with_label = f"_with_{self.buildblock_counter}"
        self.buildblock_counter += 1
        
        managers = []
        
        # 1. 评估所有上下文表达式，调用 __enter__
        for i, (expr, var) in enumerate(node.items):
            manager_var = f"_with_manager_{i}"
            enter_result_var = f"_with_result_{i}"
            temp_var = f"_with_temp_{i}"
            
            # 评估上下文表达式，先存储为原始类型
            expr_str = self._expr_to_str(expr)
            expr_type = self._get_expr_type(expr)
            
            # 如果表达式类型不是 PyObject*，需要转换
            if expr_type == 'PyObject*':
                self._write(f"PyObject* {manager_var} = {expr_str};")
            else:
                # 存储为原始类型，然后转换为 PyObject*
                self._write(f"{expr_type} {temp_var} = {expr_str};")
                if expr_type in ('int', 'long'):
                    self._write(f"PyObject* {manager_var} = PyLong_FromLong({temp_var});")
                elif expr_type == 'float':
                    self._write(f"PyObject* {manager_var} = PyFloat_FromDouble({temp_var});")
                else:
                    self._write(f"PyObject* {manager_var} = NULL;")
            
            self._write(f"Py_XINCREF({manager_var});")
            
            # 调用 __enter__
            self._write(f"PyObject* {enter_result_var} = PyObject_CallMethodObjArgs({manager_var}, PyUnicode_FromString(\"__enter__\"), NULL);")
            self._write(f"if ({enter_result_var} == NULL) {{")
            self.indent += 1
            self._write(f"    Py_XDECREF({manager_var});")
            # 根据当前函数返回类型决定返回值
            if self.current_return_type == "void":
                self._write(f"    return;")
            elif self.current_return_type.startswith("PyObject"):
                self._write(f"    return NULL;")
            else:
                self._write(f"    return 0;")
            self.indent -= 1
            self._write("}")
            
            # 如果有 as var，绑定变量
            if var:
                # 获取变量类型（如果已声明）
                var_type = self._get_var_type(var)
                if var_type == 'PyObject*':
                    self._write(f"PyObject* {var} = {enter_result_var};")
                elif var_type in ('int', 'long'):
                    self._write(f"int {var} = (int)PyLong_AsLong({enter_result_var});")
                    self._write(f"Py_XDECREF({enter_result_var});")
                elif var_type == 'float':
                    self._write(f"float {var} = (float)PyFloat_AsDouble({enter_result_var});")
                    self._write(f"Py_XDECREF({enter_result_var});")
                else:
                    self._write(f"PyObject* {var} = {enter_result_var};")
            else:
                self._write(f"Py_XDECREF({enter_result_var});")
            
            managers.append(manager_var)
        
        # 2. try块执行body
        self._write("PyErr_Clear();")
        self._write("{")
        self.indent += 1
        
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                method = f"_visit_{stmt.kind}"
                if hasattr(self, method):
                    getattr(self, method)(stmt)
                else:
                    self._write(self._expr_to_str(stmt) + ";")
        
        self.indent -= 1
        self._write("}")
        
        # 3. finally块调用 __exit__
        self._write(f"{with_label}_finally:")
        
        for i, (expr, var) in enumerate(node.items):
            manager_var = managers[i]
            # 调用 __exit__，需要传递三个参数：exc_type, exc_value, traceback
            # 如果没有异常，都传递 NULL
            self._write(f"PyObject* _exit_result_{i} = PyObject_CallMethodObjArgs({manager_var}, PyUnicode_FromString(\"__exit__\"), NULL, NULL, NULL, NULL);")
            self._write(f"Py_XDECREF(_exit_result_{i});")
            self._write(f"Py_XDECREF({manager_var});")
    
    def _visit_ExprStmt(self, node):
        """处理表达式语句"""
        value = node.value
        
        # 特殊处理构建块表达式
        if hasattr(value, 'kind') and value.kind == 'BuildBlockExpr':
            self._visit_BuildBlockExpr(value)
            return
        
        # 特殊处理await表达式
        if hasattr(value, 'kind') and value.kind == 'AwaitExpr':
            self._visit_AwaitExpr(value)
            return
        
        expr_str = self._expr_to_str(value)
        # 处理pass语句（转换为空语句）
        if expr_str == "pass":
            self._write(";")
        else:
            self._write(expr_str + ";")
    
    def _visit_AwaitExpr(self, node):
        """处理await表达式"""
        # 在非async函数中，await表达式转换为直接调用
        value_str = self._expr_to_str(node.value) if node.value else "NULL"
        # 使用PyAwaitable_Await获取协程结果
        self._write(f"PyObject* _await_result = PyAwaitable_Await((PyObject*){value_str});")
        self._write("if (!_await_result) return NULL;")
    
    def _visit_DeferStmt(self, node):
        """处理 defer 语句（在函数级别处理）
        
        defer语句的代码生成在_visit_FuncDef中统一处理：
        - 在所有return语句之前生成defer清理代码
        - 在函数末尾（如果没有return）生成defer清理代码
        
        这里生成注释标记，便于调试和理解生成的代码
        """
        self._write("// defer statement (handled at function level)")
    
    def _visit_GuardStmt(self, node):
        """处理 guard 守卫表达式语句
        
        转换规则：
        - 单行: guard cond else expr -> if (!cond) { return expr; }
        - 多行: guard cond else:\n    block -> if (!cond) { block; return last_expr; }
        - guard let: guard let v = expr else val -> v = expr; if (!v) { return val; }
        """
        test = self._expr_to_str(node.test)
        
        if node.is_let:
            # guard let 形式：先绑定，再判断
            # 获取变量名和类型
            let_var_name = node.let_target.id if hasattr(node.let_target, 'id') else self._expr_to_str(node.let_target)
            let_var_type = self._get_expr_type(node.test)
            if let_var_type == 'PyObject*':
                let_var_type = 'int'  # 默认使用 int 类型
            
            self._write(f"{let_var_type} {let_var_name} = {test};")
            test = let_var_name
        
        self._write(f"if (!({test})) {{")
        self.indent += 1
        
        if isinstance(node.orelse, list):
            # 多行形式：执行块中的所有语句，最后返回块中最后一个表达式的值
            for i, stmt in enumerate(node.orelse):
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
                    else:
                        self._write(self._expr_to_str(stmt) + ";")
            
            # 在块末尾添加隐式返回
            if node.orelse:
                last_stmt = node.orelse[-1]
                if hasattr(last_stmt, 'kind'):
                    if last_stmt.kind == 'ReturnStmt':
                        # 已经有 return 语句，不需要添加
                        pass
                    elif last_stmt.kind == 'ExprStmt':
                        # 最后一个是表达式语句，隐式返回
                        expr_str = self._expr_to_str(last_stmt.value)
                        self._write(f"return {expr_str};")
                    else:
                        # 其他类型的语句，返回 None
                        self._write("return;")
                else:
                    self._write("return;")
        else:
            # 单行形式：直接返回表达式的值
            orelse_expr = self._expr_to_str(node.orelse)
            self._write(f"return {orelse_expr};")
        
        self.indent -= 1
        self._write("}")
    
    def _visit_PassStmt(self, node):
        """处理 pass 语句（转换为空语句）"""
        self._write(";")
    
    def _visit_Import(self, node):
        """处理 import 语句
        
        转换规则：
        import module -> 在模块初始化时使用 PyImport_ImportModule 导入
        import module as alias -> 导入并设置别名
        
        在函数内部的 import 会在函数执行时动态导入
        """
        # 在函数内部的 import 语句
        if self.in_function:
            for alias in node.names:
                module_name = alias.name
                asname = alias.asname if alias.asname else alias.name
                self._write(f"PyObject* {asname} = PyImport_ImportModule(\"{module_name}\");")
                self._write(f"if (!{asname}) return NULL;")
        else:
            # 模块级别的 import，在模块初始化时处理
            self.module_imports.append((node, None))
    
    def _visit_FromImport(self, node):
        """处理 from ... import 语句
        
        转换规则：
        from module import name -> 在模块初始化时使用 PyImport_ImportModule + PyObject_GetAttrString
        from module import name as alias -> 导入并设置别名
        """
        module_name = node.module
        if self.in_function:
            # 在函数内部的 from import
            self._write(f"PyObject* _from_module = PyImport_ImportModule(\"{module_name}\");")
            self._write(f"if (!_from_module) return NULL;")
            for alias in node.names:
                name = alias.name
                asname = alias.asname if alias.asname else alias.name
                self._write(f"PyObject* {asname} = PyObject_GetAttrString(_from_module, \"{name}\");")
                self._write(f"if (!{asname}) {{ Py_DECREF(_from_module); return NULL; }}")
            self._write("Py_DECREF(_from_module);")
        else:
            # 模块级别的 from import
            self.module_imports.append((node, None))
    
    def _visit_ClassDef(self, node):
        """处理类定义语句
        
        使用 Python C API 创建类：
        1. 定义 PyTypeObject
        2. 定义 __init__ 和其他方法
        3. 使用 PyType_Ready 初始化
        4. 使用 PyModule_AddObject 添加到模块
        """
        class_name = node.name
        
        self._write(f"// Class: {class_name}")
        self._write(f"typedef struct {{")
        self.indent += 1
        self._write("PyObject_HEAD")
        # 添加实例属性
        for stmt in node.body:
            if hasattr(stmt, 'kind') and stmt.kind == 'LetStmt':
                attr_name = stmt.name
                self._write(f"    PyObject* {attr_name};")
        self.indent -= 1
        self._write(f"}} {class_name}Object;")
        self._write()
        
        # 生成 __init__ 方法
        init_func_name = f"_{class_name}_init"
        self._write(f"static int {init_func_name}({class_name}Object* self, PyObject* args, PyObject* kwargs) {{")
        self.indent += 1
        self._write("    if (PyType_Ready((PyTypeObject*)&{class_name}Type) < 0) return -1;".format(class_name=class_name))
        self._write("    (void)args; (void)kwargs;")
        # 初始化实例属性
        for stmt in node.body:
            if hasattr(stmt, 'kind') and stmt.kind == 'LetStmt':
                attr_name = stmt.name
                self._write(f"    self->{attr_name} = Py_None;")
                self._write(f"    Py_INCREF(Py_None);")
        self._write("    return 0;")
        self.indent -= 1
        self._write("}")
        self._write()
        
        # 生成类型对象
        self._write(f"static PyTypeObject {class_name}Type = {{")
        self.indent += 1
        self._write("    PyVarObject_HEAD_INIT(NULL, 0)")
        self._write(f"    .tp_name = \"{self.module_name}.{class_name}\",")
        self._write(f"    .tp_basicsize = sizeof({class_name}Object),")
        self._write("    .tp_itemsize = 0,")
        self._write("    .tp_flags = Py_TPFLAGS_DEFAULT,")
        self._write(f"    .tp_new = PyType_GenericNew,")
        self._write(f"    .tp_init = (initproc){init_func_name},")
        self.indent -= 1
        self._write("};")
        self._write()
        
        # 在模块初始化时添加类
        self.module_classes.append((class_name, f"&{class_name}Type"))
    
    def _visit_MetaBlock(self, node):
        """处理 meta 块"""
        # meta 块用于元编程，目前暂不生成代码，但输出注释标记
        self._write(f"// Meta block: {node.kind}")
    
    def _visit_ConstraintDef(self, node):
        """处理约束定义"""
        # 约束定义用于类型系统，目前暂不生成代码，但输出注释标记
        self._write(f"// Constraint: {node.name}")
    
    def _visit_SubtypeDecl(self, node):
        """处理子类型声明"""
        # 子类型声明用于类型系统，目前暂不生成代码，但输出注释标记
        self._write(f"// Subtype: {node.subtype} <: {node.supertype}")
    
    def _visit_DispatchDecl(self, node):
        """处理分发声明"""
        # 分发声明用于类型系统，目前暂不生成代码，但输出注释标记
        self._write(f"// Dispatch: {node.name}")
    
    def _visit_MacroCall(self, node):
        """处理宏调用
        
        宏调用在编译时展开，生成编译期求值代码：
        - 查找宏定义
        - 将宏参数转换为Tokens
        - 执行宏体生成新的Tokens
        - 将Tokens重新解析为AST节点
        
        简化实现：将宏调用转换为编译期求值的函数调用
        """
        # 生成编译期求值的宏展开代码
        args_str = ", ".join(self._expr_to_str(arg) for arg in node.args)
        self._write(f"// MacroCall: {node.name}({args_str})")
        self._write(f"// Note: Macro expansion happens at compile time")
        
        # 如果是简单的宏调用，尝试生成编译期求值代码
        # 实际的宏展开需要完整的Token操作支持
        if len(node.args) == 0:
            # 无参数宏，生成空语句
            self._write(";")
        else:
            # 有参数宏，生成编译期求值表达式
            # 实际实现需要查找宏定义并展开
            for arg in node.args:
                if hasattr(arg, 'kind'):
                    method = f"_visit_{arg.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(arg)
                    else:
                        self._write(self._expr_to_str(arg) + ";")
    
    def _visit_BacktickBlock(self, node):
        """处理反引号代码块 - 用于宏中的代码捕获"""
        # 反引号代码块在宏展开时处理，这里生成注释标记
        prefix = node.prefix or ""
        self._write(f"// BacktickBlock{prefix}: {len(node.content)} bytes")
    
    def _visit_BuildValueExpr(self, node):
        """处理构建值表达式"""
        # 构建值表达式用于构建块中的值生成
        self._write("// BuildValueExpr")
        if node.value:
            self._write(self._expr_to_str(node.value) + ";")
    
    def _visit_PipeExpr(self, node):
        """处理管道表达式 - x |> f |> g 转换为 g(f(x))"""
        # 管道表达式已在解析时转换为嵌套调用，这里作为fallback
        pass
    
    def _visit_AssertStmt(self, node):
        """处理 assert 语句
        
        转换规则：
        - assert expr -> if (!expr) { PyErr_SetString(PyExc_AssertionError, "assertion failed"); return; }
        - assert expr, msg -> if (!expr) { PyErr_SetString(PyExc_AssertionError, msg); return; }
        """
        test = self._expr_to_str(node.test)
        msg = self._expr_to_str(node.msg) if node.msg else '"assertion failed"'
        
        self._write(f"if (!({test})) {{")
        self.indent += 1
        self._write(f'PyErr_SetString(PyExc_AssertionError, {msg});')
        # 根据函数返回类型选择正确的返回语句
        if self.current_return_type == "void":
            self._write("return;")
        else:
            self._write("return NULL;")
        self.indent -= 1
        self._write("}")
    
    def _pattern_to_condition(self, subject: str, pattern) -> str:
        """将模式转换为条件表达式"""
        if hasattr(pattern, 'kind'):
            if pattern.kind == "Constant":
                # 常量模式：subject == value
                value = pattern.value
                if isinstance(value, str):
                    # 尝试转换为数字
                    try:
                        num_value = int(value)
                        return f"{subject} == {num_value}"
                    except ValueError:
                        try:
                            float_value = float(value)
                            return f"{subject} == {float_value}"
                        except ValueError:
                            # 字符串字面量
                            return f"{subject} == \"{value}\""
                elif isinstance(value, bool):
                    return f"{subject} == {'1' if value else '0'}"
                else:
                    return f"{subject} == {value}"
            elif pattern.kind in ("Name", "Pattern"):
                # 获取名称（Pattern 使用 name，Name 使用 id）
                var_name = pattern.name if hasattr(pattern, 'name') else pattern.id
                if var_name == "_":
                    # 通配符模式：始终为真
                    return "1"
                else:
                    # 变量模式：始终匹配，需要绑定变量
                    return "1"
        elif isinstance(pattern, dict) and "or" in pattern:
            # OR模式：pattern1 | pattern2
            conditions = [self._pattern_to_condition(subject, p) for p in pattern["or"]]
            return " || ".join(f"({c})" for c in conditions)
        elif isinstance(pattern, dict) and "pattern" in pattern and "condition" in pattern:
            # 守卫模式：pattern if condition
            inner_pattern = pattern["pattern"]
            condition = pattern["condition"]
            pattern_cond = self._pattern_to_condition(subject, inner_pattern)
            condition_str = self._expr_to_str(condition)
            return f"({pattern_cond}) && ({condition_str})"
        elif isinstance(pattern, list):
            # 列表/元组模式：[pattern1, pattern2, ...]
            if len(pattern) == 0:
                # 空列表模式：subject长度为0
                return f"PyList_Size((PyObject*){subject}) == 0"
            
            conditions = []
            # 检查长度
            conditions.append(f"PyList_Size((PyObject*){subject}) == {len(pattern)}")
            
            # 检查每个元素
            for i, inner_pattern in enumerate(pattern):
                elem_var = f"_match_elem_{i}"
                # 生成获取元素的代码
                self._write(f"PyObject* {elem_var} = PyList_GetItem((PyObject*){subject}, {i});")
                self._write(f"Py_XINCREF({elem_var});")
                elem_cond = self._pattern_to_condition(elem_var, inner_pattern)
                conditions.append(elem_cond)
            
            return " && ".join(f"({c})" for c in conditions)
        
        # 默认：始终为真（变量绑定）
        return "1"
    
    def _visit_MatchStmt(self, node):
        """处理 match/case 模式匹配语句
        
        转换规则：
        match subject:
            case pattern1:
                body1
            case pattern2:
                body2
            else:
                body_else
        
        转换为 if-else 链：
        if (subject == pattern1) { body1 }
        else if (subject == pattern2) { body2 }
        else { body_else }
        """
        subject = self._expr_to_str(node.subject)
        subject_var = f"_match_subject"
        
        # 将 subject 保存到临时变量
        self._write(f"void* {subject_var} = {subject};")
        
        for i, case_clause in enumerate(node.cases):
            pattern = case_clause.pattern
            condition = self._pattern_to_condition(subject_var, pattern)
            
            if i == 0:
                self._write(f"if ({condition}) {{")
            else:
                self._write(f"else if ({condition}) {{")
            
            self.indent += 1
            
            # 处理变量模式的绑定（支持 Pattern 和 Name 两种类型）
            if hasattr(pattern, 'kind') and pattern.kind in ("Pattern", "Name"):
                # 获取名称（Pattern 使用 name，Name 使用 id）
                var_name = pattern.name if hasattr(pattern, 'name') else pattern.id
                if var_name != "_":
                    # 绑定变量
                    self._write(f"void* {var_name} = {subject_var};")
            
            # 生成 case 体
            for stmt in case_clause.body:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
                    else:
                        self._write(self._expr_to_str(stmt) + ";")
            
            self.indent -= 1
            self._write("}")
        
        # 处理 else 分支
        if node.orelse:
            self._write("else {")
            self.indent += 1
            for stmt in node.orelse:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
                    else:
                        self._write(self._expr_to_str(stmt) + ";")
            self.indent -= 1
            self._write("}")
    
    
    
    def _visit_YieldStmt(self, node):
        """处理 yield 语句
        
        注意：这个方法在普通函数上下文中不应该被调用，
        因为包含yield的函数会被`_generate_generator_iterator`特殊处理。
        
        这里保留作为备用实现，使用标准的生成器状态变量名。
        """
        value = self._expr_to_str(node.value) if node.value else "NULL"
        
        # 标记函数包含yield
        self.has_yield = True
        
        # 设置下一个状态
        self.yield_state += 1
        next_state = self.yield_state
        
        # 保存当前状态并返回值
        # 使用 gen->_gen_state（与生成器迭代器结构体一致）
        self._write(f"// yield {value}")
        self._write(f"    gen->_gen_state = {next_state};")
        self._write(f"    gen->_last_value = {value};")
        self._write(f"    return {value};")
        
        # 添加状态恢复标签
        self._write(f"    case {next_state}:")
    
    def _visit_SpawnStmt(self, node):
        """处理 spawn 并发任务语句
        
        将 spawn 转换为 Python 线程创建：
        - spawn func(args) -> 创建线程执行函数
        - spawn: 块形式 -> 创建线程执行代码块
        
        使用 Python C API 的 PyThread_start_new_thread 实现真正的并发
        参数通过 PyObject* 打包传递给线程函数
        
        注意：C语言不支持函数嵌套定义，所以包装函数需要在函数外部生成
        """
        self._write(f"// Spawn: concurrent task execution")
        
        if node.body:
            # 块形式：spawn: 块体
            # 使用预分配的函数名
            spawn_func_name = getattr(node, '_wrapper_func_name', f"_spawn_func_{self.spawn_counter}")
            
            # 构建包装函数代码
            wrapper_code = []
            wrapper_code.append(f"static void* {spawn_func_name}(void* arg)")
            wrapper_code.append("{")
            wrapper_code.append("    PyGILState_STATE gstate = PyGILState_Ensure();")
            wrapper_code.append("    (void)arg;")
            wrapper_code.append("")
            
            # 生成块体代码
            for stmt in node.body:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        # 临时保存当前output
                        old_output = self.output[:]
                        self.output = []
                        getattr(self, method)(stmt)
                        # 将生成的代码添加到wrapper_code
                        wrapper_code.extend(self.output)
                        # 恢复output
                        self.output = old_output
                    else:
                        wrapper_code.append(self._expr_to_str(stmt) + ";")
            
            wrapper_code.append("")
            wrapper_code.append("    PyGILState_Release(gstate);")
            wrapper_code.append("    return NULL;")
            wrapper_code.append("}")
            wrapper_code.append("")
            
            # 存储包装函数代码（函数定义）
            self.spawn_wrapper_defs.append("\n".join(wrapper_code))
            
            # 在函数内部生成线程创建调用
            self._write(f"PyEval_ReleaseThread(PyThreadState_Get());")
            self._write(f"PyThread_start_new_thread((void*(*)(void*)){spawn_func_name}, (void*)NULL);")
            self._write(f"PyEval_AcquireThread(PyThreadState_Get());")
        else:
            # 调用形式：spawn func(args)
            func_name = self._expr_to_str(node.target)
            
            if node.args:
                # 有参数：创建包装函数传递参数
                # 使用预分配的函数名
                wrapper_name = getattr(node, '_wrapper_func_name', f"_spawn_wrapper_{self.spawn_counter}")
                
                # 构建包装函数代码
                wrapper_code = []
                wrapper_code.append(f"static void* {wrapper_name}(void* arg)")
                wrapper_code.append("{")
                wrapper_code.append("    PyGILState_STATE gstate = PyGILState_Ensure();")
                wrapper_code.append(f"    PyObject* args_tuple = (PyObject*)arg;")
                wrapper_code.append("    (void)args_tuple;")
                wrapper_code.append("")
                
                # 解包参数并调用原函数
                args_str = ", ".join(self._expr_to_str(arg) for arg in node.args)
                wrapper_code.append(f"    {func_name}({args_str});")
                wrapper_code.append("")
                wrapper_code.append("    PyGILState_Release(gstate);")
                wrapper_code.append("    return NULL;")
                wrapper_code.append("}")
                wrapper_code.append("")
                
                # 存储包装函数代码
                self.spawn_wrapper_defs.append("\n".join(wrapper_code))
                
                # 在函数内部生成线程创建调用（使用唯一变量名）
                self.spawn_args_counter += 1
                args_var_name = f"_spawn_args_{self.spawn_args_counter}"
                self._write(f"PyObject* {args_var_name} = PyTuple_New({len(node.args)});")
                for i, arg in enumerate(node.args):
                    arg_str = self._expr_to_str(arg)
                    self._write(f"PyTuple_SetItem({args_var_name}, {i}, PyLong_FromLong({arg_str}));")
                self._write(f"PyEval_ReleaseThread(PyThreadState_Get());")
                self._write(f"PyThread_start_new_thread((void*(*)(void*)){wrapper_name}, (void*){args_var_name});")
                self._write(f"PyEval_AcquireThread(PyThreadState_Get());")
            else:
                # 无参数：直接调用
                self._write(f"PyEval_ReleaseThread(PyThreadState_Get());")
                self._write(f"PyThread_start_new_thread((void*(*)(void*)){func_name}, (void*)NULL);")
                self._write(f"PyEval_AcquireThread(PyThreadState_Get());")
        
        self._write()
    
    def _visit_GoStmt(self, node):
        """处理 go 轻量级协程语句
        
        将 go 转换为轻量级协程（使用 Python 的线程）：
        - go func(args) -> 创建协程执行函数
        - go: 块形式 -> 创建协程执行代码块
        
        go 与 spawn 的区别：go 使用线程池复用线程，更轻量
        使用 Python C API 的 PyThread_start_new_thread 实现
        参数通过 PyObject* 打包传递给线程函数
        
        注意：C语言不支持函数嵌套定义，所以包装函数需要在函数外部生成
        """
        self._write(f"// Go: lightweight coroutine execution")
        
        if node.body:
            # 块形式：go: 块体
            # 使用预分配的函数名
            go_func_name = getattr(node, '_wrapper_func_name', f"_go_func_{self.go_counter}")
            
            # 构建包装函数代码
            wrapper_code = []
            wrapper_code.append(f"static void* {go_func_name}(void* arg)")
            wrapper_code.append("{")
            wrapper_code.append("    PyGILState_STATE gstate = PyGILState_Ensure();")
            wrapper_code.append("    (void)arg;")
            wrapper_code.append("")
            
            # 生成块体代码
            for stmt in node.body:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        # 临时保存当前output
                        old_output = self.output[:]
                        self.output = []
                        getattr(self, method)(stmt)
                        # 将生成的代码添加到wrapper_code
                        wrapper_code.extend(self.output)
                        # 恢复output
                        self.output = old_output
                    else:
                        wrapper_code.append(self._expr_to_str(stmt) + ";")
            
            wrapper_code.append("")
            wrapper_code.append("    PyGILState_Release(gstate);")
            wrapper_code.append("    return NULL;")
            wrapper_code.append("}")
            wrapper_code.append("")
            
            # 存储包装函数代码（函数定义）
            self.spawn_wrapper_defs.append("\n".join(wrapper_code))
            
            # 在函数内部生成线程创建调用
            self._write(f"// 使用线程池执行 go 协程")
            self._write(f"PyEval_ReleaseThread(PyThreadState_Get());")
            self._write(f"PyThread_start_new_thread((void*(*)(void*)){go_func_name}, (void*)NULL);")
            self._write(f"PyEval_AcquireThread(PyThreadState_Get());")
        else:
            # 调用形式：go func(args)
            func_name = self._expr_to_str(node.target)
            
            if node.args:
                # 有参数：创建包装函数传递参数
                # 使用预分配的函数名
                wrapper_name = getattr(node, '_wrapper_func_name', f"_go_wrapper_{self.go_counter}")
                
                # 构建包装函数代码
                wrapper_code = []
                wrapper_code.append(f"static void* {wrapper_name}(void* arg)")
                wrapper_code.append("{")
                wrapper_code.append("    PyGILState_STATE gstate = PyGILState_Ensure();")
                wrapper_code.append(f"    PyObject* args_tuple = (PyObject*)arg;")
                wrapper_code.append("    (void)args_tuple;")
                wrapper_code.append("")
                
                # 解包参数并调用原函数
                args_str = ", ".join(self._expr_to_str(arg) for arg in node.args)
                wrapper_code.append(f"    {func_name}({args_str});")
                wrapper_code.append("")
                wrapper_code.append("    PyGILState_Release(gstate);")
                wrapper_code.append("    return NULL;")
                wrapper_code.append("}")
                wrapper_code.append("")
                
                # 存储包装函数代码
                self.spawn_wrapper_defs.append("\n".join(wrapper_code))
                
                # 在函数内部生成线程创建调用（使用唯一变量名）
                self.spawn_args_counter += 1
                args_var_name = f"_go_args_{self.spawn_args_counter}"
                self._write(f"PyObject* {args_var_name} = PyTuple_New({len(node.args)});")
                for i, arg in enumerate(node.args):
                    arg_str = self._expr_to_str(arg)
                    self._write(f"PyTuple_SetItem({args_var_name}, {i}, PyLong_FromLong({arg_str}));")
                self._write(f"// 使用线程池执行 go 协程")
                self._write(f"PyEval_ReleaseThread(PyThreadState_Get());")
                self._write(f"PyThread_start_new_thread((void*(*)(void*)){wrapper_name}, (void*){args_var_name});")
                self._write(f"PyEval_AcquireThread(PyThreadState_Get());")
            else:
                # 无参数：直接调用
                self._write(f"// 使用线程池执行 go 协程")
                self._write(f"PyEval_ReleaseThread(PyThreadState_Get());")
                self._write(f"PyThread_start_new_thread((void*(*)(void*)){func_name}, (void*)NULL);")
                self._write(f"PyEval_AcquireThread(PyThreadState_Get());")
        
        self._write()
    
    def _visit_Decorator(self, node, func_name: str):
        """处理装饰器
        
        转换规则：
        - @test -> 在模块初始化时注册测试函数
        - @decorator -> 生成装饰器包装调用
        - @decorator(args) -> 生成带参数的装饰器包装
        """
        decorator_name = self._expr_to_str(node.name)
        
        if decorator_name == "test":
            # @test 装饰器：注册测试函数
            self._write(f"// Register test: {func_name}")
            self._write(f'PyModule_AddObject(module, "{func_name}_test", (PyObject*)&{func_name});')
        elif decorator_name == "classmethod":
            # @classmethod：标记为类方法
            pass  # 在Python包装层处理
        elif decorator_name == "staticmethod":
            # @staticmethod：标记为静态方法
            pass  # 在Python包装层处理
        else:
            # 通用装饰器：生成包装函数
            args_str = ", ".join(self._expr_to_str(arg) for arg in node.args) if node.args else ""
            if args_str:
                self._write(f"// Decorator: {decorator_name}({args_str})")
            else:
                self._write(f"// Decorator: {decorator_name}")
    
    def _visit_TypeAlias(self, node):
        """处理类型别名定义
        
        转换规则：
        - type MyInt = int -> typedef int MyInt;
        - type Maybe[T] = T | None -> 生成泛型类型别名
        - type Number = int | float -> 生成 tagged union
        """
        alias_name = node.name
        if node.generic_params:
            alias_name = f"{node.name}_{'_'.join(node.generic_params)}"
        
        target_type = node.target
        
        if hasattr(target_type, 'kind') and target_type.kind == "UnionType":
            # 联合类型：生成 tagged union
            self._visit_UnionType(target_type, alias_name)
        else:
            # 简单类型别名：生成 typedef
            c_type = self._type_to_c(target_type)
            self._write(f"typedef {c_type} {alias_name};")
            self._write()
    
    def _visit_UnionType(self, node, alias_name: str = None):
        """处理联合类型
        
        转换规则：
        - int | float -> 生成 tagged union 结构体
        """
        union_name = alias_name or f"Union_{id(node)}"
        
        # 生成 tagged union 结构体
        self._write(f"typedef struct {union_name} {{")
        self.indent += 1
        
        # 类型标签（枚举）
        self._write(f"int tag;  // 0 = {self._type_to_c(node.types[0])},")
        for i, t in enumerate(node.types[1:], 1):
            self._write(f"        // {i} = {self._type_to_c(t)}")
        
        # 联合成员
        self._write(f"union {{")
        self.indent += 1
        for i, t in enumerate(node.types):
            c_type = self._type_to_c(t)
            self._write(f"{c_type} v{i};")
        self.indent -= 1
        self._write("} data;")
        
        self.indent -= 1
        self._write(f"}} {union_name};")
        self._write()
    
    def _visit_MacroDef(self, node):
        """处理宏定义（参考 lang-zone）
        
        语法：macro name(ts: Tokens)-> Tokens = ...
        
        宏在编译期展开，操作Token流。
        参数必须是 ts: Tokens，返回值必须是 Tokens。
        
        转换规则：
        - macro name(ts: Tokens)-> Tokens = body
          -> 生成 C 宏或 static inline 函数
        """
        macro_name = node.name
        
        # 处理参数（新格式是列表，每个元素是 {"name": ..., "type": ...}）
        if isinstance(node.params, list) and len(node.params) > 0 and isinstance(node.params[0], dict):
            # 新格式：带类型注解的参数
            params_str = ", ".join(f"{self._type_to_c(p['type'])} {p['name']}" for p in node.params)
        else:
            # 旧格式：简单参数名列表
            params_str = ", ".join(node.params)
        
        # 生成 static inline 函数（更安全）
        self._write(f"// Macro: {macro_name}")
        self._write(f"static inline void {macro_name}({params_str}) {{")
        self.indent += 1
        for stmt in node.body:
            if hasattr(stmt, 'kind'):
                method = f"_visit_{stmt.kind}"
                if hasattr(self, method):
                    getattr(self, method)(stmt)
                else:
                    self._write(self._expr_to_str(stmt) + ";")
        self.indent -= 1
        self._write("}")
        self._write()
    
    def _visit_ComptimeStmt(self, node):
        """处理编译期求值语句（参考 lang-zone）
        
        语法：
        - comptime: expr          - 单行形式，编译期计算表达式
        - comptime:               - 块形式，编译期执行代码块
            body...
        
        转换规则：
        - comptime: expr -> 在编译时求值并内联结果
        - 支持常量表达式：数字、字符串、算术运算等
        """
        expr = node.expr
        
        # 检查是否是块形式（Suite节点或列表）
        if isinstance(expr, list):
            # 块形式：expr是一个语句列表
            self._write("// comptime block:")
            self.indent += 1
            for stmt in expr:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
            self.indent -= 1
            self._write()
            return
        elif hasattr(expr, 'kind') and expr.kind == 'Suite':
            # 块形式：expr是Suite节点
            self._write("// comptime block:")
            self.indent += 1
            for stmt in expr.body:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
            self.indent -= 1
            self._write()
            return
        
        # 单行形式：尝试在编译时求值表达式
        try:
            result = self._evaluate_constant(expr)
            if result is not None:
                self._write(f"// comptime: {self._expr_to_str(expr)} = {result}")
                # 将结果定义为编译时常量
                if isinstance(result, int):
                    self._write(f"#define _comptime_{id(node)} {result}")
                elif isinstance(result, float):
                    self._write(f"#define _comptime_{id(node)} {result}")
                elif isinstance(result, str):
                    self._write(f'#define _comptime_{id(node)} "{result}"')
                else:
                    self._write(f"// comptime result: {result}")
            else:
                # 无法求值，生成注释标记
                self._write(f"// comptime: {self._expr_to_str(expr)} (not evaluatable)")
        except Exception as e:
            self._write(f"// comptime: {self._expr_to_str(expr)} (evaluation failed: {e})")
        self._write()
    
    def _evaluate_constant(self, node) -> Any:
        """尝试在编译时求值表达式
        
        支持：
        - 常量字面量（整数、浮点数、字符串）
        - 算术运算（+、-、*、/、%）
        - 比较运算（==、!=、<、>、<=、>=）
        """
        if hasattr(node, 'kind'):
            if node.kind == "Constant":
                return node.value
            elif node.kind == "BinOp":
                left = self._evaluate_constant(node.left)
                right = self._evaluate_constant(node.right)
                if left is not None and right is not None:
                    op = node.op
                    if op == "+":
                        return left + right
                    elif op == "-":
                        return left - right
                    elif op == "*":
                        return left * right
                    elif op == "/":
                        return left / right if right != 0 else None
                    elif op == "%":
                        return left % right if right != 0 else None
                    elif op == "==":
                        return left == right
                    elif op == "!=":
                        return left != right
                    elif op == "<":
                        return left < right
                    elif op == ">":
                        return left > right
                    elif op == "<=":
                        return left <= right
                    elif op == ">=":
                        return left >= right
            elif node.kind == "UnaryOp":
                operand = self._evaluate_constant(node.operand)
                if operand is not None:
                    op = node.op
                    if op == "-":
                        return -operand
                    elif op == "+":
                        return operand
                    elif op == "not":
                        return not operand
        return None
    
    def _visit_BuildBlockExpr(self, node):
        """处理构建块表达式
        
        转换规则：
        - ~: 调用构建块 -> 生成匿名函数调用
        - *: 生成器构建块 -> 生成生成器函数调用
        - =: 变量构建块 -> 生成变量初始化块
        """
        # 使用确定性计数器替代 id(node)，避免缓存失效
        self.buildblock_counter += 1
        func_name = f"_buildblock_{self.buildblock_counter}"
        
        if node.block_type == BuildBlockExpr.BUILD_CALL:
            # ~: 调用构建块：生成匿名函数并立即调用
            self._write(f"// Build block call (~:)")
            self._write(f"void* {func_name}(void) {{")
            self.indent += 1
            for stmt in node.body:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
                    else:
                        self._write(self._expr_to_str(stmt) + ";")
            self._write("return NULL;")
            self.indent -= 1
            self._write(f"}}")
            self._write(f"{func_name}();")
        
        elif node.block_type == BuildBlockExpr.BUILD_GEN:
            # *: 生成器构建块：生成生成器函数
            self._write(f"// Generator build block (*:)")
            self._write(f"void* {func_name}(void) {{")
            self.indent += 1
            for stmt in node.body:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
                    else:
                        self._write(self._expr_to_str(stmt) + ";")
            self._write("return NULL;")
            self.indent -= 1
            self._write(f"}}")
        
        elif node.block_type == BuildBlockExpr.BUILD_ASSIGN:
            # =: 变量构建块：生成变量初始化块
            self._write(f"// Assign build block (=:)")
            for stmt in node.body:
                if hasattr(stmt, 'kind'):
                    method = f"_visit_{stmt.kind}"
                    if hasattr(self, method):
                        getattr(self, method)(stmt)
                    else:
                        self._write(self._expr_to_str(stmt) + ";")
        
        self._write()
    
    def _generate_lambda_function(self, lambda_info):
        """生成Lambda函数的C实现"""
        name = lambda_info['name']
        method_name = lambda_info['method_name']
        obj_name = lambda_info['obj_name']
        params = lambda_info['params']
        body = lambda_info['body']
        
        num_params = len(params)
        
        # 生成静态全局变量声明
        self._write(f"static PyObject* {obj_name} = NULL;")
        
        # 生成lambda函数实现
        self._write(f"static PyObject* {name}(PyObject* self, PyObject* args) {{")
        self.indent += 1
        
        # 解析参数
        for i, param in enumerate(params):
            param_name = param.name if hasattr(param, 'name') else f"arg{i}"
            # 默认使用int类型，实际应该根据类型注解处理
            self._write(f"    int {param_name};")
        
        # 参数解析代码
        if num_params > 0:
            format_str = "".join(["i"] * num_params)
            param_list = ", ".join([f"&{p.name if hasattr(p, 'name') else f'arg{i}'}" for i, p in enumerate(params)])
            self._write(f"    if (!PyArg_ParseTuple(args, \"{format_str}\", {param_list})) {{")
            self._write(f"        return NULL;")
            self._write(f"    }}")
        
        # 生成函数体
        if hasattr(body, 'kind'):
            method = f"_visit_{body.kind}"
            if hasattr(self, method):
                getattr(self, method)(body)
            else:
                # 包装返回值为Python对象
                self._write(f"    return PyLong_FromLong((long)({self._expr_to_str(body)}));")
        else:
            # 默认返回None
            self._write("    Py_RETURN_NONE;")
        
        self.indent -= 1
        self._write(f"}}")
        self._write()
        
        # 生成方法定义
        self._write(f"static PyMethodDef {method_name} = {{")
        self._write(f"    \"{name}\",")
        self._write(f"    (PyCFunction){name},")
        self._write(f"    METH_VARARGS,")
        self._write(f"    NULL")
        self._write(f"}};")
        self._write()
    
    def _generate_python_module(self):
        """生成 Python 模块初始化代码（包含完整的包装函数）"""
        self._write()
        self._write(f"// Python module: {self.module_name}")
        self._write()
        
        # 获取生成器函数列表和协程函数列表
        generators = getattr(self, 'generators', [])
        generator_names = {g['name'] for g in generators}
        coroutines = getattr(self, 'coroutines', [])
        coroutine_names = {c['name'] for c in coroutines}
        
        # 生成普通函数的包装函数实现
        for stmt in self.functions:
            if hasattr(stmt, 'name') and hasattr(stmt, 'params') and hasattr(stmt, 'return_type'):
                func_name = self._get_func_name(stmt)
                # 跳过生成器函数和协程函数（已在各自的生成器中处理）
                if func_name not in generator_names and func_name not in coroutine_names:
                    self._generate_wrapper_function(stmt)
        
        # 为生成器函数生成包装器（调用创建函数）
        for gen in generators:
            self._generate_generator_wrapper(gen)
        
        # 为协程函数生成包装器（调用创建函数）
        for coro in coroutines:
            self._generate_coroutine_wrapper(coro)
        
        self._write()
        
        # 模块方法表
        self._write(f"static PyMethodDef {self.module_name}_methods[] = {{")
        self.indent += 1
        
        # 添加导出的普通函数
        for stmt in self.functions:
            if hasattr(stmt, 'name') and hasattr(stmt, 'params') and hasattr(stmt, 'return_type'):
                func_name = self._get_func_name(stmt)
                if func_name in generator_names:
                    # 生成器函数：使用创建函数作为入口
                    create_func = f"{func_name}_create"
                    wrapper_name = f"_{self.module_name}_{func_name}_wrapper"
                    self._write(f'{{"{func_name}", (PyCFunction){wrapper_name}, METH_VARARGS, NULL}},')
                elif func_name in coroutine_names:
                    # 协程函数：使用创建函数作为入口
                    wrapper_name = f"_{self.module_name}_{func_name}_wrapper"
                    self._write(f'{{"{func_name}", (PyCFunction){wrapper_name}, METH_VARARGS, NULL}},')
                else:
                    # 普通函数：使用标准包装器
                    wrapper_name = f"_{self.module_name}_{func_name}_wrapper"
                    self._write(f'{{"{func_name}", (PyCFunction){wrapper_name}, METH_VARARGS, NULL}},')
        
        self._write("{NULL, NULL, 0, NULL}")
        self.indent -= 1
        self._write("};")
        self._write()
        
        # 模块定义
        self._write(f"static struct PyModuleDef {self.module_name}_module = {{")
        self.indent += 1
        self._write("PyModuleDef_HEAD_INIT,")
        self._write(f'"{self.module_name}",')
        self._write("NULL,")
        self._write("-1,")
        self._write(f"{self.module_name}_methods")
        self.indent -= 1
        self._write("};")
        self._write()
        
        # 模块初始化函数
        self._write(f"PyMODINIT_FUNC PyInit_{self.module_name}(void) {{")
        self.indent += 1
        self._write(f"    PyObject* module = PyModule_Create(&{self.module_name}_module);")
        self._write("    if (!module) return NULL;")
        
        # 初始化生成器类型
        generators = getattr(self, 'generators', [])
        for gen in generators:
            gen_struct_name = f"_{gen['name']}_Generator"
            func_name = gen['name']
            self._write(f"    // Initialize {gen_struct_name}_Type")
            self._write(f"    {gen_struct_name}_Type.tp_dealloc = (destructor)PyObject_Del;")
            self._write(f"    {gen_struct_name}_Type.tp_repr = (reprfunc)PyObject_Repr;")
            self._write(f"    {gen_struct_name}_Type.tp_iter = (getiterfunc){func_name}_iter;")
            self._write(f"    {gen_struct_name}_Type.tp_iternext = (iternextfunc){func_name}_next_wrapper;")
            self._write(f"    {gen_struct_name}_Type.tp_flags = Py_TPFLAGS_DEFAULT;")
            self._write(f"    if (PyType_Ready(&{gen_struct_name}_Type) < 0) {{")
            self._write(f"        Py_DECREF(module);")
            self._write("        return NULL;")
            self._write("    }")
        
        # 初始化协程类型
        coroutines = getattr(self, 'coroutines', [])
        for coro in coroutines:
            coro_struct_name = f"_{coro['name']}_Coroutine"
            func_name = coro['name']
            self._write(f"    // Initialize {coro_struct_name}_Type")
            self._write(f"    {coro_struct_name}_Type.tp_dealloc = (destructor)PyObject_Del;")
            self._write(f"    {coro_struct_name}_Type.tp_repr = (reprfunc){func_name}_repr;")
            self._write(f"    {coro_struct_name}_Type.tp_iter = (getiterfunc){func_name}_await;")
            self._write(f"    {coro_struct_name}_Type.tp_iternext = (iternextfunc){func_name}_resume;")
            self._write(f"    {coro_struct_name}_Type.tp_flags = Py_TPFLAGS_DEFAULT;")
            self._write(f"    if (PyType_Ready(&{coro_struct_name}_Type) < 0) {{")
            self._write(f"        Py_DECREF(module);")
            self._write("        return NULL;")
            self._write("    }")
        
        # 添加枚举值到模块
        for enum_def in self.enums:
            for variant in enum_def.variants:
                if hasattr(variant, 'name'):
                    enum_value_name = f"{enum_def.name}_{variant.name}"
                    python_name = f"{enum_def.name}_{variant.name}"
                    self._write(f"    PyModule_AddIntConstant(module, \"{python_name}\", {enum_value_name});")
        
        # 添加类到模块
        for class_name, type_object in self.module_classes:
            self._write(f"    if (PyType_Ready({type_object}) < 0) {{")
            self._write(f"        Py_DECREF(module);")
            self._write("        return NULL;")
            self._write("    }")
            self._write(f"    PyModule_AddObject(module, \"{class_name}\", (PyObject*){type_object});")
        
        # 初始化Lambda函数对象
        lambda_functions = getattr(self, 'lambda_functions', [])
        for lambda_info in lambda_functions:
            obj_name = lambda_info['obj_name']
            method_name = lambda_info['method_name']
            self._write(f"    {obj_name} = PyCFunction_New((PyMethodDef*)&{method_name}, NULL);")
        
        self._write("    return module;")
        self.indent -= 1
        self._write("}")
    
    def _generate_generator_wrapper(self, gen_info):
        """为生成器函数生成Python包装器（调用创建函数）"""
        func_name = gen_info['name']
        params = gen_info['params']
        wrapper_name = f"_{self.module_name}_{func_name}_wrapper"
        
        # 构建参数列表和解析格式
        param_names = []
        param_types = []
        parse_format = ""
        
        for param in params:
            parts = param.split()
            if len(parts) >= 2:
                p_name = parts[-1]
                p_type = " ".join(parts[:-1])
                param_names.append(p_name)
                param_types.append(p_type)
                parse_format += self._type_to_parse_format(p_type)
        
        # 生成包装函数签名
        self._write(f"static PyObject* {wrapper_name}(PyObject* self, PyObject* args) {{")
        self.indent += 1
        
        # 生成局部变量声明
        for i, (name, c_type) in enumerate(zip(param_names, param_types)):
            if c_type == 'PyObject*':
                self._write(f"    PyObject* {name} = NULL;")
            elif c_type == 'const char*':
                self._write(f"    const char* {name} = NULL;")
            else:
                self._write(f"    {c_type} {name};")
        
        # 生成参数解析代码
        self._write()
        if parse_format:
            parse_args = ", ".join(["&" + name for name in param_names])
            self._write(f"    if (!PyArg_ParseTuple(args, \"{parse_format}\", {parse_args})) {{")
            self._write("        return NULL;")
            self._write("    }")
        else:
            self._write(f"    if (!PyArg_ParseTuple(args, \"\")) {{")
            self._write("        return NULL;")
            self._write("    }")
        
        # 调用创建函数
        self._write()
        create_func = gen_info['create_func']
        if param_names:
            func_args = ", ".join(param_names)
            self._write(f"    return {create_func}({func_args});")
        else:
            self._write(f"    return {create_func}();")
        
        self.indent -= 1
        self._write("}")
    
    def _generate_coroutine_wrapper(self, coro_info):
        """为协程函数生成Python包装器（调用创建函数）"""
        func_name = coro_info['name']
        params = coro_info['params']
        wrapper_name = f"_{self.module_name}_{func_name}_wrapper"
        
        # 构建参数列表和解析格式
        param_names = []
        param_types = []
        parse_format = ""
        
        for param in params:
            parts = param.split()
            if len(parts) >= 2:
                p_name = parts[-1]
                p_type = " ".join(parts[:-1])
                param_names.append(p_name)
                param_types.append(p_type)
                parse_format += self._type_to_parse_format(p_type)
        
        # 生成包装函数签名
        self._write(f"static PyObject* {wrapper_name}(PyObject* self, PyObject* args) {{")
        self.indent += 1
        
        # 生成局部变量声明
        for i, (name, c_type) in enumerate(zip(param_names, param_types)):
            if c_type == 'PyObject*':
                self._write(f"    PyObject* {name} = NULL;")
            elif c_type == 'const char*':
                self._write(f"    const char* {name} = NULL;")
            else:
                self._write(f"    {c_type} {name};")
        
        # 生成参数解析代码
        self._write()
        if parse_format:
            parse_args = ", ".join(["&" + name for name in param_names])
            self._write(f"    if (!PyArg_ParseTuple(args, \"{parse_format}\", {parse_args})) {{")
            self._write("        return NULL;")
            self._write("    }")
        else:
            self._write(f"    if (!PyArg_ParseTuple(args, \"\")) {{")
            self._write("        return NULL;")
            self._write("    }")
        
        # 调用创建函数
        self._write()
        create_func = coro_info['create_func']
        if param_names:
            func_args = ", ".join(param_names)
            self._write(f"    return {create_func}({func_args});")
        else:
            self._write(f"    return {create_func}();")
        
        self.indent -= 1
        self._write("}")
    
    def _generate_wrapper_function(self, func_def):
        """生成单个函数的 Python 包装器"""
        func_name = self._get_func_name(func_def)
        return_type = self._type_to_c(func_def.return_type)
        wrapper_name = f"_{self.module_name}_{func_name}_wrapper"
        
        # 构建参数列表和解析格式
        param_names = []
        param_types = []
        parse_format = ""
        
        for param in func_def.params:
            param_name = param.name
            param_type = self._type_to_c(param.type_annotation) if hasattr(param, 'type_annotation') else 'PyObject*'
            param_names.append(param_name)
            param_types.append(param_type)
            parse_format += self._type_to_parse_format(param_type)
        
        # 生成包装函数签名
        self._write(f"static PyObject* {wrapper_name}(PyObject* self, PyObject* args) {{")
        self.indent += 1
        
        # 生成局部变量声明
        for i, (name, c_type) in enumerate(zip(param_names, param_types)):
            if c_type == 'PyObject*':
                self._write(f"    PyObject* {name} = NULL;")
            elif c_type == 'const char*':
                self._write(f"    const char* {name} = NULL;")
            else:
                self._write(f"    {c_type} {name};")
        
        # 生成返回值变量（如果有返回值）
        if return_type != "void":
            self._write(f"    {return_type} _result;")
        
        # 生成参数解析代码
        self._write()
        if parse_format:
            parse_args = ", ".join(["&" + name for name in param_names])
            self._write(f"    if (!PyArg_ParseTuple(args, \"{parse_format}\", {parse_args})) {{")
            self._write("        return NULL;")
            self._write("    }")
        else:
            self._write(f"    if (!PyArg_ParseTuple(args, \"\")) {{")
            self._write("        return NULL;")
            self._write("    }")
        
        # 生成函数调用
        self._write()
        if return_type != "void":
            func_args = ", ".join(param_names)
            self._write(f"    _result = {func_name}({func_args});")
            
            # 被调函数用“置位异常 + 返回错误值”表示失败：必须先检查错误指示器，
            # 否则失败会被静默转换成 0 / 0.0 / False 这样的正常返回值。
            self._write()
            self._write("    if (PyErr_Occurred()) {")
            self._write("        return NULL;")
            self._write("    }")
            
            # 根据返回类型生成对应的返回代码
            self._write()
            if return_type == "int":
                self._write("    return PyLong_FromLong((long)_result);")
            elif return_type == "long":
                self._write("    return PyLong_FromLong(_result);")
            elif return_type == "long long":
                self._write("    return PyLong_FromLongLong(_result);")
            elif return_type == "float":
                self._write("    return PyFloat_FromDouble((double)_result);")
            elif return_type == "double":
                self._write("    return PyFloat_FromDouble(_result);")
            elif return_type == "_Bool":
                self._write("    return PyBool_FromLong((long)_result);")
            elif return_type == "const char*":
                # NULL 的 C 字符串同样是失败信号，PyUnicode_FromString(NULL) 会崩溃
                self._write("    if (_result == NULL) {")
                self._write(f'        PyErr_SetString(PyExc_SystemError, "cypy: {func_name} returned NULL string without setting an exception");')
                self._write("        return NULL;")
                self._write("    }")
                self._write("    return PyUnicode_FromString(_result);")
            elif return_type == "PyObject*":
                # 被调函数按“返回新引用”约定已经把所有权交给调用方：
                # 再 Py_INCREF 一次会让每次成功调用都泄漏一个引用；
                # 而返回 NULL 是失败信号，对它 Py_INCREF 会解引用地址 0
                # （真实 .pyd 里表现为 0xC0000005 直接崩掉解释器）。
                self._write("    if (_result == NULL) {")
                self._write("        if (!PyErr_Occurred()) {")
                self._write(f'            PyErr_SetString(PyExc_SystemError, "cypy: {func_name} returned NULL without setting an exception");')
                self._write("        }")
                self._write("        return NULL;")
                self._write("    }")
                self._write("    return _result;")
            else:
                # 默认：返回 None
                self._write("    Py_RETURN_NONE;")
        else:
            func_args = ", ".join(param_names)
            self._write(f"    {func_name}({func_args});")
            self._write()
            self._write("    if (PyErr_Occurred()) {")
            self._write("        return NULL;")
            self._write("    }")
            self._write("    Py_RETURN_NONE;")
        
        self.indent -= 1
        self._write("}")
    
    def generate(self, ast, module_name: str) -> str:
        """生成 C 代码"""
        # 重置所有实例状态，确保可重复调用
        self.module_name = module_name
        self.output = []
        self.indent = 0
        self.functions = []
        self.structs = []
        self.enums = []
        self.traits = []
        self.impls = []
        self.needs_libc = False
        self.needs_python_api = True
        self.needs_simd = False
        self.current_return_type = "void"
        self.buildblock_counter = 0
        self.yield_state = 0
        self.spawn_counter = 0
        self.go_counter = 0
        self.spawn_args_counter = 0  # 用于生成唯一的参数变量名
        self.spawn_wrapper_decls = []  # 存储spawn包装函数声明
        self.spawn_wrapper_defs = []  # 存储spawn包装函数定义
        self.module_imports = []  # 存储模块级别的import语句
        self.module_classes = []  # 存储模块级别的类定义
        self.current_try_label = None  # 当前try块的标签（用于嵌套try）
        # 模块级定义的类型/函数名：except/raise 遇到与内置异常同名的本地类型时
        # 不能加 PyExc_ 前缀
        self._module_type_names = set()
        if hasattr(ast, 'body'):
            for stmt in ast.body:
                name = getattr(stmt, 'name', None)
                if isinstance(name, str):
                    self._module_type_names.add(name)
        
        # 收集函数
        if hasattr(ast, 'body'):
            for stmt in ast.body:
                if hasattr(stmt, 'kind') and stmt.kind == 'FuncDef':
                    self.functions.append(stmt)
        
        self._visit(ast)
        return "\n".join(self.output)


class BridgeCacheManager:
    """桥接编译器缓存管理器：管理.pyd文件的缓存和增量编译"""
    
    def __init__(self):
        self._manifest_cache = {}
    
    def _get_base_cache_dir(self, source_path: str = None) -> str:
        """获取基础缓存目录（__pycache__/cypy/py{major}{minor}/）

        按 Python 版本隔离缓存目录，避免不同解释器版本编译出的
        .pyd 文件（cp311/cp313 等）互相污染导致导入失败。
        """
        if source_path:
            source_dir = os.path.dirname(source_path)
        else:
            source_dir = os.getcwd()
        py_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
        cache_dir = os.path.join(source_dir, "__pycache__", "cypy", py_tag)
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
    
    def _get_cache_dir(self, module_name: str, code_hash: str) -> str:
        """获取模块对应的缓存目录"""
        base_cache_dir = self._get_base_cache_dir()
        # 使用模块名和哈希的前16位作为子目录名
        cache_dir = os.path.join(base_cache_dir, f"{module_name}_{code_hash[:16]}")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
    
    def _get_manifest_path(self) -> str:
        """获取manifest文件路径"""
        base_cache_dir = self._get_base_cache_dir()
        return os.path.join(base_cache_dir, "bridge_manifest.json")
    
    def _compute_hash(self, code: str) -> str:
        """计算代码内容的SHA256哈希"""
        import hashlib
        return hashlib.sha256(code.encode('utf-8')).hexdigest()
    
    def _load_manifest(self) -> Dict:
        """加载manifest文件"""
        manifest_path = self._get_manifest_path()
        if os.path.exists(manifest_path):
            import json
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as exc:
                import sys
                print(f"[cypy][warn] bridge manifest 无法读取，按无缓存重新编译: "
                      f"{manifest_path} ({exc})", file=sys.stderr)
        return {}
    
    def _save_manifest(self, manifest: Dict) -> None:
        """保存manifest文件"""
        manifest_path = self._get_manifest_path()
        import json
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    
    def is_stale(self, code: str, module_name: str) -> bool:
        """检查代码是否过期（需要重新编译）"""
        manifest = self._load_manifest()
        code_hash = self._compute_hash(code)
        cache_key = f"{module_name}"
        
        if cache_key not in manifest:
            return True
        
        cached_info = manifest[cache_key]
        
        # 检查哈希
        if cached_info.get("hash") != code_hash:
            return True
        
        # 检查.pyd文件是否存在
        pyd_path = cached_info.get("pyd_path")
        if pyd_path and not os.path.exists(pyd_path):
            return True
        
        return False
    
    def get_cached_pyd(self, code: str, module_name: str) -> Optional[str]:
        """获取缓存的.pyd文件路径"""
        if self.is_stale(code, module_name):
            return None
        
        manifest = self._load_manifest()
        cache_key = f"{module_name}"
        
        if cache_key not in manifest:
            return None
        
        pyd_path = manifest[cache_key].get("pyd_path")
        if pyd_path and os.path.exists(pyd_path):
            return pyd_path
        
        return None
    
    def cache_pyd(self, code: str, module_name: str, pyd_path: str) -> None:
        """缓存.pyd文件路径和相关信息"""
        manifest = self._load_manifest()
        cache_key = f"{module_name}"
        
        manifest[cache_key] = {
            "hash": self._compute_hash(code),
            "pyd_path": pyd_path,
            "timestamp": os.path.getmtime(pyd_path)
        }
        
        self._save_manifest(manifest)
    
    def clear_cache(self, module_name: str = None) -> Dict:
        """清除缓存；删除失败的条目留在 manifest 里如实汇报，不谎报已清理"""
        manifest = self._load_manifest()
        removed: List[str] = []
        failed: List[str] = []

        def _remove(path: str) -> bool:
            try:
                os.remove(path)
                return True
            except OSError as exc:
                import sys
                print(f"[cypy][warn] 缓存文件删除失败，保留其 manifest 条目: "
                      f"{path} ({exc})", file=sys.stderr)
                return False

        if module_name:
            # 清除单个模块的缓存
            cache_key = f"{module_name}"
            if cache_key in manifest:
                pyd_path = manifest[cache_key].get("pyd_path")
                if not pyd_path or not os.path.exists(pyd_path) or _remove(pyd_path):
                    del manifest[cache_key]
                    removed.append(cache_key)
                    self._save_manifest(manifest)
                else:
                    failed.append(pyd_path)
        else:
            # 清除所有缓存
            base_cache_dir = self._get_base_cache_dir()
            for root, dirs, files in os.walk(base_cache_dir):
                for file in files:
                    if file.endswith(".pyd") or file.endswith(".so") or file == "bridge_manifest.json":
                        path = os.path.join(root, file)
                        if not _remove(path):
                            failed.append(path)
            if not failed:
                self._save_manifest({})
        return {"removed": removed, "failed": failed}


class BridgeCompiler:
    """桥接编译器：负责将 Cypy 代码编译为动态链接库"""
    
    def __init__(self):
        self._compiler = self._detect_compiler()
        self._generator = CCodeGenerator()
        self._cache_manager = BridgeCacheManager()
    
    def _detect_compiler(self) -> str:
        """检测系统编译器"""
        if sys.platform.startswith('win'):
            return self._find_msvc_compiler()
        elif sys.platform.startswith('linux'):
            return 'gcc'
        elif sys.platform.startswith('darwin'):
            return 'clang'
        raise BridgeError(f"Unsupported platform: {sys.platform}")
    
    def _find_msvc_compiler(self) -> str:
        """查找MSVC编译器路径"""
        import shutil
        
        # 先检查PATH中是否有cl
        cl_path = shutil.which('cl')
        if cl_path:
            return cl_path
        
        # 尝试查找MSVC安装路径
        msvc_paths = [
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC",
            r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Tools\MSVC",
            r"C:\Program Files\Microsoft Visual Studio\2019\Community\VC\Tools\MSVC",
            r"C:\Program Files\Microsoft Visual Studio\2019\Professional\VC\Tools\MSVC",
        ]
        
        import glob
        for base_path in msvc_paths:
            if os.path.exists(base_path):
                # 查找最新版本的MSVC
                versions = sorted(glob.glob(os.path.join(base_path, '*')), reverse=True)
                if versions:
                    bin_path = os.path.join(versions[0], 'bin', 'Hostx64', 'x64')
                    cl_path = os.path.join(bin_path, 'cl.exe')
                    if os.path.exists(cl_path):
                        return cl_path
        
        return 'cl'
    
    def _parse_cypy_code(self, code: str):
        """解析 Cypy 代码为 AST"""
        try:
            from cypyc.parser.lexer import Lexer
            from cypyc.parser.parser import Parser
            
            lexer = Lexer(code)
            tokens = lexer.tokenize()
            parser = Parser(tokens)
            return parser.parse()
        except ValueError as e:
            # 保留解析器的 ValueError，包含行号信息
            raise e
        except Exception as e:
            raise BridgeError(f"Parse error: {e}")
    
    def _generate_c_code(self, code: str, module_name: str) -> str:
        """生成 C 代码"""
        ast = self._parse_cypy_code(code)
        return self._generator.generate(ast, module_name)
    
    def _compile_c_to_shared_lib(self, c_code: str, module_name: str, 
                                 output_dir: str) -> str:
        """将 C 代码编译为动态链接库"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            c_file = os.path.join(tmp_dir, f"{module_name}.c")
            # BUG-25: 不带 encoding 的文本写盘按本地代码页（本机 cp936）落字节，
            # 与读源码侧的 encoding="utf-8" 不一致，非本地字符直接 UnicodeEncodeError。
            with open(c_file, 'w', encoding='utf-8') as f:
                f.write(c_code)
            
            # 使用setuptools进行编译，自动处理环境变量
            import setuptools
            from setuptools import Extension, setup
            
            python_lib = f"python{sys.version_info.major}{sys.version_info.minor}"
            extension = Extension(
                module_name,
                sources=[c_file],
                include_dirs=[os.path.join(sys.exec_prefix, 'include')],
                library_dirs=[os.path.join(sys.exec_prefix, 'libs')],
                libraries=[python_lib]
            )
            
            # 创建setup.py内容
            # 使用raw字符串避免路径反斜杠问题
            c_file_escaped = c_file.replace('\\', '\\\\')
            include_dir_escaped = os.path.join(sys.exec_prefix, 'include').replace('\\', '\\\\')
            lib_dir_escaped = os.path.join(sys.exec_prefix, 'libs').replace('\\', '\\\\')
            
            setup_code = f'''
from setuptools import setup, Extension

extension = Extension(
    '{module_name}',
    sources=['{c_file_escaped}'],
    include_dirs=['{include_dir_escaped}'],
    library_dirs=['{lib_dir_escaped}'],
    libraries=['{python_lib}']
)

setup(
    name='{module_name}',
    ext_modules=[extension],
    script_args=['build_ext', '--inplace']
)
'''
            
            setup_file = os.path.join(tmp_dir, 'setup.py')
            with open(setup_file, 'w', encoding='utf-8') as f:
                f.write(setup_code)
            
            try:
                # 运行setup.py进行编译
                result = subprocess.run(
                    [sys.executable, setup_file, 'build_ext', '--inplace'],
                    capture_output=True,
                    cwd=tmp_dir,
                    timeout=BUILD_TIMEOUT
                )

                # 以字节读取并容错解码，避免 Windows 下默认 GBK 编码导致的
                # UnicodeDecodeError（编译器输出可能含非 GBK 字节）
                raw_out = result.stdout if isinstance(result.stdout, bytes) else result.stdout.encode("utf-8", "replace")
                raw_err = result.stderr if isinstance(result.stderr, bytes) else result.stderr.encode("utf-8", "replace")
                stdout_text = raw_out.decode("utf-8", "replace")
                stderr_text = raw_err.decode("utf-8", "replace")

                if result.returncode != 0:
                    error_msg = f"Compile error:\n{stdout_text}\n{stderr_text}"
                    raise BridgeError(error_msg)
                
                # 找到生成的.pyd文件
                output_file = None
                for file in os.listdir(tmp_dir):
                    # BUG-26: _detect_compiler 支持 linux/darwin，产物扫描却只认 .pyd，
                    # 非 Windows 上成功的编译会被报成「没找到产物」。与同文件 :3683、
                    # cypy_hook/hook.py:542 的既有口径统一。
                    if file.endswith('.pyd') or file.endswith('.so') or file.endswith('.dll'):
                        output_file = os.path.join(tmp_dir, file)
                        break
                
                if output_file is None:
                    raise BridgeError("Failed to find generated .pyd file")
                
                # 复制到输出目录
                os.makedirs(output_dir, exist_ok=True)
                import shutil
                final_output = os.path.join(output_dir, os.path.basename(output_file))
                shutil.copy(output_file, final_output)
                
                return final_output
            except FileNotFoundError:
                raise BridgeError(f"Compiler not found: {self._compiler}")
            except subprocess.TimeoutExpired:
                raise BridgeError(
                    f"Compile failed: build_ext 超过 {BUILD_TIMEOUT}s 未结束，子进程已终止")
            except Exception as e:
                raise BridgeError(f"Compile failed: {e}")
    
    def compile_c_code(self, c_code: str, module_name: str = "cypy_module", 
                       output_dir: str = None, use_cache: bool = True) -> CompileResult:
        """直接编译 C 代码字符串为动态链接库
        
        Args:
            c_code: C代码字符串
            module_name: 模块名称
            output_dir: 输出目录
            use_cache: 是否使用缓存（默认True）
        
        Returns:
            CompileResult: 编译结果
        """
        try:
            if output_dir is None:
                output_dir = tempfile.gettempdir()
            os.makedirs(output_dir, exist_ok=True)
            
            # 检查缓存
            if use_cache:
                cached_pyd = self._cache_manager.get_cached_pyd(c_code, module_name)
                if cached_pyd and os.path.exists(cached_pyd):
                    # 将缓存文件复制到指定的output_dir
                    import shutil
                    final_output = os.path.join(output_dir, os.path.basename(cached_pyd))
                    shutil.copy(cached_pyd, final_output)
                    return CompileResult(
                        success=True,
                        output_path=final_output,
                        c_code=c_code
                    )
            
            output_path = self._compile_c_to_shared_lib(c_code, module_name, output_dir)
            
            # 更新缓存
            if use_cache:
                self._cache_manager.cache_pyd(c_code, module_name, output_path)
            
            return CompileResult(
                success=True,
                output_path=output_path,
                c_code=c_code
            )
        except Exception as e:
            return CompileResult(
                success=False,
                error=str(e),
                c_code=c_code
            )
    
    def compile_code(self, code: str, module_name: str = "cypy_module", 
                     output_dir: str = None, use_cache: bool = True) -> CompileResult:
        """编译 Cypy 代码字符串
        
        Args:
            code: Cypy源代码
            module_name: 模块名称
            output_dir: 输出目录
            use_cache: 是否使用缓存（默认True）
        
        Returns:
            CompileResult: 编译结果
        """
        try:
            # 检查缓存（基于Cypy源代码）
            if use_cache:
                cached_pyd = self._cache_manager.get_cached_pyd(code, module_name)
                if cached_pyd:
                    # 生成对应的C代码用于返回
                    c_code = self._generate_c_code(code, module_name)
                    return CompileResult(
                        success=True,
                        output_path=cached_pyd,
                        c_code=c_code
                    )
            
            c_code = self._generate_c_code(code, module_name)
            
            if output_dir is None:
                output_dir = tempfile.gettempdir()
            os.makedirs(output_dir, exist_ok=True)
            
            output_path = self._compile_c_to_shared_lib(c_code, module_name, output_dir)
            
            # 更新缓存
            if use_cache:
                self._cache_manager.cache_pyd(code, module_name, output_path)
            
            return CompileResult(
                success=True,
                output_path=output_path,
                c_code=c_code
            )
        except ValueError as e:
            # 解析错误，尝试提取行号信息
            error_str = str(e)
            line = None
            col = None
            source_line = None
            
            # 尝试从错误消息中提取行号和列号
            import re
            match = re.search(r'at (\d+):(\d+)', error_str)
            if match:
                line = int(match.group(1))
                col = int(match.group(2))
            
            # 如果有行号，获取源文件中的对应行
            if line is not None:
                lines = code.split('\n')
                if line <= len(lines):
                    source_line = lines[line - 1]
            
            compile_error = CompileError(
                message=error_str,
                line=line,
                col=col,
                source_line=source_line
            )
            return CompileResult(
                success=False,
                error=str(compile_error),
                errors=[compile_error]
            )
        except Exception as e:
            return CompileResult(
                success=False,
                error=str(e)
            )
    
    def compile_module(self, source_path: str, output_dir: str = None) -> CompileResult:
        """编译 Cypy 源文件"""
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            module_name = os.path.basename(source_path)
            if module_name.endswith('.cypy'):
                module_name = module_name[:-5]
            elif module_name.endswith('.py'):
                module_name = module_name[:-3]
            
            if output_dir is None:
                output_dir = os.path.dirname(source_path)
            
            return self.compile_code(code, module_name, output_dir)
        except Exception as e:
            return CompileResult(
                success=False,
                error=str(e)
            )


def compile_code(code: str, module_name: str = "cypy_module", 
                 output_dir: str = None) -> CompileResult:
    """编译 Cypy 代码字符串（便捷函数）"""
    compiler = BridgeCompiler()
    return compiler.compile_code(code, module_name, output_dir)


def compile_module(source_path: str, output_dir: str = None) -> CompileResult:
    """编译 Cypy 源文件（便捷函数）"""
    compiler = BridgeCompiler()
    return compiler.compile_module(source_path, output_dir)


__all__ = [
    'compile_module',
    'compile_code',
    'BridgeCompiler',
    'CompileResult',
    'CompileError',
    'CCodeGenerator',
]