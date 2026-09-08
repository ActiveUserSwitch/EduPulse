"""Synthetic-name tests for the IRB research-export layer."""
from __future__ import annotations

from edupulse.research_export import export_row, looks_like_student_transmit, staff_role_code


def test_role_code_is_stable_and_has_no_last_name():
    code = staff_role_code("Ms. Jane Example")
    assert code.startswith("teacher_")
    assert "jane" not in code.lower()
    assert "example" not in code.lower()
    assert staff_role_code("Ms. Jane Example") == code


def test_export_row_strips_names_and_transcript():
    row = {
        "start_iso": "2026-09-08T12:00:00",
        "duration_sec": 4.2,
        "category": "Logistics / Movement / Hallway",
        "cat_conf": 0.8,
        "is_noise": False,
        "transcription": "Ms. Jane Example to Mr. John Sample, send Alex Demo to the office.",
        "students": ["Alex Demo"],
        "roles": ["Ms. Jane Example", "Mr. John Sample"],
        "likely_speaker": "Ms. Jane Example",
        "wav_path": "/tmp/tx.wav",
        "incident_id": "INC-101",
        "acoustic_features": {"rms": 0.2, "speech_ratio": 0.7},
        "information_score": {"value": 0.4, "lexical_surprisal": 1.2, "acoustic_composite_z": -0.1},
        "tags": ["ordinary"],
    }
    exported = export_row(row, staff=["Ms. Jane Example"], salt="test-salt", exclude_medical=True)
    assert exported is not None
    assert "transcription" not in exported
    assert "students" not in exported
    assert "wav_path" not in exported
    assert exported["student_mention_count"] == 1
    assert exported["incident_id_hash"].startswith("INC_")
    assert exported["incident_id_hash"] != "INC-101"
    blob = str(exported).lower()
    assert "jane" not in blob
    assert "alex" not in blob
    assert "sample" not in blob


def test_medical_and_student_transmit_are_dropped():
    medical = {"category": "Medical / Health Emergency", "students": [], "roles": ["Nurse Pat"]}
    assert export_row(medical, staff=[], salt="x", exclude_medical=True) is None
    student_tx = {
        "category": "Discipline (Student Conflict, Defiance, etc.)",
        "students": ["Alex Demo"],
        "roles": [],
        "likely_speaker": "Alex Demo",
        "tags": ["student_transmit"],
    }
    assert looks_like_student_transmit(student_tx)
    assert export_row(student_tx, staff=[], salt="x") is None
