"""
Cypy Bridge Enum Module

提供与Cython等价的枚举定义功能，支持cdef enum风格的枚举声明和使用。
"""

import ctypes
from typing import Any, Dict, List, Optional, Type
from .core import BridgeError


class EnumError(BridgeError):
    """枚举操作相关的异常"""
    pass


class CEnum:
    """枚举类：封装ctypes枚举操作"""
    
    def __init__(self, name: str, variants: Dict[str, int]):
        """
        参数：
            name: 枚举名称
            variants: 枚举成员字典，键为成员名，值为枚举值
        """
        self._name = name
        self._variants = variants
        self._reverse_map = {v: k for k, v in variants.items()}
        
        # 创建对应的ctypes类型
        self._ctype = ctypes.c_int
    
    @property
    def name(self) -> str:
        """返回枚举名称"""
        return self._name
    
    @property
    def variants(self) -> Dict[str, int]:
        """返回枚举成员字典"""
        return self._variants
    
    @property
    def ctype(self) -> Type:
        """返回对应的ctypes类型"""
        return self._ctype
    
    def __getattr__(self, name: str) -> int:
        """获取枚举成员值"""
        if name in self._variants:
            return self._variants[name]
        raise AttributeError(f"'{self._name}' enum has no member '{name}'")
    
    def __getitem__(self, name: str) -> int:
        """通过索引获取枚举成员值"""
        if name in self._variants:
            return self._variants[name]
        raise KeyError(f"'{self._name}' enum has no member '{name}'")
    
    def name_of(self, value: int) -> Optional[str]:
        """根据值获取枚举成员名称"""
        return self._reverse_map.get(value, None)
    
    def values(self) -> List[int]:
        """返回所有枚举值"""
        return list(self._variants.values())
    
    def names(self) -> List[str]:
        """返回所有枚举成员名称"""
        return list(self._variants.keys())
    
    def __contains__(self, value: int) -> bool:
        """检查值是否为有效的枚举值"""
        return value in self._variants.values()
    
    def __repr__(self):
        return f"CEnum('{self._name}', {self._variants})"
    
    def __str__(self):
        return f"{self._name} enum with members: {', '.join(self._variants.keys())}"


def enum(name: str, **kwargs) -> CEnum:
    """定义枚举（cdef enum风格）
    
    参数：
        name: 枚举名称
        **kwargs: 枚举成员，键为成员名，值为枚举值（可选）
    
    返回：
        CEnum对象
    
    示例：
        >>> Color = enum('Color', RED=0, GREEN=1, BLUE=2)
        >>> Color.RED
        0
        >>> Color.GREEN
        1
        
        # 自动分配值（从0开始）
        >>> Color = enum('Color', RED, GREEN, BLUE)
        >>> Color.RED
        0
        >>> Color.GREEN
        1
    """
    variants = {}
    
    if not kwargs:
        # 没有提供值，自动分配（从0开始）
        raise EnumError("Enum requires at least one member")
    
    # 处理枚举成员
    value = 0
    for key, val in kwargs.items():
        if val is None:
            # 如果值为None，自动分配
            variants[key] = value
            value += 1
        else:
            # 使用提供的值
            variants[key] = val
            # 更新下一个自动分配值
            if val >= value:
                value = val + 1
    
    return CEnum(name, variants)


def cdef_enum(name: str, *members, **named_members) -> CEnum:
    """cdef enum风格的枚举定义
    
    参数：
        name: 枚举名称
        *members: 不带值的枚举成员（自动分配值）
        **named_members: 带值的枚举成员
    
    返回：
        CEnum对象
    
    示例：
        >>> Color = cdef_enum('Color', 'RED', 'GREEN', BLUE=5)
        >>> Color.RED
        0
        >>> Color.GREEN
        1
        >>> Color.BLUE
        5
    """
    variants = {}
    value = 0
    
    # 处理不带值的成员
    for member in members:
        if isinstance(member, str):
            variants[member] = value
            value += 1
        else:
            raise EnumError(f"Enum member must be a string, got {type(member)}")
    
    # 处理带值的成员
    for key, val in named_members.items():
        if val is None:
            variants[key] = value
            value += 1
        else:
            variants[key] = val
            if val >= value:
                value = val + 1
    
    return CEnum(name, variants)


def enum_value(enum_type: CEnum, value: int) -> int:
    """创建枚举值（类型安全检查）
    
    参数：
        enum_type: CEnum类型
        value: 枚举值
    
    返回：
        验证后的枚举值
    
    抛出：
        EnumError: 如果值不是有效的枚举值
    """
    if value not in enum_type:
        raise EnumError(f"Invalid value {value} for enum '{enum_type.name}'")
    return value


__all__ = [
    'CEnum',
    'enum',
    'cdef_enum',
    'enum_value',
    'EnumError',
]
