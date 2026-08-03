"""
Cypy Bridge Pointer Operations

提供与Cython等价的指针操作功能，包括指针解引用、地址运算等。
同时提供LZ风格的所有权语义模拟，通过弱引用实现。
"""

import ctypes
import weakref
from typing import Any, Type, Optional, Generic, TypeVar
from .core import BridgeError, PointerError
from .types import _type_mapper

T = TypeVar('T')


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


class Owned(Generic[T]):
    """
    LZ风格的所有权语义模拟类，通过弱引用实现。
    
    Owned<T> 表示拥有对对象的独占所有权。
    当 Owned 对象被销毁时，其内部的弱引用不会阻止对象被垃圾回收。
    支持所有权转移和借用操作。
    
    特性：
    - 使用弱引用存储对象，不增加引用计数
    - 支持所有权转移（transfer_ownership）
    - 支持借用（borrow）- 创建临时引用而不转移所有权
    - 当内部对象被销毁时，Owned 变为无效状态
    """
    
    def __init__(self, value: T):
        """创建一个 Owned 对象
        
        参数：
            value: 要拥有所有权的对象
        """
        self._weak_ref = weakref.ref(value)
        self._is_valid = True
    
    @property
    def is_valid(self) -> bool:
        """检查 Owned 是否仍然有效（内部对象是否还存在）"""
        return self._is_valid and self._weak_ref() is not None
    
    def take(self) -> T:
        """获取内部对象并使 Owned 失效
        
        返回：
            内部对象
            
        注意：调用此方法后，Owned 对象变为无效状态，
        不能再访问其内部对象。
        """
        if not self._is_valid:
            raise PointerError("Cannot take from invalid Owned")
        obj = self._weak_ref()
        self._is_valid = False
        return obj
    
    def borrow(self) -> 'Borrowed[T]':
        """创建一个借用引用
        
        返回：
            Borrowed 对象，提供对内部对象的临时访问
            
        注意：借用期间，原 Owned 对象仍然有效。
        如果原对象被销毁，借用变为无效。
        """
        if not self.is_valid:
            raise PointerError("Cannot borrow from invalid Owned")
        return Borrowed(self._weak_ref)
    
    def transfer(self) -> 'Owned[T]':
        """转移所有权到新的 Owned 对象
        
        返回：
            新的 Owned 对象，原 Owned 变为无效
            
        注意：调用此方法后，原 Owned 对象变为无效状态。
        """
        if not self._is_valid:
            raise PointerError("Cannot transfer from invalid Owned")
        obj = self._weak_ref()
        self._is_valid = False
        return Owned(obj)
    
    def __bool__(self) -> bool:
        """检查 Owned 是否有效且非空"""
        return self.is_valid
    
    def __repr__(self) -> str:
        if not self._is_valid:
            return "Owned(INVALID)"
        obj = self._weak_ref()
        if obj is None:
            return "Owned(NULL)"
        return f"Owned({type(obj).__name__}, {repr(obj)})"


class Borrowed(Generic[T]):
    """
    借用引用类，表示对 Owned 对象的临时引用。
    
    Borrowed<T> 不拥有对象的所有权，只是临时访问。
    如果原 Owned 对象被销毁，Borrowed 变为无效状态。
    """
    
    def __init__(self, weak_ref: weakref.ref):
        """创建一个 Borrowed 对象
        
        参数：
            weak_ref: 弱引用，指向原对象
        """
        self._weak_ref = weak_ref
    
    @property
    def is_valid(self) -> bool:
        """检查借用是否仍然有效"""
        return self._weak_ref() is not None
    
    def deref(self) -> T:
        """解引用获取对象
        
        返回：
            借用的对象
            
        抛出：
            PointerError: 如果借用已失效
        """
        obj = self._weak_ref()
        if obj is None:
            raise PointerError("Cannot dereference invalid Borrowed")
        return obj
    
    def __bool__(self) -> bool:
        """检查借用是否有效"""
        return self.is_valid
    
    def __repr__(self) -> str:
        if not self.is_valid:
            return "Borrowed(INVALID)"
        obj = self._weak_ref()
        return f"Borrowed({type(obj).__name__})"


def transfer_ownership(source: Owned[T]) -> Owned[T]:
    """转移所有权
    
    参数：
        source: 源 Owned 对象
        
    返回：
        新的 Owned 对象，源对象变为无效
    """
    return source.transfer()


def borrow(owned: Owned[T]) -> Borrowed[T]:
    """创建借用引用
    
    参数：
        owned: Owned 对象
        
    返回：
        Borrowed 对象，提供临时访问
    """
    return owned.borrow()


def own(value: T) -> Owned[T]:
    """创建 Owned 对象的便捷函数
    
    参数：
        value: 要拥有所有权的对象
        
    返回：
        Owned 对象
    """
    return Owned(value)


__all__ = [
    'Pointer',
    'ptr',
    'deref',
    'addr',
    'cast_ptr',
    'null_ptr',
    'is_null',
    'Owned',
    'Borrowed',
    'transfer_ownership',
    'borrow',
    'own',
]
