import Image from "next/image";
import Link from "next/link";
import { Button } from "../components/ui/shadcn/button";
import { Card } from "../components/ui/shadcn/card";

const capabilities = [
  {
    title: "Vacantes con criterio",
    description:
      "Define requisitos explícitos y mantén cada cambio trazado por organización.",
    href: "/jobs",
    action: "Ver vacantes",
  },
  {
    title: "Evidencia verificable",
    description:
      "Documento, página y fragmento por requisito. Brechas y ausencias dichas sin relleno.",
    href: "/assessment",
    action: "Ver evaluación",
  },
  {
    title: "Traza de decisiones",
    description:
      "Ejecuciones, herramientas y aprobaciones pendientes visibles en un mismo lugar.",
    href: "/agents",
    action: "Ver traza",
  },
] as const;

const steps = [
  {
    step: "01",
    title: "Prepara la vacante",
    description: "Reúne criterios, cargo y etapas antes de abrir el pipeline.",
  },
  {
    step: "02",
    title: "Contrasta evidencia",
    description: "Revisa cada requisito con su fuente y marca lo que necesita revisión.",
  },
  {
    step: "03",
    title: "Decide y deja rastro",
    description: "Toda acción externa espera aprobación humana y queda registrada.",
  },
] as const;

const evidenceStates = [
  { label: "supported", detail: "Evidencia directa" },
  { label: "partial", detail: "Evidencia incompleta" },
  { label: "not_found", detail: "Sin evidencia" },
  { label: "needs_review", detail: "Revisión humana" },
] as const;

const pipeline = [
  {
    title: "Por revisar",
    count: "12",
    detail: "Candidato sintético · evidencia pendiente",
    tone: "bg-warning/10 text-warning",
  },
  {
    title: "En entrevista",
    count: "4",
    detail: "Prueba de concepto · datos de demo",
    tone: "bg-accent/10 text-accent",
  },
  {
    title: "Listo para decisión",
    count: "2",
    detail: "Aprobación humana requerida",
    tone: "bg-success/10 text-success",
  },
] as const;

