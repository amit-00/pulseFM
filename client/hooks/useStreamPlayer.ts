import { useState, useCallback, useEffect, useRef } from "react";
import { useAudioSlots } from "./useAudioSlots";
import { useAudioAnalyser } from "./useAudioAnalyser";
import { fetchPlayingTrack, fetchNextTrack } from "@/lib/stream";

type Slot = "first" | "second";

export function useStreamPlayer() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeSlot, setActiveSlot] = useState<Slot>("first");
  const audioElementsConnected = useRef(false);

  const {
    firstSlotAudioRef,
    secondSlotAudioRef,
    getActiveAudioRef,
    getInactiveAudioRef,
    loadTrackToSlot,
    setTrackTime,
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

  const calculateStartTime = useCallback((durationElapsedMs: number, requestDelta: number): number => {
    return (durationElapsedMs + requestDelta) / 1000;
  }, []);

  // Connect audio elements to analyser when they're available
  const connectAudioElements = useCallback(() => {
    if (audioElementsConnected.current) return;

    if (firstSlotAudioRef.current) {
      connectAudioElement(firstSlotAudioRef.current);
    }
    if (secondSlotAudioRef.current) {
      connectAudioElement(secondSlotAudioRef.current);
    }
    audioElementsConnected.current = true;
  }, [firstSlotAudioRef, secondSlotAudioRef, connectAudioElement]);

  const handleSlotEnd = useCallback(async () => {
    if (!isPlaying) return;

    try {
      const newActiveSlot = getInactiveSlot(activeSlot);
      const newActiveAudioRef = getActiveAudioRef(newActiveSlot);

      // Start playing the newly active slot
      if (newActiveAudioRef.current) {
        await newActiveAudioRef.current.play();
      }

      setActiveSlot(newActiveSlot);

      // Fetch and load next track for the newly inactive slot
      const nextTrack = await fetchNextTrack();
      const newInactiveSlot = getInactiveSlot(newActiveSlot);
      loadTrackToSlot(newInactiveSlot, nextTrack.signed_url);
    } catch (error) {
      console.error("Error switching slots:", error);
      setIsPlaying(false);
      stopAnalysing();
    }
  }, [activeSlot, isPlaying, getActiveAudioRef, getInactiveSlot, loadTrackToSlot, stopAnalysing]);

  const handlePlayPause = useCallback(async () => {
    const audioRef = getActiveAudioRef(activeSlot);

    if (isPlaying) {
      audioRef.current?.pause();
      setIsPlaying(false);
      stopAnalysing();
      return;
    }

    try {
      // Initialize audio context on user interaction (required by browsers)
      initializeAudioContext();
      connectAudioElements();

      const requestTimestamp = performance.now();
      const playingTrack = await fetchPlayingTrack();
      const responseTimestamp = performance.now();
      const delta = responseTimestamp - requestTimestamp;

      const startTimeSeconds = calculateStartTime(playingTrack.duration_elapsed_ms, delta);

      if (audioRef.current) {
        audioRef.current.src = playingTrack.signed_url;
        audioRef.current.currentTime = startTimeSeconds;
        await audioRef.current.play();
      }

      setIsPlaying(true);
      startAnalysing();

      // Preload next track
      const nextTrack = await fetchNextTrack();
      const inactiveSlot = getInactiveSlot(activeSlot);
      loadTrackToSlot(inactiveSlot, nextTrack.signed_url);
    } catch (error) {
      console.error("Error loading track:", error);
      stopAnalysing();
    }
  }, [
    activeSlot,
    isPlaying,
    getActiveAudioRef,
    getInactiveSlot,
    loadTrackToSlot,
    calculateStartTime,
    initializeAudioContext,
    connectAudioElements,
    startAnalysing,
    stopAnalysing,
  ]);

  // Set up event listeners for track end
  useEffect(() => {
    const firstAudio = firstSlotAudioRef.current;
    const secondAudio = secondSlotAudioRef.current;

    if (firstAudio) {
      firstAudio.addEventListener("ended", handleSlotEnd);
    }
    if (secondAudio) {
      secondAudio.addEventListener("ended", handleSlotEnd);
    }

    return () => {
      if (firstAudio) {
        firstAudio.removeEventListener("ended", handleSlotEnd);
      }
      if (secondAudio) {
        secondAudio.removeEventListener("ended", handleSlotEnd);
      }
    };
  }, [handleSlotEnd]);

  return {
    isPlaying,
    handlePlayPause,
    firstSlotAudioRef,
    secondSlotAudioRef,
    frequencyData,
    isAnalysing,
  };
}
