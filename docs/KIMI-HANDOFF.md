# CampusFlow 完整开发交接

交接日期：2026-10-17，Asia/Shanghai。本文面向负责人、接手AI及团队开发者。

## 1. 项目位置、版本与交接范围

- 项目：长安大学渭水校区校园停车、出行导航与早高峰动画演示，挑战杯原型。
- 仓库：https://github.com/mzy0802/CampusFlow ，公开，main。
- 本地根目录：`C:\Users\mzy\Documents\Codex\2026-10-15\referenced-chatgpt-conversation-this-is-an\outputs\campus-parking-demo`。
- 交接前最近提交：`a9e6f333d10074937f20217b55d0dd933eae033a`，消息“更新早高峰动画、同图导航和AI接口交接文档”。是否已推送，以接手时 `git status -sb` 和远端比较为准。
- 最近搜索、建筑步行和违停摆放修改尚在工作区；本次交接源码快照包含已跟踪及未跟踪文件。不得用远端旧版本覆盖。
- 本轮只整理交接，不替用户自动提交或推送。

交接包分为：源码 ZIP（交给新AI）、本地状态 ZIP（数据库/素材/旧模型迁移）、完整说明和直接粘贴的接手指令。包外已有本机 Python/Node 与依赖仍可使用，不必重新安装。密钥留在现有本地环境文件，不写进说明或源码 ZIP。

## 2. 当前产品结构

技术栈：Vue 3 + Vite + Leaflet/OSM；FastAPI + SQLite；OpenCV + Qwen视觉接口；Docker Compose部署。现有最短路实现是项目内算法，不要仅凭总体规划文档就宣称已使用 NetworkX/OR-Tools。

- `/`：早高峰主应用，默认 `SimulationApp.vue`。
- 主应用“地点与导航”：在**同一张地图**挂载 `NavigationApp.vue` 面板；搜索、普通导航、AI聊天入口在这里。保留动画、时间轴、停车状态。
- `/debug`：`App.vue`，包括停车编辑、照片/视频标注、识别测试、多视角联合识别、道路、公交、路线测试及动效图标数设置。
- API文档：后端 `/docs`；健康检查 `/api/health`。

前端仅调用 `/api`，开发时通过 Vite 代理；浏览器不能直接拿到云密钥。没有实现用户认证、线上多人权限或正式运维体系，不要把原型直接宣称为生产系统。

## 3. Windows 启动（两个窗口保持打开）

窗口一，后端：

```powershell
cd "C:\Users\mzy\Documents\Codex\2026-10-15\referenced-chatgpt-conversation-this-is-an\outputs\campus-parking-demo"
& "C:\Users\mzy\AppData\Local\Programs\Python\Python313\python.exe" run_backend.py
```

窗口二，前端：

```powershell
cd "C:\Users\mzy\Documents\Codex\2026-10-15\referenced-chatgpt-conversation-this-is-an\outputs\campus-parking-demo"
$env:CAMPUS_BACKEND_URL = "http://127.0.0.1:8000"
& "C:\Users\mzy\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" frontend/node_modules/vite/bin/vite.js frontend --host 127.0.0.1 --port 5174 --strictPort
```

打开 `http://127.0.0.1:5174/`，调试页 `http://127.0.0.1:5174/debug`，API文档 `http://127.0.0.1:8000/docs`。

`run_backend.py` 会将工作区的 `work/venv/Lib/site-packages`、项目 `.venv/Lib/site-packages`、`.vision-deps` 加入路径。直接用系统 Python `-m uvicorn` 可能找不到依赖；优先使用该脚本。机器里 `npm` 曾未加入 PATH，上述命令直接使用现有Node运行Vite，避免此问题。

若端口占用，先在对应旧服务窗口 Ctrl+C，再重启；不要盲目结束所有 Python/Node 进程。修改后端 Python、新接口需要重启后端。前端通常热更新，必要时 Ctrl+F5。

