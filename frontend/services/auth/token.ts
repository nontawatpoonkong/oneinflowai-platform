/**
 * JWT storage via a cookie so that Next.js middleware can guard routes and
 * Axios can attach the token. The cookie is non-httpOnly (readable by JS);
 * moving to an httpOnly cookie is a future hardening that requires the backend
 * to set the cookie directly.
 */
export const TOKEN_COOKIE = "oneflow_token";

const REMEMBER_MAX_AGE = 60 * 60 * 24 * 30; // 30 days

export function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${TOKEN_COOKIE}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

export function setToken(token: string, remember = false): void {
  if (typeof document === "undefined") return;
  const secure = location.protocol === "https:" ? "; Secure" : "";
  const maxAge = remember ? `; max-age=${REMEMBER_MAX_AGE}` : "";
  document.cookie = `${TOKEN_COOKIE}=${encodeURIComponent(token)}; path=/; SameSite=Lax${maxAge}${secure}`;
}

export function clearToken(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}
