import { z } from 'zod'
import { COMMON_PASSWORDS } from './common-passwords'

export const emailSchema = z.email('Email invalide').transform((s) => s.toLowerCase().trim())

/**
 * Password used at registration / reset (min 10 chars + not in top-100 blocklist).
 * Login uses a looser variant (just non-empty + max 72).
 */
export const passwordSchema = z
  .string()
  .min(10, 'Au moins 10 caractères')
  .max(72, 'Maximum 72 caractères')
  .refine((p) => !COMMON_PASSWORDS.has(p.toLowerCase()), {
    message: 'Mot de passe trop courant — choisis-en un autre',
  })

export const registerSchema = z.object({
  email: emailSchema,
})

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, 'Requis').max(72),
})

export const forgotPasswordSchema = z.object({
  email: emailSchema,
})

export const setPasswordSchema = z
  .object({
    password: passwordSchema,
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, {
    path: ['confirm'],
    message: 'Les mots de passe ne correspondent pas',
  })

export type RegisterInput = z.infer<typeof registerSchema>
export type LoginInput = z.infer<typeof loginSchema>
export type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>
export type SetPasswordInput = z.infer<typeof setPasswordSchema>
