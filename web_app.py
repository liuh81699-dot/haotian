from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import threading
import time
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_file

from bi_compare.config import CompareConfig, build_config
from bi_compare.report import write_reports
from bi_compare.runner import CompareCancelled, run_compare
from bi_compare.storage import Storage

app = Flask(__name__, template_folder="web/templates")

APP_DATA_DIR = Path("app_data")
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_ROOT = Path("web_output")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

STORE = Storage(APP_DATA_DIR / "bi_compare.db")

FIXED_SETTINGS = {
    "match_cards_by": "name",
    "request_view": "GRID",
    "compare_scope": "chartMain",
    "numeric_tolerance": 0.0,
    "ignore_paths": ["hitCache", "meta.axes.*", "extra.*"],
    "ignore_card_types": ["TEXT", "IFRAME", "PICTURE", "LAYOUT", "SELECTOR", "PARAMETER"],
    "request_offset": 0,
    "request_limit": 20000,
    "max_diffs_per_card": 200,
    "timeout_seconds": 30,
    "sort_arrays_before_compare": False,
    "request_filters": [],
    "request_dynamic_params": [],
}

_ACTIVE_TASKS: dict[str, dict[str, Any]] = {}
_TASK_LOCK = threading.Lock()

_SCHEDULER_THREAD: threading.Thread | None = None
_SCHEDULER_STOP = threading.Event()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _compose_compare_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    envs = raw_payload.get("envs")
    page_pairs = raw_payload.get("page_pairs")
    if not isinstance(envs, dict) or not isinstance(page_pairs, list):
        raise ValueError("Payload must contain envs and page_pairs")

    return {
        "envs": envs,
        "settings": dict(FIXED_SETTINGS),
        "page_pairs": page_pairs,
    }


def _validate_compare_payload(raw_payload: dict[str, Any]) -> tuple[dict[str, Any], CompareConfig]:
    payload = _compose_compare_payload(raw_payload)
    config = build_config(payload)
    return payload, config


def _task_snapshot(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "id": task["id"],
        "status": task["status"],
        "created_at": task.get("created_at"),
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "progress": task.get("progress", {}),
        "error": task.get("error"),
        "summary": task.get("summary"),
        "schedule_id": task.get("schedule_id"),
        "report_json_url": f"/api/tasks/{task['id']}/result" if task.get("report_json_path") else None,
        "report_html_url": f"/api/tasks/{task['id']}/report" if task.get("report_html_path") else None,
    }


def _is_task_active(task_id: str) -> bool:
    with _TASK_LOCK:
        return task_id in _ACTIVE_TASKS


def _has_active_schedule_task(schedule_id: str) -> bool:
    with _TASK_LOCK:
        for task in _ACTIVE_TASKS.values():
            if task.get("schedule_id") == schedule_id:
                return True
    return False


def _create_and_start_task(compare_payload: dict[str, Any], compare_config: CompareConfig, *, schedule_id: str | None = None) -> dict[str, Any]:
    task_id = uuid4().hex[:12]

    STORE.create_task(task_id, compare_payload, schedule_id=schedule_id)

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_task,
        args=(task_id, compare_config, stop_event),
        daemon=True,
    )

    with _TASK_LOCK:
        _ACTIVE_TASKS[task_id] = {
            "thread": thread,
            "stop_event": stop_event,
            "schedule_id": schedule_id,
        }

    thread.start()

    task = STORE.get_task(task_id)
    if not task:
        raise RuntimeError("Task record missing after creation")
    snapshot = _task_snapshot(task)
    if snapshot is None:
        raise RuntimeError("Failed to build task snapshot")
    return snapshot


def _run_task(task_id: str, compare_config: CompareConfig, stop_event: threading.Event) -> None:
    STORE.update_task(
        task_id,
        status="running",
        started_at=_now_iso(),
        progress={
            "stage": "starting",
            "message": "Task started",
            "processed_cards": 0,
            "total_cards": 0,
            "processed_page_pairs": 0,
            "total_page_pairs": len(compare_config.page_pairs),
        },
    )

    def on_progress(payload: dict[str, Any]) -> None:
        STORE.update_task(task_id, progress=payload)

    def should_stop() -> bool:
        return stop_event.is_set()

    try:
        result = run_compare(compare_config, on_progress=on_progress, should_stop=should_stop)
        task_output = OUTPUT_ROOT / task_id
        json_path, html_path = write_reports(result, task_output)

        STORE.update_task(
            task_id,
            status="completed",
            finished_at=_now_iso(),
            summary=result.get("summary", {}),
            report_json_path=str(json_path),
            report_html_path=str(html_path),
        )

    except CompareCancelled as e:
        STORE.update_task(
            task_id,
            status="cancelled",
            finished_at=_now_iso(),
            error=str(e),
        )

    except Exception as e:  # noqa: BLE001
        STORE.update_task(
            task_id,
            status="failed",
            finished_at=_now_iso(),
            error=str(e),
        )

    finally:
        with _TASK_LOCK:
            _ACTIVE_TASKS.pop(task_id, None)


