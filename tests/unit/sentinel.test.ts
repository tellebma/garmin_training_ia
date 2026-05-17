// Sentinel test to keep Vitest happy until real tests are added in E1.T2.
// This file should be replaced/removed when real unit tests land.
import { describe, it, expect } from 'vitest'

describe('sentinel', () => {
  it('is alive', () => {
    expect(1 + 1).toBe(2)
  })
})
