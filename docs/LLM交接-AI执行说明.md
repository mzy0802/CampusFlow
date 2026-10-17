> 2026-10-17 新需求以 [AI 导航接口交接](AI-NAVIGATION-HANDOFF.md) 为准：聊天解析起终点，同图早高峰时刻导航，指路模型独立配置由同学选择，不复用视觉 Qwen。

# LLM 接入执行说明：交给 WorkBuddy / DeepSeek

更新：2026-10-16；代码基线 ac7dcd3。本版完整替代旧交接。路径均相对 CampusFlow 项目根目录。先读取当前源码和适用的 AGENTS.md；有差异以源码为准并报告。

## 目标与范围

扩展现有 AI 按钮，实现自然语言出行查询、经过校验的只读业务工具调用、多轮条件合并、真实路线及停车推荐在地图显示。WorkBuddy 的 DeepSeek 是开发助手；识图固定使用 Qwen；本次出行助手的模型和服务商由负责接入的同学选择，不限定百炼或 Qwen。不要索取或提交真实密钥。

保留 `/` 应用与 `/debug` 内部工具两页；应用已有搜索、导航、AI 入口。不要重建项目、另造地图、迁移数据库、重新接入视觉或修改停车区坐标/ID。没有任何人工复核提示需求，不添加“待核验/需人工复核/请现场确认”等交互。

## 必须先读的源码

|文件|作用|
|---|---|
|`frontend/src/main.js`|应用/调试页面入口分流|
|`frontend/src/NavigationApp.vue`|搜索、起终点、导航、AI 按钮、停车推荐、地图绘制|
|`frontend/src/App.vue`|内部调试工具，不是用户助手主界面|
|`backend/app/main.py`|FastAPI 挂载、Store/视觉服务初始化|
|`backend/app/navigation.py`|地点、道路图路线、停车联合推荐、简单 AI 选择|
|`backend/app/parking_state.py`|`area_states(request)`：融合停车状态和容量|
|`backend/app/traffic_store.py`|SQLite 存储及当前路网/停车配置|
|`backend/app/qwen_vision.py`|现有百炼配置读取及视觉调用，保持兼容|
|`backend/app/transit.py`|公交线路/站点/车辆配置与人数观测|
|`backend/app/area_surveys.py`|多视角识别；本次仅理解统计口径，不作为助手写工具|
|`compose.yaml`、`.env.example`|部署和现有配置|

补充协议见 `docs/NAVIGATION-ANNOTATION-API.md`、`docs/PARKING-TRANSIT-MULTIVIEW.md`。SQLite 默认存储在 `backend/storage/traffic.sqlite3`；用户编辑后的数据库配置优先于初始 JSON。不能重新初始化数据库来完成接入。

## 当前能力，不要按旧文档开发

1. 道路与地点已经配置，可计算步行、骑行路线。现有道路按负责人要求可参与规划。服务道路只在默认图层隐藏，不代表不可通行。
2. 当前 41 个停车区，包含明远、鸿远和修远。区域 ID 大小写敏感，不合并 `WH2001`（鸿远）与 `x2001`（修远）。
3. Qwen 识别已经接入，包括同区同批次多视角联合估算；当前页面查询不需要再次调用视觉模型。
4. `/api/navigation/recommend` 已调用百炼，但只让模型在真实步行/骑行候选中选 ID；没有通用对话、工具循环、停车联合 AI 或公交规划。
5. 公交已有线路、站点、车辆容量与人数读写；没有时刻表、候车、换乘和公交 ETA 计算。摄像头人数写入接口存在，不等于已连接实际车内摄像头。
6. SQLite、Compose 前后端及配置加载已经存在；不要重复搭建。

## 现有只读业务接口与返回口径

### 地点与直接路线

`GET /api/navigation/places?q=文本` 返回 `items`，包含 `id/name/longitude/latitude/source/location_type`。查询本地地点、路网入口/停车节点和当前停车区。建筑中心不是建筑入口；不能把中心到路网的接驳算成已覆盖时间。

`POST /api/navigation/route` 请求：
```json
{"origin":{"longitude":108.0,"latitude":34.0},"destination":{"longitude":108.001,"latitude":34.001},"mode":"bike"}
```
以上坐标只示意协议，不是校园点位。实际坐标只能来自用户选点或地点目录。

mode 仅 walk/bike。真实结果有 `id/mode/distance_m/duration_minutes/geojson/origin_access_distance_m/destination_access_distance_m/assumed_speed_kmh/network_revision/notice`。`geojson` 是 Feature；时间使用路网速度假设，不包含入口接驳及停车操作。不连通或离路网过远返回 422，不能自动改画直线。

### 停车推荐

`POST /api/navigation/parking-recommendations` 使用同样请求。默认选择目的地直线距离 800 米内且两段路线可达的停车区，最多返回 5 项。

