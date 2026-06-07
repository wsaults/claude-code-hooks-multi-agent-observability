"""
Unit tests for the provider seam: build_event_payload(input_data, args, providers).

Run from .claude/hooks/:
    python3 -m unittest discover -s tests

These tests exercise the PUBLIC interface only. Providers are stubbed, so the
suite runs with no live server, no real transcript, and no AI dependencies
(anthropic / dotenv). Domain vocabulary (Worker / Session / Source App) comes
from CONTEXT.md.
"""

import contextlib
import io
import os
import tempfile
import unittest

import send_event
from send_event import build_event_payload


class FakeArgs:
    """Stand-in for argparse.Namespace, holding only what the seam reads."""

    def __init__(self, source_app="demo", event_type="PreToolUse",
                 add_chat=False, summarize=False):
        self.source_app = source_app
        self.event_type = event_type
        self.add_chat = add_chat
        self.summarize = summarize


class BuildEventPayloadSmokeTest(unittest.TestCase):
    def test_returns_a_dict_with_no_providers(self):
        """The seam is callable and returns a payload dict for a Session event."""
        input_data = {"session_id": "abc12345", "transcript_path": ""}
        payload = build_event_payload(input_data, FakeArgs(), providers=[])
        self.assertIsInstance(payload, dict)


class CoreEnvelopeTest(unittest.TestCase):
    def test_envelope_carries_source_app_session_and_event_type(self):
        """With no providers, the envelope is built from input_data + args."""
        input_data = {"session_id": "sess-0001"}
        args = FakeArgs(source_app="cc-agent", event_type="PreToolUse")

        payload = build_event_payload(input_data, args, providers=[])

        self.assertEqual(payload["source_app"], "cc-agent")
        self.assertEqual(payload["session_id"], "sess-0001")
        self.assertEqual(payload["hook_event_type"], "PreToolUse")
        self.assertEqual(payload["payload"], input_data)
        self.assertIsInstance(payload["timestamp"], int)

    def test_session_id_defaults_to_unknown_when_absent(self):
        """A missing Session id falls back to 'unknown', matching the hook today."""
        payload = build_event_payload({}, FakeArgs(), providers=[])
        self.assertEqual(payload["session_id"], "unknown")


class EventSpecificFlatteningTest(unittest.TestCase):
    # The full set of event-type-specific fields the hook forwards to top level.
    FLATTENED_FIELDS = [
        "tool_name", "tool_use_id", "error", "is_interrupt",
        "permission_suggestions", "agent_id", "agent_type",
        "agent_transcript_path", "stop_hook_active", "notification_type",
        "custom_instructions", "source", "reason",
    ]

    def test_present_fields_are_flattened_to_top_level(self):
        """Every event-specific field present in input_data is copied up verbatim."""
        input_data = {"session_id": "s"}
        for i, field in enumerate(self.FLATTENED_FIELDS):
            input_data[field] = "value-%d" % i

        payload = build_event_payload(input_data, FakeArgs(), providers=[])

        for i, field in enumerate(self.FLATTENED_FIELDS):
            self.assertEqual(payload[field], "value-%d" % i)

    def test_absent_fields_are_not_added(self):
        """Fields missing from input_data must not appear on the payload."""
        payload = build_event_payload({"session_id": "s"}, FakeArgs(), providers=[])
        for field in self.FLATTENED_FIELDS:
            self.assertNotIn(field, payload)

    def test_falsy_field_values_are_still_forwarded(self):
        """Presence is keyed on the key existing, not truthiness (e.g. is_interrupt=False)."""
        input_data = {"session_id": "s", "is_interrupt": False, "error": ""}
        payload = build_event_payload(input_data, FakeArgs(), providers=[])
        self.assertIs(payload["is_interrupt"], False)
        self.assertEqual(payload["error"], "")


class ProviderMergeTest(unittest.TestCase):
    def test_provider_fragment_is_merged_into_payload(self):
        """A provider's returned dict fragment is merged onto the payload."""
        def stub_provider(input_data, args, event_data):
            return {"x": 1}

        payload = build_event_payload(
            {"session_id": "s"}, FakeArgs(), providers=[stub_provider]
        )
        self.assertEqual(payload["x"], 1)

    def test_provider_returning_empty_dict_omits_its_field(self):
        """A provider may return {} to contribute nothing (the Worker 'omit' case)."""
        def omit_provider(input_data, args, event_data):
            return {}

        payload = build_event_payload(
            {"session_id": "s"}, FakeArgs(), providers=[omit_provider]
        )
        # Only the core envelope keys are present; the provider added nothing.
        self.assertNotIn("worker", payload)

    def test_provider_can_contribute_worker_fragment(self):
        """The seam accepts a future Worker identity provider returning {'worker': ...}."""
        def worker_provider(input_data, args, event_data):
            return {"worker": "worker-uuid-1234"}

        payload = build_event_payload(
            {"session_id": "s"}, FakeArgs(), providers=[worker_provider]
        )
        self.assertEqual(payload["worker"], "worker-uuid-1234")