def _scheduler_loop() -> None:
    while not _SCHEDULER_STOP.is_set():
        try:
            now = _now_iso()
            for schedule in STORE.list_due_schedules(now):
                schedule_id = str(schedule["id"])
                if _has_active_schedule_task(schedule_id):
                    continue

                template_name = str(schedule.get("template_name") or "")
                template = STORE.get_template(template_name)
                if not template:
                    STORE.set_schedule_enabled(schedule_id, False)
                    continue

                try:
                    payload, compare_config = _validate_compare_payload(template["payload"])
                except Exception:
                    STORE.set_schedule_enabled(schedule_id, False)
                    continue

                _create_and_start_task(payload, compare_config, schedule_id=schedule_id)
                STORE.mark_schedule_ran(
                    schedule_id,
                    run_at=now,
                    interval_minutes=int(schedule.get("interval_minutes") or 60),
                )

        except Exception:
            # keep scheduler alive, next loop continues
            pass

        _SCHEDULER_STOP.wait(10)


def _start_scheduler() -> None:
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return
    _SCHEDULER_STOP.clear()
    _SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, daemon=True, name="bi-compare-scheduler")
    _SCHEDULER_THREAD.start()


def _stop_scheduler() -> None:
    _SCHEDULER_STOP.set()


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/templates")
def list_templates() -> Any:
    return jsonify({"templates": STORE.list_templates()})


@app.get("/api/templates/<name>")
def get_template(name: str) -> Any:
    tpl = STORE.get_template(name)
    if tpl is None:
        return jsonify({"error": "Template not found"}), 404
    return jsonify({"template": tpl})


@app.post("/api/templates")
def save_template() -> Any:
    payload = request.get_json(force=True, silent=False)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    name = str(payload.get("name") or "").strip()
    content = payload.get("payload")
    if not name:
        return jsonify({"error": "Template name is required"}), 400
    if not isinstance(content, dict):
        return jsonify({"error": "Template payload must be object"}), 400

    try:
        _validate_compare_payload(content)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Invalid template payload: {e}"}), 400

    STORE.upsert_template(name, content)
    tpl = STORE.get_template(name)
    return jsonify({"template": tpl})


@app.delete("/api/templates/<name>")
def delete_template(name: str) -> Any:
    deleted = STORE.delete_template(name)
    if not deleted:
        return jsonify({"error": "Template not found"}), 404
    return jsonify({"ok": True})


@app.get("/api/tasks")
def list_tasks() -> Any:
    limit_str = request.args.get("limit", "100")
    try:
        limit = max(1, min(500, int(limit_str)))
    except ValueError:
        limit = 100

    tasks = [_task_snapshot(t) for t in STORE.list_tasks(limit=limit)]
    return jsonify({"tasks": [t for t in tasks if t is not None]})


@app.post("/api/tasks")
def create_task() -> Any:
    payload = request.get_json(force=True, silent=False)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        compare_payload, compare_config = _validate_compare_payload(payload)
        task = _create_and_start_task(compare_payload, compare_config)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Invalid config: {e}"}), 400

    return jsonify({"task_id": task["id"], "task": task})


