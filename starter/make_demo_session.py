"""
make_demo_session.py —— 生成一份**合成的骨架 CSV**，用来在没有视频、没有显卡的情况下
完整跑通 03 和 04 两个步骤。

为什么需要它：
  真实的坑是"视频效果不好"和"代码有 bug"混在一起，分不清是哪个。
  用合成数据先跑通一次，你就有了一条"已知正确答案"的基准线：
  · 合成数据能跑出合理结果 → 代码是对的，问题在数据
  · 合成数据也跑不出结果 → 代码/参数有问题，跟你的视频无关

用法：
    python make_demo_session.py                     # 生成 2 个球员、3 次击球
    python make_demo_session.py --session demo2 --hits 5

然后：
    python 03_events_and_metrics.py --session demo
    python 04_report.py --session demo

只有 numpy 也能跑（不依赖 pandas / torch / opencv）。
"""

import argparse
import csv
import json
import os
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from common import KEYPOINT_NAMES

# 一个"标准站姿"的 17 个关键点（像素坐标，画面 1280x960）
# 顺序严格对应 COCO-17
BASE_POSE = np.array([
    [640, 300],    # 0  nose
    [628, 292],    # 1  left_eye
    [652, 292],    # 2  right_eye
    [615, 296],    # 3  left_ear
    [665, 296],    # 4  right_ear
    [610, 360],    # 5  left_shoulder
    [670, 360],    # 6  right_shoulder
    [600, 450],    # 7  left_elbow
    [680, 450],    # 8  right_elbow
    [595, 540],    # 9  left_wrist
    [685, 540],    # 10 right_wrist
    [615, 520],    # 11 left_hip
    [665, 520],    # 12 right_hip
    [610, 690],    # 13 left_knee
    [670, 690],    # 14 right_knee
    [605, 860],    # 15 left_ankle
    [675, 860],    # 16 right_ankle
], dtype=float)

R_SHOULDER, R_ELBOW, R_WRIST = 6, 8, 10


def swing_pulse(n_frames, hit_frames, sigma=4.0, amplitude=200.0):
    """
    生成每帧的"挥拍位移量"（单位：像素）。

    先定义**速度**（高斯脉冲），再积分得到位移 —— 这样速度就只有一个峰，
    符合真实挥拍（加速 → 击球 → 减速），而不是"抬起又落下"那样的双峰。
    """
    t = np.arange(n_frames, dtype=float)
    velocity = np.zeros(n_frames, dtype=float)
    for hf in hit_frames:
        velocity += (amplitude / (sigma * np.sqrt(2 * np.pi))) * \
                    np.exp(-((t - hf) ** 2) / (2 * sigma ** 2))
    return np.cumsum(velocity)


def build_player(track_id, n_frames, hit_frames, rng, dx=0.0, dy=0.0,
                 sigma=4.0, amplitude=200.0, sway=12.0):
    """造一个球员的骨架序列。"""
    pose = BASE_POSE.copy()
    pose[:, 0] += dx
    pose[:, 1] += dy

    # 缓慢的整体晃动（模拟站姿微调），让数据不是死的
    sway_x = sway * np.sin(np.linspace(0, 4 * np.pi, n_frames))
    sway_y = (sway / 2) * np.sin(np.linspace(0, 6 * np.pi, n_frames) + 1.0)

    rows = []
    displacement = swing_pulse(n_frames, hit_frames, sigma=sigma, amplitude=amplitude)

    for f in range(n_frames):
        kp = pose.copy()
        # 全身随重心缓慢移动
        kp[:, 0] += sway_x[f]
        kp[:, 1] += sway_y[f]

        # 右臂挥动：手腕向上（y 减小）并略向前；肘跟着动一部分
        d = displacement[f]
        kp[R_WRIST, 1] -= d
        kp[R_WRIST, 0] += d * 0.25
        kp[R_ELBOW, 1] -= d * 0.45
        kp[R_ELBOW, 0] += d * 0.12

        # 关键点检测噪声（真实姿态估计就是这个量级的抖动）
        kp += rng.normal(0, 1.2, kp.shape)

        # 置信度：大部分很高；偶尔有几帧遮挡导致不可信
        conf = rng.uniform(0.85, 0.99, 17)
        if f % 47 == 0:                      # 模拟偶发遮挡
            conf[R_WRIST] = rng.uniform(0.05, 0.30)
            conf[R_ELBOW] = rng.uniform(0.20, 0.45)

        row = {'frame': f, 'track_id': track_id}
        for k in range(17):
            row[f'x{k}'] = round(float(kp[k, 0]), 2)
            row[f'y{k}'] = round(float(kp[k, 1]), 2)
            row[f'c{k}'] = round(float(conf[k]), 4)
        rows.append(row)

    return rows


