import api from "./api";
import { normalizeRole } from "../utils/role";

function buildQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === "" || value === null || value === undefined) {
      return;
    }
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

export async function fetchBootstrap(role) {
  const r = normalizeRole(role);
  if (r === "ADMIN") {
    const { data } = await api.get("/admin/bootstrap");
    return data;
  }
  if (r === "TEACHER") {
    const { data } = await api.get("/teacher/bootstrap");
    return data;
  }
  if (r !== "STUDENT") {
    return {
      summary: { total_students: 0, avg_cgpa: 0, avg_attendance: 0, high_risk_count: 0 },
      students: { items: [], total: 0 },
      teachers: [],
      subjects: [],
      studentDashboard: null,
      studentSummary: null,
    };
  }

  const { data } = await api.get("/student/me");
  if (import.meta.env.DEV) {
    console.log("[student/me]", data);
  }

  const summary = data.summary || {};
  const dashboard = data.dashboard || null;

  return {
    summary: {
      total_students: 1,
      avg_cgpa: summary.cgpa ?? 0,
      avg_attendance: summary.attendance_pct ?? 0,
      high_risk_count: (summary.backlogs ?? 0) > 0 ? 1 : 0,
    },
    students: { items: [], total: 0 },
    teachers: [],
    subjects: [],
    studentDashboard: dashboard,
    studentSummary: summary,
    studentMe: data,
  };
}

export async function fetchStudents(role, filters) {
  const r = normalizeRole(role);
  const path = r === "ADMIN" ? "/admin/students" : "/teacher/students";
  const { data } = await api.get(`${path}${buildQuery(filters)}`);
  return data;
}

export async function createStudent(role, payload) {
  const r = normalizeRole(role);
  const path = r === "ADMIN" ? "/admin/students" : "/teacher/students";
  const { data } = await api.post(path, payload);
  return data;
}

export async function fetchStudentDetail(role, studentId) {
  const r = normalizeRole(role);
  const path = r === "ADMIN" ? `/admin/students/${studentId}` : `/teacher/students/${studentId}`;
  const { data } = await api.get(path);
  return data;
}

export async function fetchAttendanceHistory(studentId) {
  const { data } = await api.get(`/teacher/students/${studentId}/attendance`);
  return data;
}

export async function saveAttendance(payload) {
  const { data } = await api.post("/teacher/attendance", payload);
  return data;
}

export async function fetchResults(studentId) {
  const { data } = await api.get(`/teacher/students/${studentId}/results`);
  return data;
}

export async function saveResult(payload) {
  const { data } = await api.post("/teacher/grades", payload);
  return data;
}

export async function fetchStudentSubjects(studentId) {
  const { data } = await api.get(`/teacher/students/${studentId}/subjects`);
  return data;
}

export async function assignStudentSubject(payload) {
  const { data } = await api.post(`/teacher/students/${payload.student_id}/subjects`, payload);
  return data;
}

export async function exportStudents(filters) {
  return api.post("/exports/students", filters, { responseType: "blob" });
}

export async function exportStudent(studentId, filters = {}) {
  return api.post(`/exports/student/${studentId}`, filters, { responseType: "blob" });
}

export async function uploadExcelFile(file, teacherId = null, onProgress) {
  const formData = new FormData();
  formData.append("file", file);
  if (teacherId != null) {
    formData.append("teacher_id", String(teacherId));
  }
  const { data } = await api.post("/import/excel", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (!onProgress || !event?.total) return;
      onProgress(Math.round((event.loaded * 100) / event.total));
    },
  });
  return data;
}

/**
 * Fetch full semester-by-semester history for a student.
 * @param {string} role  - caller role (ADMIN/TEACHER use student id path; STUDENT uses /me)
 * @param {number|null} studentId
 */
export async function fetchSemesterHistory(role, studentId = null) {
  const r = (role || "").toUpperCase();
  const path =
    r === "STUDENT"
      ? "/student/me/semester-history"
      : `/students/${studentId}/semester-history`;
  const { data } = await api.get(path);
  return data;
}

/**
 * Compare two semesters for a student.
 * @param {string} role
 * @param {number|null} studentId
 * @param {number} semA
 * @param {number} semB
 */
export async function fetchSemesterComparison(role, studentId, semA, semB) {
  const r = (role || "").toUpperCase();
  const path =
    r === "STUDENT"
      ? `/student/me/semester-compare`
      : `/students/${studentId}/semester-compare`;
  const { data } = await api.get(path, { params: { sem_a: semA, sem_b: semB } });
  return data;
}

/**
 * Fetch a single import audit (for polling background task status).
 */
export async function fetchImportAudit(auditId) {
  const { data } = await api.get(`/import/audits/${auditId}`);
  return data;
}
