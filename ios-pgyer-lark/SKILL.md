---
name: ios-pgyer-lark
description: 将当前 iOS 项目已经生成好的真机 .app 临时打成 IPA，上传到蒲公英，并发送飞书机器人通知。适用于用户说 send、发包、检查发布配置、配置蒲公英/飞书参数、管理飞书 @ 人、清理配置等场景。默认优先使用 DerivedData 中已有的 device .app，不主动重新编译。
---

# iOS 蒲公英飞书发布

## 这是干嘛的

这个技能用于把当前 iOS 项目已经生成好的真机 `.app` 临时打成 IPA，上传到蒲公英，并把二维码和下载信息发到飞书。

默认流程是：找现成 `.app` -> 生成临时 IPA -> 上传蒲公英 -> 下载二维码 -> 发飞书通知 -> 删除临时文件。

飞书通知默认包含最近 3 条 Git 提交标题，只发送标题，不发送作者、commit hash 或 diff，并会对明显的密钥、token、webhook 和本机路径做脱敏。

它不会主动重新编译项目。只有找不到已生成的 `.app` 时，才会读取 Xcode Build Settings 来定位产物。

## 技能指令用法

在 Codex 里优先这样使用：

- `[$ios-pgyer-lark] send`: 使用当前项目已生成的真机 `.app`，临时打 IPA，上传蒲公英，并发送飞书通知。
- `[$ios-pgyer-lark] 发包`: 同 `send`，发布当前项目已生成的真机 `.app`。
- `[$ios-pgyer-lark] status`: 检查蒲公英/飞书配置、飞书 @ 人，以及当前能否找到可发布的 `.app`。
- `[$ios-pgyer-lark] 检查`: 同 `status`，只检查状态，不上传、不发通知。
- `[$ios-pgyer-lark] send --app-name Falla`: 指定要找的 App 名称为 `Falla.app`，再执行发布。
- `[$ios-pgyer-lark] send --app-path /path/to/Falla.app`: 使用指定的已生成 `.app` 发布，跳过自动查找。
- `[$ios-pgyer-lark] send --no-git-log`: 发布但不在飞书通知里附带最近 Git 提交标题。
- `[$ios-pgyer-lark] at "user_id_1, user_id_2"`: 添加飞书 @ 人，之后发布通知会 @ 这些人。
- `[$ios-pgyer-lark] unat "user_id_1"`: 删除指定的飞书 @ 人。
- `[$ios-pgyer-lark] unat`: 删除全部飞书 @ 人。
- `[$ios-pgyer-lark] clear`: 清理缓存的蒲公英/飞书配置和 @ 人信息。

也可以直接说：

- `用 ios-pgyer-lark 发包`: 发布当前项目已生成的真机 `.app`。
- `用 ios-pgyer-lark 检查`: 只检查配置和可发布产物。

## 首次缺配置时的等待流程

当用户执行 `[$ios-pgyer-lark] send` / `发包`，但脚本提示 `⏸️ 发布暂停，等待补齐配置` 时，Codex 要按会话等待方式处理：

- 不要让使用者自己去终端运行 `setup` 命令。
- 不要一次性索要全部配置；按脚本输出的 `下一项` 一项一项询问。
- 询问时直接暂停当前流程，让使用者在 Codex 输入框里粘贴对应配置值。
- 收到值后，用脚本的 stdin 缓存入口写入本机缓存，不要把真实配置值写进项目文件、技能文件或最终回复。
- 缓存当前项后，重新执行原来的 `send` / `发包` 命令；如果还缺下一项，就继续按同样方式等待。
- 四项配置都补齐后，继续完成原本的打包、上传和飞书通知流程。

配置项对应关系：

- `pgy_api_key`: 蒲公英 API Key。
- `feishu_webhook_url`: 飞书机器人 Webhook URL。
- `feishu_app_id`: 飞书 App ID。
- `feishu_app_secret`: 飞书 App Secret。

收到使用者输入后，Codex 用这个入口缓存单项配置：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py setup --from-stdin pgy_api_key
```

上面的 `pgy_api_key` 要替换成脚本输出的 `下一项`。配置值通过 stdin 传入，不放在命令参数里。

## 脚本命令用法

在项目目录下直接执行：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py send --cwd "$PWD"
```

### 常用脚本命令

检查配置和可发布的 `.app`：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py status --cwd "$PWD"
```

发布到蒲公英并发送飞书通知：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py send --cwd "$PWD"
```

指定 App 名称，例如 `Falla.app`：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py send --cwd "$PWD" --app-name Falla
```

指定已经生成好的 `.app` 路径：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py send --app-path "/path/to/Falla.app"
```

发布但不附带最近 Git 提交标题：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py send --cwd "$PWD" --no-git-log
```

添加飞书 @ 人：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py at "user_id_1, user_id_2"
```

删除指定飞书 @ 人：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py unat "user_id_1"
```

删除全部飞书 @ 人：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py unat
```

清理缓存配置：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py clear
```

## 第一次使用

先检查状态：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py status --cwd "$PWD"
```

如果缺配置，脚本会提示缺哪一项。按顺序补：

```bash
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py setup --pgy-api-key "蒲公英 API Key"
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py setup --feishu-webhook-url "飞书机器人 Webhook URL"
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py setup --feishu-app-id "飞书 App ID"
python3 /Users/aa/.codex/skills/ios-pgyer-lark/scripts/publish_ios_app.py setup --feishu-app-secret "飞书 App Secret"
```

Codex 会优先使用上面的“首次缺配置时的等待流程”，让使用者在输入框里提供配置，然后缓存并继续原任务。下面这些 `setup --xxx` 命令主要保留给脚本手动使用。

不要把真实密钥写进项目文件或技能文件。脚本会把配置缓存到：

```text
${CODEX_HOME:-~/.codex}/skill-data/ios-pgyer-lark/config.json
```

缓存目录会收紧到 `700` 权限，配置文件会收紧到 `600` 权限。`status`、失败日志和普通输出只显示脱敏后的配置，不打印完整密钥、webhook 或飞书 user_id。

## 发布规则

- `send` / `发包` 会先检查配置是否完整。
- 缺配置时不要继续发布，只问用户补当前缺失项。
- 优先从 `~/Library/Developer/Xcode/DerivedData/*/Build/Products/<Configuration>-iphoneos/` 找已生成的真机 `.app`。
- 找不到 `.app` 时，才回退到 `xcodebuild -showBuildSettings` 定位产物。
- 生成的 IPA、二维码图片和日志都放在本次运行的受控临时目录里。
- 成功或失败都会删除临时目录；如果删除失败，命令会报告清理失败。
- 飞书通知默认附带最近 3 条 Git 提交标题；只发标题，并经过脱敏。使用 `--no-git-log` 可关闭。
- 原始 `.app`、DerivedData 产物、项目文件和缓存配置不会被发布流程删除。

## 输出结果

发布成功后，回复里至少包含：

- 是否成功
- App 版本号
- 构建号
- 蒲公英下载地址
- 二维码地址
- 关键日志或失败原因
