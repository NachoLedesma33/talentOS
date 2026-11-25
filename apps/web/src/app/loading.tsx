export default function Loading() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="space-y-4"
    >
      <h1 className="text-2xl font-semibold tracking-tight">Cargando…</h1>
      <div aria-hidden="true" className="space-y-3">
        <div className="h-4 w-3/4 animate-pulse rounded-sm bg-surface-muted" />
        <div className="h-4 w-full animate-pulse rounded-sm bg-surface-muted" />
        <div className="h-24 w-full animate-pulse rounded-sm bg-surface-muted" />
      </div>
    </div>
  );
}
