"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "es" | "en";

const STORAGE_KEY = "talentos:locale";

const es = {
  "nav.producto": "Producto",
  "nav.metodo": "Método",
  "nav.evidencia": "Evidencia",
  "nav.acceso": "Acceder",
  "nav.empezar": "Empezar ahora",
  "locale.toEn": "Cambiar a inglés",
  "locale.toEs": "Cambiar a español",
  "hero.eyebrow": "Para equipos que contratan con criterio",
  "hero.title": "Decisiones de contratación con evidencia, no con corazonadas.",
  "hero.body":
    "TalentOS reúne vacantes, candidatos y evaluaciones en una superficie tranquila. Cada criterio muestra su fuente, sus brechas y quién aprobó la acción.",
  "hero.cta": "Crear cuenta",
  "hero.secondary": "Ir al panel",
  "hero.note":
    "Sin inferencias de atributos protegidos. Ninguna acción externa se ejecuta sin aprobación humana.",
  "hero.pipeline": "Pipeline · vista de producto",
  "hero.synthetic": "Datos sintéticos",
  "hero.pipelineNote":
    "Cada tarjeta abre criterios, evidencia con página y fragmento, y la acción pendiente de aprobación.",
  "stats.evidence": "Estados de evidencia",
  "stats.evidenceDetail": "Con etiqueta y significado propio.",
  "stats.human": "Última palabra",
  "stats.humanValue": "Humana",
  "stats.humanDetail": "La IA propone; la persona aprueba.",
  "stats.automatic": "Acciones externas automáticas",
  "stats.automaticDetail": "Toda salida sensible queda pendiente.",
  "capabilities.eyebrow": "Producto",
  "capabilities.title": "Una superficie para todo el recorrido",
  "capabilities.body":
    "Menos pestañas, más contexto. Cada módulo responde una decisión concreta del reclutador.",
  "capabilities.jobs.title": "Vacantes con criterio",
  "capabilities.jobs.body":
    "Define requisitos explícitos y mantén cada cambio trazado por organización.",
  "capabilities.jobs.action": "Ver vacantes",
  "capabilities.evidence.title": "Evidencia verificable",
  "capabilities.evidence.body":
    "Documento, página y fragmento por requisito. Brechas y ausencias dichas sin relleno.",
  "capabilities.evidence.action": "Ver evaluación",
  "capabilities.trace.title": "Traza de decisiones",
  "capabilities.trace.body":
    "Ejecuciones, herramientas y aprobaciones pendientes visibles en un mismo lugar.",
  "capabilities.trace.action": "Ver traza",
  "steps.eyebrow": "Método",
  "steps.title": "Del criterio a la decisión, sin saltos ciegos",
  "steps.one.title": "Prepara la vacante",
  "steps.one.body": "Reúne criterios, cargo y etapas antes de abrir el pipeline.",
  "steps.two.title": "Contrasta evidencia",
  "steps.two.body": "Revisa cada requisito con su fuente y marca lo que necesita revisión.",
  "steps.three.title": "Decide y deja rastro",
  "steps.three.body": "Toda acción externa espera aprobación humana y queda registrada.",
  "evidence.eyebrow": "Evidencia",
  "evidence.title": "La ausencia de evidencia también se muestra",
  "evidence.body":
    "Los cuatro estados llevan texto y forma distinta. Ninguno depende solo del color.",
  "evidence.supported": "Evidencia directa",
  "evidence.partial": "Evidencia incompleta",
  "evidence.notFound": "Sin evidencia",
  "evidence.needsReview": "Revisión humana",
  "pipeline.review": "Por revisar",
  "pipeline.reviewDetail": "Candidato sintético · evidencia pendiente",
  "pipeline.interview": "En entrevista",
  "pipeline.interviewDetail": "Prueba de concepto · datos de demo",
  "pipeline.decision": "Listo para decisión",
  "pipeline.decisionDetail": "Aprobación humana requerida",
  "footer.tagline": "Reclutamiento asistido, trazable y supervisado. Demostración local con datos sintéticos.",
  "footer.access": "Acceso",
  "footer.login": "Iniciar sesión",
  "footer.register": "Registro",
  "footer.dashboard": "Panel",
  "footer.environment": "Estado del entorno",
  "footer.note": "TalentOS · interfaz de demostración · sin datos personales reales.",
  "shell.workspace": "Workspace",
  "shell.home": "Inicio",
  "shell.breadcrumb": "Ruta de navegación",
  "shell.activeOrg": "Organización activa",
  "shell.activeOrgAria": "Organización activa en la barra",
  "shell.loadingOrg": "Cargando organización…",
  "shell.orgError": "Error: organización no disponible.",
  "shell.retryOrgs": "Reintentar organizaciones",
  "shell.noOrgs": "Sin organizaciones.",
  "shell.loadingUser": "Cargando usuario…",
  "shell.account": "Cuenta",
  "shell.loadingSession": "Cargando sesión…",
  "shell.closingSession": "Cerrando sesión…",
  "shell.logout": "Cerrar sesión",
  "shell.login": "Iniciar sesión",
  "shell.sessionError": "No se pudo cargar la sesión.",
  "shell.orgsError": "No se pudieron cargar las organizaciones.",
  "shell.logoutNotice": "Sesión cerrada.",
  "shell.logoutError": "No se pudo cerrar la sesión.",
  "shell.errorPrefix": "Error: ",
  "shell.navWorkspace": "Navegación del workspace",
  "shell.workspaceSpace": "Espacio de trabajo",
  "shell.navSections": "Secciones del workspace",
  "shell.hideMenu": "Ocultar menú",
  "shell.showMenu": "Mostrar menú",
  "shell.navMobile": "Navegación móvil del workspace",
  "shell.footerTagline": "TalentOS · reclutamiento asistido, trazable y supervisado.",
  "shell.footerLinks": "Enlaces del workspace",
  "shell.homeLink": "Portada",
  "shell.panel": "Panel",
  "shell.organization": "Organización",
  "shell.members": "Miembros",
  "shell.recruitment": "Núcleo de selección",
  "shell.analytics": "Analítica",
  "shell.assessment": "Evaluación",
  "shell.agents": "Agentes",
  "shell.pipeline": "Pipeline",
  "shell.candidates": "Candidatos",
  "shell.automations": "Automatizaciones",
  "shell.documents": "Documentos",
  "shell.integrations": "Integraciones",
  "shell.interviews": "Entrevistas",
  "shell.jobs": "Vacantes",
  "shell.privacy": "Privacidad",
  "shell.terms": "Términos",
  "cmd.trigger": "Buscar sección…",
  "cmd.aria": "Buscar sección",
  "cmd.filter": "Filtrar secciones",
  "cmd.empty": "Sin resultados.",
  "cmd.hint.panel": "Resumen de la organización",
  "cmd.hint.jobs": "Requisitos y etapas",
  "cmd.hint.candidates": "Perfiles y evidencia",
  "cmd.hint.pipeline": "Postulaciones por etapa",
  "cmd.hint.documents": "Archivos privados",
  "cmd.hint.assessment": "Criterios y brechas",
  "cmd.hint.interviews": "Agenda y guiones",
  "cmd.hint.agents": "Ejecuciones y traza",
  "cmd.hint.automations": "Reglas y aprobaciones",
  "cmd.hint.integrations": "Adaptadores y entregas",
  "cmd.hint.analytics": "Métricas del proceso",
  "jobs.title": "Listado de vacantes",
  "jobs.filter.status": "Estado",
  "jobs.filter.all": "Todos",
  "jobs.total": "Total:",
  "jobs.loading": "Cargando vacantes…",
  "jobs.loadError": "No se pudieron cargar las vacantes.",
  "jobs.empty": "No hay vacantes para este filtro.",
  "jobs.caption": "Vacantes de la organización activa",
  "jobs.col.title": "Título",
  "jobs.col.status": "Estado",
  "jobs.col.modality": "Modalidad",
  "jobs.col.location": "Ubicación",
  "jobs.col.owner": "Responsable",
  "jobs.col.action": "Acción",
  "jobs.select": "Seleccionar",
  "jobs.selectAria": "Seleccionar vacante",
  "jobs.previous": "Anterior",
  "jobs.next": "Siguiente",
  "jobs.form.title": "Alta de vacante",
};

