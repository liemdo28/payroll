export interface EmployeeSummary {
  search_name: string;
  other_name: string;
  display_name: string;
  total_hours: number;
  ot_hours: number;
  regular_hours: number;
  tip: number;
  busser_cashier: number;
  sushi_tip: number;
  kitchen_tip: number;
  bartender_tip: number;
  grand_total: number;
}

export interface TipRecord {
  date: string;
  shift: "Lunch" | "Dinner";
  job: string;
  name: string;
  total: number;
  subtotal: number;
  card_tip: number;
  gratuity: number;
  sum_tip_gratuity: number;
  val: number;
  tip: number;
}

export interface PoolSummary {
  foh_card_tips: number;
  foh_val: number;
  t30: number;
  total_val_pool: number;
  kitchen_pool: number;
}

export interface PayrollPeriod {
  period_start: string;
  period_end: string;
  tab_name: string;
  employees: EmployeeSummary[];
  tip_records: TipRecord[];
  pool: PoolSummary;
}

export interface PeriodsIndex {
  periods: { tab_name: string; period_start: string; period_end: string }[];
}
