import { NextResponse, type NextRequest } from "next/server";

const TOKEN_COOKIE = "oneflow_token";

/**
 * Route protection:
 *  - Guests hitting /dashboard/* are redirected to /login (with a `next` param).
 *  - Authenticated users hitting /login or /register are sent to /dashboard.
 *
 * Token validity is re-checked client-side (AuthGuard + /auth/me); an invalid
 * cookie is cleared there, so this only performs the fast presence check.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasToken = Boolean(request.cookies.get(TOKEN_COOKIE)?.value);

  const isDashboard = pathname.startsWith("/dashboard");
  const isAuthPage = pathname === "/login" || pathname === "/register";

  if (isDashboard && !hasToken) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (isAuthPage && hasToken) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register"],
};
