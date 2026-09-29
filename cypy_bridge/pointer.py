"""
Cypy Bridge Pointer Operations

提供与Cython等价的指针操作功能，包括指针解引用、地址运算等。
同时提供LZ风格的所有权语义模拟，通过弱引用实现。
"""

import ctypes
import weakref
from typing import Any, Callable, Type, Optional, Generic, TypeVar
from .core import BridgeError, PointerError
from .types import _type_mapper

T = TypeVar('T')


# ctypes 实例的 _type_ 是单字符类型码（c_int -> 'l'），必须反查回真正的 ctypes 类型，
# 否则 base_type 会是一个字符串，deref()/offset()/sizeof() 全部炸掉。
_CTYPE_CODES = {
    'b': ctypes.c_byte, 'B': ctypes.c_ubyte,
    'c': ctypes.c_char, 'u': ctypes.c_wchar,
    'h': ctypes.c_short, 'H': ctypes.c_ushort,
    'i': ctypes.c_int, 'I': ctypes.c_uint,
    'l': ctypes.c_long, 'L': ctypes.c_ulong,
    'q': ctypes.c_longlong, 'Q': ctypes.c_ulonglong,
    'f': ctypes.c_float, 'd': ctypes.c_double,
    'g': ctypes.c_longdouble,
    'z': ctypes.c_char_p, 'Z': ctypes.c_wchar_p,
    'P': ctypes.c_void_p, 'x': ctypes.c_char_p,
    'O': ctypes.py_object, 'S': ctypes.py_object, 'U': ctypes.py_object,
}

# 无法（或不宜）建立弱引用的"值语义"对象，由 Owned 直接强引用持有：
# int/float/str/tuple/list/dict/bool/None 上 weakref.ref() 会抛 TypeError；
# ctypes 值对象（见 _is_ctypes_instance）虽然可以建立弱引用，但
# Owned(ctypes.c_int(42)) 这类临时对象会在 __init__ 返回后立即被回收，
# 让所有权句柄静默变成 NULL。
_VALUE_TYPES = (
    int, float, complex, str, bytes, bytearray, tuple, list, dict, set,
    frozenset, range, type(None),
)


def _is_ctypes_type(candidate: Any) -> bool:
    """candidate 是否是一个可用的 ctypes 类型
    
    用公开的 ctypes.sizeof() 判定：ctypes._CData 在部分 CPython 版本里
    并没有从 ctypes / _ctypes 导出，直接引用会 AttributeError。
    """
    if not isinstance(candidate, type):
        return False
    try:
        ctypes.sizeof(candidate)
    except TypeError:
        return False
    return True


def _is_ctypes_instance(candidate: Any) -> bool:
    """candidate 是否是一个 ctypes 实例（c_int(42)、数组、结构体、指针…）"""
    return not isinstance(candidate, type) and _is_ctypes_type(type(candidate))


def _resolve_base_type(candidate: Any) -> Type:
    """把"任何像类型的东西"归一化成可实例化/可 sizeof 的 ctypes 类型
    
    参数：
        candidate: ctypes 类型、ctypes 类型码字符串（'l'/'i'/...）、
                   Cypy 类型名（'int'/'double'/...）或 None
    
    返回：
        ctypes 类型对象
    
    异常：
        PointerError: 无法解析成 ctypes 类型
    """
    if candidate is None:
        return ctypes.c_void_p
    if _is_ctypes_type(candidate):
        return candidate
    if isinstance(candidate, type):
        # 普通 Python 类型（int/float/...）→ 对应的 ctypes 类型
        python_to_ctype = {
            bool: ctypes.c_bool,
            int: ctypes.c_int,
            float: ctypes.c_double,
            bytes: ctypes.c_char_p,
            str: ctypes.c_char_p,
            type(None): ctypes.c_void_p,  # to_ctypes("void") 返回 NoneType
        }
        if candidate in python_to_ctype:
            return python_to_ctype[candidate]
        if issubclass(candidate, str):
            return ctypes.c_char_p
        raise PointerError(f"Cannot use {candidate!r} as a pointer base type")
    if isinstance(candidate, str):
        if candidate in _CTYPE_CODES:
            return _CTYPE_CODES[candidate]
        try:
            # 映射结果可能是 NoneType（"void"）或 Python 类型，再归一化一次
            return _resolve_base_type(_type_mapper.to_ctypes(candidate))
        except Exception as e:
            raise PointerError(f"Unknown pointer base type '{candidate}': {e}")
    # 实例（而不是类型）：取其类型
    return _resolve_base_type(type(candidate))