@app.get("/api/tasks/<task_id>")
def get_task(task_id: str) -> Any:
    task = STORE.get_task(task_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 404
    snapshot = _task_snapshot(task)
    return jsonify({"task": snapshot})


@app.post("/api/tasks/<task_id>/stop")
def stop_task(task_id: str) -> Any:
    task = STORE.get_task(task_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 404

    with _TASK_LOCK:
        active = _ACTIVE_TASKS.get(task_id)

    if not active:
        return jsonify({"ok": False, "message": "Task is not running"}), 400

    active["stop_event"].set()
    progress = dict(task.get("progress") or {})
    progress["message"] = "Stop requested, waiting current request to finish"
    STORE.update_task(task_id, progress=progress)

    return jsonify({"ok": True, "message": "Stop request sent"})


@app.get("/api/tasks/<task_id>/result")
def get_task_result(task_id: str) -> Any:
    task = STORE.get_task(task_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 404
    path_str = task.get("report_json_path")
    if task.get("status") != "completed" or not path_str:
        return jsonify({"error": "Result not ready"}), 400

    path = Path(str(path_str))
    if not path.exists():
        return jsonify({"error": "Result file missing"}), 500
    return send_file(path, mimetype="application/json")


@app.get("/api/tasks/<task_id>/report")
def get_task_report(task_id: str) -> Any:
    task = STORE.get_task(task_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 404
    path_str = task.get("report_html_path")
    if task.get("status") != "completed" or not path_str:
        return jsonify({"error": "Report not ready"}), 400

    path = Path(str(path_str))
    if not path.exists():
        return jsonify({"error": "Report file missing"}), 500
    return send_file(path, mimetype="text/html")


@app.get("/api/schedules")
def list_schedules() -> Any:
    return jsonify({"schedules": STORE.list_schedules()})


@app.post("/api/schedules")
def save_schedule() -> Any:
    payload = request.get_json(force=True, silent=False)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    schedule_id = str(payload.get("id") or uuid4().hex[:12]).strip()
    name = str(payload.get("name") or "").strip()
    template_name = str(payload.get("template_name") or "").strip()
    interval_raw = payload.get("interval_minutes")
    enabled = bool(payload.get("enabled", True))

    interval_text = "" if interval_raw is None else str(interval_raw).strip()
    if not name and not template_name and not interval_text:
        return jsonify({"ok": True, "skipped": True, "message": "Empty schedule payload, skipped"}), 200

    try:
        interval_minutes = int(interval_raw)
    except (TypeError, ValueError):
        interval_minutes = 60

    if interval_minutes <= 0:
        interval_minutes = 60

    if not name:
        name = f"schedule_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if not template_name:
        templates = STORE.list_templates()
        if templates:
            template_name = str(templates[0].get("name") or "")

    if not template_name or STORE.get_template(template_name) is None:
        return jsonify({"error": "template_name not found, please create template first"}), 400

    schedule = STORE.upsert_schedule(
        schedule_id=schedule_id,
        name=name,
        template_name=template_name,
        interval_minutes=interval_minutes,
        enabled=enabled,
    )
    return jsonify({"schedule": schedule})


@app.post("/api/schedules/<schedule_id>/toggle")
def toggle_schedule(schedule_id: str) -> Any:
    payload = request.get_json(force=True, silent=True) or {}
    enabled = bool(payload.get("enabled", True))

    schedule = STORE.set_schedule_enabled(schedule_id, enabled)
    if not schedule:
        return jsonify({"error": "Schedule not found"}), 404
    return jsonify({"schedule": schedule})


@app.delete("/api/schedules/<schedule_id>")
def delete_schedule(schedule_id: str) -> Any:
    deleted = STORE.delete_schedule(schedule_id)
    if not deleted:
        return jsonify({"error": "Schedule not found"}), 404
    return jsonify({"ok": True})


@app.post("/api/schedules/<schedule_id>/run-now")
def run_schedule_now(schedule_id: str) -> Any:
    schedule = STORE.get_schedule(schedule_id)
    if not schedule:
        return jsonify({"error": "Schedule not found"}), 404

    if _has_active_schedule_task(schedule_id):
        return jsonify({"error": "Schedule already has running task"}), 400

    template = STORE.get_template(str(schedule.get("template_name") or ""))
    if not template:
        return jsonify({"error": "Template for schedule not found"}), 400

    try:
        compare_payload, compare_config = _validate_compare_payload(template["payload"])
        task = _create_and_start_task(compare_payload, compare_config, schedule_id=schedule_id)
        STORE.mark_schedule_ran(
            schedule_id,
            run_at=_now_iso(),
            interval_minutes=int(schedule.get("interval_minutes") or 60),
        )
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400

    return jsonify({"task": task})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BI compare web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", default=8787, type=int, help="Port to bind")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    should_start = True
    if args.debug:
        should_start = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    if should_start:
        _start_scheduler()

    try:
        app.run(host=args.host, port=args.port, debug=args.debug)
    finally:
        _stop_scheduler()
        time.sleep(0.1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
