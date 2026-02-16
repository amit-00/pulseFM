import { useState, useCallback, useEffect, useRef, useMemo } from "react";

import { useAudioSlots } from "./useAudioSlots";
import { useAudioAnalyser } from "./useAudioAnalyser";
import { ensureSession, fetchPlaybackState, fetchVoteStatus } from "@/lib/stream";
import {
  HelloEvent,
  PlaybackStateSnapshot,
  SongChangedEvent,
  TallyDeltaEvent,
  TallySnapshotEvent,
} from "@/lib/types";

type Slot = "first" | "second";

type VoteView = {
  voteId: string | null;
  options: Record<string, string>;
  tallies: Record<string, number>;
  endTime: number;
};

function toVoteView(snapshot: PlaybackStateSnapshot | null): VoteView {
  const poll = snapshot?.poll ?? { voteId: null, options: [], tallies: {}, version: null };
  const options = Object.fromEntries(poll.options.map((option) => [option, option]));
  return {
    voteId: poll.voteId,
    options,
    tallies: poll.tallies || {},
    endTime: snapshot?.currentSong?.endAt ?? Date.now(),
  };
}

function formatTime(seconds: number): string {
  if (seconds <= 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function computePlaybackOffsetSeconds(currentSong: PlaybackStateSnapshot["currentSong"] | null): number {
  if (!currentSong) return 0;
  const durationMs = currentSong.durationMs ?? 0;
  const endAt = currentSong.endAt ?? 0;
  if (!durationMs || !endAt) return 0;
  const startAt = endAt - durationMs;
  const elapsedMs = Math.max(0, Date.now() - startAt);
  const clampedMs = Math.min(durationMs, elapsedMs);
  return clampedMs / 1000;
}

async function fetchSignedUrls(voteIds: string[]): Promise<Record<string, string>> {
  const response = await fetch("/api/cdn-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voteIds }),
  });
  if (!response.ok) {
    throw new Error("Failed to get signed URLs");
  }
  const data = (await response.json()) as { urls: Record<string, string> };
  return data.urls;
}

export function useStreamPlayer() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeSlot, setActiveSlot] = useState<Slot>("first");
  const [snapshot, setSnapshot] = useState<PlaybackStateSnapshot | null>(null);
  const [timeRemaining, setTimeRemaining] = useState(0);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [hasVoted, setHasVoted] = useState(false);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isSubmittingVote, setIsSubmittingVote] = useState(false);
  const [voteError, setVoteError] = useState<string | null>(null);
  const [volume, setVolume] = useState(1);
  const audioElementsConnected = useRef(false);
  const sourceReady = useRef(false);
  const streamRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const snapshotRef = useRef<PlaybackStateSnapshot | null>(null);
  const pollVersionRef = useRef<number | null>(null);

  const {
    firstSlotAudioRef,
    secondSlotAudioRef,
    getActiveAudioRef,
    getInactiveAudioRef,
    loadTrackToSlot,
    getInactiveSlot,
  } = useAudioSlots();

  const {
    frequencyData,
    isAnalysing,
    connectAudioElement,
    startAnalysing,
    stopAnalysing,
    initializeAudioContext,
  } = useAudioAnalyser();

  const refreshState = useCallback(async () => {
    const nextSnapshot = await fetchPlaybackState();
    setSnapshot(nextSnapshot);
    snapshotRef.current = nextSnapshot;
    pollVersionRef.current = nextSnapshot.poll.version;

    // Restore vote state from the session cookie so all tabs stay in sync
    const voteStatus = await fetchVoteStatus(nextSnapshot.poll.voteId);
    setHasVoted(voteStatus.hasVoted);
    setSelectedOption(voteStatus.selectedOption);

    return nextSnapshot;
  }, []);

  const connectAudioElements = useCallback(() => {
    if (audioElementsConnected.current) return;
    if (firstSlotAudioRef.current) {
      connectAudioElement(firstSlotAudioRef.current);
    }
    if (secondSlotAudioRef.current) {
      connectAudioElement(secondSlotAudioRef.current);
    }
    audioElementsConnected.current = true;
  }, [connectAudioElement, firstSlotAudioRef, secondSlotAudioRef]);

  const applySongChangeover = useCallback(
    async (nextSnapshot: PlaybackStateSnapshot) => {
      if (!isPlaying) {
        sourceReady.current = false;
        return;
      }

      const currentVoteId = nextSnapshot.currentSong.voteId;
      if (!currentVoteId) {
        return;
      }

      const nextVoteId = nextSnapshot.nextSong.voteId;
      const idsToSign = [currentVoteId, ...(nextVoteId ? [nextVoteId] : [])];
      const urls = await fetchSignedUrls(idsToSign);

      const inactiveSlot = getInactiveSlot(activeSlot);
      const newActiveRef = getActiveAudioRef(inactiveSlot);
      const oldActiveRef = getActiveAudioRef(activeSlot);
      const startOffsetSec = computePlaybackOffsetSeconds(nextSnapshot.currentSong);

      if (newActiveRef.current) {
        newActiveRef.current.src = urls[currentVoteId];
        newActiveRef.current.currentTime = startOffsetSec;
        newActiveRef.current.volume = volume;
        await newActiveRef.current.play();
      }

      if (oldActiveRef.current) {
        oldActiveRef.current.pause();
      }

      if (nextVoteId && urls[nextVoteId]) {
        loadTrackToSlot(activeSlot, urls[nextVoteId]);
      } else {
        const inactiveRef = getInactiveAudioRef(inactiveSlot);
        if (inactiveRef.current) {
          inactiveRef.current.removeAttribute("src");
        }
      }

      setActiveSlot(inactiveSlot);
      startAnalysing();
    },
    [
      activeSlot,
      getActiveAudioRef,
      getInactiveAudioRef,
      getInactiveSlot,
      isPlaying,
      loadTrackToSlot,
      startAnalysing,
      volume,
    ],
  );

  const connectStream = useCallback(() => {
    streamRef.current?.close();
    const es = new EventSource("/api/playback/stream");
    streamRef.current = es;

    es.addEventListener("HELLO", (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as HelloEvent;
        pollVersionRef.current = data.version;
      } catch {
        setStreamError("Invalid HELLO event payload");
      }
    });

    es.addEventListener("TALLY_SNAPSHOT", (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as TallySnapshotEvent;
        setSnapshot((prev) => {
          if (!prev || prev.poll.voteId !== data.voteId) {
            return prev;
          }
          const next = {
            ...prev,
            poll: { ...prev.poll, tallies: data.tallies },
          };
          snapshotRef.current = next;
          return next;
        });
      } catch {
        setStreamError("Invalid TALLY_SNAPSHOT payload");
      }
    });

    es.addEventListener("TALLY_DELTA", (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as TallyDeltaEvent;
        setSnapshot((prev) => {
          if (!prev || prev.poll.voteId !== data.voteId) {
            return prev;
          }
          const nextTallies = { ...prev.poll.tallies };
          for (const [option, delta] of Object.entries(data.delta || {})) {
            nextTallies[option] = Math.max(0, (nextTallies[option] || 0) + Number(delta || 0));
          }
          const next = {
            ...prev,
            poll: { ...prev.poll, tallies: nextTallies },
          };
          snapshotRef.current = next;
          return next;
        });
      } catch {
        setStreamError("Invalid TALLY_DELTA payload");
      }
    });

    es.addEventListener("SONG_CHANGED", async (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as SongChangedEvent;
        if (pollVersionRef.current !== null && data.version === pollVersionRef.current) {
          return;
        }
        const nextSnapshot = await refreshState();
        await applySongChangeover(nextSnapshot);
      } catch {
        setStreamError("Failed to apply song changeover");
      }
    });

    es.onerror = () => {
      es.close();
      streamRef.current = null;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      reconnectTimerRef.current = window.setTimeout(async () => {
        try {
          await refreshState();
        } catch {
          // keep stream reconnect loop alive even when state fetch fails
        }
        connectStream();
      }, 1000);
    };
  }, [applySongChangeover, refreshState]);

  const handlePlayPause = useCallback(async () => {
    const activeAudioRef = getActiveAudioRef(activeSlot);

    if (isPlaying) {
      activeAudioRef.current?.pause();
      setIsPlaying(false);
      stopAnalysing();
      return;
    }

    const currentSnapshot = snapshotRef.current;
    const currentVoteId = currentSnapshot?.currentSong.voteId;
    if (!currentSnapshot || !currentVoteId) {
      setStreamError("Playback state unavailable");
      return;
    }

    try {
      initializeAudioContext();
      connectAudioElements();

      const nextVoteId = currentSnapshot.nextSong.voteId;
      const idsToSign = [currentVoteId, ...(nextVoteId ? [nextVoteId] : [])];
      const urls = await fetchSignedUrls(idsToSign);

      const startTimeSeconds = computePlaybackOffsetSeconds(currentSnapshot.currentSong);
      if (activeAudioRef.current) {
        activeAudioRef.current.src = urls[currentVoteId];
        activeAudioRef.current.currentTime = startTimeSeconds;
        activeAudioRef.current.volume = volume;
        await activeAudioRef.current.play();
      }

      if (nextVoteId && urls[nextVoteId]) {
        const inactiveSlot = getInactiveSlot(activeSlot);
        loadTrackToSlot(inactiveSlot, urls[nextVoteId]);
      }

      sourceReady.current = true;
      setIsPlaying(true);
      startAnalysing();
    } catch {
      setStreamError("Failed to start playback");
      stopAnalysing();
    }
  }, [
    activeSlot,
    connectAudioElements,
    getActiveAudioRef,
    getInactiveSlot,
    initializeAudioContext,
    isPlaying,
    loadTrackToSlot,
    startAnalysing,
    stopAnalysing,
    volume,
  ]);

  const submitVote = useCallback(async (optionKey: string) => {
    const voteId = snapshotRef.current?.poll.voteId;
    if (!voteId || isSubmittingVote) return;

    setIsSubmittingVote(true);
    setVoteError(null);
    try {
      const response = await fetch("/api/vote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voteId, option: optionKey }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error((data as { error?: string }).error || "Vote failed");
      }
      setHasVoted(true);
      setSelectedOption(optionKey);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Vote failed";
      setVoteError(message);
    } finally {
      setIsSubmittingVote(false);
    }
  }, [isSubmittingVote]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await ensureSession();
        if (cancelled) return;
        await refreshState();
        if (cancelled) return;
        connectStream();
      } catch {
        if (!cancelled) {
          setStreamError("Failed to initialize playback");
        }
      }
    })();

    return () => {
      cancelled = true;
      streamRef.current?.close();
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [connectStream, refreshState]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const endAt = snapshotRef.current?.currentSong.endAt;
      if (!endAt) {
        setTimeRemaining(0);
        return;
      }
      const seconds = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
      setTimeRemaining(seconds);
    }, 1000);

    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const firstAudio = firstSlotAudioRef.current;
    const secondAudio = secondSlotAudioRef.current;
    const onEnded = () => {
      setIsPlaying(false);
      stopAnalysing();
    };

    firstAudio?.addEventListener("ended", onEnded);
    secondAudio?.addEventListener("ended", onEnded);
    return () => {
      firstAudio?.removeEventListener("ended", onEnded);
      secondAudio?.removeEventListener("ended", onEnded);
    };
  }, [firstSlotAudioRef, secondSlotAudioRef, stopAnalysing]);

  useEffect(() => {
    const allRefs = [firstSlotAudioRef.current, secondSlotAudioRef.current];
    for (const ref of allRefs) {
      if (ref) {
        ref.volume = volume;
      }
    }
  }, [firstSlotAudioRef, secondSlotAudioRef, volume]);

  const voteData = useMemo(() => toVoteView(snapshot), [snapshot]);
  const isExpired = timeRemaining <= 0;
  const formattedTime = useMemo(() => formatTime(timeRemaining), [timeRemaining]);

  return {
    isPlaying,
    handlePlayPause,
    firstSlotAudioRef,
    secondSlotAudioRef,
    frequencyData,
    isAnalysing,
    voteData,
    hasVoted,
    selectedOption,
    isSubmittingVote,
    voteError,
    submitVote,
    formattedTime,
    isExpired,
    streamError,
    volume,
    setVolume,
    sourceReady: sourceReady.current,
  };
}
