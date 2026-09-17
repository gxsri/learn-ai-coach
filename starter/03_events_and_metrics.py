"""
03_events_and_metrics.py —— 骨架 CSV → 击球事件 + 指标

用法：
    python 03_events_and_metrics.py --session demo
    python 03_events_and_metrics.py --session demo --hand left --min-speed 4.0

产出：
    outputs/<session>/02_events.csv    每次击球一行的指标表
    outputs/<session>/03_metrics.json  按球员汇总 + 局限声明

⚠️ 所有角度都是【画面投影角】，不是生物力学意义上的关节真值。
   单目 2D 存在系统性低估。报告里必须标注，且只做同机位的纵向对比。
   详见 part2-YOLO与骨架/04-羽毛球运动表现分析实战.md
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from env_hint import explain_missing

try:
    import numpy as np
except ImportError:
    explain_missing('numpy', __file__)
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    explain_missing('pandas', __file__)
    sys.exit(1)

from common import (
    DEFAULT_CONF_THRESHOLD,
    DEFAULT_MIN_ANGLE_DELTA,
    DEFAULT_MIN_GAP_FRAMES,
    DEFAULT_MIN_SPEED,
    DEFAULT_POLYORDER,
    DEFAULT_WINDOW,
    KP,
    angle_at,
    body_scale,
    detect_hit_events,
    wrist_speed,
)


def num(value, digits=3):
    """
    把 numpy 标量 / NaN / inf 变成可以安全写进 JSON 的值。

    不处理的话，json.dump 会把 NaN 写成裸的 `NaN`（这不是合法 JSON，
    别的语言读不了），报告里也会出现 'nan' 这种难看的字眼。
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, digits)


def parse_args():
    p = argparse.ArgumentParser(description='从骨架 CSV 算击球事件与指标')
    p.add_argument('--session', required=True)
    p.add_argument('--outdir', default='outputs')
    p.add_argument('--hand', choices=['right', 'left'], default='right',
                   help='持拍手。注意：这是球员自己的左右，背对镜头时容易搞反')
    p.add_argument('--fps', type=float, default=None,
                   help='视频帧率。不填则从 meta.json 读')
    p.add_argument('--min-speed', type=float, default=DEFAULT_MIN_SPEED,
                   help=f'击球的手腕速度下限（单位：肩宽/秒，默认 {DEFAULT_MIN_SPEED}）')
    p.add_argument('--min-gap', type=int, default=DEFAULT_MIN_GAP_FRAMES,
                   help=f'两次击球的最小间隔帧数（默认 {DEFAULT_MIN_GAP_FRAMES}）')
    p.add_argument('--conf', type=float, default=DEFAULT_CONF_THRESHOLD,
                   help=f'关键点置信度阈值（默认 {DEFAULT_CONF_THRESHOLD}）')
    p.add_argument('--window', type=int, default=DEFAULT_WINDOW,
                   help=f'Savitzky-Golay 窗口（默认 {DEFAULT_WINDOW}）')
    p.add_argument('--min-track-frames', type=int, default=50,
                   help='少于这么多帧的 track 会被跳过（那是跟踪碎片，不是球员）')
    p.add_argument('--include-untracked', action='store_true',
                   help='把没有 track_id 的检测框也当序列算。⚠️ 默认关闭：'
                        '那些框身份不明，串成一条时间序列会产生完全虚假的速度峰值')
    return p.parse_args()


