import { auth } from "@/auth";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const { pathname } = req.nextUrl;

  const publicPaths = ["/login", "/register", "/forgot-password"];
  const isPublic = publicPaths.some(p => pathname.startsWith(p));
  const isApi = pathname.startsWith("/api");

  if (!isLoggedIn && !isPublic && !isApi) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  if (isLoggedIn && isPublic) {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
