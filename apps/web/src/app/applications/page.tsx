"use client";

import { PipelineBoard } from "../../components/PipelineBoard";

export default function ApplicationsPage() {
  return (
    <div className="space-y-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Pipeline</h1>
        <p className="text-sm text-text-muted">
          Postulaciones por etapa. El backend valida cada transición.
        </p>
      </section>
      <PipelineBoard />
    </div>
  );
}
