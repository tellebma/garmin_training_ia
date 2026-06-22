export function LoadingRegion({
  label,
  children,
}: {
  readonly label: string
  readonly children: React.ReactNode
}) {
  return (
    <output aria-label={label} aria-busy className="block">
      {children}
    </output>
  )
}
