# setup.ps1 —— 一键准备 Python 环境
#
# 用法（在 PowerShell 里，于本目录下执行）：
#     powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# 它会：
#   1. 建虚拟环境 .venv
#   2. 先装 CUDA 版 PyTorch（顺序很重要，反了会装成 CPU 版）
#   3. 再装 ultralytics 和其余工具
#   4. 跑一次验证，把结果打出来

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "`n=== 羽毛球动作分析 · 环境准备 ===" -ForegroundColor Cyan
Write-Host "工作目录：$here`n"

# ── 1. 检查 python ──────────────────────────────────────────────────────────
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) {
    Write-Host "[错误] 找不到 python。请先安装 Python 3.10-3.12 并勾选 Add to PATH。" -ForegroundColor Red
    exit 1
}
Write-Host "[1/5] 使用 Python：$py"
& python --version

# ── 2. 建虚拟环境 ───────────────────────────────────────────────────────────
if (Test-Path "$here\.venv\Scripts\python.exe") {
    Write-Host "[2/5] 虚拟环境已存在，跳过创建" -ForegroundColor Yellow
} else {
    Write-Host "[2/5] 创建虚拟环境 .venv ..."
    & python -m venv "$here\.venv"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "$here\.venv\Scripts\python.exe")) {
        Write-Host "     常规创建失败，尝试 --without-pip 方式（Windows 上 venv 偶尔抽风）" -ForegroundColor Yellow
        & python -m venv --without-pip "$here\.venv"
    }
}

$vpy = "$here\.venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) {
    Write-Host "[错误] 虚拟环境创建失败。试试先装 uv：python -m pip install --user uv ; uv venv .venv" -ForegroundColor Red
    exit 1
}

# ── 3. 确保 venv 里有 pip ───────────────────────────────────────────────────
& $vpy -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[3/5] 虚拟环境里没有 pip，用基础 Python 的 pip 装进去 ..."
    & python -m pip --python $vpy install --upgrade pip
} else {
    Write-Host "[3/5] pip 就绪"
    & $vpy -m pip install --quiet --upgrade pip
}

# ── 4. 装依赖（顺序不能反）──────────────────────────────────────────────────
Write-Host "[4/5] 安装 CUDA 版 PyTorch（约 2-3 GB，请耐心等待）..." -ForegroundColor Cyan
& $vpy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) {
    Write-Host "     CUDA 版安装失败。如果只是想先跑通，可以退回 CPU 版：" -ForegroundColor Yellow
    Write-Host "     & `"$vpy`" -m pip install torch torchvision" -ForegroundColor Yellow
}

Write-Host "`n     安装 ultralytics 与其余工具..." -ForegroundColor Cyan
& $vpy -m pip install ultralytics opencv-python pandas matplotlib numpy lap

# ── 5. 验证 ─────────────────────────────────────────────────────────────────
Write-Host "`n[5/5] 验证安装结果 ...`n" -ForegroundColor Cyan
& $vpy -c @"
import torch, ultralytics, cv2, pandas, numpy
print('  torch      ', torch.__version__)
print('  cuda 可用  ', torch.cuda.is_available())
if torch.cuda.is_available():
    print('  显卡       ', torch.cuda.get_device_name(0))
    print('  显存       ', round(torch.cuda.get_device_properties(0).total_memory/1024**3, 1), 'GB')
print('  ultralytics', ultralytics.__version__)
print('  opencv     ', cv2.__version__)
print('  pandas     ', pandas.__version__)
print('  numpy      ', numpy.__version__)
"@

Write-Host "`n=== 完成 ===" -ForegroundColor Green
Write-Host "接下来跑环境自检和算法自检：`n" -ForegroundColor Cyan
Write-Host "  # 注意：不要用 .\.venv\Scripts\Activate.ps1 ——"
Write-Host "  # PowerShell 默认禁止运行 .ps1 脚本，激活会失败，"
Write-Host "  # 之后 python 会指向系统 Python，报'没有安装 xxx'把你带偏。"
Write-Host "  #"
Write-Host "  # 直接调用虚拟环境里的 python 就行（.cmd 不受执行策略限制）：`n"
Write-Host "  .\run.cmd 01_check_env.py"
Write-Host "  .\run.cmd selftest.py"
Write-Host "  .\run.cmd make_demo_session.py`n"
Write-Host "  等价写法：.\.venv\Scripts\python.exe 01_check_env.py`n"
Write-Host "  不确定当前用的是哪个解释器？跑 .\run.cmd（不带参数）看诊断。`n"
