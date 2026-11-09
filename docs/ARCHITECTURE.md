# Architecture

羊剪剪由三个可独立检查的部分组成：

1. `apps/desktop/` 是 Windows WPF 与 WebView2 外壳，负责窗口、文件选择、
   原生对话框及 Python sidecar 生命周期。
2. `backend/` 提供私有 newline-delimited JSON 协议。标准输出只承载协议包，
   日志写入标准错误，避免日志破坏桌面通信。
3. `webui/` 是桌面端加载的构建后 Web UI。界面通过 WebView2 bridge 调用
   Python action，并接收 `task.progress`、`task.completed` 和
   `task.failed` 事件。

## Protocol

请求格式：

```json
{"id":"request-id","action":"video.probe","data":{"path":"C:\\media\\input.mp4"}}
```

响应格式：

```json
{"id":"request-id","success":true,"data":{},"error":null}
```

错误响应始终使用结构化代码和用户可读信息。长任务立即返回
`taskId`，结果与错误随后通过任务事件发送，并在任务中心中保留。

## Authentication

公开源码不包含账号或密码。本地管理员通过以下环境变量配置：

- `YJJ_ADMIN_USER`
- `YJJ_ADMIN_PASSWORD_HASH`，优先使用 PBKDF2-SHA256
- `YJJ_ADMIN_PASSWORD`，仅用于本地临时调试

登录会话仅保存在当前进程内。注销、关闭应用和重新启动后都需要重新登录。

## Project data

每个项目有独立目录、项目元数据和 SQLite 数据库。视频原文件保留在原位置；
应用不会因为加入项目而移动或删除用户素材。生成的中间文件位于项目目录下的
临时目录，并在任务结束后清理。

## Media runtime

FFmpeg 和模型权重不进入 Git。`YJJ_FFMPEG_DIR` 或设置中的 `ffmpeg_dir`
必须指向同时包含 `ffmpeg` 和 `ffprobe` 的目录。发布者负责选择满足其分发
与许可要求的 FFmpeg 构建，并校验下载文件的哈希。

## Trust boundaries

- Web UI 不能直接执行 shell 或访问任意后端对象，只能调用已注册 action。
- AI 不直接构造 shell 命令；媒体命令由固定代码校验和生成。
- 下载、更新和模型安装必须使用 HTTPS、大小限制和 SHA-256 校验。
- API 密钥、更新私钥、顾客视频、项目数据库和日志不得进入公开仓库。
