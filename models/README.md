# 检测模型目录

运行项目根目录 `python install_vision.py` 后，官方 YOLO11n 检测权重放到这里的 `yolo11n.pt`。
权重未随源码包分发，请勿从不明来源加载 PyTorch 权重。

运行时仅加载本地文件，不会在用户上传请求中触发模型下载。默认用 CPU；可通过 `DETECTION_MODEL` 指定兼容且包含 `person`、`bicycle` 类别的本地检测模型，通过 `DETECTION_DEVICE` 指定推理设备。
