import type { NextAuthConfig } from "next-auth";
import { SignJWT } from "jose";

export const authConfig = {
  session: { strategy: "jwt" },
  providers: [],
  pages: {
    signIn: "/login",
    error: "/login",
  },
  callbacks: {
    async jwt({ token, user }) {
      // On initial sign-in, populate userId and email from the user object
      if (user) {
        token.userId = user.id;
        token.email = user.email;
      }

      // ALWAYS re-sign the accessToken from the current token's userId.
      // This prevents stale tokens from a previous account persisting across logins.
      // If userId is somehow missing, sign-out immediately.
      if (!token.userId) {
        return { ...token, error: "MissingUserIdError" };
      }

      const secret = new TextEncoder().encode(process.env.NEXTAUTH_SECRET);
      token.accessToken = await new SignJWT({ userId: token.userId, email: token.email })
        .setProtectedHeader({ alg: "HS256" })
        .setExpirationTime("1d")  // Short expiry; re-signed on every session refresh
        .sign(secret);

      return token;
    },
    async session({ session, token }) {
      if (token.userId) {
        session.user.id = token.userId as string;
        session.accessToken = token.accessToken as string;
      }
      return session;
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
} satisfies NextAuthConfig;
