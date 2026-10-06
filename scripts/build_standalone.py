"""Standalone binary packaging and installer builder for Subterranean Staircase.

Builds self-contained release distributions:
- macOS: Standalone .app bundle compiled with PyInstaller, packaged into .dmg with /Applications symlink.
- Windows: Standalone executable compiled with PyInstaller, packaged into Inno Setup Setup.exe and portable .zip.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile


def get_platform_target() -> str:
    """Return platform target string, e.g. macos-arm64, macos-x86_64, windows-x64."""
    sys_name = platform.system().lower()
    machine = platform.machine().lower()

    if sys_name == "darwin":
        arch = "arm64" if "arm" in machine or "aarch64" in machine else "x86_64"
        return f"macos-{arch}"
    elif sys_name == "windows":
        if "arm" in machine or "aarch64" in machine:
            arch = "arm64"
        elif "64" in machine:
            arch = "x64"
        else:
            arch = "x86"
        return f"windows-{arch}"
    return f"{sys_name}-{machine}"


def run_pyinstaller(spec_path: Path, output_dir: Path) -> Path:
    """Execute PyInstaller build against subtrans.spec."""
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_path),
        "--distpath",
        str(output_dir),
        "--noconfirm",
    ]
    print(f"🔨 Running PyInstaller: {' '.join(cmd)}...")
    subprocess.run(cmd, check=True)
    return output_dir


def package_macos_dmg(app_path: Path, output_dmg_path: Path, volume_name: str = "Subterranean Staircase") -> Path:
    """Package .app bundle into a user-friendly drag-and-drop .dmg using native hdiutil."""
    if not app_path.exists():
        raise FileNotFoundError(f"App bundle not found at: {app_path}")

    staging_dir = Path(tempfile.mkdtemp(prefix="dmg_staging_"))

    try:
        # 1. Copy .app into staging directory
        staged_app = staging_dir / app_path.name
        print(f"📦 Staging {app_path.name}...")
        shutil.copytree(app_path, staged_app, symlinks=True)

        # 2. Create symlink to /Applications for drag-and-drop
        apps_link = staging_dir / "Applications"
        os.symlink("/Applications", apps_link)

        # 3. Build DMG using macOS hdiutil
        output_dmg_path.parent.mkdir(parents=True, exist_ok=True)
        if output_dmg_path.exists():
            output_dmg_path.unlink()

        cmd = [
            "hdiutil",
            "create",
            "-volname",
            volume_name,
            "-srcfolder",
            str(staging_dir),
            "-ov",
            "-format",
            "UDZO",
            str(output_dmg_path),
        ]
        print(f"🗜 Creating DMG image: {' '.join(cmd)}...")
        subprocess.run(cmd, check=True)

        size_mb = output_dmg_path.stat().st_size / (1024 * 1024)
        print(f"✔ Successfully created macOS DMG: {output_dmg_path} ({size_mb:.1f} MB)")
        return output_dmg_path
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def package_windows_installer(app_dir: Path, output_dir: Path, iss_path: Path) -> list[Path]:
    """Package Windows build into Inno Setup Setup.exe and portable .zip archive."""
    artifacts = []
    target = get_platform_target()

    # 1. Portable .zip archive
    zip_path = output_dir / f"Subterranean-Staircase-{target}-portable.zip"
    print(f"🗜 Compressing portable Windows ZIP: {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(app_dir):
            for file in files:
                full_p = Path(root) / file
                rel_p = full_p.relative_to(app_dir)
                zf.write(full_p, arcname=f"Subterranean Staircase/{rel_p.as_posix()}")
    artifacts.append(zip_path)
    print(f"✔ Created portable ZIP: {zip_path} ({zip_path.stat().st_size / (1024 * 1024):.1f} MB)")

    # 2. Inno Setup installer if iscc is found
    iscc_bin = shutil.which("iscc") or shutil.which("ISCC")
    if not iscc_bin:
        default_inno = Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe")
        if default_inno.exists():
            iscc_bin = str(default_inno)

    if not iscc_bin:
        print("ℹ Inno Setup compiler (ISCC) not found; skipping Setup.exe creation.")
    elif not iss_path.exists():
        print(f"ℹ Inno Setup script not found at {iss_path}; skipping Setup.exe creation.")
    else:
        print(f"🔨 Compiling Inno Setup installer using {iscc_bin}...")
        resolved_out = output_dir.resolve()
        resolved_app = app_dir.resolve()
        # /O overrides OutputDir= in installer.iss, /DAppSourceDir overrides source files
        cmd = [iscc_bin, f'/O"{resolved_out}"', f'/DAppSourceDir="{resolved_app}"', str(iss_path)]
        subprocess.run(cmd, check=True)

        exe_candidates = list(output_dir.glob("*-Setup.exe"))
        if exe_candidates:
            setup_exe = exe_candidates[0]
            print(f"✔ Created Windows Setup installer: {setup_exe} ({setup_exe.stat().st_size / (1024 * 1024):.1f} MB)")
            artifacts.append(setup_exe)
        else:
            raise FileNotFoundError(f"Inno Setup compiled successfully but no *-Setup.exe was found in {output_dir}")

    return artifacts


def build_all(output_dir: Path, spec_path: Path, iss_path: Path, skip_dmg: bool = False) -> list[Path]:
    """Full end-to-end build pipeline for the current platform."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = get_platform_target()
    print(f"🚀 Starting standalone build for target platform: {target}...")

    # Run PyInstaller
    run_pyinstaller(spec_path, output_dir)

    results = []
    if sys.platform == "darwin":
        app_bundle = output_dir / "Subterranean Staircase.app"
        if not app_bundle.exists():
            raise FileNotFoundError(f"PyInstaller failed to output {app_bundle}")
        results.append(app_bundle)

        if not skip_dmg:
            dmg_path = output_dir / f"Subterranean-Staircase-{target}.dmg"
            actual_dmg = package_macos_dmg(app_bundle, dmg_path)
            results.append(actual_dmg)
    elif sys.platform == "win32":
        app_dir = output_dir / "Subterranean Staircase"
        if not app_dir.exists():
            raise FileNotFoundError(f"PyInstaller failed to output {app_dir}")
        win_artifacts = package_windows_installer(app_dir, output_dir, iss_path)
        results.extend(win_artifacts)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Subterranean Staircase standalone GUI installer")
    parser.add_argument("--output", type=Path, default=Path("dist"), help="Output directory")
    parser.add_argument("--spec", type=Path, default=Path("subtrans.spec"), help="Path to PyInstaller spec")
    parser.add_argument("--iss", type=Path, default=Path("scripts/installer.iss"), help="Path to Inno Setup script")
    parser.add_argument("--skip-dmg", action="store_true", help="Skip DMG packaging on macOS")
    args = parser.parse_args()

    artifacts = build_all(args.output, args.spec, args.iss, skip_dmg=args.skip_dmg)
    print("\n📦 Built Artifacts:")
    for art in artifacts:
        print(f"  • {art}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
