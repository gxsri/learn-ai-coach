"""
04_report.py —— 生成曲线图和一页式 HTML 报告

用法：
    python 04_report.py --session demo

产出：
    outputs/<session>/curves.png    时序曲线（速度 / 肘角 / 击球间隔）
    outputs/<session>/report.html   一页式报告（可直接用浏览器打开）

⚠️ 报告里会**主动写出局限**。这不是免责声明，是让别人相信你数据的前提。
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime
from html import escape

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


def parse_args():
    p = argparse.ArgumentParser(description='生成分析报告')
    p.add_argument('--session', required=True)
    p.add_argument('--outdir', default='outputs')
    p.add_argument('--title', default=None, help='报告标题，默认用 session 名')
    return p.parse_args()


def make_figures(df_events, df_pose, metrics, out_png):
    """画三张图。matplotlib 不在就跳过，返回 None。"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('  [提示] 没有 matplotlib，跳过曲线图（pip install matplotlib）')
        return None

    # Windows 上 matplotlib 默认字体不含中文，会显示成方框
    plt.rcParams['font.sans-serif'] = [
        'Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'DejaVu Sans',
    ]
    plt.rcParams['axes.unicode_minus'] = False

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    ax1, ax2, ax3 = axes

    colors = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd']

    # ── 图 1：手腕速度 + 击球标记 ───────────────────────────────────────────
    for i, (tid, grp) in enumerate(df_events.groupby('track_id')):
        c = colors[i % len(colors)]
        ax1.plot(grp['time_s'], grp['wrist_speed'], 'o-', color=c,
                 markersize=7, label=f'球员 {tid}')
        for _, row in grp.iterrows():
            ax1.annotate(f"#{int(row['event_index'])}",
                         (row['time_s'], row['wrist_speed']),
                         textcoords='offset points', xytext=(4, 6), fontsize=8, color=c)
    ax1.set_xlabel('时间 (秒)')
    ax1.set_ylabel('手腕速度（肩宽/秒）')
    ax1.set_title('击球时刻的手腕速度峰值 —— 每个点是一次检出的击球')
    ax1.grid(alpha=0.3)
    if len(df_events):
        ax1.legend(fontsize=9)

    # ── 图 2：肘关节投影角 ──────────────────────────────────────────────────
    for i, (tid, grp) in enumerate(df_events.groupby('track_id')):
        c = colors[i % len(colors)]
        valid = grp.dropna(subset=['elbow_angle_deg'])
        if valid.empty:
            continue
        ax2.plot(valid['time_s'], valid['elbow_angle_deg'], 'o-',
                 color=c, markersize=7, label=f'球员 {tid}')
        if len(valid) > 1:
            mean = valid['elbow_angle_deg'].mean()
            ax2.axhline(mean, color=c, linestyle='--', alpha=0.4, linewidth=1)
    ax2.set_xlabel('时间 (秒)')
    ax2.set_ylabel('肘关节角（度）')
    ax2.set_title('击球瞬间的肘关节【画面投影角】'
                  '  —  虚线为均值；不是生物力学真值')
    ax2.grid(alpha=0.3)
    if len(df_events):
        ax2.legend(fontsize=9)

    # ── 图 3：击球间隔 ──────────────────────────────────────────────────────
    # 注意：横轴是"第几次间隔"，必须是**整数刻度**。
    # 早期版本用 `np.arange(n) + i*0.35` 直接当横坐标，结果轴上出现
    # 0.00 / 0.25 / 0.50 这种没有意义的刻度 —— 条形图并排要用"整数位置 + 偏移"，
    # 而不是把偏移混进坐标值本身。
    n_players = df_events['track_id'].nunique() if len(df_events) else 0
    bar_width = 0.8 / max(n_players, 1)
    plotted = False
    max_gaps = 0

    for i, (tid, grp) in enumerate(df_events.groupby('track_id')):
        grp = grp.sort_values('frame')
        if len(grp) < 2:
            continue
        gaps = np.diff(grp['time_s'].to_numpy())
        max_gaps = max(max_gaps, len(gaps))
        c = colors[i % len(colors)]
        centers = np.arange(len(gaps)) + (i - (n_players - 1) / 2) * bar_width
        ax3.bar(centers, gaps, width=bar_width, color=c, label=f'球员 {tid}')
        plotted = True

    ax3.set_xlabel('第几次击球间隔')
    ax3.set_ylabel('距上一次击球的间隔（秒）')
    ax3.set_title('击球节奏（回合节奏的粗略代理指标）')
    ax3.grid(alpha=0.3, axis='y')
    if plotted:
        ax3.set_xticks(np.arange(max_gaps))
        ax3.set_xticklabels([str(k + 1) for k in range(max_gaps)])
        ax3.set_xlim(-0.6, max_gaps - 0.4)
        ax3.legend(fontsize=9)
    else:
        ax3.text(0.5, 0.5, '击球次数不足以计算间隔',
                 ha='center', va='center', transform=ax3.transAxes, color='gray')

    fig.suptitle(f'羽毛球动作分析 · session = {metrics.get("session_id", "")}',
                 fontsize=13)
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    return out_png


