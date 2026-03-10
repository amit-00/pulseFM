"use client";

import { cn } from "@/lib/utils";
import { useState, useRef, useEffect } from "react";
import { RainbowButton } from "@/components/ui/rainbow-button";

interface PlayerControlsProps {
  isPlaying: boolean;
  onPlayPause: () => void;
  label?: string;
  songTimeRemaining?: string;
  activeListeners?: number | null;
  className?: string;
  volume?: number;
  onVolumeChange?: (volume: number) => void;
}

export function PlayerControls({
  isPlaying,
  onPlayPause,
  label = "Live Radio",
  songTimeRemaining = "0:00",
  activeListeners = null,
  className,
  volume = 1,
  onVolumeChange,
}: PlayerControlsProps) {
  const [isVolumeHovered, setIsVolumeHovered] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const previousVolumeRef = useRef(volume);

  // Handle mute/unmute
  const handleMuteToggle = () => {
    if (isMuted) {
      // Unmute: restore previous volume
      const newVolume = previousVolumeRef.current > 0 ? previousVolumeRef.current : 0.5;
      onVolumeChange?.(newVolume);
      setIsMuted(false);
    } else {
      // Mute: save current volume and set to 0
      previousVolumeRef.current = volume;
      onVolumeChange?.(0);
      setIsMuted(true);
    }
  };

  // Update mute state when volume changes externally
  useEffect(() => {
    if (volume === 0 && !isMuted) {
      setIsMuted(true);
    } else if (volume > 0 && isMuted) {
      setIsMuted(false);
    }
  }, [volume, isMuted]);

  const handleVolumeSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newVolume = parseFloat(e.target.value);
    onVolumeChange?.(newVolume);
    if (newVolume > 0 && isMuted) {
      setIsMuted(false);
    }
  };

  const listenerLabel =
    typeof activeListeners === "number"
      ? `${activeListeners} ${activeListeners === 1 ? "listener" : "listeners"}`
      : "- listeners";

  return (
    <div className={cn("flex items-center gap-4", className)}>
      {/* Play/Pause Button with Rainbow outline effect when playing */}
      <div className="relative w-14 h-14">
        {/* Base button - always visible, behind rainbow effect */}
        <button
          onClick={onPlayPause}
          className={cn(
            "absolute inset-0 flex items-center justify-center",
            "w-14 h-14 rounded-full",
            "transition-all duration-200",
            "cursor-pointer",
            "focus:outline-none",
            "active:scale-95",
            "bg-stone-800/50",
            "z-0"
          )}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? (
            // Pause icon
            <svg
              className="w-7 h-7 text-white drop-shadow-sm"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <rect x="5" y="4" width="5" height="16" rx="2" />
              <rect x="14" y="4" width="5" height="16" rx="2" />
            </svg>
          ) : (
            // Play icon
            <svg
              className="w-7 h-7 text-white drop-shadow-sm"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M6 4.5v15a1.5 1.5 0 002.3 1.26l11.5-7.5a1.5 1.5 0 000-2.52l-11.5-7.5A1.5 1.5 0 006 4.5z" />
            </svg>
          )}
        </button>

        {/* Rainbow button overlay - fades in/out when playing */}
        <div
          className={cn(
            "absolute inset-0 transition-opacity duration-700 ease-in-out z-10",
            isPlaying ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
        >
          <RainbowButton
            variant="outline"
            size="icon"
            onClick={onPlayPause}
            className={cn(
              "w-14 h-14 rounded-full",
              "flex items-center justify-center",
              "cursor-pointer",
              "p-0"
            )}
            aria-label={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? (
              // Pause icon
              <svg
                className="w-7 h-7 text-white drop-shadow-sm"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <rect x="5" y="4" width="5" height="16" rx="2" />
                <rect x="14" y="4" width="5" height="16" rx="2" />
              </svg>
            ) : (
              // Play icon
              <svg
                className="w-7 h-7 text-white drop-shadow-sm"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M6 4.5v15a1.5 1.5 0 002.3 1.26l11.5-7.5a1.5 1.5 0 000-2.52l-11.5-7.5A1.5 1.5 0 006 4.5z" />
              </svg>
            )}
          </RainbowButton>
        </div>
      </div>

      {/* Song Label */}
      <div className="flex flex-col">
        <span className="text-stone-500 text-xs uppercase tracking-wider font-medium">
          {isPlaying ? songTimeRemaining : "Ready"}
        </span>
        <span className="text-stone-100 text-lg font-semibold tracking-tight">
          {label}
        </span>
        <span className="mt-1 flex items-center gap-1.5 text-xs text-stone-300">
          <span className="relative inline-flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 blur-[1px]" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]" />
          </span>
          {listenerLabel}
        </span>
      </div>

      {/* Volume Control */}
      {onVolumeChange && (
        <div
          className="hidden md:flex items-center gap-2 ml-auto"
          onMouseEnter={() => setIsVolumeHovered(true)}
          onMouseLeave={() => setIsVolumeHovered(false)}
        >
          {/* Mute/Unmute Button */}
          <button
            onClick={handleMuteToggle}
            className={cn(
              "relative flex items-center justify-center",
              "w-10 h-10 rounded-lg",
              "transition-all duration-200",
              "hover:bg-stone-800/50",
              "focus:outline-none focus:ring-2 focus:ring-purple-400/50 focus:ring-offset-2 focus:ring-offset-stone-950",
              "active:scale-95"
            )}
            aria-label={isMuted ? "Unmute" : "Mute"}
          >
            {isMuted || volume === 0 ? (
              // Muted icon
              <svg
                className="w-5 h-5 text-stone-400"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
              </svg>
            ) : volume < 0.5 ? (
              // Low volume icon
              <svg
                className="w-5 h-5 text-stone-300"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z" />
              </svg>
            ) : (
              // High volume icon
              <svg
                className="w-5 h-5 text-stone-300"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
              </svg>
            )}
          </button>

          {/* Volume Slider */}
          <div
            className={cn(
              "flex items-center transition-all duration-300 overflow-hidden",
              // Always visible on mobile, hover on desktop
              "w-20 opacity-100 md:w-0 md:opacity-0",
              // Show on hover for desktop
              isVolumeHovered && "md:w-24 md:opacity-100"
            )}
          >
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={volume}
              onChange={handleVolumeSliderChange}
              className={cn(
                "w-full h-1.5 rounded-full appearance-none cursor-pointer",
                "bg-stone-700/50",
                "accent-purple-500",
                "focus:outline-none focus:ring-2 focus:ring-purple-400/50 focus:ring-offset-1 focus:ring-offset-stone-950"
              )}
              style={{
                background: `linear-gradient(to right, rgb(168 85 247) 0%, rgb(168 85 247) ${volume * 100}%, rgb(68 64 60 / 0.5) ${volume * 100}%, rgb(68 64 60 / 0.5) 100%)`,
              }}
              aria-label="Volume"
            />
          </div>
        </div>
      )}
    </div>
  );
}