class Pointer:
    """指针类：封装ctypes指针操作"""
    
    def __init__(self, ptr, base_type: Type = ctypes.c_void_p, keepalive: Any = None):
        self._ptr = ptr
        self._base_type = _resolve_base_type(base_type)
        # 保存被指对象的强引用：byref()/addressof 都不会延长目标生命周期，
        # 否则 ptr(ctypes.c_int(42)) 这种"临时对象取址"会立刻变成悬垂指针。
        self._keepalive = keepalive
    
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
        ptr = self._ptr
        if ptr is None:
            return 0
        if isinstance(ptr, int):
            return ptr
        if isinstance(ptr, ctypes.c_void_p):
            # c_void_p 的 value 就是目标地址（NULL 时为 None）
            return ptr.value or 0
        try:
            # POINTER(...) 实例、byref() 返回的 CArgObject 都能被 cast 成 c_void_p，
            # 这是唯一能同时覆盖这几种表示的取址方式
            return ctypes.cast(ptr, ctypes.c_void_p).value or 0
        except (TypeError, ValueError):
            pass
        if hasattr(ptr, '_objects'):
            try:
                return ctypes.addressof(ptr.contents)
            except (ValueError, AttributeError):
                return ctypes.addressof(ptr)
        try:
            return ctypes.addressof(ptr)
        except TypeError:
            return int(ptr)
    
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
        return Pointer(new_ptr, self._base_type, keepalive=self._keepalive)
    
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
    
    def __hash__(self) -> int:
        """指针哈希：与 __eq__ 一致（同一地址即同一指针）
        
        注意：定义了 __eq__ 的类若不提供 __hash__，Python 会把 __hash__ 置为 None，
        导致 Pointer 不能作 dict 键或 set 元素。
        """
        try:
            return hash(self._get_address())
        except (TypeError, ValueError):
            return hash(id(self))
    
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
    
    注意：
        - base_type 必须是真正的 ctypes 类型。ctypes 实例的 `_type_` 只是单字符
          类型码（c_int 是 'l'），拿它当 base_type 会让 deref()/offset() 崩掉，
          所以这里优先使用实例的类型对象。
        - 返回的 Pointer 用 cast() 得到真实的 POINTER 对象而不是 byref() 的
          CArgObject，这样 _get_address()/__eq__/__repr__/offset() 都能算出自己的地址。
        - 对临时对象（如 ptr(ctypes.c_int(42))）保持强引用，避免立刻悬垂。
    """
    try:
        if type_name:
            base_type = _resolve_base_type(type_name)
        elif isinstance(obj, ctypes._Pointer):
            # 已经是指针实例：_type_ 是 (基础类型, 偏移) 元组
            inner = getattr(obj, '_type_', None)
            base_type = _resolve_base_type(inner[0] if isinstance(inner, tuple) else inner)
            return Pointer(obj, base_type, keepalive=obj)
        elif _is_ctypes_instance(obj):
            base_type = type(obj)
        else:
            base_type = _resolve_base_type(obj if isinstance(obj, type) else type(obj))
        
        if _is_ctypes_instance(obj):
            target = obj
        else:
            # 普通Python值（int/float/bool/bytes）先装箱成对应的ctypes对象
            try:
                target = base_type(obj)
            except (TypeError, ValueError) as e:
                raise PointerError(f"Cannot take the address of {obj!r}: {e}")
        
        # cast() 会把 byref() 的目标地址物化成真正的指针对象，
        # 而 keepalive 负责延长目标对象的生命周期
        holder = ctypes.cast(ctypes.byref(target), ctypes.POINTER(base_type))
        return Pointer(holder, base_type, keepalive=target)
    except PointerError:
        raise
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
        # BUG-23: c_void_p 也有 .value，原先放在 hasattr 分支之后即成死代码，
        # 于是 addr(c_void_p(4096)) 返回盒子地址、addr(c_void_p(0)) 返回非零，
        # 用户的 NULL 判定永不成立。必须优先按 c_void_p 取其指向的值。
        if isinstance(obj, ctypes.c_void_p):
            return obj.value or 0
        elif hasattr(obj, 'value'):
            return ctypes.addressof(obj)
        elif isinstance(obj, ctypes._Pointer):
            return ctypes.addressof(obj.contents)
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
        new_type = _resolve_base_type(new_type)
        new_ptr = ctypes.cast(pointer.ptr, ctypes.POINTER(new_type))
        return Pointer(new_ptr, new_type, keepalive=pointer._keepalive)
    except Exception as e:
        raise PointerError(f"Failed to cast pointer: {e}")


def null_ptr(type_name: str = "void") -> Pointer:
    """创建空指针
    
    参数：
        type_name: 类型名称
    
    返回：
        空Pointer对象
    """
    base_type = _resolve_base_type(type_name)
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
    - 对支持弱引用的对象使用弱引用存储，不增加引用计数
    - 对不可弱引用的"值语义"对象（int/float/str/tuple/list/dict/bool/None、
      ctypes 值对象）退化为强引用，保证 Owned(10)/own([1,2,3]) 可用
    - 支持所有权转移（transfer_ownership）
    - 支持借用（borrow）- 创建临时引用而不转移所有权
    - 当内部对象被销毁时，Owned 变为无效状态
    """
    
    def __init__(self, value: T):
        """创建一个 Owned 对象
        
        参数：
            value: 要拥有所有权的对象
        
        注意：
            只有支持弱引用的对象才走真正的弱引用语义（原对象被 del 后 Owned 失效）。
            int/float/str/tuple/list/dict/bool/None 以及 ctypes 值对象无法建立弱引用
            （weakref.ref() 直接抛 TypeError，或临时对象会立刻变成死引用），
            对这些"值语义"对象改为持有强引用，否则 Owned(10)/own([1,2,3]) 根本无法构造，
            或得到一个静默为 NULL 的所有权句柄。
        """
        self._strong_cell: Optional[list] = None
        self._weak_ref: Callable[[], Any]
        if not isinstance(value, _VALUE_TYPES) and not _is_ctypes_instance(value):
            try:
                ref = weakref.ref(value)
            except TypeError:
                pass  # 不可弱引用，落到下面的强引用盒子
            else:
                self._weak_ref = ref  # 真正的弱引用语义
                self._is_valid = True
                return
        # 不可弱引用（或本身就是值语义类型）：用列表盒子持有强引用，
        # 盒子本身永远不是 None，所以 Owned(None) 依然是有效句柄
        self._strong_cell = [value]
        self._weak_ref = lambda: self._strong_cell
        self._is_valid = True
    
    def _get(self) -> Any:
        """取回被持有的对象；弱引用已失效时返回 None"""
        if self._strong_cell is not None:
            return self._strong_cell[0]
        return self._weak_ref()
    
    @property
    def is_valid(self) -> bool:
        """检查 Owned 是否仍然有效（内部对象是否还存在）"""
        if not self._is_valid:
            return False
        if self._strong_cell is not None:
            return True
        return self._weak_ref() is not None
    
    def take(self) -> T:
        """获取内部对象并使 Owned 失效
        
        返回：
            内部对象
            
        注意：调用此方法后，Owned 对象变为无效状态，
        不能再访问其内部对象。
        """
        if not self._is_valid:
            raise PointerError("Cannot take from invalid Owned")
        obj = self._get()
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
        return Borrowed(self._get, held_strong=self._strong_cell is not None)
    
    def transfer(self) -> 'Owned[T]':
        """转移所有权到新的 Owned 对象
        
        返回：
            新的 Owned 对象，原 Owned 变为无效
            
        注意：调用此方法后，原 Owned 对象变为无效状态。
        """
        if not self._is_valid:
            raise PointerError("Cannot transfer from invalid Owned")
        obj = self._get()
        self._is_valid = False
        return Owned(obj)
    
    def __bool__(self) -> bool:
        """检查 Owned 是否有效且非空"""
        return self.is_valid
    
    def __repr__(self) -> str:
        if not self._is_valid:
            return "Owned(INVALID)"
        obj = self._get()
        if obj is None and self._strong_cell is None:
            return "Owned(NULL)"
        return f"Owned({type(obj).__name__}, {repr(obj)})"


class Borrowed(Generic[T]):
    """
    借用引用类，表示对 Owned 对象的临时引用。
    
    Borrowed<T> 不拥有对象的所有权，只是临时访问。
    如果原 Owned 对象被销毁，Borrowed 变为无效状态。
    """
    
    def __init__(self, weak_ref: Callable[[], Any], held_strong: bool = False):
        """创建一个 Borrowed 对象
        
        参数：
            weak_ref: 取回原对象的 callable（弱引用或强引用读取器）
            held_strong: 原对象是否被强引用持有（值语义对象不可弱引用）
        """
        self._weak_ref = weak_ref
        self._held_strong = held_strong
    
    @property
    def is_valid(self) -> bool:
        """检查借用是否仍然有效"""
        if self._held_strong:
            return True
        return self._weak_ref() is not None
    
    def deref(self) -> T:
        """解引用获取对象
        
        返回：
            借用的对象
            
        抛出：
            PointerError: 如果借用已失效
        """
        obj = self._weak_ref()
        if obj is None and not self._held_strong:
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
