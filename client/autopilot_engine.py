"""
Autopilot: Autonomous Background Digital Worker
================================================
Background execution engine and task queue for running multi-step business
workflows, scheduled operations, batch tasks, and zero-vision automation asynchronously.
"""

import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional


AUTOPILOT_DIR = os.path.expanduser("~/.momento/autopilot")
TASKS_FILE = os.path.join(AUTOPILOT_DIR, "tasks.json")


def ensure_autopilot_dir() -> None:
    os.makedirs(AUTOPILOT_DIR, exist_ok=True)
    if not os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


class AutopilotEngine:
    """Asynchronous worker for scheduling and driving multi-step automation workflows."""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or AUTOPILOT_DIR
        self._lock = threading.Lock()
        self._running_tasks: Dict[str, Dict[str, Any]] = {}
        ensure_autopilot_dir()

    def list_tasks(self) -> List[Dict[str, Any]]:
        """List active and historical background tasks."""
        ensure_autopilot_dir()
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status and logs for a specific background task."""
        with self._lock:
            if task_id in self._running_tasks:
                return dict(self._running_tasks[task_id])
        for t in self.list_tasks():
            if t.get("id") == task_id:
                return t
        return None

    def enqueue_workflow(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        schedule_interval_sec: Optional[int] = None,
        target_app: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create and enqueue a multi-step background workflow task.
        Spawns worker thread immediately if not scheduled recurring.
        """
        clean_name = name.strip() or "Automated Workflow"
        task_id = f"auto_{int(time.time())}_{abs(hash(clean_name)) % 100000}"

        task_record = {
            "id": task_id,
            "name": clean_name,
            "target_app": target_app or "System",
            "steps": steps,
            "total_steps": len(steps),
            "current_step": 0,
            "status": "queued",
            "schedule_interval": schedule_interval_sec,
            "logs": [f"[{time.strftime('%H:%M:%S')}] Workflow '{clean_name}' enqueued."],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "completed_at": None,
            "progress": 0.0
        }

        with self._lock:
            self._running_tasks[task_id] = task_record

        self._save_task_record(task_record)

        # Launch execution worker thread
        worker = threading.Thread(
            target=self._run_workflow_worker,
            args=(task_id,),
            daemon=True,
            name=f"Autopilot-{task_id}"
        )
        worker.start()

        return {
            "success": True,
            "task_id": task_id,
            "task": task_record,
            "message": f"Autopilot: Enqueued '{clean_name}' ({len(steps)} steps) for background execution."
        }

    def _run_workflow_worker(self, task_id: str) -> None:
        """Worker loop executing steps with live log updates."""
        task = None
        with self._lock:
            task = self._running_tasks.get(task_id)

        if not task:
            return

        task["status"] = "running"
        steps = task.get("steps", [])
        total = max(1, len(steps))

        for idx, step in enumerate(steps):
            step_desc = step.get("description") or step.get("action") or f"Step {idx+1}"
            task["current_step"] = idx + 1
            task["progress"] = round((idx + 1) / total, 2)
            task["logs"].append(f"[{time.strftime('%H:%M:%S')}] Executing step {idx+1}/{total}: {step_desc}")

            # Check if step targets Forge native zero-vision hook
            if step.get("type") == "forge_hook":
                from client.forge_engine import global_forge_engine
                hook_res = global_forge_engine.execute_app_hook(
                    app_id=step.get("app_id", ""),
                    action=step.get("action", "add_record"),
                    payload=step.get("payload", {})
                )
                task["logs"].append(f"[{time.strftime('%H:%M:%S')}] [+] Forge Zero-Vision hook: {hook_res.get('log')}")
            else:
                time.sleep(0.4)  # Simulation of background worker progress
                task["logs"].append(f"[{time.strftime('%H:%M:%S')}] [+] Completed step {idx+1}.")

        task["status"] = "completed"
        task["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        task["progress"] = 1.0
        task["logs"].append(f"[{time.strftime('%H:%M:%S')}] Workflow '{task['name']}' finished successfully.")

        self._save_task_record(task)

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """Cancel or stop a background task."""
        with self._lock:
            if task_id in self._running_tasks:
                self._running_tasks[task_id]["status"] = "canceled"
                self._running_tasks[task_id]["logs"].append(f"[{time.strftime('%H:%M:%S')}] Task canceled by user.")
                self._save_task_record(self._running_tasks[task_id])
                return {"success": True, "message": f"Task '{task_id}' canceled."}
        return {"success": False, "error": f"Task '{task_id}' not found or already completed."}

    def _save_task_record(self, record: Dict[str, Any]) -> None:
        ensure_autopilot_dir()
        tasks = self.list_tasks()
        tasks = [t for t in tasks if t.get("id") != record.get("id")]
        tasks.insert(0, record)
        try:
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(tasks[:100], f, indent=2)
        except Exception:
            pass


# Global singleton
global_autopilot_engine = AutopilotEngine()
