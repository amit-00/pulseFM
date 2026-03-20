import { recordGenerationCompleted } from "./db";
import { createSession, verifySessionToken } from "./session";
import { StationControl } from "./station-control";
import { GenerateSongWorkflow } from "./workflow";
import type { Env, GenerationReadyPayload, ReadySong, SeedPayload } from "./types";

function json(data: unknown, status = 200, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  });
}

function corsHeaders(env: Env): HeadersInit {
  return {
    "Access-Control-Allow-Origin": env.APP_ORIGIN,
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Callback-Secret",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  };
}

async function getStation(env: Env): Promise<DurableObjectStub<StationControl>> {
  const id = env.STATION_CONTROL.idFromName("main");
  return env.STATION_CONTROL.get(id) as DurableObjectStub<StationControl>;
}

async function getSessionId(request: Request, env: Env): Promise<string | null> {
  const header = request.headers.get("Authorization");
  if (!header?.startsWith("Bearer ")) {
    return null;
  }
  return verifySessionToken(header.slice("Bearer ".length), env);
}

async function handleState(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const sessionId = await getSessionId(request, env);
  const cacheKey = new Request(new URL(request.url).toString(), { method: "GET" });
  const cache = await caches.open("pulsefm-state");
  const cached = await cache.match(cacheKey);

  if (cached) {
    if (sessionId) {
      const station = await getStation(env);
      ctx.waitUntil(station.getPublicSnapshot(sessionId).then(() => undefined));
    }
    return new Response(cached.body, cached);
  }

  const station = await getStation(env);
  const snapshot = await station.getPublicSnapshot(sessionId ?? undefined);
  const response = json(snapshot, 200, {
    ...corsHeaders(env),
    "Cache-Control": "public, max-age=2, s-maxage=2",
  });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(env) });
    }

    const url = new URL(request.url);

    if (url.pathname === "/api/session/bootstrap" && request.method === "POST") {
      const session = await createSession(env);
      return json(session, 200, corsHeaders(env));
    }

    if (url.pathname === "/api/state" && request.method === "GET") {
      return handleState(request, env, ctx);
    }

    if (url.pathname === "/api/vote" && request.method === "POST") {
      const sessionId = await getSessionId(request, env);
      if (!sessionId) {
        return json({ error: "Missing or invalid session" }, 401, corsHeaders(env));
      }

      const body = (await request.json()) as { voteId?: string; option?: string };
      if (!body.voteId || !body.option) {
        return json({ error: "voteId and option are required" }, 400, corsHeaders(env));
      }

      try {
        const station = await getStation(env);
        const snapshot = await station.castVote({
          sessionId,
          voteId: body.voteId,
          option: body.option,
        });
        return json({ status: "ok", snapshot }, 200, corsHeaders(env));
      } catch (error) {
        return json(
          { error: error instanceof Error ? error.message : "Vote failed" },
          409,
          corsHeaders(env),
        );
      }
    }

    if (url.pathname === "/internal/generation/callback" && request.method === "POST") {
      const secret = request.headers.get("X-Callback-Secret");
      if (secret !== env.INTERNAL_CALLBACK_SECRET) {
        return json({ error: "Unauthorized" }, 401, corsHeaders(env));
      }

      const payload = (await request.json()) as GenerationReadyPayload;
      if (!payload.voteId || !payload.workflowInstanceId || !payload.durationMs || !payload.publicUrl || !payload.r2Key) {
        return json({ error: "Invalid callback payload" }, 400, corsHeaders(env));
      }

      await recordGenerationCompleted(env.DB, payload);

      const instance = await env.GENERATE_SONG_WORKFLOW.get(payload.workflowInstanceId);
      await instance.sendEvent({
        type: "song-ready",
        payload,
      });

      const station = await getStation(env);
      const readySong: ReadySong = {
        voteId: payload.voteId,
        durationMs: payload.durationMs,
        audioUrl: payload.publicUrl,
        winnerOption: payload.winnerOption ?? null,
        createdAt: Date.now(),
      };
      const snapshot = await station.attachReadySong(readySong);
      return json({ status: "ok", snapshot }, 200, corsHeaders(env));
    }

    if (url.pathname === "/internal/seed" && request.method === "POST") {
      const secret = request.headers.get("X-Callback-Secret");
      if (secret !== env.INTERNAL_CALLBACK_SECRET) {
        return json({ error: "Unauthorized" }, 401, corsHeaders(env));
      }

      const seed = (await request.json()) as SeedPayload;
      const station = await getStation(env);
      const snapshot = await station.seedState(seed);
      return json(snapshot, 200, corsHeaders(env));
    }

    return json({ error: "Not found" }, 404, corsHeaders(env));
  },
};

export { StationControl, GenerateSongWorkflow };
