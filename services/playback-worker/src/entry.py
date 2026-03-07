from __future__ import annotations

from urllib.parse import urlparse

from workers import DurableObject, Request, Response, WorkerEntrypoint

from orchestrator import PlaybackOrchestrator


class PlaybackStateDurableObject(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self._orchestrator = PlaybackOrchestrator(ctx, env)

    async def fetch(self, request: Request) -> Response:
        path = urlparse(request.url).path
        if request.method.upper() == "GET" and path == "/state":
            snapshot = await self._orchestrator.state_snapshot()
            return Response.json(snapshot)

        return Response.json({"error": "not_found"}, status=404)

    async def alarm(self, alarm_info=None):
        await self._orchestrator.handle_alarm()


class Default(WorkerEntrypoint):
    async def fetch(self, request: Request) -> Response:
        path = urlparse(request.url).path
        if request.method.upper() != "GET" or path != "/state":
            return Response.json({"error": "not_found"}, status=404)

        durable_object_id = self.env.PLAYBACK_STATE.idFromName("main")
        stub = self.env.PLAYBACK_STATE.get(durable_object_id)
        return await stub.fetch(request)
