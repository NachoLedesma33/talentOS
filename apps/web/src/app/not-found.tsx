import Link from "next/link";
import { Button } from "../components/ui/shadcn/button";

export default function NotFound() {
  return (
    <section
      aria-labelledby="not-found-title"
      className="mx-auto flex w-full max-w-3xl flex-col items-start gap-8 py-16 sm:py-24"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid h-12 w-12 place-items-center rounded-xl bg-accent text-on-accent"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6">
            <path
              d="M5 6h14M12 6v12M8 18h8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </span>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
          Error 404 · ruta no encontrada
        </p>
      </div>

      <div className="space-y-4">
        <h1
          id="not-found-title"
          className="text-4xl font-semibold tracking-tight text-text sm:text-5xl"
        >
          Esta página no existe.
        </h1>
        <p className="max-w-xl text-base leading-relaxed text-text-muted">
          La ruta puede haber cambiado o no pertenecer a este espacio de trabajo. Vuelve al panel
          para continuar con tus vacantes y candidatos.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button asChild size="lg">
          <Link href="/dashboard">Volver al panel</Link>
        </Button>
        <Button asChild variant="outline" size="lg">
          <Link href="/">Ir al inicio</Link>
        </Button>
      </div>

      <dl className="grid w-full gap-4 border-t border-border-subtle pt-6 text-sm sm:grid-cols-2">
        <div className="space-y-1">
          <dt className="text-xs uppercase tracking-wider text-text-muted">Resultado</dt>
          <dd className="font-mono text-text">404 · not_found</dd>
        </div>
        <div className="space-y-1">
          <dt className="text-xs uppercase tracking-wider text-text-muted">Siguiente paso</dt>
          <dd className="text-text">Revisar la ruta o regresar al workspace.</dd>
        </div>
      </dl>
    </section>
  );
}
