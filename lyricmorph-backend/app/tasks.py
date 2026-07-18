from collections import deque

from .config import settings

try:
    from google.cloud import tasks_v2
except Exception:  # pragma: no cover - optional dependency for deployed mode
    tasks_v2 = None


class InMemoryTaskQueue:
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


class CloudTasksDispatcher:
    def __init__(self) -> None:
        if tasks_v2 is None:
            raise RuntimeError("google-cloud-tasks is not installed")
        if not settings.gcp_project_id:
            raise RuntimeError("GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT is required for Cloud Tasks")
        if not settings.worker_url:
            raise RuntimeError("SKARLY_WORKER_URL is required for Cloud Tasks")
        self._client = tasks_v2.CloudTasksClient()
        self._parent = self._client.queue_path(settings.gcp_project_id, settings.gcp_location, settings.cloud_tasks_queue)

    def enqueue_generation(self, job_id: str) -> None:
        headers = {"Content-Type": "application/json"}
        if settings.worker_shared_secret:
            headers["X-Skarly-Worker-Secret"] = settings.worker_shared_secret

        task: dict = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{settings.worker_url.rstrip('/')}/v1/worker/jobs/{job_id}/run",
                "headers": headers,
                "body": b"{}",
            }
        }
        if settings.cloud_tasks_service_account_email:
            task["http_request"]["oidc_token"] = {
                "service_account_email": settings.cloud_tasks_service_account_email,
            }
        self._client.create_task(request={"parent": self._parent, "task": task})

    def pop_next(self) -> str | None:
        return None

    def size(self) -> int:
        return 0


def build_task_queue():
    if settings.task_backend == "cloud_tasks":
        return CloudTasksDispatcher()
    return InMemoryTaskQueue()


task_queue = build_task_queue()