def main():
    p = argparse.ArgumentParser(description='生成合成骨架数据，用于离线验证流水线')
    p.add_argument('--session', default='demo')
    p.add_argument('--outdir', default='outputs')
    p.add_argument('--frames', type=int, default=300)
    p.add_argument('--fps', type=float, default=30.0)
    p.add_argument('--hits', type=int, default=3, help='击球次数')
    p.add_argument('--players', type=int, default=2, help='球员数量')
    p.add_argument('--seed', type=int, default=7)
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)
    session_dir = os.path.join(args.outdir, args.session)
    os.makedirs(session_dir, exist_ok=True)

    # 均匀分布击球时刻，避开开头和结尾
    margin = 40
    hit_positions = np.linspace(
        margin, args.frames - margin, args.hits,
    )
    base_hits = [int(round(x)) for x in hit_positions]

    all_rows = []
    truth = {}
    for i in range(args.players):
        track_id = 100 + i
        # 第二个球员在画面里靠右一些，击球时刻错开一点（更像真实对打）
        offset_frames = 0 if i == 0 else 7
        hits = [h + offset_frames for h in base_hits
                if 5 < h + offset_frames < args.frames - 5]
        rows = build_player(
            track_id, args.frames, hits, rng,
            dx=i * 220.0, dy=i * 10.0,
        )
        all_rows.extend(rows)
        truth[str(track_id)] = hits

    all_rows.sort(key=lambda r: (r['frame'], r['track_id']))

    fieldnames = ['frame', 'track_id']
    for k in range(17):
        fieldnames += [f'x{k}', f'y{k}', f'c{k}']

    csv_path = os.path.join(session_dir, '01_pose.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    meta = {
        'session_id': args.session,
        'video': '(合成数据，没有真实视频)',
        'model': '(合成数据)',
        'conf_threshold': 0.5,
        'imgsz': 640,
        'device': 'cpu',
        'fps': args.fps,
        'width': 1280,
        'height': 960,
        'frames_processed': args.frames,
        'frames_without_person': 0,
        'rows': len(all_rows),
        'track_ids': sorted(truth.keys()),
        'keypoints': KEYPOINT_NAMES,
        'synthetic': True,
        'ground_truth_hit_frames': truth,
        'note': '这是一份合成数据，用于离线验证流水线。'
                'ground_truth_hit_frames 是"标准答案"。',
    }
    meta_path = os.path.join(session_dir, 'meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print('=' * 68)
    print('已生成合成数据')
    print('=' * 68)
    print(f'  CSV   {csv_path}')
    print(f'  meta  {meta_path}')
    print(f'  帧数  {args.frames}  ·  球员 {args.players} 人  ·  帧率 {args.fps}')
    print()
    print('  【标准答案】每个球员的真实击球帧：')
    for tid, hits in truth.items():
        print(f'    球员 {tid}：{hits}')
    print()
    print('下一步：')
    print(f'  python 03_events_and_metrics.py --session {args.session}')
    print(f'  python 04_report.py --session {args.session}')
    print()
    print('  然后把 03 检出的 hit_frames 和上面的标准答案对一下 ——')
    print('  误差在 ±5 帧内就算正常。这就是你验证算法的基准线。')
    print('=' * 68)


if __name__ == '__main__':
    main()
