const RISK_OPTIONS = ["LOW", "MEDIUM", "HIGH"];

export default function FilterPanel({ filters, onChange, onReset, disabled = false }) {
  return (
    <div className="glass-panel rounded-2xl p-5 text-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-semibold">Student filters</h2>
          <p className="mt-1 text-sm text-slate-500">Search by identity, segment by academics, then drill into profiles.</p>
        </div>
        <button type="button" onClick={onReset} disabled={disabled} className="pill-button">
          Clear filters
        </button>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <input
          className="field-input"
          placeholder="Search name or email"
          value={filters.search || ""}
          onChange={(e) => onChange("search", e.target.value)}
          disabled={disabled}
        />
        <input
          className="field-input"
          placeholder="Department"
          value={filters.department || ""}
          onChange={(e) => onChange("department", e.target.value)}
          disabled={disabled}
        />
        <input
          className="field-input"
          type="number"
          min="1"
          max="8"
          placeholder="Year"
          value={filters.year || ""}
          onChange={(e) => onChange("year", e.target.value)}
          disabled={disabled}
        />
        <input
          className="field-input"
          placeholder="Section"
          value={filters.section || ""}
          onChange={(e) => onChange("section", e.target.value)}
          disabled={disabled}
        />
        <input
          className="field-input"
          type="number"
          min="0"
          max="10"
          step="0.01"
          placeholder="CGPA min"
          value={filters.cgpa_min || ""}
          onChange={(e) => onChange("cgpa_min", e.target.value)}
          disabled={disabled}
        />
        <input
          className="field-input"
          type="number"
          min="0"
          max="10"
          step="0.01"
          placeholder="CGPA max"
          value={filters.cgpa_max || ""}
          onChange={(e) => onChange("cgpa_max", e.target.value)}
          disabled={disabled}
        />
        <select
          className="field-input"
          value={filters.risk_level || ""}
          onChange={(e) => onChange("risk_level", e.target.value)}
          disabled={disabled}
        >
          <option value="">Risk level</option>
          {RISK_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
