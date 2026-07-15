import { useState, useCallback, useEffect, useRef, useMemo } from "react";

import { useAudioSlots } from "./useAudioSlots";
import { useAudioAnalyser } from "./useAudioAnalyser";
import { fetchAudioUrl } from "@/lib/audioUrl";
import { ensureSession, fetchPlaybackState, fetchVoteStatus } from "@/lib/stream";
import { diffSnapshots, nextPollDelayMs } from "@/lib/pollDiff";
import { PlaybackStateSnapshot } from "@/lib/types";

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

const HEARTBEAT_INTERVAL_MS = 15000;
const HEARTBEAT_JITTER_MS = 2000;

export function useStreamPlayer() {
  const [isInitialStateLoading, setIsInitialStateLoading] = useState(true);
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
  const [redisAvailable, setRedisAvailable] = useState(true);
  const [activeListeners, setActiveListeners] = useState<number | null>(null);
  const audioElementsConnected = useRef(false);
  const sourceReady = useRef(false);
  const snapshotRef = useRef<PlaybackStateSnapshot | null>(null);
  const isPlayingRef = useRef(false);
  const activeSlotRef = useRef<Slot>("first");
  const volumeRef = useRef(1);

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
    setActiveListeners(typeof nextSnapshot.listeners === "number" ? nextSnapshot.listeners : null);
    if (typeof nextSnapshot.redisAvailable === "boolean") {
      setRedisAvailable(nextSnapshot.redisAvailable);
    }

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

      const currentUrl = await fetchAudioUrl(currentVoteId);
      const nextUrl = nextVoteId ? await fetchAudioUrl(nextVoteId).catch(() => null) : null;

      const activeSlotValue = activeSlotRef.current;
      const inactiveSlot = getInactiveSlot(activeSlotValue);
      const newActiveRef = getActiveAudioRef(inactiveSlot);
      const oldActiveRef = getActiveAudioRef(activeSlotValue);
      const startOffsetSec = computePlaybackOffsetSeconds(nextSnapshot.currentSong);

      if (newActiveRef.current) {
        newActiveRef.current.src = currentUrl;
        newActiveRef.current.currentTime = startOffsetSec;
        newActiveRef.current.volume = volumeRef.current;
        await newActiveRef.current.play();
      }

      if (oldActiveRef.current) {
        oldActiveRef.current.pause();
      }

      if (nextVoteId && nextUrl) {
        loadTrackToSlot(activeSlotValue, nextUrl);
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

  const applySnapshotTransitions = useCallback(
    async (prev: PlaybackStateSnapshot | null, next: PlaybackStateSnapshot) => {
      const transitions = diffSnapshots(prev, next);
      if (transitions.songChanged) {
        try {
          await applySongChangeover(next);
          setStreamError(null);
        } catch {
          setStreamError("Failed to apply song changeover");
        }
      } else if (transitions.nextSongChanged && next.nextSong.voteId) {
        void fetchAudioUrl(next.nextSong.voteId)
          .then((url) => loadTrackToSlot(getInactiveSlot(activeSlotRef.current), url))
          .catch(() => {});
      }
      if (transitions.pollChanged) {
        const voteStatus = await fetchVoteStatus(next.poll.voteId);
        setHasVoted(voteStatus.hasVoted);
        setSelectedOption(voteStatus.selectedOption);
      }
    },
    [applySongChangeover, getInactiveSlot, loadTrackToSlot],
  );

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
        activeAudioRef.current.src = await fetchAudioUrl(currentVoteId);
        activeAudioRef.current.currentTime = startTimeSeconds;
        activeAudioRef.current.volume = volume;
        await activeAudioRef.current.play();
      }

      if (nextVoteId) {
        const inactiveSlot = getInactiveSlot(activeSlot);
        fetchAudioUrl(nextVoteId)
          .then((url) => loadTrackToSlot(inactiveSlot, url))
          .catch(() => {});
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
    if (!redisAvailable) {
      setVoteError("Voting temporarily unavailable");
      return;
    }
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
        const data = (await response.json().catch(() => ({}))) as { error?: string };
        if (response.status === 409 && data.error === "Duplicate vote") {
          // The backend confirmed this session already voted — keep the selection.
          return;
        }
        throw new Error(data.error || "Vote failed");
      }
      // Refresh immediately so tallies update without waiting for the next poll.
      void refreshState().catch(() => {});
    } catch (error) {
      setHasVoted(false);
      setSelectedOption(null);

      const message = error instanceof Error ? error.message : "Vote failed";
      setVoteError(message);
    } finally {
      setIsSubmittingVote(false);
    }
  }, [isSubmittingVote, redisAvailable, refreshState]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await ensureSession();
        if (cancelled) return;
        setSessionReady(true);
        await refreshState();
        if (cancelled) return;
        setIsInitialStateLoading(false);
      } catch {
        if (!cancelled) {
          setStreamError("Failed to initialize playback");
          setIsInitialStateLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [refreshState]);

  useEffect(() => {
    if (!sessionReady) return;
    let cancelled = false;
    let timerId: number | null = null;

    const poll = async () => {
      if (cancelled) return;
      const prev = snapshotRef.current;
      try {
        const next = await fetchPlaybackState();
        if (cancelled) return;
        snapshotRef.current = next;
        setSnapshot(next);
        setActiveListeners(typeof next.listeners === "number" ? next.listeners : null);
        if (typeof next.redisAvailable === "boolean") setRedisAvailable(next.redisAvailable);
        await applySnapshotTransitions(prev, next);
        setStreamError(null);
      } catch {
        if (!cancelled) setStreamError("Failed to fetch playback state");
      } finally {
        if (!cancelled) {
          timerId = window.setTimeout(poll, nextPollDelayMs(snapshotRef.current, Date.now()));
        }
      }
    };

    timerId = window.setTimeout(poll, nextPollDelayMs(snapshotRef.current, Date.now()));
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [applySnapshotTransitions, sessionReady]);

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
    // Playback continuity is poll-driven (snapshot diffing + changeover),
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
  const votePanelTimeLabel = useMemo(
    () => (isExpired ? "Next vote in" : "Vote ends in"),
    [isExpired],
  );
  const votePanelFormattedTime = useMemo(
    () => (isExpired ? formattedSongTime : formattedTime),
    [formattedSongTime, formattedTime, isExpired],
  );

  return {
    isInitialStateLoading,
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
    votePanelTimeLabel,
    votePanelFormattedTime,
    activeListeners,
    isExpired,
    streamError,
    volume,
    setVolume,
    sourceReady: sourceReady.current,
    redisAvailable,
  };
}
