/** DTOs espejo de los schemas Pydantic de `/api/v1` (Fase 2). */

export type UserStatus = "active" | "inactive";

export type MembershipRole =
  | "owner"
  | "admin"
  | "recruiter"
  | "reviewer"
  | "viewer";

/** UserResponse: devuelto por register, login y logout. */
export interface User {
  id: string;
  email: string;
  name: string;
  status: UserStatus;
}

/** Login/register devuelven UserResponse; la sesión vive en cookie HttpOnly. */
export type AuthResponse = User;

export type OnboardingStep = "create_organization" | "accept_invitation" | "complete";

export interface OnboardingStatus {
  step: OnboardingStep;
}

/** MeResponse: UserResponse más el resumen de organizaciones del backend. */
export interface MeResponse extends User {
  organizations: Array<Record<string, string>>;
  onboarding: OnboardingStatus;
}

/** OrganizationResponse. */
export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

/** MemberResponse. */
export interface Member {
  user_id: string;
  email: string;
  name: string;
  role: MembershipRole;
}

/** Cuerpos de entrada aceptados por el backend. */
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  accept_privacy?: boolean;
}

/** Recuperación de contraseña y respuestas demo sin SMTP. */
export interface PasswordResetRequest {
  email: string;
  accept_privacy?: boolean;
}

export interface PasswordResetConfirm {
  token: string;
  password: string;
  accept_privacy?: boolean;
}

export interface MessageResponse {
  message: string;
}

export interface PasswordResetRequestResponse extends MessageResponse {
  dev_token: string | null;
}

export interface InvitationCreateResponse extends MessageResponse {
  dev_token: string | null;
}

export interface InvitationDetailResponse {
  organization_name: string;
  email: string;
  role: MembershipRole;
  expires_at: string;
}

export interface InvitationAcceptResponse {
  organization_id: string;
  organization_name: string;
  role: MembershipRole;
}

export interface MemberInvite {
  email: string;
  role: MembershipRole;
}

export interface MemberRoleUpdate {
  role: MembershipRole;
}

/** Envelope de error uniforme del backend. */
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}

/** DTOs espejo de los schemas Pydantic de Fase 3 (Recruitment Core). */

export type JobStatus = "draft" | "open" | "paused" | "closed" | "archived";

export type RequirementCategory =
  | "skill"
  | "experience"
  | "education"
  | "language"
  | "certification"
  | "other";

export type RequirementImportance = "required" | "desirable";

export type CandidateProfileStatus = "draft" | "review" | "confirmed" | "archived";

export type ApplicationStage =
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "hired"
  | "rejected";

export type ApplicationSource = "manual" | "import" | "referral" | "careers";

