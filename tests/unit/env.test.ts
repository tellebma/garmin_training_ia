import { describe, it, expect } from 'vitest'

describe('env', () => {
  it('throws when NEXT_PUBLIC_SUPABASE_URL is missing', async () => {
    const original = process.env.NEXT_PUBLIC_SUPABASE_URL
    delete process.env.NEXT_PUBLIC_SUPABASE_URL
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
    // Query string forces Vitest to bypass the module cache so the top-level
    // validation in lib/env.ts re-runs with the mutated process.env. Passing
    // through a variable keeps TS happy (it cannot resolve the suffix path).
    const modulePath = '@/lib/env?missing-url'
    await expect(import(/* @vite-ignore */ modulePath)).rejects.toThrow(/NEXT_PUBLIC_SUPABASE_URL/)
    process.env.NEXT_PUBLIC_SUPABASE_URL = original
  })

  it('parses valid env vars', async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
    const { env } = await import('@/lib/env')
    expect(env.NEXT_PUBLIC_SUPABASE_URL).toBe('https://example.supabase.co')
  })
})
