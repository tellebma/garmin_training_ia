import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Garmin Training Coach',
  description: 'Plan triathlon personnalisé basé sur tes données Garmin',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'Garmin Coach',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: '/icons/icon-192.png',
    apple: '/icons/icon-192.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#0a0a0a',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="fr" className="dark">
      <body className="bg-background text-foreground min-h-screen antialiased">{children}</body>
    </html>
  )
}
