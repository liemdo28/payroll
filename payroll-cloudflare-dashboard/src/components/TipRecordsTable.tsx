import { useState } from "react";
import type { TipRecord } from "../types";

const fmt = (n: number) =>
  n ? n.toLocaleString("en-US", { style: "currency", currency: "USD" }) : "—";

const th: React.CSSProperties = {
  padding: "8px 10px",
  textAlign: "right",
  fontSize: 12,
  fontWeight: 600,
  color: "#555",
  borderBottom: "2px solid #e5e7eb",
  whiteSpace: "nowrap",
};
const thL: React.CSSProperties = { ...th, textAlign: "left" };
const td: React.CSSProperties = { padding: "7px 10px", textAlign: "right", fontSize: 12, borderBottom: "1px solid #f0f0f0" };
const tdL: React.CSSProperties = { ...td, textAlign: "left" };

const JOB_COLOR: Record<string, string> = {
  Server: "#457b9d",
  Bartender: "#6d4c41",
  FOH: "#2a9d8f",
  Cashier: "#e9c46a",
};

export function TipRecordsTable({ records }: { records: TipRecord[] }) {
  const [shiftFilter, setShiftFilter] = useState<"All" | "Lunch" | "Dinner">("All");
  const [jobFilter, setJobFilter] = useState("All");

  const jobs = ["All", ...Array.from(new Set(records.map((r) => r.job)))];

  const visible = records.filter(
    (r) =>
      (shiftFilter === "All" || r.shift === shiftFilter) &&
      (jobFilter === "All" || r.job === jobFilter)
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        {(["All", "Lunch", "Dinner"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setShiftFilter(s)}
            style={{
              padding: "5px 14px",
              borderRadius: 20,
              border: "none",
              cursor: "pointer",
              background: shiftFilter === s ? "#1d3557" : "#e5e7eb",
              color: shiftFilter === s ? "#fff" : "#333",
              fontSize: 13,
            }}
          >
            {s}
          </button>
        ))}
        <select
          value={jobFilter}
          onChange={(e) => setJobFilter(e.target.value)}
          style={{ padding: "5px 10px", borderRadius: 20, border: "1px solid #ccc", fontSize: 13 }}
        >
          {jobs.map((j) => (
            <option key={j}>{j}</option>
          ))}
        </select>
      </div>

      <div style={{ overflowX: "auto", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,.08)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
          <thead>
            <tr>
              <th style={thL}>Date</th>
              <th style={thL}>Shift</th>
              <th style={thL}>Job</th>
              <th style={thL}>Name</th>
              <th style={th}>Subtotal</th>
              <th style={th}>Card Tip</th>
              <th style={th}>Gratuity</th>
              <th style={th}>VAL</th>
              <th style={th}>Net Tip</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r, i) => (
              <tr key={i} style={{ background: r.job === "FOH" ? "#f0f9f7" : "#fff" }}>
                <td style={tdL}>{r.date}</td>
                <td style={tdL}>{r.shift}</td>
                <td style={tdL}>
                  <span
                    style={{
                      background: JOB_COLOR[r.job] ?? "#ccc",
                      color: "#fff",
                      borderRadius: 4,
                      padding: "2px 6px",
                      fontSize: 11,
                    }}
                  >
                    {r.job}
                  </span>
                </td>
                <td style={tdL}>{r.name}</td>
                <td style={td}>{fmt(r.subtotal)}</td>
                <td style={td}>{fmt(r.card_tip)}</td>
                <td style={td}>{fmt(r.gratuity)}</td>
                <td style={{ ...td, color: r.val ? "#e63946" : undefined }}>{fmt(r.val)}</td>
                <td style={{ ...td, fontWeight: 600 }}>{fmt(r.tip)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && (
          <div style={{ textAlign: "center", padding: 24, color: "#888" }}>No records match the filter.</div>
        )}
      </div>
    </div>
  );
}
