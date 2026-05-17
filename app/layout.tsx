import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Garmin Training Coach',
  description: 'Plan triathlon personnalisé basé sur tes données Garmin',
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
