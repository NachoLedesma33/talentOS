import type { Metadata } from "next";
import Link from "next/link";
import { RegisterForm } from "../../components/RegisterForm";
import { Card } from "../../components/ui/shadcn/card";

export const metadata: Metadata = {
  title: "Crear cuenta | TalentOS",
  description: "Registra un usuario para comenzar a usar TalentOS.",
};

export default function RegisterPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-4">
        <div className="space-y-1">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            TalentOS
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">Crear cuenta</h1>
          <p className="text-sm text-text-muted">
            Registra un usuario para comenzar a usar TalentOS.
          </p>
        </div>
        <Card className="p-5">
          <RegisterForm />
        </Card>
        <p className="text-sm text-text-muted">
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" className="text-accent underline underline-offset-4">
            Iniciar sesión
          </Link>
        </p>
      </div>
    </main>
  );
}
