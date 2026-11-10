# 羊剪剪（YangJianJian）

羊剪剪是一款面向短视频创作者的 Windows 智能剪辑工作台。它把自然语言需求、素材管理、字幕、视觉审核、时间线编辑、批量任务和应用内更新放在同一个桌面应用中。

Windows 用户请前往 [版本与安装包下载](https://github.com/yu4372171-crypto/yangjianjian/releases/latest)，
选择安装版或解压即用的便携版。适用 Windows 10/11 x64，AI 模型首次使用时按需下载。

本仓库是羊剪剪的公开源码版本，采用 MIT License。安装包、AI 模型、FFmpeg 运行时、顾客项目和云端服务凭据不进入 Git 仓库，由构建脚本或 GitHub Releases 单独提供。

当前仓库包含可运行的桌面外壳、视频后端和已构建的 Web UI。原始 Vue 工程与部分云端服务的运行凭据不在可恢复源码中；具体边界见
[当前源码版本边界](docs/LIMITATIONS.md)。

## 功能

- 自然语言“我的需求”工作流：把时长、比例、口播字幕、穿模处理、转场和配乐要求转换为可执行步骤。
- 智能自动剪辑：素材分析、台词识别、镜头匹配、画面裁剪、字幕、背景音乐与成片输出。
- 时间线剪辑：多轨视频、文字、音频和叠加素材，支持分割、裁剪、排序、撤销重做、连续预览与导出。
- 视觉与语言模型：OpenAI 兼容接口、服务商预设、本地模型下载和硬件推荐。
- 字幕、字体、BGM、转场、贴纸与透明叠加素材管理。
- 任务中心：查看进度、取消任务、恢复失败任务并下载历史成片。
- 应用内更新：稳定版清单、校验、下载与安装流程。
- 本地优先：项目数据保存在本机，API 密钥通过 Windows DPAPI 保护。

## 仓库结构

```text
apps/desktop/   Windows WPF + WebView2 桌面外壳
backend/        Python 智能剪辑服务与任务协议
webui/          桌面端加载的 Web UI 静态 ES 模块包
scripts/        Windows 构建与开发启动脚本
tests/          协议、配置和源码完整性检查
```

当前安装产物中的 Web UI 以构建后的 ES 模块包提供；原始 Vue 工程没有随已安装版本保存。公开仓库保留可运行、可检查的构建产物，并在 `docs/SOURCE_PROVENANCE.md` 中说明来源和维护边界。

## 本地开发

要求：

- Windows 10/11 x64
- .NET 8 SDK
- Python 3.13 x64
- FFmpeg 7 或更高版本

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\scripts\New-LocalAccount.ps1
.\scripts\run-dev.ps1
```

也可以直接构建桌面端：

```powershell
.\scripts\build.ps1
```

构建产物位于 `artifacts/`，不会提交到 Git。

## 首次运行与账号

公开发行版和源码均不内置固定账号或密码。未配置管理员时，首次填写自定账号和
至少 8 位密码，点击登录即创建本机账号；以后使用同一账号登录。
账号只在本机验证，保存于当前用户的 `%LOCALAPPDATA%\YangJianJian\public\account.json`，
只保存随机盐和 PBKDF2-SHA256 密码哈希，升级与卸载保留该用户目录。

开发者或受管部署也可预先配置本地管理员：

```powershell
.\scripts\New-LocalAccount.ps1 -Username local-owner
```

脚本将配置写入被 Git 忽略的 `.env.local`。部署环境也可以直接设置：

```powershell
$env:YJJ_ADMIN_USER = "your-user"
$env:YJJ_ADMIN_PASSWORD_HASH = "pbkdf2_sha256$600000$..."
```

`YJJ_ADMIN_PASSWORD` 仅用于本地临时调试。正式部署应使用密码哈希。
用户填写的第三方 API 密钥、顾客项目和运行日志不进入源码仓库。

登录会话只存在于当前进程。注销或关闭应用后需要重新登录。

## AI 模型与 FFmpeg

模型和 FFmpeg 二进制不提交到 Git。应用可以在设置页下载兼容的本地模型，也可以让用户填写自己的 OpenAI 兼容服务地址、模型名和密钥。

源码运行时，将 `YJJ_FFMPEG_DIR` 指向同时包含 `ffmpeg.exe` 与
`ffprobe.exe` 的目录；也可以在应用设置中填写该目录。

模型许可证由各自发布方决定。下载前应阅读模型卡和许可证；商用、再分发和地域限制以模型提供方为准。

## 参与贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。提交问题时不要附带顾客视频、账号、API 密钥、更新私钥、项目数据库或日志中的隐私数据。

## 第三方来源

羊剪剪的交互和工程思路参考过 OpenCut、MoneyPrinterTurbo 与 REA 等开源项目。当前仓库未复制这些项目的源码；具体说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q backend tests
dotnet build .\apps\desktop\YangJianJian.Desktop.csproj -c Release
```

协议测试会启动独立 sidecar，验收启动、登录、项目创建和关闭。设置
`YJJ_FFMPEG_DIR` 后，测试还会生成合成视频并验证真实探测与缩略图。

更多实现说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，源码来源和
构建产物的边界见 [docs/SOURCE_PROVENANCE.md](docs/SOURCE_PROVENANCE.md)。

## 许可证

Copyright (c) 2026 YangJianJian contributors.

本项目采用 [MIT License](LICENSE)。
