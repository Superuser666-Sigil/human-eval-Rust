"""
Sandbox wrapper for Rust code evaluation in HumanEval.

This module provides secure isolation for running rustc commands on LLM-generated code.
Uses Firejail for isolation with explicit user choice for installation or fallback modes.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 3.0.0
"""

import os
import shutil
import subprocess
import sys
from typing import NamedTuple

__all__ = [
    "SandboxError",
    "FirejailStatus",
    "InstallResult",
    "run_rustc_sandboxed",
    "run_binary_sandboxed",
    "check_firejail_available",
    "attempt_firejail_install",
    "prompt_sandbox_choice",
    "resolve_sandbox_mode",
]


class SandboxError(Exception):
    """Raised when sandbox operations fail."""

    pass


class FirejailStatus(NamedTuple):
    """Result of Firejail availability check."""

    available: bool
    version: str | None
    error: str | None


class InstallResult(NamedTuple):
    """Result of Firejail installation attempt."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int


# Cache for rustc validation (avoid checking on every call)
_host_rustc_validated = False
_firejail_validated = False


FIREJAIL_SECURITY_OPTS = [
    "--seccomp",
    "--caps.drop=all",
    "--noroot",
    "--rlimit-fsize=104857600",
    "--rlimit-nproc=50",
    "--rlimit-cpu=120",
    "--read-only=/",
    "--private-tmp",
    "--nogroups",
]


def check_firejail_available() -> FirejailStatus:
    """
    Check if Firejail is available and get version info.

    Returns:
        FirejailStatus with availability, version, and any error message.
    """
    try:
        result = subprocess.run(
            ["firejail", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Extract version from output (first line typically contains version)
            version_line = (
                result.stdout.strip().split("\n")[0] if result.stdout else None
            )
            return FirejailStatus(available=True, version=version_line, error=None)
        return FirejailStatus(
            available=False,
            version=None,
            error=f"firejail returned exit code {result.returncode}: {result.stderr}",
        )
    except subprocess.TimeoutExpired:
        return FirejailStatus(
            available=False, version=None, error="firejail --version timed out"
        )
    except FileNotFoundError:
        return FirejailStatus(
            available=False, version=None, error="firejail not found in PATH"
        )
    except Exception as e:
        return FirejailStatus(available=False, version=None, error=str(e))


def detect_package_manager() -> str | None:
    """
    Detect the available package manager for Firejail installation.

    Returns:
        Package manager command prefix or None if not detected.
    """
    # Check for common package managers in order of preference
    package_managers = [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "firejail"]),
        ("dnf", ["sudo", "dnf", "install", "-y", "firejail"]),
        ("yum", ["sudo", "yum", "install", "-y", "firejail"]),
        ("pacman", ["sudo", "pacman", "-S", "--noconfirm", "firejail"]),
        ("zypper", ["sudo", "zypper", "install", "-y", "firejail"]),
        ("apk", ["sudo", "apk", "add", "firejail"]),
    ]

    for name, _ in package_managers:
        if shutil.which(name):
            return name
    return None


def get_install_command() -> list[str] | None:
    """
    Get the appropriate Firejail installation command for this system.

    Returns:
        Installation command as list or None if no package manager found.
    """
    pm = detect_package_manager()
    if pm == "apt-get":
        return ["sudo", "apt-get", "install", "-y", "firejail"]
    elif pm == "dnf":
        return ["sudo", "dnf", "install", "-y", "firejail"]
    elif pm == "yum":
        return ["sudo", "yum", "install", "-y", "firejail"]
    elif pm == "pacman":
        return ["sudo", "pacman", "-S", "--noconfirm", "firejail"]
    elif pm == "zypper":
        return ["sudo", "zypper", "install", "-y", "firejail"]
    elif pm == "apk":
        return ["sudo", "apk", "add", "firejail"]
    return None


def attempt_firejail_install() -> InstallResult:
    """
    Attempt to install Firejail using the system package manager.

    Returns:
        InstallResult with success status, stdout, stderr, and exit code.
    """
    install_cmd = get_install_command()
    if install_cmd is None:
        return InstallResult(
            success=False,
            stdout="",
            stderr="No supported package manager found (apt-get, dnf, yum, pacman, zypper, apk)",
            exit_code=-1,
        )

    print(f"Attempting to install Firejail: {' '.join(install_cmd)}", file=sys.stderr)
    try:
        result = subprocess.run(
            install_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max for installation
        )
        return InstallResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return InstallResult(
            success=False,
            stdout="",
            stderr="Installation timed out after 5 minutes",
            exit_code=-1,
        )
    except Exception as e:
        return InstallResult(
            success=False,
            stdout="",
            stderr=str(e),
            exit_code=-1,
        )


def prompt_sandbox_choice(firejail_error: str | None = None) -> str:
    """
    Present interactive choice to user when Firejail is unavailable.

    Args:
        firejail_error: Error message from Firejail check, if any.

    Returns:
        Chosen mode: "firejail", "none", or raises SystemExit on cancel.
    """
    print("\n" + "=" * 70, file=sys.stderr)
    print("SANDBOX CONFIGURATION REQUIRED", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    if firejail_error:
        print(f"\nFirejail is not available: {firejail_error}", file=sys.stderr)
    else:
        print("\nFirejail sandbox is not available on this system.", file=sys.stderr)

    print("\nOptions:", file=sys.stderr)
    print("  [1] Install Firejail (requires sudo, Linux only)", file=sys.stderr)
    print("  [2] Cancel and exit", file=sys.stderr)
    print(
        "  [3] Proceed WITHOUT sandboxing (UNSAFE - for trusted code only)",
        file=sys.stderr,
    )
    print("\n" + "-" * 70, file=sys.stderr)

    while True:
        try:
            choice = input("Enter choice [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nOperation cancelled by user.", file=sys.stderr)
            raise SystemExit(1)

        if choice == "1":
            # Attempt installation
            install_result = attempt_firejail_install()
            if install_result.success:
                # Verify installation worked
                status = check_firejail_available()
                if status.available:
                    print(
                        f"\n✓ Firejail installed successfully: {status.version}",
                        file=sys.stderr,
                    )
                    return "firejail"
                else:
                    print(
                        "\n✗ Firejail installation appeared to succeed but "
                        f"verification failed: {status.error}",
                        file=sys.stderr,
                    )
            else:
                print("\n" + "-" * 70, file=sys.stderr)
                print("FIREJAIL INSTALLATION FAILED", file=sys.stderr)
                print("-" * 70, file=sys.stderr)
                print(f"Exit code: {install_result.exit_code}", file=sys.stderr)
                if install_result.stderr:
                    # Show first 500 chars of stderr
                    stderr_preview = install_result.stderr[:500]
                    print(f"Error output:\n{stderr_preview}", file=sys.stderr)
                print("-" * 70, file=sys.stderr)
                print("\nInstallation failed. You may need to:", file=sys.stderr)
                print("  - Run with elevated privileges", file=sys.stderr)
                print(
                    "  - Install Firejail manually from your distribution's package manager",
                    file=sys.stderr,
                )
                print("  - Visit: https://firejail.wordpress.com/", file=sys.stderr)
                print("\nChoose another option:", file=sys.stderr)
                print("  [2] Cancel and exit", file=sys.stderr)
                print("  [3] Proceed WITHOUT sandboxing (UNSAFE)", file=sys.stderr)

        elif choice == "2":
            print("\nOperation cancelled by user.", file=sys.stderr)
            raise SystemExit(1)

        elif choice == "3":
            print("\n" + "!" * 70, file=sys.stderr)
            print("WARNING: PROCEEDING WITHOUT SANDBOX", file=sys.stderr)
            print("!" * 70, file=sys.stderr)
            print(
                "\nYou are about to run untrusted LLM-generated code WITHOUT sandboxing.",
                file=sys.stderr,
            )
            print(
                "This is DANGEROUS and should only be done with trusted code.",
                file=sys.stderr,
            )
            print("\nAre you sure you want to continue?", file=sys.stderr)

            try:
                confirm = input("Type 'yes' to confirm: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nOperation cancelled by user.", file=sys.stderr)
                raise SystemExit(1)

            if confirm == "yes":
                print("\n⚠ Proceeding without sandboxing.", file=sys.stderr)
                return "none"
            else:
                print(
                    "\nConfirmation not received. Please choose again:", file=sys.stderr
                )
                print("  [1] Install Firejail", file=sys.stderr)
                print("  [2] Cancel and exit", file=sys.stderr)
                print("  [3] Proceed WITHOUT sandboxing (UNSAFE)", file=sys.stderr)

        else:
            print("Invalid choice. Please enter 1, 2, or 3.", file=sys.stderr)


def resolve_sandbox_mode(
    sandbox_mode: str | None,
    allow_no_sandbox: bool = False,
    non_interactive: bool = False,
) -> str:
    """
    Resolve the sandbox mode based on availability and user preferences.

    Args:
        sandbox_mode: Requested mode ("firejail", "none", or None for auto-detect).
        allow_no_sandbox: If True and non_interactive, allows unsandboxed mode without prompt.
        non_interactive: If True, fails fast instead of prompting.

    Returns:
        Resolved sandbox mode ("firejail" or "none").

    Raises:
        SandboxError: If Firejail required but unavailable in non-interactive mode.
        SystemExit: If user cancels interactive prompt.
    """
    # Explicit firejail mode
    if sandbox_mode == "firejail":
        status = check_firejail_available()
        if not status.available:
            raise SandboxError(
                f"Firejail sandbox mode requested but not available: {status.error}\n"
                "Install Firejail or use --sandbox-mode=none (UNSAFE)."
            )
        return "firejail"

    # Explicit none mode
    if sandbox_mode == "none":
        if not allow_no_sandbox and not non_interactive:
            print(
                "\n⚠ WARNING: Sandboxing disabled via --sandbox-mode=none",
                file=sys.stderr,
            )
            print("This is UNSAFE for untrusted LLM-generated code!", file=sys.stderr)
        return "none"

    # Auto-detect mode (sandbox_mode is None or "auto")
    status = check_firejail_available()
    if status.available:
        print(f"Using Firejail sandboxing ({status.version})", file=sys.stderr)
        return "firejail"

    # Firejail not available - handle based on mode
    if non_interactive:
        if allow_no_sandbox:
            print(
                f"\n⚠ WARNING: Firejail unavailable ({status.error}), proceeding unsandboxed",
                file=sys.stderr,
            )
            return "none"
        else:
            raise SandboxError(
                f"Firejail not available: {status.error}\n"
                "Install Firejail, or use --allow-no-sandbox to proceed unsafely."
            )

    # Interactive mode - prompt user
    return prompt_sandbox_choice(status.error)


def run_rustc_with_firejail(
    source_file: str,
    output_binary: str,
    command_args: list[str],
    timeout: float = 30.0,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run rustc command using Firejail for sandboxing.

    Args:
        source_file: Path to the Rust source file
        output_binary: Path to the output binary
        command_args: Additional rustc arguments
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    source_dir = os.path.dirname(os.path.abspath(source_file))

    rustc_cmd = (
        [
            "rustc",
        ]
        + command_args
        + [
            os.path.basename(source_file),
            "-o",
            os.path.basename(output_binary),
        ]
    )

    # Get cargo/rustup paths for Firejail whitelist
    # Rust toolchain is typically installed via rustup in ~/.cargo
    home_dir = os.path.expanduser("~")
    cargo_dir = os.environ.get("CARGO_HOME", os.path.join(home_dir, ".cargo"))
    rustup_dir = os.environ.get("RUSTUP_HOME", os.path.join(home_dir, ".rustup"))

    # Firejail command with restrictions
    # Memory limit: 4GB (same as previous Docker config for H100 optimization)
    # Using --whitelist instead of --private to allow access to Rust toolchain
    # while still restricting access to the rest of the filesystem
    firejail_cmd = (
        [
            "firejail",
            "--quiet",
            "--net=none",  # No network
            f"--whitelist={cargo_dir}",  # Allow access to cargo binaries and registry
            f"--whitelist={rustup_dir}",  # Allow access to rustup toolchains
            f"--whitelist={source_dir}",  # Allow access to source directory
            "--read-only=/usr",  # Read-only access to system libraries
            "--read-only=/lib",  # Read-only access to system libraries
            "--read-only=/lib64",  # Read-only access to system libraries (64-bit)
            "--private-tmp",  # Private /tmp directory
            "--rlimit-as=4294967296",  # 4GB memory limit (matches Docker config)
            f"--timeout={int(timeout)}",  # Timeout
            "--cwd",
            source_dir,
        ]
        + FIREJAIL_SECURITY_OPTS
        + rustc_cmd
    )

    try:
        result = subprocess.run(
            firejail_cmd,
            cwd=source_dir,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            firejail_cmd, returncode=124, stdout="", stderr="Command timed out"
        )


def run_binary_with_firejail(
    binary_path: str,
    timeout: float = 30.0,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a compiled binary using Firejail for sandboxing.

    Args:
        binary_path: Path to the binary
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    binary_dir = os.path.dirname(os.path.abspath(binary_path))
    binary_name = os.path.basename(binary_path)

    # Get rustup path for Firejail whitelist (needed for Rust stdlib)
    home_dir = os.path.expanduser("~")
    rustup_dir = os.environ.get("RUSTUP_HOME", os.path.join(home_dir, ".rustup"))

    # Memory limit: 4GB (same as previous Docker config for H100 optimization)
    # Using --whitelist instead of --private to allow access to Rust runtime libraries
    firejail_cmd = (
        [
            "firejail",
            "--quiet",
            "--net=none",
            f"--whitelist={binary_dir}",  # Allow access to binary directory
            f"--whitelist={rustup_dir}",  # Allow access to Rust stdlib (for dynamic linking)
            "--read-only=/usr",  # Read-only access to system libraries
            "--read-only=/lib",  # Read-only access to system libraries
            "--read-only=/lib64",  # Read-only access to system libraries (64-bit)
            "--private-tmp",  # Private /tmp directory
            "--rlimit-as=4294967296",  # 4GB memory limit (matches Docker config)
            f"--timeout={int(timeout)}",
            "--cwd",
            binary_dir,
        ]
        + FIREJAIL_SECURITY_OPTS
        + [f"./{binary_name}"]
    )

    try:
        result = subprocess.run(
            firejail_cmd,
            cwd=binary_dir,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            firejail_cmd, returncode=124, stdout="", stderr="Command timed out"
        )


def run_rustc_sandboxed(
    source_file: str,
    output_binary: str,
    command_args: list[str],
    timeout: float = 30.0,
    capture_output: bool = True,
    sandbox_mode: str | None = None,
) -> subprocess.CompletedProcess:
    """
    Run rustc command with sandboxing (Firejail or none).

    Args:
        source_file: Path to the Rust source file
        output_binary: Path to the output binary
        command_args: Additional rustc arguments
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr
        sandbox_mode: "firejail", "none", or None (auto-detect)

    Returns:
        CompletedProcess with returncode, stdout, stderr

    Raises:
        SandboxError: If sandboxing is required but unavailable
    """
    # Resolve sandbox mode if not already resolved
    if sandbox_mode is None:
        status = check_firejail_available()
        if status.available:
            sandbox_mode = "firejail"
        else:
            sandbox_mode = "none"
            print(
                f"[WARNING] Firejail not available ({status.error}). "
                "Untrusted completions will run UNSANDBOXED.",
                file=sys.stderr,
            )

    if sandbox_mode == "firejail":
        return run_rustc_with_firejail(
            source_file, output_binary, command_args, timeout, capture_output
        )
    elif sandbox_mode == "none":
        # No sandboxing - only for local development with trusted code
        # Validate rustc is available on host (fail fast if missing)
        global _host_rustc_validated
        if not _host_rustc_validated:
            if shutil.which("rustc") is None:
                raise SandboxError(
                    "rustc not found in PATH. "
                    "Install Rust toolchain or use sandbox_mode='firejail'."
                )
            _host_rustc_validated = True

        rustc_cmd = ["rustc"] + command_args + [source_file, "-o", output_binary]
        return subprocess.run(
            rustc_cmd, capture_output=capture_output, text=True, timeout=timeout
        )
    else:
        raise SandboxError(f"Unknown sandbox mode: {sandbox_mode}")


def run_binary_sandboxed(
    binary_path: str,
    timeout: float = 30.0,
    capture_output: bool = True,
    sandbox_mode: str | None = None,
) -> subprocess.CompletedProcess:
    """
    Run a compiled binary with sandboxing (Firejail or none).

    Args:
        binary_path: Path to the binary
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr
        sandbox_mode: "firejail", "none", or None (auto-detect)

    Returns:
        CompletedProcess with returncode, stdout, stderr

    Raises:
        SandboxError: If sandboxing is required but unavailable
    """
    # Resolve sandbox mode if not already resolved
    if sandbox_mode is None:
        status = check_firejail_available()
        if status.available:
            sandbox_mode = "firejail"
        else:
            sandbox_mode = "none"
            print(
                f"[WARNING] Firejail not available ({status.error}). "
                "Untrusted completions will run UNSANDBOXED.",
                file=sys.stderr,
            )

    if sandbox_mode == "firejail":
        return run_binary_with_firejail(binary_path, timeout, capture_output)
    elif sandbox_mode == "none":
        # No sandboxing - only for local development with trusted code
        return subprocess.run(
            [binary_path], capture_output=capture_output, text=True, timeout=timeout
        )
    else:
        raise SandboxError(f"Unknown sandbox mode: {sandbox_mode}")
