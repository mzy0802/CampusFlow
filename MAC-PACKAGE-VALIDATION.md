# Mac 交接包检查记录

- 包含当前前后端源码、Mac 安装启动脚本、依赖清单、用户区域 GeoJSON 及现有 YOLO11n 权重。
- ZIP 完整性检查通过；包内文件的 SHA256 逐项核对通过。模型 SHA256 为 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`。
- `.sh` 使用 LF 换行并在 ZIP 中标记为可执行文件；文档仍采用 `bash scripts/xxx.sh` 启动，避免解压工具未保留执行权限的问题。
- 未打包 Windows 虚拟环境、Python/Node 二进制依赖、缓存、上传历史、用户测试照片或人物检测预览。
- 前端构建、21 项数据/识别流程测试及一次照片推理在原 Windows 开发环境通过，不等于 Mac 兼容性或识别准确率验收。
- 当前无 Mac/M5 真机；未执行 macOS arm64 pip 安装、启动、MPS 或 Docker 验收。本机 Git Bash 语法检查尝试被沙箱权限阻止，脚本未据此标为已运行通过。
