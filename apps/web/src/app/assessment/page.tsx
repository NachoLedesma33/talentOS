import { AssessmentComparison } from "../../components/AssessmentComparison";
import { AssessmentPanel } from "../../components/AssessmentPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";

export default function AssessmentPage() {
  return (
    <WorkspaceShell section="Evaluación">
      <div className="space-y-6">
        <section className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Evaluación</h1>
          <p className="text-sm text-text-muted">
            Evaluación basada en evidencia: criterios, citas verificables, brechas y revisión humana.
          </p>
        </section>

        <AssessmentPanel />
        <AssessmentComparison />
      </div>
    </WorkspaceShell>
  );
}
