import { useMemo, useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";

import Modal from "../components/Modal";
import FileUpload from "../components/FileUpload";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { uploadExcelFile, fetchImportAudit } from "../services/portal";
import { formatApiError } from "../utils/apiError";

export default function UploadPage() {
  const { role } = useAuth();
  const [file, setFile] = useState(null);
  const [teacherId, setTeacherId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [auditId, setAuditId] = useState(null);
  const [status, setStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [recentAudits, setRecentAudits] = useState([]);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");
  const [selectedReport, setSelectedReport] = useState(null);

  const pollTimer = useRef(null);

  const canUpload = role === "ADMIN" || role === "TEACHER";
  const toastClass = "rounded-xl border px-4 py-3 text-sm shadow-sm";

  function pushToast(type, message) {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((current) => [...current, { id, type, message }]);
    setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 4200);
  }

  useEffect(() => {
    fetchRecentAudits();
  }, []);

  async function fetchRecentAudits() {
    try {
      const { data } = await api.get("/import/audits?limit=8");
      setRecentAudits(data);
    } catch (err) {
      console.error("Failed to fetch recent audits", err);
    }
  }

  async function openAuditReport(nextAuditId) {
    setReportOpen(true);
    setReportLoading(true);
    setReportError("");
    setSelectedReport(null);

    try {
      const detail = await fetchImportAudit(nextAuditId);
      setSelectedReport(detail);
    } catch (err) {
      const message = formatApiError(err);
      setReportError(message);
      pushToast("error", message);
    } finally {
      setReportLoading(false);
    }
  }

  useEffect(() => {
    if (!auditId || (status !== "PENDING" && status !== "PROCESSING")) {
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
      }
      return;
    }

    pollTimer.current = setInterval(async () => {
      try {
        const audit = await fetchImportAudit(auditId);
        setStatus(audit.status);

        if (audit.status === "COMPLETED" || audit.status === "FAILED") {
          const detail = await fetchImportAudit(auditId);
          setResult(detail);
          fetchRecentAudits();
          clearInterval(pollTimer.current);
          setUploading(false);

          if (audit.status === "COMPLETED") {
            pushToast("success", `Import finished: ${audit.created} new records, ${audit.updated} updated.`);
            window.dispatchEvent(new Event("students:refresh"));
          } else {
            pushToast("error", "Import failed. Check error log below.");
          }
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 2500);

    return () => clearInterval(pollTimer.current);
  }, [auditId, status]);

  async function handleUpload() {
    if (!file || uploading) {
      return;
    }

    setUploading(true);
    setProgress(0);
    setResult(null);
    setAuditId(null);
    setStatus(null);

    try {
      const response = await uploadExcelFile(
        file,
        role === "ADMIN" && teacherId ? Number(teacherId) : null,
        (pct) => setProgress(pct),
      );

      setAuditId(response.audit_id);
      setStatus(response.status);
      fetchRecentAudits();
      pushToast("success", "File uploaded. Processing in background...");
    } catch (err) {
      setUploading(false);
      pushToast("error", formatApiError(err));
    }
  }

  const failurePreview = useMemo(() => {
    if (Array.isArray(result?.errors)) {
      return result.errors;
    }
    if (!result?.errors_json) {
      return [];
    }
    try {
      return JSON.parse(result.errors_json);
    } catch (err) {
      console.error("Error parsing audit log:", err);
      return [];
    }
  }, [result]);

  if (!canUpload) {
    return <Card className="p-8 text-center text-slate-600">Access denied.</Card>;
  }

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-2xl p-6 md:p-8">
        <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">
          Intelligent Import
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Upload mass academic data. Processing now happens in the background to prevent timeouts.
        </p>
      </section>

      <Card className="p-6 md:p-8">
        <FileUpload onFileSelected={setFile} disabled={uploading} />
        <div className="mt-6 space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            {role === "ADMIN" ? (
              <input
                className="field-input max-w-xs"
                type="number"
                placeholder="Teacher ID (Optional)"
                value={teacherId}
                onChange={(event) => setTeacherId(event.target.value)}
                disabled={uploading}
              />
            ) : null}
            <button
              type="button"
              className="primary-button rounded-xl px-8"
              disabled={!file || uploading}
              onClick={handleUpload}
            >
              {uploading ? (status === "PROCESSING" ? "Processing..." : "Uploading...") : "Start Import"}
            </button>
          </div>

          {uploading ? (
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-medium text-slate-500">
                <span>{status === "PROCESSING" ? "Processing data on server..." : "Sending file..."}</span>
                <span>{status === "PROCESSING" ? "Task Active" : `${progress}%`}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full bg-linear-to-r from-sky-500 to-indigo-600 transition-all duration-300 ${
                    status === "PROCESSING" ? "animate-pulse w-full" : ""
                  }`}
                  style={{ width: status === "PROCESSING" ? "100%" : `${progress}%` }}
                />
              </div>
              <p className="text-center text-[10px] text-slate-400">
                You can browse other pages; the import will continue in the background.
              </p>
            </div>
          ) : null}
        </div>
      </Card>

      {result ? (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <Card
            className={`overflow-hidden border-t-4 ${
              result.status === "FAILED" ? "border-t-rose-500" : "border-t-emerald-500"
            } p-6`}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-display text-xl font-semibold">Import Result: {result.status}</h3>
              <span className="text-xs font-mono opacity-50">Audit ID: #{result.id}</span>
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div className="rounded-xl bg-slate-50 p-3 text-center dark:bg-slate-800/50">
                <p className="text-[10px] uppercase tracking-wider opacity-50">Total</p>
                <p className="font-display text-xl font-bold">{result.total_rows}</p>
              </div>
              <div className="rounded-xl bg-emerald-50 p-3 text-center dark:bg-emerald-950/30">
                <p className="text-[10px] uppercase tracking-wider text-emerald-600">Created</p>
                <p className="font-display text-xl font-bold text-emerald-700">{result.created}</p>
              </div>
              <div className="rounded-xl bg-sky-50 p-3 text-center dark:bg-sky-950/30">
                <p className="text-[10px] uppercase tracking-wider text-sky-600">Updated</p>
                <p className="font-display text-xl font-bold text-sky-700">{result.updated}</p>
              </div>
              <div className="rounded-xl bg-indigo-50 p-3 text-center dark:bg-indigo-950/30">
                <p className="text-[10px] uppercase tracking-wider text-indigo-600">Skipped</p>
                <p className="font-display text-xl font-bold text-indigo-700">{result.skipped}</p>
              </div>
              <div className="rounded-xl bg-rose-50 p-3 text-center dark:bg-rose-950/30">
                <p className="text-[10px] uppercase tracking-wider text-rose-600">Failed</p>
                <p className="font-display text-xl font-bold text-rose-700">{result.failed}</p>
              </div>
            </div>

            {failurePreview.length > 0 ? (
              <div className="mt-8">
                <h4 className="flex items-center gap-2 font-display font-semibold text-rose-700 dark:text-rose-400">
                  Validation Failures / System Errors
                </h4>
                <div className="mt-3 max-h-64 overflow-y-auto rounded-xl border border-rose-100 bg-rose-50/30">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-rose-100/80 text-[10px] uppercase tracking-wider text-rose-800 backdrop-blur-sm">
                      <tr>
                        <th className="px-4 py-2">Row</th>
                        <th className="px-4 py-2">Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {failurePreview.map((error, index) => (
                        <tr
                          key={`${error.row}-${index}`}
                          className="border-b border-rose-100/50 last:border-0 hover:bg-rose-100/20"
                        >
                          <td className="px-4 py-2 font-bold text-rose-600">#{error.row}</td>
                          <td className="px-4 py-2 opacity-80">{error.error}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </Card>
        </motion.div>
      ) : null}

      <section className="space-y-4">
        <h3 className="font-display text-xl font-semibold text-slate-900">Recent Imports</h3>
        <div className="grid gap-4 md:grid-cols-2">
          {recentAudits.map((audit) => (
            <Card key={audit.id} className="group flex flex-col p-4 transition-all hover:ring-2 hover:ring-sky-500/20">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400">ID: #{audit.id}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    audit.status === "COMPLETED"
                      ? "bg-emerald-100 text-emerald-700"
                      : audit.status === "FAILED"
                        ? "bg-rose-100 text-rose-700"
                        : audit.status === "PROCESSING"
                          ? "bg-sky-100 text-sky-700 animate-pulse"
                          : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {audit.status}
                </span>
              </div>
              <h4 className="mt-2 truncate font-medium text-slate-800">{audit.filename}</h4>
              <p className="text-[10px] text-slate-500">{new Date(audit.uploaded_at).toLocaleString()}</p>

              {audit.status === "COMPLETED" ? (
                <div className="mt-4 flex gap-4 text-center">
                  <div>
                    <p className="text-[10px] uppercase text-slate-400">New</p>
                    <p className="text-sm font-bold text-emerald-600">{audit.created}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase text-slate-400">Upd</p>
                    <p className="text-sm font-bold text-sky-600">{audit.updated}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase text-slate-400">Fail</p>
                    <p className="text-sm font-bold text-rose-600">{audit.failed}</p>
                  </div>
                </div>
              ) : null}

              {audit.status !== "PROCESSING" ? (
                <button
                  type="button"
                  onClick={() => openAuditReport(audit.id)}
                  className="mt-4 w-full rounded-lg bg-slate-50 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
                >
                  View Full Report
                </button>
              ) : null}
            </Card>
          ))}

          {recentAudits.length === 0 ? (
            <p className="py-4 text-sm italic text-slate-500">No recent imports found.</p>
          ) : null}
        </div>
      </section>

      <p className="text-center text-xs opacity-40">
        All imports are immutable and tracked in the system audit logs.
      </p>

      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={[
              toastClass,
              toast.type === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-rose-200 bg-rose-50 text-rose-800",
            ].join(" ")}
          >
            {toast.message}
          </div>
        ))}
      </div>

      <Modal
        open={reportOpen}
        onClose={() => {
          setReportOpen(false);
          setReportError("");
        }}
        title={selectedReport ? `Import Report #${selectedReport.id}` : "Import Report"}
        width="max-w-4xl"
      >
        {reportLoading ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-600">
            Loading import report...
          </div>
        ) : reportError ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-800">
            {reportError}
          </div>
        ) : selectedReport ? (
          <div className="space-y-6">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="font-display text-lg font-semibold text-slate-900">{selectedReport.filename}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    Uploaded {new Date(selectedReport.uploaded_at).toLocaleString()}
                  </p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${
                    selectedReport.status === "COMPLETED"
                      ? "bg-emerald-100 text-emerald-700"
                      : selectedReport.status === "FAILED"
                        ? "bg-rose-100 text-rose-700"
                        : selectedReport.status === "PROCESSING"
                          ? "bg-sky-100 text-sky-700"
                          : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {selectedReport.status}
                </span>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div className="rounded-xl bg-slate-50 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider opacity-50">Total</p>
                <p className="font-display text-xl font-bold">{selectedReport.total_rows}</p>
              </div>
              <div className="rounded-xl bg-emerald-50 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-emerald-600">Created</p>
                <p className="font-display text-xl font-bold text-emerald-700">{selectedReport.created}</p>
              </div>
              <div className="rounded-xl bg-sky-50 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-sky-600">Updated</p>
                <p className="font-display text-xl font-bold text-sky-700">{selectedReport.updated}</p>
              </div>
              <div className="rounded-xl bg-indigo-50 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-indigo-600">Skipped</p>
                <p className="font-display text-xl font-bold text-indigo-700">{selectedReport.skipped}</p>
              </div>
              <div className="rounded-xl bg-rose-50 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-rose-600">Failed</p>
                <p className="font-display text-xl font-bold text-rose-700">{selectedReport.failed}</p>
              </div>
            </div>

            {Array.isArray(selectedReport.errors) && selectedReport.errors.length > 0 ? (
              <div className="space-y-3">
                <h4 className="font-display text-lg font-semibold text-rose-700">
                  Validation Failures / System Errors
                </h4>
                <div className="max-h-80 overflow-y-auto rounded-xl border border-rose-100 bg-rose-50/40">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-rose-100/80 text-[10px] uppercase tracking-wider text-rose-800 backdrop-blur-sm">
                      <tr>
                        <th className="px-4 py-2">Row</th>
                        <th className="px-4 py-2">Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedReport.errors.map((error, index) => (
                        <tr
                          key={`${error.row}-${index}`}
                          className="border-b border-rose-100/50 last:border-0 hover:bg-rose-100/20"
                        >
                          <td className="px-4 py-2 font-bold text-rose-600">#{error.row}</td>
                          <td className="px-4 py-2 opacity-80">{error.error}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-800">
                No row-level errors were recorded for this import.
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
            Select an import report to view its details.
          </div>
        )}
      </Modal>
    </div>
  );
}
