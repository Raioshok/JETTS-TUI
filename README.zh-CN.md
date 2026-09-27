# Jetts-TUI

Jetts-TUI 是一个以终端为核心的 AI 工作空间，包含全屏 TUI、智能体运行时、记忆、子智能体、定时任务和消息平台集成。本仓库还保留使用同一运行时的桌面端和网页端。

本页提供简明安装说明。完整且持续更新的信息请查看[英文 README](README.md)和[仓库文档](website/docs)。

## 安装

克隆或下载[本仓库](https://github.com/Raioshok/JETTS-TUI)，然后在本地运行对应的安装脚本。请勿使用其他项目域名下的安装脚本来安装 Jetts-TUI。

Linux、macOS 或 WSL2：

```bash
bash setup-jetts-tui.sh
```

Windows PowerShell：

```powershell
.\setup-jetts-tui.ps1
```

如果 PowerShell 阻止运行本地脚本，可以仅对当前进程临时放宽策略：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-jetts-tui.ps1
```

重复运行安装脚本时会复用已有环境。若暂时不配置模型提供商，在 Linux/macOS 上添加 `--skip-setup`，在 Windows 上添加 `-SkipSetup`。

## 开始使用

```bash
jetts-tui          # 打开终端界面
jetts-tui setup    # 配置提供商和工具
jetts-tui model    # 选择提供商和模型
jetts-tui doctor   # 诊断问题
```

现有的模型提供商和托管服务集成仍然保留；更名不会改变这些连接。为兼容已有安装，`FREEIDE_HOME`、`~/.freeide` 等技术名称仍然保留。

## 贡献与许可

开发说明见 [CONTRIBUTING.md](CONTRIBUTING.md)；MIT 许可和原始版权声明见 [LICENSE](LICENSE)。
