"use client";

import { useState, useRef, useMemo, useCallback, useEffect } from "react";

export default function Home() {
  const [isPlaying, setIsPlaying] = useState(false);
  const firstSlotAudioRef = useRef<HTMLAudioElement>(null);
  const secondSlotAudioRef = useRef<HTMLAudioElement>(null);

  const [activeSlot, setActiveSlot] = useState<"first" | "second">("first");

  const slotMap = useMemo(() => ({
    first: firstSlotAudioRef,
    second: secondSlotAudioRef,
  }), []);

  const handleSlotEnd = useCallback(async () => {
    if (!isPlaying) return;

    try {
      // Switch to the inactive slot
      const newActiveSlot = activeSlot === "first" ? "second" : "first";
      const newActiveAudioRef = slotMap[newActiveSlot];

      // Start playing the newly active slot (which should already have the next track)
      if (newActiveAudioRef.current) {
        await newActiveAudioRef.current.play();
      }

      setActiveSlot(newActiveSlot);

      // Fetch the next track for the newly inactive slot
      const nextResponse = await fetch("/api/stream/next");

      if (!nextResponse.ok) {
        throw new Error("Failed to fetch next track");
      }

      const nextTrack = await nextResponse.json();

      const newInactiveSlot = newActiveSlot === "first" ? "second" : "first";
      const newInactiveAudioRef = slotMap[newInactiveSlot];

      if (newInactiveAudioRef.current) {
        newInactiveAudioRef.current.src = nextTrack.signed_url;
        newInactiveAudioRef.current.currentTime = 0;
      }
    } catch (error) {
      console.error("Error switching slots:", error);
      setIsPlaying(false);
    }
  }, [activeSlot, slotMap, isPlaying]);

  const handlePlayPause = useCallback(async () => {
    const audioRef = slotMap[activeSlot];
    if (isPlaying) {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      setIsPlaying(false);
    } else {
      try {
        const requestTimestamp = performance.now();

        const response = await fetch("/api/stream/playing");

        if (!response.ok) {
          throw new Error("Failed to fetch stream");
        }

        const responseTimestamp = performance.now();

        const delta = responseTimestamp - requestTimestamp;

        const playingTrack = await response.json();

        const startTimeSeconds = (playingTrack.duration_elapsed_ms + delta) / 1000;

        if (audioRef.current) {
          audioRef.current.src = playingTrack.signed_url;
          audioRef.current.currentTime = startTimeSeconds;
          await audioRef.current.play();
        }

        setIsPlaying(true);

        const nextResponse = await fetch("/api/stream/next");

        if (!nextResponse.ok) {
          throw new Error("Failed to fetch next track");
        }

        const nextTrack = await nextResponse.json();

        const inactiveSlot = activeSlot === "first" ? "second" : "first";

        const inactiveAudioRef = slotMap[inactiveSlot];

        if (inactiveAudioRef.current) {
          inactiveAudioRef.current.src = nextTrack.signed_url;
          inactiveAudioRef.current.currentTime = 0;
        }
      } catch (error) {
        console.error("Error loading track:", error);
      }
    }
  }, [activeSlot, slotMap]);

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

  return (
    <div className="">
      <audio ref={firstSlotAudioRef} controls={false} style={{ display: "none" }} />
      <audio ref={secondSlotAudioRef} controls={false} style={{ display: "none" }} />
      <button
        className="bg-blue-500 text-white p-2 rounded-md cursor-pointer"
        onClick={handlePlayPause}
      >
        {isPlaying ? "Pause" : "Play"}
      </button>
    </div>
  );
}