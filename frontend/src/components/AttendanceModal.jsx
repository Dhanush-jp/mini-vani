import { useEffect, useState } from "react";
import Modal from "./Modal";

const STATUS_OPTIONS = ["PRESENT", "ABSENT", "LEAVE"];

export default function AttendanceModal({ open, onClose, onSubmit, loading, selectedStudent, subjects }) {
  const [form, setForm] = useState({ subject_id: "", date: "", status: "PRESENT" });
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setForm({ subject_id: "", date: new Date().toISOString().slice(0, 10), status: "PRESENT" });
      setError("");
    }
  }, [open]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!selectedStudent) {
      setError("Select a student first.");
      return;
    }
    const nextError = await onSubmit({
      student_id: selectedStudent.id,
      subject_id: Number(form.subject_id),
      date: form.date,
      status: form.status,
    });
    if (!nextError) {
      onClose();
    } else {
      setError(nextError);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Mark Attendance" width="max-w-xl">
      <form onSubmit={handleSubmit} className="grid gap-3">
        {error ? (
          <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
        ) : null}
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          Student: {selectedStudent ? `${selectedStudent.name} (${selectedStudent.roll_number})` : "No student selected"}
        </div>
        <select className="field-input" value={form.subject_id} onChange={(e) => setForm((current) => ({ ...current, subject_id: e.target.value }))} required>
          <option value="">Select subject</option>
          {subjects.map((subject) => (
            <option key={subject.id} value={subject.id}>
              {subject.name} · Sem {subject.semester}
            </option>
          ))}
        </select>
        <input className="field-input" type="date" value={form.date} onChange={(e) => setForm((current) => ({ ...current, date: e.target.value }))} required />
        <div className="flex gap-2">
          {STATUS_OPTIONS.map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setForm((current) => ({ ...current, status }))}
              className={form.status === status ? "pill-button pill-active" : "pill-button"}
            >
              {status}
            </button>
          ))}
        </div>
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="pill-button" disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? "Saving..." : "Save attendance"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
