// app/(app)/stats/loading.tsx
export default function StatsLoading() {
  return (
    <div className="space-y-6">
      <div className="bg-muted/50 h-8 w-32 animate-pulse rounded" />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="bg-muted/50 h-64 animate-pulse rounded-lg" />
      ))}
    </div>
  )
}
