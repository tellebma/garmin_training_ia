export interface ChangelogEntry {
  version: string
  date: string
  bullets: string[]
}

export function parseChangelog(markdown: string): ChangelogEntry[] {
  const sections = markdown.split(/^## /m).slice(1)
  const entries: ChangelogEntry[] = []

  for (const section of sections) {
    const lines = section.split('\n')
    const title = lines[0]?.trim() ?? ''
    const separatorIndex = title.indexOf(' — ')
    if (separatorIndex === -1) continue

    const version = title.slice(0, separatorIndex).trim()
    const date = title.slice(separatorIndex + 3).trim()
    const bullets = lines
      .slice(1)
      .filter((line) => line.trim().startsWith('- '))
      .map((line) => line.trim().slice(2).trim())

    entries.push({ version, date, bullets })
  }

  return entries
}
