# Security Model

- Firejail sandboxing now includes seccomp, capability drops, CPU/file/process limits, and read-only mounts to restrict untrusted Rust execution.
- Dangerous Rust patterns (FFI, compile-time macros, assembly, intrinsics) are blocked with Unicode normalization and raw-string detection.
- Input validation prevents oversized or malformed completions.
- Resource monitoring hooks are available via `ResourceMonitor` to cap workers and memory usage.

## Known Limitations
- Firejail and cargo/clippy must be present on the host to enable full checks.
- The resource monitor only gates worker acquisition; it does not kill running jobs.
