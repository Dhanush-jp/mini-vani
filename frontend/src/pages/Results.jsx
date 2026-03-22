import { useEffect, useState } from "react";
import AssignSubjectModal from "../components/AssignSubjectModal";
import DataTable from "../components/DataTable";
import ResultModal from "../components/ResultModal";
import { useAuth } from "../context/AuthContext";
import { usePortalData } from "../hooks/usePortalData";
import { assignStudentSubject, fetchResults, fetchStudentSubjects, saveResult } from "../services/portal";
import { formatApiError } from "../utils/apiError";

export default function Results() {
  const { role } = useAuth();
  const { data } = usePortalData(role);
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [items, setItems] = useState([]);
  const [assignedSubjects, setAssignedSubjects] = useState([]);
  const [status, setStatus] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [subjectModalOpen, setSubjectModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [subjectSaving, setSubjectSaving] = useState(false);

  const selectedStudent = (data.students?.items || []).find((student) => String(student.id) === String(selectedStudentId));

  useEffect(() => {
    async function load() {
      if (!selectedStudentId || role === "STUDENT") {
        setItems([]);
        setAssignedSubjects([]);
        return;
      }
      try {
        const [resultResponse, subjectResponse] = await Promise.all([
          fetchResults(selectedStudentId),
          fetchStudentSubjects(selectedStudentId),
        ]);
        setItems(resultResponse.items || []);
        setAssignedSubjects(subjectResponse.items || []);
      } catch (err) {
        setStatus(formatApiError(err));
      }
    }
    void load();
  }, [selectedStudentId, role]);

  async function handleSave(payload) {
    setSaving(true);
    try {
      await saveResult(payload);
      const response = await fetchResults(payload.student_id);
      setItems(response.items || []);
      setStatus("Result saved.");
      return "";
    } catch (err) {
      return formatApiError(err);
    } finally {
      setSaving(false);
    }
  }

  async function handleAssignSubject(payload) {
    setSubjectSaving(true);
    try {
      await assignStudentSubject(payload);
      const response = await fetchStudentSubjects(payload.student_id);
      setAssignedSubjects(response.items || []);
      setStatus("Subject assigned.");
      return "";
    } catch (err) {
      return formatApiError(err);
    } finally {
      setSubjectSaving(false);
    }
  }

  if (role === "STUDENT") {
    return (
      <div className="glass-panel rounded-2xl p-8 text-center text-slate-600">
        Result management is restricted to teachers and admins. View your grades on the dashboard and analytics.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-2xl p-6 md:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">Results</h2>
            <p className="mt-2 text-sm text-slate-600">{status || "Assign subjects first, then store marks and pass or fail status."}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => setSubjectModalOpen(true)} className="pill-button" disabled={!selectedStudent}>
              Assign Subject
            </button>
            <button type="button" onClick={() => setModalOpen(true)} className="primary-button" disabled={!selectedStudent || !assignedSubjects.length}>
              Add Result
            </button>
          </div>
        </div>
        <div className="mt-5">
          <select className="field-input max-w-md" value={selectedStudentId} onChange={(event) => setSelectedStudentId(event.target.value)}>
            <option value="">Select student</option>
            {(data.students?.items || []).map((student) => (
              <option key={student.id} value={student.id}>
                {student.name} | {student.roll_number}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="glass-panel rounded-2xl p-6">
        <h3 className="font-display text-xl font-semibold text-slate-900">Assigned subjects</h3>
        <div className="mt-4 flex flex-wrap gap-2">
          {assignedSubjects.length ? (
            assignedSubjects.map((subject) => (
              <span key={subject.id} className="pill-button">
                {subject.name} | {subject.code} | Sem {subject.semester}
              </span>
            ))
          ) : (
            <p className="text-sm text-slate-500">No subjects assigned for the selected student yet.</p>
          )}
        </div>
      </section>

      <DataTable
        columns={[
          { key: "subject_name", label: "Subject" },
          { key: "subject_code", label: "Code" },
          { key: "semester", label: "Semester" },
          { key: "marks", label: "Marks" },
          { key: "grade", label: "Grade" },
          { key: "is_pass", label: "Status", render: (value) => (value ? "Pass" : "Fail") },
        ]}
        rows={items}
        emptyMessage="Select a student to view subject results."
      />

      <AssignSubjectModal
        open={subjectModalOpen}
        onClose={() => setSubjectModalOpen(false)}
        onSubmit={handleAssignSubject}
        loading={subjectSaving}
        selectedStudent={selectedStudent}
        allSubjects={data.subjects || []}
        assignedSubjects={assignedSubjects}
      />

      <ResultModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleSave}
        loading={saving}
        selectedStudent={selectedStudent}
        subjects={assignedSubjects}
      />
    </div>
  );
}
