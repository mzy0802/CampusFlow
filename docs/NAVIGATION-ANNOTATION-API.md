# 导航、标注和双网页接口

应用入口 `/`，内部入口 `/debug`，同一前端服务两个独立页面。开发端口5174，Compose端口8080。现阶段内部页仅作功能分离，没有身份鉴权，不要直接公开部署管理API。

## 导航

- GET `/api/navigation/places?q=鸿翔园`：本地搜索公开地点及人工入口。公开建筑中心标记为 building_center，不能冒充实际入口。
- GET `/api/navigation/map`：显示路网，隐藏 service；黄色普通道路/path，绿色cycleway，#66CCFF步行类。调试用 include_service=true 可取得全部类别。隐藏不代表道路禁行，service仍可参与算法。
- POST `/api/navigation/route`：正文 `{origin:{longitude,latitude},destination:{longitude,latitude},mode:"walk"}`，mode也可为bike。
- POST `/api/navigation/recommend`：同上，另加 preference 字符串；后端先计算步行、骑行候选，再让百炼选择合法候选ID。模型不生成坐标、路线或耗时。

选择点投影到最近可用路段并临时切分，最多150米。不增加穿越建筑的假连接线；返回两端的接驳距离，预计耗时只含路网内路段。断路、禁行或单向导致不通时返回422。速度步行4.5km/h、骑行12km/h，人工拥堵乘数参与成本。未实现实时路况、公交、逐路口语音导航或GPS跟随。

AI配置复用后端百炼密钥与视觉模型；可选 NAV_AI_MODEL、NAV_AI_BASE_URL 覆盖。密钥只在服务端。错误返回503，前端提示改用普通导航，不伪造AI推荐。

## 照片与视频标注

- GET `/api/annotations/media`：本地素材库。
- POST `/api/annotations/media?filename=...`：文件原始二进制，不是multipart。单个100MB，视频最多30分钟；不调用模型。
- GET `/api/annotations/media/{id}/content`：图片按解码后的原尺寸PNG显示，原文件保留；视频返回原文件，浏览器播放能力取决于编码。
- GET/PUT `/api/annotations/media/{id}`：读取/保存标注。

PUT正文：

```json
{"revision":0,"reviewed_frames":[0],"polygons":[{"id":"p1","label":"allowed","time_seconds":0,"note":"白线内","points":[[0.1,0.1],[0.8,0.1],[0.8,0.8],[0.1,0.8]]}]}
```

坐标为原画面归一化xy：左上(0,0)、右下(1,1)。照片时间0，视频按秒。label只允许allowed。审核帧中所有多边形的并集内可停车，其余不可停车；不在reviewed_frames中的帧为unknown。空多边形＋审核帧表示该帧全部不可停车，空多边形＋无审核帧表示尚未标注。前端邻近时间显示容差0.08秒只是预览，不能当作整段视频的审核结果。

拒绝越界、非有限值、重复顶点、退化、自相交多边形及超时长帧。乐观锁旧revision返回409，须导出草稿后重新读取，不自动覆盖。数据库保存标注，文件在storage/annotations。现有Qwen计数没有可靠定位框，本版不做区域内外自动违停统计。

## 地图停车区

GET/PUT `/api/parking-editor` 使用 `{revision,collection}`，collection是GeoJSON FeatureCollection，Polygon坐标为WGS84经纬度，每个feature属性含唯一id、name和capacity。新画区域校验闭合、面积、相交；未改变的旧导入问题边界保留并标记legacy_boundary_needs_review。与路网停车入口关联的区域不可直接删除。

保存几何后同步停车容量，停车状态仍为模拟值。数据保存在SQLite，不覆盖原始上传GeoJSON。版本历史保留在数据库中。地图边界不能直接映射到照片，需要相机标定或另行画面标注。

## 道路来源与负责人确认

2026-10-16按负责人明确要求，将现有全部道路标记verified=true，保留修改前版本。此迁移只运行一次；后续人工取消核验不会被重启覆盖。新增边默认核验。标志表示项目内采纳，不表示助手进行过实地调查。坐标仍来自OSM原数据。

地点来源为OSM map API校园包围盒数据，筛选校区边界内有名称的节点与建筑。建筑点使用几何包围盒中心，原要素ID和标签见data/osm/places-sources.json；保留© OpenStreetMap contributors / ODbL署名。
