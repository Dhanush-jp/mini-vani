from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.entities import Student, Teacher, TeacherStudent, User, UserRole


def get_teacher_or_404(db: Session, user_id: int) -> Teacher:
    teacher = db.query(Teacher).filter(Teacher.user_id == user_id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher profile not found.")
    return teacher


def get_student_or_404(db: Session, student_id: int) -> Student:
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    return student


def assert_student_access(db: Session, current_user: User, student_id: int) -> None:
    if current_user.role == UserRole.ADMIN:
        return
    if current_user.role == UserRole.STUDENT:
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student or student.id != student_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for this student.")
        return
    teacher = get_teacher_or_404(db, current_user.id)
    mapping = (
        db.query(TeacherStudent)
        .filter(TeacherStudent.teacher_id == teacher.id, TeacherStudent.student_id == student_id)
        .first()
    )
    if not mapping:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher is not assigned to this student.")
