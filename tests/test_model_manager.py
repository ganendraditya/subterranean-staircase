"""Unit tests for ModelManager and model download dialogs."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PyQt6.QtWidgets import QApplication

from core.translate.models import RECOMMENDED_MODELS, ModelManager
from ui.model_dialog import ModelDownloadProgressDialog, ModelDownloadWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_model_manager_is_installed_false_when_empty(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path)
    assert mgr.is_installed("ja-en") is False
    assert mgr.get_disk_size_mb("ja-en") == 0.0


def test_model_manager_is_installed_true_when_valid(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path)
    model_dir = tmp_path / "opus-mt-ja-en"
    model_dir.mkdir(parents=True)
    # Write at least 200 KB
    (model_dir / "model.bin").write_bytes(b"dummy_binary_data" * 20000)
    (model_dir / "source.spm").write_bytes(b"dummy_spm_data")
    (model_dir / "config.json").write_bytes(b"{}")

    assert mgr.is_installed("ja-en") is True
    assert mgr.get_disk_size_mb("ja-en") > 0.0


def test_list_models_status(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path)
    model_dir = tmp_path / "opus-mt-en-id"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"binary")
    (model_dir / "source.spm").write_bytes(b"spm")
    (model_dir / "config.json").write_bytes(b"{}")

    status_list = mgr.list_models_status()
    assert len(status_list) == len(RECOMMENDED_MODELS)

    en_id_status = next(s for s in status_list if s["pair_id"] == "en-id")
    assert en_id_status["installed"] is True

    ja_en_status = next(s for s in status_list if s["pair_id"] == "ja-en")
    assert ja_en_status["installed"] is False


def test_delete_model(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path)
    model_dir = tmp_path / "opus-mt-ko-en"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"binary")
    (model_dir / "source.spm").write_bytes(b"spm")
    (model_dir / "config.json").write_bytes(b"{}")

    assert mgr.is_installed("ko-en") is True

    success, msg = mgr.delete_model("ko-en")
    assert success is True
    assert not model_dir.exists()
    assert mgr.is_installed("ko-en") is False

    # Deleting non-existent model
    success_none, _ = mgr.delete_model("ko-en")
    assert success_none is False


def test_download_model_unknown_pair(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path)
    success, msg = mgr.download_model("invalid-pair")
    assert success is False
    assert "Unknown model" in msg


def test_download_model_success(tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path)
    progress_records = []

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        # Return chunks and then empty bytes repeatedly
        mock_resp.read = MagicMock(side_effect=[b"chunk1", b""] * 10)
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        success, msg = mgr.download_model(
            "ja-en",
            progress_cb=lambda c, t, m: progress_records.append((c, t, m)),
        )
        assert success is True
        assert mgr.is_installed("ja-en") is True
        assert len(progress_records) > 0


def test_model_download_worker(qapp, tmp_path: Path) -> None:
    mgr = ModelManager(models_dir=tmp_path)
    with patch.object(mgr, "download_model", return_value=(True, "Success")):
        worker = ModelDownloadWorker(mgr, "ja-en")
        results = []
        worker.download_finished.connect(lambda s, m: results.append((s, m)))

        worker.start()
        worker.wait(2000)
        qapp.processEvents()

        assert len(results) == 1
        assert results[0] == (True, "Success")
