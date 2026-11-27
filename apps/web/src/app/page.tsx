"use client";

import Image from "next/image";
import Link from "next/link";
import { Button } from "../components/ui/shadcn/button";
import { Card } from "../components/ui/shadcn/card";
import { LocaleToggle, useI18n, type MessageKey } from "../lib/i18n";

const capabilities: ReadonlyArray<{
  titleKey: MessageKey;
  descriptionKey: MessageKey;
  actionKey: MessageKey;
  href: string;
}> = [
  {
    titleKey: "capabilities.jobs.title",
    descriptionKey: "capabilities.jobs.body",
    href: "/jobs",
    actionKey: "capabilities.jobs.action",
  },
  {
    titleKey: "capabilities.evidence.title",
    descriptionKey: "capabilities.evidence.body",
    href: "/assessment",
    actionKey: "capabilities.evidence.action",
  },
  {
    titleKey: "capabilities.trace.title",
    descriptionKey: "capabilities.trace.body",
    href: "/agents",
    actionKey: "capabilities.trace.action",
  },
];

const steps: ReadonlyArray<{
  step: string;
  titleKey: MessageKey;
  descriptionKey: MessageKey;
}> = [
  {
    step: "01",
    titleKey: "steps.one.title",
    descriptionKey: "steps.one.body",
  },
  {
    step: "02",
    titleKey: "steps.two.title",
    descriptionKey: "steps.two.body",
  },
  {
    step: "03",
    titleKey: "steps.three.title",
    descriptionKey: "steps.three.body",
  },
];

const evidenceStates: ReadonlyArray<{ label: string; detailKey: MessageKey }> = [
  { label: "supported", detailKey: "evidence.supported" },
  { label: "partial", detailKey: "evidence.partial" },
  { label: "not_found", detailKey: "evidence.notFound" },
  { label: "needs_review", detailKey: "evidence.needsReview" },
];

const pipeline: ReadonlyArray<{
  titleKey: MessageKey;
  detailKey: MessageKey;
  count: string;
  tone: string;
}> = [
  {
    titleKey: "pipeline.review",
    count: "12",
    detailKey: "pipeline.reviewDetail",
    tone: "bg-warning/10 text-warning",
  },
  {
    titleKey: "pipeline.interview",
    count: "4",
    detailKey: "pipeline.interviewDetail",
    tone: "bg-accent/10 text-accent",
  },
  {
    titleKey: "pipeline.decision",
    count: "2",
    detailKey: "pipeline.decisionDetail",
    tone: "bg-success/10 text-success",
  },
];

