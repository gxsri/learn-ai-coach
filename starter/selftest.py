"""
selftest.py —— 用合成数据验证核心算法，**不需要显卡、不需要视频、不需要联网**。

为什么需要它：
  当你怀疑"指标算错了"的时候，你需要先回答一个问题：
  **是算法错了，还是我的数据太差？**
  这个脚本用"已知正确答案"的合成数据跑一遍算法，就能把这个问号消掉。

跑法（只需要 numpy）：
    python selftest.py

全部通过会打印 [OK] 并以退出码 0 结束。
"""

import sys

# Windows 控制台的默认编码是 GBK，遇到特殊符号会直接抛 UnicodeEncodeError。
# 强制用 UTF-8 输出，并把无法编码的字符替换掉而不是崩溃。
# （如果你在 cmd.exe 里看到中文变成乱码，先执行 chcp 65001）
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import numpy as np

from common import (
    angle_at,
    body_scale,
    detect_hit_events,
    savgol_smooth,
    wrist_speed,
)

PASS = 0
FAIL = 0
FPS = 30
SCALE = 40.0        # 肩宽 40 像素


def check(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  [OK]   {name}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name}  {detail}')


def make_swing_series(n, hit_frames, peak_speed_px_per_frame=8.0, sigma=4.0):
    """
    生成一条"手腕"的 y 轨迹，在指定的击球帧附近各有一个速度脉冲。

    做法：先定义**速度**（一个高斯脉冲），再积分得到**位置**。

    为什么要这么绕？因为如果直接用 `sin(0..pi)` 造一条"抬起再落下"的轨迹，
    它的速度在**起点和终点同时最大**（正弦的导数在两端取极值），
    于是会被正确地检测成**两次**击球 —— 那是测试数据不真实，不是算法错。

    真实的挥拍：速度从 0 升到峰值（击球），再降回 0。**只有一个峰。**
    """
    t = np.arange(n, dtype=float)
    vy = np.zeros(n, dtype=float)
    for hf in hit_frames:
        vy += peak_speed_px_per_frame * np.exp(-((t - hf) ** 2) / (2 * sigma ** 2))
    # 负号：手腕向上移动（图像坐标 y 减小）；cumsum 把速度变成位置
    return -np.cumsum(vy)


# ══════════════════════════════════════════════════════════════════════════════
print('\n[1] 角度计算')
# ══════════════════════════════════════════════════════════════════════════════

a = angle_at((0, 0), (10, 0), (0, 10))
check('90 度直角', abs(a - 90.0) < 1e-6, f'得到 {a}')

a = angle_at((0, 0), (-5, 0), (5, 0))
check('180 度平角', abs(a - 180.0) < 1e-6, f'得到 {a}')

a = angle_at((0, 0), (1, 0), (0.5, np.sqrt(3) / 2))
check('60 度锐角', abs(a - 60.0) < 1e-6, f'得到 {a}')

a = angle_at((0, 0), (0, 0), (1, 1))
check('顶点与某点重合时返回 NaN（不崩溃）', np.isnan(a), f'得到 {a}')

a1 = angle_at((0, 0), (3, 0), (1, 2))
a2 = angle_at((0, 0), (300, 0), (100, 200))
check('角度与整体尺度无关', abs(a1 - a2) < 1e-9, f'{a1} vs {a2}')

check('肩宽计算正确', abs(body_scale(0, 0, 30, 40) - 50.0) < 1e-9)

# 图像坐标的约定：y 向下增大，所以"手腕高于肩" = y 更小
check('图像坐标约定：y 更小表示更靠上', 100 < 200)


# ══════════════════════════════════════════════════════════════════════════════
print('\n[2] Savitzky-Golay 平滑')
# ══════════════════════════════════════════════════════════════════════════════

line = np.linspace(0, 10, 51)
sm = savgol_smooth(line, window=11, polyorder=2)
check('直线被完整保留', np.nanmax(np.abs(sm - line)) < 1e-6,
      f'最大偏差 {np.nanmax(np.abs(sm - line))}')

# ★ 最关键的性质：平滑后**峰值仍在**
t = np.linspace(0, 1, 201)
peak_signal = np.exp(-((t - 0.5) ** 2) / (2 * 0.02 ** 2))
rng = np.random.default_rng(42)
noisy = peak_signal + rng.normal(0, 0.02, t.size)
smoothed = savgol_smooth(noisy, window=11, polyorder=2)

peak_err = abs(smoothed.max() - peak_signal.max())
check('平滑保留了峰值（SG 的核心价值）', peak_err < 0.05,
      f'原峰 {peak_signal.max():.3f}，平滑后 {smoothed.max():.3f}')
check('平滑确实降噪了',
      np.std(smoothed - peak_signal) < np.std(noisy - peak_signal),
      f'平滑后残差 {np.std(smoothed - peak_signal):.4f} '
      f'vs 原始 {np.std(noisy - peak_signal):.4f}')

