import { NextResponse } from "next/server";
import { signIn } from "@/auth";

export async function POST(request: Request) {
  let body: { name?: unknown } = {};
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON payload" }, { status: 400 });
  }
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!name) {
    return NextResponse.json({ error: "Name is required" }, { status: 400 });
  }
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
