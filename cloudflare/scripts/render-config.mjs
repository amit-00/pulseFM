import fs from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const templatePath = path.join(root, "wrangler.template.jsonc");
const outputName = process.argv[2] || "wrangler.jsonc";
const outputPath = path.join(root, outputName);

const requiredKeys = [
  "CF_APP_ORIGIN",
  "CF_PUBLIC_AUDIO_BASE_URL",
  "CF_PUBLIC_API_BASE_URL",
  "CF_EXTERNAL_GENERATOR_URL",
  "CF_SESSION_TOKEN_SECRET",
  "CF_INTERNAL_CALLBACK_SECRET",
  "CF_ZONE_NAME",
  "CF_API_ROUTE",
  "CF_INTERNAL_ROUTE",
  "CF_D1_DATABASE_ID",
  "CF_R2_BUCKET_NAME"
];

for (const key of requiredKeys) {
  if (!process.env[key]) {
    console.error(`Missing required environment variable: ${key}`);
    process.exit(1);
  }
}

const replacements = {
  "__APP_ORIGIN__": process.env.CF_APP_ORIGIN,
  "__PUBLIC_AUDIO_BASE_URL__": process.env.CF_PUBLIC_AUDIO_BASE_URL,
  "__PUBLIC_API_BASE_URL__": process.env.CF_PUBLIC_API_BASE_URL,
  "__EXTERNAL_GENERATOR_URL__": process.env.CF_EXTERNAL_GENERATOR_URL,
  "__SESSION_TOKEN_SECRET__": process.env.CF_SESSION_TOKEN_SECRET,
  "__INTERNAL_CALLBACK_SECRET__": process.env.CF_INTERNAL_CALLBACK_SECRET,
  "__ZONE_NAME__": process.env.CF_ZONE_NAME,
  "__API_ROUTE__": process.env.CF_API_ROUTE,
  "__INTERNAL_ROUTE__": process.env.CF_INTERNAL_ROUTE,
  "__D1_DATABASE_ID__": process.env.CF_D1_DATABASE_ID,
  "__R2_BUCKET_NAME__": process.env.CF_R2_BUCKET_NAME,
  "__PREVIEW_APP_ORIGIN__": process.env.CF_PREVIEW_APP_ORIGIN || process.env.CF_APP_ORIGIN,
  "__PREVIEW_AUDIO_BASE_URL__": process.env.CF_PREVIEW_AUDIO_BASE_URL || process.env.CF_PUBLIC_AUDIO_BASE_URL,
  "__PREVIEW_API_BASE_URL__": process.env.CF_PREVIEW_API_BASE_URL || process.env.CF_PUBLIC_API_BASE_URL,
  "__PREVIEW_API_ROUTE__": process.env.CF_PREVIEW_API_ROUTE || process.env.CF_API_ROUTE,
  "__PREVIEW_INTERNAL_ROUTE__": process.env.CF_PREVIEW_INTERNAL_ROUTE || process.env.CF_INTERNAL_ROUTE,
  "__PREVIEW_D1_DATABASE_ID__": process.env.CF_PREVIEW_D1_DATABASE_ID || process.env.CF_D1_DATABASE_ID,
  "__PREVIEW_R2_BUCKET_NAME__": process.env.CF_PREVIEW_R2_BUCKET_NAME || process.env.CF_R2_BUCKET_NAME
};

let template = fs.readFileSync(templatePath, "utf8");
for (const [needle, value] of Object.entries(replacements)) {
  template = template.replaceAll(needle, value);
}

fs.writeFileSync(outputPath, template);
