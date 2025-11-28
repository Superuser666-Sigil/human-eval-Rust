"""
Sandbox wrapper for Rust code evaluation in HumanEval.

This module provides secure isolation for running rustc commands on LLM-generated code.
Uses Docker containers for isolation, with Firejail fallback for local development.
Adapted from SigilDERG-Finetuner's eval_sandbox.py for rustc-based execution.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 1.4.2
"""

import fcntl  # For file locking (Unix)
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Cache for rustc validation (avoid checking on every call)
_docker_rustc_validated = False
_host_rustc_validated = False


class SandboxError(Exception):
    """Raised when sandbox operations fail."""

    pass


def check_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_firejail_available() -> bool:
    """Check if Firejail is available."""
    try:
        result = subprocess.run(
            ["firejail", "--version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def build_docker_image() -> bool:
    """
    Build the Docker image for Rust evaluation.

    Returns:
        True if image was built successfully, False otherwise
    """
    # Get the directory containing this file
    script_dir = Path(__file__).parent.parent
    dockerfile_path = script_dir / "Dockerfile.eval"

    if not dockerfile_path.exists():
        # Create Dockerfile if it doesn't exist
        create_dockerfile(dockerfile_path)

    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "-t",
                "human-eval-rust-sandbox",
                "-f",
                str(dockerfile_path),
                str(script_dir),
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max for build
        )
        if result.returncode != 0:
            print(
                f"Warning: Docker build failed: {result.stderr}",
                file=__import__("sys").stderr,
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        print("Warning: Docker build timed out", file=__import__("sys").stderr)
        return False
    except Exception as e:
        print(f"Warning: Docker build error: {e}", file=__import__("sys").stderr)
        return False


def create_dockerfile(dockerfile_path: Path):
    """Create the Dockerfile for the evaluation sandbox.
    
    Matches the approach used in SigilDERG-Finetuner for consistency:
    - Uses rust:1.91.1-slim base image
    - Adds clippy and rustfmt components
    - Pre-downloads common Rust dependencies for --network=none support
    """
    dockerfile_content = """# Rust evaluation sandbox for human-eval-Rust
# This container provides a minimal, isolated environment for compiling Rust code
# Matches the approach used in SigilDERG-Finetuner for consistency

FROM rust:1.91.1-slim

# Install clippy and rustfmt
RUN rustup component add clippy rustfmt

# Create a non-root user for additional security
RUN useradd -m -u 1000 rustuser && \\
    mkdir -p /eval && \\
    chown -R rustuser:rustuser /eval && \\
    mkdir -p /tmp/cargo-target && \\
    chown -R rustuser:rustuser /tmp/cargo-target

# Pre-download required dependencies for evaluation (so they work with --network=none)
# This allows the sandboxed container to compile code using these crates without network access
# Must be done as rustuser so dependencies are cached in the correct user's home directory
USER rustuser
RUN mkdir -p /tmp/deps_cache && \\
    cd /tmp/deps_cache && \\
    cargo init --name deps_cache && \\
    sed -i 's/^edition = .*/edition = "2021"/' Cargo.toml && \\
    echo '    anyhow = "1.0"' >> Cargo.toml && \\
    echo '    thiserror = "1.0"' >> Cargo.toml && \\
    echo '    serde = { version = "1.0", features = ["derive"] }' >> Cargo.toml && \\
    echo '    serde_json = "1.0"' >> Cargo.toml && \\
    echo '    regex = "1.10"' >> Cargo.toml && \\
    echo '    chrono = { version = "0.4", features = ["serde"] }' >> Cargo.toml && \\
    echo '    uuid = { version = "1.6", features = ["v4", "serde"] }' >> Cargo.toml && \\
    echo '    rand = "0.8"' >> Cargo.toml && \\
    echo 'fn main() {}' > src/main.rs && \\
    cargo build --release && \\
    rm -rf /tmp/deps_cache

# Set working directory
WORKDIR /eval

# Default command (can be overridden)
CMD ["/bin/bash"]
"""
    with open(dockerfile_path, "w") as f:
        f.write(dockerfile_content)


def run_rustc_in_docker(
    source_file: str,
    output_binary: str,
    command_args: list[str],
    timeout: float = 30.0,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run rustc command inside a Docker container.

    Args:
        source_file: Path to the Rust source file on host
        output_binary: Path to the output binary on host
        command_args: Additional rustc arguments (e.g., ["--test", "--edition=2021"])
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    # Ensure Docker image exists (with process-safe file locking)
    # Check if image exists first (fast path)
    check_result = subprocess.run(
        ["docker", "images", "-q", "human-eval-rust-sandbox"],
        capture_output=True,
        text=True,
    )
    if check_result.stdout.strip():
        # Image exists, proceed
        pass
    else:
        # Image doesn't exist - need to build it with file lock to prevent multiple processes
        lock_file_path = (
            Path(tempfile.gettempdir()) / "human-eval-rust-docker-build.lock"
        )
        lock_file = None

        try:
            # Open lock file in append mode (create if doesn't exist)
            lock_file = open(lock_file_path, "a")
            try:
                # Try to acquire exclusive lock (non-blocking)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    # We have the lock - double-check image still doesn't exist
                    check_result = subprocess.run(
                        ["docker", "images", "-q", "human-eval-rust-sandbox"],
                        capture_output=True,
                        text=True,
                    )
                    if not check_result.stdout.strip():
                        # Still doesn't exist, we build it
                        print(
                            "Building Docker image for evaluation sandbox...",
                            file=__import__("sys").stderr,
                        )
                        if not build_docker_image():
                            raise SandboxError(
                                "Failed to build Docker image. Run with --sandbox-mode=none for local dev."
                            )
                finally:
                    # Release lock
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except BlockingIOError:
                # Another process is building - wait for it to finish
                # Release non-blocking lock attempt and acquire blocking lock
                lock_file.close()
                lock_file = open(lock_file_path, "a")
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # Blocking wait
                # Lock acquired means other process finished - verify image exists
                check_result = subprocess.run(
                    ["docker", "images", "-q", "human-eval-rust-sandbox"],
                    capture_output=True,
                    text=True,
                )
                if not check_result.stdout.strip():
                    raise SandboxError(
                        "Docker image build failed (another process attempted it). Run with --sandbox-mode=none for local dev."
                    )
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError):
            # File locking not available (Windows or other issue) - fall back to simple check
            # This is a best-effort approach
            print(
                "Warning: File locking not available, building Docker image without coordination",
                file=__import__("sys").stderr,
            )
            print(
                "Building Docker image for evaluation sandbox...",
                file=__import__("sys").stderr,
            )
            if not build_docker_image():
                raise SandboxError(
                    "Failed to build Docker image. Run with --sandbox-mode=none for local dev."
                )
        finally:
            if lock_file is not None:
                lock_file.close()

    # Validate rustc is available in the sandbox (fail fast if broken)
    # Only check once per process to avoid performance overhead
    global _docker_rustc_validated
    if not _docker_rustc_validated:
        test_cmd = [
            "docker",
            "run",
            "--rm",
            "human-eval-rust-sandbox",
            "bash",
            "-lc",
            "which rustc && rustc --version",
        ]
        test_result = subprocess.run(
            test_cmd, capture_output=True, text=True, timeout=10
        )
        if test_result.returncode != 0:
            raise SandboxError(
                f"Rust toolchain not available in sandbox. "
                f"This indicates the Docker image is broken.\n"
                f"stdout: {test_result.stdout}\n"
                f"stderr: {test_result.stderr}\n"
                f"Try rebuilding the image or check Docker setup."
            )
        _docker_rustc_validated = True

    # Convert host paths to absolute
    source_file = os.path.abspath(source_file)
    output_binary = os.path.abspath(output_binary)
    source_dir = os.path.dirname(source_file)
    source_name = os.path.basename(source_file)
    output_name = os.path.basename(output_binary)

    # Base Docker options (security restrictions)
    # Optimized for H100: 4GB memory limit (was 512m) to handle complex Rust compilation
    # 2GB tmpfs (was 300m) to prevent "disk full" errors during build
    base_docker_opts = [
        "--rm",  # Remove container after execution
        "--memory=4g",  # Limit memory (increased for complex Rust compilation)
        "--cpus=1",  # Limit CPU
        "--read-only",  # Read-only root filesystem
        "--tmpfs",
        "/tmp:rw,exec,nosuid,size=2g,mode=1777",  # Temporary writable space (increased for build artifacts)
        "-v",
        f"{source_dir}:/eval:ro",  # Mount source directory as read-only
        "-w",
        "/eval",  # Working directory
        "-e",
        "CARGO_TARGET_DIR=/tmp/cargo-target",  # Set cargo to use tmpfs
    ]

    # Build rustc command
    rustc_cmd = (
        [
            "rustc",
        ]
        + command_args
        + [
            source_name,
            "-o",
            output_name,
        ]
    )

    # Run with --network=none (most secure)
    docker_cmd = (
        [
            "docker",
            "run",
        ]
        + base_docker_opts
        + [
            "--network=none",  # No network access
            "human-eval-rust-sandbox",
        ]
        + rustc_cmd
    )

    try:
        result = subprocess.run(
            docker_cmd, capture_output=capture_output, text=True, timeout=timeout
        )

        # Check for Docker infrastructure errors
        if result.returncode != 0 and capture_output:
            error_output = (result.stderr or "") + (result.stdout or "")
            error_lower = error_output.lower()

            docker_error_patterns = [
                "docker: error response from daemon",
                "failed to create task for container",
                "failed to create shim task",
                "oci runtime create failed",
                "error mounting",
                "read-only file system",
                "cannot create directory",
                "permission denied",
                "no space left on device",
            ]

            if any(pattern in error_lower for pattern in docker_error_patterns):
                raise SandboxError(
                    f"Docker infrastructure error: {error_output[:500]}\n"
                    f"This indicates a problem with the Docker setup, not the code being evaluated.\n"
                    f"Check Docker daemon status, disk space, and permissions."
                )

        return result
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            docker_cmd, returncode=124, stdout="", stderr="Command timed out"
        )


def run_binary_in_docker(
    binary_path: str,
    timeout: float = 30.0,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a compiled binary inside a Docker container.

    Args:
        binary_path: Path to the binary on host
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    binary_path = os.path.abspath(binary_path)
    binary_dir = os.path.dirname(binary_path)
    binary_name = os.path.basename(binary_path)

    # Base Docker options
    # Optimized for H100: 4GB memory limit (was 512m) to handle complex Rust compilation
    # 2GB tmpfs (was 300m) to prevent "disk full" errors during build
    base_docker_opts = [
        "--rm",
        "--memory=4g",  # Limit memory (increased for complex Rust compilation)
        "--cpus=1",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,size=2g,mode=1777",  # Temporary writable space (increased for build artifacts)
        "-v",
        f"{binary_dir}:/eval:ro",
        "-w",
        "/eval",
    ]

    docker_cmd = (
        [
            "docker",
            "run",
        ]
        + base_docker_opts
        + [
            "--network=none",
            "human-eval-rust-sandbox",
            f"./{binary_name}",
        ]
    )

    try:
        result = subprocess.run(
            docker_cmd, capture_output=capture_output, text=True, timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            docker_cmd, returncode=124, stdout="", stderr="Command timed out"
        )


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

    # Firejail command with restrictions
    firejail_cmd = [
        "firejail",
        "--quiet",
        "--net=none",  # No network
        "--private",  # Private filesystem
        "--private-cwd",  # Private working directory
        "--rlimit-as=512000000",  # 512MB memory limit
        f"--timeout={int(timeout)}",  # Timeout
        "--cwd",
        source_dir,
    ] + rustc_cmd

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

    firejail_cmd = [
        "firejail",
        "--quiet",
        "--net=none",
        "--private",
        "--private-cwd",
        "--rlimit-as=512000000",
        f"--timeout={int(timeout)}",
        "--cwd",
        binary_dir,
        f"./{binary_name}",
    ]

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
    sandbox_mode: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """
    Run rustc command with sandboxing (Docker preferred, Firejail fallback).

    Args:
        source_file: Path to the Rust source file
        output_binary: Path to the output binary
        command_args: Additional rustc arguments
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr
        sandbox_mode: "docker", "firejail", "none", or None (auto-detect)

    Returns:
        CompletedProcess with returncode, stdout, stderr

    Raises:
        SandboxError: If sandboxing is required but unavailable
    """
    # Auto-detect sandbox mode if not specified
    auto_mode = sandbox_mode is None
    if sandbox_mode is None:
        if check_docker_available():
            sandbox_mode = "docker"
        elif check_firejail_available():
            sandbox_mode = "firejail"
        else:
            sandbox_mode = "none"
            if auto_mode:
                print(
                    "[WARNING] sandbox-mode=auto resolved to 'none' "
                    "(no Docker or Firejail detected). "
                    "Untrusted completions will run UNSANDBOXED.",
                    file=sys.stderr,
                )

    if sandbox_mode == "docker":
        return run_rustc_in_docker(
            source_file, output_binary, command_args, timeout, capture_output
        )
    elif sandbox_mode == "firejail":
        return run_rustc_with_firejail(
            source_file, output_binary, command_args, timeout, capture_output
        )
    elif sandbox_mode == "none":
        # No sandboxing - only for local development with trusted code
        # Validate rustc is available on host (fail fast if missing)
        # Only check once per process to avoid performance overhead
        global _host_rustc_validated
        if not _host_rustc_validated:
            import shutil

            if shutil.which("rustc") is None:
                raise SandboxError(
                    "rustc not found in PATH. "
                    "Install Rust toolchain or use sandbox_mode='docker' or 'firejail'."
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
    sandbox_mode: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """
    Run a compiled binary with sandboxing (Docker preferred, Firejail fallback).

    Args:
        binary_path: Path to the binary
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr
        sandbox_mode: "docker", "firejail", "none", or None (auto-detect)

    Returns:
        CompletedProcess with returncode, stdout, stderr

    Raises:
        SandboxError: If sandboxing is required but unavailable
    """
    # Auto-detect sandbox mode if not specified
    auto_mode = sandbox_mode is None
    if sandbox_mode is None:
        if check_docker_available():
            sandbox_mode = "docker"
        elif check_firejail_available():
            sandbox_mode = "firejail"
        else:
            sandbox_mode = "none"
            if auto_mode:
                print(
                    "[WARNING] sandbox-mode=auto resolved to 'none' "
                    "(no Docker or Firejail detected). "
                    "Untrusted completions will run UNSANDBOXED.",
                    file=sys.stderr,
                )

    if sandbox_mode == "docker":
        return run_binary_in_docker(binary_path, timeout, capture_output)
    elif sandbox_mode == "firejail":
        return run_binary_with_firejail(binary_path, timeout, capture_output)
    elif sandbox_mode == "none":
        # No sandboxing - only for local development with trusted code
        return subprocess.run(
            [binary_path], capture_output=capture_output, text=True, timeout=timeout
        )
    else:
        raise SandboxError(f"Unknown sandbox mode: {sandbox_mode}")
