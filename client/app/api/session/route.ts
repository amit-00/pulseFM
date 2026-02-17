import { NextResponse } from "next/server";
import { signIn } from "@/auth";

export async function POST(request: Request) {
  try {
    const result = await signIn("credentials", {
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
