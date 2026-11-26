import type { Metadata } from "next";
import Link from "next/link";
import { LoginForm } from "../../components/LoginForm";
import { Card } from "../../components/ui/shadcn/card";

export const metadata: Metadata = {
  title: "Iniciar sesión | TalentOS",
  description: "Accede a tu cuenta de TalentOS para gestionar tus organizaciones.",
};

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-4">
        <div className="space-y-1">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            TalentOS
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">Iniciar sesión</h1>
          <p className="text-sm text-text-muted">
            Accede con tu cuenta para gestionar tus organizaciones.
          </p>
        </div>
        <Card className="p-5">
          <LoginForm />
        </Card>
        <p className="text-sm text-text-muted">
          ¿Aún no tienes cuenta?{" "}
          <Link href="/register" className="text-accent underline underline-offset-4">
            Crear cuenta
          </Link>
        </p>
      </div>
    </main>
  );
}
