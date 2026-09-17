# starter · 可运行的代码骨架

> 从"一段视频"走到"一份带指标的报告"。每一步都能单独跑、单独验证。

---

## 先跑这两个（不需要显卡、不需要视频）

> ### ⚠️ 先说一个必踩的坑：不要用 `Activate.ps1`
>
> Windows PowerShell **默认禁止运行 `.ps1` 脚本**，所以：
>
> ```powershell
> .\.venv\Scripts\Activate.ps1
> # → 无法加载文件 ... 因为在此系统上禁止运行脚本
> ```
>
> **虚拟环境因此没有激活**，这时敲 `python` 用的是**系统 Python**，
> 包都装在 `.venv` 里 —— 于是你会看到
> `ModuleNotFoundError: No module named 'pandas'` 这种**把人引向错误方向**的报错。
>
> **正确做法：根本不激活，直接调用虚拟环境里的 python。**
> 本目录提供了一个快捷方式 `run.cmd`（`.cmd` 不受 PowerShell 执行策略限制）：
>
> ```powershell
> .\run.cmd                    # 环境诊断（不带参数）
> .\run.cmd selftest.py        # 等价于 .venv\Scripts\python.exe selftest.py
> .\run.cmd 01_check_env.py
> ```
>
> 或者直接写全路径（效果一样，少一层封装）：
>
> ```powershell
> .\.venv\Scripts\python.exe selftest.py
> ```
>
> **想用常规的 activate 也行**，加一句临时放开（只影响当前窗口，关掉即失效）：
>
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\.venv\Scripts\Activate.ps1
> ```
>
> 怎么确认修好了：`python -c "import sys; print(sys.executable)"`
> 输出的路径里**必须带 `.venv`**。

### 三个自检

```powershell
cd D:\program\learn-ai-coach\starter

.\run.cmd 01_check_env.py      # 环境自检：告诉你缺什么、怎么装
.\run.cmd selftest.py          # 算法自检：26 项，用合成数据验证核心算法
.\run.cmd make_demo_session.py # 生成合成数据，完整跑通 03/04（不需要视频和显卡）
```

**这三步现在就能跑。** 跑通了，你就已经验证了：算法是对的、流水线是通的。
之后遇到问题，就能确定是**数据**的问题，不是**代码**的问题。

---

## 装环境

```powershell
# 一键脚本（推荐）
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

