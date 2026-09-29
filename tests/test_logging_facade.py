"""Unit tests for logging configuration (Consumer mode vs Developer audit facade)."""

import logging
import os
import sys
from unittest.mock import patch

from run import _init_logging


def test_consumer_mode_default_logging() -> None:
    # Default consumer invocation without flags: WARNING level, no FileHandler
    with patch.object(sys, "argv", ["run.py"]), \
         patch.dict(os.environ, {}, clear=True):
        logger = _init_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0


def test_developer_mode_cli_flag_logging(tmp_path) -> None:
    # Developer invocation with --audit: INFO level and FileHandler enabled
    with patch.object(sys, "argv", ["run.py", "--audit"]), \
         patch.dict(os.environ, {}, clear=True):
        logger = _init_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0


def test_developer_mode_env_var_logging(tmp_path) -> None:
    # Developer invocation with SUBTRANS_AUDIT=1: INFO level and FileHandler enabled
    with patch.object(sys, "argv", ["run.py"]), \
         patch.dict(os.environ, {"SUBTRANS_AUDIT": "1"}):
        logger = _init_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0
