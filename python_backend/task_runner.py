from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from python_backend.epub_metadata import mark_epub_generated_by_tool
from python_backend.json_output import dumps_json_line
from python_backend.protocol import TaskEvent, TaskRequest, TaskResult


def resolve_default_log_path() -> Path:
    override = os.environ.get("EPUB_TOOL_LOG_PATH")
    if override:
        return Path(override)

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().with_name("log.txt")

    return Path(__file__).resolve().parent.parent / "log.txt"


LOG_PATH = resolve_default_log_path()
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("EPUB_TOOL_LOG_PATH", str(LOG_PATH))
TASK_SUFFIX = {
    "reformat": "_reformat.epub",
    "decrypt": "_decrypt.epub",
    "encrypt": "_encrypt.epub",
    "font_encrypt": "_font_encrypt.epub",
    "font_decrypt": "_font_decrypt.epub",
    "transfer_img": "_transfer.epub",
}
TASK_LABELS = {
    "reformat": "格式化",
    "decrypt": "文件解密",
    "encrypt": "文件加密",
    "font_encrypt": "字体加密",
    "font_decrypt": "字体解密",
    "transfer_img": "图片转换",
}
MODULE_PATHS = {
    "reformat": "python_backend.services.reformat_epub",
    "decrypt": "python_backend.services.decrypt_epub",
    "encrypt": "python_backend.services.encrypt_epub",
    "font_encrypt": "python_backend.services.encrypt_font",
    "font_decrypt": "python_backend.services.decrypt_font",
    "transfer_img": "python_backend.services.transfer_img",
}
FUNCTION_NAMES = {
    "reformat": "run",
    "decrypt": "run",
    "encrypt": "run",
    "font_encrypt": "run_epub_font_encrypt",
    "font_decrypt": "run_epub_font_decrypt",
    "transfer_img": "run_epub_img_transfer",
}
# Tasks that do not share mutable module globals beyond logger replacement.
PARALLEL_SAFE_TASK_TYPES = frozenset(
    {
        "reformat",
        "decrypt",
        "encrypt",
        "transfer_img",
    }
)
_LOADED_MODULES: dict[str, Any] = {}
_ACTIVE_TASK_CANCEL_EVENTS: dict[str, threading.Event] = {}
_ACTIVE_TASK_LOCK = threading.Lock()


class TaskCancelled(Exception):
    """Raised when the current task is cancelled between files."""


class JsonLineEmitter:
    def __init__(self):
        self._lock = threading.Lock()

    def emit(self, event: TaskEvent) -> None:
        line = dumps_json_line(event.to_dict()) + "\n"
        with self._lock:
            sys.stdout.write(line)
            sys.stdout.flush()


class BroadcastLogger:
    def __init__(
        self,
        emitter: JsonLineEmitter,
        task_id: str,
        context_provider: Callable[[], dict[str, Any]],
    ):
        self.emitter = emitter
        self.task_id = task_id
        self.context_provider = context_provider
        self.path = str(LOG_PATH)
        self._lock = threading.Lock()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            LOG_PATH.write_text(f"time: {current_time}\n", encoding="utf-8")

    def write(self, text: str) -> None:
        text = str(text).rstrip("\n")
        with self._lock:
            with LOG_PATH.open("a", encoding="utf-8") as file:
                file.write(f"{text}\n")
        context = self.context_provider()
        self.emitter.emit(
            TaskEvent(
                event="task.log",
                task_id=self.task_id,
                status="running",
                progress=context["progress"],
                message=text,
                current_file=context["current_file"],
                current_index=context["current_index"],
                total_files=context["total_files"],
                output_path=context["output_path"],
                level="info",
            )
        )


def load_module(task_type: str) -> Any:
    """按任务惰性加载服务模块，并在当前进程内复用。

    sidecar 既会处理实际任务，也会只读取字体列表。原先的实现每次都会
    导入全部六个服务模块，使轻任务和字体列表读取也承担 OCR 相关依赖的
    初始化成本。
    """
    module = _LOADED_MODULES.get(task_type)
    if module is not None:
        return module

    module_path = MODULE_PATHS.get(task_type)
    if module_path is None:
        raise ValueError(f"不支持的任务类型: {task_type}")

    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Python 依赖未安装完整，请先执行 `python -m pip install -r requirements/requirements.txt`。"
        ) from exc

    _LOADED_MODULES[task_type] = module
    return module


