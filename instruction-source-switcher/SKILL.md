---
name: instruction-source-switcher
description: 切换、记住并使用当前项目的指令文件来源，让当前项目下的后续任务持续使用目标目录下的 AGENTS.md 和相关指令文件，直到切换或清除。适用于用户要 set、use、show、switch、temp-use 或 clear 指令来源目录，或当前项目已有保存来源、需要按该来源继续处理后续任务时。
---

# Instruction Source Switcher

## Overview

Use this skill to switch the instruction-file source for the current project. The current project is the current working directory. Once a source is saved with `set` or `switch`, later tasks in this project should use that source until it is replaced or cleared. The source must be a directory containing `AGENTS.md`; every file under that directory is a potential instruction file, and the target `AGENTS.md` decides which files to read and how to use them.

This skill does not override system, developer, or current user messages. It only changes the project-level instruction source you consult while doing the user's work in the current project. When cleared, the project falls back to the `AGENTS.md` and related instruction files in the current working directory.

## Commands

- `set /path/to/instructions`: save this directory as the current project's instruction-file source.
- `use`: use the saved project instruction-file source.
- `show`: show the saved project instruction-file source.
- `switch /path/to/instructions`: replace the saved project instruction-file source.
- `temp /path/to/instructions`: use this source for the current request only, without saving it.
- `clear`: clear the saved project instruction-file source and fall back to the current working directory's normal instruction files.

Examples:

- `[$instruction-source-switcher] set /path/to/instruction-files`: 设置并记住这个目录作为指令文件来源。
- `[$instruction-source-switcher] use`: 使用当前项目已记住的指令文件来源，先读目标 `AGENTS.md`，再按其中说明继续工作。
- `[$instruction-source-switcher] show`: 查看当前记住的是哪个指令文件来源。
- `[$instruction-source-switcher] switch /path/to/other-instruction-files`: 更换指令文件来源，并覆盖之前记住的位置。
- `[$instruction-source-switcher] temp /path/to/instruction-files`: 只在本次对话临时使用这个来源，不修改已保存记忆。
- `[$instruction-source-switcher] clear`: 清除当前项目已保存的指令文件来源，恢复使用当前目录下的默认指令文件。

## Workflow

1. Parse the user's command.
   - For `set` and `switch`, run `scripts/instruction_profile.py set <path>` and treat the validated source as the current project's persisted instruction-file source for later tasks.
   - For `temp`, run `scripts/instruction_profile.py temp <path>`.
   - For `use`, run `scripts/instruction_profile.py use`.
   - For `show`, run `scripts/instruction_profile.py show` and report the result; do not read instruction files unless the user also asks to work under them.
   - For `clear`, run `scripts/instruction_profile.py clear`, report that the project has fallen back to the current working directory's normal instruction files, and stop.
2. If no source is saved and the user asks to `use`, ask for the absolute path of the instruction-file source.
3. Accept either a directory path or a direct path to `AGENTS.md`. When the user gives `AGENTS.md`, use its parent directory as the source.
4. Validate that the source exists, is a directory, and contains `AGENTS.md`.
5. Read the target `AGENTS.md` first.
6. Treat every file under the source directory as a potential instruction file. Do not assume fixed filenames, fixed subdirectories, or a fixed reading order beyond `AGENTS.md`.
7. Continue reading only the files required by the target `AGENTS.md`, the active instruction source, or the user's task.
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

The saved source is stored per project in `~/.codex/state/agent-instruction-files.json`. The project key is the current working directory. For tests or unusual project keys, set `AGENT_INSTRUCTION_FILES_PROJECT`.

For tests or isolated runs, set `AGENT_INSTRUCTION_FILES_CONFIG` to a temporary JSON path before running `scripts/instruction_profile.py`.
