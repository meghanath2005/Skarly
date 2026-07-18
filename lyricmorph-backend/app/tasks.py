from collections import deque


class InMemoryTaskQueue:
    """Small local queue used by the inline FastAPI worker."""

    def __init__(self) -> None:
        self._queue: deque[str] = deque()

    def enqueue_generation(self, job_id: str) -> None:
        self._queue.append(job_id)

    def pop_next(self) -> str | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def size(self) -> int:
        return len(self._queue)


task_queue = InMemoryTaskQueue()
