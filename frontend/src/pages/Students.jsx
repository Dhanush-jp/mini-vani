import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import FilterPanel from "../components/FilterPanel";
import StudentFormModal from "../components/StudentFormModal";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { usePortalData } from "../hooks/usePortalData";
import { createStudent, fetchStudents } from "../services/portal";
import { formatApiError } from "../utils/apiError";

const INITIAL_FILTERS = {
  search: "",
  department: "",
  year: "",
  section: "",
  cgpa_min: "",
  cgpa_max: "",
  risk_level: "",
};

export default function Students() {
  const { role } = useAuth();
  const navigate = useNavigate();
  const { data, loading, error, reload } = usePortalData(role);
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [students, setStudents] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    setStudents(data.students?.items || []);
  }, [data.students]);

  async function applyFilters(nextFilters = filters) {
    if (role === "STUDENT") return;
    try {
      const payload = Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value !== ""));
      const response = await fetchStudents(role, payload);
      setStudents(response.items || []);
      setStatus(`${response.total || 0} students matched.`);
    } catch (err) {
      setStatus(formatApiError(err));
    }
  }

  function handleFilterChange(key, value) {
    const next = { ...filters, [key]: value };
    setFilters(next);
    void applyFilters(next);
  }

  function handleReset() {
    setFilters(INITIAL_FILTERS);
    setStudents(data.students?.items || []);
    setStatus("");
  }

  async function handleCreate(payload) {
    setSaving(true);
    try {
      await createStudent(role, payload);
      await reload();
      setStatus("Student created successfully.");
      return "";
    } catch (err) {
      return formatApiError(err);
    } finally {
      setSaving(false);
    }
  }

  const list = students.length ? students : data.students?.items || [];

  if (role === "STUDENT") {
    return (
      <Card className="p-8 text-center text-slate-600">
        The student directory is available to administrators and teachers. Use your dashboard for your own records.
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-2xl p-6 md:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">Students</h2>
            <p className="mt-2 text-sm text-slate-600">{error || status || "Search and open a student profile."}</p>
          </div>
          <button type="button" onClick={() => setModalOpen(true)} className="primary-button">
            Add Student
          </button>
        </div>
      </section>

      <FilterPanel filters={filters} onChange={handleFilterChange} onReset={handleReset} disabled={loading} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {list.map((row, index) => (
          <motion.button
            key={row.id}
            type="button"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.03, duration: 0.35 }}
            onClick={() => navigate(`/students/${row.id}`)}
            className="text-left"
          >
            <Card hover className="h-full p-5 transition">
              <p className="font-display text-lg font-semibold text-slate-900">{row.name}</p>
              <p className="mt-2 text-sm text-slate-600">{row.email}</p>
              <p className="mt-3 text-xs text-slate-400">
                {row.department} · Year {row.year} · {row.roll_number}
              </p>
            </Card>
          </motion.button>
        ))}
      </div>

      {!list.length ? (
        <p className="text-center text-sm text-slate-500">No students in scope yet.</p>
      ) : null}

      <StudentFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleCreate}
        loading={saving}
        role={role}
        teachers={data.teachers || []}
      />
    </div>
  );
}
