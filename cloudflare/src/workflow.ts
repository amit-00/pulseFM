import { WorkflowEntrypoint, WorkflowEvent, WorkflowStep } from "cloudflare:workers";
import { recordGenerationCompleted, recordGenerationFailure, recordGenerationQueued } from "./db";
import type { Env, GenerationReadyPayload, GenerationWorkflowParams } from "./types";

export class GenerateSongWorkflow extends WorkflowEntrypoint<Env, GenerationWorkflowParams> {
  async run(
    event: WorkflowEvent<GenerationWorkflowParams>,
    step: WorkflowStep,
  ): Promise<GenerationReadyPayload> {
    const timeoutSeconds = Number(this.env.GENERATION_TIMEOUT_SEC || "900");
    const payload = event.payload;

    await step.do("queue generation job", async () => {
      const callbackUrl = `${this.env.PUBLIC_API_BASE_URL.replace(/\/$/, "")}/internal/generation/callback`;
      const response = await fetch(`${this.env.EXTERNAL_GENERATOR_URL.replace(/\/$/, "")}/jobs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Callback-Secret": this.env.INTERNAL_CALLBACK_SECRET,
        },
        body: JSON.stringify({
          voteId: payload.voteId,
          workflowInstanceId: event.instanceId,
          descriptor: payload.descriptor,
          winnerOption: payload.winnerOption,
          callbackUrl,
          outputKey: `encoded/${payload.voteId}.m4a`,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Generation dispatch failed: ${detail}`);
      }

      const data = (await response.json()) as { jobId?: string };
      await recordGenerationQueued(this.env.DB, payload.voteId, event.instanceId, data.jobId ?? null);
      return data;
    });

    try {
      const readyEvent = await step.waitForEvent<GenerationReadyPayload>("wait for song-ready", {
        type: "song-ready",
        timeout: `${timeoutSeconds} seconds`,
      });
      const ready = readyEvent.payload;

      await step.do("persist completion", async () => {
        await recordGenerationCompleted(this.env.DB, ready);
      });

      return ready;
    } catch (error) {
      await step.do("persist failure", async () => {
        await recordGenerationFailure(
          this.env.DB,
          payload.voteId,
          event.instanceId,
          error instanceof Error ? error.message : "Timed out waiting for song",
        );
      });
      throw error;
    }
  }
}
