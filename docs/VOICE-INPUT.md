# AI 导航语音输入

语音只作为**输入方式**：音频在后端转成文字后交给现有对话链路，`/api/navigation/chat` 的协议一行未改。
选择「先转文字再交给大模型」而不是音频直连多模态，原因是转写结果可见可改、后端协议零改动、指路模型不被厂商锁死。

## 改动清单

| 文件 | 改动 |
| --- | --- |
| `backend/app/nav_voice.py` | 新增。ASR 调用、地点纠错、两个接口 |
| `backend/app/main.py` | 加 2 行：import 与 `include_router` |
| `backend/tests/test_nav_voice.py` | 新增。12 条离线测试 |
| `frontend/src/NavigationApp.vue` | 重写 `toggleVoice`，改为优先云端 ASR |
| `.env.example` | 追加 `NAV_ASR_*` 三个变量 |

## 接口

### `GET /api/navigation/asr`

就绪探测，前端据此决定走云端还是浏览器语音。未配置返回 `{"ready":false,"message":"…"}`。

### `POST /api/navigation/transcribe`

```json
{"audio":"<base64，不含 data URL 前缀>","mime":"audio/wav","language":"zh"}
```

响应：

```json
{"text":"我要去修远楼一区","raw":"我要去修元楼一区",
 "corrections":[{"from":"修元","to":"修远"}],"engine":"qwen3-asr-flash","bytes":8004,"mime":"audio/wav"}
```

- `raw` 是模型原样输出，`text` 是纠错后文本，两者都返回以便核对；
- `corrections` 非空时前端显示「已校正听错的地点：修元 → 修远」；
- 转写结果**填入输入框等用户确认再发送**，不自动发出。

错误码：`400` 格式不支持或音频超限；`503` 未配置 / 服务不可达 / 没听清。

## 配置

```dotenv
NAV_ASR_API_KEY=
NAV_ASR_MODEL=qwen3-asr-flash
NAV_ASR_BASE_URL=
```

与视觉 Qwen、`NAV_AI_*` 三者配置独立，互不复用。三个变量都填才启用，缺任一个前端自动降级到浏览器语音，
导航其余功能不受影响。`NAV_ASR_BASE_URL` 填兼容 API 根路径，代码会追加 `/chat/completions`，
音频以 `input_audio` 的 base64 data URL 提交。本地回环地址允许明文 HTTP，其他地址强制 HTTPS。

## 兼容性

`system` 上下文消息不是所有兼容端点都接受，实测 dashscope 旧域名返回 `400 does not support this input`。
首次遇到该错误时降级为不带 system 重试一次，并按 `BASE_URL + MODEL` 把结论缓存到进程内，
之后不再重复这次必然失败的请求。识别结果不受影响——校园地名纠错本来就由本地 `repair_places` 完成。

只有确认是 system 相关的 400 才缓存；`audio format not supported`、`invalid api key` 这类错误不会被误判成
上下文问题，下一句仍会带上地名上下文。

## 地点纠错

地名听错会让整句话无法匹配目录，只能退化成追问，所以转写后加了一层修正：

1. **同音字表**（`HOMOPHONES`）：`修元→修远`、`名远→明远`、`宏远→鸿远` 等，命中即替换；
2. **相似度匹配**：用保长的 `loose()` 归一化后滑窗比对目录名与别名，阈值 0.66，与 `place_search.search_places` 口径一致。

没有复用 `place_search.normalize`：它会剥掉「楼 / 区 / 教学」，归一化后的片段映射不回原文，替换无法命中。

## 前端行为

1. 打开导航时调一次 `/api/navigation/asr` 记录是否可用；
2. 点 🎤：可用则录音（`AudioContext` 采集 → 重采样 16 kHz → 封装 WAV → base64），最长 30 秒，再点一次停止并上传；
3. 服务端返回 503「尚未配置」时自动切换浏览器 `SpeechRecognition`，并提示「未做校园地名校正，请核对后再发送」；
4. 两者都不可用时提示直接打字，**不伪造识别结果**。

## 验证

- `pytest backend/tests/test_nav_voice.py -q` → 12 passed；全仓库 98 passed / 0 failed
- 假 ASR 服务端实测：模型返回「我要去修元楼一区」，接口返回 `text` 已改为「修远楼一区」并带 `corrections`
- 回归：`/api/health`、`/api/navigation/places`、`/api/parking/status`、`/api/navigation/chat` 均正常
- 前端 `npm run build` 通过

## 尚未做

- 真实百炼联调（本机无密钥）。联调时需确认 `qwen3-asr-flash` 是否接受 `asr_options.language` 字段，不接受则删掉该字段。
- 未使用热词表：百炼热词需另行创建词库，当前改用 system 提示注入校园地名（最多 200 个）。
- 实时流式识别（`qwen3-asr-flash-realtime`，WebSocket）未接，体验更好但需处理鉴权与断线重连。
