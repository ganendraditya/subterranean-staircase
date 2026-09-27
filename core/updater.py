"""Decoupled in-app update checker and self-updater.

Checks for updates against Git upstream or GitHub API, applies updates via git pull
and pip, and supports seamless application restart.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

logger = logging.getLogger("subtitle_translator.updater")

GITHUB_API_COMMITS_URL = "https://api.github.com/repos/ganendraditya/subtitle-translator/commits/main"


@dataclass
class UpdateInfo:
    """Status details regarding application update availability."""
    has_update: bool
    current_commit: str = ""
    latest_commit: str = ""
    message: str = ""


class UpdateManager:
    """Manages update checking, dependency syncing, and application restart."""

    def __init__(self, repo_dir: Optional[Path] = None) -> None:
        self.repo_dir = repo_dir or Path(__file__).resolve().parent.parent

    def get_local_commit(self) -> str:
        """Retrieve local HEAD commit hash."""
        try:
            res = subprocess.run(
                ["git", "-C", str(self.repo_dir), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            return res.stdout.strip()
        except Exception as e:
            logger.debug("Failed to get local git commit: %s", e)
            return ""

    def get_remote_commit(self) -> str:
        """Retrieve latest upstream commit hash via git ls-remote or GitHub API fallback."""
        # 1. Try git ls-remote (fast, lightweight, no working tree mutation)
        try:
            res = subprocess.run(
                ["git", "-C", str(self.repo_dir), "ls-remote", "origin", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            output = res.stdout.strip()
            if output:
                return output.split()[0]
        except Exception as e:
            logger.debug("git ls-remote failed, attempting GitHub API: %s", e)

        # 2. Fallback to GitHub REST API (works even if git command or remote is unconfigured)
        try:
            req = urllib.request.Request(
                GITHUB_API_COMMITS_URL,
                headers={"User-Agent": "SubtitleTranslator-Updater"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "sha" in data:
                    return str(data["sha"])
        except Exception as e:
            logger.debug("GitHub API commit check failed: %s", e)

        return ""

    def check_for_updates(self) -> UpdateInfo:
        """Compare local commit with remote commit to determine update availability."""
        local = self.get_local_commit()
        if not local:
            return UpdateInfo(
                has_update=False,
                message="Cannot check for updates: local Git repository not detected.",
            )

        remote = self.get_remote_commit()
        if not remote:
            return UpdateInfo(
                has_update=False,
                current_commit=local[:7],
                message="Could not reach update server. Please check internet connection.",
            )

        if local.lower() != remote.lower():
            return UpdateInfo(
                has_update=True,
                current_commit=local[:7],
                latest_commit=remote[:7],
                message=f"Update available: {local[:7]} → {remote[:7]}",
            )

        return UpdateInfo(
            has_update=False,
            current_commit=local[:7],
            latest_commit=remote[:7],
            message="Subtitle Translator is up to date.",
        )

    def apply_update(
        self,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """Pull latest changes from git and update dependencies via pip."""
        try:
            if progress_cb:
                progress_cb("Pulling latest updates from repository...")

            pull_res = subprocess.run(
                ["git", "-C", str(self.repo_dir), "pull", "--quiet"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if pull_res.returncode != 0:
                err = pull_res.stderr.strip() or "git pull failed"
                logger.error("Update git pull failed: %s", err)
                return False, f"Git pull failed: {err}"

            req_file = self.repo_dir / "requirements.txt"
            if req_file.exists():
                if progress_cb:
                    progress_cb("Checking and updating dependencies...")
                pip_res = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req_file)],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if pip_res.returncode != 0:
                    err = pip_res.stderr.strip() or "pip install failed"
                    logger.error("Dependency update failed: %s", err)
                    return False, f"Dependency install failed: {err}"

            if progress_cb:
                progress_cb("Update completed successfully!")
            return True, "Application successfully updated."

        except Exception as e:
            logger.exception("Unexpected error during update: %s", e)
            return False, f"Update error: {str(e)}"

    def restart_app(self) -> None:
        """Relaunch the application and terminate the current process."""
        python_exe = sys.executable
        args = [python_exe] + sys.argv
        logger.info("Restarting application: %s", args)

        if sys.platform == "win32":
            subprocess.Popen(args, close_fds=True)
            sys.exit(0)
        else:
            os.execv(python_exe, args)
