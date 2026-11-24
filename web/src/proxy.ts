/**
 * Optimistic auth redirect (Next 16 "Proxy", formerly middleware). It only checks that a session
 * cookie EXISTS; the API does the real check on every call (AUTH-3). Role-based routing happens in
 * the shells via useMe() + homePathFor().
 */
import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "forte_session";

export function proxy(request: NextRequest) {
  if (!request.cookies.has(SESSION_COOKIE)) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/admin/:path*",
    "/payroll/:path*",
    "/employees/:path*",
    "/timesheets/:path*",
    "/corrections/:path*",
    "/me/:path*",
    "/setup",
  ],
};
