"""
semester_history.py  ─  services/semester_history.py
Builds rich semester-by-semester performance data for a student:
  - SGPA, CGPA, backlogs per semester
  - Per-subject marks + attendance for every semester (from AcademicRecord)
  - Falls back to Grade + Attendance tables when AcademicRecord is empty
  - Comparison delta between any two semesters
"""
from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models.entities import (
    AcademicRecord,
    Attendance,
    AttendanceStatus,
    Grade,
    SemesterResult,
    Subject,
)
from services.helpers import safe_float, safe_percentage


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _grade_letter(marks: float) -> str:
    if marks >= 90: return "O"
    if marks >= 80: return "A+"
    if marks >= 70: return "A"
    if marks >= 60: return "B+"
    if marks >= 50: return "B"
    if marks >= 40: return "C"
    return "F"


def _subject_rows_from_academic_records(
    db: Session, student_id: int
) -> dict[int, list[dict]]:
    """Build {semester → [subject_row]} from AcademicRecord (imported data)."""
    rows = (
        db.query(AcademicRecord, Subject.name, Subject.code)
        .join(Subject, Subject.id == AcademicRecord.subject_id)
        .filter(AcademicRecord.student_id == student_id)
        .order_by(AcademicRecord.semester.asc(), Subject.name.asc())
        .all()
    )
    by_sem: dict[int, list[dict]] = {}
    for rec, subj_name, subj_code in rows:
        sem = rec.semester
        by_sem.setdefault(sem, []).append({
            "subject_name": subj_name,
            "subject_code": subj_code,
            "marks": round(float(rec.marks), 2),
            "attendance_pct": round(rec.attendance_percentage, 2),
            "backlogs": rec.backlogs,
            "detained": rec.detained,
            "grade": _grade_letter(float(rec.marks)),
            "is_pass": float(rec.marks) >= 40,
            "status": "Pass" if float(rec.marks) >= 40 else "Fail",
        })
    return by_sem


def _subject_rows_from_grades(
    db: Session, student_id: int
) -> dict[int, list[dict]]:
    """Build {semester → [subject_row]} from Grade table (manually entered data)."""
    grade_rows = (
        db.query(Grade, Subject.name, Subject.code)
        .join(Subject, Subject.id == Grade.subject_id)
        .filter(Grade.student_id == student_id)
        .order_by(Grade.semester.asc(), Subject.name.asc())
        .all()
    )

    # attendance per subject (not semester-isolated in old table — best effort)
    att_q = (
        db.query(
            Attendance.subject_id,
            func.count(Attendance.id).label("total"),
            func.sum(
                case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)
            ).label("present"),
        )
        .filter(Attendance.student_id == student_id)
        .group_by(Attendance.subject_id)
        .all()
    )
    att_map = {r.subject_id: safe_percentage(r.present, r.total) for r in att_q}

    by_sem: dict[int, list[dict]] = {}
    for g, subj_name, subj_code in grade_rows:
        sem = g.semester
        by_sem.setdefault(sem, []).append({
            "subject_name": subj_name,
            "subject_code": subj_code,
            "marks": round(safe_float(g.marks), 2),
            "attendance_pct": att_map.get(g.subject_id, 0.0),
            "backlogs": 0,
            "detained": False,
            "grade": g.grade or _grade_letter(safe_float(g.marks)),
            "is_pass": g.is_pass,
            "status": "Pass" if g.is_pass else "Fail",
        })
    return by_sem


def _merge_subject_maps(
    primary: dict[int, list[dict]],
    fallback: dict[int, list[dict]],
) -> dict[int, list[dict]]:
    """Use primary (AcademicRecord) where data exists, else fall back to Grade table."""
    merged: dict[int, list[dict]] = {}
    all_keys = set(primary) | set(fallback)
    for sem in all_keys:
        merged[sem] = primary[sem] if sem in primary and primary[sem] else fallback.get(sem, [])
    return merged