旧AI曾为验证单独启动 `18000` 后端和 `5175` 前端，5175代理18000，与用户常用的8000/5174不同。接手时查端口再判断，不要把5175连到旧8000后端。预览进程是否仍在运行不能保证。

## 4. 新电脑 / Mac / Docker

已有 Dockerfile 和 Compose：

```sh
docker compose up -d --build
docker compose logs -f backend
docker compose down
```

网页 `http://127.0.0.1:8080/`，API `8000`。数据目录只读挂载，SQLite与上传素材存在命名卷 `vision-storage` 中。不要使用 `docker compose down -v` 清空卷。当前 Compose是 backend/frontend 两个常驻服务，尚未拆出独立vision任务容器。Docker运行在这台机器上未完成端到端验证，不能写“Docker已实测全部通过”。

Mac Apple Silicon可先用Docker；原生方式使用Python3.12/3.13创建venv、安装 `backend/requirements.txt`，前端安装Node22后 `npm ci`。还原本机已有数据时不能只复制源码：需迁移本地状态或Docker卷。Windows venv/Node缓存不能直接搬到Mac执行。视觉当前云端Qwen，不依赖CUDA。

## 5. Git / 发布当前代码

```powershell
git status -sb
git add .
git diff --cached --stat
git commit -m "完善地点搜索、楼内步行和违停展示"
git push origin main
```

LF/CRLF警告不是错误。曾因误操作生成名为 `h origin main` 的Git统计文件，已取消暂存并移出仓库，备份在上层 `work/accidental-git-stat-20261017.txt`，无需恢复。`.gitignore` 已忽略密钥、数据库、上传存储、模型权重、node_modules及构建目录。提交前检查实际暂存内容，勿修改忽略规则把这些本地文件上传。

## 6. 用户已确认的产品与视觉要求

- 页面沿用类似Google Maps的搜索/导航逻辑；普通模式支持模糊地点搜索、地图选起终点，显示路线和用时及目的地附近停车推荐。
- AI模式只有自然语言对话，不强迫先填起终点。起终点不全就通过聊天补全。AI可推荐工具真实计算的路线，不能编造路线坐标、耗时和空位。
- 普通/AI导航共用早高峰当前截面：人流、车流、拥挤成本、停车容量/余量、停车后步行。调时间后可按当前时刻重新规划，旧结果显示自己的规划时刻。
- 导航线在动效上层；关闭规划清除路线和导航标记，不能销毁原动画地图。
- 绿＝自行车道，橙＝**通用道路**，灰褐＝步行道；不要恢复“通用道路/路径”或浅蓝步行道。服务道路不额外画在可见道路图层。
- 字体为本地打包HarmonyOS Sans，Mac优先苹方；统一CSS变量 `--app-font`。原始TTF未修改，保留字体许可和页面小字署名。
- 人物是大学生卡通风格，不要大胡子；车辆停车后人在车旁出现，再步行进入教学区。
- 拖尾为连续赛车流光，不是虚线；已缩短亮带并降低底色，每段结束后24个情景秒内淡出。
- 停车标签远景缩小、近景移到停车区边缘外，不压住内部车辆；停车区与车辆、容载率与违停率采用现有两个开关。
- 不加入“人工复核”提示，不恢复全校/环岛/中部掉头快捷按钮。
- 用户希望展示原有停车习惯与系统引导后的对比，不希望页面堆满“情景仿真”等标签；但接口与技术文档必须保留生成数据/参考模型来源，不能把仿真写成实测研究成果。

## 7. 早高峰人数与停车口径（严禁混淆）

默认08:00—08:30完整生成4000人，3400骑行者（自行车/电动二轮车）、600直接步行者。短距离更偏向步行。一个骑行者对应一辆车；`cohort_per_vehicle=1`。

