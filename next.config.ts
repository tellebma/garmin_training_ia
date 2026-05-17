import withPWAInit from '@ducanh2912/next-pwa'
import type { NextConfig } from 'next'

const withPWA = withPWAInit({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  workboxOptions: {
    skipWaiting: true,
  },
})

// Webpack's `node` option (build-time mocking for Node globals). We avoid
// pulling in `webpack`'s types just for this, and the official Next.js
// `webpack` callback is typed as `(config: any, ctx) => any` upstream.
interface WebpackNodeOption {
  __dirname?: boolean | 'eval-only' | 'mock' | 'node-module' | 'warn-mock'
  __filename?: boolean | 'eval-only' | 'mock' | 'node-module' | 'warn-mock'
  global?: boolean | 'warn'
}
interface WebpackConfigShape {
  node?: WebpackNodeOption | false
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Run middleware on the Node.js runtime (Next.js 15 experimental opt-in).
  // The Edge runtime is a V8 isolate that doesn't expose `__dirname`, so any
  // package that bundles it (transitively through `@supabase/ssr` /
  // `@supabase/supabase-js`) crashes at request time with
  // `ReferenceError: __dirname is not defined`. Switching the middleware to
  // Node lets us mock those Node globals at build time and avoids the crash.
  //
  // The `nodeMiddleware` flag is read at runtime by Next.js 15.5+ but the
  // public TS types still mark middleware as Edge-only, so we cast through
  // `Record<string, unknown>` to escape the type check.
  experimental: {
    nodeMiddleware: true,
  } as NextConfig['experimental'] & { nodeMiddleware: boolean },
  // Fix "ReferenceError: __dirname is not defined" on Vercel.
  // Pre-compiled deps shipped inside Next.js (e.g. ua-parser-js) reference
  // __dirname / __filename. On Vercel's serverless runtime those globals are
  // not always provided depending on how the function is wrapped, which causes
  // a runtime 500 at request time. Telling webpack to mock them at build time
  // (instead of leaving them as free runtime identifiers) avoids the error
  // everywhere — Node Lambda, Edge runtime, and local prod alike.
  webpack: (config, { isServer }) => {
    if (isServer) {
      const c = config as WebpackConfigShape
      c.node = { ...c.node, __dirname: true, __filename: true }
    }
    return config as unknown
  },
}

export default withPWA(nextConfig)
