"use client";

import { CandidatesPanel } from "../../components/CandidatesPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";

export default function CandidatesPage() {
  return (
    <WorkspaceShell section="Candidatos">
      <div className="space-y-6">
        <section className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Candidatos</h1>
          <p className="text-sm text-text-muted">
            Perfiles, notas internas y actividad de la organización activa.
          </p>
        </section>
        <CandidatesPanel />
      </div>
    </WorkspaceShell>
  );
}
