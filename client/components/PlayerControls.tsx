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
      {/* Play/Pause Button with Aurora effect */}
      <button
        onClick={onPlayPause}
        className={cn(
          "relative flex items-center justify-center",
          "w-14 h-14 rounded-full",
          "transition-all duration-200",
          "focus:outline-none focus:ring-2 focus:ring-purple-400/50 focus:ring-offset-2 focus:ring-offset-slate-950",
          "active:scale-95",
          "shadow-lg shadow-purple-500/20",
          "overflow-hidden"
        )}
        aria-label={isPlaying ? "Pause" : "Play"}
      >
        {/* Aurora gradient background */}
        <span
          className="absolute inset-0 animate-aurora bg-[length:200%_auto]"
          style={{
            backgroundImage: "linear-gradient(135deg, #FF0080, #7928CA, #0070F3, #38bdf8, #FF0080)",
            animationDuration: "4s",
          }}
        />
        {/* Overlay for depth */}
        <span className="absolute inset-0 bg-black/10" />
        
        {isPlaying ? (
          // Pause icon
          <svg
            className="relative z-10 w-7 h-7 text-white drop-shadow-sm"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <rect x="5" y="4" width="5" height="16" rx="2" />
            <rect x="14" y="4" width="5" height="16" rx="2" />
          </svg>
        ) : (
          // Play icon
          <svg
            className="relative z-10 w-7 h-7 text-white drop-shadow-sm"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M6 4.5v15a1.5 1.5 0 002.3 1.26l11.5-7.5a1.5 1.5 0 000-2.52l-11.5-7.5A1.5 1.5 0 006 4.5z" />
          </svg>
        )}
      </button>

      {/* Song Label */}
      <div className="flex flex-col">
        <span className="text-slate-500 text-xs uppercase tracking-wider font-medium">
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
