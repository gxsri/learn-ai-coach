# 02 · YOLO 从零到能用

> 目标：从"没装过"到"能在自己的图上跑出结果"，再到"知道怎么训练自己的模型"。
> 每一步都给完整命令，可以照抄。

---

## 一、先搞清楚 YOLO 的版本乱象（这是新手第一个坑）

网上教程满天飞，讲的可能是五六年前的版本。**先建立正确的时间线认知：**

| 版本 | 状态 | 新手要不要用 |
|---|---|---|
| YOLOv5 | 老教程重灾区 | ❌ 别学，资料全是过时的 |
| YOLOv8 | Ultralytics 出品，曾经的长期主流 | ⚠️ 还能用，但已是老版本 |
| **YOLO11** | Ultralytics 官方标注为**当前稳定版、推荐所有场景使用** | ✅ 生态资料最全，**作为回退选项记住它** |
| YOLO12 | ⚠️ **社区模型**，不是 Ultralytics 官方主线 | ❌ 官方文档明确提到它**训练不稳定、显存占用高**，而且**只发布了检测权重**（姿态/分割/分类/旋转框的预训练权重都没有） |
| YOLO13 | — | ❌ **不存在**。看到有人讲 YOLO13，那篇可以直接关掉 |
| **YOLO26** | Ultralytics 较新发布，官方定位为新的 SOTA（端到端实时视觉模型） | ✅ **新项目直接用这个** |
| YOLO27 | 官方页面已存在，但明确写**模型尚未发布** | ❌ 还不能用 |

> **一句话决策**：
> **新项目 → `yolo26n-pose.pt`（姿态）或 `yolo26n.pt`（检测）。**
> **遇到资料对不上、教程找不到 → 回退到 `yolo11n-pose.pt`，它的资料最全。**

**为什么推荐 YOLO26 而不是资料更多的 YOLO11？** 因为性能差距是实打实的。
同为 2.9M 参数的最小姿态模型，官方 COCO 关键点指标：
`yolo11n-pose` = **50.0** mAP50-95，`yolo26n-pose` = **57.2** mAP50-95。
**同样大小、同样速度，精度高 7 个点。**

---

## 二、许可证：一个必须知道的事

**Ultralytics 是 AGPL-3.0 许可。** 这句话的实际含义：

| 你的用途 | 是否免费 |
|---|---|
| 自己学习、课程作业、学术研究 | ✅ 免费 |
| 开源你自己的项目（同样 AGPL 开源） | ✅ 免费 |
| 做一个网站/App/服务对外提供（哪怕只是内部工具） | ❌ **需要商业授权** |
| 用自己微调出来的模型商用 | ❌ **需要商业授权**（微调权重同样受 AGPL 约束） |

> **对你现在**：自己做分析、写报告、发朋友圈——**完全没问题**。
> **但如果有一天你想做成产品**，要么买 Ultralytics Enterprise 授权，要么换掉模型。
>
> 📌 **养成习惯**：以后每引入一个新库，先问一句"它是什么许可证"。这个问题问 AI 助手，它答得通常不错。

---

## 三、五种任务：你要的是哪一种

Ultralytics 一个库干五件事，用同一个 API：

| 任务 | 干什么 | 输出 | 羽毛球场景用不用 |
|---|---|---|---|
| `detect` | 目标检测 | 矩形框 + 类别 | 用（检测球员、球拍） |
| `segment` | 实例分割 | 像素级轮廓 | 不必要 |
| `pose` | **姿态估计 / 关键点** | **17 个关键点 + 框** | ✅ **主力** |
| `classify` | 整图分类 | 一个类别 | 暂不用 |
| `obb` | 旋转框 | 带角度的框 | 暂不用 |

**你要的是 `pose`。** 它会一次性给你：每个人的检测框 + 17 个关键点 + （配合跟踪时）稳定的 id。

> ⚠️ **常见误解**：以为"先学 detect 再学 pose"。
> 对**训练自己的模型**来说确实可以先学 detect（流程一样，pose 只是多几个关键点）。
> 但对**你的羽毛球项目**来说，**detect 出的框算不出任何动作指标**——直接上 pose。

### COCO-17 关键点索引（背下来，或者抄进代码常量表）

这是 YOLO-pose 输出的 17 个点，**索引写错是最高频的 bug**：

