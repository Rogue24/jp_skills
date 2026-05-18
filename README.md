# jp_skills

我自定义的一些技能（for Codex）。

## Skills

### switch-instruction-files

- 切换项目的指令文件来源。
- 目标目录必须包含 `AGENTS.md`。
- 使用方式：`[$switch-instruction-files] set /path/to/instructions`。
- 常用命令：`use`、`show`、`switch`、`temp`、`clear`。

### xib-to-code-migration

- 将 iOS/macOS 的 `.xib` 或 `.nib` 界面迁移为纯代码实现。
- 清理 `loadNibNamed`、`UINib`、`registerNib` 和 Xcode 工程引用。
- 默认目标是 1:1 还原界面与行为，不重新设计。
- 使用方式：`[$xib-to-code-migration] 把 XXX.xib 迁移成纯代码`。
