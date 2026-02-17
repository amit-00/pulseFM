import { NextResponse } from "next/server";
import { signIn } from "@/auth";

export const runtime = "nodejs";

export async function POST(request: Request) {
  let body: { name?: unknown } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const providedName = typeof body.name === "string" ? body.name.trim() : "";
  const name = providedName || `listener-${Math.random().toString(36).slice(2, 8)}`;
  try {
    const result = await signIn("credentials", {
      name,
      redirect: false,
    });
    if (result?.error) {
      return NextResponse.json({ error: "Invalid session bootstrap request" }, { status: 401 });
    }
    return NextResponse.json({ status: "ok" });
  } catch {
    return NextResponse.json({ error: "Failed to create session" }, { status: 500 });
  }
}
