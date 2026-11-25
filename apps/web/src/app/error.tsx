"use client";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function Error({ error, reset }: ErrorProps) {
  return (
    <section role="alert" className="space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">
        No se pudo cargar esta sección
      </h1>
      <p className="text-sm text-text-muted">
        Comprueba que la API local esté disponible y vuelve a intentarlo.
      </p>
      {error.digest ? (
        <p className="text-sm text-text-muted">Referencia: {error.digest}</p>
      ) : null}
      <button
        type="button"
        onClick={reset}
        className="rounded-sm bg-accent px-3 py-2 text-sm font-semibold text-on-accent"
      >
        Reintentar
      </button>
      <p className="text-sm">
        <a href="/dashboard">Volver al panel</a>
      </p>
    </section>
  );
}
