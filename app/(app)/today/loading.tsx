// app/(app)/today/loading.tsx
export default function TodayLoading() {
  return (
    <div className="space-y-6">
      <div className="bg-muted/50 h-8 w-48 animate-pulse rounded" />
      <div className="bg-muted/50 h-36 animate-pulse rounded-lg" />
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-muted/50 h-24 animate-pulse rounded-lg" />
        <div className="bg-muted/50 h-24 animate-pulse rounded-lg" />
        <div className="bg-muted/50 h-24 animate-pulse rounded-lg" />
      </div>
      <div className="bg-muted/50 h-64 animate-pulse rounded-lg" />
    </div>
  )
}
