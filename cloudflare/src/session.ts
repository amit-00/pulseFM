import type { BootstrapSession, Env } from "./types";

const encoder = new TextEncoder();

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(value: string): Uint8Array {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function importKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

async function sign(payload: string, secret: string): Promise<string> {
  const key = await importKey(secret);
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
  return toBase64Url(new Uint8Array(signature));
}

export async function createSession(env: Env): Promise<BootstrapSession> {
  const sessionId = crypto.randomUUID();
  const payload = `${sessionId}.${Date.now()}`;
  const signature = await sign(payload, env.SESSION_TOKEN_SECRET);
  return {
    sessionId,
    token: `${payload}.${signature}`,
  };
}

export async function verifySessionToken(token: string, env: Env): Promise<string | null> {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }

  const [sessionId, issuedAt, providedSignature] = parts;
  if (!sessionId || !issuedAt || !providedSignature) {
    return null;
  }

  const expected = await sign(`${sessionId}.${issuedAt}`, env.SESSION_TOKEN_SECRET);
  const provided = fromBase64Url(providedSignature);
  const expectedBytes = fromBase64Url(expected);

  if (provided.length !== expectedBytes.length) {
    return null;
  }

  let mismatch = 0;
  for (let i = 0; i < provided.length; i += 1) {
    mismatch |= provided[i] ^ expectedBytes[i];
  }

  return mismatch === 0 ? sessionId : null;
}
