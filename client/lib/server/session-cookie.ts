const encoder = new TextEncoder();

export const SESSION_COOKIE_NAME = process.env.SESSION_COOKIE_NAME || "pulsefm_session";

async function _hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  const bytes = new Uint8Array(signature);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function _constantTimeEquals(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

export async function mintSignedSessionValue(sessionId: string, secret: string): Promise<string> {
  const signature = await _hmacHex(secret, sessionId);
  return `${sessionId}.${signature}`;
}

export async function verifySignedSessionValue(
  value: string | undefined,
  secret: string,
): Promise<string | null> {
  if (!value) {
    return null;
  }
  const split = value.lastIndexOf(".");
  if (split <= 0 || split >= value.length - 1) {
    return null;
  }
  const sessionId = value.slice(0, split);
  const providedSignature = value.slice(split + 1);
  const expectedSignature = await _hmacHex(secret, sessionId);
  if (!_constantTimeEquals(expectedSignature, providedSignature)) {
    return null;
  }
  return sessionId;
}
