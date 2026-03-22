import { useEffect, useState } from "react";
import DataTable from "../components/DataTable";
import FilterPanel from "../components/FilterPanel";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { usePortalData } from "../hooks/usePortalData";
import { exportStudent, exportStudents, fetchStudents } from "../services/portal";
import { formatApiError, formatBlobError } from "../utils/apiError";

const INITIAL_FILTERS = {
  search: "",
  department: "",
  year: "",
  section: "",
  cgpa_min: "",
  cgpa_max: "",
  risk_level: "",
};

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ExportPage() {
  const { role } = useAuth();
  const { data } = usePortalData(role);
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [rows, setRows] = useState(data.students?.items || []);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRows(data.students?.items || []);
  }, [data.students]);

  async function handleFilterChange(key, value) {
    const next = { ...filters, [key]: value };
    setFilters(next);
    try {
      const payload = Object.fromEntries(Object.entries(next).filter(([, current]) => current !== ""));
      const response = await fetchStudents(role, payload);
      setRows(response.items || []);
    } catch (err) {
      setStatus(formatApiError(err));
    }
  }

  async function handleExportAll() {
    setBusy(true);
    setStatus("");
    try {
      const payload = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ""));
      const response = await exportStudents(payload);
      triggerBlobDownload(response.data, "students_export.xlsx");
      setStatus("Filtered export downloaded.");
    } catch (err) {
      setStatus(await formatBlobError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleExportSingle(row) {
    setBusy(true);
    setStatus("");
    try {
      const response = await exportStudent(row.id, {});
      triggerBlobDownload(response.data, `student_${row.id}_report.xlsx`);
      setStatus(`Exported ${row.name}.`);
    } catch (err) {
      setStatus(await formatBlobError(err));
    } finally {
      setBusy(false);
    }
  }

  if (role === "STUDENT") {
    return (
      <Card className="p-8 text-center text-slate-600">
        Export is available for administrator and teacher accounts.
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-2xl p-6 md:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">Export</h2>
            <p className="mt-2 text-sm text-slate-600">{status || "Download filtered student lists or a single student workbook."}</p>
          </div>
          <button type="button" onClick={handleExportAll} className="primary-button" disabled={busy}>
            {busy ? "Working..." : "Export filtered students"}
          </button>
        </div>
      </section>

      <FilterPanel
        filters={filters}
        onChange={handleFilterChange}
        onReset={() => {
          setFilters(INITIAL_FILTERS);
          setRows(data.students?.items || []);
        }}
        disabled={busy}
      />

      <DataTable
        columns={[
          { key: "name", label: "Name" },
          { key: "department", label: "Department" },
          { key: "cgpa", label: "CGPA" },
          { key: "risk_level", label: "Risk" },
          {
            key: "id",
            label: "Action",
            render: (_, row) => (
              <button
                type="button"
                className="pill-button"
                onClick={(event) => {
                  event.stopPropagation();
                  void handleExportSingle(row);
                }}
              >
                Single report
              </button>
            ),
          },
        ]}
        rows={rows}
      />
    </div>
  );
}
