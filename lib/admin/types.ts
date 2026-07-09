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

export interface FeatureFlagRow {
  key: string
  enabled: boolean
  expires_at: string | null
  description: string
  updated_at: string
}

// La colonne `enabled` ne tient pas compte de l'expiration (la row reste enabled=true
// après que expires_at soit passé) — seule cette fonction (miroir de
// is_feature_flag_active() côté DB) résout l'état réel. Ne jamais lire flag.enabled
// directement pour savoir si un flag est actif.
export function isFlagActive(flag: FeatureFlagRow): boolean {
  if (!flag.enabled) return false
  if (!flag.expires_at) return true
  return new Date(flag.expires_at) > new Date()
}
