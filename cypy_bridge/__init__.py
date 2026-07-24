"""
Cypy Bridge Library

提供与Cython等价的核心功能，作为移除Cython依赖的桥接层。

主要组件：
- types: 类型系统和类型映射
- memory: 内存管理（malloc, free, sizeof）
- pointer: 指针操作
- struct: 结构体定义
- defer: 资源管理机制
- compiler: 编译API
"""

from .types import (
    TypeMapper,
    cdef,
    cpdef,
    int_,
    float_,
    double_,
    bool_,
    str_,
    void,
    size_t,
    cast,
    ccast,
    # 扩展类型别名
    long_,
    longlong_,
    short_,
    char_,
    byte_,
    ubyte_,
    uint_,
    ulong_,
    ulonglong_,
    ushort_,
    int32_,
    int64_,
    uint32_,
    uint64_,
    ssize_t,
    ptrdiff_t,
    longdouble_,
    void_p,
)

from .memory import (
    malloc,
    free,
    sizeof,
    aligned_alloc,
)

from .pointer import (
    Pointer,
    ptr,
    deref,
    addr,
)

from .struct import (
    Struct,
    struct,
)

from .defer import (
    defer,
    DeferManager,
)

from .enum import (
    CEnum,
    enum,
    cdef_enum,
    enum_value,
)

from .union import (
    CUnion,
    CUnionType,
    cdef_union,
    union,
)

from .generics import (
    FusedType,
    FusedFunction,
    fused,
    generic,
    GenericError,
    # 预设融合类型
    Numeric,
    Integer,
    Floating,
    AnyType,
)

from .meta import (
    CypyMetaClass,
    TypeCheckedMeta,
    AutoSlotsMeta,
    SingletonMeta,
    meta,
    cdef_meta,
    MetaError,
)

from .nogil import (
    nogil,
    nogil_thread,
    nogil_pool,
    nogil_exec,
    nogil_parallel,
    release_gil,
    acquire_gil,
    GilState,
    NoGilError,
)

from .compiler import (
    compile_module,
    compile_code,
    BridgeCompiler,
    CompileResult,
)

__all__ = [
    # types
    'TypeMapper',
    'cdef',
    'cpdef',
    'int_',
    'float_',
    'double_',
    'bool_',
    'str_',
    'void',
    'size_t',
    'cast',
    'ccast',
    # extended types
    'long_',
    'longlong_',
    'short_',
    'char_',
    'byte_',
    'ubyte_',
    'uint_',
    'ulong_',
    'ulonglong_',
    'ushort_',
    'int32_',
    'int64_',
    'uint32_',
    'uint64_',
    'ssize_t',
    'ptrdiff_t',
    'longdouble_',
    'void_p',
    
    # memory
    'malloc',
    'free',
    'sizeof',
    'aligned_alloc',
    
    # pointer
    'Pointer',
    'ptr',
    'deref',
    'addr',
    
    # struct
    'Struct',
    'struct',
    
    # defer
    'defer',
    'DeferManager',
    
    # enum
    'CEnum',
    'enum',
    'cdef_enum',
    'enum_value',
    
    # union
    'CUnion',
    'CUnionType',
    'cdef_union',
    'union',
    
    # generics
    'FusedType',
    'FusedFunction',
    'fused',
    'generic',
    'GenericError',
    'Numeric',
    'Integer',
    'Floating',
    'AnyType',
    
    # meta
    'CypyMetaClass',
    'TypeCheckedMeta',
    'AutoSlotsMeta',
    'SingletonMeta',
    'meta',
    'cdef_meta',
    'MetaError',
    
    # nogil
    'nogil',
    'nogil_thread',
    'nogil_pool',
    'nogil_exec',
    'nogil_parallel',
    'release_gil',
    'acquire_gil',
    'GilState',
    'NoGilError',
    
    # compiler
    'compile_module',
    'compile_code',
    'BridgeCompiler',
    'CompileResult',
]

__version__ = '0.1.0'
