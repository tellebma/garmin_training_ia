export function MaintenancePage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6 text-center">
      <div className="max-w-sm space-y-2">
        <h1 className="text-xl font-semibold">Maintenance en cours</h1>
        <p className="text-muted-foreground text-sm">
          L&rsquo;application est momentanément indisponible. Réessaie dans quelques minutes.
        </p>
      </div>
    </div>
  )
}
