#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path


SKILL_NAME = "ios-pgyer-lark"
REQUIRED_CONFIG = [
    "pgy_api_key",
    "feishu_webhook_url",
    "feishu_app_id",
    "feishu_app_secret",
]
CONFIG_LABELS = {
    "pgy_api_key": "蒲公英 API Key",
    "feishu_webhook_url": "飞书机器人 Webhook URL",
    "feishu_app_id": "飞书 App ID",
    "feishu_app_secret": "飞书 App Secret",
}
SECRET_CONFIG_KEYS = {"pgy_api_key", "feishu_app_secret"}
ENV_ALIASES = {
    "pgy_api_key": ["IOS_PGYER_LARK_PGY_API_KEY", "PGY_API_KEY"],
    "feishu_webhook_url": ["IOS_PGYER_LARK_FEISHU_WEBHOOK_URL", "FEISHU_WEBHOOK_URL"],
    "feishu_app_id": ["IOS_PGYER_LARK_FEISHU_APP_ID", "FEISHU_APP_ID"],
    "feishu_app_secret": ["IOS_PGYER_LARK_FEISHU_APP_SECRET", "FEISHU_APP_SECRET"],
}
APP_PATH_ENV_ALIASES = ["IOS_PGYER_LARK_APP_PATH", "APP_PATH"]
APP_NAME_ENV_ALIASES = ["IOS_PGYER_LARK_APP_NAME", "APP_NAME"]
DERIVED_DATA_ENV_ALIASES = ["IOS_PGYER_LARK_DERIVED_DATA_DIR", "DERIVED_DATA_DIR"]
RUN_DIR_PREFIX = f"{SKILL_NAME}-"
RUN_MARKER_NAME = ".ios-pgyer-lark-run.json"
INCLUDE_GIT_LOG_ENV = "IOS_PGYER_LARK_INCLUDE_GIT_LOG"


class PublishError(Exception):
    def __init__(self, stage, reason):
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


class ConfigRequired(PublishError):
    def __init__(self, missing):
        self.missing = list(missing)
        super().__init__("配置等待", "缺少配置：" + ", ".join(self.missing))


class Logger:
    def __init__(self, log_path, secrets=None):
        self.log_path = Path(log_path)
        self.lines = []
        self.secrets = [s for s in (secrets or []) if s]

    def add_secret(self, value):
        if value and value not in self.secrets:
            self.secrets.append(value)

    def redact(self, text):
        value = str(text)
        for secret in self.secrets:
            if secret:
                value = value.replace(secret, "<redacted>")
        home = str(Path.home())
        if home:
            value = value.replace(home, "~")
        replacements = [
            (r'("signature"\s*:\s*")[^"]+(")', r"\1<redacted>\2"),
            (r'("x-cos-security-token"\s*:\s*")[^"]+(")', r"\1<redacted>\2"),
            (r'("tenant_access_token"\s*:\s*")[^"]+(")', r"\1<redacted>\2"),
            (r'("app_secret"\s*:\s*")[^"]+(")', r"\1<redacted>\2"),
            (r'(_api_key=)[^&\s]+', r"\1<redacted>"),
            (r'(?i)((?:api[_-]?key|token|secret|password|app_secret)\s*[:=]\s*)[^\s,;]+', r"\1<redacted>"),
            (r'\bsk-[A-Za-z0-9._-]+\b', r"<redacted>"),
            (r'(Bearer\s+)[A-Za-z0-9._-]+', r"\1<redacted>"),
            (r'(bot/v2/hook/)[A-Za-z0-9-]+', r"\1<redacted>"),
        ]
        for pattern, replacement in replacements:
            value = re.sub(pattern, replacement, value)
        return value

    def log(self, message=""):
        safe = self.redact(message)
        print(safe)
        self.lines.append(safe)
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(safe + "\n")
        except OSError:
            pass

    def tail(self, count=8):
        return self.lines[-count:]

    def log_memory(self, message=""):
        safe = self.redact(message)
        print(safe)
        self.lines.append(safe)


def temp_root():
    return Path(tempfile.gettempdir()).resolve()


def safe_temp_child(path, prefix=None, suffix=None):
    resolved = Path(path).expanduser().resolve(strict=False)
    root = temp_root()
    if resolved.parent != root:
        return None
    if prefix and not resolved.name.startswith(prefix):
        return None
    if suffix and not resolved.name.endswith(suffix):
        return None
    return resolved


