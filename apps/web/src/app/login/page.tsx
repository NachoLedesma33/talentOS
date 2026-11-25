import { LoginForm } from "../../components/LoginForm";
import { WorkspaceShell } from "../../components/WorkspaceShell";

export default function LoginPage() {
  return (
    <WorkspaceShell section="Iniciar sesión">
      <section className="space-y-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Iniciar sesión</h1>
          <p className="text-sm text-text-muted">
            Accede con tu cuenta para gestionar tus organizaciones.
          </p>
        </div>
        <LoginForm />
        <p className="text-sm">
          ¿Aún no tienes cuenta? <a href="/register">Crear cuenta</a>
        </p>
      </section>
    </WorkspaceShell>
  );
}
