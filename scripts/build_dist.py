"""Packaging script for Subterranean Staircase standalone binary distribution.

Creates a standalone self-contained release archive using PyInstaller or standalone venv freeze.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


def get_target_triple() -> str:
    """Detect OS and machine architecture for asset naming."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        os_name = "macos"
        arch = "arm64" if "arm" in machine or "aarch64" in machine else "x86_64"
    elif system == "windows":
        os_name = "windows"
        arch = "x86_64" if "64" in machine else "x86"
    else:
        os_name = "linux"
        arch = "x86_64" if "64" in machine else "arm64"

    return f"{os_name}-{arch}"


def build_distribution(output_dir: Path) -> Path:
    """Bundle repository and environment into standalone archive."""
    root_dir = Path(__file__).resolve().parent.parent
    target_triple = get_target_triple()
    output_dir.mkdir(parents=True, exist_ok=True)

    dist_name = f"subtrans-{target_triple}"
    stage_dir = output_dir / dist_name
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    print(f"Staging distribution for target: {target_triple}...")

    # 1. Copy core codebase & essentials
    for item in ["core", "ui", "run.py", "requirements.txt", "uninstall.sh", "uninstall.ps1", "README.md"]:
        src = root_dir / item
        if src.exists():
            if src.is_dir():
                shutil.copytree(src, stage_dir / item, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, stage_dir / item)

    # 2. Package into tar.gz (macOS/Linux) or zip (Windows)
    if platform.system().lower() == "windows":
        archive_path = output_dir / f"{dist_name}.zip"
        print(f"Compressing {archive_path.name}...")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(stage_dir):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(stage_dir)
                    zf.write(full_p, arcname=f"{dist_name}/{rel_p}")
    else:
        archive_path = output_dir / f"{dist_name}.tar.gz"
        print(f"Compressing {archive_path.name}...")
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(stage_dir, arcname=dist_name)

    shutil.rmtree(stage_dir)
    print(f"Distribution build complete: {archive_path} ({round(archive_path.stat().st_size / (1024*1024), 2)} MB)")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Subterranean Staircase distribution asset")
    parser.add_argument("--output", type=Path, default=Path("dist"), help="Output directory")
    args = parser.parse_args()

    build_distribution(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
