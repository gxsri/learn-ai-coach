# YOLO 自定义数据集与训练全流程（面向羽毛球运动表现分析）

## 一句话结论

从 0 到第一个能用的模型，最短路径是：**自己录 3–5 段羽毛球视频 → ffmpeg 按 2 fps 抽帧 + 去重 → X-AnyLabeling 标 3 类（player / racket / shuttle）约 300–500 张 → `yolo detect train model=yolo26n.pt` 在 8GB 显存上用 `imgsz=640 batch=8` 训 100–150 轮**，命令全部来自 Ultralytics 官方文档，不需要自己写训练代码。

## 核心概念

- **Ultralytics 版本现状**：目前官方主线模型家族是 **YOLO26**（`yolo26n.pt` … `yolo26x.pt`），YOLO11 仍受支持，**YOLO27 官方标注为"The models are not yet available"**，不要用 `yolo27n.pt` 这种文件名（[模型总览](https://docs.ultralytics.com/zh/models/)）。
- **两种数据来源**：公开数据集（COCO/VOC/VisDrone，或 Roboflow Universe 上别人导出的羽毛球/球拍数据集）省标注但**场景和你自己的球馆、机位不匹配**；自己录视频抽帧最贴合实际，代价是标注时间。羽毛球建议后者，且必须覆盖：白天/夜间灯光、近景/远景、左右半场、单打/双打。
- **YOLO txt 标注格式**：一行一个目标，`class_id cx cy w h`，后四个都是 **0–1 归一化**数字（相对整张图宽高），不是像素。真实例子——1920×1080 帧里一名球员框为 `(x1=640, y1=200, x2=800, y2=900)`：cx=(640+800)/2/1920=0.375，cy=(200+900)/2/1080=0.509，w=160/1920=0.083，h=700/1080=0.648，于是该行写成 `0 0.375 0.509 0.083 0.648`；类别后面用空格分隔（[数据集格式说明入口](https://docs.ultralytics.com/zh/datasets/detect/)）。
- **标注工具现状**（新手最省事 → 专业）：

  | 工具 | 形态 | 优劣 |
  | --- | --- | --- |
  | **X-AnyLabeling** | 本地桌面（Python） | 内置 SAM / Grounding 类模型做**半自动预标注**，导出 YOLO txt；对新手最省事。3.0 版本加入 Qwen3-VL、SAM3 与远程推理（[发布说明](https://mp.weixin.qq.com/s/hKy4oud3IECZTk1N3mMxmQ)、[仓库](https://github.com/CVHub520/X-AnyLabeling)） |
  | **Roboflow** | 网页 | 浏览器里标完一键导出 YOLO 格式，团队协作好；免费额度有限，数据在云上 |
  | **labelme** | 本地桌面 | 经典、教程最多，但只有多边形/矩形框，格式是 JSON，要写脚本转 YOLO，无 AI 辅助 |
  | **CVAT** | 自托管/在线 | 视频逐帧标注、多人审核最强；Docker 部署对新手偏重 |
  | **Label Studio** | 自托管/在线 | 支持文本/音频/图像多模态流水线，做纯目标检测比前两个绕 |

- **`data.yaml` 怎么写**（路径建议写绝对路径，避免 YAML 相对路径的坑）：

  ```yaml
  path: D:/datasets/badminton      # 数据集根目录
  train: images/train               # 相对 path
  val: images/val
  names:
    0: player
    1: racket
    2: shuttle
  ```

  目录结构必须是 `images/train` 与 `labels/train` **同名同目录层级**，图片 `a.jpg` 对应标签 `a.txt`，没有目标的图**可以没有 txt，但不能有空的错位文件**。
- **指标怎么读**：`Box(P, R, mAP50, mAP50-95)` 中 P=精确率（误检少）、R=召回率（漏检少）、**mAP50 是 IoU=0.5 下的均值，偏"检测得到"；mAP50-95 在 0.5–0.95 多阈值取平均，偏"框得准不准"**。羽毛球场景：可以先看 mAP50 是否 >0.8，再看 mAP50-95；shuttle 这类小目标 mAP50-95 通常明显低于 player（[性能指标指南](https://docs.ultralytics.com/zh/guides/yolo-performance-metrics/)）。

## 可执行的最短路径（真实命令）

```bash
# 1) 环境（Windows 建议独立 venv）
pip install ultralytics            # 会自动带上 torch 等依赖

# 2) 抽帧：每 0.5 秒一帧（2 fps），输出连续编号
ffmpeg -i raw.MP4 -vf fps=2 -q:v 2 frames/f_%05d.jpg

# 只要"画面变化明显"的帧（羽毛球动作快、静帧多时更省标注量）
ffmpeg -i raw.MP4 -vf "select='gt(scene,0.08)',fps=2" -vsync vfr -q:v 2 frames/s_%05d.jpg
```

抽完帧后**务必去重**（否则相邻帧几乎一样，等于白标）：先用 `opencv-python` 计算每帧 dHash 或用直方图/SSIM 与上一张比较，相似度超过阈值就丢弃；也可以用 `video-to-keyframes` 这类现成工具（[参考](https://github.com/davidj-brewster/video-to-keyframes)）。OpenCV 版核心是 `cv2.VideoCapture` 循环 `read()` 后按帧号取模保存，不要一天抽几万帧——羽毛球单类 300–500 张就能出可用效果。

```bash
# 3) 标注后按 8:2 划分，并用官方脚本核对标签（可选但强烈建议）
#    训练
yolo detect train model=yolo26n.pt data=D:/datasets/badminton/data.yaml \
  epochs=150 imgsz=640 batch=8 device=0 workers=4 \
  project=runs/badminton name=v1 patience=40

# 4) 验证与推理
yolo detect val model=runs/badminton/v1/weights/best.pt data=D:/datasets/badminton/data.yaml
yolo predict model=runs/badminton/v1/weights/best.pt source=test.mp4 save=True

# 5) 断点续训（关键：resume 必须指向 last.pt）
yolo detect train resume model=runs/badminton/v1/weights/last.pt
```

Windows 上如果写成 `.py` 脚本调用，必须在文件里加 `if __name__ == "__main__":`，否则会报多进程 `RuntimeError`（[官方训练文档](https://docs.ultralytics.com/zh/modes/train/)）。

**训练输出目录**（`runs/badminton/v1/`）里每个文件是什么：

| 文件 | 含义 |
| --- | --- |
| `weights/best.pt` | 验证指标**最优**那一轮的权重，部署/推理只用它 |
| `weights/last.pt` | 最后一个 epoch 的权重，含优化器状态，**resume 用它** |
| `results.csv` | 每轮 loss 与指标，判断过拟合/欠拟合的一手数据 |
| `confusion_matrix.png` / `confusion_matrix_normalized.png` | 混淆矩阵，看哪两类互相误判（如 racket 被判成 player） |
| `BoxPR_curve.png` / `BoxF1_curve.png` | PR 曲线与 F1 曲线，用来挑置信度阈值 |
| `labels.jpg` / `labels_correlogram.jpg` | 标注框分布，检查标注是否严重失衡 |
| `train_batch*.jpg` / `val_batch*_pred.jpg` | 增强后的训练样本与验证集预测可视化 |
| `args.yaml` | 本次全部超参，复现实验靠它 |

**过拟合 vs 欠拟合**（看 `results.csv`）：训练 loss 持续下降而验证 mAP 早早平台化甚至下滑=过拟合，办法是加数据、加强增强、`patience` 早停、减小模型（n/s）；训练 loss 和验证指标都很差且不降=欠拟合，办法是加轮数、检查标注是否正确、确认 `data.yaml` 的 names 与 txt 里的 class_id 对得上。

**数据增强参数**（默认值可用 `yolo checks` 或查看安装包内 `ultralytics/cfg/default.yaml` 核对你的版本）：常用的是 `mosaic`（四图拼接，对小目标友好）、`mixup`、`copy_paste`、`hsv_h/hsv_s/hsv_v`（色调/饱和度/亮度）、`degrees`、`translate`、`scale`、`fliplr`（左右翻转）、`close_mosaic`（最后 N 轮关掉 mosaic 稳定收敛）。**羽毛球注意**：`fliplr=0.5` 通常没问题，但如果你的任务是判断"左手/右手持拍"或球场方位有语义，翻转会破坏语义；`mosaic` 默认开启是双刃剑，小球容易被拼到画面边缘。

**导出命令与取舍**：

```bash
yolo export model=runs/badminton/v1/weights/best.pt format=onnx        # 通用、跨平台
yolo export model=... format=openvino                                   # Intel/CPU 部署，CPU 提速明显
yolo export model=... format=engine                                    # TensorRT，N 卡上最快
```

ONNX 兼容性最好、几乎到处能跑（但 NMS 常需自己写）；OpenVINO 面向 CPU/核显，适合没有独显的部署机；TensorRT `format=engine` 在 RTX 4060 上延迟最低，但**与 TensorRT/CUDA 版本强绑定，换机器要重新导出**，INT8 还需要用 `data=` 提供校准数据（[导出文档](https://docs.ultralytics.com/zh/modes/export/)）。

## 选型建议（RTX 4060 Laptop 8GB）

- **模型**：先 `yolo26n.pt`（也可用同尺寸的 `yolo11n.pt`）。8GB 显存不要一上手就 `s` 或 `m`，尤其羽毛球要检测小球时你会想提高分辨率，那更吃显存。
- **epochs**：100–150 起步，配 `patience=40` 早停；数据只有几百张时 300 轮以上大概率过拟合。
- **imgsz**：默认 `640`。**shuttle（羽毛球）在 640 下常常只有几个像素，是这类任务的最大瓶颈**——先 640 跑通流程，再试 `imgsz=960` 或 `1280`，同时把 `batch` 降到 4 或 2；显存不够时用 `batch=-1` 让 Ultralytics 自动按 60% 显存选 batch。
- **batch**：`640` 用 8–16（8GB 安全值是 8）；`960` 用 4；`1280` 用 2。batch 变小等效学习率降低，可把 `lr0` 略降或适当加轮数。
- **workers**：Windows 上设小一点（2–4），设太大会卡在数据加载甚至报共享内存错误。
- **竞技分析的后续工程**：检测只是第一步，真正的"运动表现"（跑动距离、击球点位置、回合时长）要靠 `yolo track` 得到 ID 后做轨迹统计，且必须做**单应性变换（球场四点→平面）**才能把像素坐标还原成米，这一步没有现成命令，需要单独写代码。

## 常见坑

1. **数据集划分泄漏**：把连续视频帧随机分到 train/val，验证集里全是训练集的"近邻帧"，mAP 虚高、上线就崩。正确做法是**按视频/比赛分组划分**，或每 10 帧抽 1 帧后划到 val。
2. **标签格式错**：忘记归一化、写成了 `x1 y1 x2 y2`、class_id 从 1 开始（YOLO 从 **0** 开始）、图片与 txt 文件名对不上。Ultralytics 训练时会给警告但常常不报错，只是学不出来。
3. **`data.yaml` 路径**：训练时报 "dataset not found"，八成是相对路径基准不对或 Windows 反斜杠转义，直接写正斜杠绝对路径最省事。
4. **改了数据集没删缓存**：`labels.cache` 残留会导致改动不生效，删掉 `labels/` 下的 `*.cache` 再训。
5. **`resume` 指向 `best.pt`**：必须用 `last.pt`；如果换了 `imgsz`/`data` 等参数，resume 不生效，应改成"载入 best.pt 再训"。
6. **过早追求 SOTA**：先 640 + n 模型跑通"数据→标注→训练→推理"全链路，再谈精度。第一个模型的常见结局是 mAP50 0.6–0.8，能跑通就有价值。
7. **显存爆了别硬扛**：报 CUDA out of memory 时依次降 `batch` → 降 `imgsz` → 关 `cache`，不要在同一张卡上叠加跑别的任务。

## 参考链接

- Ultralytics 训练文档（中文）：https://docs.ultralytics.com/zh/modes/train/
- Ultralytics 配置/超参数总表（中文）：https://docs.ultralytics.com/zh/usage/cfg/
- Ultralytics 目标检测数据集格式（中文）：https://docs.ultralytics.com/zh/datasets/detect/
- Ultralytics 性能指标解读（中文）：https://docs.ultralytics.com/zh/guides/yolo-performance-metrics/
- Ultralytics 导出格式与量化（中文）：https://docs.ultralytics.com/zh/modes/export/
- Ultralytics 模型家族总览：https://docs.ultralytics.com/zh/models/
- Ultralytics 超参数调优与增强搜索空间（中文）：https://docs.ultralytics.com/zh/guides/hyperparameter-tuning/
- X-AnyLabeling 仓库：https://github.com/CVHub520/X-AnyLabeling
- X-AnyLabeling 3.0 发布说明：https://mp.weixin.qq.com/s/hKy4oud3IECZTk1N3mMxmQ
- labelme 仓库：https://github.com/wkentaro/labelme
- CVAT 官网：https://www.cvat.ai/
- Label Studio 官网：https://labelstud.io/
- Roboflow：https://roboflow.com/
- video-to-keyframes（关键帧抽取工具）：https://github.com/davidj-brewster/video-to-keyframes
- ultralytics 版本发布记录（核对最新版本号）：https://github.com/ultralytics/ultralytics/releases

## 给 AI 编程助手的提示词

```
我在做羽毛球视频的 YOLO 目标检测（RTX 4060 Laptop 8GB）。请先确认我用的 ultralytics 版本和可用的模型文件名
（当前主线是 yolo26n.pt/yolo11n.pt，YOLO27 尚未发布，不要编造模型名），再给我命令。
数据方面：我会用 ffmpeg 抽帧，请帮我写去重脚本，并强调必须按视频/比赛分组划分 train/val，不能把连续帧随机分。
检查项：标签必须是 `class cx cy w h` 且四个坐标 0–1 归一化、class 从 0 开始、图片与 txt 同名、data.yaml 用绝对路径。
会踩的坑：Windows 要 if __name__ == "__main__"、改数据后删 labels.cache、resume 必须用 last.pt、显存不够先降 batch 再降 imgsz。
不要一次给我完整项目，先给能跑通的最小命令，等我贴报错再改。
```
