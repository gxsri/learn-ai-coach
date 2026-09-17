"""
01_check_env.py —— 环境自检。**只用标准库**，所以任何情况下都能跑。

先跑这个，再跑别的。它会告诉你：缺什么、怎么装、装完怎么验证。

    python 01_check_env.py
"""

import importlib.util
import os
import platform
import shutil
import subprocess
import sys

# Windows 控制台编码兜底
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

OK = '[OK]  '
MISS = '[MISS]'
WARN = '[WARN]'

problems = []


def line(status, text):
    print(f'  {status} {text}')


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def module_version(name):
    try:
        mod = __import__(name)
        return getattr(mod, '__version__', '未知版本')
    except Exception as error:
        return f'导入失败：{error}'


print('=' * 68)
print('羽毛球动作分析 · 环境自检')
print('=' * 68)

# ── 1. Python ────────────────────────────────────────────────────────────────
print('\n[1] Python')
print(f'     版本：{platform.python_version()}')
print(f'     解释器：{sys.executable}')
print(f'     虚拟环境：{"是" if sys.prefix != sys.base_prefix else "否（用的是系统 Python）"}')

if sys.version_info < (3, 9):
    problems.append('Python 版本过低，建议 3.10 - 3.12')
    line(WARN, 'Python 版本低于 3.9，很多库装不上')
else:
    line(OK, f'Python {platform.python_version()}')

if sys.prefix == sys.base_prefix:
    line(WARN, '没有在虚拟环境里。强烈建议先建一个（见 setup.ps1）')
else:
    line(OK, '在虚拟环境中')

# ── 2. Python 包 ─────────────────────────────────────────────────────────────
print('\n[2] Python 包')

PACKAGES = [
    ('numpy',      'numpy',       'pip install numpy',                True),
    ('cv2',        'opencv-python', 'pip install opencv-python',      True),
    ('pandas',     'pandas',      'pip install pandas',               False),
    ('matplotlib', 'matplotlib',  'pip install matplotlib',           False),
    ('torch',      'torch',       'pip install torch torchvision --index-url '
                                  'https://download.pytorch.org/whl/cu128', True),
    ('ultralytics', 'ultralytics', 'pip install ultralytics',         True),
]

for module_name, pip_name, install_cmd, required in PACKAGES:
    if has_module(module_name):
        line(OK, f'{pip_name:18s} {module_version(module_name)}')
    else:
        line(MISS, f'{pip_name:18s} 未安装  →  {install_cmd}')
        if required:
            problems.append(f'缺少 {pip_name}，运行：{install_cmd}')

# ── 3. GPU / CUDA ────────────────────────────────────────────────────────────
print('\n[3] 显卡')

if has_module('torch'):
    try:
        import torch
        if torch.cuda.is_available():
            line(OK, f'CUDA 可用：{torch.cuda.get_device_name(0)}')
            total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            line(OK, f'显存：{total:.1f} GB   ·   CUDA 版本：{torch.version.cuda}')
            if total < 6:
                line(WARN, '显存较小，训练时把 batch 调到 2-4，imgsz 用 640')
        else:
            line(WARN, 'CUDA 不可用 —— 装成 CPU 版 PyTorch 了')
            print('         修复：pip uninstall torch torchvision -y')
            print('               pip install torch torchvision --index-url '
                  'https://download.pytorch.org/whl/cu128')
            problems.append('PyTorch 是 CPU 版，推理会非常慢')
    except Exception as error:
        line(WARN, f'检查 CUDA 时出错：{error}')
else:
    line(MISS, 'PyTorch 未安装，无法检查显卡')

# nvidia-smi 是独立于 PyTorch 的旁证
smi = shutil.which('nvidia-smi')
if smi:
    try:
        out = subprocess.run(
            [smi, '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        line(OK, f'nvidia-smi 报告：{out}')
    except Exception as error:
        line(WARN, f'nvidia-smi 调用失败：{error}')
else:
    line(WARN, 'PATH 里没有 nvidia-smi（如果不是 N 卡就正常）')

# ── 4. 外部工具 ──────────────────────────────────────────────────────────────
print('\n[4] 外部工具')

if shutil.which('ffmpeg'):
    try:
        out = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True,
                             timeout=20).stdout.splitlines()[0]
        line(OK, f'ffmpeg 可用：{out[:70]}')
    except Exception:
        line(OK, 'ffmpeg 可用')
else:
    line(MISS, 'ffmpeg 未安装（抽帧要用）')
    print('         安装：winget install --id Gyan.FFmpeg -e')
    print('         装完重开一个终端，再跑一次本脚本')
    problems.append('缺少 ffmpeg，无法从视频抽帧做标注')

# ── 5. 目录结构 ──────────────────────────────────────────────────────────────
print('\n[5] 项目目录')

here = os.path.dirname(os.path.abspath(__file__))
for name in ['common.py', 'selftest.py', '02_extract_pose.py',
             '03_events_and_metrics.py', '04_report.py']:
    path = os.path.join(here, name)
    line(OK if os.path.exists(path) else MISS, f'{name}')

outputs = os.path.join(here, 'outputs')
print(f'         outputs 目录：{outputs} '
      f'({"已存在" if os.path.isdir(outputs) else "还没有（第一次运行会自动创建）"})')

# ── 6. 算法自检 ──────────────────────────────────────────────────────────────
print('\n[6] 算法自检（不需要显卡）')

if has_module('numpy'):
    selftest = os.path.join(here, 'selftest.py')
    if os.path.exists(selftest):
        try:
            result = subprocess.run([sys.executable, selftest], cwd=here,
                                    capture_output=True, text=True, timeout=180)
            tail = [ln for ln in result.stdout.splitlines() if '通过' in ln]
            if result.returncode == 0:
                line(OK, f'selftest 通过（{tail[-1] if tail else "全部通过"}）')
            else:
                line(WARN, 'selftest 有失败项，运行 python selftest.py 看详情')
                problems.append('算法自检未通过')
        except Exception as error:
            line(WARN, f'运行 selftest 出错：{error}')
    else:
        line(MISS, '找不到 selftest.py')
else:
    line(MISS, 'numpy 未安装，跳过')

# ── 汇总 ─────────────────────────────────────────────────────────────────────
print('\n' + '=' * 68)
if not problems:
    print('[OK] 环境完全就绪。')
    print('\n下一步：')
    print('  1. python 02_extract_pose.py --video 你的视频.mp4 --session demo')
    print('  2. python 03_events_and_metrics.py --session demo')
    print('  3. python 04_report.py --session demo')
else:
    print(f'发现 {len(problems)} 个问题，按顺序解决：')
    for i, p in enumerate(problems, 1):
        print(f'  {i}. {p}')
    print('\n解决后重新运行：python 01_check_env.py')
print('=' * 68)

sys.exit(0)
