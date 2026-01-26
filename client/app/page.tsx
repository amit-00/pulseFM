"use client";

import { useState, useRef } from "react";

export default function Home() {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  const handlePlayPause = async () => {
    if (isPlaying) {
      // Pause the audio
      if (audioRef.current) {
        audioRef.current.pause();
      }
      setIsPlaying(false);
    } else {
      // Play: make request to get current stream position
      try {
        // Record timestamp before making request
        const requestTimestamp = performance.now();

        // Make request to /api/stream
        const response = await fetch("/api/stream");

        if (!response.ok) {
          throw new Error("Failed to fetch stream");
        }

        // Record timestamp when response arrives
        const responseTimestamp = performance.now();

        // Calculate delta (time taken for request)
        const delta = responseTimestamp - requestTimestamp;

        // Get response data
        const { signed_url, duration_elapsed_ms } = await response.json();

        // Calculate start time: duration_elapsed_ms + delta (convert to seconds)
        const startTimeSeconds = (duration_elapsed_ms + delta) / 1000;

        // Set audio source and start time
        if (audioRef.current) {
          audioRef.current.src = signed_url;
          audioRef.current.currentTime = startTimeSeconds;
          await audioRef.current.play();
        }

        setIsPlaying(true);
      } catch (error) {
        console.error("Error loading track:", error);
      }
    }
  };

  return (
    <div className="">
      <audio ref={audioRef} controls={false} style={{ display: "none" }} />
      <button
        className="bg-blue-500 text-white p-2 rounded-md cursor-pointer"
        onClick={handlePlayPause}
      >
        {isPlaying ? "Pause" : "Play"}
      </button>
    </div>
  );
}