import { cache } from 'react'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { parseChangelog } from './parse'
import type { ChangelogEntry } from './parse'

const CHANGELOG_PATH = path.join(process.cwd(), 'docs', 'nouveautes.md')

// cache() dedupes the disk read within a single request (runs on every layout render).
export const loadChangelog = cache(async (): Promise<ChangelogEntry[]> => {
  const markdown = await readFile(CHANGELOG_PATH, 'utf-8').catch(() => '')
  return parseChangelog(markdown)
})
