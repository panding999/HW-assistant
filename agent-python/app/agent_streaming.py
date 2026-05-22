from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any

from app.agent_runtime import AgentTraceStep


_DONE = object()


def stream_agent_events(execute: Callable[[Callable[[AgentTraceStep], None]], Any]) -> Iterator[str]:
    events: queue.Queue[dict[str, Any] | object] = queue.Queue()

    def event_sink(step: AgentTraceStep) -> None:
        events.put(
            {
                "type": "stage",
                "stage": step.stage,
                "status": step.status,
                "message": step.output_summary,
                "trace_step": model_to_data(step),
            }
        )

    def worker() -> None:
        try:
            result = execute(event_sink)
            events.put({"type": "final", "data": model_to_data(result)})
        except Exception as exc:
            events.put({"type": "error", "message": str(exc), "error_type": exc.__class__.__name__})
        finally:
            events.put(_DONE)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = events.get()
        if event is _DONE:
            break
        yield json.dumps(event, ensure_ascii=False) + "\n"


def model_to_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value
