import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_runtime import AgentTraceStep
from app.agent_streaming import stream_agent_events


class AgentStreamingTests(unittest.TestCase):
    def test_stream_agent_events_outputs_stage_then_final(self) -> None:
        def execute(event_sink):
            event_sink(
                AgentTraceStep(
                    step_index=1,
                    stage="retrieve",
                    tool_name="search_materials",
                    input_summary="top_k=8",
                    output_summary="retrieved=3",
                    status="SUCCEEDED",
                    duration_ms=3,
                )
            )
            return {"assignment_id": 1, "markdown": "# Report"}

        events = [json.loads(line) for line in stream_agent_events(execute)]

        self.assertEqual(events[0]["type"], "stage")
        self.assertEqual(events[0]["stage"], "retrieve")
        self.assertEqual(events[0]["status"], "SUCCEEDED")
        self.assertEqual(events[0]["message"], "retrieved=3")
        self.assertEqual(events[-1]["type"], "final")
        self.assertEqual(events[-1]["data"]["markdown"], "# Report")

    def test_stream_agent_events_outputs_error_without_final(self) -> None:
        def execute(event_sink):
            event_sink(
                AgentTraceStep(
                    step_index=1,
                    stage="generate",
                    tool_name="build_report_draft",
                    input_summary="start",
                    output_summary="running",
                    status="RUNNING",
                    duration_ms=1,
                )
            )
            raise RuntimeError("boom")

        events = [json.loads(line) for line in stream_agent_events(execute)]

        self.assertEqual(events[0]["type"], "stage")
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("boom", events[-1]["message"])
        self.assertNotIn("final", [event["type"] for event in events])


if __name__ == "__main__":
    unittest.main()
