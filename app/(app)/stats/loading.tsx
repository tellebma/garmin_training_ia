// app/(app)/stats/loading.tsx
export default function StatsLoading() {
  return (
    <div className="space-y-8" aria-label="Chargement du cockpit">
      <div className="flex items-end justify-between">
        <div className="space-y-2">
          <div className="bg-muted/50 h-4 w-28 animate-pulse rounded" />
          <div className="bg-muted/50 h-8 w-64 animate-pulse rounded" />
        </div>
        <div className="bg-muted/50 h-9 w-44 animate-pulse rounded-md" />
      </div>
      <div className="bg-muted/50 h-24 animate-pulse rounded-md" />
      <div className="grid border-y sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse p-4">
            <div className="bg-muted/50 h-4 w-20 rounded" />
            <div className="bg-muted/50 mt-3 h-7 w-24 rounded" />
          </div>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="bg-muted/50 h-72 animate-pulse rounded-md" />
        <div className="bg-muted/50 h-72 animate-pulse rounded-md" />
      </div>
    </div>
  )
}