export default function Home() {
  const { t } = useI18n();

  return (
    <div className="flex flex-col">
      <header className="border-b border-border-subtle bg-surface">
        <div className="mx-auto flex w-full max-w-[1440px] flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-10">
          <Link href="/" className="flex items-center gap-3 text-text">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-on-accent"
            >
              <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
                <path
                  d="M5 6h14M12 6v12M8 18h8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="text-sm font-semibold tracking-tight">TalentOS</span>
          </Link>

          <nav aria-label="Navegación de la portada">
            <ul className="flex flex-wrap items-center gap-5 text-sm text-text-muted">
              <li><Link href="#producto">{t("nav.producto")}</Link></li>
              <li><Link href="#metodo">{t("nav.metodo")}</Link></li>
              <li><Link href="#evidencia">{t("nav.evidencia")}</Link></li>
            </ul>
          </nav>

          <div className="flex items-center gap-2">
            <LocaleToggle />
            <Button asChild variant="ghost" size="sm">
              <Link href="/login" className="text-text-muted">{t("nav.acceso")}</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/register">{t("nav.empezar")}</Link>
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1440px] px-4 sm:px-6 lg:px-10">
        <section
          aria-labelledby="hero-heading"
          className="grid gap-14 py-20 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:py-28"
        >
          <div className="space-y-7">
            <p className="inline-flex rounded-full border border-border-subtle bg-surface-muted px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
              {t("hero.eyebrow")}
            </p>
            <h1
              id="hero-heading"
              className="max-w-3xl text-4xl font-semibold leading-[1.04] tracking-tight text-text sm:text-5xl lg:text-6xl"
            >
              {t("hero.title")}
            </h1>
            <p className="max-w-2xl text-base leading-relaxed text-text-muted sm:text-lg">
              {t("hero.body")}
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild size="lg" className="group gap-3 rounded-full px-6">
                <Link href="/register">
                  {t("hero.cta")}
                  <span
                    aria-hidden="true"
                    className="grid h-7 w-7 place-items-center rounded-full bg-white/20 text-base transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:translate-x-0.5"
                  >
                    →
                  </span>
                </Link>
              </Button>
              <Button asChild variant="ghost" size="lg">
                <Link href="/dashboard">{t("hero.secondary")}</Link>
              </Button>
            </div>
            <p className="text-sm text-text-muted">{t("hero.note")}</p>
          </div>

          <div className="space-y-4">
            <Image
              src="/hero-talentos.jpg"
              alt="Ilustración: dos personas revisan una postulación con evidencia y aprobación humana."
              width={1200}
              height={896}
              className="h-auto w-full rounded-[1.75rem] border border-border-subtle bg-surface-muted"
              priority
            />
            <div className="rounded-[1.5rem] bg-surface-muted p-2">
              <div className="rounded-[1.25rem] bg-surface p-5 sm:p-6">
                <div className="mb-5 flex items-baseline justify-between gap-3">
                  <h2 className="text-sm font-semibold text-text">{t("hero.pipeline")}</h2>
                  <span className="text-[11px] uppercase tracking-wider text-text-muted">
                    {t("hero.synthetic")}
                  </span>
                </div>
                <ol className="space-y-3">
                  {pipeline.map((item) => (
                    <li
                      key={item.titleKey}
                      className="flex items-center gap-4 rounded-xl bg-surface-muted px-4 py-3"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-text">{t(item.titleKey)}</span>
                        <span className="block text-xs text-text-muted">{t(item.detailKey)}</span>
                      </span>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${item.tone}`}>
                        {item.count}
                      </span>
                    </li>
                  ))}
                </ol>
                <p className="mt-5 text-xs leading-relaxed text-text-muted">{t("hero.pipelineNote")}</p>
              </div>
            </div>
          </div>
        </section>

        <dl className="grid gap-6 border-y border-border-subtle py-8 sm:grid-cols-3">
          <div className="space-y-1">
            <dt className="text-xs uppercase tracking-wider text-text-muted">{t("stats.evidence")}</dt>
            <dd className="text-3xl font-semibold tracking-tight text-text">
              4
              <span className="mt-1 block text-xs font-normal text-text-muted">
                {t("stats.evidenceDetail")}
              </span>
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="text-xs uppercase tracking-wider text-text-muted">{t("stats.human")}</dt>
            <dd className="text-3xl font-semibold tracking-tight text-text">
              {t("stats.humanValue")}
              <span className="mt-1 block text-xs font-normal text-text-muted">
                {t("stats.humanDetail")}
              </span>
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="text-xs uppercase tracking-wider text-text-muted">{t("stats.automatic")}</dt>
            <dd className="text-3xl font-semibold tracking-tight text-text">
              0
              <span className="mt-1 block text-xs font-normal text-text-muted">
                {t("stats.automaticDetail")}
              </span>
            </dd>
          </div>
        </dl>

        <section id="producto" aria-labelledby="capabilities-heading" className="space-y-8 py-20">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{t("capabilities.eyebrow")}</p>
            <h2 id="capabilities-heading" className="text-3xl font-semibold tracking-tight text-text">
              {t("capabilities.title")}
            </h2>
            <p className="text-base leading-relaxed text-text-muted">{t("capabilities.body")}</p>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {capabilities.map((item) => (
              <Card key={item.href} className="flex h-full flex-col justify-between gap-6 p-5">
                <div className="space-y-2">
                  <h3 className="text-base font-semibold text-text">{t(item.titleKey)}</h3>
                  <p className="text-sm leading-relaxed text-text-muted">{t(item.descriptionKey)}</p>
                </div>
                <Link
                  href={item.href}
                  className="inline-flex w-fit items-center gap-2 text-sm font-medium text-accent"
                >
                  {t(item.actionKey)}
                  <span aria-hidden="true">→</span>
                </Link>
              </Card>
            ))}
          </div>
        </section>

        <section id="metodo" aria-labelledby="steps-heading" className="space-y-8 py-20">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{t("steps.eyebrow")}</p>
            <h2 id="steps-heading" className="text-3xl font-semibold tracking-tight text-text">
              {t("steps.title")}
            </h2>
          </div>
          <ol className="grid gap-5 md:grid-cols-3">
            {steps.map((item) => (
              <li key={item.step} className="space-y-3 border-t border-border-subtle pt-5">
                <span className="text-xs font-semibold tracking-widest text-accent">{item.step}</span>
                <h3 className="text-base font-semibold text-text">{t(item.titleKey)}</h3>
                <p className="text-sm leading-relaxed text-text-muted">{t(item.descriptionKey)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="evidencia" aria-labelledby="evidence-heading" className="space-y-8 py-20">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{t("evidence.eyebrow")}</p>
            <h2 id="evidence-heading" className="text-3xl font-semibold tracking-tight text-text">
              {t("evidence.title")}
            </h2>
            <p className="text-base leading-relaxed text-text-muted">{t("evidence.body")}</p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {evidenceStates.map((state) => (
              <li
                key={state.label}
                className="rounded-xl bg-surface-muted px-4 py-3 text-sm text-text"
              >
                <span className="block font-mono text-xs text-accent">{state.label}</span>
                <span className="text-text-muted">{t(state.detailKey)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <footer className="border-t border-border-subtle bg-surface-muted">
        <div className="mx-auto grid w-full max-w-[1440px] gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.4fr_1fr] lg:px-10">
          <div className="space-y-3">
            <p className="text-sm font-semibold tracking-tight text-text">TalentOS</p>
            <p className="max-w-sm text-sm leading-relaxed text-text-muted">{t("footer.tagline")}</p>
          </div>
          <div id="accesos" className="space-y-3 text-sm">
            <h2 className="font-semibold text-text">{t("footer.access")}</h2>
            <ul className="space-y-2 text-text-muted">
              <li><Link href="/login">{t("footer.login")}</Link></li>
              <li><Link href="/register">{t("footer.register")}</Link></li>
              <li><Link href="/dashboard">{t("footer.dashboard")}</Link></li>
            </ul>
          </div>
        </div>
        <div className="mx-auto w-full max-w-[1440px] px-4 pb-8 text-xs text-text-muted sm:px-6 lg:px-10">
          <p>{t("footer.note")}</p>
        </div>
      </footer>
    </div>
  );
}
