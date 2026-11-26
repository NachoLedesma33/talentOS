"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "./ui/shadcn/button";
import { Input } from "./ui/shadcn/input";

const commands = [
  { href: "/dashboard", label: "Panel", hint: "Resumen de la organización" },
  { href: "/jobs", label: "Vacantes", hint: "Requisitos y etapas" },
  { href: "/candidates", label: "Candidatos", hint: "Perfiles y evidencia" },
  { href: "/applications", label: "Pipeline", hint: "Postulaciones por etapa" },
  { href: "/documents", label: "Documentos", hint: "Archivos privados" },
  { href: "/assessment", label: "Evaluación", hint: "Criterios y brechas" },
  { href: "/interviews", label: "Entrevistas", hint: "Agenda y guiones" },
  { href: "/agents", label: "Agentes", hint: "Ejecuciones y traza" },
  { href: "/automations", label: "Automatizaciones", hint: "Reglas y aprobaciones" },
  { href: "/integrations", label: "Integraciones", hint: "Adaptadores y entregas" },
  { href: "/analytics", label: "Analítica", hint: "Métricas del proceso" },
] as const;

export function CommandMenu() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && open) {
        setOpen(false);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setQuery("");
        setOpen((current) => !current);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    }
  }, [open]);

  const visible = useMemo(() => {
    const filter = query.trim().toLocaleLowerCase("es");
    return commands.filter(({ label }) => label.toLocaleLowerCase("es").includes(filter));
  }, [query]);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-keyshortcuts="Control+K Meta+K"
        aria-expanded={open}
        onClick={() => {
          setQuery("");
          setOpen((current) => !current);
        }}
      >
        Buscar sección…
      </Button>
      {open ? (
        <dialog
          open
          aria-label="Buscar sección"
          className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-lg rounded-md border border-border bg-surface p-4 text-text shadow-lg"
        >
          <div className="space-y-3">
            <Input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filtrar secciones"
              aria-label="Filtrar secciones"
            />
            <ul className="max-h-80 space-y-1 overflow-y-auto text-sm">
              {visible.map((command) => (
                <li key={command.href}>
                  <a
                    href={command.href}
                    className="block rounded-sm px-2 py-2 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => setOpen(false)}
                  >
                    <span className="font-medium">{command.label}</span>
                    <span className="ml-2 text-text-muted">{command.hint}</span>
                  </a>
                </li>
              ))}
            </ul>
            {visible.length === 0 ? <p className="text-sm text-text-muted">Sin resultados.</p> : null}
          </div>
        </dialog>
      ) : null}
    </>
  );
}
