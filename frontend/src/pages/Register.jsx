import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { formatApiError } from "../utils/apiError";

const ROLES = [
  { value: "STUDENT", label: "Student" },
  { value: "TEACHER", label: "Teacher" },
  { value: "ADMIN", label: "Admin" },
];

const INITIAL_FORM = {
  name: "",
  email: "",
  password: "",
  confirmPassword: "",
  role: "STUDENT",
  department: "",
  roll_number: "",
  year: "",
  section: "",
};

export default function Register() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(INITIAL_FORM);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function validate() {
    if (form.password !== form.confirmPassword) {
      return "Passwords do not match.";
    }
    if (form.role === "TEACHER" && !form.department.trim()) {
      return "Department is required for teacher registration.";
    }
    if (form.role === "STUDENT") {
      if (!form.department.trim() || !form.roll_number.trim() || !form.section.trim()) {
        return "Department, roll number, and section are required for students.";
      }
      if (!Number(form.year)) {
        return "Year is required for students.";
      }
    }
    return "";
  }

  async function onSubmit(event) {
    event.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError("");
    setLoading(true);
    try {
      const payload = {
        name: form.name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        role: form.role,
      };
      if (form.role === "TEACHER") {
        payload.department = form.department.trim();
      }
      if (form.role === "STUDENT") {
        payload.department = form.department.trim();
        payload.roll_number = form.roll_number.trim();
        payload.year = Number(form.year);
        payload.section = form.section.trim();
      }
      const { data } = await api.post("/auth/register", payload);
      login(data.access_token, data.role, data.user_id);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#ffffff] p-4">
      <form onSubmit={onSubmit} className="glass-panel w-full max-w-xl rounded-2xl p-8 text-slate-900 shadow-xl shadow-slate-900/5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Onboarding</p>
        <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">Create account</h2>
        <p className="mb-5 mt-3 text-sm text-slate-600">Use the built-in registration flow for local setup and testing.</p>

        {error ? (
          <p className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
        ) : null}

        <div className="grid gap-3 md:grid-cols-2">
          <input className="field-input" placeholder="Full name" value={form.name} onChange={(event) => setField("name", event.target.value)} required />
          <input className="field-input" type="email" placeholder="Email" value={form.email} onChange={(event) => setField("email", event.target.value)} required />
          <select className="field-input" value={form.role} onChange={(event) => setField("role", event.target.value)}>
            {ROLES.map((role) => (
              <option key={role.value} value={role.value}>
                {role.label}
              </option>
            ))}
          </select>
          {form.role !== "ADMIN" ? (
            <input className="field-input" placeholder="Department" value={form.department} onChange={(event) => setField("department", event.target.value)} />
          ) : (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Admin registration should be restricted outside local development.
            </div>
          )}
          {form.role === "STUDENT" ? <input className="field-input" placeholder="Roll number" value={form.roll_number} onChange={(event) => setField("roll_number", event.target.value)} /> : null}
          {form.role === "STUDENT" ? <input className="field-input" type="number" min="1" max="8" placeholder="Year" value={form.year} onChange={(event) => setField("year", event.target.value)} /> : null}
          {form.role === "STUDENT" ? <input className="field-input" placeholder="Section" value={form.section} onChange={(event) => setField("section", event.target.value)} /> : null}
          <input className="field-input" type="password" placeholder="Password" value={form.password} onChange={(event) => setField("password", event.target.value)} minLength={8} required />
          <input className="field-input" type="password" placeholder="Confirm password" value={form.confirmPassword} onChange={(event) => setField("confirmPassword", event.target.value)} minLength={8} required />
        </div>

        <button type="submit" disabled={loading} className="primary-button mt-5 w-full disabled:opacity-50">
          {loading ? "Creating account..." : "Register"}
        </button>

        <p className="mt-4 text-center text-sm text-slate-500">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-sky-600 underline-offset-2 hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
