"""
Cypy Bridge Memory Management

提供与Cython等价的内存管理功能，包括malloc/free/sizeof等。
"""

import ctypes
import threading
from typing import Any, Dict, Optional, Tuple, Type
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


# restype 为 c_void_p 时 ctypes 把结果转成 *int*（NULL 时为 None），
# 因此下面这些函数的返回类型注解一律写成 int，避免 `-> c_void_p` 的谎言
# 让 isinstance(x, c_void_p) 分支永久失效。
_AlignedBlock = Tuple[int, int, int]  # (原始malloc地址, 请求大小, 对齐值)
_aligned_blocks: Dict[int, _AlignedBlock] = {}
_aligned_lock = threading.Lock()


def _as_address(value: Any, arg_name: str = "ptr") -> int:
    """把任意"指针样"的参数归一化成裸地址整数
    
    接受：int（malloc()/aligned_alloc() 的返回类型）、ctypes.c_void_p、
    Pointer（.ptr 属性）、ctypes.byref() 的 CArgObject。
    
    异常：
        MemoryError: 参数为 NULL/None 或根本不是指针。
            把 NULL 直接传给 memmove/memcpy/memset 是未定义行为
            （实测为 access violation），必须在调用C库之前拦下。
    """
    if value is None:
        raise MemoryError(f"{arg_name} is NULL")
    
    if isinstance(value, int) and not isinstance(value, bool):
        address = value
    elif isinstance(value, ctypes.c_void_p):
        address = value.value
    elif hasattr(value, 'ptr'):  # cypy_bridge.pointer.Pointer
        return _as_address(value.ptr, arg_name)
    else:
        try:
            address = ctypes.cast(value, ctypes.c_void_p).value
        except (TypeError, ValueError):
            raise MemoryError(f"{arg_name} is not a pointer: {value!r}")
    
    if not address:
        raise MemoryError(f"{arg_name} is NULL")
    return int(address)


def _as_c_void_p(value: Any, arg_name: str = "ptr") -> ctypes.c_void_p:
    """归一化为 ctypes 可直接传给C库的 c_void_p"""
    return ctypes.c_void_p(_as_address(value, arg_name))


def _check_size(size: Any, arg_name: str = "size") -> int:
    """校验长度参数，避免负数被 c_size_t 静默回绕成巨大值"""
    if hasattr(size, 'value') and isinstance(getattr(size, 'value'), int):
        size = size.value  # 接受 ctypes 整数对象 / CDefVariable
    if not isinstance(size, int) or isinstance(size, bool):
        raise MemoryError(f"Invalid {arg_name}: {size!r}")
    if size < 0:
        raise MemoryError(f"Invalid {arg_name}: {size}")
    return size


def malloc(size: int) -> int:
    """分配内存（类似C的malloc）
    
    参数：
        size: 要分配的字节数
    
    返回：
        指向分配内存的裸地址（int）。ctypes 在 restype=c_void_p 时返回的就是 int，
        所以这里可以安全地做地址运算（如 `ptr + 10`），也能直接传给 free()。
    
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
        ptr: 要释放的内存指针（int 地址 / c_void_p / Pointer 均可）
    
    注意：
        - free(NULL) 在C里是合法的空操作，这里保持一致。
        - aligned_alloc() 返回的是对齐后的地址，不是 malloc 的原始地址；
          它登记在 _aligned_blocks 里，本函数会自动换算回原始地址再释放，
          因此对齐块同样可以直接 free()（Windows CRT 释放中间指针会破坏堆）。
    """
    try:
        address = _as_address(ptr)
    except MemoryError:
        return  # free(NULL) 是C定义的空操作
    
    with _aligned_lock:
        block = _aligned_blocks.pop(address, None)
    if block is not None:
        address = block[0]  # 回到 malloc() 的原始地址
    
    _c_stdlib.free(ctypes.c_void_p(address))



