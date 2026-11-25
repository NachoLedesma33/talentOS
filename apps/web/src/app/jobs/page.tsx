"use client";

import { JobsPanel } from "../../components/JobsPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";

export default function JobsPage() {
  return (
    <WorkspaceShell section="Vacantes">
      <div className="space-y-6">
        <section className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Vacantes</h1>
          <p className="text-sm text-text-muted">
            Gestión de vacantes y requisitos de la organización activa.
          </p>
        </section>
        <JobsPanel />
      </div>
    </WorkspaceShell>
  );
}
