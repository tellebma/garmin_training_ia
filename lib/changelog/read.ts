import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { parseChangelog } from './parse'
import type { ChangelogEntry } from './parse'

const CHANGELOG_PATH = path.join(process.cwd(), 'docs', 'nouveautes.md')

export async function loadChangelog(): Promise<ChangelogEntry[]> {
  const markdown = await readFile(CHANGELOG_PATH, 'utf-8').catch(() => '')
  return parseChangelog(markdown)
}
