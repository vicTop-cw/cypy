"""
Cypy Bridge Core Module

提供桥接库的核心基础设施和工具函数。
"""

import ctypes
import sys
import os
from typing import Any, Type, Dict, Optional, Callable


class BridgeError(Exception):
    """桥接库通用异常"""
    pass


class TypeConversionError(BridgeError):
    """类型转换异常"""
    pass


class MemoryError(BridgeError):
    """内存操作异常"""
    pass


class PointerError(BridgeError):
    """指针操作异常"""
    pass


class StructError(BridgeError):
    """结构体操作异常"""
    pass


def get_platform() -> str:
    """获取当前平台"""
    if sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('linux'):
        return 'linux'
    elif sys.platform.startswith('darwin'):
        return 'macos'
    return sys.platform


def get_c_stdlib() -> Any:
    """获取C标准库的ctypes绑定"""
    platform = get_platform()
    if platform == 'windows':
        try:
            return ctypes.msvcrt
        except AttributeError:
            # 在某些Python版本中msvcrt不可用，尝试其他方式
            return ctypes.CDLL('msvcrt.dll')
    elif platform == 'linux':
        return ctypes.CDLL('libc.so.6')
    elif platform == 'macos':
        return ctypes.CDLL('libc.dylib')
    else:
        raise BridgeError(f"Unsupported platform: {platform}")


def ctype_to_python(ctype_value: Any) -> Any:
    """将ctypes值转换为Python值"""
    if isinstance(ctype_value, ctypes._Pointer):
        return ctype_value
    elif isinstance(ctype_value, ctypes.Structure):
        return ctype_value
    elif hasattr(ctype_value, 'value'):
        return ctype_value.value
    return ctype_value


def python_to_ctype(python_value: Any, ctype: Type) -> Any:
    """将Python值转换为ctypes值"""
    if isinstance(python_value, ctype):
        return python_value
    try:
        return ctype(python_value)
    except TypeError as e:
        raise TypeConversionError(f"Failed to convert {python_value} to {ctype}: {e}")


def align_of(ctype: Type) -> int:
    """获取ctypes类型的对齐要求"""
    return ctypes.alignment(ctype)


def offset_of(struct_type: Type, field_name: str) -> int:
    """获取结构体字段的偏移量"""
    if not issubclass(struct_type, ctypes.Structure):
        raise StructError(f"{struct_type} is not a ctypes Structure")
    return getattr(struct_type, field_name).offset


def size_of(ctype: Type) -> int:
    """获取ctypes类型的大小"""
    return ctypes.sizeof(ctype)


# 全局C标准库引用
_c_stdlib = get_c_stdlib()
