import { RegisterForm } from "../../components/RegisterForm";

export default function RegisterPage() {
  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Crear cuenta</h1>
        <p className="text-sm text-text-muted">
          Registra un usuario para comenzar a usar TalentOS.
        </p>
      </div>
      <RegisterForm />
      <p className="text-sm">
        ¿Ya tienes cuenta? <a href="/login">Iniciar sesión</a>
      </p>
    </section>
  );
}
