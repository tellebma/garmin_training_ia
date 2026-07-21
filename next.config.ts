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
  // Bundle `docs/nouveautes.md` into the serverless function trace.
  // `lib/changelog/read.ts` reads it at runtime via `fs.readFile(process.cwd()/docs/…)`,
  // but the file lives outside the app graph so @vercel/nft doesn't trace it. Without
  // this, the file is missing from the Vercel Lambda, the read fails (caught → ''), and
  // the "Nouveautés" bell shows no entries in production. The `'/*'` key applies to all
  // routes (the (app) layout that loads the changelog wraps every page).
  outputFileTracingIncludes: {
    '/*': ['./docs/nouveautes.md'],
  },
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
