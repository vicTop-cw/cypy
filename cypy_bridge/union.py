"""
Cypy Bridge Union Types
实现Cython风格的联合类型支持，允许一个值可以是多种类型之一。
"""

import ctypes
from typing import Any, Type, Tuple, Union, Optional, List
from .core import BridgeError, TypeConversionError


class UnionTypeError(BridgeError):
    """联合类型相关错误"""
    pass


class CUnion:
    """联合类型封装类
    
    联合类型允许一个内存位置存储多种不同类型的值，但同一时间只能存储一种类型。
    
    示例：
        # 创建联合类型
        my_union = CUnion(int, float)
        
        # 设置值
        my_union.value = 42  # 存储int
        my_union.value = 3.14  # 存储float
        
        # 获取值（自动类型转换）
        print(my_union.value)  # 3.14
    """
    
    def __init__(self, *member_types: Type):
        """
        创建联合类型
        
        参数：
            member_types: 联合成员类型（可以是ctypes类型或类型名称字符串）
        """
        if not member_types:
            raise UnionTypeError("Union must have at least one member type")
        
        # 解析成员类型
        self._member_types = []
        self._member_names = []
        
        for i, mtype in enumerate(member_types):
            if isinstance(mtype, str):
                from .types import _type_mapper
                ctype = _type_mapper.to_ctypes(mtype)
                name = mtype
            else:
                ctype = mtype
                name = ctype.__name__
            
            self._member_types.append(ctype)
            self._member_names.append(name)
        
        # 计算联合的大小（取最大成员类型的大小）
        self._size = max(ctypes.sizeof(t) for t in self._member_types)
        
        # 分配内存（使用ctypes直接分配）
        self._buffer = ctypes.create_string_buffer(self._size)
        
        # 当前活跃类型索引
        self._active_type_index = 0
    
    @property
    def size(self) -> int:
        """联合的大小（字节）"""
        return self._size
    
    @property
    def member_types(self) -> List[Type]:
        """联合成员类型列表"""
        return self._member_types
    
    @property
    def active_type(self) -> Type:
        """当前活跃的成员类型"""
        return self._member_types[self._active_type_index]
    
    @property
    def value(self) -> Any:
        """获取当前值"""
        ctype = self._member_types[self._active_type_index]
        return ctype.from_buffer(self._buffer).value
    
    @value.setter
    def value(self, new_value: Any):
        """设置值（自动推断类型）"""
        # 尝试找到合适的类型
        for i, ctype in enumerate(self._member_types):
            try:
                # 尝试转换为该类型
                cval = ctype(new_value)
                # 写入内存
                ctype.from_buffer(self._buffer).value = cval.value
                self._active_type_index = i
                return
            except (TypeError, ValueError):
                continue
        
        raise UnionTypeError(f"Value {new_value} cannot be converted to any member type")
    
    def set_value(self, new_value: Any, type_index: int):
        """设置值并指定类型索引"""
        if type_index < 0 or type_index >= len(self._member_types):
            raise UnionTypeError(f"Invalid type index {type_index}")
        
        ctype = self._member_types[type_index]
        try:
            cval = ctype(new_value)
            ctype.from_buffer(self._buffer).value = cval.value
            self._active_type_index = type_index
        except (TypeError, ValueError) as e:
            raise UnionTypeError(f"Failed to set value: {e}")
    
    def get_value_as(self, type_index: int) -> Any:
        """按指定类型获取值（类型转换）"""
        if type_index < 0 or type_index >= len(self._member_types):
            raise UnionTypeError(f"Invalid type index {type_index}")
        
        ctype = self._member_types[type_index]
        return ctype.from_buffer(self._buffer).value
    
    def __repr__(self):
        return f"CUnion({', '.join(self._member_names)})"


def cdef_union(*member_types: Type) -> CUnion:
    """声明联合类型（类似Cython的cdef union）
    
    示例：
        # 创建联合类型
        my_union = cdef_union("int", "float")
        
        # 设置值
        my_union.value = 42
        
        # 获取值
        print(my_union.value)  # 42
    """
    return CUnion(*member_types)


def union(*member_types: Type) -> CUnion:
    """声明联合类型（简化版）
    
    示例：
        my_union = union(int, float)
    """
    return CUnion(*member_types)


# 类型别名
CUnionType = CUnion


__all__ = [
    'CUnion',
    'CUnionType',
    'cdef_union',
    'union',
    'UnionTypeError',
]
