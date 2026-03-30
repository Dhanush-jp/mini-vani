import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";

export default function Issues() {
  const { token } = useAuth();
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchIssues = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/v1/issues", {
          headers: { Authorization: `Bearer ${token}` }
        });
        const data = await res.json();
        setIssues(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchIssues();
  }, [token]);

  return (
    <div className="flex flex-col gap-8 transition-all duration-300">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-slate-900 transition-all duration-300">Reported Issues</h1>
          <p className="mt-2 text-lg text-slate-500">View user-reported system issues.</p>
        </div>
      </header>
      
      {loading ? (
        <p>Loading...</p>
      ) : issues.length === 0 ? (
        <p>No issues reported.</p>
      ) : (
        <div className="glass-panel overflow-hidden transition-all duration-300 shadow-lg rounded-2xl">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/80 border-b border-slate-200 uppercase text-slate-500 text-xs tracking-wider">
                <tr>
                  <th className="px-6 py-4 font-semibold">User ID</th>
                  <th className="px-6 py-4 font-semibold">Name</th>
                  <th className="px-6 py-4 font-semibold">Title</th>
                  <th className="px-6 py-4 font-semibold">Description</th>
                  <th className="px-6 py-4 font-semibold">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {issues.map(issue => (
                  <tr key={issue.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4 font-medium">{issue.user_id}</td>
                    <td className="px-6 py-4">{issue.user_name}</td>
                    <td className="px-6 py-4 font-semibold">{issue.title}</td>
                    <td className="px-6 py-4">{issue.description}</td>
                    <td className="px-6 py-4 text-xs whitespace-nowrap">{new Date(issue.timestamp).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
