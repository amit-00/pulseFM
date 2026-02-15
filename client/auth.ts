import { randomUUID } from "node:crypto";
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

export const { handlers, signIn, signOut, auth } = NextAuth({
  trustHost: true,
  session: {
    strategy: "jwt",
  },
  providers: [
    Credentials({
      name: "Anonymous",
      credentials: {
        name: { label: "Name", type: "text" },
      },
      authorize(credentials) {
        const name = typeof credentials?.name === "string" ? credentials.name.trim() : "";
        if (!name) {
          return null;
        }
        return {
          id: randomUUID(),
          name,
        };
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user?.id) {
        token.sub = user.id;
      }
      if (user?.name) {
        token.name = user.name;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        session.user.name = typeof token.name === "string" ? token.name : session.user.name;
      }
      return session;
    },
  },
});
