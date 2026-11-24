import { AutomationRulePanel } from "../../components/AutomationRulePanel";

export default function AutomationsPage() {
  return (
    <div className="space-y-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Automatizaciones</h1>
        <p className="text-sm text-text-muted">
          Reglas por evento, condiciones deterministas, versiones y aprobaciones humanas.
        </p>
      </section>

      <AutomationRulePanel />
    </div>
  );
}
