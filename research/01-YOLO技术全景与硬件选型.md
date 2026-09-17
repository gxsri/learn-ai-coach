# YOLO 技术全景与硬件选型（羽毛球视频分析 · RTX 4060 Laptop 8GB）

> 核对时间：PyPI 上 `ultralytics` 最新版 **8.4.153**；官方最新模型 **YOLO26**（2026-01 发布）；**YOLO27 尚未发布**。以下版本号、模型名、命令均可点链接复核。

## 一句话结论

做羽毛球视频分析，**从 `yolo11n-pose.pt` 起步**——YOLO11 版本、姿态估计任务、n 尺寸。先用官方 COCO 17 点权重跑通"读视频 → 出关键点 → 算关节角度"这条链路，再考虑标注微调。不要从 detect 起步，不要用 YOLO12，不要一上来就上 m/l/x。

## 核心概念

### 版本序列：哪些是官方的

| 模型 | 归属 |
|---|---|
| YOLOv5 / YOLOv8 / **YOLO11** / **YOLO26** | Ultralytics 自研（官方主线）|
| YOLOv6 美团 · YOLOv7、YOLOv9 中研院 Wang · YOLOv10 清华 · YOLO12 Buffalo+国科大 · YOLO-NAS Deci AI | 第三方论文，被集成进同一个库 |

YOLO11（2024-09-10）被官方标注为 "Current stable release and the recommended choice for all use cases"，即**当前最稳的选择**，资料最多、报错最好搜。YOLO26（2026-01）是最新 SOTA，主打端到端无 NMS。

**YOLO12 官方明确警告**是社区模型，"may exhibit training instability, elevated memory consumption"，且**只发布了 detect 预训练权重**，pose/seg/cls/obb 的 `.pt` 全都没有，必须从 `.yaml` 从零训练，官方原话是建议改用 YOLO11 或 YOLO26。对不会调试的人直接排除。

### 许可证：AGPL-3.0 的红线

库与官方权重均为 AGPL-3.0。**免费**：个人学习、学术研究、课程作业、完全开源项目。**必须买 Enterprise 授权**：任何商业产品/服务、闭源软件、公司内部工具、SaaS/API、嵌入硬件设备，**以及"用自己微调出来的模型商用"**。判据是"是否愿意把整个项目开源"；AGPL 覆盖网络服务，所以放服务器上不发给客户也躲不掉。自己学、给教练看——免费；**卖课、卖 App、卖给球馆——要谈授权**。

### 五种任务的区别

| 任务 | 后缀 | 输出 | 羽毛球相关度 |
|---|---|---|---|
| 检测 | 无 | 矩形框 + 类别 | 低：只有框，算不出动作 |
| 实例分割 | `-seg` | 像素级掩膜 | 低：标注成本极高 |
| **姿态** | **`-pose`** | **人体 17 关键点 (x, y, 可见性)** | **最高：核心任务** |
| 分类 | `-cls` | 整图单一标签 | 低：无法定位帧内的人 |
| 旋转框 | `-obb` | 带角度的旋转框 | 低：人形不需旋转框 |

17 点索引固定：0 鼻、1-2 眼、3-4 耳、5-6 肩、7-8 肘、9-10 腕、11-12 髋、13-14 膝、15-16 踝——**肘、肩、腕、髋、膝正好覆盖挥拍角度、蹬转、重心转移**。

### 各尺寸参数量（官方 COCO 数据）

YOLO11 检测：n 2.6M / 6.5GFLOPs / mAP 39.5；s 9.4M / 21.6 / 47.0；m 20.1M / 68.1 / 51.5；l 25.3M / 87.2 / 53.4；x 56.9M / 195.3 / 54.7。
YOLO11-pose：n 2.9M / 7.5GFLOPs / mAP 50.0，m 20.9M / 64.9；YOLO26n-pose 2.9M / 57.2。

**官方只公布 CPU ONNX 与 T4 TensorRT 耗时，没有笔记本显卡数据**——任何"4060 跑 XX FPS"的表格都不如自己实测。

### 8GB 显存上的可行规模

4060 Laptop 是 Ada 架构、3072 CUDA 核心、8GB GDDR6。**8GB 是天花板，不是算力**：推理 n/s 宽裕、m 可行；训练 n/s 舒服，m 在 `imgsz=640` 下需把 batch 压到 4–8 且可能仍紧，**l/x 不现实**（训练还要存梯度与优化器状态）。内置 `batch=-1` 会按约 60% 显存自动找 batch，单卡首次 OOM 还会自动减半重试最多 3 次——**先别手调，先让它探**。

## 可执行的最短路径

```bash
pip install ultralytics                      # Python>=3.8，自带 PyTorch
pip install ultralytics[export]              # 需要导出 ONNX/TensorRT 时
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
yolo pose predict model=yolo11n-pose.pt source=my_match.mp4 save=True
yolo benchmark model=yolo11n-pose.pt data=coco8-pose.yaml imgsz=640 device=0
yolo pose train data=my_badminton.yaml model=yolo11n-pose.pt epochs=100 imgsz=640 batch=-1 device=0
yolo track model=yolo11n-pose.pt source=my_match.mp4 tracker=ocsort.yaml save=True
```

