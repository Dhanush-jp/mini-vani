import { useEffect, useState } from "react";
import Modal from "./Modal";

export default function AssignSubjectModal({ open, onClose, onSubmit, loading, selectedStudent, allSubjects, assignedSubjects }) {
  const [subjectId, setSubjectId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setSubjectId("");
      setError("");
    }
  }, [open]);

  const assignedIds = new Set((assignedSubjects || []).map((subject) => subject.id));
  const availableSubjects = (allSubjects || []).filter((subject) => !assignedIds.has(subject.id));

  async function handleSubmit(event) {
    event.preventDefault();
    if (!selectedStudent) {
      setError("Select a student first.");
      return;
    }
    const nextError = await onSubmit({
      student_id: selectedStudent.id,
      subject_id: Number(subjectId),
    });
    if (!nextError) {
      onClose();
    } else {
      setError(nextError);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Assign Subject" width="max-w-xl">
      <form onSubmit={handleSubmit} className="grid gap-3">
        {error ? (
          <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
        ) : null}
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          Student: {selectedStudent ? `${selectedStudent.name} (${selectedStudent.roll_number})` : "No student selected"}
        </div>
        <select className="field-input" value={subjectId} onChange={(event) => setSubjectId(event.target.value)} required>
          <option value="">Select subject</option>
          {availableSubjects.map((subject) => (
            <option key={subject.id} value={subject.id}>
              {subject.name} | {subject.code} | Sem {subject.semester}
            </option>
          ))}
        </select>
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="pill-button" disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="primary-button" disabled={loading || !availableSubjects.length}>
            {loading ? "Saving..." : "Assign subject"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
