# Apple 芯片 Mac 安装与启动

需要原生 arm64 Python 3.12 或 3.13、Node.js 22.12+ 和 npm。不要复制 Windows 的 venv 或 node_modules。SQLite 随 Python 提供。网页默认 Qwen，普通安装不需要 PyTorch 或 YOLO 权重。

进入项目目录运行：

```bash
bash scripts/setup-mac.sh
.venv/bin/python scripts/check-mac.py
```

复制 .env.example 为 .env，填写自己的 DASHSCOPE_API_KEY 和对应百炼接口地址。密钥不提交 Git。没有密钥也能测试地图及路由，云端识别不可用。

两个终端分别运行：

```bash
bash scripts/start-backend-mac.sh
```

```bash
bash scripts/start-frontend-mac.sh
```

打开 http://127.0.0.1:5173，后端文档 http://127.0.0.1:8000/docs。两个终端保持运行，Ctrl+C 停止。

可选 bash scripts/setup-mac.sh --local-yolo 仅安装旧本地实验依赖，不切换网页默认引擎。通常不需要此步骤。

也可安装并启动 Apple Silicon 版 Docker Desktop，运行 docker compose up -d --build，打开 http://127.0.0.1:8080。停止用 docker compose down，不加 -v。

路线验收见 docs/MORNING-ACCEPTANCE.md，接口交接见 docs/ROUTING-API.md。Mac 与 Docker 尚未实机验收，反馈日志时请隐藏密钥。