前端最多显示1000个确定性抽样图标，可在调试页调到100—1000；它只是绘制预算。改变1000为300不会改变实际生成对象、停车数、违停数或导航拥挤度。禁止再拿图标数乘权重凑出停车量。

当前41个停车区合计3627：修远15区1208、明远17区640、鸿远9区1779。容量来自导入和数据库，不能硬编码成永远不变的常量，不能随意缩小制造拥堵。

初始占用为0；停车动作18秒完成后计入；下车18秒、离开车位24秒；随后步行至教学楼。违停是停车总数的子集，不要加两次。违停显示点沿已有骑行接近道路生成，距离附近停车区有限范围且排除所有停车多边形；没有合适位置就不画回退点，不改统计总数。

高需求区：修远3东、修远大停车场、修远4北、修远2东；明远1西侧、明远4东北角、明远1中1、明远1中2、明远4南侧、明远4东南2；鸿远2区东、鸿远1区东、鸿远1区北。其他停车区也有到访。

baseline/guided相同人口、起点、目的地、出发时间及方式，改变停车分配。guided是容量负载和步行距离的启发式，不是全局最优。增加楼内通行/新目的地、修改容量和路网后，要重新跑指标，不能继续硬引用旧的216%等数字。

## 8. 导航、地点与教学楼步行

地点来源为本地OSM目录、用户入口及停车区。`place_search.py`做规范化、别名、排序和有限错字匹配。明远1—5映射A—E；修远/鸿远数字与中文区号互通。楼号已给出时不要跨楼号猜测；明确楼群时不把修远混到明远结果中。

修远四区的真实OSM对象是relation16871375，旧导入漏了multipolygon，已补到 `places.osm.json` 与 `buildings.osm.geojson`。来源原文在 `data/osm/campus-building-relations.raw.json`。普通建筑轮廓原文为 `campus-buildings.raw.json`。只覆盖相关教学片区，不能宣称全校建筑目录完整。

`building_walk.py`按用户“教学楼可穿行”规则为修远/明远/鸿远生成步行连接：各侧附近现有路网节点接入实际建筑轮廓，可见性路径避开凹边界和中庭洞，仅walk。**接入点和室内连接是参考模型，不是实测门位、走廊、楼层或无障碍通道**。自行车不能借其穿楼。步行距离计入接驳直线估算，骑行起点接驳仍未完整建模。

道路拥挤成本当前为 `base_seconds*(1+min(3,(walkers+2*riders)/max(3,segment_m/12)))`，属于当前截面启发式，未做实采速度模型标定、不预测在途未来流量。

停车候选800米直线范围再检查路网可达；动态时刻排除已满，比较骑行时间、2倍步行时间、5倍容载率成本，动态总时间加1分钟停车/下车操作。推荐不代表预约或保证到达时有空位。候选显示 `walk_minutes/walk_distance_m/free/count/capacity/percent/illegal_count`。

## 9. 视觉、标注、多视角与公交

- 当前视觉是Qwen云端计数，YOLO11/26本地历史实现和权重仍保留，不是当前默认方案。`qwen_vision.py`、`vision_service.py`、`vision.py`为主要入口。
- 分类：自行车、电动两轮车、总数；另有行人和无法确定类型。不得把电动两轮车漏掉，也不能把牌子上的自行车图案算真实车辆。
- 上传原图用于识别，不主动把高分辨率原图压成低分辨率；云供应商内部预处理不可保证“绝无缩放”。视频抽帧有帧数与采样限制，不能说每帧都已处理。
- 原通用模型在密集遮挡场景漏检明显；云计数也不是精确地面真值。多视角并集是模型估计，不是带标定的跨镜头重识别，不可简单相加。
- 只标可停车范围，标注帧内其他位置按规则视为不可停。未标注帧不能自动当违停。
- 标注多边形已处理双击/闭合时重复末顶点；自交、面积为零仍应拒绝。
- 标注可关联地图停车区；同区同批次视角联合识别、容量来自停车区；周围违停归属该区并计入容载率。保持视角/批次和拍摄时间语义。
- 公交有路线和停站点编辑、车辆容量及观察记录接口，后续接车内摄像头人数/上下车流。不要把手动/测试观察当已接入真实摄像头。
- 历史需求含多方式公交与AI业务闭环，当前完善程度须以实际接口和界面为准，不假定总体V3计划的所有功能都已实现。

