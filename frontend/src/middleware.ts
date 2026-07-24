import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

const { auth } = NextAuth(authConfig);

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const { pathname } = req.nextUrl;

  const publicPaths = ["/login", "/register", "/forgot-password"];
  const isPublic = publicPaths.some(p => pathname.startsWith(p));
  const isApi = pathname.startsWith("/api");

  if (!isLoggedIn && !isPublic && !isApi) {
    return Response.redirect(new URL("/login", req.url));
  }
  if (isLoggedIn && isPublic) {
    return Response.redirect(new URL("/dashboard", req.url));
  }
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
