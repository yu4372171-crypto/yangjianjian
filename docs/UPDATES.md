# 应用内更新与代码签名

公开稳定更新源：

```text
https://github.com/yu4372171-crypto/yangjianjian/releases/latest/download/latest.json
```

2026.11.10.1 起预置此地址。应用启动后自动检查；顾客选择“下载更新”，
完成后点击“安装并重启”。安装前仍会检查任务，避免在成片生成期间替换应用。
联网访问 GitHub 失败时，应用会显示错误并可重试，不会把网络错误当作已更新。

## 旧版首次接入

2026.10.27.1 等未预置公开源的版本无法自动发现一个原本不存在的地址。
在应用“检查更新 → 更新设置 → 发布地址”粘贴上述地址并保存，然后检查更新。
也可以覆盖安装新版一次。以后保持同一公开地址即可在应用内升级。
新版会忽略旧配置中空白的发布地址，同时保留顾客自己设置的有效地址和自动检查开关。

## 每次正式发布

1. 修改 `app-version.json` 和 `webui/app-release.json` 为相同的新版本。
2. 生成干净安装包；有可信证书时，先签发行者自己的应用文件，再打包、签安装包。
   第三方文件保留各自原签名。
3. 用最终安装包生成更新清单。签名会绑定版本、URL、大小、SHA-256 和说明，
   私钥必须匹配客户应用预置的公钥；错误密钥、其他下载站点和非 EXE 内容会被拒绝。
4. 在 GitHub 创建草稿版本，上传安装包、便携版、校验文件和 `latest.json`。
   验证全部上传成功后才发布，并设置为最新稳定版本。
5. 用旧客户端实际检查、下载、安装；用新客户端检查“已是最新版本”。
   验证项目、模型和顾客配置保留。

```powershell
.\.venv\Scripts\python.exe .\scripts\publish-update.py publish `
  --installer "<最终安装包路径>" `
  --version "2026.11.10.1" `
  --private-key "<仓库外的更新私钥路径>" `
  --url "https://github.com/yu4372171-crypto/yangjianjian/releases/download/v2026.11.10.1" `
  --notes-file "<更新说明文件路径>" `
  --out ".\artifacts\updates"
```

不要提交私钥，不要为常规更新更换公钥，不要覆盖已发布版本的安装包。
每个稳定版本必须带 `latest.json`，否则 GitHub 的固定地址会返回 404。
更新清单签名使用 Ed25519；它保护应用更新，与 Windows 发布者证书是两套独立机制。

## Windows Authenticode

当前发布环境尚无可用代码签名证书或已获批的托管签名身份。因此不能宣称安装包已经
获得 Windows 可信发布者签名。脚本不创建自签证书、不修改顾客信任根证书、
不关闭 SmartScreen。

取得可信代码签名证书后，将证书与私钥放在 Windows 证书存储或受控硬件中；
公开仓库只需配置指纹和 SignTool 路径：

```powershell
$env:YJJ_SIGNING_CERT_THUMBPRINT = "<证书指纹>"
$env:YJJ_SIGNTOOL = "<Windows SDK signtool.exe>"
.\scripts\Sign-WindowsRelease.ps1 -Path "<最终安装包.exe>"
.\scripts\Sign-WindowsRelease.ps1 -Path "<最终安装包.exe>" -VerifyOnly
```

脚本强制 SHA-256、RFC 3161 时间戳、证书用途与有效期、信任链验证，
并在签名后再次检查。缺证书、失效证书、自签证书或未签名文件会中止。
签名必须在生成 `.sha256` 和 `latest.json` 之前完成，否则散列会变化。

可信签名需要发行者身份验证。可评估 CA 代码签名证书或符合条件的托管签名服务；
SignPath Foundation 的免费开源计划需要独立审批、可核验的源码构建和项目资格，
并非注册 GitHub 仓库后即自动获批。任何付费申请都需由发行者确认费用。

官方资料：

- https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options
- https://learn.microsoft.com/dotnet/framework/tools/signtool-exe
- https://signpath.org/terms.html
