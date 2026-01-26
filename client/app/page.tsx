"use client";

import { useStreamPlayer } from "../hooks/useStreamPlayer";

export default function Home() {
  const {
    isPlaying,
    handlePlayPause,
    firstSlotAudioRef,
    secondSlotAudioRef
  } = useStreamPlayer();

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