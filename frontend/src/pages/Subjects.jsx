import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";

export default function Subjects() {
  const { token, role } = useAuth();
  const [subjects, setSubjects] = useState([]);
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Create form
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [semester, setSemester] = useState("");
  
  // Assign form
  const [assignStudent, setAssignStudent] = useState("");
  const [assignSubject, setAssignSubject] = useState("");
  
  const [msg, setMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const fetchData = async () => {
    try {
      setLoading(true);
      setErrorMsg("");
      const [subjRes, stuRes] = await Promise.all([
        fetch("http://localhost:8000/api/v1/subjects", { headers: { Authorization: `Bearer ${token}` } }),
        fetch("http://localhost:8000/api/v1/admin/bootstrap", { headers: { Authorization: `Bearer ${token}` } })
      ]);
      
      if (!subjRes.ok) throw new Error("Failed to fetch subjects");
      const subjData = await subjRes.json();
      setSubjects(Array.isArray(subjData) ? subjData : []);

      if (stuRes.ok) {
        const stuData = await stuRes.json();
        setStudents(Array.isArray(stuData.students) ? stuData.students : []);
      }
    } catch (err) {
      console.error(err);
      setErrorMsg("Failed to load initial data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [token]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setMsg(""); setErrorMsg("");
    try {
      const res = await fetch("http://localhost:8000/api/v1/subjects", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name, code, semester: parseInt(semester, 10) })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create subject");
      setMsg("Subject created successfully");
      setName(""); setCode(""); setSemester("");
      fetchData();
    } catch (err) {
      setErrorMsg(err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure? This will permanently delete the subject and all related grades/attendance.")) return;
    setMsg(""); setErrorMsg("");
    try {
      const res = await fetch(`http://localhost:8000/api/v1/subjects/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to delete subject");
      }
      setMsg("Subject deleted successfully");
      fetchData();
    } catch (err) {
      setErrorMsg(err.message);
    }
  };

  const handleAssign = async (e) => {
    e.preventDefault();
    setMsg(""); setErrorMsg("");
    if (!assignStudent || !assignSubject) {
      setErrorMsg("Please select both a student and a subject.");
      return;
    }
    try {
      const res = await fetch("http://localhost:8000/api/v1/subjects/assign", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ student_id: parseInt(assignStudent, 10), subject_id: parseInt(assignSubject, 10) })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to assign subject");
      setMsg(data.message || "Subject assigned successfully");
      setAssignStudent(""); setAssignSubject("");
    } catch (err) {
      setErrorMsg(err.message);
    }
  };

  if (role !== "ADMIN") {
    return <div className="p-8 text-center text-red-500">Access Denied. Admins only.</div>;
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl transition-all duration-300">
      <h1 className="font-display text-4xl font-bold tracking-tight text-slate-900 transition-all duration-300">Manage Subjects</h1>
      
      {msg && <div className="p-4 bg-emerald-50 text-emerald-700 rounded-2xl transition-all duration-300 shadow-sm border border-emerald-100">{msg}</div>}
      {errorMsg && <div className="p-4 bg-rose-50 text-rose-700 rounded-2xl transition-all duration-300 shadow-sm border border-rose-100">{errorMsg}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Create Subject Card */}
        <div className="glass-panel p-6 shadow-sm rounded-2xl transition-all duration-300 hover:shadow-md">
          <h2 className="text-xl font-semibold mb-4 text-slate-800">Create New Subject</h2>
          <form onSubmit={handleCreate} className="flex flex-col gap-4">
            <div>
              <label className="block text-sm mb-1 text-slate-600 font-medium">Subject Name</label>
              <input type="text" className="field-input" value={name} onChange={e=>setName(e.target.value)} required placeholder="e.g. Advanced AI" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm mb-1 text-slate-600 font-medium">Code</label>
                <input type="text" className="field-input" value={code} onChange={e=>setCode(e.target.value)} required placeholder="e.g. CS501" />
              </div>
              <div>
                <label className="block text-sm mb-1 text-slate-600 font-medium">Semester</label>
                <input type="number" min="1" max="8" className="field-input" value={semester} onChange={e=>setSemester(e.target.value)} required placeholder="1-8" />
              </div>
            </div>
            <button type="submit" className="primary-button mt-2 transition-all duration-300">Create Subject</button>
          </form>
        </div>

        {/* Assign Subject Card */}
        <div className="glass-panel p-6 shadow-sm rounded-2xl transition-all duration-300 hover:shadow-md">
          <h2 className="text-xl font-semibold mb-4 text-slate-800">Assign Subject to Student</h2>
          <form onSubmit={handleAssign} className="flex flex-col gap-4">
            <div>
              <label className="block text-sm mb-1 text-slate-600 font-medium">Select Student</label>
              <select className="field-input bg-white" value={assignStudent} onChange={e=>setAssignStudent(e.target.value)} required>
                <option value="">-- Select Student --</option>
                {students.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.roll_number})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm mb-1 text-slate-600 font-medium">Select Subject</label>
              <select className="field-input bg-white" value={assignSubject} onChange={e=>setAssignSubject(e.target.value)} required>
                <option value="">-- Select Subject --</option>
                {subjects.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.code}) - Sem {s.semester}</option>
                ))}
              </select>
            </div>
            <button type="submit" className="primary-button mt-2 transition-all duration-300 bg-linear-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500">Assign Subject</button>
          </form>
        </div>
      </div>

      {/* Subject List Table */}
      <div className="glass-panel p-1 shadow-sm rounded-2xl transition-all duration-300 mt-2">
        <div className="p-5 border-b border-slate-100">
           <h2 className="text-xl font-semibold text-slate-800">Subject Database</h2>
        </div>
        {loading ? <div className="p-6 text-slate-500">Loading directory...</div> : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/80 border-b border-slate-200 uppercase text-slate-500 text-xs tracking-wider">
                <tr>
                  <th className="px-6 py-4 font-semibold">Subject Name</th>
                  <th className="px-6 py-4 font-semibold">Code</th>
                  <th className="px-6 py-4 font-semibold">Semester</th>
                  <th className="px-6 py-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {subjects.length === 0 ? (
                  <tr><td colSpan="4" className="text-center py-8 text-slate-400">No subjects officially registered.</td></tr>
                ) : (
                  subjects.map(s => (
                    <tr key={s.id} className="hover:bg-slate-50/50 transition-colors duration-200">
                      <td className="px-6 py-4 font-medium text-slate-800">{s.name}</td>
                      <td className="px-6 py-4">{s.code}</td>
                      <td className="px-6 py-4">Semester {s.semester}</td>
                      <td className="px-6 py-4 text-right">
                        <button 
                          onClick={() => handleDelete(s.id)} 
                          className="text-rose-500 hover:text-rose-700 hover:bg-rose-50 px-3 py-1.5 rounded-xl transition-all duration-200 font-medium text-xs"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
