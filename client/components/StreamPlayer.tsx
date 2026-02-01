"use client"

import { Play, Pause } from "lucide-react"
import { useStreamPlayer } from "@/hooks/useStreamPlayer"
import { cn } from "@/lib/utils"

export function StreamPlayer() {
  const { isPlaying, handlePlayPause, firstSlotAudioRef, secondSlotAudioRef } = useStreamPlayer()

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Hidden audio elements */}
      <audio ref={firstSlotAudioRef} controls={false} style={{ display: "none" }} />
      <audio ref={secondSlotAudioRef} controls={false} style={{ display: "none" }} />

      {/* Player UI */}
      <div className="flex flex-col items-center gap-4">
        <button
          onClick={handlePlayPause}
          className={cn(
            "relative flex items-center justify-center",
            "w-20 h-20 rounded-full",
            "bg-slate-800 border-2 border-slate-700",
            "hover:bg-slate-700 hover:border-slate-600",
            "transition-all duration-200",
            "focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 focus:ring-offset-slate-950",
            "active:scale-95"
          )}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? (
            <Pause className="w-8 h-8 text-slate-50" fill="currentColor" />
          ) : (
            <Play className="w-8 h-8 text-slate-50 ml-1" fill="currentColor" />
          )}
        </button>

        <div className="text-center">
          <p className="text-sm text-slate-400">
            {isPlaying ? "Now Playing" : "Ready to Play"}
          </p>
        </div>
      </div>
    </div>
  )
}

