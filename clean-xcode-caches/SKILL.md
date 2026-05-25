---
name: clean-xcode-caches
description: 检查并安全清理本机 Xcode 占用空间。适用于用户想查找或删除 Xcode 垃圾文件/缓存、清理 DerivedData、Interface Builder 模拟器支持缓存、Xcode Products、XcodeBuildMCP DerivedData，或清空模拟器中已安装 App 和数据，同时明确保留 Xcode Archives、iOS DeviceSupport、模拟器设备定义、runtime、描述文件、代码片段、快捷键和其他个人 Xcode 设置。
---

# clean-xcode-caches

## 安全边界

只用于本机 macOS/Xcode 清理。清理属于破坏性操作，执行前必须先盘点并确认保留项。

始终保留：

- `~/Library/Developer/Xcode/Archives`
- `~/Library/Developer/Xcode/iOS DeviceSupport`
- `~/Library/Developer/CoreSimulator/Devices`
- Xcode 个人设置，例如 CodeSnippets、KeyBindings、FontAndColorThemes、Provisioning Profiles

默认清理目标：

- `~/Library/Developer/Xcode/UserData/IB Support/Simulator Devices`
- `~/Library/Developer/Xcode/UserData/IB%20Support/Simulator%20Devices`
- `~/Library/Developer/Xcode/DerivedData`
- `~/Library/Developer/Xcode/Products`
- `~/Library/Developer/XcodeBuildMCP/workspaces/*/DerivedData`

清空模拟器 App 和数据时必须使用 `xcrun simctl erase all`，不要手动删除 `CoreSimulator/Devices`。这样可以保留模拟器设备定义和 runtime，同时删除已安装 App、App 沙盒、登录态、照片等模拟器数据。

## 使用流程

1. 先检查，不删除任何东西：

   ```bash
   python3 scripts/clean_xcode_caches.py
   ```

   输出当前剩余空间、待清理目标、受保护路径和预计可回收空间。

2. 用户确认清理后再执行：

   ```bash
   python3 scripts/clean_xcode_caches.py --execute
   ```

   这个命令会删除缓存目标，执行 `xcrun simctl shutdown all`，再执行 `xcrun simctl erase all`。

3. 只有用户明确要求时才调整范围：

   ```bash
   python3 scripts/clean_xcode_caches.py --execute --skip-simulator-erase
   # 清缓存，但保留模拟器里的 App 和数据

   python3 scripts/clean_xcode_caches.py --execute --skip-xcodebuildmcp
   # 清官方 Xcode 缓存，但保留 XcodeBuildMCP 的 DerivedData
   ```

4. 执行后验证：

   ```bash
   python3 scripts/clean_xcode_caches.py
   xcrun simctl list devices
   ```

   确认待清理目标已经不存在或明显变小，受保护路径仍然存在，模拟器设备仍能列出，磁盘剩余空间增加。

## Codex 执行注意事项

- 在沙箱化的 Codex 环境里，删除 `~/Library/Developer` 下的内容和抹除模拟器通常需要提权。如果删除或 `simctl` 因权限、CoreSimulatorService、日志访问问题失败，按环境规则重新用提权执行。
- 尽量先让用户关闭 Xcode 和 Simulator。即使用户没有关闭，也要先执行 `xcrun simctl shutdown all`，再执行 `xcrun simctl erase all`。
- 不要用 `rm -rf ~/Library/Developer/CoreSimulator/Devices` 完成这个清理流程。
- 除非用户明确修改保留策略，否则不要删除 Archives 或 DeviceSupport。