const en: typeof es = {
  "nav.producto": "Product",
  "nav.metodo": "Method",
  "nav.evidencia": "Evidence",
  "nav.acceso": "Sign in",
  "nav.empezar": "Get started",
  "locale.toEn": "Switch to English",
  "locale.toEs": "Switch to Spanish",
  "hero.eyebrow": "For teams that hire with judgment",
  "hero.title": "Hiring decisions backed by evidence, not gut feeling.",
  "hero.body":
    "TalentOS brings jobs, candidates and assessments into one calm surface. Every criterion shows its source, its gaps and who approved the action.",
  "hero.cta": "Create account",
  "hero.secondary": "Open dashboard",
  "hero.note":
    "No inference of protected attributes. No external action runs without human approval.",
  "hero.pipeline": "Pipeline · product view",
  "hero.synthetic": "Synthetic data",
  "hero.pipelineNote":
    "Each card opens criteria, evidence with page and excerpt, and the action awaiting approval.",
  "stats.evidence": "Evidence states",
  "stats.evidenceDetail": "Each with its own label and meaning.",
  "stats.human": "Final word",
  "stats.humanValue": "Human",
  "stats.humanDetail": "AI proposes; a person approves.",
  "stats.automatic": "Automatic external actions",
  "stats.automaticDetail": "Every sensitive output stays pending.",
  "capabilities.eyebrow": "Product",
  "capabilities.title": "One surface for the whole journey",
  "capabilities.body":
    "Fewer tabs, more context. Each module answers a concrete recruiter decision.",
  "capabilities.jobs.title": "Jobs with criteria",
  "capabilities.jobs.body":
    "Define explicit requirements and keep every change traceable by organization.",
  "capabilities.jobs.action": "View jobs",
  "capabilities.evidence.title": "Verifiable evidence",
  "capabilities.evidence.body":
    "Document, page and excerpt per requirement. Gaps and absences stated without filler.",
  "capabilities.evidence.action": "View assessment",
  "capabilities.trace.title": "Decision trail",
  "capabilities.trace.body":
    "Runs, tools and pending approvals visible in the same place.",
  "capabilities.trace.action": "View trail",
  "steps.eyebrow": "Method",
  "steps.title": "From criterion to decision, no blind jumps",
  "steps.one.title": "Prepare the job",
  "steps.one.body": "Collect criteria, role and stages before opening the pipeline.",
  "steps.two.title": "Check evidence",
  "steps.two.body": "Review each requirement against its source and flag what needs review.",
  "steps.three.title": "Decide and leave a trail",
  "steps.three.body": "Every external action waits for human approval and is recorded.",
  "evidence.eyebrow": "Evidence",
  "evidence.title": "Missing evidence is shown too",
  "evidence.body":
    "All four states have distinct text and shape. None relies on color alone.",
  "evidence.supported": "Direct evidence",
  "evidence.partial": "Partial evidence",
  "evidence.notFound": "No evidence",
  "evidence.needsReview": "Human review",
  "pipeline.review": "To review",
  "pipeline.reviewDetail": "Synthetic candidate · evidence pending",
  "pipeline.interview": "In interview",
  "pipeline.interviewDetail": "Proof of concept · demo data",
  "pipeline.decision": "Ready for decision",
  "pipeline.decisionDetail": "Human approval required",
  "footer.tagline": "Assisted, traceable and supervised hiring. Local demo with synthetic data.",
  "footer.access": "Access",
  "footer.login": "Sign in",
  "footer.register": "Register",
  "footer.dashboard": "Dashboard",
  "footer.environment": "Environment status",
  "footer.note": "TalentOS · demo interface · no real personal data.",
  "shell.workspace": "Workspace",
  "shell.home": "Home",
  "shell.breadcrumb": "Breadcrumb",
  "shell.activeOrg": "Active organization",
  "shell.activeOrgAria": "Active organization in header",
  "shell.loadingOrg": "Loading organization…",
  "shell.orgError": "Error: organization unavailable.",
  "shell.retryOrgs": "Retry organizations",
  "shell.noOrgs": "No organizations.",
  "shell.loadingUser": "Loading user…",
  "shell.account": "Account",
  "shell.loadingSession": "Loading session…",
  "shell.closingSession": "Signing out…",
  "shell.logout": "Sign out",
  "shell.login": "Sign in",
  "shell.sessionError": "Could not load the session.",
  "shell.orgsError": "Could not load organizations.",
  "shell.logoutNotice": "Session closed.",
  "shell.logoutError": "Could not sign out.",
  "shell.errorPrefix": "Error: ",
  "shell.navWorkspace": "Workspace navigation",
  "shell.workspaceSpace": "Workspace",
  "shell.navSections": "Workspace sections",
  "shell.hideMenu": "Hide menu",
  "shell.showMenu": "Show menu",
  "shell.navMobile": "Mobile workspace navigation",
  "shell.footerTagline": "TalentOS · assisted, traceable and supervised hiring.",
  "shell.footerLinks": "Workspace links",
  "shell.homeLink": "Home",
  "shell.panel": "Dashboard",
  "shell.organization": "Organization",
  "shell.members": "Members",
  "shell.recruitment": "Recruitment core",
  "shell.analytics": "Analytics",
  "shell.assessment": "Assessment",
  "shell.agents": "Agents",
  "shell.pipeline": "Pipeline",
  "shell.candidates": "Candidates",
  "shell.automations": "Automations",
  "shell.documents": "Documents",
  "shell.integrations": "Integrations",
  "shell.interviews": "Interviews",
  "shell.jobs": "Jobs",
  "shell.privacy": "Privacy",
  "shell.terms": "Terms",
  "cmd.trigger": "Search section…",
  "cmd.aria": "Search section",
  "cmd.filter": "Filter sections",
  "cmd.empty": "No results.",
  "cmd.hint.panel": "Organization overview",
  "cmd.hint.jobs": "Requirements and stages",
  "cmd.hint.candidates": "Profiles and evidence",
  "cmd.hint.pipeline": "Applications by stage",
  "cmd.hint.documents": "Private files",
  "cmd.hint.assessment": "Criteria and gaps",
  "cmd.hint.interviews": "Schedule and scripts",
  "cmd.hint.agents": "Runs and trace",
  "cmd.hint.automations": "Rules and approvals",
  "cmd.hint.integrations": "Adapters and deliveries",
  "cmd.hint.analytics": "Process metrics",
  "jobs.title": "Job list",
  "jobs.filter.status": "Status",
  "jobs.filter.all": "All",
  "jobs.total": "Total:",
  "jobs.loading": "Loading jobs…",
  "jobs.loadError": "Could not load jobs.",
  "jobs.empty": "No jobs for this filter.",
  "jobs.caption": "Jobs in the active organization",
  "jobs.col.title": "Title",
  "jobs.col.status": "Status",
  "jobs.col.modality": "Modality",
  "jobs.col.location": "Location",
  "jobs.col.owner": "Owner",
  "jobs.col.action": "Action",
  "jobs.select": "Select",
  "jobs.selectAria": "Select job",
  "jobs.previous": "Previous",
  "jobs.next": "Next",
  "jobs.form.title": "Create job",
};

const messages: Record<Locale, typeof es> = { es, en };

export type MessageKey = keyof typeof es;

type I18nValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: (key: MessageKey) => string;
};

const I18nContext = createContext<I18nValue>({
  locale: "es",
  setLocale: () => undefined,
  toggleLocale: () => undefined,
  t: (key) => es[key],
});

export function LocaleProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [locale, setLocale] = useState<Locale>("es");

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "es" || saved === "en") {
      queueMicrotask(() => setLocale(saved));
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nValue>(
    () => ({
      locale,
      setLocale,
      toggleLocale: () => setLocale((current) => (current === "es" ? "en" : "es")),
      t: (key) => messages[locale][key],
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}

export function LocaleToggle() {
  const { locale, toggleLocale, t } = useI18n();
  const label = locale === "es" ? t("locale.toEn") : t("locale.toEs");

  return (
    <button
      type="button"
      onClick={toggleLocale}
      aria-label={label}
      title={label}
      className="rounded-md border border-border-subtle px-2 py-1 text-xs font-semibold text-text-muted transition-colors hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      {locale === "es" ? "EN" : "ES"}
    </button>
  );
}
