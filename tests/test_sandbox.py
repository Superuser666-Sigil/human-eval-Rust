"""
Sandbox module tests for HumanEval Rust.

Tests Firejail detection, sandbox mode resolution, and security configuration.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from human_eval import sandbox
from human_eval.sandbox import (
    FIREJAIL_SECURITY_OPTS,
    FirejailStatus,
    InstallResult,
    SandboxError,
    check_firejail_available,
    detect_package_manager,
    get_install_command,
    resolve_sandbox_mode,
)


class TestFirejailSecurityOptions:
    """Test Firejail security options configuration."""

    def test_firejail_security_opts_present(self) -> None:
        """Test that security options are defined."""
        assert "--seccomp" in FIREJAIL_SECURITY_OPTS
        assert "--caps.drop=all" in FIREJAIL_SECURITY_OPTS

    def test_all_required_options_present(self) -> None:
        """Test that all required security options are present."""
        required = [
            "--seccomp",
            "--caps.drop=all",
            "--noroot",
            "--private-tmp",
            "--nogroups",
            "--read-only=/",
        ]
        for opt in required:
            assert opt in FIREJAIL_SECURITY_OPTS, f"Missing required option: {opt}"

    def test_resource_limits_present(self) -> None:
        """Test that resource limits are configured."""
        opts_str = " ".join(FIREJAIL_SECURITY_OPTS)
        assert "--rlimit-fsize" in opts_str
        assert "--rlimit-nproc" in opts_str
        assert "--rlimit-cpu" in opts_str


class TestFirejailDetection:
    """Test Firejail availability detection."""

    def test_detection_when_available(self) -> None:
        """Test detection when Firejail is available."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="firejail version 0.9.72\n", stderr=""
            )
            status = check_firejail_available()

            assert status.available is True
            assert status.version is not None
            assert "firejail" in status.version.lower()
            assert status.error is None

    def test_detection_when_not_found(self) -> None:
        """Test detection when Firejail is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("firejail not found")
            status = check_firejail_available()

            assert status.available is False
            assert status.version is None
            assert status.error is not None
            assert "not found" in status.error.lower()

    def test_detection_when_timeout(self) -> None:
        """Test detection when version check times out."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("firejail", 5)
            status = check_firejail_available()

            assert status.available is False
            assert status.version is None
            assert status.error is not None
            assert "timed out" in status.error.lower()

    def test_detection_when_nonzero_exit(self) -> None:
        """Test detection when Firejail returns non-zero exit code."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="error message"
            )
            status = check_firejail_available()

            assert status.available is False

    def test_firejail_status_namedtuple(self) -> None:
        """Test FirejailStatus named tuple structure."""
        status = FirejailStatus(available=True, version="0.9.72", error=None)
        assert status.available is True
        assert status.version == "0.9.72"
        assert status.error is None


class TestPackageManagerDetection:
    """Test package manager detection."""

    @pytest.mark.parametrize(
        "pm_name",
        ["apt-get", "dnf", "yum", "pacman", "zypper", "apk"],
    )
    def test_detects_package_managers(self, pm_name: str) -> None:
        """Test detection of various package managers."""
        with patch("shutil.which") as mock_which:
            # Return the pm_name only for the matching one
            mock_which.side_effect = lambda x: x if x == pm_name else None
            result = detect_package_manager()
            assert result == pm_name

    def test_returns_none_when_no_pm(self) -> None:
        """Test that None is returned when no package manager is found."""
        with patch("shutil.which", return_value=None):
            result = detect_package_manager()
            assert result is None


class TestInstallCommand:
    """Test install command generation."""

    def test_apt_install_command(self) -> None:
        """Test apt-get install command."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: x if x == "apt-get" else None
            cmd = get_install_command()
            assert cmd is not None
            assert "apt-get" in cmd
            assert "install" in cmd
            assert "firejail" in cmd

    def test_returns_none_when_no_pm(self) -> None:
        """Test that None is returned when no package manager is found."""
        with patch("shutil.which", return_value=None):
            cmd = get_install_command()
            assert cmd is None


class TestSandboxModeResolution:
    """Test sandbox mode resolution logic."""

    def test_explicit_firejail_mode_when_available(self) -> None:
        """Test explicit firejail mode when Firejail is available."""
        with patch.object(sandbox, "check_firejail_available") as mock_check:
            mock_check.return_value = FirejailStatus(
                available=True, version="0.9.72", error=None
            )
            result = resolve_sandbox_mode("firejail")
            assert result == "firejail"

    def test_explicit_firejail_mode_when_unavailable(self) -> None:
        """Test explicit firejail mode when Firejail is unavailable."""
        with patch.object(sandbox, "check_firejail_available") as mock_check:
            mock_check.return_value = FirejailStatus(
                available=False, version=None, error="not found"
            )
            with pytest.raises(SandboxError):
                resolve_sandbox_mode("firejail")

    def test_explicit_none_mode(self) -> None:
        """Test explicit none mode (no sandboxing)."""
        result = resolve_sandbox_mode("none", allow_no_sandbox=True)
        assert result == "none"

    def test_auto_detect_uses_firejail_when_available(self) -> None:
        """Test auto-detection uses Firejail when available."""
        with patch.object(sandbox, "check_firejail_available") as mock_check:
            mock_check.return_value = FirejailStatus(
                available=True, version="0.9.72", error=None
            )
            result = resolve_sandbox_mode(None, non_interactive=True)
            assert result == "firejail"

    def test_auto_detect_non_interactive_with_allow_no_sandbox(self) -> None:
        """Test auto-detection in non-interactive mode with allow_no_sandbox."""
        with patch.object(sandbox, "check_firejail_available") as mock_check:
            mock_check.return_value = FirejailStatus(
                available=False, version=None, error="not found"
            )
            result = resolve_sandbox_mode(
                None, allow_no_sandbox=True, non_interactive=True
            )
            assert result == "none"

    def test_auto_detect_non_interactive_without_allow_raises(self) -> None:
        """Test auto-detection raises in non-interactive mode without allow."""
        with patch.object(sandbox, "check_firejail_available") as mock_check:
            mock_check.return_value = FirejailStatus(
                available=False, version=None, error="not found"
            )
            with pytest.raises(SandboxError):
                resolve_sandbox_mode(None, allow_no_sandbox=False, non_interactive=True)


class TestSandboxError:
    """Test SandboxError exception."""

    def test_sandbox_error_is_exception(self) -> None:
        """Test that SandboxError is an Exception."""
        assert issubclass(SandboxError, Exception)

    def test_sandbox_error_message(self) -> None:
        """Test SandboxError message."""
        error = SandboxError("test error message")
        assert str(error) == "test error message"


class TestInstallResult:
    """Test InstallResult named tuple."""

    def test_install_result_structure(self) -> None:
        """Test InstallResult named tuple structure."""
        result = InstallResult(
            success=True, stdout="installed", stderr="", exit_code=0
        )
        assert result.success is True
        assert result.stdout == "installed"
        assert result.stderr == ""
        assert result.exit_code == 0

    def test_install_result_failure(self) -> None:
        """Test InstallResult for failure case."""
        result = InstallResult(
            success=False, stdout="", stderr="permission denied", exit_code=1
        )
        assert result.success is False
        assert result.exit_code == 1
