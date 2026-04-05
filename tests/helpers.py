from __future__ import annotations


def sample_note(
    *,
    note_id: str = "not_1d3tmYTlCICgjy",
    title: str | None = "Quarterly yoghurt budget review",
    created_at: str = "2026-01-27T15:30:00Z",
    updated_at: str = "2026-01-27T16:45:00Z",
    summary_text: str = "The quarterly yoghurt budget review was a success.",
    transcript: list[dict] | None = None,
) -> dict:
    if transcript is None:
        transcript = [
            {
                "speaker": {"source": "microphone"},
                "text": "I'm done pretending.",
                "start_time": created_at,
                "end_time": updated_at,
            },
            {
                "speaker": {"source": "speaker"},
                "text": "Finally.",
                "start_time": created_at,
                "end_time": updated_at,
            },
        ]

    return {
        "id": note_id,
        "object": "note",
        "title": title,
        "owner": {"name": "Oat Benson", "email": "oat@granola.ai"},
        "created_at": created_at,
        "updated_at": updated_at,
        "calendar_event": {
            "event_title": title,
            "invitees": [{"email": "raisin@granola.ai"}],
            "organiser": "oat@granola.ai",
            "calendar_event_id": "evt_123",
            "scheduled_start_time": created_at,
            "scheduled_end_time": updated_at,
        },
        "attendees": [
            {"name": "Oat Benson", "email": "oat@granola.ai"},
            {"name": "Raisin Patel", "email": "raisin@granola.ai"},
        ],
        "folder_membership": [
            {"id": "fol_123", "object": "folder", "name": "Top secret recipes"}
        ],
        "summary_text": summary_text,
        "summary_markdown": "## Summary",
        "transcript": transcript,
    }
