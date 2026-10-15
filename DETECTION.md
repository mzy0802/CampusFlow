# 人员与两轮车识别：测试版

> 更新：已加入 motorcycle 候选类、两轮车合计及整图 + 重叠切片。默认置信度改为 0.20。motorcycle 暂时只能标为电动两轮车/摩托车候选，不能可靠区分车型。密集停车照片仍有严重漏检，参见 [实测复核](DETECTION-REVIEW.md)。所有结果需结合检测框人工核验。

检测在 FastAPI 后端执行，前端只负责上传、查询任务和显示后端返回的数据。采用本地 Ultralytics YOLO11n 检测模型，检测 `person`、`bicycle`、`motorcycle` 三类，后者仅作为电动两轮车/摩托车候选。当前是上传测试入口；尚未接入摄像头、目标跟踪或跨画面识别。

## 在当前电脑启用

先在原后端 PowerShell 窗口按 Ctrl+C，然后在项目目录执行（使用系统 Python）：

```powershell
cd "C:\Users\mzy\Documents\Codex\2026-10-15\referenced-chatgpt-conversation-this-is-an\outputs\campus-parking-demo"
python install_vision.py
python run_backend.py
```

安装脚本将依赖装入项目内 `.vision-deps`，下载官方权重到 `models/yolo11n.pt`。首次安装包括 PyTorch，下载较大，需要网络和数分钟时间。脚本成功后再启动后端。启动脚本也兼容本项目先前的 `work/venv` 依赖路径，不必再手工设置 PYTHONPATH。

如果系统命令 `python` 不可用，这台电脑可用的解释器路径是 `C:\Users\mzy\AppData\Local\Programs\Python\Python313\python.exe`。不要使用之前临时虚拟环境的 Python 启动器。

保持前端开发服务运行，打开现有的 http://127.0.0.1:5174/ ，刷新页面，点击左侧“人车识别”，必要时点击“重新检查识别引擎”。新启动前端的默认地址仍是 http://localhost:5173 。

模型缺失或依赖缺失时，健康接口返回 `ready=false`，前端禁用开始按钮，后端上传接口返回 503。请求期间不自动下载模型，也不会用随机数代替识别结果。

## 测试方法

1. 选择照片或视频；选择关联停车区，或使用“独立测试”。
2. 核对两轮车总容量。关联区域时预填 GeoJSON 容量，允许针对测试调整。人员容量默认 50，只是可编辑的参考值，不是现场核定容量。
3. 可调整置信度阈值（默认 0.20）及视频抽帧间隔（默认 1 秒）。
4. 点击“开始识别”。等待上传、排队、识别。前端每 1.5 秒查询任务。
5. 查看人数、自行车数、各自拥挤度、检测框图片与视频采样表。成功的关联任务会同步到地图的区域卡片和标记，标明“上传识别 · 非实时”。

照片应尽量只覆盖目标停车区；当前没有相机视角 ROI 标定，不能把一张包含多个区域的照片自动分配到各停车区。GeoJSON 经纬度多边形不能直接当作摄像头画面的像素 ROI。

## 数量和拥挤度口径

`拥挤度 = 当前采样帧识别数量 / 配置容量 × 100%`，不截断百分比。自行车与电动两轮车候选分开显示，停车拥挤度按同帧两轮车候选总数计算；人数另算，人数与车辆数不相加。

| 数量 / 容量 | 拥挤度 | 等级 |
|---|---|---|
| 30 / 100 | 30% | 通畅（低于 50%） |
| 60 / 100 | 60% | 适中（50% 起） |
| 90 / 100 | 90% | 拥挤（80% 起） |
| 100 / 100 | 100% | 拥挤（达到容量） |
| 120 / 100 | 120% | 超出容量（大于 100%） |

视频逐采样帧计数，不把各帧数量相加。结果同时返回最后一个采样帧、采样峰值和平均数量。地图使用最后采样帧；峰值只表示抽到的画面中的最高数量，不保证是视频所有帧的峰值。无跟踪时不能将它描述为“视频中共经过多少独立行人”。

