import type { Metadata } from "next";
import Link from "next/link";
import { RegisterForm } from "../../components/RegisterForm";
import { Card } from "../../components/ui/shadcn/card";

export const metadata: Metadata = {
  title: "Crear cuenta | TalentOS",
  description: "Registra un usuario para comenzar a usar TalentOS.",
};

const highlights = [
  "Criterios explícitos por vacante.",
  "Evidencia con documento, página y fragmento.",
  "Toda acción externa espera aprobación humana.",
];

export default function RegisterPage() {
  return (
    <div className="grid min-h-[calc(100vh-4rem)] items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
      <section
        aria-labelledby="register-intro-heading"
        className="relative hidden overflow-hidden rounded-3xl border border-border-subtle bg-surface-muted p-10 lg:block"
      >
        <span aria-hidden="true" className="absolute -right-12 -top-12 h-44 w-44 rounded-full bg-accent/10" />
        <span aria-hidden="true" className="absolute -bottom-16 -left-10 h-40 w-40 rounded-full bg-success/10" />
        <div className="relative space-y-6">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
            TalentOS · Demostración
          </p>
          <h2 id="register-intro-heading" className="max-w-lg text-4xl font-semibold leading-tight tracking-tight">
            Decisiones de contratación con evidencia, no con corazonadas.
          </h2>
          <p className="max-w-md text-base leading-relaxed text-text-muted">
            Crea una cuenta para organizar vacantes, revisar criterios y dejar registrada cada aprobación.
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
            Datos sintéticos. Sin acciones externas automáticas.
          </p>
        </div>
      </section>

      <section aria-labelledby="register-heading" className="mx-auto w-full max-w-md space-y-5">
        <div className="space-y-2">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            TalentOS
          </Link>
          <h1 id="register-heading" className="text-3xl font-semibold tracking-tight">
            Crear cuenta
          </h1>
          <p className="text-sm leading-relaxed text-text-muted">
            Registra un usuario para comenzar a usar TalentOS.
          </p>
        </div>
        <Card className="p-6">
          <RegisterForm />
        </Card>
        <p className="text-sm text-text-muted">
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" className="font-medium text-accent hover:opacity-80">
            Iniciar sesión
          </Link>
        </p>
      </section>
    </div>
  );
}
