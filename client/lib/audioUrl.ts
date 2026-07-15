type CachedUrl = { url: string; expiresAt: number };

const cache = new Map<string, CachedUrl>();
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

export async function fetchAudioUrl(voteId: string): Promise<string> {
  const cached = cache.get(voteId);
  if (cached && cached.expiresAt - Date.now() > REFRESH_MARGIN_MS) {
    return cached.url;
  }
  const response = await fetch(`/api/track/${encodeURIComponent(voteId)}`, { cache: "no-store" });
  if (!response.ok) {
    if (cached && cached.expiresAt > Date.now()) return cached.url;
    throw new Error("Failed to resolve track URL");
  }
  const data = (await response.json()) as CachedUrl;
  cache.set(voteId, data);
  return data.url;
}