```python
KP = {
    'nose': 0,
    'left_eye': 1,  'right_eye': 2,
    'left_ear': 3,  'right_ear': 4,
    'left_shoulder': 5,  'right_shoulder': 6,
    'left_elbow': 7,     'right_elbow': 8,
    'left_wrist': 9,     'right_wrist': 10,
    'left_hip': 11,      'right_hip': 12,
    'left_knee': 13,     'right_knee': 14,
    'left_ankle': 15,    'right_ankle': 16,
}
```

⚠️ **提醒**：
- `5` 是**左**肩，`6` 才是右肩。很多人搞反。
- **没有脚部点**，只有脚踝。要做步法分析的话 COCO-17 不够用（需要 26 点模型）。
- 模型说的 left/right 是**球员自己身体的左右**。球员背对镜头时，画面左边的其实是他的右手。

---

## 四、装环境（照抄）

### 4.1 装 ffmpeg（Windows）

视频抽帧要用它。选一种：

```powershell
# 方式一：winget（Windows 10/11 自带）
winget install --id Gyan.FFmpeg -e

# 方式二：如果装了 scoop
scoop install ffmpeg
```

装完**重开一个终端**，验证：

```powershell
ffmpeg -version
```

### 4.2 建一个干净的 Python 环境

**强烈建议用虚拟环境。** 不是为了显得专业，是因为深度学习库的版本冲突极多，
把系统 Python 弄脏了以后很难收拾。

```powershell
# 建环境（在你的项目目录下）
cd D:\program\learn-ai-coach\starter
python -m venv .venv
```

### ⚠️ 然后**不要**急着 `Activate.ps1`

这是 Windows 上最坑的一步。PowerShell **默认禁止运行 `.ps1` 脚本**：

```powershell
.\.venv\Scripts\Activate.ps1
# → 无法加载文件 ...\Activate.ps1，因为在此系统上禁止运行脚本
```

**后果很容易被误判**：虚拟环境其实没激活，之后敲 `python` 用的是**系统 Python**，
于是报 `ModuleNotFoundError: No module named 'pandas'` ——
**这个报错会把你引向"是不是没装"这个完全错误的方向**（其实装了，只是装在了别处）。

**三种解法，推荐第 1 种：**

```powershell
# 【推荐】不激活，直接用虚拟环境里的 python。不受执行策略影响。
.\.venv\Scripts\python.exe selftest.py

# 或者用 starter 目录下的快捷方式（少打字）
.\run.cmd selftest.py

# 【临时】只放开当前这个窗口，关掉就失效，很安全
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

# 【永久】一次设置，以后都不用管。⚠️ 这会放宽你账户的脚本执行策略
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**验证当前用的是哪个解释器**（养成习惯，能省掉大量排查时间）：

```powershell
python -c "import sys; print(sys.executable)"
# 路径里必须带 .venv 才对
```

> **如果 `python -m venv` 报 `ensurepip ... returned non-zero exit status 1`**：
> 这是 Windows 上 venv 模块偶尔抽风，通常是临时目录权限问题。两个绕法：
> 1. 改用 `python -m venv --without-pip .venv`，然后 `python -m pip --python .venv\Scripts\python.exe install pip`
> 2. 装一个 `uv`：`python -m pip install --user uv`，然后 `uv venv .venv`（uv 建环境不需要 ensurepip，而且快得多）

### 4.3 装 PyTorch 和 Ultralytics

**顺序很重要：先装 PyTorch，再装 ultralytics。** 不然 ultralytics 会自动给你装一个 CPU 版。

```powershell
# ① 先装 CUDA 版 PyTorch（约 2-3 GB，耐心等）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# ② 再装 ultralytics 和工具
pip install ultralytics opencv-python pandas matplotlib

# ③ 验证（这一步必须做！）
python -c "import torch, ultralytics; print('torch', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only'); print('ultralytics', ultralytics.__version__)"
```

**期望输出**应该是 `cuda available: True` 和你的 `NVIDIA GeForce RTX 4060 Laptop GPU`。

> ⚠️ **如果 `cuda available: False`**：说明装成了 CPU 版。
> `pip uninstall torch torchvision -y`，然后重跑第 ① 步，确认 `--index-url` 那一串没写错。

> ⚠️ **不要同时装 `opencv-python` 和 `opencv-python-headless`，也不要装 mediapipe 后再装 opencv-python**——
> 它们共用同一个 `cv2` 命名空间，会互相覆盖，症状是"某个函数莫名其妙不存在"。
> **一个环境只留一个 OpenCV 包。**

---

## 五、第一个模型：三行代码

```python
from ultralytics import YOLO