## 文件与处理限制

- 图片：JPG/JPEG、PNG、WebP；解码后最多 4000 万像素。
- 视频：MP4、MOV、AVI、WebM；具体编码需 OpenCV 能解码；最长 120 秒，分辨率不超过 1600 万像素。
- 文件：最大 100 MB，后端流式写入并限制字节数，Nginx 同步设置 100 MB 限制。
- 一个进程同时推理 1 个任务，含正在上传/运行的最多 4 个在途任务；满队列返回 429。
- 最多 240 个采样帧，每次模型推理最多 1000 个检测框（切片后合并）。超密集场景需重新评估模型及限制。
- 图像损坏、不可解码、模型加载失败等会返回失败任务，不生成假结果。

任务状态和结果存于 `backend/storage/<任务ID>/job.json`，保留最后一个采样帧的带框预览 `preview.jpg`。输入文件在处理完成或失败后删除；结果与预览不会自动过期，适合本机开发。进程重启会将未完成任务标为失败，原有已完成结果仍可查询。需要清理时，先停止后端，再备份或删除 `backend/storage` 中的测试任务目录。

## 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/vision/health` | 环境/权重就绪情况、上传限制 |
| POST | `/api/vision/jobs` | 上传文件，立即返回 202 和任务 ID |
| GET | `/api/vision/jobs/{id}` | 进度、状态、错误、结果及逐帧框坐标 |
| GET | `/api/vision/jobs/{id}/preview` | 最后一帧带框 JPEG |
| GET | `/api/vision/observations` | 每个关联区域最近提交并已完成的识别结果 |

上传接口使用原始文件作为 HTTP 请求体，非 multipart，查询参数为 `filename`、可选 `area_id`、`bicycle_capacity`、`person_capacity`、`confidence`、`interval_seconds`。不信任文件名作为磁盘路径，磁盘目录使用后端生成的 UUID。

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/vision/jobs?filename=test.jpg&area_id=X4001&bicycle_capacity=100&person_capacity=50" -H "Content-Type: image/jpeg" --data-binary "@test.jpg"
```

检测框的 `box` 为归一化 `[x1,y1,x2,y2]`，原点为画面左上角。`bicycle.latest`、`motorcycle.latest`、`two_wheeler.latest` 和 `person.latest` 均返回 `count/capacity/percent/level`；`peak` 为该类别采样峰值，`mean_count` 为平均数量。JSON 数据由后端计算，前端只负责格式化与颜色显示。

停车模拟接口继续独立工作。上传识别结果不会改写模拟空位，避免把测试图片当成现场实时传感器。

## Docker

默认 `compose.yaml` 使用轻量后端，停车页面正常运行，识别模块显示未安装。启用识别镜像时，先准备 `models/yolo11n.pt`，再执行：

```powershell
docker compose -f compose.yaml -f compose.vision.yaml up --build -d
```

也可以先构建识别镜像，然后在一次性容器内下载权重（将模型挂载临时改为可写）：

```powershell
docker compose -f compose.yaml -f compose.vision.yaml build backend
docker compose -f compose.yaml -f compose.vision.yaml run --rm --volume "./models:/app/models" backend python setup_vision.py
docker compose -f compose.yaml -f compose.vision.yaml up -d
```

Compose 将模型只读挂载至 `/app/models`，结果写入 `vision-storage` 卷。镜像默认 CPU 推理；当前版本按单进程设计，请勿增加 Uvicorn workers 或多个共享同一存储的副本。

## 模型与下一步

通用预训练模型可作为功能联调起点，校园俯视、小目标、遮挡及密集自行车需要现场样本评估和微调；当前没有测得或承诺校园识别准确率。未来摄像头模块可以复用后端引擎与拥挤度计算，将测试上传替换为持续帧输入，再增加视角 ROI、跟踪和结果过期策略。

参考 [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/)、[推理接口](https://docs.ultralytics.com/modes/predict/)。Ultralytics 软件及权重的使用遵循其 [许可证说明](https://www.ultralytics.com/license)。
