from __future__ import annotations

from urllib.parse import urlparse

from workers import DurableObject, Request, Response, WorkerEntrypoint

from orchestrator import PlaybackOrchestrator


class PlaybackStateDurableObject(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self._orchestrator = PlaybackOrchestrator(ctx, env)

    async def fetch(self, request: Request) -> Response:
        method = request.method.upper()
        path = urlparse(request.url).path

        if method == "GET" and path == "/state":
            return Response.json(await self._orchestrator.state_snapshot())

        if method == "POST" and path == "/start":
            return Response.json(await self._orchestrator.start())

        return Response.json({"error": "not_found"}, status=404)

    async def alarm(self, alarm_info=None):
        await self._orchestrator.handle_alarm()


class Default(WorkerEntrypoint):
    async def fetch(self, request: Request) -> Response:
        method = request.method.upper()
        path = urlparse(request.url).path

        if (method, path) not in {("GET", "/state"), ("POST", "/start")}:
            return Response.json({"error": "not_found"}, status=404)

        durable_object_id = self.env.PLAYBACK_STATE.idFromName("main")
        stub = self.env.PLAYBACK_STATE.get(durable_object_id)
        return await stub.fetch(request)