model = YOLO('yolo26n-pose.pt')        # 首次运行会自动下载权重（需要联网）
results = model.predict('test.jpg', save=True)   # 结果存到 runs/pose/predict/
```

或者一条命令行：

```powershell
yolo pose predict model=yolo26n-pose.pt source=test.jpg save=True
```

**跑通标志**：终端打印出检测到的目标数量，`runs/` 目录下出现一张带骨架的图。

### 换成视频

```powershell
yolo pose predict model=yolo26n-pose.pt source=badminton.mp4 save=True
```

**加跟踪**（让每个球员有稳定的 id —— 这对羽毛球分析是**必须的**）：

```python
results = model.track(source='badminton.mp4', persist=True, save=True)
```

`persist=True` 让跟踪状态跨帧保持。输出里 `r.boxes.id` 就是每个人的 id。

> **为什么必须跟踪？** 没有 id 的话，你只知道"这一帧有 2 个人"，
> 但不知道哪个是哪个。跨帧的骨架曲线会随机跳到另一个人身上，指标全废。

---

## 六、训练自己的模型（阶段 4 才做，先读不练）

### 6.1 数据从哪来

| 方式 | 说明 |
|---|---|
| **公开数据集** | 找现成的标注，最省事。检索"你的目标 + 类别 + dataset + YOLO format" |
| **自己录视频抽帧** | 最现实。见下面 |
| Roboflow 等在线平台 | 能在线标注 + 自动转格式，新手友好，但免费额度有限 |

### 6.2 抽帧（用 ffmpeg）

不要每个视频都抽成几千张，**先稀疏抽帧做标注**：

```powershell
# 每秒抽 2 帧（用于"抽样标注"）
ffmpeg -i badminton.mp4 -vf fps=2 frames/%06d.jpg

# 每 0.5 秒一帧 → 上面就是 2fps
# 想只要能看清动作的关键帧，可以加筛选：
ffmpeg -i badminton.mp4 -vf "fps=2,scale=1280:-1" frames/%06d.jpg
```

> ⚠️ **2fps 只能用来做静态标注。**
> 后面算"手腕速度峰值"这种时序特征时，**必须回到原帧率（30fps 以上）**。
> 两者混用的话，峰值检测会完全失效——因为击球只持续几帧，2fps 根本采不到。

### 6.3 标注工具

| 工具 | 特点 |
|---|---|
| **X-AnyLabeling** | 国产、免费、支持 AI 预标注（能调用模型自动标框）。**推荐新手** |
| Label Studio | 通用、网页版、功能全，配置稍复杂 |
| Roboflow | 在线平台，标注 + 增强 + 导出一条龙 |
| CVAT | 工业级，团队协作用 |
| labelme | 老牌，偏分割 |

**关键技巧：先用一个训练好的模型做"预标注"，再人工修正。** 速度能快 5-10 倍。

### 6.4 YOLO 的标注格式（必懂）

YOLO 不用 XML/JSON，用的是**一个图片配一个 txt**：

```
# frames/000001.txt
0 0.375 0.509 0.083 0.648
0 0.812 0.493 0.091 0.702
```

每一行一个目标，5 个数字，**全部归一化到 0-1**：

```
<class_id> <中心x> <中心y> <宽> <高>
```

- `class_id` **从 0 开始**，必须和 `names` 列表的索引严格对应
- 中心点和宽高都是**除以图片宽高之后的比值**（不是像素）
- 没有目标的图片可以没有 txt 文件

> ⚠️ **最常见的低级错误**：`class_id` 从 1 开始写。YOLO 会静默地把它当成"第 2 个类别"。

### 6.5 `data.yaml`

```yaml
path: D:/program/badminton/dataset    # 数据集根目录
train: images/train                   # 训练图片目录（相对 path）
val: images/val

names:
  0: player
  1: racket
