#!/usr/bin/env python3
"""检查并清理 Xcode 缓存，同时保留归档和设备信息。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    label: str
    path: Path
    required: bool = False


def size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_symlink():
                total += child.lstat().st_size
            elif child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def human_size(num: int) -> str:
    units = ["B", "K", "M", "G", "T"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}B"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}T"


def disk_free(path: Path) -> str:
    usage = shutil.disk_usage(path)
    return f"可用 {human_size(usage.free)} / 总计 {human_size(usage.total)}"


def build_targets(home: Path, include_xcodebuildmcp: bool) -> list[Target]:
    targets = [
        Target(
            "Interface Builder 模拟器支持缓存",
            home / "Library/Developer/Xcode/UserData/IB Support/Simulator Devices",
        ),
        Target(
            "Interface Builder 转义路径支持缓存",
            home / "Library/Developer/Xcode/UserData/IB%20Support/Simulator%20Devices",
        ),
        Target("Xcode DerivedData", home / "Library/Developer/Xcode/DerivedData"),
        Target("Xcode Products 缓存", home / "Library/Developer/Xcode/Products"),
    ]
    if include_xcodebuildmcp:
        workspaces = home / "Library/Developer/XcodeBuildMCP/workspaces"
        targets.extend(
            Target("XcodeBuildMCP 工作区 DerivedData", path)
            for path in sorted(workspaces.glob("*/DerivedData"))
        )
    return targets


def protected_paths(home: Path) -> list[Target]:
    return [
        Target("Xcode Archives", home / "Library/Developer/Xcode/Archives"),
        Target("iOS DeviceSupport", home / "Library/Developer/Xcode/iOS DeviceSupport"),
        Target("CoreSimulator 设备定义", home / "Library/Developer/CoreSimulator/Devices"),
        Target("代码片段", home / "Library/Developer/Xcode/UserData/CodeSnippets"),
        Target("快捷键绑定", home / "Library/Developer/Xcode/UserData/KeyBindings"),
        Target("描述文件", home / "Library/Developer/Xcode/UserData/Provisioning Profiles"),
    ]


def print_table(title: str, rows: list[Target]) -> int:
    print(f"\n{title}")
    total = 0
    for row in rows:
        size = size_bytes(row.path)
        total += size
        status = "存在" if row.path.exists() else "不存在"
        print(f"- {human_size(size):>8}  {status:<7}  {row.label}: {row.path}")
    print(f"  合计: {human_size(total)}")
    return total


def run_command(args: list[str], *, allow_failure: bool = False) -> int:
    print(f"+ {' '.join(args)}")
    result = subprocess.run(args, text=True)
    if result.returncode != 0 and not allow_failure:
        raise RuntimeError(f"命令失败，退出码 {result.returncode}: {' '.join(args)}")
    return result.returncode


def remove_target(target: Target) -> None:
    if not target.path.exists():
        print(f"跳过不存在路径: {target.path}")
        return
    print(f"删除: {target.path}")
    if target.path.is_dir() and not target.path.is_symlink():
        shutil.rmtree(target.path)
    else:
        target.path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查并清理 Xcode 缓存，同时保留 Archives、DeviceSupport 和模拟器设备定义。"
    )
    parser.add_argument("--execute", action="store_true", help="真正删除缓存目标，并清空模拟器 App 和数据。")
    parser.add_argument("--home", type=Path, default=Path.home(), help="要检查的 Home 目录，默认是当前用户 Home。")
    parser.add_argument("--skip-simulator-erase", action="store_true", help="不执行 xcrun simctl erase all。")
    parser.add_argument("--skip-xcodebuildmcp", action="store_true", help="不清理 XcodeBuildMCP 工作区 DerivedData。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    home = args.home.expanduser().resolve()
    targets = build_targets(home, include_xcodebuildmcp=not args.skip_xcodebuildmcp)
    protected = protected_paths(home)

    print(f"Home: {home}")
    print(f"清理前磁盘空间: {disk_free(home)}")
    reclaimable = print_table("待清理目标", targets)
    print_table("受保护路径", protected)
    print(f"\n预计可清理缓存大小: {human_size(reclaimable)}")

    if not args.execute:
        print("\n当前只是预览，不会删除任何东西。重新加 --execute 才会真正清理。")
        return 0

    print("\n开始执行清理...")
    for target in targets:
        remove_target(target)

    if args.skip_simulator_erase:
        print("跳过模拟器抹除")
    else:
        run_command(["xcrun", "simctl", "shutdown", "all"], allow_failure=True)
        run_command(["xcrun", "simctl", "erase", "all"])

    print(f"\n清理后磁盘空间: {disk_free(home)}")
    print_table("剩余待清理目标", targets)
    print_table("清理后的受保护路径", protected)
    if args.skip_simulator_erase:
        print("\n完成。下次启动 Xcode 时会重新生成已删除的缓存；模拟器 App 和数据没有被抹除。")
    else:
        print("\n完成。下次启动 Xcode 时会重新生成缓存，并把 App 重新安装到已抹除的模拟器中。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