## 10. 数据、数据库、存储与迁移

`backend/storage/traffic.sqlite3` 是默认本机SQLite，含路网/历史、停车配置、停车几何/历史、识别记录、标注素材、公交配置/历史/观察和设置。`backend/storage/`也保存上传文件、任务及预览等。数据不全在GeoJSON里；改过的容量和路网可能只在SQLite。

`main.py`启动时执行已有导入批次和身份迁移，`parking_editor.py`有版本/冲突保护。不要直接删库逼它重新导入，不要反复覆盖用户编辑。

停车主要文件：`data/parking.imported.geojson`，另有明远、鸿远、修远原始导入与修远v2映射。鸿远ID按用户要求为WH系列；明远WM系列；修远保留当前导入ID，不做随意格式统一。项目根 `明远.geojson` 为用户源文件之一，不可当垃圾清理。

路网：`data/network.osm.json`、`roads.osm.geojson`；连接/修复规则为 `road_corrections.py`、`cycleway.owner.json`。用户已将1083更正为1073，连接顺序包含11451826855、11173238457、新节点1072、新节点1073、2613667577。道路按用户规则视为已核验；环岛已修正穿心弦、中部掉头沿用保存路网。

本次本地状态包会使用SQLite备份API生成一致快照，并复制上传目录和models。恢复前停止目标后端，先保留目标现有数据，再把包中storage恢复到backend/storage、models恢复到models。**同一台电脑接手不需要覆盖任何存储。** Docker命名卷需要单独恢复进卷，不是拷到主机backend/storage就自动生效。

`.env` / `百炼.env` 存在于本地时继续读取，不要把内容贴聊天。视觉用 `DASHSCOPE_API_KEY/QWEN_VISION_MODEL/QWEN_VISION_BASE_URL`；导航独立用 `NAV_AI_API_KEY/NAV_AI_MODEL/NAV_AI_BASE_URL`（也支持LLM_API_KEY作为导航key来源），导航未配好就返回503，不回退调用视觉模型。

## 11. 文件地图