def chmod_and_retry(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        func(path)
    except OSError:
        raise exc_info[1]


def rmtree_checked(path):
    path = Path(path)
    if not path.exists():
        return
    shutil.rmtree(path, onerror=chmod_and_retry)
    if path.exists():
        raise OSError(f"删除后路径仍存在：{path}")


def cleanup_temp_tree(path, prefix=None, suffix=None):
    safe_path = safe_temp_child(path, prefix=prefix, suffix=suffix)
    if not safe_path:
        raise PublishError("清理临时文件", f"拒绝清理非受控临时路径：{path}")
    rmtree_checked(safe_path)
    return safe_path


def write_run_marker(run_dir):
    marker = Path(run_dir) / RUN_MARKER_NAME
    marker.write_text(json.dumps({"pid": os.getpid(), "created": time.time()}), encoding="utf-8")


def marker_pid(path):
    marker = Path(path) / RUN_MARKER_NAME
    if not marker.exists():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return int(payload.get("pid"))
    except (TypeError, ValueError):
        return None


def process_is_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def cleanup_stale_run_dirs(exclude=None):
    root = temp_root()
    excluded = Path(exclude).resolve(strict=False) if exclude else None
    for path in root.glob(f"{RUN_DIR_PREFIX}*"):
        safe_path = safe_temp_child(path, prefix=RUN_DIR_PREFIX)
        if not safe_path or (excluded and safe_path == excluded):
            continue
        pid = marker_pid(safe_path)
        if pid and pid != os.getpid() and process_is_alive(pid):
            continue
        try:
            cleanup_temp_tree(safe_path, prefix=RUN_DIR_PREFIX)
        except PublishError as exc:
            print(f"⚠️ 清理历史临时目录失败：{exc.reason}")


def cleanup_run_dir(run_dir, logger=None):
    if not run_dir:
        return
    safe_path = safe_temp_child(run_dir, prefix=RUN_DIR_PREFIX)
    if not safe_path:
        raise PublishError("清理临时文件", f"拒绝清理非本次临时目录：{run_dir}")
    if not safe_path.exists():
        return
    if logger:
        logger.log(f"清理临时目录: {safe_path}")
    cleanup_temp_tree(safe_path, prefix=RUN_DIR_PREFIX)
    if logger:
        logger.log_memory("临时目录已清理")


def xcode_result_bundle_paths(text):
    paths = []
    for line in str(text).splitlines():
        match = re.search(r"Writing error result bundle to (.+?\.xcresult)", line)
        if match:
            paths.append(match.group(1).strip())
    return paths


def cleanup_xcode_result_bundles(text):
    notes = []
    for path in xcode_result_bundle_paths(text):
        try:
            safe_path = cleanup_temp_tree(path, prefix="ResultBundle_", suffix=".xcresult")
            notes.append(f"已清理 Xcode 错误结果包: {safe_path}")
        except PublishError as exc:
            notes.append(f"Xcode 错误结果包清理失败: {exc.reason}")
    return notes


def config_dir_from_args(args):
    if getattr(args, "config_dir", None):
        return Path(args.config_dir).expanduser()
    if os.environ.get("IOS_PGYER_LARK_CONFIG_DIR"):
        return Path(os.environ["IOS_PGYER_LARK_CONFIG_DIR"]).expanduser()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "skill-data" / SKILL_NAME


def config_path(args):
    return config_dir_from_args(args) / "config.json"


def harden_existing_config_path(path):
    if path.is_symlink():
        raise PublishError("保护配置", f"配置文件不能是符号链接：{path}")
    if path.parent.exists():
        try:
            current_mode = stat.S_IMODE(path.parent.stat().st_mode)
            if current_mode & 0o077:
                os.chmod(path.parent, 0o700)
        except OSError as exc:
            raise PublishError("保护配置", f"配置目录权限无法收紧：{exc}") from exc
    if path.exists():
        try:
            current_mode = stat.S_IMODE(path.stat().st_mode)
            if current_mode & 0o077:
                os.chmod(path, 0o600)
        except OSError as exc:
            raise PublishError("保护配置", f"配置文件权限无法收紧：{exc}") from exc


def ensure_config_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def load_config(args):
    path = config_path(args)
    harden_existing_config_path(path)
    if not path.exists():
        return {"feishu_at_user_ids": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError("读取配置", f"配置文件无法读取：{exc}") from exc
    if not isinstance(data, dict):
        raise PublishError("读取配置", "配置文件格式不是 JSON 对象")
    if not isinstance(data.get("feishu_at_user_ids"), list):
        data["feishu_at_user_ids"] = []
    return data


def save_config(args, data):
    path = config_path(args)
    harden_existing_config_path(path)
    ensure_config_dir(path.parent)
    cleaned = dict(data)
    cleaned["feishu_at_user_ids"] = unique_ids(cleaned.get("feishu_at_user_ids", []))
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(cleaned, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(tmp_path, 0o600)
    tmp_path.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def clear_config(args):
    path = config_path(args)
    if path.exists():
        path.unlink()
        print(f"已清理配置: {display_path(path)}")
    else:
        print(f"配置不存在，无需清理: {display_path(path)}")


def mask(value):
    if not value:
        return "未配置"
    text = str(value)
    if len(text) <= 8:
        return text[0:1] + "***" + text[-1:]
    return text[:4] + "***" + text[-4:]


def mask_list(values):
    return [mask(value) for value in unique_ids(values)]


def display_path(path):
    value = str(path)
    home = str(Path.home())
    if home:
        value = value.replace(home, "~")
    return value


def env_truthy(name):
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def env_value(key):
    for env_name in ENV_ALIASES[key]:
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def first_env_value(names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def prompt_value(label, existing="", secret=False):
    suffix = f"（当前: {mask(existing)}，直接回车保留）" if existing else ""
    prompt = f"{label}{suffix}: "
    if secret:
        value = getpass.getpass(prompt)
    else:
        value = input(prompt)
    if value:
        return value.strip()
    return existing


def read_stdin_config_value(label, secret=False):
    print(f"等待输入 {label}，收到后会写入本机缓存。")
    if sys.stdin.isatty():
        value = getpass.getpass(f"{label}: " if secret else f"{label}: ")
    else:
        value = sys.stdin.readline()
    return value.strip()


def setup_config(args):
    cfg = load_config(args)
    updates = {
        "pgy_api_key": getattr(args, "pgy_api_key", None),
        "feishu_webhook_url": getattr(args, "feishu_webhook_url", None),
        "feishu_app_id": getattr(args, "feishu_app_id", None),
        "feishu_app_secret": getattr(args, "feishu_app_secret", None),
    }
    for key, value in updates.items():
        if value:
            cfg[key] = value.strip()

    stdin_key = getattr(args, "from_stdin", None)
    if stdin_key:
        value = read_stdin_config_value(CONFIG_LABELS[stdin_key], secret=stdin_key in SECRET_CONFIG_KEYS)
        if not value:
            raise PublishError("配置", f"{CONFIG_LABELS[stdin_key]} 不能为空")
        cfg[stdin_key] = value

    if sys.stdin.isatty() and not stdin_key:
        for key in REQUIRED_CONFIG:
            cfg[key] = prompt_value(CONFIG_LABELS[key], cfg.get(key, ""), secret=key in SECRET_CONFIG_KEYS)

    if not any(updates.values()) and not stdin_key and not sys.stdin.isatty():
        missing = [key for key in REQUIRED_CONFIG if not cfg.get(key)]
        if missing:
            raise PublishError("配置", "非交互环境缺少配置，请用 setup 参数传入：" + ", ".join(missing))

    save_config(args, cfg)
    print(f"配置已缓存: {config_path(args)}")
    print_status(args, discover=False)


def ensure_required_config(args):
    cfg = load_config(args)
    changed = False
    for key in REQUIRED_CONFIG:
        if not cfg.get(key):
            value = env_value(key)
            if value:
                cfg[key] = value
                changed = True
    missing = [key for key in REQUIRED_CONFIG if not cfg.get(key)]
    if missing and sys.stdin.isatty():
        print("发布前需要补齐配置。")
        for key in missing:
            cfg[key] = prompt_value(CONFIG_LABELS[key], "", secret=key in SECRET_CONFIG_KEYS)
            changed = True
        missing = [key for key in REQUIRED_CONFIG if not cfg.get(key)]
    if missing:
        raise ConfigRequired(missing)
    if changed:
        save_config(args, cfg)
    return cfg


def parse_user_ids(raw_items):
    raw = " ".join(raw_items or []).strip()
    if not raw:
        return []
    parts = []
    for item in raw.split(","):
        value = item.strip().strip('"').strip("'")
        if value:
            parts.append(value)
    return unique_ids(parts)


def unique_ids(items):
    result = []
    seen = set()
    for item in items or []:
        value = str(item).strip()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def add_mentions(args):
    ids = parse_user_ids(args.user_ids)
    if not ids:
        raise PublishError("@人", "请传入一个或多个飞书 user_id，例如：at \"xxxx, yyyy\"")
    cfg = load_config(args)
    before = unique_ids(cfg.get("feishu_at_user_ids", []))
    cfg["feishu_at_user_ids"] = unique_ids(before + ids)
    save_config(args, cfg)
    added = [item for item in ids if item not in before]
    print("已添加 @ 人: " + (", ".join(mask_list(added)) if added else "无新增，均已存在"))
    print("当前 @ 人: " + (", ".join(mask_list(cfg["feishu_at_user_ids"])) or "无"))


def remove_mentions(args):
    cfg = load_config(args)
    current = unique_ids(cfg.get("feishu_at_user_ids", []))
    ids = parse_user_ids(args.user_ids)
    if not ids:
        cfg["feishu_at_user_ids"] = []
        save_config(args, cfg)
        print("已删除全部 @ 人")
        return
    remove_set = set(ids)
    cfg["feishu_at_user_ids"] = [item for item in current if item not in remove_set]
    save_config(args, cfg)
    print("已删除 @ 人: " + ", ".join(mask_list(ids)))
    print("当前 @ 人: " + (", ".join(mask_list(cfg["feishu_at_user_ids"])) or "无"))


def find_repo_root(cwd):
    path = Path(cwd).expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    return path


def is_skipped_project_path(path):
    skipped = {"Pods", "Carthage", "DerivedData", ".build", "build", "Build", "node_modules"}
    package_suffixes = (".app", ".appex", ".bundle", ".framework", ".xcarchive", ".xcodeproj", ".xcworkspace")
    return any(part in skipped or part.endswith(package_suffixes) for part in path.parts[:-1])


def xcode_containers(root):
    workspaces = []
    projects = []
    for pattern in ("*.xcworkspace", "*.xcodeproj"):
        for path in root.rglob(pattern):
            if is_skipped_project_path(path):
                continue
            stem = path.stem
            if not stem or stem == "Pods":
                continue
            if path.suffix == ".xcworkspace":
                workspaces.append(path)
            else:
                projects.append(path)
    selected = workspaces or projects
    return sorted(selected, key=lambda item: str(item))


def discover_project(cwd):
    root = find_repo_root(cwd)
    containers = xcode_containers(root)
    if not containers:
        raise PublishError("产物发现", f"当前项目未找到 .xcworkspace 或 .xcodeproj：{root}")
    if len(containers) > 1:
        names = [str(path.relative_to(root)) for path in containers]
        raise PublishError("产物发现", "发现多个 Xcode 项目，无法自动确定归属：" + ", ".join(names))
    return root, containers[0]


def container_args(container):
    flag = "-workspace" if container.suffix == ".xcworkspace" else "-project"
    return [flag, str(container)]


def xcode_working_dir(root, container):
    if container.parent.exists():
        return container.parent
    return root


def xcodebuild(args, cwd, stage):
    try:
        result = subprocess.run(
            ["xcodebuild", *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise PublishError(stage, f"xcodebuild 无法执行：{exc}") from exc
    if result.returncode != 0:
        detail = "\n".join(
            line.strip()
            for line in (result.stderr + "\n" + result.stdout).splitlines()
            if line.strip()
        )
        cleanup_notes = cleanup_xcode_result_bundles(detail)
        if cleanup_notes:
            detail = detail + "\n" + "\n".join(cleanup_notes)
        raise PublishError(stage, detail[-1000:] or f"xcodebuild 退出码 {result.returncode}")
    return result.stdout


def list_schemes(root, container):
    output = xcodebuild(
        ["-list", "-json", *container_args(container)],
        xcode_working_dir(root, container),
        "读取 Xcode Scheme",
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise PublishError("读取 Xcode Scheme", "xcodebuild -list -json 输出不是合法 JSON") from exc
    data = payload.get("workspace") or payload.get("project") or {}
    schemes = data.get("schemes") or []
    return [str(item) for item in schemes if str(item).strip()]


def choose_scheme(args, root, container):
    explicit = getattr(args, "scheme", None) or os.environ.get("IOS_PGYER_LARK_SCHEME")
    if explicit:
        return explicit
    schemes = list_schemes(root, container)
    preferred = [container.stem, root.name]
    for name in preferred:
        if name in schemes:
            return name
    if len(schemes) == 1:
        return schemes[0]
    if not schemes:
        raise PublishError("读取 Xcode Scheme", f"未从 {container.name} 读取到可用 scheme")
    raise PublishError("读取 Xcode Scheme", "发现多个 scheme，无法自动确定：" + ", ".join(schemes))


def parse_build_settings(output):
    settings = {}
    for line in output.splitlines():
        match = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.*)$", line)
        if match:
            settings[match.group(1)] = match.group(2).strip()
    return settings


def build_configuration(args):
    return getattr(args, "configuration", None) or os.environ.get("IOS_PGYER_LARK_CONFIGURATION") or "Debug"


def validate_app_path(app_path, stage="产物发现"):
    path = Path(app_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    if path.suffix != ".app":
        raise PublishError(stage, f"指定产物不是 .app：{path}")
    if not path.exists():
        raise PublishError(stage, f"指定 App 不存在：{path}")
    if not path.is_dir():
        raise PublishError(stage, f"指定 App 不是目录：{path}")
    return path


def explicit_app_path(args):
    raw = getattr(args, "app_path", None) or first_env_value(APP_PATH_ENV_ALIASES)
    if not raw:
        return None
    return validate_app_path(raw)


def app_name_candidates(args, root, container):
    names = []
    explicit_app_name = getattr(args, "app_name", None) or first_env_value(APP_NAME_ENV_ALIASES)
    explicit_scheme = getattr(args, "scheme", None) or os.environ.get("IOS_PGYER_LARK_SCHEME")
    for value in [explicit_app_name, explicit_scheme, container.stem, root.name, Path(getattr(args, "cwd", "")).name]:
        if value and value not in names and value != "Pods":
            names.append(value)
    return names


def derived_data_roots():
    roots = []
    explicit = first_env_value(DERIVED_DATA_ENV_ALIASES)
    for value in [explicit, str(Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData")]:
        if not value:
            continue
        path = Path(value).expanduser()
        if path.exists() and path not in roots:
            roots.append(path)
    return roots


def app_configuration(app_path):
    parent_name = app_path.parent.name
    if parent_name.endswith("-iphoneos"):
        return parent_name[:-len("-iphoneos")]
    return ""


def is_generated_device_app(app_path, configuration):
    parts = set(app_path.parts)
    if "Index.noindex" in parts:
        return False
    parent_name = app_path.parent.name
    if not parent_name.endswith("-iphoneos"):
        return False
    if configuration and parent_name != f"{configuration}-iphoneos":
        return False
    path_text = str(app_path)
    return "/Build/Products/" in path_text


def find_latest_generated_app(args, root, container):
    selected = explicit_app_path(args)
    if selected:
        return {
            "root": root,
            "container": container,
            "scheme": getattr(args, "scheme", None) or selected.stem,
            "configuration": app_configuration(selected) or build_configuration(args),
            "app_path": selected,
            "product_name": selected.stem,
            "discovery": "指定 App 路径",
        }

    configuration = build_configuration(args)
    candidates = []
    for derived_root in derived_data_roots():
        for app_name in app_name_candidates(args, root, container):
            pattern = f"*/Build/Products/{configuration}-iphoneos/{app_name}.app"
            for app_path in derived_root.glob(pattern):
                if is_generated_device_app(app_path, configuration) and app_path.is_dir():
                    candidates.append(app_path)
    if not candidates:
        return None

    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return {
        "root": root,
        "container": container,
        "scheme": getattr(args, "scheme", None) or latest.stem,
        "configuration": app_configuration(latest) or configuration,
        "app_path": latest,
        "product_name": latest.stem,
        "discovery": "DerivedData 已生成 App 快速路径",
    }


def discover_app_from_build_settings(args, root, container):
    scheme = choose_scheme(args, root, container)
    configuration = getattr(args, "configuration", None) or os.environ.get("IOS_PGYER_LARK_CONFIGURATION") or "Debug"
    output = xcodebuild(
        [
            *container_args(container),
            "-scheme",
            scheme,
            "-configuration",
            configuration,
            "-sdk",
            "iphoneos",
            "-showBuildSettings",
        ],
        xcode_working_dir(root, container),
        "读取 Xcode Build Settings",
    )
    settings = parse_build_settings(output)
    product_type = settings.get("PRODUCT_TYPE", "")
    if product_type and product_type != "com.apple.product-type.application":
        raise PublishError("产物发现", f"scheme {scheme} 的 PRODUCT_TYPE 不是 iOS App：{product_type}")

    app_value = settings.get("CODESIGNING_FOLDER_PATH")
    if not app_value:
        build_dir = settings.get("TARGET_BUILD_DIR") or settings.get("BUILT_PRODUCTS_DIR")
        wrapper_name = settings.get("WRAPPER_NAME")
        if build_dir and wrapper_name:
            app_value = str(Path(build_dir) / wrapper_name)
    if not app_value:
        raise PublishError("产物发现", "Xcode build settings 中缺少 CODESIGNING_FOLDER_PATH 或 TARGET_BUILD_DIR/WRAPPER_NAME")

    app_path = Path(app_value).expanduser()
    if not app_path.is_absolute():
        app_path = (root / app_path).resolve()
    if app_path.suffix != ".app":
        raise PublishError("产物发现", f"项目设定得到的产物不是 .app：{app_path}")
    if not app_path.exists():
        raise PublishError("产物发现", f"项目设定的真机 App 不存在：{app_path}。请先用 Xcode 为真机完成一次 Build。")
    if not app_path.is_dir():
        raise PublishError("产物发现", f"项目设定的 App 不是目录：{app_path}")

    return {
        "root": root,
        "container": container,
        "scheme": scheme,
        "configuration": configuration,
        "app_path": app_path,
        "product_name": settings.get("PRODUCT_NAME") or app_path.stem,
        "discovery": "Xcode Build Settings 回退路径",
    }


def discover_app(args):
    root, container = discover_project(getattr(args, "cwd", os.getcwd()))
    generated = find_latest_generated_app(args, root, container)
    if generated:
        return generated
    return discover_app_from_build_settings(args, root, container)


def zip_path(zip_file, path, arcname):
    if path.is_symlink():
        info = zipfile.ZipInfo(str(arcname))
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zip_file.writestr(info, os.readlink(path))
        return
    zip_file.write(path, arcname)


def make_ipa_from_app(app_path, run_dir, logger):
    ipa_path = run_dir / f"{app_path.stem}.ipa"
    logger.log(f"App 路径: {app_path}")
    logger.log(f"生成临时 IPA: {ipa_path}")
    try:
        with zipfile.ZipFile(ipa_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            payload_root = Path("Payload")
            for path in [app_path, *app_path.rglob("*")]:
                arcname = payload_root / path.relative_to(app_path.parent)
                zip_path(archive, path, arcname)
    except OSError as exc:
        raise PublishError("生成 IPA", f"生成临时 IPA 失败：{exc}") from exc
    if not ipa_path.exists():
        raise PublishError("生成 IPA", "临时 IPA 未生成")
    logger.log(f"临时 IPA 已生成: {ipa_path}")
    return ipa_path


def http_request(url, method="GET", data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise PublishError("网络请求", str(exc.reason)) from exc


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    status, body = http_request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return status, body.decode("utf-8", errors="replace")


def post_json(url, payload, headers=None):
    merged_headers = {"Content-Type": "application/json"}
    merged_headers.update(headers or {})
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, body = http_request(url, method="POST", data=data, headers=merged_headers)
    return status, body.decode("utf-8", errors="replace")


def multipart_body(fields, files):
    boundary = "----ios-pgyer-lark-" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode(),
            b"\r\n",
        ])
    for field, file_path, content_type in files:
        path = Path(file_path)
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(chunks)


def post_multipart(url, fields, files, headers=None):
    boundary, body = multipart_body(fields, files)
    merged_headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    merged_headers.update(headers or {})
    return http_request(url, method="POST", data=body, headers=merged_headers)


def parse_json(text, stage):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PublishError(stage, f"响应不是合法 JSON：{text[:300]}") from exc


def upload_to_pgyer(ipa_path, cfg, logger):
    app_name = ipa_path.stem
    logger.log(f"开始上传 {app_name}.ipa 到蒲公英...")
    logger.log("步骤1: 获取上传Token...")
    status, token_text = post_form(
        "http://api.pgyer.com/apiv2/app/getCOSToken",
        {"_api_key": cfg["pgy_api_key"], "buildType": "ipa"},
    )
    if status != 200:
        raise PublishError("获取上传Token", f"HTTP 状态码 {status}")
    logger.log("Token响应: " + token_text)
    token = parse_json(token_text, "获取上传Token")
    data = token.get("data") or {}
    params = data.get("params") or {}
    endpoint = data.get("endpoint")
    key = params.get("key") or data.get("key")
    signature = params.get("signature")
    security_token = params.get("x-cos-security-token")
    if not all([endpoint, key, signature, security_token]):
        raise PublishError("获取上传Token", "蒲公英响应缺少 endpoint/key/signature/x-cos-security-token")

    logger.log("步骤2: 上传文件到蒲公英...")
    status, body = post_multipart(
        endpoint,
        {
            "key": key,
            "signature": signature,
            "x-cos-security-token": security_token,
            "x-cos-meta-file-name": ipa_path.name,
        },
        [("file", ipa_path, "application/octet-stream")],
    )
    if status != 204:
        detail = body.decode("utf-8", errors="replace")[:300]
        raise PublishError("上传文件到蒲公英", f"HTTP 状态码 {status}，响应：{detail}")
    logger.log("文件上传成功（HTTP 204）")

    logger.log("步骤3: 检查构建结果...")
    upload_result = None
    code = None
    for index in range(1, 61):
        url = "http://api.pgyer.com/apiv2/app/buildInfo?" + urllib.parse.urlencode(
            {"_api_key": cfg["pgy_api_key"], "buildKey": key}
        )
        status, body = http_request(url)
        text = body.decode("utf-8", errors="replace")
        if status != 200:
            logger.log(f"检查构建状态... (尝试 {index}/60)，HTTP {status}: {text[:300]}")
            time.sleep(1)
            continue
        upload_result = parse_json(text, "检查构建结果")
        code = str(upload_result.get("code"))
        if code == "0":
            logger.log("上传成功！")
            break
        logger.log(f"检查构建状态... (尝试 {index}/60)，响应: {text}")
        time.sleep(1)
    if code != "0" or not upload_result:
        raise PublishError("检查构建结果", "轮询构建结果超时")

    result_text = json.dumps(upload_result, ensure_ascii=False, separators=(",", ":"))
    logger.log("上传完成，结果如下：")
    logger.log(result_text)
    build = upload_result.get("data") or {}
    shortcut = build.get("buildShortcutUrl")
    if not shortcut:
        raise PublishError("解析上传结果", "蒲公英响应缺少 buildShortcutUrl")
    qr_url = f"https://www.pgyer.com/app/qrcode/{shortcut}"
    logger.log(f"蒲公英下载地址: https://www.pgyer.com/{shortcut}")
    logger.log(f"蒲公英二维码地址: {qr_url}")
    return build, qr_url


def feishu_tenant_token(cfg, logger):
    status, text = post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": cfg["feishu_app_id"], "app_secret": cfg["feishu_app_secret"]},
    )
    if status != 200:
        raise PublishError("获取飞书 tenant_access_token", f"HTTP 状态码 {status}")
    payload = parse_json(text, "获取飞书 tenant_access_token")
    if str(payload.get("code")) != "0":
        raise PublishError("获取飞书 tenant_access_token", f"code: {payload.get('code')}")
    token = payload.get("tenant_access_token")
    if not token:
        raise PublishError("获取飞书 tenant_access_token", "tenant_access_token 为空")
    logger.add_secret(token)
    return token


def upload_feishu_image(token, image_path):
    status, body = post_multipart(
        "https://open.feishu.cn/open-apis/im/v1/images",
        {"image_type": "message"},
        [("image", image_path, "image/png")],
        headers={"Authorization": f"Bearer {token}"},
    )
    text = body.decode("utf-8", errors="replace")
    if status != 200:
        raise PublishError("上传图片到飞书", f"HTTP 状态码 {status}")
    payload = parse_json(text, "上传图片到飞书")
    if str(payload.get("code")) != "0":
        raise PublishError("上传图片到飞书", f"code: {payload.get('code')}")
    image_key = (payload.get("data") or {}).get("image_key")
    if not image_key:
        raise PublishError("上传图片到飞书", "image_key 为空")
    return image_key


def send_feishu_payload(cfg, payload):
    status, text = post_json(cfg["feishu_webhook_url"], payload)
    if status != 200:
        raise PublishError("发送飞书消息", f"HTTP 状态码 {status}")
    result = parse_json(text, "发送飞书消息")
    status_code = result.get("code", result.get("StatusCode", "0"))
    if str(status_code) != "0":
        raise PublishError("发送飞书消息", f"code: {status_code}")


def send_feishu_image(cfg, image_key):
    send_feishu_payload(
        cfg,
        {"msg_type": "image", "content": {"image_key": image_key}},
    )


def mention_text(user_ids):
    ids = unique_ids(user_ids)
    return " ".join([f'<at user_id="{user_id}"></at>' for user_id in ids])


def git_logs(repo_root, logger=None):
    try:
        result = subprocess.run(
            ["git", "log", "-3", "--pretty=format:-> %s"],
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "-> 未获取到 git 日志"
    output = result.stdout.strip() or "-> 未获取到 git 日志"
    if logger:
        return "\n".join(logger.redact(line) for line in output.splitlines())
    return output


def send_feishu_notification(cfg, build, qr_url, qr_path, repo_root, logger, include_git_log=True):
    logger.log("下载二维码图片...")
    status, body = http_request(qr_url)
    if status != 200:
        raise PublishError("下载二维码图片", f"HTTP 状态码 {status}")
    qr_path.write_bytes(body)

    token = feishu_tenant_token(cfg, logger)
    image_key = upload_feishu_image(token, qr_path)
    send_feishu_image(cfg, image_key)

    build_name = build.get("buildName") or "App"
    build_version = build.get("buildVersion") or ""
    version_no = build.get("buildVersionNo") or ""
    build_version_no = build.get("buildBuildVersion") or ""
    shortcut = build.get("buildShortcutUrl") or ""
    title = f"{build_name} 有新版本啦~ ↑"
    body_text = (
        f"版本号: {build_version}({version_no}_{build_version_no})\n"
        f"更新时间：{time.strftime('%Y-%m-%d %H:%M')}\n"
        f"蒲公英下载地址: https://www.pgyer.com/{shortcut}\n"
        f"蒲公英二维码地址: {qr_url}"
    )
    if include_git_log:
        body_text = body_text + f"\n\n最近 Git 提交:\n{git_logs(repo_root, logger)}"
    mentions = mention_text(cfg.get("feishu_at_user_ids", []))
    if mentions:
        body_text = body_text + "\n" + mentions
    send_feishu_payload(
        cfg,
        {"msg_type": "text", "content": {"text": f"{title}\n{body_text}"}},
    )


def run_send(args):
    cleanup_stale_run_dirs()
    cfg = ensure_required_config(args)
    run_dir = Path(tempfile.mkdtemp(prefix=RUN_DIR_PREFIX))
    write_run_marker(run_dir)
    logger = Logger(run_dir / "publish.log", [cfg.get(key) for key in REQUIRED_CONFIG])
    publish_error = None
    cleanup_error = None
    try:
        start = time.monotonic()
        artifact = discover_app(args)
        logger.log(f"产物发现耗时: {time.monotonic() - start:.2f}s")
        logger.log(f"当前项目: {artifact['container'].stem} ({artifact['root']})")
        logger.log(f"Xcode 容器: {artifact['container']}")
        logger.log(f"Scheme: {artifact['scheme']}")
        logger.log(f"Configuration: {artifact['configuration']}")
        logger.log(f"产物发现方式: {artifact.get('discovery', '未知')}")
        ipa_path = make_ipa_from_app(artifact["app_path"], run_dir, logger)
        build, qr_url = upload_to_pgyer(ipa_path, cfg, logger)
        send_feishu_notification(
            cfg,
            build,
            qr_url,
            run_dir / "temp_qr_img.png",
            artifact["root"],
            logger,
            include_git_log=not getattr(args, "no_git_log", False),
        )
        logger.log("✅ 打包并通知完成")
    except PublishError as exc:
        publish_error = exc
    finally:
        try:
            cleanup_run_dir(run_dir, logger)
            cleanup_stale_run_dirs()
        except PublishError as exc:
            cleanup_error = exc

    if publish_error:
        print_failure(publish_error, logger)
        if cleanup_error:
            print_failure(cleanup_error, logger)
        raise SystemExit(1) from publish_error
    if cleanup_error:
        print_failure(cleanup_error, logger)
        raise SystemExit(1) from cleanup_error


def print_failure(exc, logger=None):
    print("❌ 打包失败")
    print(f"阶段: {exc.stage}")
    reason = logger.redact(exc.reason) if logger else str(exc.reason)
    print(f"原因: {reason}")
    lines = logger.tail() if logger else []
    if lines:
        print("关键日志:")
        for line in lines:
            if line.strip():
                print(f"- {line}")


def print_config_required(exc):
    print("⏸️ 发布暂停，等待补齐配置")
    print("缺少配置: " + ", ".join(exc.missing))
    next_key = exc.missing[0]
    print(f"下一项: {next_key}（{CONFIG_LABELS[next_key]}）")
    print(f"缓存入口: setup --from-stdin {next_key}")
    print("请 Codex 暂停并只向使用者询问这一项，收到后用 stdin 缓存，再继续原流程。")


def print_status(args, discover=True):
    cfg = load_config(args)
    print(f"配置文件: {display_path(config_path(args))}")
    for key in REQUIRED_CONFIG:
        print(f"{key}: {mask(cfg.get(key))}")
    ids = unique_ids(cfg.get("feishu_at_user_ids", []))
    print("feishu_at_user_ids: " + (", ".join(mask_list(ids)) if ids else "无"))
    if discover:
        try:
            artifact = discover_app(args)
            print(f"当前项目: {artifact['container'].stem} ({display_path(artifact['root'])})")
            print(f"Xcode 容器: {display_path(artifact['container'])}")
            print(f"Scheme: {artifact['scheme']}")
            print(f"Configuration: {artifact['configuration']}")
            print(f"产物发现方式: {artifact.get('discovery', '未知')}")
            print(f"可发布 App: {display_path(artifact['app_path'])}")
            print("临时 IPA: send / 发包 时自动生成并在结束后清理")
        except PublishError as exc:
            print(f"可发布 App: 未确定（{exc.reason}）")


def build_parser():
    aliases = {
        "发包": "send",
        "配置": "setup",
        "检查": "status",
        "清理": "clear",
        "@人": "at",
        "删@": "unat",
    }
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config-dir",
        default=argparse.SUPPRESS,
        help="覆盖配置目录，主要用于测试或隔离环境",
    )

    parser = argparse.ArgumentParser(description="把当前 iOS 项目已生成的真机 .app 临时打成 IPA，上传蒲公英并通知飞书")
    parser.add_argument(
        "--config-dir",
        default=argparse.SUPPRESS,
        help="覆盖配置目录，主要用于测试或隔离环境",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send", aliases=["发包"], parents=[common], help="发布已发现的 iOS App")
    send.add_argument("--cwd", default=os.getcwd(), help="用于发现产物的项目目录")
    send.add_argument("--scheme", default=None, help="指定 Xcode scheme，可选")
    send.add_argument("--app-name", default=None, help="指定已生成的 .app 名称，不带 .app 后缀")
    send.add_argument("--app-path", default=None, help="指定已经生成好的 .app 路径")
    send.add_argument("--no-git-log", action="store_true", help="飞书通知中不附带最近 Git 提交标题")
    send.add_argument(
        "--configuration",
        default=os.environ.get("IOS_PGYER_LARK_CONFIGURATION", "Debug"),
        help="用于查找已生成 .app 的构建配置，默认 Debug",
    )
    send.set_defaults(func=run_send)

    setup = sub.add_parser("setup", aliases=["配置"], parents=[common], help="配置蒲公英和飞书参数")
    setup.add_argument("--pgy-api-key")
    setup.add_argument("--feishu-webhook-url")
    setup.add_argument("--feishu-app-id")
    setup.add_argument("--feishu-app-secret")
    setup.add_argument(
        "--from-stdin",
        choices=REQUIRED_CONFIG,
        help="从 stdin 读取并缓存单个配置值，适合 Codex 等待使用者输入后继续执行",
    )
    setup.set_defaults(func=setup_config)

    status = sub.add_parser("status", aliases=["检查"], parents=[common], help="查看配置和 App 发现状态")
    status.add_argument("--cwd", default=os.getcwd())
    status.add_argument("--scheme", default=None, help="指定 Xcode scheme，可选")
    status.add_argument("--app-name", default=None, help="指定已生成的 .app 名称，不带 .app 后缀")
    status.add_argument("--app-path", default=None, help="指定已经生成好的 .app 路径")
    status.add_argument(
        "--configuration",
        default=os.environ.get("IOS_PGYER_LARK_CONFIGURATION", "Debug"),
        help="用于查找已生成 .app 的构建配置，默认 Debug",
    )
    status.set_defaults(func=lambda args: print_status(args, discover=True))

    clear = sub.add_parser("clear", aliases=["清理"], parents=[common], help="清理缓存配置")
    clear.set_defaults(func=clear_config)

    at_cmd = sub.add_parser("at", aliases=["@人"], parents=[common], help="添加飞书 user_id，用于发布通知时 @ 人")
    at_cmd.add_argument("user_ids", nargs="+")
    at_cmd.set_defaults(func=add_mentions)

    unat = sub.add_parser("unat", aliases=["删@"], parents=[common], help="删除飞书 @ 人；不传 ID 时删除全部")
    unat.add_argument("user_ids", nargs="*")
    unat.set_defaults(func=remove_mentions)

    parser.aliases = aliases
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if argv and argv[0] in parser.aliases:
        argv[0] = parser.aliases[argv[0]]
    try:
        args = parser.parse_args(argv)
        args.func(args)
    except ConfigRequired as exc:
        print_config_required(exc)
        return 2
    except PublishError as exc:
        print_failure(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
