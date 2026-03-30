import { useMemo, useState, useEffect, useRef } from "react";
import FileUpload from "../components/FileUpload";
import Card from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { uploadExcelFile, fetchImportAudit } from "../services/portal";
import { formatApiError } from "../utils/apiError";
import api from "../services/api"; // Added for direct audit list fetch

export default function UploadPage() {
  const { role } = useAuth();
  const [file, setFile] = useState(null);
  const [teacherId, setTeacherId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [auditId, setAuditId] = useState(null);
  const [status, setStatus] = useState(null); // PENDING, PROCESSING, COMPLETED, FAILED
  const [result, setResult] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [recentAudits, setRecentAudits] = useState([]);

  const pollTimer = useRef(null);

  const canUpload = role === "ADMIN" || role === "TEACHER";
  const toastClass = "rounded-xl border px-4 py-3 text-sm shadow-sm";

  function pushToast(type, message) {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((current) => [...current, { id, type, message }]);
    setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
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

  // ── Polling logic ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!auditId || (status !== "PENDING" && status !== "PROCESSING")) {
      if (pollTimer.current) clearInterval(pollTimer.current);
      return;
    }

    pollTimer.current = setInterval(async () => {
      try {
        const audit = await fetchImportAudit(auditId);
        setStatus(audit.status);
        if (audit.status === "COMPLETED" || audit.status === "FAILED") {
          const detail = await fetchImportAudit(auditId); // Get full detail with errors
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
    if (!file || uploading) return;
    setUploading(true);
    setProgress(0);
    setResult(null);
    setAuditId(null);
    setStatus(null);

    try {
      const response = await uploadExcelFile(
        file,
        role === "ADMIN" && teacherId ? Number(teacherId) : null,
        (pct) => setProgress(pct)
      );

      // response = { audit_id, status: 'PENDING', message: '...' }
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
    if (!result?.errors_json) return [];
    try {
      return JSON.parse(result.errors_json);
    } catch (e) {
      console.error("Error parsing audit log:", e);
      return [];
    }
  }, [result]);

  if (!canUpload) {
    return <Card className="p-8 text-center text-slate-600">Access denied.</Card>;
  }

  return (
    <div className="space-y-6">
      <section className="glass-panel rounded-2xl p-6 md:p-8">
        <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">Intelligent Import</h2>
        <p className="mt-2 text-sm text-slate-600">
          Upload mass academic data. Processing now happens in the background to prevent timeouts.
        </p>
      </section>

      <Card className="p-6 md:p-8">
        <FileUpload onFileSelected={setFile} disabled={uploading} />
        <div className="mt-6 space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            {role === "ADMIN" && (
              <input
                className="field-input max-w-xs"
                type="number"
                placeholder="Teacher ID (Optional)"
                value={teacherId}
                onChange={(e) => setTeacherId(e.target.value)}
                disabled={uploading}
              />
            ) }
            <button
              type="button"
              className="primary-button rounded-xl px-8"
              disabled={!file || uploading}
              onClick={handleUpload}
            >
              {uploading ? (status === "PROCESSING" ? "Processing..." : "Uploading...") : "Start Import"}
            </button>
          </div>

          {uploading && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-medium text-slate-500">
                <span>{status === "PROCESSING" ? "Processing data on server..." : "Sending file..."}</span>
                <span>{status === "PROCESSING" ? "Task Active" : `${progress}%`}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full bg-linear-to-r from-sky-500 to-indigo-600 transition-all duration-300 ${status === "PROCESSING" ? "animate-pulse w-full" : ""}`}
                  style={{ width: status === "PROCESSING" ? "100%" : `${progress}%` }}
                />
              </div>
              <p className="text-center text-[10px] text-slate-400">
                You can browse other pages; the import will continue in the background.
              </p>
            </div>
          )}
        </div>
      </Card>

      {result && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <Card className={`overflow-hidden border-t-4 ${result.status === "FAILED" ? "border-t-rose-500" : "border-t-emerald-500"} p-6`}>
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

            {failurePreview.length > 0 && (
              <div className="mt-8">
                <h4 className="flex items-center gap-2 font-display font-semibold text-rose-700 dark:text-rose-400">
                  ⚠️ Validation Failures / System Errors
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
                      {failurePreview.map((err, i) => (
                        <tr key={i} className="border-b border-rose-100/50 last:border-0 hover:bg-rose-100/20">
                          <td className="px-4 py-2 font-bold text-rose-600">#{err.row}</td>
                          <td className="px-4 py-2 opacity-80">{err.error}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </Card>
        </motion.div>
      )}

      {/* Recent Imports History */}
      <section className="space-y-4">
        <h3 className="font-display text-xl font-semibold text-slate-900">Recent Imports</h3>
        <div className="grid gap-4 md:grid-cols-2">
          {recentAudits.map((a) => (
            <Card key={a.id} className="group flex flex-col p-4 transition-all hover:ring-2 hover:ring-sky-500/20">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400">ID: #{a.id}</span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  a.status === 'COMPLETED' ? 'bg-emerald-100 text-emerald-700' :
                  a.status === 'FAILED' ? 'bg-rose-100 text-rose-700' :
                  a.status === 'PROCESSING' ? 'bg-sky-100 text-sky-700 animate-pulse' :
                  'bg-slate-100 text-slate-700'
                }`}>
                  {a.status}
                </span>
              </div>
              <h4 className="mt-2 truncate font-medium text-slate-800">{a.filename}</h4>
              <p className="text-[10px] text-slate-500">{new Date(a.uploaded_at).toLocaleString()}</p>
              
              {a.status === 'COMPLETED' && (
                <div className="mt-4 flex gap-4 text-center">
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase">New</p>
                    <p className="text-sm font-bold text-emerald-600">{a.created}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase">Upd</p>
                    <p className="text-sm font-bold text-sky-600">{a.updated}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase">Fail</p>
                    <p className="text-sm font-bold text-rose-600">{a.failed}</p>
                  </div>
                </div>
              )}
              
              {a.status !== 'PROCESSING' && (
                <button 
                  onClick={async () => {
                    setUploading(true);
                    try {
                      const det = await fetchImportAudit(a.id);
                      setResult(det);
                      window.scrollTo({ top: 400, behavior: 'smooth' });
                    } finally {
                      setUploading(false);
                    }
                  }}
                  className="mt-4 w-full rounded-lg bg-slate-50 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
                >
                  View Full Report
                </button>
              )}
            </Card>
          ))}
          {recentAudits.length === 0 && (
            <p className="text-sm text-slate-500 py-4 italic">No recent imports found.</p>
          )}
        </div>
      </section>

      {/* Persistence / Histoy Note */}
      <p className="text-center text-xs opacity-40">
        All imports are immutable and tracked in the system audit logs.
      </p>

      {/* Toast Portal */}
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
    </div>
  );
}

// Simple motion polyfill if framer-motion is missing or just use simple div
function motion_div({ children, ...props }) { return <div {...props}>{children}</div>; }
const motion = { div: motion_div };
