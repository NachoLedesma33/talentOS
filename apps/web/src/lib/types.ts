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
