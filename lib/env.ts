import { z } from 'zod'

// Public env vars (exposed to the browser bundle)
const publicSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
})

// Server-only env vars (NEVER exposed to the browser)
const serverSchema = z.object({
  WORKER_URL: z.url().default('http://localhost:8080'),
})

const publicParsed = publicSchema.safeParse({
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
})

if (!publicParsed.success) {
  const issues = publicParsed.error.issues
    .map((i) => `- ${i.path.join('.')}: ${i.message}`)
    .join('\n')
  throw new Error(`Invalid public environment variables:\n${issues}`)
}

export const env = publicParsed.data

// Lazy server-only access — only call from Server Components / Route Handlers / Server Actions.
export function getServerEnv() {
  const parsed = serverSchema.safeParse({
    WORKER_URL: process.env.WORKER_URL,
  })
  if (!parsed.success) {
    throw new Error('Invalid server env: ' + JSON.stringify(parsed.error.issues))
  }
  return parsed.data
}
