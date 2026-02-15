import { createHmac } from "node:crypto";

function toBase64Url(input: Buffer | string): string {
  const value = Buffer.isBuffer(input) ? input.toString("base64") : Buffer.from(input, "utf8").toString("base64");
  return value.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decodeBase64Url(input: string): Buffer {
  const normalized = input.replace(/-/g, "+").replace(/_/g, "/");
  const padding = normalized.length % 4 === 0 ? "" : "=".repeat(4 - (normalized.length % 4));
  return Buffer.from(normalized + padding, "base64");
}

export function buildSignedUrl(params: {
  url: string;
  keyName: string;
  keyValue: string;
  expiresEpochSec: number;
}): string {
  const separator = params.url.includes("?") ? "&" : "?";
  const urlWithExpiry = `${params.url}${separator}Expires=${params.expiresEpochSec}&KeyName=${params.keyName}`;
  const signature = createHmac("sha1", decodeBase64Url(params.keyValue))
    .update(urlWithExpiry)
    .digest();
  return `${urlWithExpiry}&Signature=${toBase64Url(signature)}`;
}