def build_html(title, session, metrics, df_events, png_path, df_pose_summary):
    def fmt(value, spec='{:.1f}'):
        """把 NaN / None 渲染成空单元格，避免报告里出现 'nan'。"""
        if value is None:
            return ''
        try:
            if pd.isna(value):
                return ''
        except (TypeError, ValueError):
            pass
        return spec.format(value)

    rows = []
    for _, r in df_events.iterrows():
        rows.append(
            '<tr>'
            f'<td>{int(r["track_id"])}</td>'
            f'<td>{int(r["event_index"])}</td>'
            f'<td>{int(r["frame"])}</td>'
            f'<td>{r["time_s"]:.2f}</td>'
            f'<td>{r["wrist_speed"]:.2f}</td>'
            f'<td>{fmt(r["elbow_angle_deg"])}</td>'
            f'<td>{fmt(r["shoulder_angle_deg"])}</td>'
            f'<td>{fmt(r["knee_angle_deg"])}</td>'
            f'<td>{r["wrist_above_shoulder"]:+.2f}</td>'
            '</tr>'
        )
    table_body = '\n'.join(rows) if rows else \
        '<tr><td colspan="9" class="empty">没有检出任何击球</td></tr>'

    player_rows = []
    for tid, m in (metrics.get('players') or {}).items():
        player_rows.append(
            '<tr>'
            f'<td>{tid}</td>'
            f'<td>{m["hits"]}</td>'
            f'<td>{m["frames"]}</td>'
            f'<td>{m["wrist_speed_max"] if m["wrist_speed_max"] is not None else "-"}</td>'
            f'<td>{m["elbow_angle_mean_deg"] if m["elbow_angle_mean_deg"] is not None else "-"}</td>'
            f'<td>{m["elbow_angle_std_deg"] if m["elbow_angle_std_deg"] is not None else "-"}</td>'
            f'<td>{m["mean_gap_seconds"] if m["mean_gap_seconds"] is not None else "-"}</td>'
            f'<td>{m["hip_lateral_range_shoulder_units"] if m["hip_lateral_range_shoulder_units"] is not None else "-"}</td>'
            '</tr>'
        )
    player_body = '\n'.join(player_rows) if player_rows else \
        '<tr><td colspan="8" class="empty">没有可汇总的球员</td></tr>'

    limits = '\n'.join(f'<li>{escape(str(x))}</li>' for x in metrics.get('limitations', []))

    img_tag = ''
    if png_path and os.path.exists(png_path):
        with open(png_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        img_tag = f'<img src="data:image/png;base64,{b64}" alt="时序曲线">'

    params = metrics.get('parameters', {})

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
         max-width: 1100px; margin: 0 auto; padding: 24px; line-height: 1.6; }}
  h1 {{ font-size: 1.6rem; border-bottom: 2px solid #8884; padding-bottom: 8px; }}
  h2 {{ font-size: 1.15rem; margin-top: 32px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; margin: 12px 0; }}
  th, td {{ border: 1px solid #8883; padding: 6px 10px; text-align: right; }}
  th {{ background: #8881; text-align: center; font-weight: 600; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .empty {{ text-align: center; color: #888; }}
  .meta {{ background: #8881; padding: 12px 16px; border-radius: 8px; font-size: 0.9rem; }}
  .meta div {{ margin: 2px 0; }}
  .limits {{ background: #ffb0001a; border-left: 4px solid #ffb000;
             padding: 12px 16px 12px 32px; border-radius: 4px; font-size: 0.9rem; }}
  img {{ max-width: 100%; border: 1px solid #8883; border-radius: 8px; }}
  code {{ background: #8881; padding: 1px 5px; border-radius: 4px; font-size: 0.88em; }}
  footer {{ margin-top: 40px; font-size: 0.82rem; color: #888; border-top: 1px solid #8883;
            padding-top: 12px; }}
</style>
</head>
<body>

<h1>{escape(title)}</h1>

<div class="meta">
  <div><b>session</b>：<code>{escape(session)}</code></div>
  <div><b>视频</b>：{escape(str(metrics.get('video') or '未记录'))}</div>
  <div><b>帧率</b>：{metrics.get('fps')}</div>
  <div><b>持拍手</b>：{escape(str(params.get('hand')))}（注意：这是球员自身的左右）</div>
  <div><b>检出击球</b>：{metrics.get('total_hits', 0)} 次</div>
  <div><b>生成时间</b>：{escape(str(metrics.get('generated_at'))) }</div>
  <div><b>参数</b>：速度阈值 {params.get('min_speed_shoulder_units_per_sec')} 肩宽/秒 ·
       最小间隔 {params.get('min_gap_frames')} 帧 ·
       置信度阈值 {params.get('conf_threshold')} ·
       SG 窗口 {params.get('savgol_window')}</div>
</div>

<h2>按球员汇总</h2>
<table>
  <thead><tr>
    <th>球员</th><th>击球次数</th><th>有效帧</th><th>速度峰值</th>
    <th>肘角均值</th><th>肘角标准差</th><th>平均间隔(秒)</th><th>髋横向幅度</th>
  </tr></thead>
  <tbody>
{player_body}
  </tbody>
</table>
<p style="font-size:0.85rem;color:#888">
  「髋横向幅度」单位是肩宽。所有角度均为<b>画面投影角</b>。
</p>

<h2>逐次击球明细</h2>
<table>
  <thead><tr>
    <th>球员</th><th>序号</th><th>帧号</th><th>时间(s)</th><th>手腕速度</th>
    <th>肘角(度)</th><th>肩角(度)</th><th>膝角(度)</th><th>腕相对肩高</th>
  </tr></thead>
  <tbody>
{table_body}
  </tbody>
</table>
<p style="font-size:0.85rem;color:#888">
  「腕相对肩高」以肩宽为单位，<b>负值表示手腕高于肩</b>（图像坐标 y 轴向下）。
</p>

<h2>时序曲线</h2>
{img_tag or '<p>（没有生成曲线图）</p>'}

<h2>本报告的局限</h2>
<div class="limits">
  <b>请连同以下内容一起阅读，否则数字会被误读：</b>
  <ul>
{limits}
  </ul>
</div>

<h2>数据溯源</h2>
<div class="meta">
  <div>骨架来源：{escape(str(metrics.get('video') or '视频'))} 经 YOLO-pose 提取，
       关键点格式 COCO-17</div>
  <div>平滑：Savitzky-Golay，窗口 {params.get('savgol_window')}，2 阶</div>
  <div>尺度归一化：肩宽（关键点 5-6 距离的中位数）</div>
  <div>中间产物：<code>01_pose.csv</code>（骨架）·
       <code>02_events.csv</code>（击球明细）·
       <code>03_metrics.json</code>（汇总与参数）</div>
</div>

<footer>
  由 learn-ai-coach starter 生成 · 这是一个分析辅助工具，不能替代教练或运动科学评估。
</footer>

</body>
</html>
"""


def main():
    args = parse_args()
    session_dir = os.path.join(args.outdir, args.session)

    events_path = os.path.join(session_dir, '02_events.csv')
    metrics_path = os.path.join(session_dir, '03_metrics.json')
    pose_path = os.path.join(session_dir, '01_pose.csv')

    for path in (events_path, metrics_path):
        if not os.path.exists(path):
            print(f'[错误] 找不到 {path}', file=sys.stderr)
            print(f'       先运行：python 03_events_and_metrics.py --session {args.session}',
                  file=sys.stderr)
            sys.exit(1)

    with open(metrics_path, encoding='utf-8') as f:
        metrics = json.load(f)

    df_events = pd.read_csv(events_path)
    df_pose = pd.read_csv(pose_path) if os.path.exists(pose_path) else pd.DataFrame()

    print('=' * 68)
    print('步骤 3/3 · 生成报告')
    print('=' * 68)
    print(f'  击球事件 {len(df_events)} 条')

    png_path = os.path.join(session_dir, 'curves.png')
    make_figures(df_events, df_pose, metrics, png_path)
    if os.path.exists(png_path):
        print(f'  曲线图   {png_path}')

    title = args.title or f'羽毛球动作分析报告 · {args.session}'
    html = build_html(title, args.session, metrics, df_events, png_path, None)
    html_path = os.path.join(session_dir, 'report.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'  报告     {html_path}')
    print()
    print('  用浏览器打开报告：')
    print(f'    start "" "{html_path}"')
    print('=' * 68)
    print()
    print('  [提醒] 报告里已经写入了局限声明。请不要把里面的角度当成')
    print('         生物力学真值，也不要把报告用于医疗或训练决策。')


if __name__ == '__main__':
    main()