@contextmanager
def patched_logger(task_type: str, logger: BroadcastLogger):
    """只替换当前任务模块的 logger，避免为日志配置而导入无关模块。"""
    module = load_module(task_type)
    original = module.logger
    module.logger = logger
    try:
        yield
    finally:
        module.logger = original


def register_task_cancel_event(task_id: str) -> threading.Event:
    event = threading.Event()
    with _ACTIVE_TASK_LOCK:
        _ACTIVE_TASK_CANCEL_EVENTS[task_id] = event
    return event


def clear_task_cancel_event(task_id: str) -> None:
    with _ACTIVE_TASK_LOCK:
        _ACTIVE_TASK_CANCEL_EVENTS.pop(task_id, None)


def request_task_cancel(task_id: str) -> bool:
    with _ACTIVE_TASK_LOCK:
        event = _ACTIVE_TASK_CANCEL_EVENTS.get(task_id)
        if event is None:
            return False
        event.set()
        return True


def is_task_cancelled(task_id: str, cancel_event: threading.Event | None = None) -> bool:
    if cancel_event is not None and cancel_event.is_set():
        return True
    with _ACTIVE_TASK_LOCK:
        event = _ACTIVE_TASK_CANCEL_EVENTS.get(task_id)
        return bool(event and event.is_set())


def ensure_not_cancelled(task_id: str, cancel_event: threading.Event | None = None) -> None:
    if is_task_cancelled(task_id, cancel_event):
        raise TaskCancelled(f"任务已取消: {task_id}")


def build_expected_output_path(
    input_file: str, task_type: str, output_dir: str | None
) -> str | None:
    suffix = TASK_SUFFIX.get(task_type)
    if suffix is None:
        return None
    input_path = Path(input_file)
    target_dir = Path(output_dir) if output_dir else input_path.parent
    return str(target_dir / f"{input_path.stem}{suffix}")


def resolve_generated_output_path(
    input_file: str, task_type: str, output_dir: str | None
) -> str | None:
    candidates = []
    primary_output = build_expected_output_path(input_file, task_type, output_dir)
    fallback_output = build_expected_output_path(input_file, task_type, None)

    for candidate in (primary_output, fallback_output):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return primary_output


