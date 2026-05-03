"""macOS DMG 打包脚本。

用法:
    python build_dmg.py

产物:
    dist/KoreanGlossaryReview.app        — macOS 应用包
    release/KoreanGlossaryReview-<ver>.dmg — 可分发的磁盘镜像

前置:
    1. cd frontend && npm install && npm run build
    2. pip install -r requirements.txt pyinstaller
    3. (可选) brew install create-dmg  — 不存在时回退到 hdiutil
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
ENTRY_POINT = BASE_DIR / "run_safe.py"
ASSETS_DIR = BASE_DIR / "assets"
ICON_ICO = ASSETS_DIR / "icon.ico"
ICON_ICNS = ASSETS_DIR / "icon.icns"
APP_NAME = "KoreanGlossaryReview"
DISPLAY_NAME = "AI Glossary Review"
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
RELEASE_DIR = BASE_DIR / "release"

# 平台守卫:DMG 必须在 macOS 上构建。
if sys.platform != "darwin":
    print("ERROR: build_dmg.py 必须在 macOS 上运行。", file=sys.stderr)
    sys.exit(1)

if not FRONTEND_DIST.exists():
    print(
        "ERROR: 未发现前端产物。请先在 frontend/ 下执行 npm run build。",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# 1. 准备 .icns 图标(PyInstaller 在 macOS 上仅识别 .icns)
# ---------------------------------------------------------------------------
def ensure_icns_icon() -> Path | None:
    """若已存在 icon.icns 则直接使用;否则尝试由 icon.ico 转换。失败时返回 None。"""
    if ICON_ICNS.exists():
        return ICON_ICNS
    if not ICON_ICO.exists():
        print("WARN: 未找到 icon.icns / icon.ico,将使用 PyInstaller 默认图标。")
        return None

    print(f"由 {ICON_ICO.name} 生成 {ICON_ICNS.name} ...")
    iconset = BUILD_DIR / "icon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True, exist_ok=True)

    # 用 sips 把 .ico 解码为基准 PNG,再生成多分辨率 iconset
    base_png = BUILD_DIR / "icon_base.png"
    try:
        subprocess.run(
            ["sips", "-s", "format", "png", str(ICON_ICO), "--out", str(base_png)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"WARN: sips 转换失败({exc}),回退到默认图标。")
        return None

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in sizes:
        subprocess.run(
            [
                "sips",
                "-z",
                str(size),
                str(size),
                str(base_png),
                "--out",
                str(iconset / name),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    try:
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(ICON_ICNS)],
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"WARN: iconutil 生成 .icns 失败({exc}),回退到默认图标。")
        return None
    return ICON_ICNS


# ---------------------------------------------------------------------------
# 2. 读取应用版本(用于 DMG 命名 / Info.plist)
# ---------------------------------------------------------------------------
def read_version() -> str:
    version_module: dict[str, str] = {}
    version_file = BASE_DIR / "backend" / "version.py"
    exec(version_file.read_text(encoding="utf-8"), version_module)  # noqa: S102
    return version_module.get("__version__", "0.0.0")


# ---------------------------------------------------------------------------
# 3. 调用 PyInstaller 生成 .app
# ---------------------------------------------------------------------------
def build_app(icon_path: Path | None, version: str) -> Path:
    """运行 PyInstaller 生成 .app bundle,返回其路径。"""
    print("\n=== Step 1/3: PyInstaller 打包 .app ===")

    # macOS 上 --add-data 使用冒号分隔
    add_data_args = [
        f"--add-data={FRONTEND_DIST}:frontend/dist",
    ]

    hidden_imports = [
        "backend",
        "backend.app",
        "backend.core",
        "backend.version",
        "backend.updater",
        "requests",
    ]
    hidden_import_args = [f"--hidden-import={h}" for h in hidden_imports]

    args: list[str] = [
        str(ENTRY_POINT),
        f"--name={APP_NAME}",
        "--windowed",   # 在 macOS 上 --windowed 会同时产出 .app bundle
        "--onedir",
        "--clean",
        "--noconfirm",
        # macOS Bundle 元数据
        f"--osx-bundle-identifier=com.koreanglossaryreview.app",
    ]
    if icon_path is not None:
        args.append(f"--icon={icon_path}")

    args.extend(add_data_args)
    args.extend(hidden_import_args)

    print(f"PyInstaller args: {len(args)}")
    PyInstaller.__main__.run(args)

    app_path = DIST_DIR / f"{APP_NAME}.app"
    if not app_path.exists():
        print(f"ERROR: 未在 {app_path} 找到 .app 输出。", file=sys.stderr)
        sys.exit(1)

    # 把 cfg.json.example 拷贝进 .app 内部资源目录,作为首次运行模板
    bundled_resources = app_path / "Contents" / "Resources"
    cfg_example = BASE_DIR / "cfg.json.example"
    if cfg_example.exists() and bundled_resources.exists():
        shutil.copy(cfg_example, bundled_resources / "cfg.json")

    # 注入版本号到 Info.plist(PyInstaller 默认值常为 0.0.0)
    plist_path = app_path / "Contents" / "Info.plist"
    if plist_path.exists():
        try:
            subprocess.run(
                [
                    "/usr/libexec/PlistBuddy",
                    "-c",
                    f"Set :CFBundleShortVersionString {version}",
                    str(plist_path),
                ],
                check=False,
            )
            subprocess.run(
                [
                    "/usr/libexec/PlistBuddy",
                    "-c",
                    f"Set :CFBundleVersion {version}",
                    str(plist_path),
                ],
                check=False,
            )
            subprocess.run(
                [
                    "/usr/libexec/PlistBuddy",
                    "-c",
                    f"Set :CFBundleDisplayName {DISPLAY_NAME}",
                    str(plist_path),
                ],
                check=False,
            )
        except FileNotFoundError:
            print("WARN: 未找到 PlistBuddy,跳过 Info.plist 元数据更新。")

    return app_path


# ---------------------------------------------------------------------------
# 4. 用 create-dmg 或 hdiutil 生成 DMG
# ---------------------------------------------------------------------------
def build_dmg(app_path: Path, version: str) -> Path:
    print("\n=== Step 2/3: 生成 DMG ===")
    RELEASE_DIR.mkdir(exist_ok=True)
    dmg_path = RELEASE_DIR / f"{APP_NAME}-{version}.dmg"
    if dmg_path.exists():
        dmg_path.unlink()

    # 优先使用 create-dmg(若用户已经 brew install create-dmg)
    if shutil.which("create-dmg"):
        print("使用 create-dmg ...")
        cmd = [
            "create-dmg",
            "--volname",
            f"{DISPLAY_NAME} {version}",
            "--window-size",
            "600",
            "400",
            "--icon-size",
            "100",
            "--icon",
            f"{APP_NAME}.app",
            "150",
            "200",
            "--app-drop-link",
            "450",
            "200",
            "--no-internet-enable",
            str(dmg_path),
            str(app_path),
        ]
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0 and dmg_path.exists():
            return dmg_path
        print("WARN: create-dmg 失败,回退到 hdiutil。")

    # 回退方案:hdiutil(macOS 系统自带,不依赖外部工具)
    print("使用 hdiutil ...")
    staging = BUILD_DIR / "dmg_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    # 拷贝 .app 进入暂存目录,并加入指向 /Applications 的符号链接
    shutil.copytree(app_path, staging / app_path.name, symlinks=True)
    os.symlink("/Applications", staging / "Applications")

    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            f"{DISPLAY_NAME} {version}",
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ],
        check=True,
    )
    return dmg_path


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------
def main() -> None:
    version = read_version()
    print(f"开始打包 {APP_NAME} v{version} (macOS)")

    icon_path = ensure_icns_icon()
    app_path = build_app(icon_path, version)

    print("\n=== Step 3/3: 校验 ===")
    bundled_frontend = app_path / "Contents" / "Resources" / "frontend" / "dist"
    if not bundled_frontend.exists():
        # PyInstaller 6.x 可能把数据放在 _internal 旁,做兜底校验
        alt = app_path / "Contents" / "Frameworks" / "frontend" / "dist"
        if not alt.exists():
            print(
                f"WARN: 未在 {bundled_frontend} 或 {alt} 找到前端资源,"
                "应用启动时可能 404。请检查 --add-data 参数。"
            )
        else:
            print(f"前端资源位于: {alt}")
    else:
        print(f"前端资源位于: {bundled_frontend}")

    dmg_path = build_dmg(app_path, version)

    print("\n打包完成 ")
    print(f"  .app : {app_path}")
    print(f"  .dmg : {dmg_path}")
    print(
        "\n提示:DMG 未做代码签名 / 公证。终端用户首次启动需在"
        "‘系统设置 -> 隐私与安全性’中允许打开,或执行:\n"
        f"  xattr -dr com.apple.quarantine /Applications/{APP_NAME}.app"
    )


if __name__ == "__main__":
    main()
