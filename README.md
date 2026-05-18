# jp_skills

我自定义的一些技能（for Codex）。

## Skills

### Instruction Source Switcher

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

### XIB-to-Code Migration

- 技能 ID：`xib-to-code-migration`。
- 将 iOS/macOS 的 `.xib` 或 `.nib` 界面迁移为纯代码实现。
- 清理 `loadNibNamed`、`UINib`、`registerNib` 和 Xcode 工程引用。
- 默认目标是 1:1 还原界面与行为，不重新设计。
- 使用方式：`[$xib-to-code-migration] 把 XXX.xib 迁移成纯代码`。
