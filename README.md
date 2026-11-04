# 微信双开重签工具（网页面板 + 原生 App）

一个纯本地的微信重签工具，点按钮即可完成，不用敲命令。
界面参考了 `multiChat` / `moveChat` 那类工具的卡片风格。

## 下载现成 App

不想自己编译？直接下载 `dist/微信双开重签工具-macOS-arm64.zip`，解压后把 `.app` 拖进「应用程序」即可。

> 本地构建的 ad-hoc 签名，从网上下载后首次打开若被 Gatekeeper 拦截，右键 →「打开」即可。

## ⚠️ 换电脑 / 兼容性注意事项（重要）

这个 `.app` **不是任意一台 Mac 都能直接跑**，需同时满足以下硬性条件：

| 条件 | 当前实际情况 | 不满足会怎样 |
|---|---|---|
| **CPU 架构** | 只编译了 `arm64`（Apple Silicon） | Intel Mac 无法运行 |
| **系统版本** | 二进制实际最低要求 **macOS 27.2**（编译 SDK 默认值；`Info.plist` 写的 12.0 只是显示值） | 更老的系统打开即报错 / 闪退 |
| **python3** | 原生 App 内部调用 `/usr/bin/python3` 启动内置服务 | 新电脑没装 Xcode Command Line Tools 时，界面显示「本地服务启动失败」 |

此外还有使用前提：

1. 新电脑需有 **`/Applications/WeChat.app`**（App 只负责重签它）。
2. **外置硬盘软链接需单独配置**：App 能自动生成「工作微信.app」（复制 + 改 bundle id + 重签），但**不会**自动把聊天记录目录软链接到外置硬盘；这一步需手动做，或改用微信自带的「存储空间 → 更改存储位置」。
3. 从网上下载的 `.app` 带 quarantine，首次打开若被 Gatekeeper 拦截，**右键 →「打开」**即可。

> 想要更广的兼容性，可重新构建：降低最低系统版本（如 `swiftc -target arm64-apple-macos12.0`）、编译成 Universal（Intel + Apple Silicon），或把 `server.py` 逻辑用 Swift 重写以彻底去掉 python3 依赖。

## 最终形态

已打包为原生 macOS App：**`/Applications/微信双开重签工具.app`**
双击打开即出现独立窗口（Swift + WKWebView），关掉窗口即退出、并自动停止内置服务。

## 两种运行方式

### 方式一：原生 App（推荐）

直接双击 `/Applications/微信双开重签工具.app`。

想重新构建：

```bash
./build-native.sh        # 生成 微信双开重签工具.app（会覆盖）
```

> 构建需要 Xcode Command Line Tools（自带 `swiftc`）。

### 方式二：本地网页

```bash
/usr/bin/python3 server.py
```

终端会打印地址（默认 `http://127.0.0.1:8899/`），浏览器打开即可。
只监听 `127.0.0.1`，不对外网开放；关闭终端即停止。

## 功能

- **微信应用**：显示主微信 / 工作微信的 bundle id、版本、签名状态
  - `App Store 沙盒版` = 更新后需要重签
  - `ad-hoc 已重签` = 可正常打开
- **聊天数据**：显示外置硬盘软链接指向
- **多开**：新建微信副本（从主微信复制 + 改 bundle id + 重签，独立数据），可创建第 3、4… 个微信
- **操作**：一键重签（主+工作）/ 只重签主微信 / 只更新工作微信 / 回滚
- **处理进度**：实时日志

## 依赖

- 系统自带 `python3`
- 同目录或上一级目录有 `resign-wechat.sh`（重签逻辑复用它）
- 构建原生 App 需要 `swiftc`（Xcode Command Line Tools）

## 目录结构

```
wechat-gui/
├── server.py          # 本地服务 + API（复用 resign-wechat.sh）
├── index.html         # 页面
├── resign-wechat.sh   # 核心重签脚本
├── start.command      # 网页版双击启动
├── build-native.sh    # 打包原生 App
├── sync.sh            # 一键同步到 GitHub
├── native/
│   ├── main.swift     # 原生壳（窗口 + WKWebView + 拉起内置服务）
│   └── Info.plist
├── dist/              # 打包好的 .app zip
└── README.md
```

> 原生 App 内置了 `server.py` / `index.html` / `resign-wechat.sh` 的副本，
> 一旦 `resign-wechat.sh` 有更新，重新跑一次 `./build-native.sh` 即可同步。

## 同步到 GitHub

日常改动后，一条命令同步本地与 GitHub：

```bash
./sync.sh                  # 使用默认提交信息
./sync.sh "feat: 改了xxx"   # 自定义提交信息
```

> 依赖已保存的 GitHub 凭据（macOS 钥匙串）。若 token 失效，直接 `git push` 时输入新 token（会自动保存）即可。