def _semester_summary(subjects: list[dict]) -> dict:
    if not subjects:
        return {"avg_marks": None, "avg_attendance": None, "pass_count": 0, "fail_count": 0, "total_subjects": 0}
    marks_vals = [s["marks"] for s in subjects if s["marks"] is not None]
    att_vals   = [s["attendance_pct"] for s in subjects if s["attendance_pct"] is not None]
    return {
        "avg_marks":     round(sum(marks_vals) / len(marks_vals), 2) if marks_vals else None,
        "avg_attendance": round(sum(att_vals) / len(att_vals), 2)    if att_vals  else None,
        "pass_count":    sum(1 for s in subjects if s["is_pass"]),
        "fail_count":    sum(1 for s in subjects if not s["is_pass"]),
        "total_subjects": len(subjects),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_semester_history(db: Session, student_id: int) -> dict:
    """
    Returns a structured history dict:
    {
      "semesters": [
        {
          "semester": 1,
          "sgpa": 8.2,
          "cgpa": 8.2,
          "backlogs": 0,
          "is_current": False,
          "subjects": [ { subject_name, marks, attendance_pct, grade, is_pass, ... } ],
          "summary": { avg_marks, avg_attendance, pass_count, fail_count, total_subjects }
        },
        ...
      ],
      "current_semester": 4,
      "all_semester_numbers": [1, 2, 3, 4],
    }
    """
    # ── 1. SemesterResult rows ───────────────────────────────────────────────
    sem_results = (
        db.query(SemesterResult)
        .filter(SemesterResult.student_id == student_id)
        .order_by(SemesterResult.semester.asc())
        .all()
    )
    sem_result_map: dict[int, SemesterResult] = {s.semester: s for s in sem_results}

    # ── 2. Subject rows (prefer AcademicRecord, fall back to Grade) ──────────
    ar_map   = _subject_rows_from_academic_records(db, student_id)
    grad_map = _subject_rows_from_grades(db, student_id)
    subj_map = _merge_subject_maps(ar_map, grad_map)

    # ── 3. Build unified semester list ───────────────────────────────────────
    all_sem_nums = sorted(set(sem_result_map) | set(subj_map))

    if not all_sem_nums:
        return {
            "semesters": [],
            "current_semester": None,
            "all_semester_numbers": [],
        }

    current_semester = max(all_sem_nums)

    semesters = []
    for sem in all_sem_nums:
        sr = sem_result_map.get(sem)
        subjects = subj_map.get(sem, [])
        semesters.append({
            "semester":    sem,
            "sgpa":        safe_float(sr.sgpa)    if sr else None,
            "cgpa":        safe_float(sr.cgpa)    if sr else None,
            "backlogs":    int(sr.backlogs)        if sr else None,
            "is_current":  sem == current_semester,
            "subjects":    subjects,
            "summary":     _semester_summary(subjects),
        })

    return {
        "semesters":            semesters,
        "current_semester":    current_semester,
        "all_semester_numbers": all_sem_nums,
    }


def build_semester_comparison(
    db: Session, student_id: int, sem_a: int, sem_b: int
) -> dict:
    """
    Compare performance between two semesters.
    Returns delta values and a subject-level diff table.
    """
    history = build_semester_history(db, student_id)
    sem_map = {s["semester"]: s for s in history["semesters"]}

    a = sem_map.get(sem_a)
    b = sem_map.get(sem_b)

    if not a or not b:
        missing = []
        if not a: missing.append(sem_a)
        if not b: missing.append(sem_b)
        return {"error": f"No data for semester(s): {missing}"}

    def delta(v1, v2):
        if v1 is None or v2 is None:
            return None
        return round(v2 - v1, 2)

    # Subject-level comparison by name
    a_subj = {s["subject_name"]: s for s in a["subjects"]}
    b_subj = {s["subject_name"]: s for s in b["subjects"]}
    all_subjects = sorted(set(a_subj) | set(b_subj))

    subject_diff = []
    for name in all_subjects:
        sa = a_subj.get(name)
        sb = b_subj.get(name)
        subject_diff.append({
            "subject_name": name,
            "sem_a_marks":       sa["marks"]          if sa else None,
            "sem_b_marks":       sb["marks"]          if sb else None,
            "marks_delta":       delta(sa["marks"] if sa else None, sb["marks"] if sb else None),
            "sem_a_attendance":  sa["attendance_pct"] if sa else None,
            "sem_b_attendance":  sb["attendance_pct"] if sb else None,
            "attendance_delta":  delta(sa["attendance_pct"] if sa else None, sb["attendance_pct"] if sb else None),
        })

    return {
        "sem_a": sem_a,
        "sem_b": sem_b,
        "sgpa_delta":        delta(a["sgpa"], b["sgpa"]),
        "cgpa_delta":        delta(a["cgpa"], b["cgpa"]),
        "avg_marks_delta":   delta(a["summary"]["avg_marks"], b["summary"]["avg_marks"]),
        "avg_att_delta":     delta(a["summary"]["avg_attendance"], b["summary"]["avg_attendance"]),
        "backlogs_delta":    delta(a["backlogs"], b["backlogs"]),
        "sem_a_data":        a,
        "sem_b_data":        b,
        "subject_diff":      subject_diff,
    }
