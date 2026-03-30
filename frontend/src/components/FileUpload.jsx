import { useRef, useState } from "react";

export default function FileUpload({ onFileSelected, disabled = false }) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  function handleFile(file) {
    if (!file) return;
    onFileSelected(file);
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          if (disabled) return;
          handleFile(event.dataTransfer.files?.[0]);
        }}
        className={[
          "w-full rounded-xl border-2 border-dashed px-6 py-10 text-left transition",
          dragOver
            ? "border-sky-400 bg-sky-50/70"
            : "border-slate-300/90 bg-white/70 hover:border-slate-400 hover:bg-slate-50/70",
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
        ].join(" ")}
      >
        <p className="font-display text-lg font-semibold text-slate-900">Drag & drop Excel file</p>
        <p className="mt-2 text-sm text-slate-600">
          Upload `.xlsx` with columns: Name, Email, Department, Year, Section, Attendance, CGPA, Backlogs
        </p>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xlsm,.xltx,.xltm"
        className="hidden"
        onChange={(event) => handleFile(event.target.files?.[0])}
      />
    </div>
  );
}
