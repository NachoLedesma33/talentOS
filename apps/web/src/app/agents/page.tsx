import { AgentRunPanel } from "../../components/AgentRunPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";

export default function AgentsPage() {
  return (
    <WorkspaceShell section="Agentes">
      <div className="space-y-6">
        <section className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Agentes</h1>
          <p className="text-sm text-text-muted">
            Centro de control de ejecuciones: traza por evento, errores y aprobaciones humanas.
          </p>
        </section>

        <AgentRunPanel />
      </div>
    </WorkspaceShell>
  );
}
