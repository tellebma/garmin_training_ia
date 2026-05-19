// app/(app)/history/loading.tsx
export default function HistoryLoading() {
  return (
    <div className="space-y-6">
      <div className="bg-muted/50 h-8 w-32 animate-pulse rounded" />
      <div className="flex gap-2">
        <div className="bg-muted/50 h-9 w-32 animate-pulse rounded" />
        <div className="bg-muted/50 h-9 w-32 animate-pulse rounded" />
      </div>
      {Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="bg-muted/50 h-14 animate-pulse rounded" />
      ))}
    </div>
  )
}