/** Envelope de listado con paginación devuelto por los tres recursos. */
export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Job {
  id: string;
  title: string;
  description: string;
  status: JobStatus;
  modality: string | null;
  location: string | null;
  seniority: string | null;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

export interface JobCreate {
  title: string;
  description: string;
  modality: string | null;
  location: string | null;
  seniority: string | null;
  owner_id: string;
}

export interface JobRequirement {
  id: string;
  job_id: string;
  category: RequirementCategory;
  description: string;
  importance: RequirementImportance;
  expected_level: string | null;
  acceptable_evidence: string[];
  weight: number;
  weight_justification: string;
  created_at: string;
  updated_at: string;
}

export interface RequirementCreate {
  category: RequirementCategory;
  description: string;
  importance: RequirementImportance;
  weight: number;
  weight_justification: string;
}

export interface JobVersion {
  id: string;
  job_id: string;
  version: number;
  snapshot: Record<string, unknown>;
  created_at: string;
}

export type JobList = Paginated<Job>;
export type RequirementList = JobRequirement[];
export type JobVersionList = JobVersion[];

export interface Candidate {
  id: string;
  name: string;
  email: string;
  location: string | null;
  profile_status: CandidateProfileStatus;
  created_at: string;
  updated_at: string;
}

export interface CandidateCreate {
  name: string;
  email: string;
  location: string | null;
}

export interface Note {
  id: string;
  candidate_id: string;
  author_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface ActivityEntry {
  id: string;
  action: string;
  actor_id: string | null;
  resource_type: string;
  resource_id: string;
  timestamp: string;
}

export type CandidateList = Paginated<Candidate>;
export type NoteList = Note[];
export type ActivityList = ActivityEntry[];

export interface Application {
  id: string;
  job_id: string;
  candidate_id: string;
  stage: ApplicationStage;
  source: ApplicationSource | null;
  created_at: string;
  updated_at: string;
}

export interface StageChange {
  id: string;
  application_id: string;
  from_stage: ApplicationStage | null;
  to_stage: ApplicationStage;
  actor_id: string | null;
  note: string | null;
  created_at: string;
}

export interface StageChangeRequest {
  to_stage: ApplicationStage;
  note?: string;
}

export type ApplicationList = Paginated<Application>;
export type StageChangeList = StageChange[];

/** Documentos privados: el backend nunca devuelve rutas internas ni el CV crudo. */
export interface Document {
  id: string;
  candidate_id: string;
  original_filename: string;
  content_type: string;
  extension: string;
  size_bytes: number;
  checksum_sha256: string;
  status: "uploaded" | "processing" | "processed" | "failed";
  page_count: number | null;
  created_at: string;
}

export type ExtractedFieldName =
  | "name"
  | "email"
  | "location"
  | "experience"
  | "education"
  | "skills"
  | "projects"
  | "languages";

export type ExtractedFieldStatus =
  | "extracted"
  | "needs_review"
  | "missing"
  | "confirmed"
  | "corrected";

export interface EvidenceRef {
  document_id: string;
  page: number;
  quote: string;
  offset: number | null;
}

export interface ExtractionField {
  id: string;
  field_name: ExtractedFieldName;
  value: unknown;
  status: ExtractedFieldStatus;
  evidence: EvidenceRef[];
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface Extraction {
  id: string;
  document_id: string;
  provider: string;
  model: string;
  prompt_version: string;
  status: "pending" | "completed" | "failed";
  injection_detected: boolean;
  review_required: boolean;
  fields: ExtractionField[];
  created_at: string;
  updated_at: string;
}

export interface ReviewResult {
  field_id: string;
  field_name: ExtractedFieldName;
  status: ExtractedFieldStatus;
  value: unknown;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface ReviewSummary {
  document_id: string;
  extraction_id: string;
  confirmed: number;
  corrected: number;
  needs_review: number;
  pending: number;
  total: number;
  review_required: boolean;
  injection_detected: boolean;
}

/** DTOs espejo de los schemas Pydantic de Fase 5 (assessment). Sin score. */

export type AssessmentStatus = "pending" | "completed" | "failed" | "needs_review";

export type RequirementEvaluationStatus =
  | "supported"
  | "partial"
  | "not_found"
  | "needs_review";

export interface AssessmentEvidenceRef {
  document_id: string;
  field_name: string;
  page: number;
  quote: string;
  offset: number | null;
}

export interface AssessmentSummary {
  strengths: string[];
  gaps: string[];
  questions: string[];
}

export interface RequirementEvaluation {
  id: string;
  requirement_id: string;
  status: RequirementEvaluationStatus;
  explanation: string;
  evidence: AssessmentEvidenceRef[];
  limitations: string[];
  review_required: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface Assessment {
  id: string;
  application_id: string;
  job_version_id: string;
  candidate_id: string;
  status: AssessmentStatus;
  model_version: string;
  prompt_version: string;
  summary: AssessmentSummary;
  limitations: string[];
  evaluations: RequirementEvaluation[];
  review_required: boolean;
  created_at: string;
}

export type AssessmentList = Paginated<Assessment>;

export interface RunAssessmentRequest {
  application_id: string;
}

export interface ReviewDecision {
  status: RequirementEvaluationStatus;
  explanation: string | null;
}

export interface StatusChange {
  before: RequirementEvaluationStatus | null;
  after: RequirementEvaluationStatus | null;
  changed: boolean;
}

export interface ExplanationChange {
  before: string | null;
  after: string | null;
  changed: boolean;
}

export interface EvidenceRefsChange {
  before: AssessmentEvidenceRef[];
  after: AssessmentEvidenceRef[];
  changed: boolean;
}

export interface ReviewRequiredChange {
  before: boolean | null;
  after: boolean | null;
  changed: boolean;
}

export interface RequirementComparison {
  requirement_id: string;
  status: StatusChange;
  explanation: ExplanationChange;
  evidence_refs: EvidenceRefsChange;
  review_required: ReviewRequiredChange;
}

export interface ComparisonVersion {
  assessment_id: string;
  status: AssessmentStatus;
  model_version: string;
  prompt_version: string;
}

export interface AssessmentComparison {
  base: ComparisonVersion;
  target: ComparisonVersion;
  changes: RequirementComparison[];
}

/** DTOs espejo de `/api/v1/agents` (Fase 6). Sin puntajes ni decisiones automáticas. */

export type AgentRunStatus =
  | "pending"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out";

export type ApprovalStatus = "pending" | "approved" | "rejected";

export type AgentEventType =
  | "run.created"
  | "run.started"
  | "run.waiting_approval"
  | "run.completed"
  | "run.failed"
  | "run.cancelled"
  | "run.timed_out"
  | "approval.requested"
  | "approval.resolved"
  | "graph.interrupted"
  | "checkpoint.saved"
  | "tool.invoked";

export interface AgentRunSummary {
  id: string;
  workflow: string;
  version: string;
  status: AgentRunStatus;
  correlation_id: string;
  created_at: string;
  updated_at: string;
  output_ref: string | null;
  job_id: string | null;
  candidate_id: string | null;
}

export interface AgentEventSummary {
  event_type: AgentEventType;
  count: number;
}

/** Detalle devuelto por POST/GET /runs; `review_required` se deriva del estado servidor. */
export interface AgentRun extends AgentRunSummary {
  event_summary: AgentEventSummary[];
  event_count: number;
  duration_ms?: number;
  configured_provider?: string;
  configured_model?: string | null;
}

export type AgentRunDetail = AgentRun;
export type AgentRunList = Paginated<AgentRunSummary>;

/** Payload saneado por backend: solo metadatos, nunca CV, secretos ni rutas internas. */
export interface AgentEvent {
  event_type: AgentEventType;
  created_at: string;
  correlation_id: string;
  payload: Record<string, unknown>;
}

export type AgentEventList = Paginated<AgentEvent>;

export interface Approval {
  id: string;
  action_type: string;
  status: ApprovalStatus;
  created_at: string;
  decided_at: string | null;
}

export interface AgentRunStart {
  application_id: string;
  idempotency_key: string;
  correlation_id?: string;
}

export interface AgentApprovalDecision {
  decision: Exclude<ApprovalStatus, "pending">;
  note?: string | null;
}

export interface AgentResumeResponse {
  agent_run_id: string;
  status: AgentRunStatus;
  queued: boolean;
  correlation_id: string;
}

/** DTOs espejo de `/api/v1/interviews` (Fase 7). Sin score ni decisión de contratación. */

export type InterviewGuideStatus = "draft" | "published" | "archived";
export type InterviewQuestionCategory = "technical" | "deep_dive";
export type InterviewQuestionStatus = "draft" | "approved" | "rejected" | "archived";
export type InterviewFeedbackStatus = "pending" | "submitted" | "needs_review";

export interface InterviewQuestion {
  id: string;
  requirement_id: string;
  category: InterviewQuestionCategory;
  question: string;
  evidence_focus: string;
  competency: string;
  status: InterviewQuestionStatus;
  position: number;
  review_required: boolean;
  model_version: string;
  prompt_version: string;
}

export interface InterviewGuideSummary {
  id: string;
  application_id: string;
  title: string;
  status: InterviewGuideStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface InterviewGuideDetail extends InterviewGuideSummary {
  job_version_id: string | null;
  model_version: string | null;
  prompt_version: string | null;
  limitations: string[];
  review_required: boolean;
  needs_review: boolean;
  questions: InterviewQuestion[];
}

export type InterviewGuideList = Paginated<InterviewGuideSummary>;

export interface GuideGeneration {
  guide_id: string;
  application_id: string;
  version: number;
  status: InterviewGuideStatus;
  model_version: string;
  prompt_version: string;
  job_version_id: string | null;
  questions: InterviewQuestion[];
  rejected_questions: InterviewQuestion[];
  limitations: string[];
  review_required: boolean;
  needs_review: boolean;
  created: boolean;
}

export interface GenerateGuideRequest {
  application_id: string;
}

export interface InterviewGuideUpdate {
  title?: string;
  status?: InterviewGuideStatus;
}

export interface InterviewQuestionCreateRequest {
  requirement_id: string;
  position: number;
  category: InterviewQuestionCategory;
  question: string;
  evidence_focus: string;
  competency: string;
  review_required: boolean;
  model_version: string;
  prompt_version: string;
}

export interface InterviewQuestionUpdateRequest {
  question?: string;
  evidence_focus?: string;
  competency?: string;
  position?: number;
  status?: InterviewQuestionStatus;
}

export interface InterviewFeedback {
  id: string;
  question_id: string;
  requirement_id: string;
  interviewer_id: string;
  status: InterviewFeedbackStatus;
  observed_evidence: string[];
  gaps: string[];
  follow_up_needed: boolean;
  notes: string | null;
  submitted_at: string | null;
  created_at: string;
}

export type InterviewFeedbackList = Paginated<InterviewFeedback>;

export interface InterviewFeedbackSubmitRequest {
  observed_evidence: string[];
  gaps: string[];
  follow_up_needed: boolean;
  notes?: string | null;
}

export interface GuideRevision {
  id: string;
  version: number;
  created_by: string;
  created_at: string;
  snapshot: Record<string, unknown>;
}

export type GuideRevisionList = Paginated<GuideRevision>;

/** El backend añade `reason_code` a los 422 de política; `apiFetch` sólo expone code/message. */
export interface PolicyErrorEnvelope {
  error: ErrorEnvelope["error"] & { reason_code?: string };
}

/** DTOs espejo de `/api/v1/automations` (Fase 8). Sin score ni decisión automática. */

export type AutomationStatus = "draft" | "active" | "inactive" | "archived";
export type AutomationTriggerEventType = "application.stage_changed";
export type AutomationConditionField = "to_stage" | "from_stage" | "job_status";
export type AutomationConditionOperator = "eq" | "neq" | "in";

export type AutomationActionType =
  | "create_task"
  | "create_message_draft"
  | "request_approval"
  | "record_note"
  | "propose_stage_change"
  | "run_authorized_analysis";

export type AutomationRunMode = "test" | "live";
export type AutomationRunStatus =
  | "pending"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out";

export type AutomationRunEventType =
  | "trigger_matched"
  | "condition_evaluated"
  | "action_planned"
  | "action_executed"
  | "approval_requested"
  | "approval_resolved"
  | "retry_scheduled"
  | "completed"
  | "failed"
  | "cancelled"
  | "dry_run";

export type AutomationApprovalStatus = "pending" | "approved" | "rejected";

export interface AutomationCondition {
  field: AutomationConditionField;
  operator: AutomationConditionOperator;
  value: string | string[];
}

export interface AutomationActionPayload {
  template_id: string | null;
  note: string | null;
  target_stage: ApplicationStage | null;
}

export interface AutomationAction {
  type: AutomationActionType;
  payload: AutomationActionPayload;
}

export interface AutomationTrigger {
  event_type: AutomationTriggerEventType;
}

export interface AutomationVersionCreate {
  trigger: AutomationTrigger;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
}

export interface AutomationSnapshot {
  trigger: Record<string, unknown>;
  conditions: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
  created_at: string | null;
}

export interface AutomationSummary {
  id: string;
  name: string;
  status: AutomationStatus;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface AutomationDetail extends AutomationSummary {
  active_version: AutomationSnapshot | null;
}

export interface AutomationVersionResult {
  id: string;
  automation_id: string;
  version: number;
  created_at: string;
}

export type AutomationList = Paginated<AutomationSummary>;

export interface AutomationCreateRequest {
  name: string;
}

export interface AutomationStatusUpdate {
  status: AutomationStatus;
}

export interface AutomationExecutionRequest {
  application_id: string;
  idempotency_key: string;
  correlation_id?: string | null;
}

export interface AutomationDecisionRequest {
  decision: Exclude<AutomationApprovalStatus, "pending">;
  note?: string | null;
}

export interface AutomationEventCount {
  event_type: AutomationRunEventType;
  count: number;
}

export interface AutomationTestResult {
  id: string;
  automation_id: string;
  status: AutomationRunStatus;
  mode: AutomationRunMode;
  correlation_id: string;
  event_summary: AutomationEventCount[];
}

export interface AutomationRunSummary {
  id: string;
  automation_id: string;
  version: number;
  mode: AutomationRunMode;
  status: AutomationRunStatus;
  correlation_id: string;
  trigger_event_type: string;
  error_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationRunDetail extends AutomationRunSummary {
  started_at: string | null;
  finished_at: string | null;
  draft_ids: string[];
  approval_ids: string[];
}

export type AutomationRunList = Paginated<AutomationRunSummary>;

export interface AutomationRunEvent {
  event_type: AutomationRunEventType;
  created_at: string;
  correlation_id: string;
  payload: Record<string, unknown>;
}

export type AutomationRunEventList = Paginated<AutomationRunEvent>;

export interface AutomationApproval {
  id: string;
  action_type: AutomationActionType;
  status: AutomationApprovalStatus;
  created_at: string;
  decided_at: string | null;
}

export interface AutomationApprovalDecisionResult {
  id: string;
  run_id: string;
  action_type: AutomationActionType;
  status: AutomationApprovalStatus;
  decided_by: string | null;
  decided_at: string | null;
  run_status: AutomationRunStatus;
}

export interface AutomationRunQueueResult {
  id: string;
  status: AutomationRunStatus;
  queued: boolean;
  correlation_id: string;
}

/** DTOs espejo de `/api/v1/integrations` (Fase 9): sin config, token ni secreto. */

export type IntegrationProvider = "email_sandbox" | "webhook_outbound" | "webhook_inbound";
export type IntegrationStatus = "active" | "disabled";

export type WebhookEventType =
  | "candidate.created"
  | "document.uploaded"
  | "document.extraction.completed"
  | "application.stage_changed"
  | "assessment.completed"
  | "approval.requested"
  | "approval.resolved";

export type WebhookDeliveryStatus =
  | "pending"
  | "sending"
  | "delivered"
  | "failed"
  | "dead_letter";

export type EmailTemplate = "initial_contact" | "interview_invite" | "follow_up";
export type EmailLanguage = "es" | "en";
export type EmailApprovalStatus = "pending" | "approved" | "rejected";
export type EmailDeliveryStatus = "not_sent" | "sent" | "failed";

export interface IntegrationSummary {
  id: string;
  provider: IntegrationProvider;
  status: IntegrationStatus;
  config_version: number;
  key_id: string;
  created_at: string;
  updated_at: string;
}

export type IntegrationList = Paginated<IntegrationSummary>;

export interface WebhookDelivery {
  id: string;
  event_id: string;
  event_type: WebhookEventType;
  status: WebhookDeliveryStatus;
  attempts: number;
  last_error_code: string | null;
  last_status_code: number | null;
  created_at: string;
  delivered_at: string | null;
}

export type WebhookDeliveryList = Paginated<WebhookDelivery>;

export interface EmailDraft {
  id: string;
  candidate_id: string;
  template: EmailTemplate;
  approval_status: EmailApprovalStatus;
  delivery_status: EmailDeliveryStatus;
  attempts: number;
  created_at: string;
}

export interface EmailDraftDetail extends EmailDraft {
  integration_id: string;
  topic: string;
  language: EmailLanguage;
  call_to_action: string;
  subject: string;
  body_hash: string;
  requested_by: string | null;
  decided_by: string | null;
  decided_at: string | null;
  last_error_code: string | null;
  sent_at: string | null;
  updated_at: string;
}

export type EmailDraftList = Paginated<EmailDraft>;
