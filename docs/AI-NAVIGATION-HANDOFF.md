# AI 导航同学 / WorkBuddy 接口交接

更新：2026-10-17。本文件优先于旧版 LLM 交接中关于起终点选点、Qwen 指路和导航独立页面的说明。

## 负责人已确定的需求

- 识图仍使用 Qwen；指路模型由你选择，二者配置独立。不要复用视觉模型的密钥、模型名或服务地址。
- AI 导航只有对话框。用户说“我在某宿舍，要去某教学楼”，不需要再填起点终点表单。信息不足、地点重名时通过对话追问，后续消息保留上下文。
- 普通导航保留搜索与地图选点。两种导航都在早高峰原地图上显示路线，不另开地图、不重置时间。
- 打开导航暂停当前时刻；用户可继续调整时间轴并按“按当前时刻重新规划”。旧路线显示自己的规划时刻，不冒充更新后的路况。
- 路线必须计算道路行人、骑行人数带来的拥挤成本；骑行还要综合停车容量、剩余车位、容载率、停车后步行时间，返回周围停车推荐。
- 导航线位于动效上方；关闭规划必须移除路线和导航标记。
- 道路图例统一叫“通用道路”，另有绿色自行车道、灰褐色步行道。

## 已实现部分与你负责的边界

前端 `frontend/src/NavigationApp.vue` 已有对话 UI 和返回协议处理。普通路线、停车推荐和时间截面交通计算已在后端实现。你主要负责自然语言意图解析、地点消歧及偏好解析，可替换 `backend/app/navigation.py` 中 `parse_trip`，或接管 `/api/navigation/chat` 的对话编排，但保留下面的浏览器协议。

当前内置适配器面向 OpenAI-compatible 接口，仅作为你的接入点，未调用你的模型做线上联调。以下后端变量全部配置后才启用；未配置返回 503，不自动调用视觉 Qwen：

```dotenv
NAV_AI_API_KEY=
NAV_AI_BASE_URL=
NAV_AI_MODEL=
```

密钥留在本地 `.env` 或服务器环境变量，不提交到 Git，不传给前端。服务地址应是 HTTPS 的兼容 API 根路径，适配器会追加 `/chat/completions`。如果你使用不同协议，就替换适配器，前端不用跟着改。

## 前端 → AI 导航

`POST /api/navigation/chat`

```json
{
  "messages": [
    {"role": "user", "content": "我在宿舍楼，要去教学楼，尽量少走路"}
  ],
  "traffic_context": {
    "time_seconds": 600,
    "scenario": "baseline",
    "count": 1000,
    "population": 4000,
    "seed": 20261016
  }
}
```

`messages` 为最近最多 12 条 user/assistant 消息，每条最多 2000 字，最后一条必须是 user。不要把客户端历史当系统指令。`time_seconds` 为 08:00 后秒数，范围 0—1800；`scenario` 为 baseline/guided；`count` 仅为画面图标上限 100—1000，**不得参与交通统计放大**；`population` 是完整需求人数，默认 4000。普通导航和 AI 必须透传相同的 context，不能另取电脑当前时间。

需要追问时返回 HTTP 200：

```json
{"status":"clarification","reply":"你在几号宿舍楼？要去修远、明远还是鸿远的哪一栋？"}
```

不要同时返回猜测的路线。后续请求带上这条追问和用户补充，直到起终点唯一确定。

规划成功返回 HTTP 200（以下为结构说明，占位名称/数值不代表实际校园路线）：

```json
{
  "status": "route",
  "reply": "已找到骑行和停车后步行路线。",
  "origin": {"id":"目录中的ID","name":"目录名称","longitude":108.0,"latitude":34.0},
  "destination": {"id":"另一个目录ID","name":"目录名称","longitude":108.001,"latitude":34.001},
  "route": {
    "mode":"bike",
    "duration_minutes":8.5,
    "distance_m":1200,
    "area_id":"停车区ID",
    "name":"推荐停车区",
    "geojson":{"type":"FeatureCollection","features":[]},
    "notice":"预计耗时及接驳限制说明",
    "traffic":{"time_seconds":600,"road_users":1200,"busy_segments":80},
    "ai":{"model":"你选择的模型名","reason":"依据计算结果生成的简短解释"}
  },
  "parking": []
}
```