或者手动（**顺序不能反**）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 先装 CUDA 版 PyTorch —— 反过来的话 ultralytics 会给你装 CPU 版
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# 再装其余的
pip install ultralytics opencv-python pandas matplotlib numpy
```

还需要 **ffmpeg**（抽帧用）：

```powershell
winget install --id Gyan.FFmpeg -e
```

> **卡住了？** 先看 `../part2-YOLO与骨架/05-常见坑与调试.md`，那是专门写给你的排错手册。

---

## 完整流水线

> ✅ **本流水线已在一台真实机器上端到端跑通**
> （RTX 4060 Laptop / torch 2.11.0+cu128 / ultralytics 8.4.153 / pandas 3.0.5）
> 真实测试：341 帧 1080p 视频，27.3 秒处理完，11-12 帧/秒，产出 1014 行骨架。

```
┌──────────────────────────────────────────────────────────────┐
│ ① 视频 → 骨架坐标                                            │
│    .\run.cmd 02_extract_pose.py --video 视频.mp4 --session s1 │
│    产出 01_pose.csv + meta.json                              │
│    ⚠️ 需要显卡 + 联网（首次会自动下载权重）                    │
│    ⚠️ 跑完一定要看"跟踪稳定性体检"的输出                       │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ ② 骨架 → 击球事件 + 指标                                     │
│    .\run.cmd 03_events_and_metrics.py --session s1            │
│    产出 02_events.csv + 03_metrics.json                      │
│    ⚠️ 不需要显卡。这一步最容易被做错                          │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ ③ 生成报告                                                   │
│    .\run.cmd 04_report.py --session s1                        │
│    产出 curves.png + report.html                             │
└──────────────────────────────────────────────────────────────┘
```

> 下面的命令一律用 `.\run.cmd xxx.py`。
> 如果你已经正确激活了虚拟环境（`python` 指向 `.venv`），把 `.\run.cmd` 换成 `python` 也一样。

### 手边没有羽毛球视频？用自带的测试视频

`testdata/people-walking.mp4` 是一段真实的行人视频（25fps / 1920×1080 / 341 帧），
来自 Roboflow 的公开示例素材。**它不是羽毛球视频**，所以"击球"结果没有意义 ——
但它能验证整条流水线（读视频 → 推理 → 跟踪 → 落盘 → 报告）是通的。

```powershell
.\run.cmd 02_extract_pose.py --video testdata/people-walking.mp4 --session walk
.\run.cmd 03_events_and_metrics.py --session walk
.\run.cmd 04_report.py --session walk
```

---

## 文件清单

| 文件 | 作用 | 需要什么 |
|---|---|---|
| `run.cmd` | **快捷启动器**：直接用 `.venv` 的 python 跑脚本，绕开 PowerShell 执行策略 | — |
| `env_hint.py` | 用错解释器时给出可自我诊断的提示（`.\run.cmd` 不带参数即运行它） | 无 |
| `common.py` | 公共常量 + 核心算法（角度、SG 平滑、速度、击球检测、标定） | numpy |
| `selftest.py` | **26 项算法自检**，用合成数据验证算法正确性 | numpy |
| `01_check_env.py` | 环境体检：缺什么、怎么装 | 无（标准库） |
| `02_extract_pose.py` | 视频 → `01_pose.csv` | ultralytics + torch + cv2 |
| `03_events_and_metrics.py` | CSV → 击球事件 + 指标 | pandas + numpy |
| `04_report.py` | → `curves.png` + `report.html` | pandas + matplotlib |
| `make_demo_session.py` | 生成合成数据，离线验证流水线 | numpy |
| `setup.ps1` | 一键装环境（UTF-8 **带 BOM**，否则 PowerShell 5.1 会把中文读成乱码） | — |

> ### 两个 Windows 编码坑（改这些文件之前先看）
>
> **① `.cmd` / `.bat` 必须是纯 ASCII。**
> `cmd.exe` 用**系统 OEM 代码页（中文 Windows 上是 GBK）**读取批处理文件，**不是 UTF-8**。
> 在 `.cmd` 里写中文注释，会被解码成乱码字节，`cmd` 会**把乱码当命令去执行**，
> 表现为刷屏的 `'xxx' is not recognized as an internal or external command` 死循环。
> `run.cmd` 因此**刻意全用英文注释**。
>
> **② `.ps1` 必须带 UTF-8 BOM。**
> 本机是 **Windows PowerShell 5.1**，它读取**无 BOM** 的 `.ps1` 时按 ANSI(cp936) 解析，
> 中文全部乱码。带 BOM 才会按 UTF-8 解析。
>
> ⚠️ **注意**：用编辑器（或 AI 助手）改完 `setup.ps1` 之后，**BOM 可能会被去掉**。
> 检查并加回：
>
> ```powershell
> $p = '.\setup.ps1'
> $b = [System.IO.File]::ReadAllBytes($p)
> if (-not ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)) {
>   $t = [System.IO.File]::ReadAllText($p, (New-Object System.Text.UTF8Encoding $false))
>   [System.IO.File]::WriteAllText($p, $t, (New-Object System.Text.UTF8Encoding $true))
>   'BOM 已加回'
> }
> ```
>
> 好消息是：BOM 丢了只会让**提示文字乱码**，脚本逻辑本身（全是 ASCII）照常工作。

---

## 每个脚本的关键参数

### `02_extract_pose.py`

| 参数 | 默认 | 什么时候改 |
|---|---|---|
| `--session` | 必填 | 每次分析换一个名字。**这是数据划分的关键字段，不要重复用** |
| `--model` | `yolo26n-pose.pt` | 资料找不到就换 `yolo11n-pose.pt` |
| `--conf` | `0.3` | 检测阈值。漏检多 → 降到 `0.15`；误检多 → 升到 `0.5` |
| `--imgsz` | `640` | **人小就提到 1280** —— 实测能把"无 id 的框"从 31.9% 降到 0% |
| `--overlay` | 关 | **强烈建议开**：输出 `overlay.mp4`，用肉眼看跟踪准不准 |

### ⭐ `--overlay` 是你最该用的一个开关

```powershell
.\run.cmd 02_extract_pose.py --video 你的视频.mp4 --session s1 --overlay
```

它会输出一段 `overlay.mp4`，画面上直接标出：

| 画的东西 | 含义 |
|---|---|
| 绿色连线 | 骨架，两端关键点都可信 |
| 橙色实心点 | 关键点置信度 ≥ 0.5（03 步骤会采用） |
| **红色叉** | 置信度 < 0.5（03 步骤会**丢掉**这些点，所以你看到红叉就是那个部位不可信） |
| `id=8` 黄字 | 跟踪 id |
| `id=?` | **跟踪器没给这个人分配 id** —— 这种行 03 默认会跳过 |

**为什么必须看**：`01_pose.csv` 里全是数字，
`report.html` 里全是统计量 —— **两者都看不出"骨架到底跟没跟住人"**。
只有把骨架画回视频上，你才能一眼看出：
串号了没有、遮挡时断了没有、红叉是不是出现在关键部位。

> **这一步是"数据质量验收"，不是可选项。** 骨架跟不住，后面所有指标都是垃圾。

### `03_events_and_metrics.py`

| 参数 | 默认 | 什么时候改 |
|---|---|---|
| `--hand` | `right` | **持拍手搞反了是最常见的错**。结果不对先试 `--hand left` |
| `--min-speed` | `3.0` | 击球检出太少 → 降到 `2.0`；假击球太多 → 升到 `5.0` |
| `--min-gap` | `10` | 一次挥拍被拆成好几次 → 调大 |
| `--fps` | 从 meta 读 | meta 里没有就**必须手工传**，否则所有速度指标都偏 |

---

## 跑完之后，怎么判断结果对不对

### 有合成数据时（推荐先做这个）

```powershell
python make_demo_session.py
python 03_events_and_metrics.py --session demo
```

把 `03_metrics.json` 里的 `hit_frames` 和 `meta.json` 里的
`ground_truth_hit_frames` 对一下 —— **误差在 ±5 帧内就算正常**。

> 实测：2 个球员各 3 次击球，检出 **6/6**，最大误差 **1 帧**。

### 用真实视频时

| 检查什么 | 怎么查 | 正常的样子 |
|---|---|---|
| **跟踪稳不稳** | `02` 跑完的体检输出 | 2-4 个 `track_id`，每个覆盖几千帧 |
| **骨架跟不跟得住** | `02` 加 `save=True` 看叠加视频 | 火柴人贴着人不乱跳 |
| **击球次数合不合理** | 数一下视频里大概打了几拍 | 检出数量量级一致（±20%） |
| **速度曲线有没有峰** | 看 `curves.png` 第一张图 | 明显的峰谷，不是一条平线 |
| **角度值合不合理** | 看 `report.html` 的明细表 | 肘角大致在 90°-180° 之间 |

---

## ⚠️ 三条必须知道的限制

1. **所有角度都是「画面投影角」，不是生物力学真值。**
   单目 2D 有系统性低估。报告里已经自动写入了这条声明。
   只做**同一机位、同一球员**的纵向对比。

2. **速度的单位是「肩宽/秒」，不是「米/秒」。**
   要换成米，必须先做场地标定（`common.py` 里有 `homography_from_points`）。

3. **不要把报告用于医疗或训练决策。** 它是一个分析辅助工具。

---

## 下一步

- 想理解每一步的原理 → `../part2-YOLO与骨架/`
- 卡住了 → `../part2-YOLO与骨架/05-常见坑与调试.md`
- 想学怎么用多 agent 加速这些工作 → `../part1-多agent协作/`