def build_progress(index: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((index / total) * 100, 2)


def normalize_target_map(raw_map: Any) -> dict[str, list[str]]:
    if not isinstance(raw_map, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, value in raw_map.items():
        if isinstance(value, list):
            normalized[os.path.normpath(key)] = [str(item) for item in value if item]
    return normalized


def resolve_task_concurrency(task_type: str, options: dict[str, Any]) -> int:
    raw = options.get("task_concurrency", options.get("concurrency", 1))
    try:
        value = int(raw)
    except Exception:
        value = 1
    value = max(1, min(4, value))
    if task_type not in PARALLEL_SAFE_TASK_TYPES:
        return 1
    return value


def list_font_targets(epub_path: str) -> dict[str, Any]:
    font_module = load_module("font_encrypt")
    result = font_module.list_epub_font_encrypt_targets(epub_path)
    return {
        "ok": True,
        "input_file": os.path.normpath(epub_path),
        "font_families": result.get("font_families", []),
    }


def iter_font_targets(epub_paths: list[str]):
    """逐本产生字体列表结果，使 CLI 能在一个 sidecar 中推送批量进度。"""
    total_files = len(epub_paths)
    for index, epub_path in enumerate(epub_paths, start=1):
        normalized_path = os.path.normpath(epub_path)
        try:
            result = list_font_targets(normalized_path)
        except Exception as exc:
            result = {
                "ok": False,
                "input_file": normalized_path,
                "font_families": [],
                "error": str(exc),
            }
        yield {
            "event": "font-targets.progress",
            "current_index": index,
            "total_files": total_files,
            "result": result,
        }


def list_font_targets_batch(epub_paths: list[str]) -> list[dict[str, Any]]:
    """保留可复用的批量 API，供 CLI 和测试调用。"""
    return [event["result"] for event in iter_font_targets(epub_paths)]


def execute_task(
    task_type: str,
    input_file: str,
    output_dir: str | None,
    options: dict[str, Any],
) -> Any:
    module = load_module(task_type)
    func_name = FUNCTION_NAMES.get(task_type)
    if module is None or func_name is None:
        raise ValueError(f"不支持的任务类型: {task_type}")
    func: Callable[..., Any] = getattr(module, func_name)

    if task_type in ("font_encrypt", "font_decrypt"):
        target_map = normalize_target_map(options.get("target_font_families_by_file"))
        default_targets = options.get("target_font_families") or []
        targets = target_map.get(os.path.normpath(input_file), default_targets)
        if not targets:
            return "skip"
        kwargs = {"target_font_families": targets}
        if task_type == "font_decrypt":
            kwargs["ocr_options"] = options
        return func(input_file, output_dir, **kwargs)

    return func(input_file, output_dir)


def _process_one_file(
    *,
    request: TaskRequest,
    emitter: JsonLineEmitter,
    context: dict[str, Any],
    context_lock: threading.Lock,
    completed_counter: list[int],
    index: int,
    input_file: str,
    cancel_event: threading.Event,
) -> tuple[str, Any, str | None, int, str | None]:
    """Return (status, payload, output_path, duration_ms, message)."""
    ensure_not_cancelled(request.task_id, cancel_event)
    normalized_input = os.path.normpath(input_file)
    expected_output = build_expected_output_path(
        normalized_input, request.task_type, request.output_dir
    )

    with context_lock:
        context.update(
            {
                "current_file": normalized_input,
                "current_index": index,
                "progress": build_progress(completed_counter[0], context["total_files"]),
                "output_path": expected_output,
            }
        )
        progress = context["progress"]

    emitter.emit(
        TaskEvent(
            event="task.file.started",
            task_id=request.task_id,
            status="running",
            progress=progress,
            message=f"开始处理 {os.path.basename(normalized_input)}",
            current_file=normalized_input,
            current_index=index,
            total_files=context["total_files"],
            output_path=expected_output,
        )
    )

    start_at = time.perf_counter()
    try:
        ensure_not_cancelled(request.task_id, cancel_event)
        if not normalized_input.lower().endswith(".epub"):
            raise ValueError("当前只支持 .epub 文件")
        if not os.path.exists(normalized_input):
            raise FileNotFoundError(f"EPUB文件不存在: {normalized_input}")
        ret = execute_task(
            request.task_type,
            normalized_input,
            request.output_dir,
            request.options,
        )
        duration_ms = int((time.perf_counter() - start_at) * 1000)
        with context_lock:
            completed_counter[0] += 1
            context["progress"] = build_progress(
                completed_counter[0], context["total_files"]
            )
            progress = context["progress"]

        if ret == 0:
            actual_output = resolve_generated_output_path(
                normalized_input,
                request.task_type,
                request.output_dir,
            )
            if actual_output:
                mark_epub_generated_by_tool(actual_output)
            emitter.emit(
                TaskEvent(
                    event="task.file.finished",
                    task_id=request.task_id,
                    status="success",
                    progress=progress,
                    message=f"处理成功，用时 {duration_ms}ms",
                    current_file=normalized_input,
                    current_index=index,
                    total_files=context["total_files"],
                    output_path=expected_output,
                )
            )
            return "success", actual_output, expected_output, duration_ms, None

        if ret == "skip":
            emitter.emit(
                TaskEvent(
                    event="task.file.finished",
                    task_id=request.task_id,
                    status="skip",
                    progress=progress,
                    message="已跳过",
                    current_file=normalized_input,
                    current_index=index,
                    total_files=context["total_files"],
                    output_path=expected_output,
                    level="warning",
                )
            )
            return (
                "skip",
                {
                    "input_file": normalized_input,
                    "message": "该文件在当前模式下无需处理，或未选择字体目标。",
                },
                expected_output,
                duration_ms,
                None,
            )

        emitter.emit(
            TaskEvent(
                event="task.file.finished",
                task_id=request.task_id,
                status="error",
                progress=progress,
                message=str(ret),
                current_file=normalized_input,
                current_index=index,
                total_files=context["total_files"],
                output_path=expected_output,
                level="error",
            )
        )
        return (
            "error",
            {"input_file": normalized_input, "message": str(ret)},
            expected_output,
            duration_ms,
            str(ret),
        )
    except TaskCancelled:
        with context_lock:
            completed_counter[0] += 1
            context["progress"] = build_progress(
                completed_counter[0], context["total_files"]
            )
            progress = context["progress"]
        emitter.emit(
            TaskEvent(
                event="task.file.finished",
                task_id=request.task_id,
                status="cancelled",
                progress=progress,
                message="任务已取消",
                current_file=normalized_input,
                current_index=index,
                total_files=context["total_files"],
                output_path=expected_output,
                level="warning",
            )
        )
        return (
            "cancelled",
            {"input_file": normalized_input, "message": "任务已取消"},
            expected_output,
            int((time.perf_counter() - start_at) * 1000),
            "任务已取消",
        )
    except Exception as exc:
        with context_lock:
            completed_counter[0] += 1
            context["progress"] = build_progress(
                completed_counter[0], context["total_files"]
            )
            progress = context["progress"]
        emitter.emit(
            TaskEvent(
                event="task.file.finished",
                task_id=request.task_id,
                status="error",
                progress=progress,
                message=str(exc),
                current_file=normalized_input,
                current_index=index,
                total_files=context["total_files"],
                output_path=expected_output,
                level="error",
            )
        )
        return (
            "error",
            {"input_file": normalized_input, "message": str(exc)},
            expected_output,
            int((time.perf_counter() - start_at) * 1000),
            str(exc),
        )


def run_task(request: TaskRequest) -> TaskResult:
    emitter = JsonLineEmitter()
    total_files = len(request.input_files)
    context = {
        "current_file": None,
        "current_index": 0,
        "total_files": total_files,
        "progress": 0.0,
        "output_path": None,
    }
    context_lock = threading.Lock()
    logger = BroadcastLogger(emitter, request.task_id, lambda: context.copy())
    cancel_event = register_task_cancel_event(request.task_id)
    concurrency = resolve_task_concurrency(request.task_type, request.options or {})

    outputs: list[str] = []
    errors: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    cancelled: list[dict[str, str]] = []
    success_count = 0
    completed_counter = [0]

    emitter.emit(
        TaskEvent(
            event="task.started",
            task_id=request.task_id,
            status="started",
            progress=0,
            message=(
                f"正在加载{TASK_LABELS.get(request.task_type, request.task_type)}处理模块…"
                + (f"（并发 {concurrency}）" if concurrency > 1 else "")
            ),
            total_files=total_files,
        )
    )

    try:
        with patched_logger(request.task_type, logger):
            if concurrency <= 1:
                for index, input_file in enumerate(request.input_files, start=1):
                    ensure_not_cancelled(request.task_id, cancel_event)
                    status, payload, _expected, _duration, _message = _process_one_file(
                        request=request,
                        emitter=emitter,
                        context=context,
                        context_lock=context_lock,
                        completed_counter=completed_counter,
                        index=index,
                        input_file=input_file,
                        cancel_event=cancel_event,
                    )
                    if status == "success":
                        success_count += 1
                        if payload and payload not in outputs:
                            outputs.append(payload)
                    elif status == "skip":
                        skipped.append(payload)
                    elif status == "cancelled":
                        cancelled.append(payload)
                        break
                    else:
                        errors.append(payload)
            else:
                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    futures = {
                        executor.submit(
                            _process_one_file,
                            request=request,
                            emitter=emitter,
                            context=context,
                            context_lock=context_lock,
                            completed_counter=completed_counter,
                            index=index,
                            input_file=input_file,
                            cancel_event=cancel_event,
                        ): index
                        for index, input_file in enumerate(request.input_files, start=1)
                    }
                    for future in as_completed(futures):
                        status, payload, _expected, _duration, _message = future.result()
                        if status == "success":
                            success_count += 1
                            if payload and payload not in outputs:
                                outputs.append(payload)
                        elif status == "skip":
                            skipped.append(payload)
                        elif status == "cancelled":
                            cancelled.append(payload)
                        else:
                            errors.append(payload)
                        if cancel_event.is_set():
                            # Let already-running workers finish current file boundaries.
                            continue
    finally:
        clear_task_cancel_event(request.task_id)

    total = total_files
    success = success_count
    failed = len(errors)
    skipped_count = len(skipped)
    cancelled_count = len(cancelled)
    final_status = "error"
    if cancelled_count > 0 and success == 0 and failed == 0 and skipped_count == 0:
        final_status = "cancelled"
    elif cancelled_count > 0:
        final_status = "partial"
    elif failed == 0 and skipped_count == 0:
        final_status = "success"
    elif failed == 0 and skipped_count > 0:
        final_status = "partial"
    elif success > 0 or skipped_count > 0:
        final_status = "partial"

    result = TaskResult(
        ok=failed == 0 and cancelled_count == 0,
        status=final_status,
        outputs=outputs,
        errors=errors,
        skipped=skipped + cancelled,
        summary={
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped_count + cancelled_count,
            "cancelled": cancelled_count,
        },
        log_path=str(LOG_PATH),
    )

    finish_message = "任务已取消" if final_status == "cancelled" else "任务执行完成"
    emitter.emit(
        TaskEvent(
            event="task.finished",
            task_id=request.task_id,
            status=final_status,
            progress=100,
            message=finish_message,
            total_files=total_files,
            result=result.to_dict(),
        )
    )
    return result
