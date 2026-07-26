# SIMD向量

## 向量类型

### 基本向量

```python
# 2D向量
let v2: Vec2[int] = Vec2(10, 20)
let v2f: Vec2[float] = Vec2(3.14, 2.71)

# 3D向量
let v3: Vec3[int] = Vec3(1, 2, 3)
let v3f: Vec3[float] = Vec3(1.0, 2.0, 3.0)

# 4D向量
let v4: Vec4[int] = Vec4(1, 2, 3, 4)
let v4f: Vec4[float] = Vec4(1.0, 2.0, 3.0, 4.0)
```

### 向量构造

```python
# 从标量构造
let v: Vec3[float] = Vec3.fill(5.0)  # (5.0, 5.0, 5.0)

# 从元组构造
let v: Vec2[int] = Vec2.from_tuple((10, 20))

# 从列表构造
let v: Vec3[float] = Vec3.from_list([1.0, 2.0, 3.0])
```

## 向量运算

### 基本运算

```python
# 向量加法
let a: Vec3[float] = Vec3(1.0, 2.0, 3.0)
let b: Vec3[float] = Vec3(4.0, 5.0, 6.0)
let c: Vec3[float] = a + b  # (5.0, 7.0, 9.0)

# 向量减法
let d: Vec3[float] = a - b  # (-3.0, -3.0, -3.0)

# 向量乘法（逐元素）
let e: Vec3[float] = a * b  # (4.0, 10.0, 18.0)

# 向量除法（逐元素）
let f: Vec3[float] = b / a  # (4.0, 2.5, 2.0)
```

### 标量运算

```python
# 标量乘法
let v: Vec3[float] = Vec3(1.0, 2.0, 3.0)
let scaled: Vec3[float] = v * 2.0  # (2.0, 4.0, 6.0)

# 标量除法
let divided: Vec3[float] = v / 2.0  # (0.5, 1.0, 1.5)
```

### 向量函数

```python
# 点积
let dot_product: float = a.dot(b)  # 1*4 + 2*5 + 3*6 = 32

# 叉积（仅3D）
let cross_product: Vec3[float] = a.cross(b)

# 长度
let length: float = a.length()  # sqrt(1+4+9) = sqrt(14)

# 归一化
let normalized: Vec3[float] = a.normalize()
```

## 向量变换

### 矩阵乘法

```python
# 向量与矩阵相乘
let v: Vec4[float] = Vec4(1.0, 2.0, 3.0, 1.0)
let m: Mat4[float] = Mat4.identity()
let result: Vec4[float] = m * v
```

### 旋转

```python
# 绕X轴旋转
let rotated: Vec3[float] = v3.rotate_x(45.0)

# 绕Y轴旋转
let rotated: Vec3[float] = v3.rotate_y(45.0)

# 绕Z轴旋转
let rotated: Vec3[float] = v3.rotate_z(45.0)
```

## SIMD优化

### 自动SIMD

```python
# Cypy自动使用SIMD指令优化向量运算
let a: Vec4[float] = Vec4(1.0, 2.0, 3.0, 4.0)
let b: Vec4[float] = Vec4(5.0, 6.0, 7.0, 8.0)
let c: Vec4[float] = a + b  # 使用SSE/AVX指令
```

### 对齐内存

```python
# 向量类型自动对齐到SIMD边界
let v: Vec4[float] = Vec4(1.0, 2.0, 3.0, 4.0)
# v 在内存中对齐到 16 字节边界
```

## SIMD向量特性

| 特性 | 说明 |
|------|------|
| **向量类型** | `Vec2`, `Vec3`, `Vec4` 支持多种数值类型 |
| **基本运算** | `+`, `-`, `*`, `/` 逐元素运算 |
| **标量运算** | 向量与标量的运算 |
| **向量函数** | `dot`, `cross`, `length`, `normalize` |
| **矩阵乘法** | 支持 `Mat4 * Vec4` |
| **旋转变换** | 支持绕X/Y/Z轴旋转 |
| **SIMD优化** | 自动使用SSE/AVX指令 |
| **内存对齐** | 自动对齐到SIMD边界 |