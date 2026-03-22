import { useEffect, useState } from "react";
import Modal from "./Modal";

const INITIAL_FORM = {
  name: "",
  email: "",
  password: "",
  roll_number: "",
  department: "",
  year: "",
  section: "",
  teacher_id: "",
};

export default function StudentFormModal({ open, onClose, onSubmit, loading, role, teachers }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setForm(INITIAL_FORM);
      setError("");
    }
  }, [open]);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    const payload = {
      ...form,
      email: form.email.trim().toLowerCase(),
      name: form.name.trim(),
      department: form.department.trim(),
      section: form.section.trim(),
      roll_number: form.roll_number.trim(),
      year: Number(form.year),
    };
    if (role === "ADMIN") {
      payload.teacher_id = Number(form.teacher_id);
      if (!payload.teacher_id) {
        setError("Teacher is required.");
        return;
      }
    } else {
      delete payload.teacher_id;
    }
    if (!payload.year) {
      setError("Year is required.");
      return;
    }
    const nextError = await onSubmit(payload);
    if (!nextError) {
      onClose();
    } else {
      setError(nextError);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add Student">
      <form onSubmit={handleSubmit} className="grid gap-3 md:grid-cols-2">
        {error ? (
          <p className="md:col-span-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
        ) : null}
        <input className="field-input" placeholder="Student name" value={form.name} onChange={(e) => setField("name", e.target.value)} disabled={loading} required />
        <input className="field-input" type="email" placeholder="Email" value={form.email} onChange={(e) => setField("email", e.target.value)} disabled={loading} required />
        <input className="field-input" type="password" placeholder="Password" value={form.password} onChange={(e) => setField("password", e.target.value)} disabled={loading} minLength={8} required />
        <input className="field-input" placeholder="Roll number" value={form.roll_number} onChange={(e) => setField("roll_number", e.target.value)} disabled={loading} required />
        <input className="field-input" placeholder="Department" value={form.department} onChange={(e) => setField("department", e.target.value)} disabled={loading} required />
        <input className="field-input" type="number" min="1" max="8" placeholder="Year" value={form.year} onChange={(e) => setField("year", e.target.value)} disabled={loading} required />
        <input className="field-input" placeholder="Section" value={form.section} onChange={(e) => setField("section", e.target.value)} disabled={loading} required />
        {role === "ADMIN" ? (
          <select className="field-input" value={form.teacher_id} onChange={(e) => setField("teacher_id", e.target.value)} disabled={loading} required>
            <option value="">Select teacher</option>
            {teachers.map((teacher) => (
              <option key={teacher.id} value={teacher.id}>
                {teacher.name} · {teacher.department}
              </option>
            ))}
          </select>
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
            This student will be assigned automatically to you.
          </div>
        )}
        <div className="md:col-span-2 flex justify-end gap-3">
          <button type="button" onClick={onClose} className="pill-button" disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? "Saving..." : "Create student"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
