import Link from "next/link";

export default function NotFound() {
  return (
    <section className="space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">
        Página no encontrada
      </h1>
      <p className="text-sm text-text-muted">
        La página que buscas no existe o cambió de ubicación.
      </p>
      <Link href="/">Volver al inicio</Link>
    </section>
  );
}