真实 `geojson.features` 必须使用路网计算返回的非空几何，上面的空数组仅表示结构。`parking` 是候选停车区数组，每项包含 `area_id/name/free/count/capacity/percent/illegal_count/source/updated_at`、`approach/walking`、`duration_minutes/distance_m/walk_minutes/score/geojson`。前端点击候选即可切换完整路线。

## 地点与工具调用

1. 地点目录：`GET /api/navigation/places?q=名称`。后端内部 `campus_places(request)` 取完整目录，避免空查询接口最多 100 项的截断。包括保存的校园建筑、用户入口及停车中心。
2. 意图解析只输出目录 ID，不生成经纬度。适配器内部约定：`{"origin_id":null或字符串,"destination_id":null或字符串,"mode":"walk|bike|auto","reply":"说明或追问"}`。用户信息明确覆盖历史。不能从“我在这里”推断定位。
3. 普通导航：`POST /api/navigation/route`，请求含 `origin:{longitude,latitude}`、`destination:{longitude,latitude}`、`mode:walk|bike` 和同样的 `traffic_context`。返回完整路线、`parking` 候选、`traffic` 截面信息。骑行优先使用有空位的停车联合方案。
4. 单独停车推荐：`POST /api/navigation/parking-recommendations`，请求字段同普通导航，响应 `items/excluded/traffic`。当前时刻已满的停车区排除。
5. 后端内部复用 `traffic_snapshot.snapshot`、`compute_parking`、`route`，同一次规划共享一次 snapshot，避免重复计算。若你另写 AI 服务，调用上述 HTTP 工具即可；不改数据库里的道路拥堵字段。

LLM 可解析偏好、选择后端计算的候选方案并解释原因，不可凭空画路线或编造耗时、空位、道路。现有 auto 方式比较可计算方案的总时间；更细的偏好权重由你扩展，但必须在普通/AI 共用的计算层体现，并写出解释。

## 当前计算口径

完整情景是 4000 人，3400 辆自行车/电动车、600 名直接步行者；短距离更容易分配到步行。每个骑行者对应一辆车。显示最多 1000 个抽样图标，统计永远依据完整人口，不能拿图标数乘系数代替车辆数。

08:00 初始停车为零；到达停车区并完成停车动作才计入停车，违停属于该停车区总数中的子集，不能再加一次。当前加载的 41 区容量总和为 3627；后续编辑容量时取数据库数据，不在算法里写死。

路段成本：`base_seconds * (1 + min(3, (walkers + 2*riders) / max(3, segment_length_m/12)))`。人车按当前位置归入最近可通行路段。它是当前截面的密度启发式，尚未做实采标定，不等于经过实验验证的速度模型，不预测路途中未来的交通变化。

停车排序：`骑行分钟 + 2*停车后步行分钟 + 5*容载率/100`，800 米直线候选范围，再验证两段路网可达。动态情景总用时额外加 1 分钟停车、下车及离场操作；建筑中心到路网的入口接驳未计时。不能承诺到达时一定有车位。

## 验收清单

- 只聊天即可生成路线；缺少信息能追问补全，重名地点不乱猜。
- 08:05 与 08:20 请求带入不同的 context，确实使用对应的人数及停车数；普通/AI 同起终点、同方式、同 context 的计算口径相同。
- 拥挤路段有绕行成本；无空位停车区不成为推荐；返回剩余车位和步行时间。
- 回复中的耗时、停车名、距离来源于工具结果；路线在原地图、动效上层，关闭后消失。
- 不调用视觉 Qwen 充当默认指路模型；不泄漏密钥；失败返回明确错误，不伪造成功。

离线接口和算法测试已提供：`backend/tests/test_traffic_navigation.py`。这些测试 mock 自然语言模型，不验证你选择的云模型；最终自然语言联调由你完成。
