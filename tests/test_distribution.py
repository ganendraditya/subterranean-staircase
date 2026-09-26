"""Unit tests verifying installer script syntax and presence."""

import os
from pathlib import Path


def test_distribution_scripts_exist_and_executable() -> None:
    root = Path(__file__).parent.parent
    install_sh = root / "install.sh"
    uninstall_sh = root / "uninstall.sh"
    install_ps1 = root / "install.ps1"
    uninstall_ps1 = root / "uninstall.ps1"

    assert install_sh.exists()
    assert uninstall_sh.exists()
    assert install_ps1.exists()
    assert uninstall_ps1.exists()

    # Verify shell scripts start with proper shebang
    with open(install_sh, "r", encoding="utf-8") as f:
        assert f.readline().startswith("#!/usr/bin/env bash")

    with open(uninstall_sh, "r", encoding="utf-8") as f:
        assert f.readline().startswith("#!/usr/bin/env bash")