返回 `items/excluded/radius_m/formula/notice`。每项包含：
- 停车状态：`area_id/name/capacity/count/percent/available/source/updated_at/illegal_count/legal_count/unknown_location_count/job_id` 等。
- `approach`：起点到停车区的路线；`walking`：停车区到终点步行路线。
- `score/walk_minutes/duration_minutes/distance_m`。
- `geojson`：FeatureCollection，分别以 `properties.segment=approach/walk` 表示两段。

现有公式：`approach_minutes + 2 * walk_minutes + 5 * occupancy_percent / 100`。空列表是有效业务结果，说明没有候选，不能编一个停车区。

现有参数不支持自定义偏好权重。要支持“少走路/更空闲”，应在保持兼容的前提下增加受校验的优先级或权重参数，由后端实际计算排序，并用测试证明排序变化。不能只让模型口头声称已经优化。没有动态道路拥堵输入时不能承诺避开实时拥堵。

### 停车统一状态

`GET /api/parking/areas` 是当前区域及容量。`GET /api/parking/overview` 调用 `area_states(request)`，返回：
```json
{"items":[],"is_live":false,"formula":"total_unique_two_wheelers_including_assigned_illegal / map_area_capacity * 100"}
```
items 含 ID、名称、几何、容量、数量、percent、available、source、updated_at 以及违停分类等。来源逐项是 `qwen_estimate` 或 `simulated`，允许混合，不要给全部结果统一贴“实时”或“模拟”。识别是上传素材估算；available 是容量减数量且下限为 0，不是预约或保证车位。

规则：同区最新记录替换旧快照，不相加；多视角联合去重，不按视角相加；归属违停已在二轮车总数内，不重复加。容载率不封顶，容量修改后按当前地图容量重算。`illegal_count=null` 不等于 0。自行车、电动两轮车、类型未知三类合计为总数；合法、违停、位置未知三类合计也为同一总数。

不要默认使用 `/api/parking/status`，它仍只生成模拟状态。`/api/trips/plan` 是另一套节点 ID 规划且校园停车使用模拟快照；本次优先接 coordinate navigation 接口。旧 `/api/routing/plan` 仍为 501，但不代表当前导航不可用。

### 公交

`GET /api/transit` 返回 `revision/status/message/stops/routes/vehicles`。
- stops：id/name/longitude/latitude。
- routes：id/name/points/stop_ids/color；points 是经纬度对象，stop_ids 为停站顺序。
- vehicles：id/name/route_id/capacity/camera_id/observation。
- observation 可为空，否则含 count/captured_at/source/capacity/percent/level 等，source 为 camera 或 manual_test。

按时间与来源展示，manual_test 是测试数据；车内人数/容量也允许 120%。线路几何可显示，但不能据此生成班次、等待时间或公交总 ETA。空配置直接说明没有配置公交数据。助手不调用公交配置 PUT 或人数上报 POST。

## 新增助手协议（以下是待实现要求）

建议增加 `POST /api/assistant/chat`；保留现有导航接口兼容，不让旧 AI 按钮失效。请求例：
```json
{
  "session_id": null,
  "message": "骑车过去，停车后少走路",
  "context": {
    "origin": {"place_id":"来自目录的ID"},
    "destination": {"longitude":108.001,"latitude":34.001},
    "preferences": {"allowed_modes":["bike","walk"],"priority":"less_walking"}
  }
}
```
坐标仍仅示意。用 Pydantic 定义地点联合类型：目录 ID 或用户地图坐标；有限值、经度范围、纬度范围须校验。目录 ID 由服务端查回坐标，不能信任模型为它附加的坐标。缺地点或有歧义返回目录候选；用户地图选点优先，不被模型覆盖。若传出发时间，必须含时区，并说明当前未支持按班次规划。

响应至少含：
- `session_id/request_id/status`：status 为 ok/needs_clarification/unavailable。
- `answer/resolved_request/clarification`：合并后的需求、缺失字段及真实地点候选。
- `parking_options`：实际工具候选，默认 []。
- `route_plan`：实际算法结果，默认 null；前端可使用现有 GeoJSON 渲染。
- `sources`：服务端组装的来源和时间，区分识别估算/模拟/路网计算/公交观测。
- `limitations`：实际能力限制和时间假设，不加入人工复核提示。

新增健康检查可只返回 configured、模型标识、可用工具，不触发收费调用。configured 不等于远程已验证连通。输入错误 422；缺配置 503；上游超时 504；其他上游失败以脱敏错误码处理。业务缺条件可 200 + needs_clarification，无法规划可 unavailable。

## 工具执行与模型边界

只允许以下只读工具，名称可调整：
1. `search_places(query)`：本地目录搜索。
2. `get_parking_overview(area_id?)`：统一状态，保留逐项时间和来源。
3. `plan_direct_route(origin,destination,mode)`：实际道路图计算。
4. `recommend_parking(origin,destination,mode,priority?)`：实际停车联合推荐；新增优先级需先实现算法支持。
5. `read_transit()`：已有线路、站点、车辆人数及时间。

共享业务函数可抽到服务层，保持原接口兼容；避免同进程绕 localhost HTTP。不要把 `ask_ai` 或 `/navigation/recommend` 包成工具再让助手调用，造成一次查询多次模型套模型。

