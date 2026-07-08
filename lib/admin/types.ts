export interface CostPerDayPoint {
  date: string
  cost_usd: number
}

export interface AdminOverview {
  users: { total: number; active_7d: number }
  activities: { total: number; last_7d: number }
  llm_estimated: { total_tokens_7d: number; cost_usd_7d: number }
  llm_billed: { cost_usd_7d: number }
  sync_health: { ok: number; failed: number }
  cost_per_day_7d: CostPerDayPoint[]
}
