"""
env_hint.py —— 把"用错了解释器"这个高频错误变成一句能自我诊断的提示。

为什么单独一个文件：
  它必须在 numpy / pandas / torch 都还没导入成功的时候就能运行，
  所以**不能依赖任何第三方库**，只准用标准库。

背景（这是 Windows 上最常见的一个坑）：
  PowerShell 默认禁止运行 .ps1 脚本，所以 `.venv\\Scripts\\Activate.ps1`
  会直接报 "在此系统上禁止运行脚本"，虚拟环境其实**没有激活**。
  这时候敲 `python`，用的是系统 Python —— 包都装在 .venv 里，当然找不到。
  报错信息却会说"没有安装 xxx"，把人引向完全错误的方向。

  解决办法不是去改系统策略，而是**根本不激活**：
  直接调用 `.venv\\Scripts\\python.exe` 就行（或用同目录的 run.cmd）。
"""

import os
import sys


def venv_python(script_file=None):
    """返回与本文件同级目录下 .venv 里的 python 路径；不存在则返回 None。"""
    base = os.path.dirname(os.path.abspath(script_file or __file__))
    for candidate in (
        os.path.join(base, '.venv', 'Scripts', 'python.exe'),   # Windows
        os.path.join(base, '.venv', 'bin', 'python'),           # Linux / macOS
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def in_venv():
    """当前解释器是不是跑在某个虚拟环境里。"""
    return sys.prefix != sys.base_prefix


def explain_missing(module_name, script_file=None, pip_name=None):
    """
    打印一段能真正定位问题的提示。

    它区分两种情况：
      A. 有 .venv 但当前不是它  → "你用错了解释器"（给出精确命令）
      B. 确实没装               → "装上它"
    """
    pip_name = pip_name or module_name
    target = venv_python(script_file)
    using_wrong_python = False

    if target:
        try:
            same = os.path.normcase(os.path.abspath(sys.executable)) == \
                   os.path.normcase(os.path.abspath(target))
        except Exception:
            same = False
        using_wrong_python = not same

    w = sys.stderr.write
    w('\n' + '=' * 68 + '\n')

    if using_wrong_python:
        # ── 情况 A：这是最可能的真实原因，把它放在最前面 ──────────────────
        w(f'[错误] 当前 Python 里没有 {module_name}\n\n')
        w('        但真正的问题不是"没装"，而是你用错了解释器。\n\n')
        w(f'        现在的解释器    {sys.executable}\n')
        w(f'        包实际装在这里  {target}\n\n')
        w('        最常见的原因：PowerShell 禁止运行 .ps1 脚本，\n')
        w('        所以 .\\.venv\\Scripts\\Activate.ps1 报"禁止运行脚本"，\n')
        w('        虚拟环境其实没激活 —— 这时 python 用的是系统 Python。\n\n')
        w('  ── 怎么修（任选一个，推荐第 1 个）──\n\n')
        w('  1) 不激活，直接用虚拟环境里的 python：【最省事，不受执行策略影响】\n\n')
        w(f'       "{target}" 02_extract_pose.py --video 视频.mp4 --session s1\n\n')
        w('     或者用本目录下的快捷方式（推荐，少打字）：\n\n')
        if os.name == 'nt':
            w('       .\\run.cmd 02_extract_pose.py --video 视频.mp4 --session s1\n\n')
        else:
            w('       ./run 02_extract_pose.py --video 视频.mp4 --session s1\n\n')

        w('  2) 临时允许本次窗口运行脚本，然后再激活\n')
        w('     （只影响当前这个 PowerShell 窗口，关掉就失效，很安全）：\n\n')
        w('       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass\n')
        w('       .\\.venv\\Scripts\\Activate.ps1\n\n')

        w('  3) 永久允许当前用户运行本地脚本（一次设置，以后都不用管）\n')
        w('     ⚠️ 这会放宽你账户的脚本执行策略，请自行判断是否接受：\n\n')
        w('       Set-ExecutionPolicy -Scope CurrentUser RemoteSigned\n\n')

        w('  ── 怎么确认修好了 ──\n\n')
        w('       python -c "import sys; print(sys.executable)"\n')
        w(f'     输出的路径里应该带 .venv（也就是上面那个 {target}）\n')
    else:
        # ── 情况 B：确实没装 ──────────────────────────────────────────────
        w(f'[错误] 没有安装 {module_name}\n\n')
        w(f'        当前解释器    {sys.executable}\n')
        w(f'        在不在虚拟环境  {"是" if in_venv() else "否"}\n\n')
        w('  ── 怎么修 ──\n\n')
        if not in_venv():
            w('  1) 先建并进入虚拟环境：\n\n')
            w('       python -m venv .venv\n')
            w('       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass\n')
            w('       .\\.venv\\Scripts\\Activate.ps1\n\n')
            w('     懒得处理执行策略的话，直接跑本目录的 setup.ps1：\n\n')
            w('       powershell -ExecutionPolicy Bypass -File .\\setup.ps1\n\n')
        w(f'  2) 装它：\n\n       python -m pip install {pip_name}\n\n')
        w('  注意：永远用 `python -m pip install` 而不是 `pip install`，\n')
        w('        这样能保证 pip 和 python 是同一个环境。\n')

    w('=' * 68 + '\n')
    sys.stderr.flush()


def fail_fast(module_name, script_file=None, pip_name=None):
    """打印诊断信息并退出（退出码 1）。"""
    explain_missing(module_name, script_file, pip_name)
    sys.exit(1)


if __name__ == '__main__':
    # 单独运行本文件 = 诊断一下当前环境
    print('当前解释器        ', sys.executable)
    print('在虚拟环境里      ', '是' if in_venv() else '否')
    # 注意：venv_python() 收的是**脚本文件路径**，不是目录 —— 它内部会自己取 dirname
    target = venv_python(__file__)
    print('本目录的 .venv    ', target or '（不存在）')
    if target:
        same = os.path.normcase(os.path.abspath(sys.executable)) == \
               os.path.normcase(os.path.abspath(target))
        print('是否就是当前解释器', '是 —— 环境正确' if same else '否 —— 你应该用上面那个')
    print()
    print('第三方库：')
    for mod, pip in (('numpy', 'numpy'), ('cv2', 'opencv-python'),
                     ('pandas', 'pandas'), ('matplotlib', 'matplotlib'),
                     ('torch', 'torch'), ('ultralytics', 'ultralytics')):
        try:
            __import__(mod)
            print(f'  [OK]   {pip}')
        except ImportError:
            print(f'  [MISS] {pip}')
