import threading

import psutil


class ResourceMonitor:
    """Monitor and limit resource usage during evaluation."""

    def __init__(
        self,
        max_memory_percent: float = 80.0,
        max_workers: int = 24,
        check_interval: float = 1.0,
    ):
        self.max_memory_percent = max_memory_percent
        self.max_workers = max_workers
        self.check_interval = check_interval
        self._active_workers = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def acquire_worker(self) -> bool:
        """Try to acquire a worker slot. Returns False if limit reached."""

        with self._lock:
            if psutil.virtual_memory().percent > self.max_memory_percent:
                return False
            if self._active_workers >= self.max_workers:
                return False
            self._active_workers += 1
            return True

    def release_worker(self):
        """Release a worker slot."""

        with self._lock:
            self._active_workers = max(0, self._active_workers - 1)

    def stop(self):
        self._stop_event.set()


__all__ = ["ResourceMonitor"]
