import { useState } from "react";
import { usePeriodsList, usePayrollPeriod } from "./hooks/usePayroll";
import { PoolCards } from "./components/PoolCards";
import { EmployeeTable } from "./components/EmployeeTable";
import { TipRecordsTable } from "./components/TipRecordsTable";

type Tab = "summary" | "tips";

export default function App() {
  const [selectedPeriod, setSelectedPeriod] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("summary");

  const { data: periodsData, loading: periodsLoading, error: periodsError } = usePeriodsList();
  const { data: payroll, loading: payrollLoading, error: payrollError } = usePayrollPeriod(selectedPeriod);

  const headerStyle: React.CSSProperties = {
    background: "#1d3557",
    color: "#fff",
    padding: "16px 28px",
    display: "flex",
    alignItems: "center",
    gap: 16,
    flexWrap: "wrap",
  };

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: "8px 18px",
    border: "none",
    borderBottom: active ? "3px solid #e63946" : "3px solid transparent",
    background: "none",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: active ? 700 : 400,
    color: active ? "#1d3557" : "#666",
  });

  return (
    <div style={{ minHeight: "100vh", background: "#f4f6f9" }}>
      {/* Header */}
      <div style={headerStyle}>
        <div>
          <div style={{ fontSize: 11, opacity: 0.7, letterSpacing: 1 }}>RAW SUSHI BISTRO</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>Payroll Dashboard</div>
        </div>

        {/* Period selector */}
        <div style={{ marginLeft: "auto" }}>
          {periodsLoading && <span style={{ opacity: 0.7, fontSize: 13 }}>Loading periods…</span>}
          {periodsError && (
            <span style={{ color: "#ff6b6b", fontSize: 13 }}>Error: {periodsError}</span>
          )}
          {periodsData && (
            <select
              value={selectedPeriod ?? ""}
              onChange={(e) => setSelectedPeriod(e.target.value || null)}
              style={{
                padding: "8px 14px",
                borderRadius: 6,
                border: "none",
                fontSize: 14,
                minWidth: 180,
              }}
            >
              <option value="">— Select period —</option>
              {periodsData.periods.map((p) => (
                <option key={p.tab_name} value={p.tab_name}>
                  {p.period_start} → {p.period_end}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Main content */}
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px" }}>
        {!selectedPeriod && (
          <div
            style={{
              textAlign: "center",
              padding: 64,
              color: "#888",
              background: "#fff",
              borderRadius: 12,
              boxShadow: "0 1px 4px rgba(0,0,0,.08)",
            }}
          >
            <div style={{ fontSize: 36, marginBottom: 12 }}>📋</div>
            <div style={{ fontSize: 16 }}>Select a payroll period above to view data.</div>
          </div>
        )}

        {payrollLoading && (
          <div style={{ textAlign: "center", padding: 48, color: "#888" }}>
            Loading payroll data…
          </div>
        )}

        {payrollError && (
          <div
            style={{
              background: "#fff5f5",
              border: "1px solid #fc8181",
              borderRadius: 8,
              padding: 16,
              color: "#c53030",
            }}
          >
            Failed to load period: {payrollError}
          </div>
        )}

        {payroll && (
          <>
            {/* Period heading */}
            <div style={{ marginBottom: 20 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700 }}>
                Period: {payroll.period_start} → {payroll.period_end}
              </h2>
            </div>

            {/* Pool metric cards */}
            <PoolCards pool={payroll.pool} />

            {/* Tab nav */}
            <div
              style={{
                display: "flex",
                borderBottom: "1px solid #e5e7eb",
                marginBottom: 18,
                background: "#fff",
                borderRadius: "10px 10px 0 0",
                padding: "0 8px",
              }}
            >
              <button style={tabStyle(activeTab === "summary")} onClick={() => setActiveTab("summary")}>
                Employee Summary
              </button>
              <button style={tabStyle(activeTab === "tips")} onClick={() => setActiveTab("tips")}>
                Tip Records ({payroll.tip_records.length})
              </button>
            </div>

            {activeTab === "summary" && <EmployeeTable rows={payroll.employees} />}
            {activeTab === "tips" && <TipRecordsTable records={payroll.tip_records} />}
          </>
        )}
      </div>
    </div>
  );
}