```python
from ultralytics import YOLO

model = YOLO("yolo11n-pose.pt")
for r in model.track(source="my_match.mp4", stream=True, persist=True, tracker="ocsort.yaml"):
    xy, ids = r.keypoints.xy, r.boxes.id   # 17 个关键点 + 跟踪 ID
```

`stream=True` 逐帧产出，长视频不爆内存；`persist=True` 保持跨帧 ID。官方跟踪器选型指引写明：非线性运动（体育、舞蹈、急停变向）且不想要重识别开销 → **OC-SORT**。另有 `botsort.yaml` / `bytetrack.yaml` / `deepocsort.yaml` / `fasttrack.yaml` / `tracktrack.yaml` 可选。

## 选型建议（针对 8GB 显存）

**明确回答：姿态估计任务 + n 尺寸，即 `yolo11n-pose.pt`。**

1. **任务选 pose**：只有关键点能算出角度、轨迹、重心；detect 只给框，classify 只给标签，obb 解决的是航拍/文字的旋转问题，seg 标注成本对个人项目不划算。
2. **尺寸选 n**：2.9M 参数、7.5 GFLOPs，8GB 训练推理都宽裕；瓶颈是**数据准备和调试**，不是精度。跑通后升 `s` 通常还有提升，`m` 在 8GB 训练会勉强。
3. **版本选 YOLO11**：官方认证稳定版，生态资料最多；YOLO26 更强但资料少；YOLO12 无 pose 权重，排除。
4. **别急着自己训练**：先用官方 COCO 权重直接预测。真正要解决的多是"远处球员漏检"，手段是**提高推理 `imgsz`** 或**先裁剪球场区域再送入**，而不是换更大模型。

## 常见坑

- **Windows 训练脚本必须加 `if __name__ == "__main__":`**，否则报 RuntimeError（官方明示）。
- **Windows 多卡训练是坏的**：`torch>=2.4` 官方 Windows 轮子未编 libuv，报 `use_libuv was requested but PyTorch was built without libuv support`。单卡 `device=0` 正常，多卡请用 WSL2。
- **网上"YOLOv11""YOLO13"都是错的**：官方没有 v11，正确写法是 YOLO11；**YOLO13 不存在**，提它的资料是编的。
- `batch` 默认 16，m/l 在 8GB 上直接 OOM，用 `batch=-1` 或先降到 4。
- 球员交叉时**跟踪 ID 会漂**，快速球类场景尤其明显；用 `ocsort.yaml`，且 `persist=True` 只适用于同一段连续视频。
- 视频推理慢，先怀疑视频解码与数据加载，而不是模型。

## 参考链接

- [Ultralytics YOLO11 官方文档（各尺寸参数表）](https://docs.ultralytics.com/models/yolo11/)
- [Ultralytics YOLO26 官方文档](https://docs.ultralytics.com/models/yolo26/)
- [Ultralytics YOLO12 官方文档（社区模型警告）](https://docs.ultralytics.com/models/yolo12/)
- [Ultralytics 姿态估计任务文档（17 点索引）](https://docs.ultralytics.com/tasks/pose/)
- [Ultralytics 训练模式文档（batch 自动 / OOM 重试 / Windows 注意）](https://docs.ultralytics.com/modes/train/)
- [Ultralytics 跟踪模式文档（六种跟踪器选型）](https://docs.ultralytics.com/modes/track/)
- [Ultralytics 基准测试模式文档](https://docs.ultralytics.com/modes/benchmark/)
- [Ultralytics 许可证与商用边界](https://www.ultralytics.com/license)
- [PyPI: ultralytics（版本号与 AGPL-3.0 声明）](https://pypi.org/project/ultralytics/)
- [NVIDIA GeForce RTX 4060 Laptop GPU 规格](https://www.notebookcheck.net/NVIDIA-GeForce-RTX-4060-Laptop-GPU-Benchmarks-and-Specs.675692.0.html)

## 给 AI 编程助手的提示词

1. **把任务说死**："用 `ultralytics` 做羽毛球视频姿态分析，模型固定 `yolo11n-pose.pt`（YOLO11 + pose + n 尺寸），不要擅自换成 YOLOv8 / YOLO12 / 其他尺寸。"
2. **要求先验证再写**："写代码前确认模型文件名与参数名在官方文档里真实存在并给出链接，不要凭记忆编造参数。"
3. **交代环境**："Windows + RTX 4060 Laptop 8GB + Python 3.10，`ultralytics 8.4.x`。训练必须带 `if __name__ == '__main__':`；batch 用 `batch=-1` 让我自己看显存，不要假设我有 24GB 显存。"
4. **要它检查三件事**：① 先跑 `torch.cuda.is_available()`；② 视频处理必须 `stream=True`，不要一次把所有帧读进内存；③ 跟踪用 `persist=True` + `tracker="ocsort.yaml"`，并提醒我球员交叉时 ID 会漂。
5. **提醒许可证**："先说明这段代码若用于商用（卖课 / 卖 App）会触发 AGPL-3.0 的哪些义务。"
