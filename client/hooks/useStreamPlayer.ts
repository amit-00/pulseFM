import { useState, useCallback, useEffect, useRef, useMemo } from "react";

import { useAudioSlots } from "./useAudioSlots";
import { useAudioAnalyser } from "./useAudioAnalyser";
import { ensureSession, fetchPlaybackState, fetchVoteStatus, submitVote as postVote } from "@/lib/stream";
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

const SONG_CHANGE_RETRY_ATTEMPTS = 2;
const POLL_INTERVAL_MS = 3000;

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
  const pollingRef = useRef<number | null>(null);
  const refreshInFlightRef = useRef<Promise<PlaybackStateSnapshot> | null>(null);

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

  const getAudioUrl = useCallback((song: PlaybackStateSnapshot["currentSong"] | PlaybackStateSnapshot["nextSong"]) => {
    if (song.audioUrl) {
      return song.audioUrl;
    }
    if (!song.voteId) {
      return null;
    }
    const baseUrl = process.env.NEXT_PUBLIC_AUDIO_BASE_URL || "";
    if (!baseUrl) {
      return null;
    }
    return `${baseUrl.replace(/\/$/, "")}/encoded/${song.voteId}.m4a`;
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

      const currentSource = getAudioUrl(nextSnapshot.currentSong);
      if (!currentSource) {
        return;
      }

      const nextSource = getAudioUrl(nextSnapshot.nextSong);

      const activeSlotValue = activeSlotRef.current;
      const inactiveSlot = getInactiveSlot(activeSlotValue);
      const newActiveRef = getActiveAudioRef(inactiveSlot);
      const oldActiveRef = getActiveAudioRef(activeSlotValue);
      const startOffsetSec = computePlaybackOffsetSeconds(nextSnapshot.currentSong);

      if (newActiveRef.current) {
        newActiveRef.current.src = currentSource;
        newActiveRef.current.currentTime = startOffsetSec;
        newActiveRef.current.volume = volumeRef.current;
        await newActiveRef.current.play();
      }

      if (oldActiveRef.current) {
        oldActiveRef.current.pause();
      }

      if (nextSource) {
        loadTrackToSlot(activeSlotValue, nextSource);
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
      getAudioUrl,
      getActiveAudioRef,
      getInactiveAudioRef,
      getInactiveSlot,
      loadTrackToSlot,
      startAnalysing,
    ],
  );

  const syncVoteState = useCallback((voteId: string | null) => {
    const voteStatus = fetchVoteStatus(voteId);
    setHasVoted(voteStatus.hasVoted);
    setSelectedOption(voteStatus.selectedOption);
  }, []);

  const refreshState = useCallback(async () => {
    if (refreshInFlightRef.current) {
      return refreshInFlightRef.current;
    }

    const refreshPromise = (async () => {
      const previous = snapshotRef.current;
      const nextSnapshot = await fetchPlaybackState();
      setSnapshot(nextSnapshot);
      snapshotRef.current = nextSnapshot;
      setActiveListeners(typeof nextSnapshot.listeners === "number" ? nextSnapshot.listeners : null);
      setRedisAvailable(true);
      syncVoteState(nextSnapshot.poll.voteId);

      const nextSource = getAudioUrl(nextSnapshot.nextSong);
      if (nextSource) {
        const inactiveSlot = getInactiveSlot(activeSlotRef.current);
        loadTrackToSlot(inactiveSlot, nextSource);
      }

      const currentChanged =
        previous?.currentSong.voteId !== nextSnapshot.currentSong.voteId ||
        previous?.currentSong.startAt !== nextSnapshot.currentSong.startAt;

      if (currentChanged && isPlayingRef.current) {
        let attempt = 0;
        while (attempt < SONG_CHANGE_RETRY_ATTEMPTS) {
          try {
            await applySongChangeover(nextSnapshot);
            break;
          } catch (error) {
            attempt += 1;
            if (attempt >= SONG_CHANGE_RETRY_ATTEMPTS) {
              throw error;
            }
          }
        }
      }

      return nextSnapshot;
    })();

    refreshInFlightRef.current = refreshPromise;
    try {
      return await refreshPromise;
    } finally {
      refreshInFlightRef.current = null;
    }
  }, [applySongChangeover, getAudioUrl, getInactiveSlot, loadTrackToSlot, syncVoteState]);

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
    const currentSource = currentSnapshot ? getAudioUrl(currentSnapshot.currentSong) : null;
    if (!currentSnapshot || !currentSource) {
      setStreamError("Playback state unavailable");
      return;
    }

    try {
      initializeAudioContext();
      connectAudioElements();

      const startTimeSeconds = computePlaybackOffsetSeconds(currentSnapshot.currentSong);
      if (activeAudioRef.current) {
        activeAudioRef.current.src = currentSource;
        activeAudioRef.current.currentTime = startTimeSeconds;
        activeAudioRef.current.volume = volume;
        await activeAudioRef.current.play();
      }

      const nextSource = getAudioUrl(currentSnapshot.nextSong);
      if (nextSource) {
        const inactiveSlot = getInactiveSlot(activeSlot);
        loadTrackToSlot(inactiveSlot, nextSource);
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
    getAudioUrl,
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
      await postVote(voteId, optionKey);
      await refreshState();
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
          setRedisAvailable(false);
          setIsInitialStateLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [refreshState]);

  useEffect(() => {
    if (!sessionReady) {
      return;
    }

    const runPoll = async () => {
      try {
        await refreshState();
        setStreamError(null);
      } catch {
        setRedisAvailable(false);
        setStreamError("Waiting for the Cloudflare control plane");
      }
    };

    pollingRef.current = window.setInterval(() => {
      void runPoll();
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollingRef.current !== null) {
        window.clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [refreshState, sessionReady]);

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
