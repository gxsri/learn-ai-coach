"""
common.py —— 公共常量与核心算法。

设计原则：
  * 只依赖 numpy，所以这个文件里的算法可以脱离显卡、脱离视频单独测试
    （见 selftest.py —— 不用显卡、不用视频就能验证算法对不对）
  * 关键点索引用**常量名**，不用魔法数字

关键点索引来自 COCO-17。**这是 YOLO-pose 的输出格式。**
不要把 MediaPipe 的 33 点索引套到这里来，它们完全不同。
"""

from __future__ import annotations

import numpy as np

# ── COCO-17 关键点 ────────────────────────────────────────────────────────────
# 索引 → 名字
KEYPOINT_NAMES = [
    'nose',            # 0
    'left_eye',        # 1
    'right_eye',       # 2
    'left_ear',        # 3
    'right_ear',       # 4
    'left_shoulder',   # 5
    'right_shoulder',  # 6
    'left_elbow',      # 7
    'right_elbow',     # 8
    'left_wrist',      # 9
    'right_wrist',     # 10
    'left_hip',        # 11
    'right_hip',       # 12
    'left_knee',       # 13
    'right_knee',      # 14
    'left_ankle',      # 15
    'right_ankle',     # 16
]

# 名字 → 索引。写代码时请用这个，不要写 5、7、9 这种数字。
KP = {name: i for i, name in enumerate(KEYPOINT_NAMES)}

# 骨架连线表（COCO-17）。用来把关键点画成"火柴人"。
# 每个元组是一根骨头，两端是关键点索引。
SKELETON_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),          # 头：鼻子-眼-耳
    (5, 6),                                   # 两肩
    (5, 7), (7, 9),                           # 左臂：肩-肘-腕
    (6, 8), (8, 10),                          # 右臂：肩-肘-腕
    (5, 11), (6, 12), (11, 12),               # 躯干：肩-髋 + 两髋
    (11, 13), (13, 15),                       # 左腿：髋-膝-踝
    (12, 14), (14, 16),                       # 右腿：髋-膝-踝
]

# 注意：5 是**左**肩。很多人会搞反。
L_SHOULDER = KP['left_shoulder']    # 5
R_SHOULDER = KP['right_shoulder']   # 6
L_ELBOW = KP['left_elbow']          # 7
R_ELBOW = KP['right_elbow']         # 8
L_WRIST = KP['left_wrist']          # 9
R_WRIST = KP['right_wrist']         # 10
L_HIP = KP['left_hip']              # 11
R_HIP = KP['right_hip']             # 12
L_KNEE = KP['left_knee']            # 13
R_KNEE = KP['right_knee']           # 14
L_ANKLE = KP['left_ankle']          # 15
R_ANKLE = KP['right_ankle']         # 16

# ── 默认参数（都可以在命令行覆盖）─────────────────────────────────────────────
DEFAULT_CONF_THRESHOLD = 0.5      # 关键点置信度低于它 → 这个点不可信
DEFAULT_WINDOW = 11               # Savitzky-Golay 窗口（奇数）
DEFAULT_POLYORDER = 2             # Savitzky-Golay 多项式阶数
DEFAULT_MIN_GAP_FRAMES = 10       # 两次击球至少间隔帧数（30fps 下约 0.33 秒）
DEFAULT_MIN_SPEED = 3.0           # 最小手腕速度，单位：肩宽/秒
DEFAULT_MIN_ANGLE_DELTA = 10.0    # 角度差异小于它就不下结论（度）


# ══════════════════════════════════════════════════════════════════════════════
# 几何
# ══════════════════════════════════════════════════════════════════════════════

def angle_at(vertex, point_a, point_c) -> float:
    """
    计算以 vertex 为顶点的夹角，返回**度**。三个参数都是 (x, y)。

    ⚠️ 重要：输入是像素坐标，所以输出是【画面投影角】，
       不是生物力学意义上的关节角。单目 2D 存在系统性低估
       （对照研究测得髋约 −11.2°、膝约 −10.6°）。
       报告里必须标注"投影角"，且只做同机位的纵向对比。
    """
    a = np.asarray(point_a, dtype=float)
    b = np.asarray(vertex, dtype=float)
    c = np.asarray(point_c, dtype=float)

    v1 = a - b
    v2 = c - b
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 < 1e-6 or n2 < 1e-6:
        return float('nan')     # 两点重合，角度无定义

    cos = float(np.dot(v1, v2) / (n1 * n2))
    cos = max(-1.0, min(1.0, cos))      # 浮点误差可能让它超出 [-1, 1]
    return float(np.degrees(np.arccos(cos)))


def body_scale(x_left, y_left, x_right, y_right) -> float:
    """
    用身体的某个"宽度"做尺度基准。**不要用检测框的宽高**——
    杀球时手臂高举、腿大幅伸展，框会剧烈变化。

    推荐传肩（5-6）或髋（11-12）这两个点。
    """
    return float(np.hypot(float(x_left) - float(x_right), float(y_left) - float(y_right)))


# ══════════════════════════════════════════════════════════════════════════════
# 信号处理
# ══════════════════════════════════════════════════════════════════════════════

