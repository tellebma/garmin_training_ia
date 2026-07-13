import { describe, expect, it } from 'vitest'
import { parseChangelog } from '@/lib/changelog/parse'

describe('parseChangelog', () => {
  it('returns an empty array for empty markdown', () => {
    expect(parseChangelog('')).toEqual([])
  })

  it('parses a single section with bullets', () => {
    const md = `# Nouveautés\n\n## 1.9.0 — 2026-07-11\n\n- Première puce.\n- Deuxième puce.\n`
    expect(parseChangelog(md)).toEqual([
      { version: '1.9.0', date: '2026-07-11', bullets: ['Première puce.', 'Deuxième puce.'] },
    ])
  })

  it('parses multiple sections and preserves file order', () => {
    const md = `# Nouveautés\n\n## 1.9.0 — 2026-07-11\n\n- A.\n\n## 1.8.0 — 2026-07-10\n\n- B.\n`
    expect(parseChangelog(md).map((e) => e.version)).toEqual(['1.9.0', '1.8.0'])
  })

  it('returns an empty bullets array for a section with no bullets', () => {
    const md = `## 1.7.0 — 2026-07-09\n`
    expect(parseChangelog(md)).toEqual([{ version: '1.7.0', date: '2026-07-09', bullets: [] }])
  })

  it('ignores a malformed section title without the " — " separator', () => {
    const md = `## broken title\n\n- ignored bullet\n\n## 1.6.0 — 2026-07-09\n\n- kept.\n`
    expect(parseChangelog(md)).toEqual([
      { version: '1.6.0', date: '2026-07-09', bullets: ['kept.'] },
    ])
  })

  it('parses long bullets on a single physical line without truncation', () => {
    const longBullet =
      'Connecte ton compte Strava : tes activités arrivent maintenant en temps réel, dès que tu termines une sortie.'
    const md = `## 1.9.0 — 2026-07-11\n\n- ${longBullet}\n`
    expect(parseChangelog(md)).toEqual([
      { version: '1.9.0', date: '2026-07-11', bullets: [longBullet] },
    ])
  })
})
