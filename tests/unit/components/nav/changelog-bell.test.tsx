// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi, beforeEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChangelogBell } from '@/components/nav/changelog-bell'

const markChangelogSeen = vi.fn()

vi.mock('@/app/actions/changelog', () => ({
  markChangelogSeen: (...args: unknown[]) => markChangelogSeen(...args) as unknown,
}))

const entries = [
  { version: '1.9.0', date: '2026-07-11', bullets: ['Strava en temps réel.'] },
  { version: '1.8.0', date: '2026-07-10', bullets: ['Survol carte/graphiques corrélé.'] },
]

afterEach(cleanup)

// jsdom n'implémente pas l'API Pointer Events utilisée par Radix Dialog (base du
// composant Sheet) pour la gestion du focus/dismiss — sans ce polyfill, un clic
// simulé via `userEvent` sur le trigger lève `hasPointerCapture is not a function`.
// Premier composant Radix testé dans ce projet (`alert-dialog` n'a encore aucun test) :
// pas de précédent existant à suivre, ce polyfill est le correctif standard documenté
// par la communauté Radix pour jsdom.
beforeAll(() => {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- jsdom's Element type declares these as always-defined, but they are absent at runtime; the guard is required for the polyfill to be a no-op when a future jsdom version implements them natively.
  Element.prototype.hasPointerCapture ??= () => false
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- see above
  Element.prototype.setPointerCapture ??= () => undefined
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- see above
  Element.prototype.releasePointerCapture ??= () => undefined
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- see above
  Element.prototype.scrollIntoView ??= () => undefined
})

describe('ChangelogBell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    markChangelogSeen.mockResolvedValue({ success: true })
  })

  it('shows an unread badge when the latest version has not been seen', () => {
    render(<ChangelogBell entries={entries} latestVersion="1.9.0" initialLastSeenVersion="1.8.0" />)
    expect(screen.getByTestId('changelog-unread-dot')).toBeTruthy()
  })

  it('does not show a badge when the latest version has already been seen', () => {
    render(<ChangelogBell entries={entries} latestVersion="1.9.0" initialLastSeenVersion="1.9.0" />)
    expect(screen.queryByTestId('changelog-unread-dot')).toBeNull()
  })

  it('does not show a badge when there is no changelog entry', () => {
    render(<ChangelogBell entries={[]} latestVersion={null} initialLastSeenVersion={null} />)
    expect(screen.queryByTestId('changelog-unread-dot')).toBeNull()
  })

  it('opens the panel, lists entries, marks as seen and clears the badge', async () => {
    const user = userEvent.setup()
    render(<ChangelogBell entries={entries} latestVersion="1.9.0" initialLastSeenVersion="1.8.0" />)

    await user.click(screen.getByRole('button', { name: /nouveautés/i }))

    expect(await screen.findByText('Strava en temps réel.')).toBeTruthy()
    expect(screen.getByText('Survol carte/graphiques corrélé.')).toBeTruthy()
    expect(markChangelogSeen).toHaveBeenCalledWith('1.9.0')
    expect(screen.queryByTestId('changelog-unread-dot')).toBeNull()
  })
})
