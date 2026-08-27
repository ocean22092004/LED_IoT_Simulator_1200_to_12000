export type UserRole = "STAFF" | "TECHNICIAN" | "ADMIN";

export type AuthUser = {
  id: string;
  username: string;
  role: UserRole;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
};

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
};
