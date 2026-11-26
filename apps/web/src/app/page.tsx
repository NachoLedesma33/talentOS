import Link from "next/link";
import { Button } from "../components/ui/shadcn/button";
import { Card } from "../components/ui/shadcn/card";

const capabilities = [
  {
    title: "Vacantes y candidatos",
    description:
      "Organiza requisitos, postulaciones y etapas con criterios explícitos y traza de cada cambio.",
    href: "/jobs",
    action: "Ver vacantes",
  },
  {
    title: "Evaluación con evidencia",
    description:
      "Cada criterio muestra su evidencia verificable, sus brechas y el estado de revisión humana.",
    href: "/assessment",
    action: "Ver evaluación",
  },
  {
    title: "Agentes y automatizaciones",
    description:
      "Ejecuciones, herramientas invocadas y aprobaciones pendientes quedan visibles en la traza.",
    href: "/agents",
    action: "Ver agentes",
  },
] as const;

const steps = [
  {
    title: "1. Define el puesto",
    description: "Publica la vacante y registra los criterios que se evaluarán.",
  },
  {
    title: "2. Revisa la evidencia",
    description: "Contrasta requisitos con fragmentos verificables y limitaciones declaradas.",
  },
  {
    title: "3. Decide con supervisión",
    description: "Las acciones externas y las decisiones sensibles esperan aprobación humana.",
  },
] as const;

export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-12 px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <Link href="/" className="text-base font-semibold tracking-tight">
          TalentOS
        </Link>
        <nav aria-label="Navegación de la portada">
          <ul className="flex flex-wrap gap-4 text-sm text-text-muted">
            <li>
              <a href="#producto">Producto</a>
            </li>
            <li>
              <a href="#flujo">Flujo</a>
            </li>
            <li>
              <a href="#accesos">Accesos</a>
            </li>
          </ul>
        </nav>
      </header>

      <main className="flex-1 space-y-14">
        <section
          aria-labelledby="hero-heading"
          className="grid gap-8 py-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-center"
        >
          <div className="space-y-5">
            <p className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              Reclutamiento asistido y supervisado
            </p>
            <h1
              id="hero-heading"
              className="text-4xl font-semibold tracking-tight sm:text-5xl"
            >
              Decisiones de contratación con evidencia, no con corazonadas.
            </h1>
            <p className="max-w-2xl text-base text-text-muted sm:text-lg">
              TalentOS organiza vacantes, candidatos y evaluaciones. Muestra la evidencia
              verificable, las brechas y quién aprobó cada acción.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg">
                <a href="/register">Crear cuenta</a>
              </Button>
              <Button asChild variant="outline" size="lg">
                <a href="/dashboard">Ir al panel</a>
              </Button>
            </div>
            <p className="text-sm text-text-muted">
              Sin inferencias de atributos protegidos. Ninguna acción externa se ejecuta sin
              aprobación humana.
            </p>
          </div>

          <Card className="space-y-3 p-5">
            <h2 className="text-sm font-semibold">Qué verás antes de decidir</h2>
            <ul className="space-y-2 text-sm text-text-muted">
              <li>Requisitos evaluados y estado de cada uno.</li>
              <li>Documento, página y fragmento de cada evidencia.</li>
              <li>Limitaciones, brechas y revisión pendiente.</li>
              <li>Actor y consecuencia de cada aprobación.</li>
            </ul>
          </Card>
        </section>

        <section id="producto" aria-labelledby="capabilities-heading" className="space-y-4">
          <h2 id="capabilities-heading" className="text-2xl font-semibold tracking-tight">
            Una sola superficie para el proceso
          </h2>
          <div className="grid gap-4 md:grid-cols-3">
            {capabilities.map((item) => (
              <Card key={item.href} className="space-y-2 p-4">
                <h3 className="text-base font-semibold">{item.title}</h3>
                <p className="text-sm text-text-muted">{item.description}</p>
                <a
                  href={item.href}
                  className="text-sm font-medium text-accent underline-offset-4 hover:underline"
                >
                  {item.action}
                </a>
              </Card>
            ))}
          </div>
        </section>

        <section id="flujo" aria-labelledby="steps-heading" className="space-y-4">
          <h2 id="steps-heading" className="text-2xl font-semibold tracking-tight">
            Cómo funciona
          </h2>
          <ol className="grid gap-4 md:grid-cols-3">
            {steps.map((step) => (
              <li key={step.title}>
                <Card className="h-full space-y-2 p-4">
                  <h3 className="text-base font-semibold">{step.title}</h3>
                  <p className="text-sm text-text-muted">{step.description}</p>
                </Card>
              </li>
            ))}
          </ol>
        </section>

        <section
          id="accesos"
          aria-labelledby="access-heading"
          className="space-y-3 border-t border-border pt-6"
        >
          <h2 id="access-heading" className="text-lg font-semibold">
            Accesos
          </h2>
          <ul className="flex flex-wrap gap-4 text-sm">
            <li>
              <a href="/login">Iniciar sesión</a>
            </li>
            <li>
              <a href="/register">Registro</a>
            </li>
            <li>
              <a href="/jobs">Panel de vacantes</a>
            </li>
            <li>
              <a href="/candidates">Panel de candidatos</a>
            </li>
          </ul>
        </section>
      </main>

      <footer className="border-t border-border pt-4 text-xs text-text-muted">
        <p>
          TalentOS · entorno local:{" "}
          <a href="http://localhost:8000/health">/health</a> ·{" "}
          <a href="http://localhost:8000/ready">/ready</a>
        </p>
      </footer>
    </div>
  );
}
