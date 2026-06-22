export function LoadingRegion({
  label,
  children,
}: {
  readonly label: string
  readonly children: React.ReactNode
}) {
  return (
    <div role="status" aria-label={label} aria-busy>
      {children}
    </div>
  )
}