```

### 6.6 训练

```powershell
yolo pose train model=yolo26n-pose.pt data=data.yaml epochs=100 imgsz=640 batch=8 device=0
```

**参数在 8GB 显存下的建议**：

| 参数 | 建议值 | 说明 |
|---|---|---|
| `imgsz` | `640` | 别一上来 1280，显存会炸 |
| `batch` | `8`（爆显存就降到 4 或 2） | 报 `CUDA out of memory` 就往下调 |
| `epochs` | `100` 起步 | 看 `results.csv` 决定要不要加 |
| `device` | `0` | 用第一块 GPU；`cpu` 强制用 CPU |
| `patience` | `20` | 20 轮没提升就自动早停 |

**断点续训**：

```powershell
yolo pose train model=runs/pose/train/weights/last.pt data=data.yaml resume=True
```

### 6.7 训练输出里每个文件是什么

```
runs/pose/train/
├── weights/
│   ├── best.pt        ← 验证集表现最好的权重，**用它**
│   └── last.pt        ← 最后一轮的，用来续训
├── results.csv        ← 每轮的指标，用 Excel/pandas 打开画曲线
├── results.png        ← 上面那个的图
├── confusion_matrix.png  ← 混淆矩阵，看哪两类在互相混
├── labels.jpg         ← 标注分布直方图
└── train_batch*.jpg   ← 训练时的实际输入（**用它检查数据增强有没有做坏**）
```

### 6.8 看懂指标

| 指标 | 含义 | 怎么用 |
|---|---|---|
| **mAP50** | IoU 阈值 0.5 时的平均精度 | 宽松指标，看着高不代表好用 |
| **mAP50-95** | IoU 从 0.5 到 0.95 取平均 | **最严格的综合指标，主要看这个** |
| Precision | 查准率：报出来的里有多少是对的 | 误报多 → 关注它 |
| Recall | 查全率：该找到的找到了多少 | 漏检多 → 关注它 |

**判断过拟合**：训练 loss 一直降，验证 loss 先降后升 → 过拟合了。
（看 `results.png` 里两条 loss 曲线。）

### 6.9 导出成别的格式（部署用）

```powershell
# 把路径写完整，不要留省略号
yolo export model=runs/pose/train/weights/best.pt format=onnx
yolo export model=runs/pose/train/weights/best.pt format=openvino
yolo export model=runs/pose/train/weights/best.pt format=engine half=True   # TensorRT
```

> ⚠️ 网上很多教程写 `model=...`，那是**占位符**，照抄必报错。

| 格式 | 什么时候用 |
|---|---|
| `.pt` | 训练、验证、开发阶段 |
| ONNX | 跨平台部署，通用 |
| OpenVINO | Intel CPU/核显加速 |
| TensorRT (`.engine`) | **NVIDIA 显卡上最快**，但导出慢、和驱动/CUDA 版本绑定紧 |

**先别急着导出。** 开发阶段用 `.pt` 最省事，等真的要部署了再说。

---

## 七、8GB 显存下能干什么

| 任务 | 可行性 |
|---|---|
| `yolo26n-pose` 推理 1080p 视频 | ✅ 毫无压力 |
| `yolo26s-pose` / `yolo26m-pose` 推理 | ✅ 可以，`imgsz` 保持 640-960 |
| 训练 `yolo26n-pose`（小数据集） | ✅ 可以，`batch=8` 左右 |
| 训练 `yolo26l/x-pose` | ❌ 不要碰 |
| 同时跑姿态模型 + TrackNet | ⚠️ 分段批处理，别同时塞 |

**显存不够时的降级顺序**：降 `batch` → 降 `imgsz` → 换更小的模型 → 开混合精度。

---

## 八、给 AI 编程助手的提示词

> 我要在 Windows + Python 3.12 + RTX 4060 Laptop 8GB 上使用 Ultralytics YOLO 做**姿态估计**。
> 请用 `yolo26n-pose.pt`（如果官方已改名请告诉我实际可用的权重名），**不要**用 YOLOv5/v8 时代的写法。
>
> **请先确认**：库名、权重文件名、CLI 参数、Python API 参数在你即将给出的版本里真实存在。
> 如果不确定，先让我运行 `python -c "import ultralytics; print(ultralytics.__version__)"` 确认版本，再给代码。**不要凭印象编造参数名。**
>
> 涉及许可时请主动提醒：Ultralytics 是 AGPL-3.0，我的用途是个人学习分析。
>
> 请按"最小可运行脚本"给我：先能跑通，再谈优化。每个命令告诉我它会产生什么文件、在哪。
> 如果某一步可能失败，先告诉我失败长什么样、怎么判断、怎么修。
