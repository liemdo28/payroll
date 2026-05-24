import type { EmployeeSummary } from "../types";

const fmt = (n: number) =>
  n ? n.toLocaleString("en-US", { style: "currency", currency: "USD" }) : "—";

const fmtH = (n: number) => (n ? n.toFixed(2) : "—");

const th: React.CSSProperties = {
  padding: "9px 12px",
  textAlign: "right",
  fontSize: 12,
  fontWeight: 600,
  color: "#555",
  whiteSpace: "nowrap",
  borderBottom: "2px solid #e5e7eb",
};

const thL: React.CSSProperties = { ...th, textAlign: "left" };

const td: React.CSSProperties = {
  padding: "8px 12px",
  textAlign: "right",
  fontSize: 13,
  borderBottom: "1px solid #f0f0f0",
};

const tdL: React.CSSProperties = { ...td, textAlign: "left", fontWeight: 500 };

export function EmployeeTable({ rows }: { rows: EmployeeSummary[] }) {
  const totals = rows.reduce(
    (acc, r) => ({
      total_hours: acc.total_hours + r.total_hours,
      ot_hours: acc.ot_hours + r.ot_hours,
      tip: acc.tip + r.tip,
      busser_cashier: acc.busser_cashier + r.busser_cashier,
      sushi_tip: acc.sushi_tip + r.sushi_tip,
      kitchen_tip: acc.kitchen_tip + r.kitchen_tip,
      bartender_tip: acc.bartender_tip + r.bartender_tip,
      grand_total: acc.grand_total + r.grand_total,
    }),
    {
      total_hours: 0, ot_hours: 0, tip: 0,
      busser_cashier: 0, sushi_tip: 0, kitchen_tip: 0,
      bartender_tip: 0, grand_total: 0,
    }
  );

  return (
    <div style={{ overflowX: "auto", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,.08)" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
        <thead>
          <tr>
            <th style={thL}>Employee</th>
            <th style={th}>Hours</th>
            <th style={th}>OT</th>
            <th style={th}>Server Tip</th>
            <th style={th}>Busser/Cashier</th>
            <th style={th}>Sushi</th>
            <th style={th}>Kitchen</th>
            <th style={th}>Bartender</th>
            <th style={{ ...th, color: "#1a1a2e" }}>Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.search_name} style={{ background: r.grand_total ? "#fff" : "#fafafa" }}>
              <td style={tdL}>
                {r.display_name}
                {r.other_name ? (
                  <span style={{ color: "#888", fontSize: 11, marginLeft: 6 }}>
                    ({r.other_name})
                  </span>
                ) : null}
              </td>
              <td style={td}>{fmtH(r.total_hours)}</td>
              <td style={{ ...td, color: r.ot_hours ? "#e63946" : undefined }}>
                {fmtH(r.ot_hours)}
              </td>
              <td style={td}>{fmt(r.tip)}</td>
              <td style={td}>{fmt(r.busser_cashier)}</td>
              <td style={td}>{fmt(r.sushi_tip)}</td>
              <td style={td}>{fmt(r.kitchen_tip)}</td>
              <td style={td}>{fmt(r.bartender_tip)}</td>
              <td style={{ ...td, fontWeight: 700, color: "#1a1a2e" }}>
                {fmt(r.grand_total)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ background: "#f8f9fa" }}>
            <td style={{ ...tdL, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>TOTAL</td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>
              {totals.total_hours.toFixed(2)}
            </td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>
              {totals.ot_hours.toFixed(2)}
            </td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>
              {fmt(totals.tip)}
            </td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>
              {fmt(totals.busser_cashier)}
            </td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>
              {fmt(totals.sushi_tip)}
            </td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>
              {fmt(totals.kitchen_tip)}
            </td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb" }}>
              {fmt(totals.bartender_tip)}
            </td>
            <td style={{ ...td, fontWeight: 700, borderTop: "2px solid #e5e7eb", color: "#1a1a2e" }}>
              {fmt(totals.grand_total)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
