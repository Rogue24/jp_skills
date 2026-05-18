---
name: switch-instruction-files
description: Switch and remember an alternate instruction-file source for Codex project guidance. Use when the user asks to set, use, show, switch, temp-use, or clear a directory whose files are treated as instruction files and whose AGENTS.md is the required entrypoint, especially when they want Codex to follow AGENTS.md from another directory instead of the current working directory.
---

# Switch Instruction Files

## Overview

Use this skill to switch the project-level instruction-file source for the current task. The source must be a directory containing `AGENTS.md`; every file under that directory is a potential instruction file, and the target `AGENTS.md` decides which files to read and how to use them.

This skill does not override system, developer, or current user messages. It only changes the project-level instruction files you consult while doing the user's work.

## Commands

- `set /path/to/instructions`: save this directory as the instruction-file source.
- `use`: use the saved instruction-file source.
- `show`: show the saved instruction-file source.
- `switch /path/to/instructions`: replace the saved instruction-file source.
- `temp /path/to/instructions`: use this source for the current request only, without saving it.
- `clear`: clear the saved instruction-file source.

Examples:

- `[$switch-instruction-files] set /Users/jp/Documents/jp_agents`: 设置并记住这个目录作为指令文件来源。
- `[$switch-instruction-files] use`: 使用已记住的指令文件来源，先读目标 `AGENTS.md`，再按其中说明继续工作。
- `[$switch-instruction-files] show`: 查看当前记住的是哪个指令文件来源。
- `[$switch-instruction-files] switch /Users/jp/Documents/xxx/agents`: 更换指令文件来源，并覆盖之前记住的位置。
- `[$switch-instruction-files] temp /Users/jp/Documents/jp_agents`: 只在本次对话临时使用这个来源，不修改已保存记忆。
- `[$switch-instruction-files] clear`: 清除已保存的指令文件来源，下次使用时重新询问。

## Workflow

1. Parse the user's command.
   - For `set` and `switch`, run `scripts/instruction_profile.py set <path>`.
   - For `temp`, run `scripts/instruction_profile.py temp <path>`.
   - For `use`, run `scripts/instruction_profile.py use`.
   - For `show`, run `scripts/instruction_profile.py show` and report the result; do not read instruction files unless the user also asks to work under them.
   - For `clear`, run `scripts/instruction_profile.py clear` and stop after reporting the result.
2. If no source is saved and the user asks to `use`, ask for the absolute path of the instruction-file source.
3. Accept either a directory path or a direct path to `AGENTS.md`. When the user gives `AGENTS.md`, use its parent directory as the source.
4. Validate that the source exists, is a directory, and contains `AGENTS.md`.
5. Read the target `AGENTS.md` first.
6. Treat every file under the source directory as a potential instruction file. Do not assume fixed filenames, fixed subdirectories, or a fixed reading order beyond `AGENTS.md`.
7. Continue reading only the files required by the target `AGENTS.md` or by the current task.
8. Keep code reads, code edits, commands, tests, and builds in the current real workspace unless the user explicitly asks to change the working directory.
9. When responding, mention the active instruction-file source and summarize any source-switching action performed.

## Precedence

Follow instruction priority in this order:

1. System, developer, tool, and current user instructions.
2. This skill's command semantics.
3. The active instruction-file source, beginning with its `AGENTS.md`.
4. Existing workspace conventions and target code behavior.

If the active instruction files conflict with higher-priority instructions, follow the higher-priority instruction and state the conflict briefly when it matters.

## State

The saved source is stored in `~/.codex/state/agent-instruction-files.json`.

For tests or isolated runs, set `AGENT_INSTRUCTION_FILES_CONFIG` to a temporary JSON path before running `scripts/instruction_profile.py`.
