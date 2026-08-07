# jp_skills

一些自定义的 Codex Skills，覆盖日常开发、构建发布、工程清理与文档整理等场景。

## Skills

### 日常开发

#### Instruction Source Switcher

- 技能 ID：`instruction-source-switcher`。
- 切换并记住当前项目使用的指令文件来源。
- 目标目录必须包含 `AGENTS.md`；保存后，当前项目下后续任务都会先读取该文件，再按其中说明继续读取相关指令文件。
- 不会覆盖系统、开发者或当前用户消息，只改变当前项目参考的项目级指令来源。
- 使用方式：`[$instruction-source-switcher] set /path/to/instructions`。
- 常用命令：
  - `set /path/to/instructions`：保存一个包含 `AGENTS.md` 的指令来源目录，作为当前项目后续任务的默认指令来源。
  - `use`：使用当前项目已保存的来源；如果还没保存，需要先提供目录。
  - `show`：查看并验证已保存的来源，不会自动读取指令内容继续工作。
  - `switch /path/to/instructions`：替换当前项目已保存的来源。
  - `temp /path/to/instructions`：仅本次临时使用这个来源，不修改已保存配置。
  - `clear`：清除当前项目已保存的来源，恢复使用当前目录下的默认指令文件。

#### XIB-to-Code Migration

- 技能 ID：`xib-to-code-migration`。
- 将 iOS/macOS 的 `.xib` 或 `.nib` 界面迁移为纯代码实现。
- 清理 `loadNibNamed`、`UINib`、`registerNib` 和 Xcode 工程引用。
- 默认目标是 1:1 还原界面与行为，不重新设计。
- 使用方式：`[$xib-to-code-migration] 把 XXX.xib 迁移成纯代码`。

### 构建发布

#### iOS->Pgyer->Lark

- 技能 ID：`ios-pgyer-lark`。
- 将当前 iOS 项目已经生成好的真机 `.app` 临时打成 IPA，上传到蒲公英，并发送飞书机器人通知。
- 默认优先使用 DerivedData 中已有的 device `.app`，不会主动重新编译项目；只有找不到已生成的 `.app` 时，才读取 Xcode Build Settings 定位产物。
- 飞书通知会显示当前 Git 分支，并默认包含最近 3 条 Git 提交标题；只发送标题，不发送作者、commit hash 或 diff，并会对密钥、token、webhook 和本机路径做脱敏。
- 如果 `.app` 内存在有效的 `${App名字}BuildInfo.plist`，飞书通知和结果摘要会补充构建时间。
- 如果配置了 `feishu_sender_user_id`，飞书通知和结果摘要会补充发包者。
- 发布前会做蒲公英和飞书相关域名的网络预检；生成的 IPA、二维码图片和日志会放在受控临时目录里，成功或失败后都会清理。
- 生成 IPA 前会校验原 `.app` 完整性；校验失败且已配置 `codesign_identity_hash` 时，会使用 `.app.xcent` 对原 `.app` 原地重签；缺配置或重签失败会停止发布。
- 使用方式：`[$ios-pgyer-lark] send` 或 `[$ios-pgyer-lark] 发包`；需要追加备注时可使用 `[$ios-pgyer-lark] send "备注1" "备注2"`。
- 第一次使用如果缺配置，Codex 会暂停发布流程，并按脚本提示一项一项要求输入；缓存当前项后会继续原来的发布任务，原命令里的备注会保留。
- 第一次需要输入并缓存的信息：
  - `pgy_api_key`：蒲公英 API Key。
  - `feishu_webhook_url`：飞书机器人 Webhook URL。
  - `feishu_app_id`：飞书 App ID。
  - `feishu_app_secret`：飞书 App Secret。
- 可选后续配置：
  - `codesign_identity_hash`：本机 codesign 签名证书 SHA-1 指纹，只在 `.app` 完整性校验失败、需要重签时使用。
  - `feishu_sender_user_id`：发包者飞书 user_id，发布通知会显示「发包者：@xxx」。
- 配置缓存位置：`${CODEX_HOME:-~/.codex}/skill-data/ios-pgyer-lark/config.json`；不要把真实密钥写进项目文件、README 或 skill 文件。
- 常用命令：
  - `status` / `检查`：检查蒲公英、飞书配置和当前能否找到可发布的 `.app`。
  - `send "备注1" "备注2"` / `发包 "备注1" "备注2"`：发布并在飞书通知最下面追加备注块。
  - `send --app-name MyApp`：指定要查找的 App 名称。
  - `send --app-path /path/to/MyApp.app`：使用指定的已生成 `.app` 发布。
  - `send --no-git-log`：发布但不在飞书通知里附带最近 Git 提交标题。
  - `setup --codesign-identity-hash 40位SHA1`：设置或更新本机 codesign 签名证书 SHA-1 指纹。
  - `setup --feishu-sender-user-id "user_id"`：设置或更新发包者飞书 user_id。
  - `at "user_id_1, user_id_2"` / `unat`：管理飞书通知中的 @ 人。
  - `clear --codesign-identity-hash` / `clear --feishu-sender-user-id`：只清理指定可选配置。
  - `clear`：清理全部缓存配置，包括蒲公英、飞书、@ 人、签名证书指纹和发包者信息。

### 工程清理

#### Clean Xcode Caches

- 技能 ID：`clean-xcode-caches`。
- 检查并安全清理本机 Xcode 占用空间。
- 默认清理 DerivedData、Interface Builder 模拟器支持缓存、Xcode Products 和 XcodeBuildMCP DerivedData。
- 始终保留 Xcode Archives、iOS DeviceSupport、模拟器设备定义、runtime、描述文件、代码片段、快捷键和其他个人 Xcode 设置。
- 清空模拟器 App 和数据时使用 `xcrun simctl erase all`，不手动删除 `CoreSimulator/Devices`。
- 使用方式：引用一下`[$clean-xcode-caches]`就行。

### 文档整理

#### Export Conversation to Markdown

- 技能 ID：`export-conversation-md`。
- 将当前对话总结并导出为一份规范的中文 Markdown 技术文档。
- 只保留有价值的技术讨论、结论、代码分析、方案对比与踩坑解决,自动剔除关于导出、生成技能、闲聊等元对话。
- 产出带引言区、目录锚点、分章节、Markdown 表格、带语言标注的代码块,并以 `## 总体结论` 收尾。
- 直接用 Write 手写生成 `.md`,不调用 `/export` 命令;默认写到项目根目录,文件名用能体现主题的中文短语。
- 使用方式:说"导出对话""把讨论整理成文档""总结当前对话生成文档"等,或 `[$export-conversation-md]`。
