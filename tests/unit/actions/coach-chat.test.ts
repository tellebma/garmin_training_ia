import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

vi.mock('@/lib/env', () => ({
  getServerEnv: () => ({ WORKER_URL: 'http://localhost:8080' }),
}))

const getSession = vi.fn()
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({ auth: { getSession } }),
}))

import { askCoach } from '@/app/actions/coach-chat'

function mockWorker(payload: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({ status, json: async () => payload })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('askCoach', () => {
  beforeEach(() => {
    getSession.mockReset()
    getSession.mockResolvedValue({ data: { session: { access_token: 'jwt-123' } } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('relays the question and returns the answer', async () => {
    const fetchMock = mockWorker({
      status: 'ok',
      conversation_id: 'c1',
      answer: 'Tu es en forme.',
      tools_used: ['get_form_state'],
      rounds: 2,
      remaining_usd: 1.4,
    })

    const result = await askCoach('Suis-je prêt ?')

    expect(result).toEqual({
      success: true,
      conversationId: 'c1',
      answer: 'Tu es en forme.',
      toolsUsed: ['get_form_state'],
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8080/coach/chat',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-123' }),
      })
    )
  })

  it('forwards the conversation id when continuing a thread', async () => {
    const fetchMock = mockWorker({
      status: 'ok',
      conversation_id: 'c1',
      answer: 'ok',
      tools_used: [],
      rounds: 1,
      remaining_usd: 1,
    })

    await askCoach('et ensuite ?', 'c1')

    // workerPost sérialise toujours le corps en JSON avant l'appel.
    const init = fetchMock.mock.calls[0]?.[1] as { body?: string } | undefined
    const body = JSON.parse(init?.body ?? '{}') as Record<string, unknown>
    expect(body.conversation_id).toBe('c1')
  })

  it('rejects an empty question without calling the worker', async () => {
    const fetchMock = mockWorker({})

    const result = await askCoach('   ')

    expect(result).toEqual({ success: false, error: 'Pose une question.' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('requires a session', async () => {
    getSession.mockResolvedValue({ data: { session: null } })

    const result = await askCoach('question')

    expect(result).toEqual({ success: false, error: 'Session expirée, reconnecte-toi.' })
  })

  it('explains a spent quota instead of showing an error', async () => {
    mockWorker({ status: 'budget_exceeded', reason: 'quota', remaining_usd: 0 })

    const result = await askCoach('question')

    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toContain('quota')
  })

  it('explains rate limiting in plain language', async () => {
    mockWorker({ status: 'rate_limited', retry_after_seconds: 300 })

    const result = await askCoach('question')

    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toContain('minutes')
  })

  it('reports a disabled chat without leaking the reason', async () => {
    mockWorker({ status: 'chat_disabled', reason: 'budget global mensuel atteint ($20.13)' })

    const result = await askCoach('question')

    expect(result.success).toBe(false)
    // Le montant dépensé par l'application ne regarde pas l'utilisateur.
    if (!result.success) expect(result.error).not.toContain('20.13')
  })

  it('handles an unknown conversation', async () => {
    mockWorker({ status: 'conversation_not_found' })

    const result = await askCoach('question', 'c9')

    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toContain('introuvable')
  })

  it('survives a worker timeout', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('The operation was aborted due to timeout'))
    )

    const result = await askCoach('question')

    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toContain('Réessaie')
  })
})
