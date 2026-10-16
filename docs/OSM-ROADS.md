# 渭水校区公开道路导入

来源：© OpenStreetMap contributors，ODbL 1.0。

- 校区边界：https://www.openstreetmap.org/way/271773865
- 授权及署名：https://www.openstreetmap.org/copyright
- 下载端点：https://overpass.kumi.systems/api/interpreter
- 本次下载日期：2026-10-16（原始服务数据时间见 raw.json 的 osm3s）
- 服务数据快照：2026-07-15T15:22:01Z，不代表下载日现状。
- 边界筛选后：217 条 OSM way、1,259 个路段、1,071 个节点。

查询：

```text
[out:json][timeout:45];
way(271773865);map_to_area->.campus;
(way(area.campus)[highway];way(271773865););
out body;>;out skel qt;
```

原始记录保存在 data/osm/weishui.raw.json。运行 `python scripts/import-osm-roads.py` 可离线重建 network.osm.json、roads.osm.geojson 和 campus-boundary.osm.geojson。分发这些道路数据时保留 OSM 署名与 ODbL 信息。

导入保留原始 WGS84 坐标及 OSM 共用节点的连接关系。按校区边界检查道路段两端和中点，排除越界段；未自动延长道路、吸附断点或添加停车入口。曲线按原始节点拆分，因此“1259 段”不是 1259 条独立道路。

2026-10-16 按负责人要求，当前全部道路 verified=true，表示项目内采纳而非独立实地核验。启动时对既有路网做一次迁移并保留旧版本。步行道、台阶和路径保守设为步行，明确 bicycle=yes/designated/permissive 的允许骑行；禁止或私有通行标签保守排除对应方式。当前模型以道路共用方向表达 oneway，不能完整表达骑行单向但行人双向等规则，实际核验时需拆分相应道路。原始标签保存在 GeoJSON 中，供进一步核对。道路重叠不自动视为交叉路口，立交、台阶及缺失路口应实地核实。

后端启动时只初始化 revision=0 且完全空白的校园图。已有编辑绝不覆盖；若已有路网，使用工作台导入 data/network.osm.json，确认后保存。设置 CAMPUS_NETWORK_FILE 为空字符串可禁用初始化。

本次完成的是公开道路标绘，不保证覆盖全部校内道路，也不表示实地可通行。停车入口、建筑入口以及校内公交线路和站点仍需补充。道路已参与路线计算。应用页黄色表示普通道路与path，绿色表示cycleway，#66CCFF表示步行类；service不叠加绘制，但仍可参与规划。
