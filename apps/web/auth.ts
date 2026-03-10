import { randomUUID } from "node:crypto";
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

declare module "next-auth/jwt" {
  interface JWT {
    lastVoteId?: string;
    lastVoteOption?: string;
  }
}

declare module "next-auth" {
  interface Session {
    lastVoteId?: string;
    lastVoteOption?: string;
  }
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  trustHost: true,
  session: {
    strategy: "jwt",
  },

  providers: [
    Credentials({
      name: "Anonymous",
      credentials: {},
      authorize() {
        return { id: randomUUID() };
      },
    }),
  ],

  callbacks: {
    jwt({ token, trigger, session }) {
      // Persist vote state when the session is updated via unstable_update
      if (trigger === "update" && session) {
        if (typeof session.lastVoteId === "string") {
          token.lastVoteId = session.lastVoteId;
        }
        if (typeof session.lastVoteOption === "string") {
          token.lastVoteOption = session.lastVoteOption;
        }
      }
      return token;
    },
    session({ session, token }) {
      if (token.lastVoteId) {
        session.lastVoteId = token.lastVoteId;
      }
      if (token.lastVoteOption) {
        session.lastVoteOption = token.lastVoteOption;
      }
      return session;
    },
  },
});
