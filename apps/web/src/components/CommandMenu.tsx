"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n, type MessageKey } from "../lib/i18n";
import { Button } from "./ui/shadcn/button";
import { Input } from "./ui/shadcn/input";

const commands: ReadonlyArray<{ href: string; label: MessageKey; hint: MessageKey }> = [
  { href: "/dashboard", label: "shell.panel", hint: "cmd.hint.panel" },
  { href: "/jobs", label: "shell.jobs", hint: "cmd.hint.jobs" },
  { href: "/candidates", label: "shell.candidates", hint: "cmd.hint.candidates" },
  { href: "/applications", label: "shell.pipeline", hint: "cmd.hint.pipeline" },
  { href: "/documents", label: "shell.documents", hint: "cmd.hint.documents" },
  { href: "/assessment", label: "shell.assessment", hint: "cmd.hint.assessment" },
  { href: "/interviews", label: "shell.interviews", hint: "cmd.hint.interviews" },
  { href: "/agents", label: "shell.agents", hint: "cmd.hint.agents" },
  { href: "/automations", label: "shell.automations", hint: "cmd.hint.automations" },
  { href: "/integrations", label: "shell.integrations", hint: "cmd.hint.integrations" },
  { href: "/analytics", label: "shell.analytics", hint: "cmd.hint.analytics" },
];

export function CommandMenu() {
  const { locale, t } = useI18n();
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
    const filter = query.trim().toLocaleLowerCase(locale);
    return commands.filter(({ label }) => t(label).toLocaleLowerCase(locale).includes(filter));
  }, [locale, query, t]);

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
        {t("cmd.trigger")}
      </Button>
      {open ? (
        <dialog
          open
          aria-label={t("cmd.aria")}
          className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-lg rounded-md border border-border bg-surface p-4 text-text shadow-lg"
        >
          <div className="space-y-3">
            <Input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("cmd.filter")}
              aria-label={t("cmd.filter")}
            />
            <ul className="max-h-80 space-y-1 overflow-y-auto text-sm">
              {visible.map((command) => (
                <li key={command.href}>
                  <a
                    href={command.href}
                    className="block rounded-sm px-2 py-2 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => setOpen(false)}
                  >
                    <span className="font-medium">{t(command.label)}</span>
                    <span className="ml-2 text-text-muted">{t(command.hint)}</span>
                  </a>
                </li>
              ))}
            </ul>
            {visible.length === 0 ? (
              <p className="text-sm text-text-muted">{t("cmd.empty")}</p>
            ) : null}
          </div>
        </dialog>
      ) : null}
    </>
  );
}
