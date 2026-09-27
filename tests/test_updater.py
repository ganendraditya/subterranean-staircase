"""Unit tests for UpdateManager, UpdateCheckWorker, and UpdateProgressDialog."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PyQt6.QtWidgets import QApplication

from core.updater import UpdateInfo, UpdateManager
from ui.updater_dialog import ApplyUpdateWorker, UpdateCheckWorker, UpdateProgressDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_update_info_dataclass() -> None:
    info = UpdateInfo(has_update=True, current_commit="abc1234", latest_commit="def5678", message="Update found")
    assert info.has_update is True
    assert info.current_commit == "abc1234"
    assert info.latest_commit == "def5678"
    assert info.message == "Update found"


def test_get_local_commit(tmp_path: Path) -> None:
    mgr = UpdateManager(repo_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="1234567890abcdef\n")
        commit = mgr.get_local_commit()
        assert commit == "1234567890abcdef"

    with patch("subprocess.run", side_effect=Exception("git error")):
        assert mgr.get_local_commit() == ""


def test_get_remote_commit_via_git(tmp_path: Path) -> None:
    mgr = UpdateManager(repo_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="abcdef1234567890\trefs/heads/main\n"
        )
        remote = mgr.get_remote_commit()
        assert remote == "abcdef1234567890"


def test_get_remote_commit_via_github_api_fallback(tmp_path: Path) -> None:
    mgr = UpdateManager(repo_dir=tmp_path)
    with patch("subprocess.run", side_effect=Exception("git error")):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"sha": "fedcba0987654321"}'
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            remote = mgr.get_remote_commit()
            assert remote == "fedcba0987654321"


def test_check_for_updates_scenarios(tmp_path: Path) -> None:
    mgr = UpdateManager(repo_dir=tmp_path)

    # 1. No local commit
    with patch.object(mgr, "get_local_commit", return_value=""):
        res = mgr.check_for_updates()
        assert not res.has_update
        assert "not detected" in res.message

    # 2. Remote unreachable
    with patch.object(mgr, "get_local_commit", return_value="1111111111"), \
         patch.object(mgr, "get_remote_commit", return_value=""):
        res = mgr.check_for_updates()
        assert not res.has_update
        assert "Could not reach" in res.message

    # 3. Already up to date
    with patch.object(mgr, "get_local_commit", return_value="1111111111"), \
         patch.object(mgr, "get_remote_commit", return_value="1111111111"):
        res = mgr.check_for_updates()
        assert not res.has_update
        assert "up to date" in res.message

    # 4. Update available
    with patch.object(mgr, "get_local_commit", return_value="1111111111"), \
         patch.object(mgr, "get_remote_commit", return_value="2222222222"):
        res = mgr.check_for_updates()
        assert res.has_update
        assert res.current_commit == "1111111"
        assert res.latest_commit == "2222222"


def test_apply_update_success(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy\n")

    mgr = UpdateManager(repo_dir=tmp_path)
    progress_messages: list[str] = []

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        success, msg = mgr.apply_update(progress_cb=progress_messages.append)
        assert success is True
        assert "successfully" in msg
        assert len(progress_messages) >= 2


def test_apply_update_git_pull_failure(tmp_path: Path) -> None:
    mgr = UpdateManager(repo_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="merge conflict")
        success, msg = mgr.apply_update()
        assert success is False
        assert "Git pull failed" in msg


def test_apply_update_pip_failure(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy\n")

    mgr = UpdateManager(repo_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        # First call (git pull) succeeds, second call (pip) fails
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="pip network timeout"),
        ]
        success, msg = mgr.apply_update()
        assert success is False
        assert "Dependency install failed" in msg


def test_update_check_worker(qapp, tmp_path: Path) -> None:
    mgr = UpdateManager(repo_dir=tmp_path)
    with patch.object(mgr, "check_for_updates") as mock_check:
        mock_check.return_value = UpdateInfo(has_update=True, latest_commit="abcdef1")
        worker = UpdateCheckWorker(mgr)
        results: list[UpdateInfo] = []
        worker.check_finished.connect(results.append)

        worker.start()
        worker.wait(2000)
        qapp.processEvents()

        assert len(results) == 1
        assert results[0].has_update is True
        assert results[0].latest_commit == "abcdef1"


def test_apply_update_worker(qapp, tmp_path: Path) -> None:
    mgr = UpdateManager(repo_dir=tmp_path)
    with patch.object(mgr, "apply_update") as mock_apply:
        mock_apply.return_value = (True, "OK")
        worker = ApplyUpdateWorker(mgr)
        results: list[tuple[bool, str]] = []
        worker.update_finished.connect(lambda s, m: results.append((s, m)))

        worker.start()
        worker.wait(2000)
        qapp.processEvents()

        assert len(results) == 1
        assert results[0] == (True, "OK")
