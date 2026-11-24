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

/** MeResponse: UserResponse más el resumen de organizaciones del backend. */
export interface MeResponse extends User {
  organizations: Array<Record<string, string>>;
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
