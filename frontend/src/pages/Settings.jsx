import { useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function Settings() {
  const { role, token } = useAuth();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [issueTitle, setIssueTitle] = useState("");
  const [issueDesc, setIssueDesc] = useState("");
  const [msg, setMsg] = useState("");
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch("http://localhost:8000/api/v1/auth/change-password", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update password");
      setMsg(data.message);
      setOldPassword("");
      setNewPassword("");
    } catch (err) {
      setMsg(err.message);
    }
  };

  const handleIssueSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch("http://localhost:8000/api/v1/issues", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ title: issueTitle, description: issueDesc })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to report issue");
      setMsg(data.message);
      setIssueTitle("");
      setIssueDesc("");
    } catch (err) {
      setMsg(err.message);
    }
  };

  const toggleTheme = () => {
    const newTheme = theme === "light" ? "dark" : "light";
    setTheme(newTheme);
    localStorage.setItem("theme", newTheme);
    document.documentElement.classList.toggle("dark", newTheme === "dark");
  };

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <h1 className="font-display text-3xl font-bold tracking-tight">Settings</h1>
      {msg && <div className="p-4 bg-sky-500/10 text-sky-500 rounded-2xl mb-4 border border-sky-500/20">{msg}</div>}
      
      <div className="glass-panel p-6 shadow-sm rounded-2xl">
        <h2 className="text-xl font-semibold mb-4">Appearance</h2>
        <div className="flex items-center justify-between">
          <span className="opacity-80">Current Theme: {theme}</span>
          <button onClick={toggleTheme} className="pill-button">Toggle Dark Mode</button>
        </div>
      </div>

      <div className="glass-panel p-6 shadow-sm rounded-2xl transition-all duration-300">
        <h2 className="text-xl font-semibold mb-4">Change Password</h2>
        <form onSubmit={handlePasswordChange} className="flex flex-col gap-4">
          <input 
            type="password" 
            placeholder="Old Password" 
            className="field-input" 
            value={oldPassword} 
            onChange={e => setOldPassword(e.target.value)} 
            required 
          />
          <input 
            type="password" 
            placeholder="New Password" 
            className="field-input" 
            value={newPassword} 
            onChange={e => setNewPassword(e.target.value)} 
            required 
          />
          <button type="submit" className="primary-button self-start">Update Password</button>
        </form>
      </div>

      <div className="glass-panel p-6 shadow-sm rounded-2xl transition-all duration-300">
        <h2 className="text-xl font-semibold mb-4">Report an Issue</h2>
        <form onSubmit={handleIssueSubmit} className="flex flex-col gap-4">
          <input 
            type="text" 
            placeholder="Issue Title" 
            className="field-input" 
            value={issueTitle} 
            onChange={e => setIssueTitle(e.target.value)} 
            required 
          />
          <textarea 
            placeholder="Describe your issue..." 
            className="field-input" 
            rows="4" 
            value={issueDesc} 
            onChange={e => setIssueDesc(e.target.value)} 
            required 
          />
          <button type="submit" className="primary-button self-start">Submit Issue</button>
        </form>
      </div>
    </div>
  );
}