def aligned_alloc(alignment: int, size: int) -> int:
    """分配对齐的内存（类似C11的aligned_alloc）
    
    参数：
        alignment: 对齐要求（必须是正的2的幂）
        size: 要分配的字节数
    
    返回：
        指向 size 字节、地址按 alignment 对齐的裸地址（int）
    
    异常：
        MemoryError: 参数非法或分配失败
    
    实现说明：
        Windows 的 CRT 不允许把"堆块中间地址"交给 free()（会破坏堆），
        而 msvcrt.dll 也没有导出 _aligned_malloc。所以这里用
        "多分配 + 向上取整 + 登记表" 的方案：真实交付对齐地址，
        同时把 对齐地址 -> 原始地址 的映射记入 _aligned_blocks，
        由本模块的 free() 换算后释放，调用方仍然只需要 free()。
    """
    size = _check_size(size)
    if size == 0:
        raise MemoryError(f"Invalid size: {size}")
    
    # 检查alignment是否是正的2的幂（alignment == 0 时 0 & -1 == 0，必须单独排除）
    if alignment <= 0 or (alignment & (alignment - 1)) != 0:
        raise MemoryError(f"Alignment must be power of 2: {alignment}")
    
    # 最坏情况下向上取整会浪费 alignment-1 字节，所以多分配这些余量
    ptr = malloc(size + alignment - 1)
    base = _as_address(ptr)
    aligned = ((base + alignment - 1) // alignment) * alignment
    
    if aligned != base:
        with _aligned_lock:
            _aligned_blocks[aligned] = (base, size, alignment)
    
    return aligned



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


def realloc(ptr: Any, size: int) -> Optional[int]:
    """重新分配内存（类似C的realloc）
    
    参数：
        ptr: 原内存指针
        size: 新的大小
    
    返回：
        新的内存地址（int）；size <= 0 时返回 None
    
    异常：
        MemoryError: 内存分配失败，或 ptr 来自 aligned_alloc()
    
    注意：
        realloc() 会原地搬移堆块，无法维持 alignment 约束，
        因此对 aligned_alloc() 得到的地址直接报错，而不是静默返回一个
        不再对齐、且再也无法被 free() 正确换算的地址。

        size <= 0 走的是 C 的 `realloc(p, 0)` 口径：**释放**原内存并返回 None
        （此后调用方不得再使用该地址）。这与 `malloc(0)` 抛 MemoryError 不同——
        那边没有"释放已有内存"的副作用可承担，两边不是同一条规则。
    """
    if size <= 0:
        free(ptr)
        return None
    
    address = _as_address(ptr)
    with _aligned_lock:
        if address in _aligned_blocks:
            raise MemoryError(
                "realloc() cannot move an aligned_alloc() block; "
                "use malloc() + memcpy() + free() instead"
            )
    
    result = _c_stdlib.realloc(ctypes.c_void_p(address), size)
    if not result:
        raise MemoryError(f"Failed to reallocate {size} bytes")
    
    return result


def memset(ptr: Any, value: int, size: int) -> None:
    """填充内存（类似C的memset）
    
    参数：
        ptr: 内存指针
        value: 填充值（0-255）
        size: 填充大小
    
    异常：
        MemoryError: ptr 为 NULL（传给C库就是未定义行为）
    """
    _c_stdlib.memset(_as_c_void_p(ptr), value, _check_size(size))


def memcpy(dest: Any, src: Any, size: int) -> None:
    """复制内存（类似C的memcpy）
    
    参数：
        dest: 目标指针
        src: 源指针
        size: 复制大小
    
    异常：
        MemoryError: dest/src 为 NULL
    """
    c_dest = _as_c_void_p(dest, 'dest')
    c_src = _as_c_void_p(src, 'src')
    _c_stdlib.memcpy(c_dest, c_src, _check_size(size))


def memmove(dest: Any, src: Any, size: int) -> None:
    """移动内存（类似C的memmove，支持重叠区域）
    
    参数：
        dest: 目标指针
        src: 源指针
        size: 移动大小
    
    异常：
        MemoryError: dest/src 为 NULL
    """
    c_dest = _as_c_void_p(dest, 'dest')
    c_src = _as_c_void_p(src, 'src')
    _c_stdlib.memmove(c_dest, c_src, _check_size(size))


def calloc(count: int, size: int) -> int:
    """分配并清零内存（类似C的calloc）
    
    参数：
        count: 元素数量
        size: 每个元素的大小
    
    返回：
        指向分配并清零的内存的裸地址（int）
    """
    total_size = count * size
    ptr = malloc(total_size)
    memset(ptr, 0, total_size)
    return ptr


def aligned_block_count() -> int:
    """当前登记在案、尚未释放的对齐内存块数量（供测试/诊断使用）"""
    with _aligned_lock:
        return len(_aligned_blocks)



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
    'aligned_block_count',
]