# 对照：移动平均会削平峰值 —— 这就是不能用它的原因
k = 11
kernel = np.ones(k) / k
moving_avg = np.convolve(np.pad(noisy, (k // 2, k // 2), mode='edge'), kernel, mode='valid')
print(f'         （对照）移动平均峰值 {moving_avg.max():.3f}，'
      f'比真值低 {peak_signal.max() - moving_avg.max():.3f} —— 峰值被削平了')

with_nan = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0])
res = savgol_smooth(with_nan, window=5, polyorder=2)
check('NaN 不会污染相邻点',
      np.isfinite(res[0]) and np.isfinite(res[1]) and np.isfinite(res[3]),
      f'得到 {np.round(res, 2)}')


# ══════════════════════════════════════════════════════════════════════════════
print('\n[3] 手腕速度')
# ══════════════════════════════════════════════════════════════════════════════

N = 90
frames = np.arange(N)
cy = make_swing_series(N, hit_frames=[45])
cx = np.full(N, 100.0)
conf = np.ones(N)

speed, _, _ = wrist_speed(cx, cy, SCALE, FPS, conf=conf)

check('速度序列长度正确', speed.size == N)
check('静止段速度接近 0', speed[0] < 0.5, f'得到 {speed[0]:.3f}')
check('挥拍段速度明显很大', speed.max() > 5.0, f'峰值 {speed.max():.3f}')
check('速度峰值出现在击球帧附近', abs(int(np.argmax(speed)) - 45) <= 3,
      f"峰值在第 {int(np.argmax(speed))} 帧，期望约 45")

speed_low, _, _ = wrist_speed(cx, cy, SCALE, FPS, conf=np.zeros(N), conf_threshold=0.5)
check('置信度不足时速度归零（防止伪造击球）', np.all(speed_low == 0.0),
      f'最大值 {speed_low.max()}')

try:
    wrist_speed(cx, cy, 0.0, FPS)
    check('肩宽为 0 时应该抛错', False, '没有抛错')
except ValueError:
    check('肩宽为 0 时抛出 ValueError（而不是产生 inf）', True)


# ══════════════════════════════════════════════════════════════════════════════
print('\n[4] 击球事件检测')
# ══════════════════════════════════════════════════════════════════════════════

events = detect_hit_events(frames, speed, min_gap_frames=10, min_speed=3.0)
check('单次挥拍被识别为恰好 1 次击球', len(events) == 1,
      f'得到 {len(events)} 次：{[e["frame"] for e in events]}')
if events:
    check('击球帧与真值误差在 5 帧以内', abs(events[0]['frame'] - 45) <= 5,
          f"真值 45，得到 {events[0]['frame']}")

TRUE_HITS = [40, 140, 240]
cy3 = make_swing_series(300, hit_frames=TRUE_HITS)
speed3, _, _ = wrist_speed(np.full(300, 100.0), cy3, SCALE, FPS, conf=np.ones(300))
events3 = detect_hit_events(np.arange(300), speed3, min_gap_frames=10, min_speed=3.0)

check('3 次挥拍被识别为恰好 3 次击球（不多不少）', len(events3) == 3,
      f'得到 {len(events3)} 次：{[e["frame"] for e in events3]}')
if len(events3) == 3:
    errors = [abs(e['frame'] - truth) for e, truth in zip(events3, TRUE_HITS)]
    check('每次击球的帧号误差都在 5 帧以内', max(errors) <= 5,
          f'误差 {errors}，真值 {TRUE_HITS}')

events_high = detect_hit_events(np.arange(300), speed3, min_gap_frames=10, min_speed=1000.0)
check('阈值过高时正确返回空', len(events_high) == 0, f'得到 {len(events_high)} 次')

check('全零速度序列返回空',
      len(detect_hit_events(np.arange(50), np.zeros(50))) == 0)
check('超短序列不崩溃', detect_hit_events(np.arange(2), np.zeros(2)) == [])

# min_gap_frames 的作用：设得太大，两拍之间会被合并
events_merged = detect_hit_events(np.arange(300), speed3, min_gap_frames=200, min_speed=3.0)
check('min_gap_frames 过大时会合并击球（说明这个参数必须按节奏调）',
      len(events_merged) < 3, f'得到 {len(events_merged)} 次')


# ══════════════════════════════════════════════════════════════════════════════
print('\n[5] 为什么投影角不能当关节真值（这是"说明"而不是"缺陷"）')
# ══════════════════════════════════════════════════════════════════════════════

def project(p):
    """弱透视投影：丢掉深度坐标 z。"""
    return (p[0], p[1])


def angle3d(vertex, a, c):
    v = np.asarray(a, float) - np.asarray(vertex, float)
    w = np.asarray(c, float) - np.asarray(vertex, float)
    cos = float(np.dot(v, w) / (np.linalg.norm(v) * np.linalg.norm(w)))
    return float(np.degrees(np.arccos(max(-1.0, min(1.0, cos)))))


# 一个真实的 60 度三维关节角，两条边都朝摄像机方向倾斜
vertex3d = (0.0, 0.0, 0.0)
a3d = (100.0, 0.0, 100.0)
c3d = (0.0, 100.0, 100.0)

true_angle = angle3d(vertex3d, a3d, c3d)
proj_angle = angle_at(project(vertex3d), project(a3d), project(c3d))

check('三维真值 60 度的关节角，在画面上量出来是 90 度',
      abs(true_angle - 60.0) < 1e-6 and abs(proj_angle - 90.0) < 1e-6,
      f'真值 {true_angle:.1f} 度，投影后 {proj_angle:.1f} 度')
print(f'         （误差 {abs(true_angle - proj_angle):.0f} 度 —— 和机位角度强相关）')
print('     [!] 结论：单目算出的角度是【画面投影角】，不是关节真值。')
print('         报告里必须标注；只做同一机位的纵向对比；差异小于 10 度不下结论。')


# ══════════════════════════════════════════════════════════════════════════════
print(f'\n{"=" * 60}')
print(f'通过 {PASS} 项，失败 {FAIL} 项')
print('=' * 60)

if FAIL == 0:
    print('\n[OK] 核心算法自检全部通过。')
    print('     这意味着：如果你的指标看起来不对，问题更可能出在')
    print('     数据质量（跟踪跳变、遮挡、模糊）或参数设置上，而不是算法本身。')
else:
    print(f'\n[FAIL] 有 {FAIL} 项失败，请先修好再往下做。')

sys.exit(1 if FAIL else 0)