| 文件 | 作用 |
|---|---|
| frontend/src/main.js | 应用/调试页分流 |
| SimulationApp.vue | 地图、动画状态、统计、停车标签、导航挂载 |
| trafficArt.js | 缓存卡通Canvas贴图与连续流光 |
| simulationMath.js / simulationRender.js | 阶段、计数、投影与路径缓存 |
| parkingPlacement.js | 违停道路位置生成，禁止随机建筑旁回退 |
| NavigationApp.vue | 搜索、普通导航、AI聊天、推荐列表、路线图层清理 |
| App.vue / components/*Workbench.vue | 内部调试与标注工作台 |
| fonts.css / public/fonts | 字体及原始许可 |
| backend/app/main.py | 服务装配及启动迁移 |
| simulation.py | 4000人两种情景生成 |
| traffic_snapshot.py | 完整人流/停车截面、密度权重、情景缓存 |
| navigation.py | 地点、路由、停车推荐、AI适配接口 |
| place_search.py / building_walk.py | 地点别名模糊匹配、楼内步行参考图 |
| traffic_store.py / parking_editor.py | SQLite持久化、停车编辑、导入批次 |
| annotations.py / area_surveys.py | 素材标注、多视角及停车区关联 |
| qwen_vision.py / vision_service.py | 云视觉请求、识别任务与结果 |
| transit.py | 公交线路站点及人数观察 |

以上前端相对路径均从frontend/src开始，后端相对路径从backend/app开始，具体接口以 `/docs` 和源码为准。

## 12. API与团队边界

优先读 `docs/AI-NAVIGATION-HANDOFF.md`：聊天 `/api/navigation/chat`、普通 `/api/navigation/route`、停车 `/api/navigation/parking-recommendations`、地点 `/api/navigation/places`，以及完整请求/响应和交通上下文。参数包含 `time_seconds/scenario/count/population/seed`，两种导航必须一致，不能另取电脑当前时间。

另一位同学负责自然语言指路模型选择与接入。当前UI和兼容协议适配点已备好，但未用该同学模型线上联调。不要把测试中的mock叫真实AI成功。视觉服务仍用Qwen，指路独立。

其他文档：`QWEN-VISION.md`（识图）、`PARKING-TRANSIT-MULTIVIEW.md`（多视角与公交）、`TEAM-ANNOTATION-HANDOFF.md`（标注人员）、`PLACE-SEARCH-BUILDING-WALK.md`（最近搜索和步行）、`OSM-ROADS.md`（路网）、`MORNING-SIMULATION.md`（当前动画）。申报书AI文档是研究表达参考，不是实验已完成的证据。

## 13. 测试与已验证范围

最近完整后端：81项通过。最后搜索隔离改动又运行相关4项通过。前端14项通过，Vite构建通过。浏览器实际验证了明远1优先返回A栋、修远4区可搜索、普通导航显示停车后步行米数/分钟、路线位于Canvas动效上方、关闭清空路线；未联调同学的自然语言模型。Docker和Mac当前版本未实机端到端验证。

Windows后端测试（隔离目录，避免默认临时目录权限问题）：

```powershell
@'
import runpy,sys
runpy.run_path('run_backend.py',run_name='campus_test')
import pytest
sys.exit(pytest.main(['backend/tests','-q','--tb=short','--basetemp=../../work/pytest-kimi-handoff']))
'@ | & "C:\Users\mzy\AppData\Local\Programs\Python\Python313\python.exe" -
```

前端：

```powershell
& "C:\Users\mzy\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" --test frontend/tests/*.test.js
& "C:\Users\mzy\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" frontend/node_modules/vite/bin/vite.js build frontend
```

测试依赖pytest/httpx等在现有工作区环境中；`backend/requirements.txt`偏运行依赖，新电脑跑测试时按报错补齐测试依赖。`backend/tests/conftest.py`隔离数据库和存储，勿移除隔离。纯文档交接不需要再重跑所有测试。

## 14. 已知限制与接手建议

- 真实停车容量、名称、用户编辑和当前DB比旧文档数字优先；不要偷换统计口径。
- 交通/停车密度是可复现情景，尚缺真实流量标定与多种子干预实验；guided也不保证所有区都不过载。
- 楼内门位、楼层、走廊和无障碍未实测；目前是轮廓约束的可穿行参考模型。进一步完善应增加真实入口/走廊数据，不画任意穿墙直线。
- 位置信息从OSM补齐但没有保证全校园POI完整；新增地点须有明确数据来源，不编造真实坐标。
- 拥挤成本为当前截面，不预测到达时空位，不做预约。
- Qwen密集遮挡计数和跨视角融合仍有误差，不能宣称百分百准确；视觉上传非实时监控。
- 调试服务默认本机监听；公开部署的身份、上传限制、反向代理超时与备份需另做评估与验证。
- fonts有两份约8MB的原始TTF，首次加载较大；许可禁止擅自修改/子集化字体。不要为优化体积直接转字库而不看许可。
- 4000逻辑人口与1000可视预算已分开；以后做性能优化应保持计数一致，不能靠删掉真实对象加速。

建议接手顺序：确认工作区和Git未提交内容→看服务端口→按用户新需求验证可复现问题→读对应模块→最小增量修改→针对性测试与浏览器验证→清楚说明已完成和模型假设。不要在未获新需求时自行重构全项目。
