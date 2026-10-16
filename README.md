# CampusFlow · 校园导航与标注平台

**Apple 芯片 MacBook 接收者请先看 [Mac 安装启动说明](START-HERE-MAC.md)。** 原生 Mac 安装使用 `scripts/setup-mac.sh`，不要使用下方 Windows 临时环境路径。

Vue 3 + Vite + Leaflet / OSM，FastAPI，Docker Compose。用于长安大学渭水校区校园停车与出行项目的开发演示。

当前网页识别默认使用 **Qwen3-VL-Plus**，由后端调用百炼。支持照片、最多12帧的视频抽样计数，以及1～6个原尺寸视角联合估算。显示自行车、电动两轮车、类型不确定车辆及总数；容载率可超过100%。预览为原图，不生成检测框。关联地图停车区与可停车范围后，可联合估算区内及周边违停，违停已包含在该区总数中。

将 `.env.example` 复制为 `.env`，填写自己的百炼密钥和对应地域/工作空间的接口地址。密钥只在后端读取，不提交 Git。安装及限制见 [Qwen 识别说明](docs/QWEN-VISION.md)。旧 YOLO 文档和脚本保留供实验参考，不是当前网页默认引擎。

**当前默认加载用户上传的33个停车区：原有7个、明远17个、修远新标注9个。** 合并数据为 `data/parking.imported.geojson`；三份原文件分别保存在 `data/parking.upload.original.geojson`、`data/parking.mingyuan.original.geojson` 和 `data/parking.xiuyuan.original.geojson`。明远容量合计640；修远新文件容量合计1779，按文件提供的面积估算容量使用。修远新区域名称增加“修远”前缀，原名称存于original_name。容量、ID、经纬度均来自用户文件，不覆盖旧区域；原文件中大小写不同的ID分别保留。已有数据库启动时各批次只追加一次，保留现有修改；不会在以后重启时恢复用户删除的区域。应用状态优先使用最近Qwen上传估算，否则明确显示模拟数据及时间。独立虚构示例不参与当前展示。

原修远区域导入将7条带ID、名称的LineString按原坐标顺序闭合成Polygon，将`capility`转为`capacity`；2个无属性的单点线条仅保留在原文件。明远区域导入将`space`转为`capacity`，闭合WM1002的LineString，移除两处连续重复顶点；所有经纬度沿用用户文件，未补造地理点位。

重启当前电脑的后端：在旧后端终端按 Ctrl+C，进入本项目目录执行 `python run_backend.py`，再刷新页面。首次安装后端依赖执行 `python -m pip install -r backend/requirements.txt`，并配置百炼密钥。

## 路网编辑与停车联合推荐

点击“路线”打开工作台，可录入道路和入口、保存 SQLite、导入导出 JSON，计算最快或少走路方案。全新或未编辑的空白校园路网会自动载入 OSM 公开道路（已按负责人要求纳入规划），独立虚构示例仍可直接演示。公开数据来源与限制见 [道路说明](docs/OSM-ROADS.md)。见 [验收说明](docs/MORNING-ACCEPTANCE.md) 和 [LLM 接口交接](docs/ROUTING-API.md)。

## 应用与内部工具分开使用

- 应用页 `/`：搜索栏优先，旁边按钮展开起终点导航；停车推荐、路线和耗时、百炼AI、停车与容载率图层开关、公交图层。
- 调试页 `/debug`：照片/视频可停范围与地图区关联、多角度联合识别、地图停车区编辑、公交线路/停站/车辆编辑、路网编辑。两页共用同一服务。

新功能操作和接口见 [停车、公交与多角度说明](docs/PARKING-TRANSIT-MULTIVIEW.md)。
- [给标注同学的操作交接](docs/TEAM-ANNOTATION-HANDOFF.html)（可双击打开或打印），[文字版](docs/TEAM-ANNOTATION-HANDOFF.md)。
- [新增接口与数据规则](docs/NAVIGATION-ANNOTATION-API.md)。道路已按负责人要求纳入规划；服务道路不叠加显示，未删除其路网连接。

## Docker 一键启动

安装并启动 Docker Desktop（Linux 容器，Compose v2），在本目录运行：

```sh
docker compose up --build -d
```

- 页面： http://localhost:8080
- 接口文档： http://localhost:8000/docs
- 健康检查： http://localhost:8000/api/health
- 查看日志：`docker compose logs -f`
- 停止：`docker compose down`

首次构建需要网络下载镜像和依赖；OSM 瓦片需要浏览器联网。OSM 底图无需 API Key；Qwen 识别需要百炼密钥。前端通过 Nginx 将 `/api` 转发给后端，浏览器不访问容器内部主机名。端口仅绑定本机。

## 本地开发

需要 Node.js 22.12+（建议 22 LTS）、npm、Python 3.12+。以下为 PowerShell 示例，均从项目根目录开始。

