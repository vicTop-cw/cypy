"""
Cypy Bridge Pointer Operations

提供与Cython等价的指针操作功能，包括指针解引用、地址运算等。
"""

import ctypes
from typing import Any, Type
from .core import BridgeError, PointerError
from .types import _type_mapper


class Pointer:
    """指针类：封装ctypes指针操作"""
    
    def __init__(self, ptr, base_type: Type = ctypes.c_void_p):
        self._ptr = ptr
        self._base_type = base_type
    
    @property
    def ptr(self):
        """返回底层ctypes指针"""
        return self._ptr
    
    @property
    def base_type(self):
        """返回指针指向的基础类型"""
        return self._base_type
    
    def _get_address(self) -> int:
        """获取指针的地址值"""
        if hasattr(self._ptr, 'value'):
            # c_void_p类型
            return self._ptr.value
        elif hasattr(self._ptr, '_objects'):
            # POINTER类型
            return ctypes.addressof(self._ptr.contents)
        else:
            # CArgObject（byref返回）或其他类型
            try:
                return ctypes.addressof(ctypes.c_int.from_buffer(self._ptr))
            except (TypeError, AttributeError):
                return int(self._ptr)
    
    def deref(self):
        """解引用指针（*ptr）
        
        返回：
            指针指向的值
        """
        if not self._ptr:
            raise PointerError("Cannot dereference null pointer")
        
        try:
            # 创建一个基础类型的实例，从指针位置读取数据
            value = self._base_type()
            ctypes.memmove(ctypes.byref(value), self._ptr, ctypes.sizeof(self._base_type))
            return value.value
        except Exception as e:
            raise PointerError(f"Failed to dereference pointer: {e}")
    
    def assign(self, value):
        """给指针指向的位置赋值（*ptr = value）
        
        参数：
            value: 要赋的值
        """
        if not self._ptr:
            raise PointerError("Cannot assign to null pointer")
        
        try:
            # 将值写入指针位置
            cvalue = self._base_type(value)
            ctypes.memmove(self._ptr, ctypes.byref(cvalue), ctypes.sizeof(self._base_type))
        except Exception as e:
            raise PointerError(f"Failed to assign to pointer: {e}")
    
    def offset(self, n: int) -> 'Pointer':
        """指针偏移（ptr + n）
        
        参数：
            n: 偏移量（以基础类型大小为单位）
        
        返回：
            新的Pointer对象
        """
        if not self._ptr:
            raise PointerError("Cannot offset null pointer")
        
        offset_bytes = n * ctypes.sizeof(self._base_type)
        addr = self._get_address()
        new_addr = addr + offset_bytes
        
        # 创建新的指针
        new_ptr = ctypes.cast(
            ctypes.c_void_p(new_addr),
            ctypes.POINTER(self._base_type)
        )
        return Pointer(new_ptr, self._base_type)
    
    def __add__(self, n: int) -> 'Pointer':
        """指针加法"""
        return self.offset(n)
    
    def __sub__(self, n: int) -> 'Pointer':
        """指针减法"""
        return self.offset(-n)
    
    def __eq__(self, other) -> bool:
        """指针比较"""
        if isinstance(other, Pointer):
            return self._get_address() == other._get_address()
        return False
    
    def __ne__(self, other) -> bool:
        """指针不等比较"""
        return not self.__eq__(other)
    
    def __bool__(self) -> bool:
        """指针布尔值（非空检查）"""
        return self._ptr is not None and bool(self._ptr)
    
    def __repr__(self):
        if self._ptr:
            addr = self._get_address()
            return f"Pointer({self._base_type.__name__}, 0x{addr:x})"
        return f"Pointer({self._base_type.__name__}, NULL)"


def ptr(obj, type_name: str = None) -> Pointer:
    """获取对象的指针（&obj）
    
    参数：
        obj: ctypes对象或值
        type_name: 类型名称（可选）
    
    返回：
        Pointer对象
    """
    try:
        if type_name:
            base_type = _type_mapper.to_ctypes(type_name)
        elif hasattr(obj, '_type_'):
            base_type = obj._type_
        elif hasattr(obj, '__class__'):
            base_type = type(obj)
        else:
            base_type = ctypes.c_void_p
        
        if hasattr(obj, 'value'):
            # obj是ctypes的c_xxx类型
            return Pointer(ctypes.byref(obj), base_type)
        elif hasattr(obj, '__ctypes_array__'):
            # obj是ctypes数组
            return Pointer(ctypes.byref(obj), base_type)
        elif isinstance(obj, ctypes._Pointer):
            # obj已经是指针
            return Pointer(obj, base_type)
        elif isinstance(obj, ctypes.c_void_p):
            # obj是c_void_p类型
            return Pointer(obj, base_type)
        else:
            # 创建临时ctypes对象并获取指针
            cobj = base_type(obj)
            return Pointer(ctypes.byref(cobj), base_type)
    except Exception as e:
        raise PointerError(f"Failed to get pointer: {e}")


def deref(pointer: Pointer):
    """解引用指针（*ptr）
    
    参数：
        pointer: Pointer对象
    
    返回：
        指针指向的值
    """
    return pointer.deref()


def addr(obj) -> int:
    """获取对象的地址
    
    参数：
        obj: ctypes对象
    
    返回：
        地址（整数）
    """
    try:
        if hasattr(obj, 'value'):
            return ctypes.addressof(obj)
        elif isinstance(obj, ctypes._Pointer):
            return ctypes.addressof(obj.contents)
        elif isinstance(obj, ctypes.c_void_p):
            return obj.value
        else:
            return id(obj)
    except Exception as e:
        raise PointerError(f"Failed to get address: {e}")


def cast_ptr(pointer: Pointer, new_type: Type) -> Pointer:
    """指针类型转换
    
    参数：
        pointer: 原Pointer对象
        new_type: 新的基础类型
    
    返回：
        新类型的Pointer对象
    """
    try:
        new_ptr = ctypes.cast(pointer.ptr, ctypes.POINTER(new_type))
        return Pointer(new_ptr, new_type)
    except Exception as e:
        raise PointerError(f"Failed to cast pointer: {e}")


def null_ptr(type_name: str = "void") -> Pointer:
    """创建空指针
    
    参数：
        type_name: 类型名称
    
    返回：
        空Pointer对象
    """
    base_type = _type_mapper.to_ctypes(type_name)
    return Pointer(None, base_type)


def is_null(pointer: Pointer) -> bool:
    """检查指针是否为空
    
    参数：
        pointer: Pointer对象
    
    返回：
        是否为空指针
    """
    return not pointer


__all__ = [
    'Pointer',
    'ptr',
    'deref',
    'addr',
    'cast_ptr',
    'null_ptr',
    'is_null',
]
