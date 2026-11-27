import type { Metadata } from "next";
import Link from "next/link";
import { LoginForm } from "../../components/LoginForm";
import { Card } from "../../components/ui/shadcn/card";

export const metadata: Metadata = {
  title: "Iniciar sesión | TalentOS",
  description: "Accede a tu cuenta de TalentOS para gestionar tus organizaciones.",
};

const highlights = [
  "Una vista por decisión del reclutador.",
  "Evidencia y brechas visibles sin abrir el CV completo.",
  "Aprobaciones con actor y consecuencia claros.",
];

export default function LoginPage() {
  return (
    <div className="grid min-h-[calc(100vh-4rem)] items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
      <section
        aria-labelledby="login-intro-heading"
        className="relative hidden overflow-hidden rounded-3xl border border-border-subtle bg-surface-muted p-10 lg:block"
      >
        <span aria-hidden="true" className="absolute -right-12 -top-12 h-44 w-44 rounded-full bg-accent/10" />
        <span aria-hidden="true" className="absolute -bottom-16 -left-10 h-40 w-40 rounded-full bg-success/10" />
        <div className="relative space-y-6">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
            TalentOS · Espacio de trabajo
          </p>
          <h2 id="login-intro-heading" className="max-w-lg text-4xl font-semibold leading-tight tracking-tight">
            Tu proceso de selección, trazable de principio a fin.
          </h2>
          <p className="max-w-md text-base leading-relaxed text-text-muted">
            Accede a tus organizaciones para revisar postulaciones, evidencia y aprobaciones pendientes.
          </p>
          <ul className="space-y-3">
            {highlights.map((item) => (
              <li key={item} className="flex items-start gap-3 text-sm text-text-muted">
                <span
                  aria-hidden="true"
                  className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-success/10 text-[11px] font-bold text-success"
                >
                  ✓
                </span>
                {item}
              </li>
            ))}
          </ul>
          <p className="text-xs text-text-muted">
            La sesión y los permisos los valida el servidor.
          </p>
        </div>
      </section>

      <section aria-labelledby="login-heading" className="mx-auto w-full max-w-md space-y-5">
        <div className="space-y-2">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            TalentOS
          </Link>
          <h1 id="login-heading" className="text-3xl font-semibold tracking-tight">
            Iniciar sesión
          </h1>
          <p className="text-sm leading-relaxed text-text-muted">
            Accede con tu cuenta para gestionar tus organizaciones.
          </p>
        </div>
        <Card className="p-6">
          <LoginForm />
        </Card>
        <p className="text-sm text-text-muted">
          ¿Olvidaste tu contraseña?{" "}
          <Link href="/forgot-password" className="font-medium text-accent hover:opacity-80">
            Recuperar contraseña
          </Link>
        </p>
        <p className="text-sm text-text-muted">
          ¿Aún no tienes cuenta?{" "}
          <Link href="/register" className="font-medium text-accent hover:opacity-80">
            Crear cuenta
          </Link>
        </p>
      </section>
    </div>
  );
}
