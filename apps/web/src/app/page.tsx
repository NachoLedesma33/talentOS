import { WorkspaceShell } from "../components/WorkspaceShell";

const apiEndpoints = [
  { url: "http://localhost:8000/health" },
  { url: "http://localhost:8000/ready" },
] as const;

export default function Home() {
  return (
    <WorkspaceShell section="TalentOS">
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

      <section aria-labelledby="access-heading" className="space-y-2">
        <h2 id="access-heading" className="text-sm font-semibold text-text-muted">
          Accesos
        </h2>
        <ul className="flex flex-wrap gap-4 text-sm">
          <li>
            <a href="/login">Iniciar sesión</a>
          </li>
          <li>
            <a href="/register">Crear cuenta</a>
          </li>
          <li>
            <a href="/dashboard">Ir al panel</a>
          </li>
          <li>
            <a href="/jobs">Vacantes</a>
          </li>
          <li>
            <a href="/candidates">Candidatos</a>
          </li>
          <li>
            <a href="/applications">Pipeline</a>
          </li>
          <li>
            <a href="/assessment">Evaluación</a>
          </li>
        </ul>
      </section>

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
    </WorkspaceShell>
  );
}
