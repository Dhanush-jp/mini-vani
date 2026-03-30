import { useEffect, useState } from "react";
import AttendanceModal from "../components/AttendanceModal";
import DataTable from "../components/DataTable";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { usePortalData } from "../hooks/usePortalData";
import { fetchAttendanceHistory, saveAttendance } from "../services/portal";
import { formatApiError } from "../utils/apiError";

export default function Attendance() {
  const { role } = useAuth();
  const { data } = usePortalData(role);
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const selectedStudent = (data.students?.items || []).find((student) => String(student.id) === String(selectedStudentId));

  useEffect(() => {
    async function load() {
      if (!selectedStudentId || role === "STUDENT") {
        setItems([]);
        return;
      }
      try {
        const response = await fetchAttendanceHistory(selectedStudentId);
        setItems(response.items || []);
      } catch (err) {
        setStatus(formatApiError(err));
      }
    }
    void load();
  }, [selectedStudentId, role]);

  async function handleSave(payload) {
    setSaving(true);
    try {
      await saveAttendance(payload);
      const response = await fetchAttendanceHistory(payload.student_id);
      setItems(response.items || []);
      setStatus("Attendance saved.");
      return "";
    } catch (err) {
      return formatApiError(err);
    } finally {
      setSaving(false);
    }
  }

  if (role === "STUDENT") {
    return (
      <Card className="p-8 text-center text-slate-600">
        Attendance marking is restricted to teachers and administrators. Your attendance appears on your dashboard.
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-2xl p-6 md:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">Attendance</h2>
            <p className="mt-2 text-sm text-slate-600">{status || "Mark, review, and update attendance per subject."}</p>
          </div>
          <button type="button" onClick={() => setModalOpen(true)} className="primary-button" disabled={!selectedStudent}>
            Add attendance
          </button>
        </div>
        <div className="mt-5">
          <select className="field-input max-w-md" value={selectedStudentId} onChange={(e) => setSelectedStudentId(e.target.value)}>
            <option value="">Select student</option>
            {(data.students?.items || []).map((student) => (
              <option key={student.id} value={student.id}>
                {student.name} · {student.roll_number}
              </option>
            ))}
          </select>
        </div>
      </section>

      <DataTable
        columns={[
          { key: "subject_name", label: "Subject" },
          { key: "date", label: "Date" },
          { key: "status", label: "Status" },
        ]}
        rows={items}
        emptyMessage="Select a student to view attendance history."
      />

      <AttendanceModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleSave}
        loading={saving}
        selectedStudent={selectedStudent}
        subjects={data.subjects || []}
      />
    </div>
  );
}
