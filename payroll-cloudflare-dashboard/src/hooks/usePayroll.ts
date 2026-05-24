import { useState, useEffect } from "react";
import type { PayrollPeriod, PeriodsIndex } from "../types";

export function usePeriodsList() {
  const [data, setData] = useState<PeriodsIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/payroll/periods")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<PeriodsIndex>;
      })
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e))
      )
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}

export function usePayrollPeriod(tabName: string | null) {
  const [data, setData] = useState<PayrollPeriod | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tabName) return;
    setLoading(true);
    setError(null);
    setData(null);

    fetch(`/api/payroll/${tabName}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<PayrollPeriod>;
      })
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e))
      )
      .finally(() => setLoading(false));
  }, [tabName]);

  return { data, loading, error };
}
