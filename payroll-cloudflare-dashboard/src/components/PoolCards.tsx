import type { PoolSummary } from "../types";

const fmt = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD" });

interface CardProps {
  label: string;
  value: number;
  sub?: string;
  accent?: string;
}

function Card({ label, value, sub, accent = "#e63946" }: CardProps) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 10,
        padding: "18px 22px",
        borderTop: `4px solid ${accent}`,
        boxShadow: "0 1px 4px rgba(0,0,0,.08)",
        minWidth: 160,
        flex: "1 1 160px",
      }}
    >
      <div style={{ fontSize: 13, color: "#666", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{fmt(value)}</div>
      {sub && <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export function PoolCards({ pool }: { pool: PoolSummary }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginBottom: 28 }}>
      <Card label="FOH Card Tips" value={pool.foh_card_tips} sub="Takeout / pickup" accent="#457b9d" />
      <Card label="FOH VAL (1/3)" value={pool.foh_val} sub="→ tip pool" accent="#1d3557" />
      <Card label="T30 – Kitchen pool" value={pool.t30} sub="FOH×2/3 − cashier paid" accent="#e63946" />
      <Card label="Total VAL pool" value={pool.total_val_pool} sub="Server 6% + FOH 1/3" accent="#2a9d8f" />
    </div>
  );
}
