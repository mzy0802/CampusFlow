# 路线与停车接口交接

接口前缀 /api，本地后端 http://127.0.0.1:8000，完整字段和约束见 /docs。LLM 负责解析需求、调用工具、解释结果，不生成坐标或空位。

本文保留节点式停车联合规划接口。新版应用页使用 /api/navigation 下的地点搜索、地图选点和路线接口，详见 [导航与标注 API](NAVIGATION-ANNOTATION-API.md)。应用页为 /，内部工具页为 /debug。

## 查询流程

1. GET /places?dataset=campus 获取已保存节点，选择起终点。重名或输入不明确时请用户确认。
2. POST /trips/plan 传节点 ID 与偏好。
3. 展示 recommended、alternatives、segments[].geojson，并保留 warnings、parking_source 和时间信息。

独立虚构示例请求：

```json
{"dataset":"example","origin_id":"start","destination_id":"goal","preference":"fastest"}
```

preference 可为 fastest 或 less_walking。默认 bike_speed_kmh=12、walk_speed_kmh=4.5、parking_minutes=1、min_available=1。

成功 status=ok；无可行方案返回 HTTP 200、status=no_route、recommended=null 和 excluded 原因。空路网返回 409；不存在的节点或非法参数返回 422。

## 管理接口

| 接口 | 用途 |
| --- | --- |
| GET /network/campus | 校园 OSM 路网；已按负责人要求纳入规划 |
| GET /network/example | 独立虚构示意路网 |
| PUT /network/{dataset} | 保存完整图，必须携带读取时的 revision |
| GET /roads | 校园道路 GeoJSON，包含 verified 标志 |
| GET /parking/status | 模拟停车状态及更新时间 |
| PUT /parking/{area_id}/capacity | 配置容量，正文如 {"capacity":100} |
| GET /vision/history?limit=50 | 上传测试历史，不代表实时监控 |

保存采用乐观锁，旧 revision 返回 409，需要重新读取并合并。节点和边 ID 唯一，道路必须引用存在且不同坐标的节点。校园停车入口必须关联现有 parking_id。JSON 导入后须保存才参与计算。

## 算法与边界

Dijkstra 分别计算骑行与停车后步行路径，遵守方向、通行方式和核验标志。只使用明确连接的已核验道路，不自动补路。长度为节点间球面距离，弯道需录入中间节点。时间=距离/设定速度×道路 congestion 乘数；最后加停车耗时。

fastest 按总耗时排序；less_walking 按步行距离优先、总耗时其次排序。拥堵乘数是人工设置，空位为模拟值，预计耗时不是实测预测。

Qwen 上传历史入库但不覆盖停车实时状态。公交返回 not_configured。旧 /routing/plan 坐标吸附接口仍为 501，请使用 /trips/plan 节点接口。

当前为本机演示，无账户鉴权，不要将可写管理接口直接开放到公网。
