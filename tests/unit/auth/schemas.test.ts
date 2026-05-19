import { describe, expect, it } from 'vitest'
import {
  emailSchema,
  passwordSchema,
  registerSchema,
  loginSchema,
  forgotPasswordSchema,
  setPasswordSchema,
} from '@/lib/auth/schemas'

describe('emailSchema', () => {
  it('accepts valid email and lowercases it', () => {
    const r = emailSchema.safeParse('FOO@Bar.com')
    expect(r.success).toBe(true)
    if (r.success) expect(r.data).toBe('foo@bar.com')
  })

  it('rejects invalid email', () => {
    expect(emailSchema.safeParse('not-an-email').success).toBe(false)
  })

  it('trims whitespace', () => {
    const r = emailSchema.safeParse('  a@b.com  ')
    if (r.success) expect(r.data).toBe('a@b.com')
  })
})

describe('passwordSchema', () => {
  it('accepts 10+ chars non-common', () => {
    expect(passwordSchema.safeParse('M1ghty-Tr1@thlete').success).toBe(true)
  })

  it('rejects < 10 chars', () => {
    expect(passwordSchema.safeParse('Short1!').success).toBe(false)
  })

  it('rejects > 72 chars', () => {
    expect(passwordSchema.safeParse('a'.repeat(73)).success).toBe(false)
  })

  it('rejects common password "password123"', () => {
    expect(passwordSchema.safeParse('password123').success).toBe(false)
  })

  it('rejects common password "qwerty123" case-insensitive', () => {
    expect(passwordSchema.safeParse('QWERTY123').success).toBe(false)
  })
})

describe('registerSchema', () => {
  it('accepts a valid email', () => {
    expect(registerSchema.safeParse({ email: 'a@b.com' }).success).toBe(true)
  })

  it('rejects missing email', () => {
    expect(registerSchema.safeParse({}).success).toBe(false)
  })
})

describe('loginSchema', () => {
  it("accepts any non-empty password (login doesn't check complexity)", () => {
    expect(loginSchema.safeParse({ email: 'a@b.com', password: 'short' }).success).toBe(true)
  })

  it('rejects empty password', () => {
    expect(loginSchema.safeParse({ email: 'a@b.com', password: '' }).success).toBe(false)
  })
})

describe('forgotPasswordSchema', () => {
  it('accepts a valid email', () => {
    expect(forgotPasswordSchema.safeParse({ email: 'a@b.com' }).success).toBe(true)
  })
})

describe('setPasswordSchema', () => {
  const valid = { password: 'M1ghty-Tr1@thlete', confirm: 'M1ghty-Tr1@thlete' }

  it('accepts matching strong passwords', () => {
    expect(setPasswordSchema.safeParse(valid).success).toBe(true)
  })

  it('rejects mismatching passwords', () => {
    expect(setPasswordSchema.safeParse({ ...valid, confirm: 'Different-One99' }).success).toBe(
      false
    )
  })

  it('rejects when password fails passwordSchema (< 10)', () => {
    expect(setPasswordSchema.safeParse({ password: 'Short1!', confirm: 'Short1!' }).success).toBe(
      false
    )
  })
})
