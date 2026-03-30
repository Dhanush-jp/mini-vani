import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { formatApiError } from "../utils/apiError";

export default function Login() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", {
        email: form.email.trim().toLowerCase(),
        password: form.password,
      });
      login(data.access_token, data.role, data.user_id);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={onSubmit} className="glass-panel w-full max-w-md rounded-2xl p-8 shadow-xl shadow-slate-900/5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] opacity-60">Secure access</p>
        <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">Sign in</h2>
        <p className="mb-5 mt-3 text-sm opacity-80">Student intelligence portal for admins, teachers, and students.</p>

        {error ? (
          <p className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
        ) : null}

        <label className="mb-1 block text-xs font-medium opacity-60">Email</label>
        <input
          className="field-input mb-3"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
          disabled={loading}
          required
        />

        <label className="mb-1 block text-xs font-medium opacity-60">Password</label>
        <input
          className="field-input mb-5"
          type="password"
          autoComplete="current-password"
          value={form.password}
          onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
          disabled={loading}
          required
          minLength={8}
        />

        <button type="submit" disabled={loading} className="primary-button w-full">
          {loading ? "Signing in..." : "Login"}
        </button>

        <p className="mt-4 text-center text-sm opacity-60">
          New here?{" "}
          <Link to="/register" className="font-medium text-sky-500 underline-offset-2 hover:underline">
            Create an account
          </Link>
        </p>
      </form>
    </div>
  );
}
