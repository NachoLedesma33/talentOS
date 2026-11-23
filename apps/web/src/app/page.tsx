const apiEndpoints = [
  { url: "http://localhost:8000/health" },
  { url: "http://localhost:8000/ready" },
] as const;

export default function Home() {
  return (
    <div className="space-y-5">
      <section className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">TalentOS</h1>
        <p className="text-base text-text-muted">
          Reclutamiento asistido, trazable y supervisado.
        </p>
      </section>

      <p className="inline-flex rounded-sm border border-border bg-surface-muted px-3 py-2 text-sm text-text">
        Fase 1 — Fundación del monorepo
      </p>

      <section aria-labelledby="api-endpoints-heading" className="space-y-2">
        <h2
          id="api-endpoints-heading"
          className="text-sm font-semibold text-text-muted"
        >
          Endpoints de la API
        </h2>
        <ul className="space-y-1">
          {apiEndpoints.map((endpoint) => (
            <li key={endpoint.url}>
              <a href={endpoint.url}>{endpoint.url}</a>
            </li>
          ))}
        </ul>
        <p className="text-sm text-text-muted">
          Comprueba estos endpoints con la API local en ejecución.
        </p>
      </section>
    </div>
  );
}
