import { InterviewGuidePanel } from "../../components/InterviewGuidePanel";

export default function InterviewsPage() {
  return (
    <div className="space-y-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Entrevistas</h1>
        <p className="text-sm text-text-muted">
          Guías por postulación, preguntas trazables a requisitos, feedback humano e historial de
          cambios. Sin puntuación ni decisión automática.
        </p>
      </section>

      <InterviewGuidePanel />
    </div>
  );
}
