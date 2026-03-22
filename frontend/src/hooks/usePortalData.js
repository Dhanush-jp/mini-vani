import { useEffect, useState } from "react";
import { fetchBootstrap } from "../services/portal";
import { formatApiError } from "../utils/apiError";

const EMPTY_BOOTSTRAP = {
  summary: { total_students: 0, avg_cgpa: 0, avg_attendance: 0, high_risk_count: 0 },
  students: { items: [], total: 0 },
  teachers: [],
  subjects: [],
  studentDashboard: null,
  studentSummary: null,
};

export function usePortalData(role) {
  const [data, setData] = useState(EMPTY_BOOTSTRAP);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function reload() {
    setLoading(true);
    setError("");
    try {
      const response = await fetchBootstrap(role);
      setData({ ...EMPTY_BOOTSTRAP, ...response });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [role]);

  return { data, loading, error, reload, setData };
}
