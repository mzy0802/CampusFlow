# 第三方软件与模型

本项目交接包包含源码及已有的 `models/yolo11n.pt`，未包含 Windows/macOS Python 二进制依赖、Node 模块或商业地图 SDK。依赖通过 npm/pip 从上游安装。

- Ultralytics 软件版本：8.4.177；本项目识别接口基于其公开 API。上游源码：https://github.com/ultralytics/ultralytics/tree/v8.4.177 。软件包附带的 AGPL-3.0 许可证原文随包保存在 `licenses/ULTRALYTICS-LICENSE.txt`。
- 模型：现有 YOLO11n 通用预训练模型。本项目先前安装脚本通过 Ultralytics 模型加载流程获取，当前仅复制现有权重，未修改权重、未训练校园专用模型。模型介绍：https://docs.ultralytics.com/models/yolo11/ 。权重及 Ultralytics 软件的使用、修改与再分发应遵循上游条款：https://www.ultralytics.com/license 。本说明不替代上游许可。
- Vue、Vite、Leaflet、FastAPI、Uvicorn、PyTorch、OpenCV 等依赖的许可和版权归各自上游所有；它们的二进制/源码依赖不在此交接包内，安装时随对应软件包取得。
- OSM 地图需保留版权署名并遵守瓦片政策：https://operations.osmfoundation.org/policies/tiles/ 。本包不包含瓦片离线缓存。

文件完整性可参照 `MANIFEST-SHA256.json`。交接包中的模型和代码是当前测试版本，不代表已经达到准确的密集停车计数效果。
