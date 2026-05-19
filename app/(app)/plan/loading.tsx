// app/(app)/plan/loading.tsx
export default function PlanLoading() {
  return (
    <div className="space-y-6">
      <div className="bg-muted/50 h-8 w-48 animate-pulse rounded" />
      <div className="bg-muted/50 h-10 w-full animate-pulse rounded" />
      <div className="space-y-2">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="bg-muted/50 h-16 animate-pulse rounded-lg" />
        ))}
      </div>
    </div>
  )
}