export default function Home() {
  return (
    <div className="flex flex-col">
      <header className="border-b border-border-subtle bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3 text-text">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-on-accent"
            >
              <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
                <path
                  d="M5 6h14M12 6v12M8 18h8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="text-sm font-semibold tracking-tight">TalentOS</span>
          </Link>

          <nav aria-label="Navegación de la portada">
            <ul className="flex flex-wrap items-center gap-5 text-sm text-text-muted">
              <li><Link href="#producto">Producto</Link></li>
              <li><Link href="#metodo">Método</Link></li>
              <li><Link href="#evidencia">Evidencia</Link></li>
            </ul>
          </nav>

          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link href="/login" className="text-text-muted">Acceder</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/register">Empezar ahora</Link>
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8">
        <section
          aria-labelledby="hero-heading"
          className="grid gap-14 py-20 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:py-28"
        >
          <div className="space-y-7">
            <p className="inline-flex rounded-full border border-border-subtle bg-surface-muted px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
              Para equipos que contratan con criterio
            </p>
            <h1
              id="hero-heading"
              className="max-w-3xl text-4xl font-semibold leading-[1.04] tracking-tight text-text sm:text-5xl lg:text-6xl"
            >
              Decisiones de contratación con evidencia, no con corazonadas.
            </h1>
            <p className="max-w-2xl text-base leading-relaxed text-text-muted sm:text-lg">
              TalentOS reúne vacantes, candidatos y evaluaciones en una superficie tranquila.
              Cada criterio muestra su fuente, sus brechas y quién aprobó la acción.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild size="lg" className="group gap-3 rounded-full px-6">
                <Link href="/register">
                  Crear cuenta
                  <span
                    aria-hidden="true"
                    className="grid h-7 w-7 place-items-center rounded-full bg-white/20 text-base transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:translate-x-0.5"
                  >
                    →
                  </span>
                </Link>
              </Button>
              <Button asChild variant="ghost" size="lg">
                <Link href="/dashboard">Ir al panel</Link>
              </Button>
            </div>
            <p className="text-sm text-text-muted">
              Sin inferencias de atributos protegidos. Ninguna acción externa se ejecuta sin
              aprobación humana.
            </p>
          </div>

          <div className="space-y-4">
            <Image
              src="/hero-talentos.svg"
              alt="Ilustración original: etapas de selección conectadas con evidencia y aprobación humana."
              width={720}
              height={420}
              className="h-auto w-full rounded-[1.75rem] border border-border-subtle bg-surface-muted"
              priority
            />
            <div className="rounded-[1.5rem] bg-surface-muted p-2">
              <div className="rounded-[1.25rem] bg-surface p-5 sm:p-6">
                <div className="mb-5 flex items-baseline justify-between gap-3">
                  <h2 className="text-sm font-semibold text-text">Pipeline · vista de producto</h2>
                  <span className="text-[11px] uppercase tracking-wider text-text-muted">
                    Datos sintéticos
                  </span>
                </div>
                <ol className="space-y-3">
                  {pipeline.map((item) => (
                    <li
                      key={item.title}
                      className="flex items-center gap-4 rounded-xl bg-surface-muted px-4 py-3"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-text">{item.title}</span>
                        <span className="block text-xs text-text-muted">{item.detail}</span>
                      </span>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${item.tone}`}>
                        {item.count}
                      </span>
                    </li>
                  ))}
                </ol>
                <p className="mt-5 text-xs leading-relaxed text-text-muted">
                  Cada tarjeta abre criterios, evidencia con página y fragmento, y la acción
                  pendiente de aprobación.
                </p>
              </div>
            </div>
          </div>
        </section>

        <dl className="grid gap-6 border-y border-border-subtle py-8 sm:grid-cols-3">
          <div className="space-y-1">
            <dt className="text-xs uppercase tracking-wider text-text-muted">Estados de evidencia</dt>
            <dd className="text-3xl font-semibold tracking-tight text-text">4</dd>
            <p className="text-xs text-text-muted">Con etiqueta y significado propio.</p>
          </div>
          <div className="space-y-1">
            <dt className="text-xs uppercase tracking-wider text-text-muted">Última palabra</dt>
            <dd className="text-3xl font-semibold tracking-tight text-text">Humana</dd>
            <p className="text-xs text-text-muted">La IA propone; la persona aprueba.</p>
          </div>
          <div className="space-y-1">
            <dt className="text-xs uppercase tracking-wider text-text-muted">Acciones externas automáticas</dt>
            <dd className="text-3xl font-semibold tracking-tight text-text">0</dd>
            <p className="text-xs text-text-muted">Toda salida sensible queda pendiente.</p>
          </div>
        </dl>

        <section id="producto" aria-labelledby="capabilities-heading" className="space-y-8 py-20">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Producto</p>
            <h2 id="capabilities-heading" className="text-3xl font-semibold tracking-tight text-text">
              Una superficie para todo el recorrido
            </h2>
            <p className="text-base leading-relaxed text-text-muted">
              Menos pestañas, más contexto. Cada módulo responde una decisión concreta del
              reclutador.
            </p>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {capabilities.map((item) => (
              <Card key={item.href} className="flex h-full flex-col justify-between gap-6 p-5">
                <div className="space-y-2">
                  <h3 className="text-base font-semibold text-text">{item.title}</h3>
                  <p className="text-sm leading-relaxed text-text-muted">{item.description}</p>
                </div>
                <Link
                  href={item.href}
                  className="inline-flex w-fit items-center gap-2 text-sm font-medium text-accent"
                >
                  {item.action}
                  <span aria-hidden="true">→</span>
                </Link>
              </Card>
            ))}
          </div>
        </section>

        <section id="metodo" aria-labelledby="steps-heading" className="space-y-8 py-20">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Método</p>
            <h2 id="steps-heading" className="text-3xl font-semibold tracking-tight text-text">
              Del criterio a la decisión, sin saltos ciegos
            </h2>
          </div>
          <ol className="grid gap-5 md:grid-cols-3">
            {steps.map((item) => (
              <li key={item.step} className="space-y-3 border-t border-border-subtle pt-5">
                <span className="text-xs font-semibold tracking-widest text-accent">{item.step}</span>
                <h3 className="text-base font-semibold text-text">{item.title}</h3>
                <p className="text-sm leading-relaxed text-text-muted">{item.description}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="evidencia" aria-labelledby="evidence-heading" className="space-y-8 py-20">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Evidencia</p>
            <h2 id="evidence-heading" className="text-3xl font-semibold tracking-tight text-text">
              La ausencia de evidencia también se muestra
            </h2>
            <p className="text-base leading-relaxed text-text-muted">
              Los cuatro estados llevan texto y forma distinta. Ninguno depende solo del color.
            </p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {evidenceStates.map((state) => (
              <li
                key={state.label}
                className="rounded-xl bg-surface-muted px-4 py-3 text-sm text-text"
              >
                <span className="block font-mono text-xs text-accent">{state.label}</span>
                <span className="text-text-muted">{state.detail}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <footer className="border-t border-border-subtle bg-surface-muted">
        <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr] lg:px-8">
          <div className="space-y-3">
            <p className="text-sm font-semibold tracking-tight text-text">TalentOS</p>
            <p className="max-w-sm text-sm leading-relaxed text-text-muted">
              Reclutamiento asistido, trazable y supervisado. Demostración local con datos
              sintéticos.
            </p>
          </div>
          <div id="accesos" className="space-y-3 text-sm">
            <h2 className="font-semibold text-text">Acceso</h2>
            <ul className="space-y-2 text-text-muted">
              <li><Link href="/login">Iniciar sesión</Link></li>
              <li><Link href="/register">Registro</Link></li>
              <li><Link href="/dashboard">Panel</Link></li>
            </ul>
          </div>
          <div className="space-y-3 text-sm">
            <h2 className="font-semibold text-text">Estado del entorno</h2>
            <ul className="space-y-2 text-text-muted">
              <li>
                <a href="http://localhost:8000/health">/health</a>
              </li>
              <li>
                <a href="http://localhost:8000/ready">/ready</a>
              </li>
            </ul>
          </div>
        </div>
        <div className="mx-auto w-full max-w-6xl px-4 pb-8 text-xs text-text-muted sm:px-6 lg:px-8">
          <p>TalentOS · interfaz de demostración · sin datos personales reales.</p>
        </div>
      </footer>
    </div>
  );
}
