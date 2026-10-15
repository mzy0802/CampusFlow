# MacBook Air（Apple 芯片）交接说明

此包面向队友的 MacBook Air M5 / macOS arm64。包含校园停车地图前端、FastAPI 后端、7 个用户标注停车区、识别代码和现有 YOLO11n 模型文件。**未在 M5 真机验收**；在 Windows 上已完成前端构建、21 项数据/识别流程测试与单张真实照片推理。

## 1. 需要安装的软件

| 软件 | 建议配置 | 用途 |
|---|---|---|
| Python | 3.12，macOS universal2/arm64；也接受 3.13 | 后端和识别 |
| Node.js + npm | Node.js 22.12+，arm64；npm 随 Node 安装 | 前端安装与启动 |
| 终端 Terminal | macOS 自带，使用原生 Apple 芯片模式 | 执行脚本 |
| 浏览器 | Safari / Chrome 等现代浏览器 | 打开 Demo |
| VS Code | 可选 | 看代码、修改项目 |
| Docker Desktop | 可选，首次运行无需安装 | Docker Compose 容器方案 |

下载：[Python for macOS](https://www.python.org/downloads/macos/)、[Node.js](https://nodejs.org/en/download)。Python 明确选择 3.12 或 3.13，本交接脚本未针对 3.14/3.15 验证。Node 选择 Apple Silicon / ARM64，Python 安装包选择包含 Apple Silicon 的版本。

不需要 CUDA、NVIDIA 驱动、数据库、Google Maps Key 或 Windows Python 环境。默认原生 CPU 推理，先把流程跑通；MPS 作为可选项单独验证。

## 2. 解压后先安装依赖

解压 ZIP，进入 `campus-parking-demo` 文件夹。打开“终端”，输入 `cd `（后面留一个空格），将此文件夹拖到终端，再按回车。这样无需手工填写含空格的路径。

以下命令均在这个项目目录执行：

```bash
bash scripts/setup-mac.sh
```

脚本创建 Mac 自己的 `.venv`、安装 Python 推理依赖，并通过 `npm ci` 安装前端依赖。包内已附现有模型；模型文件丢失时脚本才尝试下载官方权重。依赖安装仍需要网络，PyTorch 下载可能较大。

如果暂时只看地图和网页，不安装识别依赖：

```bash
bash scripts/setup-mac.sh --map-only
```

之后想启用识别，重新执行不带 `--map-only` 的安装命令即可。安装失败时先看最后的错误，修复网络或软件版本后可重复运行，无需删除整个项目。

## 3. 启动（两个终端窗口）

第一个窗口，在项目目录运行后端：

```bash
bash scripts/start-backend-mac.sh
```

第二个终端窗口也先进入同一个项目目录，再运行前端：

```bash
bash scripts/start-frontend-mac.sh
```

打开：

- 页面：[http://127.0.0.1:5173/](http://127.0.0.1:5173/)
- 后端文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 后端健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- 识别就绪检查：[http://127.0.0.1:8000/api/vision/health](http://127.0.0.1:8000/api/vision/health)

两个终端都要保持运行。停止服务按各自窗口的 Ctrl+C，重启再执行对应启动命令。这个包默认只允许这台电脑本机访问。

## 4. 页面上可以看什么

- 全屏 OSM 地图，7 个导入停车区，搜索与点击定位。
- 模拟停车空位，明确标注“模拟”。
- “人车识别”入口上传照片/视频，显示任务进度、检测框、人数、自行车、两轮车候选分项和总数。
- 拥挤度允许超过 100%；例如 120 个候选 / 100 个车位 = 120%。
- 道路、公交、路线功能目前为预留入口。

文件限制：图片或视频不超过 100 MB，视频最长 120 秒，视频按间隔抽帧，不是跨帧去重后的通行量。

## 5. 识别能力的实际限制

当前模型是 **YOLO11n 通用预训练模型**，未针对校园密集停车数据训练。motorcycle 类只作为“电动两轮车 / 摩托车候选”，尚不能可靠区分这两种车型。远处、遮挡严重的车辆会漏检。

已在一张用户照片上复现旧版只检出 1 辆；修正为整图 + 重叠切片后检出 20 个两轮车候选，仍明显低于照片中的真实车辆数。**这个包用于看界面和验证处理流程，尚不能作为准确停车数量或空闲判断依据。** 具体见 `DETECTION-REVIEW.md`。没有把用户照片、上传历史或带人物的识别预览放入交接包。

## 6. Apple GPU（MPS，可选）

先保持默认 CPU 跑通。检查 Mac 的 PyTorch 是否支持 MPS：

```bash
.venv/bin/python scripts/check-mac.py
```

当显示 `MPS available: True` 时，可以先停止后端，再尝试：

```bash
DETECTION_DEVICE=mps bash scripts/start-backend-mac.sh
```

本项目没有在 M5 上验证推理算子兼容性和性能，不保证 MPS 必然更快。出现 MPS 错误时 Ctrl+C，重新用默认启动命令回到 CPU。原生 macOS 的 MPS 由 [PyTorch 官方文档](https://docs.pytorch.org/docs/2.14/notes/mps.html)说明；Docker 内不按原生 MPS 方案运行。

## 7. 依赖与项目结构

前端（版本在 `frontend/package.json` 和锁文件中）：Vue 3.5.44、Vite 8.3.4、Leaflet 1.9.4、Vue Vite 插件 6.0.10。前端应使用 `npm ci` 按锁文件安装。

后端：FastAPI 0.115.12、Uvicorn 0.34.2；识别：Ultralytics 8.4.177、OpenCV 4.x，PyTorch/torchvision 等由 pip 按 macOS arm64 解析兼容版本。清单位于 `backend/requirements-mac.txt`，不是 Windows 的整套已安装二进制环境。

```text
START-HERE-MAC.md             本说明
scripts/setup-mac.sh         安装本机环境
scripts/start-backend-mac.sh 启动后端
scripts/start-frontend-mac.sh 启动前端
scripts/check-mac.py         环境与 MPS 检查
frontend/                    Vue 前端源码及 npm 锁文件
backend/app/                 FastAPI 与检测模块
backend/tests/               流程与数据测试
data/                        用户标注区域及原虚构示例
models/yolo11n.pt            当前模型文件
THIRD-PARTY-NOTICES.md        模型来源与许可说明
MANIFEST-SHA256.json          包内文件校验值
```

测试可选：`.venv/bin/python -m pip install -r backend/requirements-dev.txt` 后运行 `.venv/bin/python -m pytest`；前端构建 `cd frontend && npm run build`。Mac 脚本、MPS 和容器运行尚未做真机验收，遇错请发送终端最后的报错及 `scripts/check-mac.py` 输出。

常见问题：

- `command not found`：安装指定 Python / Node 后重新打开终端。
- 架构显示 `x86_64`：检查终端是否经 Rosetta 运行，以及 Python/Node 是否装了 Intel 版本。
- `Address already in use` / `Port 5173 is already in use`：先在原来的对应服务窗口 Ctrl+C，不要重复开同一个服务。
- 地图有区域没有底图：OSM 瓦片网络可能不通，区域展示不依赖瓦片。
- 引擎未就绪：确认没有只安装 `--map-only`，再检查 `models/yolo11n.pt`，重启后端并刷新页面。
- 不要将 Windows 的 `.vision-deps`、`venv`、`node_modules` 或绝对路径复制到 Mac。
