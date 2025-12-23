from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable


@dataclass(slots=True)
class LabelTask:
    task_id: str
    input_text: str
    context: str | None = None
    status: str = "PENDING"
    labels: dict[str, str] = field(default_factory=dict)
    assigned_to: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class LabelQueue:
    """In-memory labeling queue for human-in-the-loop workflows."""

    def __init__(self) -> None:
        self._tasks: dict[str, LabelTask] = {}

    def add_tasks(self, tasks: Iterable[LabelTask]) -> None:
        for task in tasks:
            self._tasks[task.task_id] = task

    def list_tasks(self, status: str | None = None) -> list[LabelTask]:
        tasks = list(self._tasks.values())
        if status is None:
            return tasks
        return [task for task in tasks if task.status == status]

    def assign(self, task_id: str, labeler: str) -> LabelTask:
        task = self._require_task(task_id)
        task.status = "ASSIGNED"
        task.assigned_to = labeler
        return task

    def complete(self, task_id: str, labels: dict[str, str]) -> LabelTask:
        task = self._require_task(task_id)
        task.labels = labels
        task.status = "COMPLETED"
        task.completed_at = datetime.now(timezone.utc)
        return task

    def _require_task(self, task_id: str) -> LabelTask:
        if task_id not in self._tasks:
            raise KeyError(f"Unknown task_id: {task_id}")
        return self._tasks[task_id]
