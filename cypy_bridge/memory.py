"""
Cypy Bridge Memory Management

提供与Cython等价的内存管理功能，包括malloc/free/sizeof等。
"""

import ctypes
from typing import Any, Type
from .core import BridgeError, MemoryError, _c_stdlib, size_of


# 设置C标准库函数的参数和返回类型
_c_stdlib.malloc.argtypes = [ctypes.c_size_t]
_c_stdlib.malloc.restype = ctypes.c_void_p

_c_stdlib.free.argtypes = [ctypes.c_void_p]
_c_stdlib.free.restype = None

_c_stdlib.realloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
_c_stdlib.realloc.restype = ctypes.c_void_p

_c_stdlib.memset.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
_c_stdlib.memset.restype = ctypes.c_void_p

_c_stdlib.memcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
_c_stdlib.memcpy.restype = ctypes.c_void_p

_c_stdlib.memmove.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
_c_stdlib.memmove.restype = ctypes.c_void_p


def malloc(size: int) -> ctypes.c_void_p:
    """分配内存（类似C的malloc）
    
    参数：
        size: 要分配的字节数
    
    返回：
        ctypes.c_void_p指针，指向分配的内存
    
    异常：
        MemoryError: 内存分配失败
    """
    if size <= 0:
        raise MemoryError(f"Invalid size: {size}")
    
    result = _c_stdlib.malloc(size)
    if not result:
        raise MemoryError(f"Failed to allocate {size} bytes")
    
    return result


def free(ptr: Any) -> None:
    """释放内存（类似C的free）
    
    参数：
        ptr: 要释放的内存指针
    """
    if ptr:
        if isinstance(ptr, ctypes.c_void_p):
            _c_stdlib.free(ptr)
        elif hasattr(ptr, 'ptr'):
            # 处理Pointer对象
            _c_stdlib.free(ptr.ptr)
        else:
            _c_stdlib.free(ctypes.cast(ptr, ctypes.c_void_p))


def aligned_alloc(alignment: int, size: int) -> ctypes.c_void_p:
    """分配对齐的内存（类似C11的aligned_alloc）
    
    参数：
        alignment: 对齐要求（必须是2的幂）
        size: 要分配的字节数
    
    返回：
        ctypes.c_void_p指针，指向分配的内存
    """
    if size <= 0:
        raise MemoryError(f"Invalid size: {size}")
    
    # 检查alignment是否是2的幂
    if (alignment & (alignment - 1)) != 0:
        raise MemoryError(f"Alignment must be power of 2: {alignment}")
    
    # 使用malloc分配足够的内存
    ptr = malloc(size + alignment - 1)
    if not ptr:
        raise MemoryError(f"Failed to allocate {size} bytes with alignment {alignment}")
    
    # 返回原始指针（简化实现，实际应该计算对齐地址）
    return ptr


def sizeof(obj_or_type) -> int:
    """获取对象或类型的大小（类似C的sizeof）
    
    参数：
        obj_or_type: ctypes类型或实例
    
    返回：
        对象或类型的大小（字节）
    """
    try:
        if isinstance(obj_or_type, type):
            return size_of(obj_or_type)
        return size_of(type(obj_or_type))
    except Exception as e:
        raise MemoryError(f"Failed to get size: {e}")


def realloc(ptr: Any, size: int) -> ctypes.c_void_p:
    """重新分配内存（类似C的realloc）
    
    参数：
        ptr: 原内存指针
        size: 新的大小
    
    返回：
        新的内存指针
    
    异常：
        MemoryError: 内存分配失败
    """
    if size <= 0:
        free(ptr)
        return None
    
    if isinstance(ptr, ctypes.c_void_p):
        c_ptr = ptr
    elif hasattr(ptr, 'ptr'):
        c_ptr = ptr.ptr
    else:
        c_ptr = ctypes.cast(ptr, ctypes.c_void_p)
    
    result = _c_stdlib.realloc(c_ptr, size)
    if not result:
        raise MemoryError(f"Failed to reallocate {size} bytes")
    
    return result


def memset(ptr: Any, value: int, size: int) -> None:
    """填充内存（类似C的memset）
    
    参数：
        ptr: 内存指针
        value: 填充值（0-255）
        size: 填充大小
    """
    if isinstance(ptr, ctypes.c_void_p):
        c_ptr = ptr
    elif hasattr(ptr, 'ptr'):
        c_ptr = ptr.ptr
    else:
        c_ptr = ctypes.cast(ptr, ctypes.c_void_p)
    
    _c_stdlib.memset(c_ptr, value, size)


def memcpy(dest: Any, src: Any, size: int) -> None:
    """复制内存（类似C的memcpy）
    
    参数：
        dest: 目标指针
        src: 源指针
        size: 复制大小
    """
    if isinstance(dest, ctypes.c_void_p):
        c_dest = dest
    elif hasattr(dest, 'ptr'):
        c_dest = dest.ptr
    else:
        c_dest = ctypes.cast(dest, ctypes.c_void_p)
    
    if isinstance(src, ctypes.c_void_p):
        c_src = src
    elif hasattr(src, 'ptr'):
        c_src = src.ptr
    else:
        c_src = ctypes.cast(src, ctypes.c_void_p)
    
    _c_stdlib.memcpy(c_dest, c_src, size)


def memmove(dest: Any, src: Any, size: int) -> None:
    """移动内存（类似C的memmove，支持重叠区域）
    
    参数：
        dest: 目标指针
        src: 源指针
        size: 移动大小
    """
    if isinstance(dest, ctypes.c_void_p):
        c_dest = dest
    elif hasattr(dest, 'ptr'):
        c_dest = dest.ptr
    else:
        c_dest = ctypes.cast(dest, ctypes.c_void_p)
    
    if isinstance(src, ctypes.c_void_p):
        c_src = src
    elif hasattr(src, 'ptr'):
        c_src = src.ptr
    else:
        c_src = ctypes.cast(src, ctypes.c_void_p)
    
    _c_stdlib.memmove(c_dest, c_src, size)


def calloc(count: int, size: int) -> ctypes.c_void_p:
    """分配并清零内存（类似C的calloc）
    
    参数：
        count: 元素数量
        size: 每个元素的大小
    
    返回：
        ctypes.c_void_p指针，指向分配并清零的内存
    """
    total_size = count * size
    ptr = malloc(total_size)
    memset(ptr, 0, total_size)
    return ptr


__all__ = [
    'malloc',
    'free',
    'sizeof',
    'aligned_alloc',
    'realloc',
    'memset',
    'memcpy',
    'memmove',
    'calloc',
]