class ProviderIsolationTest(unittest.TestCase):
    def test_raising_provider_does_not_propagate_and_drops_only_its_field(self):
        """A provider that raises is isolated: no crash, its field absent,
        and a sibling provider's fragment still lands."""
        def boom_provider(input_data, args, event_data):
            raise RuntimeError("provider exploded")

        def good_provider(input_data, args, event_data):
            return {"survivor": True}

        # boom is first so we also prove later providers still run after a failure.
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            payload = build_event_payload(
                {"session_id": "s"}, FakeArgs(),
                providers=[boom_provider, good_provider],
            )

        self.assertNotIn("boom", payload)
        self.assertIs(payload["survivor"], True)
        # The core envelope is intact despite the failing provider.
        self.assertEqual(payload["session_id"], "s")
        # The failure is logged to stderr (not raised).
        self.assertIn("boom_provider", stderr.getvalue())


class ModelProviderTest(unittest.TestCase):
    def setUp(self):
        self._orig_extractor = send_event.get_model_from_transcript
        self.addCleanup(
            setattr, send_event, "get_model_from_transcript", self._orig_extractor
        )

    def test_model_provider_contributes_model_name_from_transcript(self):
        """The model provider derives model_name for a Session via the extractor."""
        send_event.get_model_from_transcript = (
            lambda session_id, transcript_path: "claude-opus-4-8"
        )
        input_data = {"session_id": "s", "transcript_path": "/fake/transcript.jsonl"}

        payload = build_event_payload(
            input_data, FakeArgs(), providers=[send_event.model_provider]
        )

        self.assertEqual(payload["model_name"], "claude-opus-4-8")

    def test_model_provider_returns_empty_model_name_without_transcript(self):
        """No transcript_path means model_name is '' (key still present, as today)."""
        def fail_if_called(session_id, transcript_path):  # pragma: no cover
            raise AssertionError("extractor must not run without a transcript")

        send_event.get_model_from_transcript = fail_if_called
        payload = build_event_payload(
            {"session_id": "s"}, FakeArgs(), providers=[send_event.model_provider]
        )

        self.assertEqual(payload["model_name"], "")


class SummaryProviderTest(unittest.TestCase):
    def test_summary_provider_adds_summary_when_summarize_requested(self):
        """With --summarize, the provider attaches the generated one-liner."""
        self.addCleanup(
            setattr, send_event, "_summarize_event", send_event._summarize_event
        )
        send_event._summarize_event = lambda event_data: "Reads config from project root"

        payload = build_event_payload(
            {"session_id": "s"}, FakeArgs(summarize=True),
            providers=[send_event.summary_provider],
        )
        self.assertEqual(payload["summary"], "Reads config from project root")

    def test_summary_provider_is_skipped_without_summarize_flag(self):
        """No --summarize means the summarizer is never invoked and no key added."""
        def fail_if_called(event_data):  # pragma: no cover
            raise AssertionError("summarizer must not run without --summarize")

        self.addCleanup(
            setattr, send_event, "_summarize_event", send_event._summarize_event
        )
        send_event._summarize_event = fail_if_called

        payload = build_event_payload(
            {"session_id": "s"}, FakeArgs(summarize=False),
            providers=[send_event.summary_provider],
        )
        self.assertNotIn("summary", payload)

    def test_summary_provider_failure_does_not_crash_and_omits_summary(self):
        """If the summarizer raises, the event still ships with no 'summary' key.

        This is the regression guard for the bug where a summary failure could
        crash the hook and drop the event entirely.
        """
        self.addCleanup(
            setattr, send_event, "_summarize_event", send_event._summarize_event
        )

        def boom(event_data):
            raise RuntimeError("LLM unreachable")

        send_event._summarize_event = boom

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            payload = build_event_payload(
                {"session_id": "s"}, FakeArgs(summarize=True),
                providers=[send_event.summary_provider],
            )

        self.assertNotIn("summary", payload)
        self.assertEqual(payload["session_id"], "s")  # event still intact


class ChatProviderTest(unittest.TestCase):
    def _write_transcript(self, text):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_chat_provider_parses_transcript_lines_when_add_chat(self):
        """With --add-chat, the provider reads the Session transcript into 'chat',
        parsing each JSONL line and skipping malformed ones."""
        path = self._write_transcript(
            '{"role": "user", "n": 1}\n'
            "\n"                       # blank line ignored
            "not json\n"               # malformed line skipped
            '{"role": "assistant", "n": 2}\n'
        )
        payload = build_event_payload(
            {"session_id": "s", "transcript_path": path},
            FakeArgs(add_chat=True), providers=[send_event.chat_provider],
        )
        self.assertEqual(
            payload["chat"], [{"role": "user", "n": 1}, {"role": "assistant", "n": 2}]
        )

    def test_chat_provider_skipped_without_add_chat_flag(self):
        path = self._write_transcript('{"role": "user"}\n')
        payload = build_event_payload(
            {"session_id": "s", "transcript_path": path},
            FakeArgs(add_chat=False), providers=[send_event.chat_provider],
        )
        self.assertNotIn("chat", payload)

    def test_chat_provider_omits_chat_when_transcript_missing(self):
        payload = build_event_payload(
            {"session_id": "s", "transcript_path": "/no/such/file.jsonl"},
            FakeArgs(add_chat=True), providers=[send_event.chat_provider],
        )
        self.assertNotIn("chat", payload)


if __name__ == "__main__":
    unittest.main()
