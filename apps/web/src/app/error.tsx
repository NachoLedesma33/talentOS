"use client";

import Link from "next/link";
import { Button } from "../components/ui/shadcn/button";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function Error({ error, reset }: ErrorProps) {
  return (
    <section
      role="alert"
      aria-labelledby="section-error-title"
      className="mx-auto flex w-full max-w-3xl flex-col items-start gap-8 py-16 sm:py-24"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid h-12 w-12 place-items-center rounded-xl bg-accent text-on-accent"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6">
            <path
              d="M12 8v5M12 16h.01M10.3 4.8 3.6 17a1.5 1.5 0 0 0 1.3 2.2h14.2a1.5 1.5 0 0 0 1.3-2.2L13.7 4.8a1.9 1.9 0 0 0-3.4 0Z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
          Error de carga · sección no disponible
        </p>
      </div>

      <div className="space-y-4">
        <h1
          id="section-error-title"
          className="text-4xl font-semibold tracking-tight text-text sm:text-5xl"
        >
          No se pudo cargar esta sección.
        </h1>
        <p className="max-w-xl text-base leading-relaxed text-text-muted">
          Comprueba que la API local esté disponible y vuelve a intentarlo. Si el problema
          continúa, regresa al panel para revisar el estado del entorno.
        </p>
        {error.digest ? (
          <p className="text-sm text-text-muted">
            Referencia: <code className="font-mono text-text">{error.digest}</code>
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-3">
        <Button type="button" size="lg" onClick={reset}>
          Reintentar
        </Button>
        <Button asChild variant="outline" size="lg">
          <Link href="/dashboard">Volver al panel</Link>
        </Button>
      </div>

      <dl className="grid w-full gap-4 border-t border-border-subtle pt-6 text-sm sm:grid-cols-2">
        <div className="space-y-1">
          <dt className="text-xs uppercase tracking-wider text-text-muted">Alcance</dt>
          <dd className="text-text">Esta sección; el resto del workspace sigue disponible.</dd>
        </div>
        <div className="space-y-1">
          <dt className="text-xs uppercase tracking-wider text-text-muted">Datos</dt>
          <dd className="text-text">No se muestran mensajes crudos ni datos personales.</dd>
        </div>
      </dl>
    </section>
  );
}