终端一：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
python run_backend.py
```

终端二：

```powershell
cd frontend
npm ci
npm run dev
```

访问 http://localhost:5173 。Vite 已代理 `/api` 到本机 8000 端口。`npm run preview` 仅预览静态构建，不提供后端代理；联调请使用开发服务器或 Compose。

## 文件结构

```text
data/parking.imported.geojson 当前默认区域（用户上传，待核验）
data/parking.upload.original.geojson 上传原件
data/parking.example.geojson  原虚构示例（未启用）
backend/app/data.py           读取与基础校验
backend/app/parking.py        区域及模拟状态 API
backend/app/mobility.py       道路、公交、路径规划预留
backend/app/vision.py         识别任务与上传 API
backend/app/vision_engine.py  本地 YOLO 图片/视频推理
backend/app/vision_service.py 任务队列、进度和持久化
backend/app/vision_metrics.py 人车数量与拥挤度口径
backend/app/main.py           应用入口和启动校验
backend/tests/test_api.py     接口与数据约束测试
frontend/src/App.vue          地图、区域卡片及模块入口
frontend/src/api.js           同源 API 请求
frontend/src/style.css        页面与移动端布局
frontend/nginx.conf          容器内前端代理
compose.yaml                 服务编排
compose.vision.yaml          启用识别的 CPU 容器配置
install_vision.py            本机安装依赖与官方模型
run_backend.py               本机后端启动入口
```

## 区域数据交接

停车区边界与停车状态分开：GeoJSON 只存边界、名称和配置容量，**无需填写当前停车量**。占用数由模拟状态接口提供。

1. 队友交付经过现场或可靠资料核验的 GeoJSON，放到 `data/parking.verified.geojson`。
2. 格式为 `FeatureCollection`，顶层增加 `"is_example": false`；每个 Feature 是 Polygon，`properties` 必须有唯一字符串 `id`、`name`、正整数 `capacity`。容量也需核验，未核验时应继续使用示例标记。建议另加 `source`、`verified_at`、`verified_by` 作为交接记录。
3. 使用 WGS84 经纬度，坐标顺序 `[经度, 纬度]`，每个环至少四个坐标且首尾闭合。不要直接使用 GCJ-02/BD-09 数据。当前骨架仅支持 Polygon；多个独立区域可拆成多个 Feature。
4. 修改 `compose.yaml` 中 `PARKING_DATA_FILE` 为 `/app/data/parking.verified.geojson`，运行 `docker compose up -d --force-recreate backend`。本地开发则设置环境变量 `$env:PARKING_DATA_FILE = (Resolve-Path data/parking.verified.geojson).Path` 后重启后端。
5. 刷新页面，地图自动按区域范围定位；可打开 OSM 底图检查配准。顶层 `is_example` 只用于标记来源，程序无法证明真实性。

后端启动时加载文件，修改文件后需要重启后端。重复 ID、非法容量、未闭合环、越界坐标等基础错误会阻止启动；尚未实现自相交等完整拓扑校验。

## API 约定

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/health` | 服务健康状态 |
| GET | `/api/parking/areas` | 读取文件得到的 GeoJSON |
| GET | `/api/parking/status` | 所有区域模拟状态 |
| GET | `/api/parking/{id}/status` | 单区状态；未知 ID 返回 404 |
| GET | `/api/roads` | 空 FeatureCollection，`not_configured` |
| GET | `/api/transit` | 空站点和线路，`not_configured` |
| POST | `/api/routing/plan` | 合法请求返回 501；非法坐标返回 422 |

状态响应包含 `mode: simulated`、`is_example`、UTC `updated_at`、`refresh_seconds: 15` 和 `items`。每项包含 `id/capacity/occupied/available/state`。按区域 ID 和 UTC 15 秒窗口生成固定伪随机值，重复请求不累计占用，始终满足 `occupied + available = capacity`。这只是界面联调模拟，不是预测模型。占用率 100% 为 `full`，80% 起为 `busy`，其余为 `available`。

路径请求示例（仅演示字段，不代表校园位置）：

```json
{
  "origin": {"longitude": 0, "latitude": 0},
  "destination": {"longitude": 0.001, "latitude": 0.001}
}
```

道路模块以后读取核验路网；公交模块以后接站点、线路和时刻；路径模块以后接自建路网算法或路由服务。当前不画虚构道路、公交站点或直线“导航路线”。

## 验证

```powershell
.\.venv\Scripts\python -m pytest backend/tests -q
cd frontend
npm run build
```

项目根目录的 `pytest.ini` 已配置模块路径。手工验收：卡片与多边形联动、15 秒刷新、断开后端显示失败提示、OSM 不可用时仍显示区域、三个预留入口显示未接入、窄屏布局可用。

## OSM 与后续接入

Leaflet 使用标准 OSM 瓦片 URL，开启时保留地图右下角版权署名；不做离线预取或批量下载。演示阶段按需加载，正式部署请根据流量选择合适的瓦片服务并遵守服务条款。参考 [OSM 瓦片使用政策](https://operations.osmfoundation.org/policies/tiles/)、[Leaflet GeoJSON](https://leafletjs.com/examples/geojson/)、[Vite 文档](https://vite.dev/guide/)、[FastAPI 容器部署](https://fastapi.tiangolo.com/deployment/docker/)。

项目暂不包含账户、数据库、传感器接入、真实路网和生产监控。建议下一步先完成真实边界与容量核验，再逐个替换模拟数据服务。
