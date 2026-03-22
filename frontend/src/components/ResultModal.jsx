import { useEffect, useState } from "react";
import Modal from "./Modal";

export default function ResultModal({ open, onClose, onSubmit, loading, selectedStudent, subjects }) {
  const [form, setForm] = useState({ subject_id: "", semester: "", marks: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setForm({ subject_id: "", semester: "", marks: "" });
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
      semester: Number(form.semester),
      marks: Number(form.marks),
    });
    if (!nextError) {
      onClose();
    } else {
      setError(nextError);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add or Update Result" width="max-w-xl">
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
              {subject.name} · {subject.code}
            </option>
          ))}
        </select>
        <input className="field-input" type="number" min="1" max="12" placeholder="Semester" value={form.semester} onChange={(e) => setForm((current) => ({ ...current, semester: e.target.value }))} required />
        <input className="field-input" type="number" min="0" max="100" step="0.01" placeholder="Marks" value={form.marks} onChange={(e) => setForm((current) => ({ ...current, marks: e.target.value }))} required />
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="pill-button" disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? "Saving..." : "Save result"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
