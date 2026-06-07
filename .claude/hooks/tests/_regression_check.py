"""Throwaway regression guard: prove the new seam emits content-identical
payloads to the ORIGINAL inline construction, for every event type, when all
providers succeed. Not part of the unittest suite — run directly:

    cd .claude/hooks && python3 tests/_regression_check.py
"""
import json
import os
import tempfile

import send_event
from send_event import (
    build_event_payload, model_provider, chat_provider, summary_provider,
)


class Args:
    def __init__(self, add_chat=False, summarize=False):
        self.source_app = "demo"
        self.event_type = "EVT"
        self.add_chat = add_chat
        self.summarize = summarize


FIXED_MODEL = "claude-opus-4-8"
FIXED_SUMMARY = "Performs a representative action for the event type"


def old_builder(input_data, args):
    """Verbatim copy of the ORIGINAL main() inline construction (pre-refactor),
    with the model extractor and summarizer replaced by the same fixed stubs the
    new path uses, so we compare construction logic, not I/O."""
    session_id = input_data.get('session_id', 'unknown')
    transcript_path = input_data.get('transcript_path', '')
    model_name = ''
    if transcript_path:
        model_name = FIXED_MODEL  # stub of get_model_from_transcript

    event_data = {
        'source_app': args.source_app,
        'session_id': session_id,
        'hook_event_type': args.event_type,
        'payload': input_data,
        'timestamp': 0,
        'model_name': model_name,
    }

    if 'tool_name' in input_data:
        event_data['tool_name'] = input_data['tool_name']
    if 'tool_use_id' in input_data:
        event_data['tool_use_id'] = input_data['tool_use_id']
    if 'error' in input_data:
        event_data['error'] = input_data['error']
    if 'is_interrupt' in input_data:
        event_data['is_interrupt'] = input_data['is_interrupt']
    if 'permission_suggestions' in input_data:
        event_data['permission_suggestions'] = input_data['permission_suggestions']
    if 'agent_id' in input_data:
        event_data['agent_id'] = input_data['agent_id']
    if 'agent_type' in input_data:
        event_data['agent_type'] = input_data['agent_type']
    if 'agent_transcript_path' in input_data:
        event_data['agent_transcript_path'] = input_data['agent_transcript_path']
    if 'stop_hook_active' in input_data:
        event_data['stop_hook_active'] = input_data['stop_hook_active']
    if 'notification_type' in input_data:
        event_data['notification_type'] = input_data['notification_type']
    if 'custom_instructions' in input_data:
        event_data['custom_instructions'] = input_data['custom_instructions']
    if 'source' in input_data:
        event_data['source'] = input_data['source']
    if 'reason' in input_data:
        event_data['reason'] = input_data['reason']

    if args.add_chat and 'transcript_path' in input_data:
        tp = input_data['transcript_path']
        if os.path.exists(tp):
            chat_data = []
            try:
                with open(tp, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                chat_data.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                event_data['chat'] = chat_data
            except Exception:
                pass

    if args.summarize:
        summary = FIXED_SUMMARY  # stub of generate_event_summary
        if summary:
            event_data['summary'] = summary

    return event_data


def new_builder(input_data, args):
    return build_event_payload(
        input_data, args,
        providers=[model_provider, chat_provider, summary_provider],
    )


# A transcript file shared by add_chat cases.
fd, TRANSCRIPT = tempfile.mkstemp(suffix=".jsonl")
with os.fdopen(fd, "w") as f:
    f.write('{"type": "assistant", "message": {"model": "x"}}\n{"type": "user"}\n')

EVENT_INPUTS = {
    "SessionStart": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                     "source": "startup", "agent_type": "main"},
    "SessionEnd": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                   "reason": "clear"},
    "UserPromptSubmit": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                         "prompt": "hello"},
    "PreToolUse": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                   "tool_name": "Bash", "tool_use_id": "tu_1"},
    "PostToolUse": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                    "tool_name": "Read", "tool_use_id": "tu_2"},
    "PostToolUseFailure": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                           "tool_name": "Edit", "tool_use_id": "tu_3",
                           "error": "boom", "is_interrupt": False},
    "PermissionRequest": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                          "tool_name": "Bash",
                          "permission_suggestions": ["allow"]},
    "Notification": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                     "notification_type": "idle"},
    "SubagentStart": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                      "agent_id": "a1", "agent_type": "Explore"},
    "SubagentStop": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                     "agent_id": "a1", "agent_type": "Explore",
                     "agent_transcript_path": "/tmp/a1.jsonl",
                     "stop_hook_active": True},
    "Stop": {"session_id": "s1", "transcript_path": TRANSCRIPT,
             "stop_hook_active": False},
    "PreCompact": {"session_id": "s1", "transcript_path": TRANSCRIPT,
                   "custom_instructions": "keep tests"},
    # An event with no transcript_path: model_name should be '' in both.
    "NoTranscript": {"session_id": "s2"},
}

# Stub the heavy collaborators so "all providers succeed" deterministically.
send_event.get_model_from_transcript = lambda sid, tp: FIXED_MODEL
send_event._summarize_event = lambda event_data: FIXED_SUMMARY

failures = 0
order_diffs = 0
for name, base_input in EVENT_INPUTS.items():
    for add_chat in (False, True):
        for summarize in (False, True):
            args = Args(add_chat=add_chat, summarize=summarize)
            args.event_type = name
            old = old_builder(dict(base_input), args)
            new = new_builder(dict(base_input), args)
            # Normalize timestamp (time-based; identical logic).
            new = dict(new)
            new['timestamp'] = 0
            # Content equality (order-insensitive): the real server guarantee.
            if old != new:
                failures += 1
                print(f"CONTENT MISMATCH {name} add_chat={add_chat} summarize={summarize}")
                print("  old:", json.dumps(old, sort_keys=True))
                print("  new:", json.dumps(new, sort_keys=True))
            # Byte-for-byte (order-sensitive) — informational only.
            elif json.dumps(old) != json.dumps(new):
                order_diffs += 1

os.remove(TRANSCRIPT)

total = len(EVENT_INPUTS) * 2 * 2
print(f"\nCompared {total} payloads across {len(EVENT_INPUTS)} event types x add_chat x summarize.")
print(f"Content mismatches: {failures}")
print(f"Byte-order-only differences (key position of model_name; semantically equal): {order_diffs}")
print("RESULT:", "PASS (content-identical)" if failures == 0 else "FAIL")