校验工具名、参数、目录/区域 ID、用户可选交通方式。建议最多 4 轮、每轮最多 4 次调用，并设总时间与上下文上限。禁止任意 Python/SQL/shell/URL 执行；不提供编辑路网/停车区、公交配置、上传素材或收费视觉任务工具。

结构化结果从实际执行缓存组装，不采用模型生成的路线坐标、时间、空位或 percent。模型可以在本次真实候选里选 ID 并解释；服务端验证 ID 属于候选集，再返回原始方案。一次推荐以该工具返回的快照为准，不拼接另一个时间窗口的模拟数字。说明文本事实校验失败时使用工具数据模板。

用户或地名/工具数据中的指令不能改变白名单或索取密钥。会话隔离并有 TTL/容量上限；重启会话是否丢失写清。若持久化，使用现有 SQLite 的独立表迁移，不覆盖现有业务表。

## 前端和配置

在 `NavigationApp.vue` 现有 AI 入口接入对话与方案卡片，复用起终点、搜索、地图选点和 `renderRoute`。保留并发请求失效控制，不能让旧响应覆盖新终点。Feature 和 FeatureCollection 均要正确显示；骑行到停车区、停车后步行两段保留。选择停车候选更新地图。现有“停车区域与容载率”一个开关同时控制两层，公交仍单独开关。

诊断和模型配置说明放 `/debug`；密钥只在后端。模型文本安全插值，若渲染 Markdown 则过滤 HTML。云端失败仍可用普通导航与现有停车推荐，不伪装成功。

现有配置加载读取项目 `百炼.env`、`.env`，环境变量覆盖文件。既有变量：
```
DASHSCOPE_API_KEY=
QWEN_VISION_MODEL=qwen3-vl-plus
QWEN_VISION_BASE_URL=
NAV_AI_MODEL=
NAV_AI_BASE_URL=
```
NAV_AI 空值复用视觉配置，这是现有兼容行为，不是新助手必须采用 Qwen 的限制。新增助手应使用独立服务商、模型、地址和密钥配置，不能把其他服务商密钥写入 DASHSCOPE_API_KEY。Compose 已有可选 env_file。不要修改既有视觉参数来实现助手；可新增独立助手 model/base_url/timeout/tool rounds 配置，但必须实现加载、Compose 注入及空值策略并更新模板。密钥不进 VITE_、Git、镜像或日志；保留已有本机配置。日志只保留 request_id、工具、耗时、用量和脱敏错误。

先实现可注入模型适配器和离线测试，再验证所选模型服务实际支持的工具协议；不能把当前 JSON 选路线接口当作工具循环已经完成。未做付费云端联调就明确记录，不默认在测试中触发付费请求。

## 开发顺序与交付

1. 读取源码，确认当前接口；定义助手请求响应、配置及只读工具。
2. 完成地点解析、缺失/歧义澄清、统一停车查询。
3. 完成直接路线、停车联合推荐和地图显示。
4. 支持追问更新偏好；如需权重扩展，保持默认推荐兼容并验证排序。
5. 接入公交查询和人数；公交 ETA 未提供时明确能力限制。
6. 补错误处理、调用上限、会话隔离、部署说明和云端联调记录。

必要测试：真实业务函数被调用；模拟/识别混合来源；120% 不截断；违停不重复；null 不变成 0；区域 ID 大小写；容量变化后重算；缺起点/重名；越权工具与伪造候选 ID；模型伪造 GeoJSON 不被采用；偏好确实改变排序；公交为空或有人数但无 ETA；超时/未配置后普通导航可用；上下文隔离与工具调用上限；响应日志不泄露密钥。

运行项目已有后端测试与前端构建。说明哪些是离线测试、哪些实际调用所选模型服务、哪些 Docker/Mac 尚未验证。交付代码、无密钥模板、请求响应样例、启动说明和完成清单；不要提交本机 .env、媒体、backend/storage、虚拟环境、node_modules。独立分支提交并说明集成点，避免覆盖负责人正在改的前端。

## 最新负责人更正：模型与区域归属

- 识图固定使用 Qwen；出行助手/指路模型由负责 LLM 接入的同学选择，服务商、模型和密钥独立配置。不要把视觉 Qwen 选型当作助手选型限制。
- `Untitled.geojson20000.geojson` 中的 15 个有效区域是真正的修远停车区。
- 原文件 `修远楼停车区标注.geojson` 中的 9 个区域实际属于鸿远，名称应为“鸿远1区北”等；ID 统一为 `WH` 加原编号，例如 `X1001 → WH1001`、`X2001 → WH2001`。原文件名不能作为区域归属依据。
- 其余明远 17 个区域保留，共 41 个区域。名称与 ID 以当前后端目录为准，LLM 不自行改写。若收到旧接口快照，先刷新区域目录，不根据名称猜 ID。
- 鸿远改名迁移由项目负责人这边完成，LLM 同学不另做一次导入。已有素材、识别结果和道路入口需跟随 ID 迁移；不得把鸿远结果挂到真正修远区域。