def savgol_smooth(y, window: int = DEFAULT_WINDOW, polyorder: int = DEFAULT_POLYORDER):
    """
    Savitzky-Golay 平滑：在滑动窗口里做多项式最小二乘拟合，取中心点的拟合值。

    **为什么不用移动平均**：移动平均会把峰值削平，而"击球"恰恰就是一个速度峰值。
    SG 滤波在降噪的同时能保留峰的形状。

    NaN 会被排除在拟合之外；如果窗口内有效点太少，原样返回该点。

    window 必须是奇数；太小没效果，太大（> 21 左右）会把真实峰值抹平。
    30fps 视频建议从 11 开始试。
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n == 0:
        return y.copy()

    if window % 2 == 0:
        window += 1
    half = window // 2

    out = np.empty(n, dtype=float)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        ys = y[lo:hi]
        ok = np.isfinite(ys)

        # 有效点不够拟合 → 不猜，原样输出（可能是 NaN，让调用方看见）
        if ok.sum() <= polyorder:
            out[i] = y[i]
            continue

        xs = np.arange(lo, hi, dtype=float)[ok]
        coeffs = np.polyfit(xs, ys[ok], polyorder)
        out[i] = float(np.polyval(coeffs, float(i)))

    return out


def wrist_speed(x, y, scale: float, fps: float, window: int = DEFAULT_WINDOW,
                polyorder: int = DEFAULT_POLYORDER, conf=None,
                conf_threshold: float = DEFAULT_CONF_THRESHOLD):
    """
    算出逐帧的手腕速度，单位是【肩宽／秒】。

    用肩宽归一化，是为了让不同距离、不同身高的球员之间可比。

    返回 (speed, x_smooth, y_smooth)。
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    x_s = savgol_smooth(x, window=window, polyorder=polyorder)
    y_s = savgol_smooth(y, window=window, polyorder=polyorder)

    if fps <= 0:
        raise ValueError(f'fps 必须为正数，收到 {fps}')
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError(f'尺度(肩宽)必须为正数，收到 {scale}')

    # np.gradient 是中心差分；对端点用单侧差分
    vx = np.gradient(x_s) * fps
    vy = np.gradient(y_s) * fps
    speed = np.hypot(vx, vy) / scale

    # ★ 置信度太低的关键点算出来的"速度"是噪声，必须归零，
    #   否则一个乱跳的手腕会伪造出一次击球。
    if conf is not None:
        conf = np.asarray(conf, dtype=float)
        speed = np.where(np.isfinite(conf) & (conf >= conf_threshold), speed, 0.0)

    return speed, x_s, y_s


# ══════════════════════════════════════════════════════════════════════════════
# 击球检测
# ══════════════════════════════════════════════════════════════════════════════

def detect_hit_events(frames, speed, *, min_gap_frames: int = DEFAULT_MIN_GAP_FRAMES,
                      min_speed: float = DEFAULT_MIN_SPEED):
    """
    从手腕速度序列里找出击球事件。

    做法：
      1. 找局部极大值（比左右邻居都快）
      2. 过滤掉低于 min_speed 的（那不是击球，只是手在动）
      3. 如果两个候选离得太近（< min_gap_frames），只保留更快的那个
         —— 否则一次挥拍会被拆成好几个"击球"

    返回 [{'frame': int, 'speed': float, 'index': int}, ...]
    """
    frames = np.asarray(frames)
    speed = np.asarray(speed, dtype=float)
    n = speed.size
    if n < 3:
        return []

    events = []
    for i in range(1, n - 1):
        s = speed[i]
        if not np.isfinite(s) or s < min_speed:
            continue
        if not (s >= speed[i - 1] and s >= speed[i + 1]):
            continue        # 不是局部极大

        frame = int(frames[i])
        if events and (frame - events[-1]['frame']) < min_gap_frames:
            # 离上一次太近：保留更快的那次，并替换
            if s > events[-1]['speed']:
                events[-1] = {'frame': frame, 'speed': float(s), 'index': i}
            continue

        events.append({'frame': frame, 'speed': float(s), 'index': i})

    return events


# ══════════════════════════════════════════════════════════════════════════════
# 场地标定
# ══════════════════════════════════════════════════════════════════════════════

# 羽毛球场地真值（米）。做标定时必须用这些数字。
COURT = {
    'length_m': 13.40,          # 场地总长
    'width_doubles_m': 6.10,    # 双打宽
    'width_singles_m': 5.18,    # 单打宽
    'net_height_center_m': 1.524,
    'net_height_post_m': 1.55,
    'short_service_line_m': 1.98,   # 前发球线到网
    'doubles_long_service_m': 0.76, # 双打后发球线到端线
}


def homography_from_points(pixel_points, world_points):
    """
    用 4 组对应点求单应矩阵（像素 ↔ 真实米制平面）。

    ⚠️ 需要 opencv。这个函数放在这里是提醒你：标定是必须做的一步。
    ⚠️ 单应变换成立的前提是"所有点在同一平面上"。
       球员身体是立体的 —— 地上的点准，空中的点**不准**。
       想算"击球点离地多高"，必须明确标注误差范围。

    返回 (H, 重投影误差数组)。误差超过 5 像素说明角点选得不好。
    """
    import cv2      # 延迟导入：没装 opencv 也能用这个模块的其它功能

    src = np.asarray(pixel_points, dtype=np.float32).reshape(-1, 1, 2)
    dst = np.asarray(world_points, dtype=np.float32).reshape(-1, 1, 2)
    if src.shape[0] != 4 or dst.shape[0] != 4:
        raise ValueError('需要正好 4 组对应点')

    H, _ = cv2.findHomography(src, dst)
    if H is None:
        raise RuntimeError('求单应矩阵失败，检查 4 个点是不是共线了')

    H_inv = np.linalg.inv(H)
    back = cv2.perspectiveTransform(dst, H_inv).reshape(-1, 2)
    error = np.linalg.norm(back - src.reshape(-1, 2), axis=1)
    return H, error
