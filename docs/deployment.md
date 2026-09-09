# LoreDock 部署说明

## 当前支持范围

一期只发布 Windows 本地桌面版。应用内置 LoreDock Core，不需要 Docker、系统 Python 或外部数据库，网络监听限于 `127.0.0.1`。macOS、Linux、服务器 Web 和远程 MCP 尚未完成发布验证。

## Windows 安装

MSI 与 NSIS 提供相同功能，选择一种安装即可，不要交叉覆盖。安装后从开始菜单启动 LoreDock，Core 会自动启动和停止。

用户数据默认位于 `%APPDATA%\app.loredock.desktop`，与程序文件分离。卸载程序会保留用户数据，重新安装后仍可读取。

## 覆盖升级

升级前先在设置中创建并验证备份。使用与旧版相同的安装包类型进行覆盖升级。新版本启动时会核对桌面、Core、API、数据库和索引版本；应用数据库执行受支持的前向迁移，派生索引在需要时从原件重建。

正式发布前需在一次性干净 Windows 虚拟机中分别验证 MSI 和 NSIS 的安装、启动、覆盖升级、卸载、数据保留及孤儿进程。

开发环境搭建和检查命令见[开发环境说明](development-setup.md)。