def main():
    args = parse_args()
    session_dir = os.path.join(args.outdir, args.session)
    csv_path = os.path.join(session_dir, '01_pose.csv')
    meta_path = os.path.join(session_dir, 'meta.json')

    if not os.path.exists(csv_path):
        print(f'[错误] 找不到 {csv_path}', file=sys.stderr)
        print('       先运行：python 02_extract_pose.py --video 视频.mp4 '
              f'--session {args.session}', file=sys.stderr)
        sys.exit(1)

    fps = args.fps
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
        if fps is None:
            fps = meta.get('fps')
    if not fps or fps <= 0:
        fps = 30.0
        print(f'[提示] 没能确定帧率，按 {fps} 处理。'
              f'速度类指标会因此有偏差，建议传 --fps 明确指定。')

    print('=' * 68)
    print('步骤 2/3 · 击球事件检测与指标计算')
    print('=' * 68)
    print(f'  帧率        {fps}')
    print(f'  持拍手      {args.hand}')
    print(f'  速度阈值    {args.min_speed} 肩宽/秒')
    print(f'  最小间隔    {args.min_gap} 帧')
    print()

    df = pd.read_csv(csv_path)
    print(f'  读入 {len(df)} 行，{df["track_id"].nunique()} 个 track_id')

    # ★ 没有 track_id 的检测框（02 里标记为 -1）默认必须剔除。
    #   它们不是"一个球员"，而是"一堆身份不明的人"。
    #   如果不剔，不同人的坐标会被串成一条时间序列，
    #   逐帧差分时就会算出几百肩宽/秒这种离谱的假速度，然后被当成"击球"。
    #   —— 这不是假想的风险，是本教程实机跑真实视频时**真实发生过**的 bug。
    n_untracked = int((df['track_id'] < 0).sum())
    if n_untracked:
        if args.include_untracked:
            print(f'  [警告] 有 {n_untracked} 行没有 track_id，但你指定了 --include-untracked。')
            print('         这些行会被当成一个序列，结果很可能包含虚假的击球。')
        else:
            print(f'  跳过 {n_untracked} 行没有 track_id 的检测（身份不明，不能当同一人）')
            df = df[df['track_id'] >= 0].copy()
            print(f'  剩余 {len(df)} 行，{df["track_id"].nunique() if len(df) else 0} 个 track_id')
    if df.empty:
        print()
        print('[错误] 剔除后没有可用的数据了。', file=sys.stderr)
        print('       说明这个视频里没有任何一个球员被稳定跟踪。', file=sys.stderr)
        print('       回到 02 步骤的体检输出，先解决跟踪不稳定问题。', file=sys.stderr)
        sys.exit(1)

    # 持拍侧的四个关键点索引
    if args.hand == 'right':
        idx_shoulder, idx_elbow, idx_wrist = KP['right_shoulder'], KP['right_elbow'], KP['right_wrist']
    else:
        idx_shoulder, idx_elbow, idx_wrist = KP['left_shoulder'], KP['left_elbow'], KP['left_wrist']
    idx_hip_l, idx_hip_r = KP['left_hip'], KP['right_hip']
    idx_knee = KP['right_knee'] if args.hand == 'right' else KP['left_knee']
    idx_ankle = KP['right_ankle'] if args.hand == 'right' else KP['left_ankle']

    event_rows = []
    metrics = {}

    for track_id, person in df.groupby('track_id'):
        person = person.sort_values('frame')
        if len(person) < args.min_track_frames:
            print(f'  跳过 track {track_id}：只有 {len(person)} 帧（少于 {args.min_track_frames}）')
            continue

        frames = person['frame'].to_numpy()

        # ── 尺度基准：用肩宽中位数。**不要用检测框的宽高** ──────────────────
        sw = np.array([
            body_scale(r[f'x{KP["left_shoulder"]}'], r[f'y{KP["left_shoulder"]}'],
                       r[f'x{KP["right_shoulder"]}'], r[f'y{KP["right_shoulder"]}'])
            for _, r in person.iterrows()
        ])
        sw_valid = sw[np.isfinite(sw) & (sw > 1e-3)]
        if sw_valid.size == 0:
            print(f'  跳过 track {track_id}：算不出肩宽')
            continue
        scale = float(np.median(sw_valid))

        # ── 手腕速度 ────────────────────────────────────────────────────────
        wx = person[f'x{idx_wrist}'].to_numpy(dtype=float)
        wy = person[f'y{idx_wrist}'].to_numpy(dtype=float)
        wc = person[f'c{idx_wrist}'].to_numpy(dtype=float)

        try:
            speed, _, _ = wrist_speed(wx, wy, scale, fps,
                                      window=args.window, polyorder=DEFAULT_POLYORDER,
                                      conf=wc, conf_threshold=args.conf)
        except ValueError as error:
            print(f'  跳过 track {track_id}：{error}')
            continue

        # ── 击球检测 ────────────────────────────────────────────────────────
        events = detect_hit_events(frames, speed,
                                   min_gap_frames=args.min_gap,
                                   min_speed=args.min_speed)
        print(f'  track {track_id}：{len(person)} 帧，肩宽 {scale:.1f}px，'
              f'速度峰值 {np.nanmax(speed):.2f} 肩宽/秒，检出 {len(events)} 次击球')

        person_by_frame = person.set_index('frame')

        for i, ev in enumerate(events):
            f_no = ev['frame']
            if f_no not in person_by_frame.index:
                continue
            row = person_by_frame.loc[f_no]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]

            # 断言：这一步算出来的都是【画面投影角】
            elbow = angle_at(
                (row[f'x{idx_elbow}'], row[f'y{idx_elbow}']),
                (row[f'x{idx_shoulder}'], row[f'y{idx_shoulder}']),
                (row[f'x{idx_wrist}'], row[f'y{idx_wrist}']),
            )
            shoulder = angle_at(
                (row[f'x{idx_elbow}'], row[f'y{idx_elbow}']),
                (row[f'x{idx_shoulder}'], row[f'y{idx_shoulder}']),
                (row[f'x{idx_hip_l}'], row[f'y{idx_hip_l}']),
            )
            knee = angle_at(
                (row[f'x{idx_hip_l}'], row[f'y{idx_hip_l}']),
                (row[f'x{idx_knee}'], row[f'y{idx_knee}']),
                (row[f'x{idx_ankle}'], row[f'y{idx_ankle}']),
            )

            # 手腕相对肩的高度（单位：肩宽）。图像坐标 y 向下 → 越小越高，
            # 所以"手腕高于肩"时这个值是负数。
            wrist_above_shoulder = (row[f'y{idx_wrist}'] - row[f'y{idx_shoulder}']) / scale

            hip_x = (row[f'x{idx_hip_l}'] + row[f'x{idx_hip_r}']) / 2.0
            hip_y = (row[f'y{idx_hip_l}'] + row[f'y{idx_hip_r}']) / 2.0

            event_rows.append({
                'session_id': args.session,          # ★ 数据划分的关键字段
                'track_id': int(track_id),
                'event_index': i + 1,
                'frame': int(f_no),
                'time_s': round(float(f_no) / fps, 3),
                'wrist_speed': round(float(ev['speed']), 3),
                'elbow_angle_deg': None if np.isnan(elbow) else round(elbow, 1),
                'shoulder_angle_deg': None if np.isnan(shoulder) else round(shoulder, 1),
                'knee_angle_deg': None if np.isnan(knee) else round(knee, 1),
                'wrist_above_shoulder': round(float(wrist_above_shoulder), 3),
                'hip_center_x': round(float(hip_x), 1),
                'hip_center_y': round(float(hip_y), 1),
                'hand': args.hand,
            })

        # ── 按球员汇总 ──────────────────────────────────────────────────────
        speeds = [e['speed'] for e in events]
        gaps = np.diff([e['frame'] for e in events]) if len(events) > 1 else np.array([])
        hip_xs = ((person[f'x{idx_hip_l}'] + person[f'x{idx_hip_r}']) / 2).to_numpy(dtype=float)
        hip_ys = ((person[f'y{idx_hip_l}'] + person[f'y{idx_hip_r}']) / 2).to_numpy(dtype=float)
        hip_range = float(np.nanmax(hip_xs) - np.nanmin(hip_xs)) / scale if scale else None

        angles = [r['elbow_angle_deg'] for r in event_rows
                  if r['track_id'] == int(track_id) and r['elbow_angle_deg'] is not None]

        metrics[str(int(track_id))] = {
            'frames': int(len(person)),
            'shoulder_width_px': num(scale, 1),
            'hits': len(events),
            'hit_frames': [e['frame'] for e in events],
            'wrist_speed_max': num(np.nanmax(speeds) if speeds else None),
            'wrist_speed_mean': num(np.nanmean(speeds) if speeds else None),
            'elbow_angle_mean_deg': num(np.nanmean(angles) if angles else None, 1),
            'elbow_angle_std_deg': num(np.nanstd(angles) if angles else None, 1),
            'elbow_angle_min_deg': num(np.nanmin(angles) if angles else None, 1),
            'elbow_angle_max_deg': num(np.nanmax(angles) if angles else None, 1),
            'mean_gap_frames': num(np.mean(gaps) if gaps.size else None, 1),
            'mean_gap_seconds': num(np.mean(gaps) / fps if gaps.size else None, 2),
            'hip_lateral_range_shoulder_units': num(hip_range, 2),
        }

    # ── 写文件 ──────────────────────────────────────────────────────────────
    events_path = os.path.join(session_dir, '02_events.csv')
    if event_rows:
        pd.DataFrame(event_rows).to_csv(events_path, index=False, encoding='utf-8')
    else:
        # 仍然写一个只有表头的文件，避免后面的步骤找不到文件
        pd.DataFrame(columns=[
            'session_id', 'track_id', 'event_index', 'frame', 'time_s', 'wrist_speed',
            'elbow_angle_deg', 'shoulder_angle_deg', 'knee_angle_deg',
            'wrist_above_shoulder', 'hip_center_x', 'hip_center_y', 'hand',
        ]).to_csv(events_path, index=False, encoding='utf-8')

    summary = {
        'session_id': args.session,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'video': meta.get('video'),
        'fps': fps,
        'parameters': {
            'hand': args.hand,
            'min_speed_shoulder_units_per_sec': args.min_speed,
            'min_gap_frames': args.min_gap,
            'conf_threshold': args.conf,
            'savgol_window': args.window,
        },
        'total_hits': len(event_rows),
        'untracked_rows_skipped': (0 if args.include_untracked else n_untracked),
        'players': metrics,
        # ★ 把局限写进数据文件本身，而不是只写在文档里
        'limitations': [
            '所有关节角均为【画面投影角】，不是生物力学真值。'
            '单目 2D 存在系统性低估（文献对照：髋约 -11.2 度、膝约 -10.6 度）。',
            '只应做同一机位、同一球员的纵向对比，不要跨机位或跨设备比较。',
            '角度差异小于 '
            f'{DEFAULT_MIN_ANGLE_DELTA} 度时不应下结论。',
            '击球时刻由手腕速度峰值推断，遮挡或运动模糊严重时会漏检/误检。',
            '所有位移量以肩宽为单位；要换成米必须先做场地标定（单应变换）。',
            '若 --fps 不是视频真实帧率，所有速度类指标都会成比例偏移。',
        ],
    }
    metrics_path = os.path.join(session_dir, '03_metrics.json')
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # ── 打印汇总 ────────────────────────────────────────────────────────────
    print()
    print('=' * 68)
    print(f'完成。共检出 {" " if event_rows else "0 "}{len(event_rows)} 次击球')
    print(f'  事件表  {events_path}')
    print(f'  指标    {metrics_path}')
    print()

    if not event_rows:
        print('  没有检出任何击球。按顺序排查：')
        print('    1. 把速度曲线画出来看看峰值有多大（见 04_report.py 的曲线图）')
        print('    2. 阈值定太高了？试试 --min-speed 2.0')
        print('    3. 持拍手搞反了？试试 --hand left')
        print('    4. 置信度过滤太严？试试 --conf 0.3')
    else:
        for tid, m in metrics.items():
            print(f'  球员 {tid}: {m["hits"]} 次击球，'
                  f'速度峰值 {m["wrist_speed_max"]} 肩宽/秒，'
                  f'肘角均值 {m["elbow_angle_mean_deg"]} 度'
                  + (f'，平均间隔 {m["mean_gap_seconds"]} 秒' if m['mean_gap_seconds'] else ''))

    print()
    print('  [提醒] 以上角度全部是【画面投影角】，报告里必须标注。')
    print('=' * 68)
    print('\n下一步：python 04_report.py --session ' + args.session)


if __name__ == '__main__':
    main()
