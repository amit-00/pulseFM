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
      credentials: {
        name: { label: "Name", type: "text" },
      },
      authorize(credentials) {
        const name = typeof credentials?.name === "string" ? credentials.name.trim() : "";
        if (!name) {
          return null;
        }
        return {
          id: crypto.randomUUID(),
          name,
        };
      },
    }),
  ],
  callbacks: {
    jwt({ token, user, trigger, session }) {
      if (user?.id) {
        token.sub = user.id;
      }
      if (user?.name) {
        token.name = user.name;
      }
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
      if (session.user) {
        session.user.name = typeof token.name === "string" ? token.name : session.user.name;
      }
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
