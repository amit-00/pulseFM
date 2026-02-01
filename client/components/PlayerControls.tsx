"use client";

import { cn } from "@/lib/utils";

interface PlayerControlsProps {
  isPlaying: boolean;
  onPlayPause: () => void;
  label?: string;
  className?: string;
}

export function PlayerControls({
  isPlaying,
  onPlayPause,
  label = "Live Radio",
  className,
}: PlayerControlsProps) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      {/* Play/Pause Button */}
      <button
        onClick={onPlayPause}
        className={cn(
          "relative flex items-center justify-center",
          "w-14 h-14 rounded-full",
          "bg-emerald-500 hover:bg-emerald-400",
          "transition-all duration-200",
          "focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-950",
          "active:scale-95",
          "shadow-lg shadow-emerald-500/25"
        )}
        aria-label={isPlaying ? "Pause" : "Play"}
      >
        {isPlaying ? (
          // Pause icon
          <svg
            className="w-6 h-6 text-slate-950"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
        ) : (
          // Play icon (slightly offset for visual centering)
          <svg
            className="w-6 h-6 text-slate-950 ml-0.5"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M8 5.14v14.72a1 1 0 001.5.86l11-7.36a1 1 0 000-1.72l-11-7.36a1 1 0 00-1.5.86z" />
          </svg>
        )}
      </button>

      {/* Song Label */}
      <div className="flex flex-col">
        <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">
          {isPlaying ? "Now Playing" : "Ready"}
        </span>
        <span className="text-slate-100 text-lg font-semibold tracking-tight">
          {label}
        </span>
      </div>

      {/* Live indicator */}
      {isPlaying && (
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
          </span>
          <span className="text-red-400 text-xs font-semibold uppercase tracking-wider">
            Live
          </span>
        </div>
      )}
    </div>
  );
}

