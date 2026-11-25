"use client";

import { IntegrationsPanel } from "../../components/IntegrationsPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";

export default function IntegrationsPage() {
  return (
    <WorkspaceShell section="Integraciones">
      <div className="space-y-6">
        <section className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Integraciones</h1>
          <p className="text-sm text-text-muted">
            Estado de proveedores, entregas salientes y borradores pendientes de decisión humana.
          </p>
          <p className="text-sm">
            <a href="/dashboard">Volver al panel</a>
          </p>
        </section>

        <IntegrationsPanel />
      </div>
    </WorkspaceShell>
  );
}
