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
  status: "OPEN" | "CLOSED" | null;
  winnerOption: string | null;
};

function toVoteView(snapshot: PlaybackStateSnapshot | null): VoteView {
  const poll = snapshot?.poll ?? {
    voteId: null,
    options: [],
    tallies: {},
    version: null,
    status: null,
    endAt: null,
    winnerOption: null,
  };
  const options = Object.fromEntries(poll.options.map((option) => [option, option]));
  return {
    voteId: poll.voteId,
    options,
    tallies: poll.tallies || {},
    endTime: poll.endAt ?? snapshot?.currentSong?.endAt ?? Date.now(),
    status: poll.status ?? null,
    winnerOption: poll.winnerOption ?? null,
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

function getAudioUrl(voteId: string): string {
  const cdnBaseUrl = process.env.NEXT_PUBLIC_CDN_BASE_URL || "";
  const bucketBaseUrl =
    process.env.NEXT_PUBLIC_BUCKET_BASE_URL || "https://storage.googleapis.com/pulsefm-generated-songs";
  const baseUrl = cdnBaseUrl || bucketBaseUrl;
  const normalized = baseUrl.replace(/\/$/, "");
  return `${normalized}/encoded/${voteId}.m4a`;
}

const SONG_CHANGE_RETRY_ATTEMPTS = 2;
const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const RECONNECT_JITTER_MS = 250;
const HEARTBEAT_INTERVAL_MS = 15000;
const HEARTBEAT_JITTER_MS = 2000;

export function useStreamPlayer() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeSlot, setActiveSlot] = useState<Slot>("first");
  const [snapshot, setSnapshot] = useState<PlaybackStateSnapshot | null>(null);
  const [timeRemaining, setTimeRemaining] = useState(0);
  const [songTimeRemaining, setSongTimeRemaining] = useState(0);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [hasVoted, setHasVoted] = useState(false);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [isSubmittingVote, setIsSubmittingVote] = useState(false);
  const [voteError, setVoteError] = useState<string | null>(null);
  const [volume, setVolume] = useState(1);
  const [sessionReady, setSessionReady] = useState(false);
  const [activeListeners, setActiveListeners] = useState<number | null>(null);
  const audioElementsConnected = useRef(false);
  const sourceReady = useRef(false);
  const streamRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const snapshotRef = useRef<PlaybackStateSnapshot | null>(null);
  const pollVersionRef = useRef<number | null>(null);
  const isPlayingRef = useRef(false);
  const activeSlotRef = useRef<Slot>("first");
  const volumeRef = useRef(1);
  const queuedSongChangedRef = useRef<SongChangedEvent | null>(null);
  const songChangedInFlightRef = useRef(false);

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
    setActiveListeners(typeof nextSnapshot.listeners === "number" ? nextSnapshot.listeners : null);

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
      if (!isPlayingRef.current) {
        sourceReady.current = false;
        return;
      }

      const currentVoteId = nextSnapshot.currentSong.voteId;
      if (!currentVoteId) {
        return;
      }

      const nextVoteId = nextSnapshot.nextSong.voteId;

      const activeSlotValue = activeSlotRef.current;
      const inactiveSlot = getInactiveSlot(activeSlotValue);
      const newActiveRef = getActiveAudioRef(inactiveSlot);
      const oldActiveRef = getActiveAudioRef(activeSlotValue);
      const startOffsetSec = computePlaybackOffsetSeconds(nextSnapshot.currentSong);

      if (newActiveRef.current) {
        newActiveRef.current.src = getAudioUrl(currentVoteId);
        newActiveRef.current.currentTime = startOffsetSec;
        newActiveRef.current.volume = volumeRef.current;
        await newActiveRef.current.play();
      }

      if (oldActiveRef.current) {
        oldActiveRef.current.pause();
      }

      if (nextVoteId) {
        loadTrackToSlot(activeSlotValue, getAudioUrl(nextVoteId));
      } else {
        const inactiveRef = getInactiveAudioRef(inactiveSlot);
        if (inactiveRef.current) {
          inactiveRef.current.removeAttribute("src");
        }
      }

      activeSlotRef.current = inactiveSlot;
      setActiveSlot(inactiveSlot);
      startAnalysing();
    },
    [
      getActiveAudioRef,
      getInactiveAudioRef,
      getInactiveSlot,
      loadTrackToSlot,
      startAnalysing,
    ],
  );

  const processSongChangedEvent = useCallback(
    async (data: SongChangedEvent) => {
      if (pollVersionRef.current !== null && data.version !== null && data.version <= pollVersionRef.current) {
        return;
      }

      let attempt = 0;
      while (attempt < SONG_CHANGE_RETRY_ATTEMPTS) {
        try {
          const nextSnapshot = await refreshState();
          await applySongChangeover(nextSnapshot);
          setStreamError(null);
          return;
        } catch (error) {
          attempt += 1;
          if (attempt >= SONG_CHANGE_RETRY_ATTEMPTS) {
            throw error;
          }
        }
      }
    },
    [applySongChangeover, refreshState],
  );

  const flushSongChangedQueue = useCallback(async () => {
    if (songChangedInFlightRef.current) {
      return;
    }
    songChangedInFlightRef.current = true;

    try {
      while (queuedSongChangedRef.current) {
        const event = queuedSongChangedRef.current;
        queuedSongChangedRef.current = null;
        await processSongChangedEvent(event);
      }
    } catch {
      setStreamError("Failed to apply song changeover");
    } finally {
      songChangedInFlightRef.current = false;
      if (queuedSongChangedRef.current) {
        void flushSongChangedQueue();
      }
    }
  }, [processSongChangedEvent]);

  const connectStream = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    streamRef.current?.close();
    const es = new EventSource("/api/playback/stream");
    streamRef.current = es;

    es.onopen = () => {
      reconnectAttemptRef.current = 0;
      setStreamError(null);
    };

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
            poll: {
              ...prev.poll,
              tallies: data.tallies,
              status: data.status ?? prev.poll.status,
              winnerOption: data.winnerOption ?? null,
            },
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
        if (typeof data.listeners === "number") {
          setActiveListeners(data.listeners);
        } else if (data.listeners === null) {
          setActiveListeners(null);
        }
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
        const queuedVersion = queuedSongChangedRef.current?.version;
        if (
          queuedVersion !== null &&
          queuedVersion !== undefined &&
          data.version !== null &&
          data.version !== undefined &&
          data.version < queuedVersion
        ) {
          return;
        }
        queuedSongChangedRef.current = data;
        await flushSongChangedQueue();
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
      const attempt = reconnectAttemptRef.current;
      const baseDelay = Math.min(RECONNECT_MAX_DELAY_MS, RECONNECT_BASE_DELAY_MS * 2 ** attempt);
      const jitter = Math.floor(Math.random() * RECONNECT_JITTER_MS);
      const delayMs = Math.min(RECONNECT_MAX_DELAY_MS, baseDelay + jitter);
      reconnectAttemptRef.current = Math.min(reconnectAttemptRef.current + 1, 10);
      reconnectTimerRef.current = window.setTimeout(async () => {
        try {
          await refreshState();
        } catch {
          // keep stream reconnect loop alive even when state fetch fails
        }
        connectStream();
      }, delayMs);
    };
  }, [flushSongChangedQueue, refreshState]);

  const handlePlayPause = useCallback(async () => {
    const activeAudioRef = getActiveAudioRef(activeSlot);

    if (isPlaying) {
      activeAudioRef.current?.pause();
      isPlayingRef.current = false;
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

      const startTimeSeconds = computePlaybackOffsetSeconds(currentSnapshot.currentSong);
      if (activeAudioRef.current) {
        activeAudioRef.current.src = getAudioUrl(currentVoteId);
        activeAudioRef.current.currentTime = startTimeSeconds;
        activeAudioRef.current.volume = volume;
        await activeAudioRef.current.play();
      }

      if (nextVoteId) {
        const inactiveSlot = getInactiveSlot(activeSlot);
        loadTrackToSlot(inactiveSlot, getAudioUrl(nextVoteId));
      }

      sourceReady.current = true;
      isPlayingRef.current = true;
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
    const voteStatus = snapshotRef.current?.poll.status;
    if (!voteId || isSubmittingVote) return;
    if (voteStatus !== "OPEN") {
      setVoteError("Voting is closed");
      return;
    }

    setIsSubmittingVote(true);
    setVoteError(null);

    setHasVoted(true);
    setSelectedOption(optionKey);

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
    } catch (error) {
      setHasVoted(false);
      setSelectedOption(null);

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
        setSessionReady(true);
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
    if (!sessionReady) {
      return;
    }

    let cancelled = false;
    let timerId: number | null = null;

    const scheduleNext = () => {
      if (cancelled) {
        return;
      }
      const jitterMs = Math.floor((Math.random() * 2 - 1) * HEARTBEAT_JITTER_MS);
      const delayMs = Math.max(1000, HEARTBEAT_INTERVAL_MS + jitterMs);
      timerId = window.setTimeout(sendHeartbeat, delayMs);
    };

    const sendHeartbeat = async () => {
      if (cancelled) {
        return;
      }
      try {
        await fetch("/api/heartbeat", {
          method: "POST",
          cache: "no-store",
        });
      } catch {
        // Silent retry only.
      } finally {
        scheduleNext();
      }
    };

    timerId = window.setTimeout(sendHeartbeat, 0);

    return () => {
      cancelled = true;
      if (timerId !== null) {
        window.clearTimeout(timerId);
      }
    };
  }, [sessionReady]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    activeSlotRef.current = activeSlot;
  }, [activeSlot]);

  useEffect(() => {
    volumeRef.current = volume;
  }, [volume]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const endAt = snapshotRef.current?.poll.endAt ?? snapshotRef.current?.currentSong.endAt;
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
    const interval = window.setInterval(() => {
      const songEndAt = snapshotRef.current?.currentSong.endAt;
      if (!songEndAt) {
        setSongTimeRemaining(0);
        return;
      }
      const seconds = Math.max(0, Math.ceil((songEndAt - Date.now()) / 1000));
      setSongTimeRemaining(seconds);
    }, 1000);

    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    // Playback continuity is stream-driven (SONG_CHANGED + snapshot refresh),
    // so natural track endings should not force a local playback stop.
    const onMediaError = () => {
      const activeAudio = getActiveAudioRef(activeSlotRef.current).current;
      if (!activeAudio?.error) {
        return;
      }
      activeAudio.pause();
      isPlayingRef.current = false;
      setIsPlaying(false);
      stopAnalysing();
      setStreamError("Playback stopped due to unrecoverable media error");
    };

    const firstAudio = firstSlotAudioRef.current;
    const secondAudio = secondSlotAudioRef.current;
    firstAudio?.addEventListener("error", onMediaError);
    secondAudio?.addEventListener("error", onMediaError);
    return () => {
      firstAudio?.removeEventListener("error", onMediaError);
      secondAudio?.removeEventListener("error", onMediaError);
    };
  }, [firstSlotAudioRef, secondSlotAudioRef, getActiveAudioRef, stopAnalysing]);

  useEffect(() => {
    const allRefs = [firstSlotAudioRef.current, secondSlotAudioRef.current];
    for (const ref of allRefs) {
      if (ref) {
        ref.volume = volume;
      }
    }
  }, [firstSlotAudioRef, secondSlotAudioRef, volume]);

  const voteData = useMemo(() => toVoteView(snapshot), [snapshot]);
  const isExpired = timeRemaining <= 0 || voteData.status === "CLOSED";
  const formattedTime = useMemo(() => formatTime(timeRemaining), [timeRemaining]);
  const formattedSongTime = useMemo(() => formatTime(songTimeRemaining), [songTimeRemaining]);

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
    formattedSongTime,
    activeListeners,
    isExpired,
    streamError,
    volume,
    setVolume,
    sourceReady: sourceReady.current,
  };
}
