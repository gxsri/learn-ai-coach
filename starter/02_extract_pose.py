"""
02_extract_pose.py —— 视频 → 骨架坐标 CSV

这一步是整个项目的地基。**骨架跟不住人，后面全是垃圾。**

用法：
    python 02_extract_pose.py --video badminton.mp4 --session demo
    python 02_extract_pose.py --video badminton.mp4 --session demo --hand left
    python 02_extract_pose.py --video badminton.mp4 --session demo --model yolo11n-pose.pt

产出：
    outputs/<session>/01_pose.csv    每帧每人的 17 个关键点 + 置信度 + 跟踪 id
    outputs/<session>/meta.json      视频信息与本次运行的参数

跑完请务必检查：
    * 跟踪 id 是不是有跳变（id 数量远多于画面人数 = 跟踪一直在断）
    * 把 CSV 里的点画到视频上，火柴人跟得住人吗
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from env_hint import explain_missing

try:
    from common import DEFAULT_CONF_THRESHOLD, KEYPOINT_NAMES, KP, SKELETON_EDGES
except ImportError:
    explain_missing('numpy', __file__)
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description='从视频提取人体骨架，保存为 CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--video', required=True, help='输入视频路径')
    parser.add_argument('--session', required=True,
                        help='本次分析的标识（英文数字），用于 outputs/<session>/ 目录和后续数据划分')
    parser.add_argument('--model', default='yolo26n-pose.pt',
                        help='YOLO 姿态模型权重（默认 yolo26n-pose.pt；资料不够时可换 yolo11n-pose.pt）')
    parser.add_argument('--conf', type=float, default=0.3,
                        help='检测置信度阈值（默认 0.3，越低越容易检测到但误检更多）')
    parser.add_argument('--imgsz', type=int, default=640,
                        help='推理分辨率（默认 640；显存不够就降到 480）')
    parser.add_argument('--device', default=None,
                        help='设备：0 = 第一块 GPU，cpu = 强制 CPU。不填则自动选择')
    parser.add_argument('--outdir', default='outputs', help='输出根目录')
    parser.add_argument('--overlay', action='store_true',
                        help='额外输出一段带骨架叠加的视频 overlay.mp4。'
                             '⚠️ 强烈建议加：报告里的数字看不出跟踪准不准，'
                             '必须用肉眼在视频上确认。')
    return parser.parse_args()


def draw_people(canvas, xy, conf, ids, conf_threshold):
    """
    把骨架画到画面上。**这是检查跟踪质量唯一可靠的方法。**

    设计上的三个刻意选择：
      · 高置信度的点画实心圆、连线画绿色；低于阈值的点画红色叉 ——
        一眼就能看出"骨架断了"是因为真的遮挡，还是因为检测失败。
      · id 用 ASCII 文字画在髋部旁边（OpenCV 的 Hershey 字体不支持中文）。
      · 没有 id 的框标成 `id=?`，让你直接看到"跟踪器没认出来"的那些人。
    """
    import cv2
    import numpy as np

    for person in range(xy.shape[0]):
        track_id = int(ids[person]) if ids is not None else -1
        points = xy[person]
        scores = conf[person] if conf is not None else np.ones(len(points))

        # 连线：两端都可信才画，避免把噪声连成看着很合理的骨架
        for a, b in SKELETON_EDGES:
            if scores[a] < conf_threshold or scores[b] < conf_threshold:
                continue
            pa = (int(points[a][0]), int(points[a][1]))
            pb = (int(points[b][0]), int(points[b][1]))
            cv2.line(canvas, pa, pb, (0, 200, 0), 2, cv2.LINE_AA)

        # 关键点：可信的画实心点，不可信的画红叉（看得见才敢忽略它）
        for k in range(len(points)):
            x, y = int(points[k][0]), int(points[k][1])
            if scores[k] >= conf_threshold:
                cv2.circle(canvas, (x, y), 4, (0, 140, 255), -1, cv2.LINE_AA)
            else:
                cv2.drawMarker(canvas, (x, y), (0, 0, 255),
                               cv2.MARKER_TILTED_CROSS, 12, 2)

        # id 标签画在髋部旁边，带黑色描边，保证任何背景下都看得清
        hip_x = int((points[KP['left_hip']][0] + points[KP['right_hip']][0]) / 2)
        hip_y = int((points[KP['left_hip']][1] + points[KP['right_hip']][1]) / 2)
        label = f'id={track_id}' if track_id >= 0 else 'id=?'
        origin = (hip_x - 30, max(20, hip_y))
        cv2.putText(canvas, label, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(canvas, label, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 255), 1, cv2.LINE_AA)

    return canvas


def fail(message, hint=None):
    print(f'\n[错误] {message}', file=sys.stderr)
    if hint:
        print(f'       {hint}', file=sys.stderr)
    sys.exit(1)


def main():
    args = parse_args()

    # ── 检查依赖 ────────────────────────────────────────────────────────────
    try:
        from ultralytics import YOLO
    except ImportError:
        explain_missing('ultralytics', __file__)
        sys.exit(1)

    import torch

    if not os.path.exists(args.video):
        fail(f'找不到视频文件：{args.video}',
             '路径请用绝对路径试一次，比如 D:\\videos\\test.mp4')

    # ── 输出目录 ────────────────────────────────────────────────────────────
    session_dir = os.path.join(args.outdir, args.session)
    os.makedirs(session_dir, exist_ok=True)
    csv_path = os.path.join(session_dir, '01_pose.csv')
    meta_path = os.path.join(session_dir, 'meta.json')

    device = args.device
    if device is None:
        device = '0' if torch.cuda.is_available() else 'cpu'

    # 读视频元信息。fps 一定要记下来 —— 后面所有"速度"类指标都依赖它。
    fps, width, height = None, None, None
    try:
        import cv2
        cap = cv2.VideoCapture(args.video)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        if not fps or fps <= 0:
            fps = None
    except Exception as error:
        print(f'  [提示] 读取视频信息失败（{error}），后面需要手工指定 --fps')

    print('=' * 68)
    print('步骤 1/3 · 从视频提取骨架')
    print('=' * 68)
    print(f'  视频      {args.video}')
    print(f'  session   {args.session}')
    print(f'  模型      {args.model}')
    print(f'  帧率      {fps if fps else "读取失败，03 步骤请手工传 --fps"}' + (f'  ·  {width}x{height}' if width else ''))
    print(f'  设备      {device}'
          + (f'（{torch.cuda.get_device_name(0)}）' if device != 'cpu' and torch.cuda.is_available() else ''))
    print(f'  输出      {csv_path}')
    print()

    # ── 加载模型 ────────────────────────────────────────────────────────────
    print('  加载模型（首次运行会自动下载权重，需要联网）...')
    try:
        model = YOLO(args.model)
    except Exception as error:
        fail(f'加载模型失败：{error}',
             '常见原因：权重名写错、网络不通导致下载失败。\n'
             '       可以换 yolo11n-pose.pt 试试，或者手动下载权重放到当前目录。')

    # stream=True：逐帧返回，不会把整个视频加载进内存
    try:
        results = model.track(
            source=args.video,
            persist=True,
            stream=True,
            conf=args.conf,
            imgsz=args.imgsz,
            device=device,
            verbose=False,
        )
    except Exception as error:
        fail(f'启动跟踪失败：{error}',
             '报 CUDA out of memory 就降 imgsz（640 → 480）或换更小的模型（s → n）')

    # ── 逐帧收集 ────────────────────────────────────────────────────────────
    fieldnames = ['frame', 'track_id']
    for i in range(17):
        fieldnames += [f'x{i}', f'y{i}', f'c{i}']

    rows = []
    started = time.time()
    n_frames = 0
    n_no_person = 0
    n_untracked = 0          # 检测到人、但跟踪器没给它分配 id 的框数量

    # 骨架叠加视频（用于肉眼检查跟踪质量）。
    # 注意变量名是 video_writer —— 下面写 CSV 时用到的 `writer` 是另一个东西。
    overlay_path = os.path.join(session_dir, 'overlay.mp4') if args.overlay else None
    video_writer = None

    print('  开始处理...')
    try:
        for frame_idx, r in enumerate(results):
            n_frames += 1
            if n_frames % 100 == 0:
                elapsed = time.time() - started
                print(f'    已处理 {n_frames} 帧，'
                      f'耗时 {elapsed:.0f}s，'
                      f'{"%.1f" % (n_frames / elapsed)} 帧/秒', end='\r')

            # 先取出这一帧的结果；没有检测到人也要继续（叠加视频需要每一帧）
            xy = conf = ids = None
            if r.keypoints is not None and r.keypoints.xy is not None:
                xy = r.keypoints.xy.cpu().numpy()            # [人数, 17, 2]
                c = r.keypoints.conf
                conf = c.cpu().numpy() if c is not None else None   # [人数, 17]
                raw_ids = getattr(r.boxes, 'id', None)
                ids = raw_ids.cpu().numpy() if raw_ids is not None else None

            if xy is None or xy.shape[0] == 0:
                n_no_person += 1
            else:
                for p in range(xy.shape[0]):
                    # ⚠️ 跟踪器不保证给每个检测框都分配 id：新出现的人、置信度边缘的框、
                    #    被遮挡后重新出现的框都会没有 id。这里用 -1 作哨兵值。
                    #    **-1 不是"一个球员"** —— 它是"一堆身份不明的人"的集合，
                    #    绝不能把它们的坐标串成一条时间序列去算速度，那会产生完全虚假的峰值。
                    #    下游的 03_events_and_metrics.py 默认会跳过它们。
                    track_id = int(ids[p]) if ids is not None else -1
                    if track_id < 0:
                        n_untracked += 1

                    row = {'frame': frame_idx, 'track_id': track_id}
                    for k in range(17):
                        row[f'x{k}'] = float(xy[p, k, 0])
                        row[f'y{k}'] = float(xy[p, k, 1])
                        row[f'c{k}'] = float(conf[p, k]) if conf is not None else float('nan')
                    rows.append(row)

            # ── 画叠加视频（每一帧都写，包括没检测到人的帧）────────────────────
            if overlay_path is not None:
                canvas = getattr(r, 'orig_img', None)
                if canvas is not None:
                    if video_writer is None:
                        import cv2
                        h, w = canvas.shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        video_writer = cv2.VideoWriter(
                            overlay_path, fourcc, float(fps or 25.0), (w, h))
                    canvas = canvas.copy()
                    if xy is not None and xy.shape[0] > 0:
                        # 用 0.5 作为画图阈值 —— 和 03 步骤默认的可信阈值一致，
                        # 所以你在视频里看到"红叉"，就是 03 会丢掉的那些点。
                        draw_people(canvas, xy, conf, ids, DEFAULT_CONF_THRESHOLD)
                    video_writer.write(canvas)
    except KeyboardInterrupt:
        print('\n  用户中断，保存已处理的部分...')

    if video_writer is not None:
        video_writer.release()

    print()
    elapsed = time.time() - started

    if not rows:
        fail('一个人都没检测到',
             '按顺序排查：\n'
             '        1. 换一张官方示例图试一次 —— 如果也不行，是环境问题\n'
             '        2. 视频里人是不是太小 / 太黑 / 只有一部分在画面里\n'
             '        3. 把 --conf 降到 0.15 再试\n'
             '        4. 用 --imgsz 960 提高分辨率再试')

    # ── 写 CSV ──────────────────────────────────────────────────────────────
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ── 写 meta.json ────────────────────────────────────────────────────────
    track_ids = sorted({row['track_id'] for row in rows})
    real_track_ids = [t for t in track_ids if t >= 0]
    meta = {
        'session_id': args.session,
        'video': os.path.abspath(args.video),
        'model': args.model,
        'conf_threshold': args.conf,
        'imgsz': args.imgsz,
        'device': str(device),
        'fps': fps,
        'width': width,
        'height': height,
        'frames_processed': n_frames,
        'frames_without_person': n_no_person,
        'rows': len(rows),
        'untracked_rows': n_untracked,
        'track_ids': real_track_ids,
        'keypoints': KEYPOINT_NAMES,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ── 汇总 + 体检 ─────────────────────────────────────────────────────────
    print('=' * 68)
    print(f'完成。共 {len(rows)} 条记录，来自 {n_frames} 帧，耗时 {elapsed:.1f}s')
    print(f'  CSV   {csv_path}')
    print(f'  meta  {meta_path}')
    if overlay_path and os.path.exists(overlay_path):
        size_mb = os.path.getsize(overlay_path) / (1024 * 1024)
        print(f'  叠加视频 {overlay_path}  ({size_mb:.1f} MB)')
        print('          → 用播放器打开它，肉眼确认骨架跟不跟得住人。')
        print('            绿色连线=可信，红色叉=置信度低于 0.5（03 会丢掉这些点），')
        print('            id=? 表示跟踪器没给这个人分配 id。')
    elif args.overlay:
        print('  [警告] --overlay 指定了但没写出视频，可能是这一版模型不返回原图')
    print()

    # ── 跟踪稳定性体检 —— 这是最关键的一步，不要跳过 ───────────────────────
    # 一次遍历算完每个 id 的帧范围和计数（比反复过滤整个列表快得多）
    stats = {}
    for row in rows:
        tid = row['track_id']
        entry = stats.get(tid)
        if entry is None:
            stats[tid] = [1, row['frame'], row['frame']]
        else:
            entry[0] += 1
            if row['frame'] < entry[1]:
                entry[1] = row['frame']
            if row['frame'] > entry[2]:
                entry[2] = row['frame']

    real = sorted((t for t in stats if t >= 0), key=lambda t: -stats[t][0])

    print('跟踪稳定性体检：')
    print(f'  有 id 的 track 共 {len(real)} 个')
    for tid in real[:8]:
        cnt, fmin, fmax = stats[tid]
        print(f'    id={tid:>4}  出现 {cnt:>6} 次   帧范围 {fmin} - {fmax}')
    if len(real) > 8:
        print(f'    ... 还有 {len(real) - 8} 个 id')

    print()
    problems = []

    # ★ 没有 id 的检测框：它们**不是**同一个球员，混在一起会算出差到离谱的速度
    share = n_untracked / len(rows) if rows else 0.0
    if n_untracked:
        print(f'  [注意] 有 {n_untracked} 行没有 track_id（占 {share:.1%}），已标记为 -1。')
        print('         这些是跟踪器没能匹配上的检测框（新人入场、被遮挡后重现、')
        print('         置信度边缘的框）。它们身份不明，**不能当成同一个球员**。')
        print('         03 步骤默认会跳过它们（要强制算就加 --include-untracked）。')
        if share > 0.05:
            problems.append(f'无 id 的框占 {share:.1%}，偏高')
            print('         比例偏高。可以试：提高 --conf 减少边缘框、换 tracker、')
            print('         或改善拍摄质量减少遮挡。')
    else:
        print('  [OK] 每个检测框都拿到了 track_id。')

    # 有 id 的 track 数量异常多 → 跟踪一直在断
    if len(real) > 10 and len(real) > 0.05 * n_frames:
        problems.append(f'有 id 的 track 多达 {len(real)} 个，跟踪一直在断')
        print(f'  [警告] 有 id 的 track 多达 {len(real)} 个 —— 跟踪很可能一直在断。')
        print('         这会毁掉后面所有跨帧指标，请先解决：')
        print('         · 提高拍摄快门（1/1000s 以上），减少运动模糊')
        print('         · 换跟踪器：model.track(..., tracker="botsort.yaml")')
        print('         · 画面里人太多的话，先把视频裁剪到球场区域')
    elif real:
        print(f'  [OK] track 数量看起来正常（{len(real)} 个）。')

    if problems:
        print()
        print('  本步发现 ' + str(len(problems)) + ' 个问题：')
        for p in problems:
            print(f'    · {p}')
    else:
        print('  [OK] 本步没有发现明显问题。')

    print('=' * 68)
    print('\n下一步：python 03_events_and_metrics.py --session ' + args.session)


if __name__ == '__main__':
    main()
