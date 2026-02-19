"use client";

import { useState } from "react";

import { DotMatrixVisualizer } from "./DotMatrixVisualizer";
import { WaveformVisualizer } from "./WaveformVisualizer";
import { PlayerControls } from "./PlayerControls";
import { VotePanel } from "./VotePanel";
import { AuroraText } from "./ui/aurora-text";
import { useStreamPlayer } from "@/hooks/useStreamPlayer";
import { cn } from "@/lib/utils";

type VisualizerType = "waveform" | "dotmatrix";

interface SynthesizerPlayerProps {
  className?: string;
}

export function SynthesizerPlayer({ className }: SynthesizerPlayerProps) {
  const [visualizer, setVisualizer] = useState<VisualizerType>("waveform");
  const {
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
    activeListeners,
    isExpired,
    streamError,
    volume,
    setVolume,
  } = useStreamPlayer();

  return (
    <div className={cn("relative h-full w-full", className)}>
      <audio
        ref={firstSlotAudioRef}
        controls={false}
        preload="auto"
        crossOrigin="anonymous"
        style={{ display: "none" }}
      />
      <audio
        ref={secondSlotAudioRef}
        controls={false}
        preload="auto"
        crossOrigin="anonymous"
        style={{ display: "none" }}
      />

      <div className="absolute inset-0">
        {visualizer === "waveform" ? (
          <WaveformVisualizer frequencyData={frequencyData} isActive={isAnalysing} />
        ) : (
          <DotMatrixVisualizer frequencyData={frequencyData} isActive={isAnalysing} />
        )}
      </div>

      <div className="absolute top-4 left-4 sm:top-6 sm:left-6 md:top-8 md:left-8 pointer-events-none">
        <div
          className={cn(
            "px-4 py-2 md:px-6 md:py-3 lg:px-8 lg:py-4",
            "rounded-lg md:rounded-xl lg:rounded-2xl",
            "bg-stone-950/50 backdrop-blur-sm border border-stone-800/30",
          )}
        >
          <span className="text-lg md:text-2xl lg:text-3xl xl:text-4xl font-bold tracking-tight text-stone-100">
            Pulse <AuroraText className="italic" active={isPlaying}>FM</AuroraText>
          </span>
        </div>
      </div>

      <div className="absolute top-4 right-4 sm:top-6 sm:right-6 md:top-8 md:right-8 flex items-center gap-2 md:gap-3">
        <button
          onClick={() => setVisualizer(visualizer === "waveform" ? "dotmatrix" : "waveform")}
          className={cn(
            "flex items-center gap-2",
            "px-3 py-2 md:px-4 md:py-2.5",
            "rounded-lg md:rounded-xl",
            "bg-stone-950/50 backdrop-blur-sm border border-stone-700/30",
            "text-stone-400 hover:text-stone-200 hover:border-stone-600/50",
            "transition-all duration-200",
          )}
        >
          {visualizer === "waveform" ? (
            <>
              <svg className="w-4 h-4 md:w-5 md:h-5" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="6" cy="6" r="2" />
                <circle cx="12" cy="6" r="2" />
                <circle cx="18" cy="6" r="2" />
                <circle cx="6" cy="12" r="2" />
                <circle cx="12" cy="12" r="2" />
                <circle cx="18" cy="12" r="2" />
                <circle cx="6" cy="18" r="2" />
                <circle cx="12" cy="18" r="2" />
                <circle cx="18" cy="18" r="2" />
              </svg>
              <span className="text-xs md:text-sm font-medium">Matrix</span>
            </>
          ) : (
            <>
              <svg
                className="w-4 h-4 md:w-5 md:h-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              >
                <path d="M2 12h2l2-6 3 12 3-8 2 4 2-2h6" />
              </svg>
              <span className="text-xs md:text-sm font-medium">Wave</span>
            </>
          )}
        </button>

        <div
          className={cn(
            "flex items-center gap-2 md:gap-3",
            "px-3 py-2 md:px-4 md:py-2.5 lg:px-5 lg:py-3",
            "rounded-lg md:rounded-xl",
            "bg-stone-950/50 backdrop-blur-sm border",
            "transition-all duration-300 pointer-events-none",
            isPlaying ? "border-red-500/30 shadow-lg shadow-red-500/10" : "border-stone-700/30 opacity-50",
          )}
        >
          <span className="relative flex h-2.5 w-2.5 md:h-3 md:w-3 lg:h-3.5 lg:w-3.5">
            {isPlaying && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            )}
            <span
              className={cn(
                "relative inline-flex rounded-full h-2.5 w-2.5 md:h-3 md:w-3 lg:h-3.5 lg:w-3.5 transition-colors duration-300",
                isPlaying ? "bg-red-500" : "bg-stone-500",
              )}
            />
          </span>
          <span
            className={cn(
              "text-xs md:text-sm lg:text-base font-semibold uppercase tracking-wider transition-colors duration-300",
              isPlaying ? "text-red-400" : "text-stone-500",
            )}
          >
            Live
          </span>
        </div>
      </div>

      <div className="absolute inset-x-0 bottom-0 px-4 pb-4 sm:px-6 sm:pb-6 md:px-8 md:pb-8 pointer-events-none">
        <div className="w-full p-4 sm:p-5 rounded-2xl bg-stone-950/50 backdrop-blur-sm border border-stone-800/20 pointer-events-auto">
          <div className="flex flex-col md:flex-row gap-4 md:gap-6 md:items-center">
            <div className="flex-1">
              <PlayerControls
                isPlaying={isPlaying}
                onPlayPause={handlePlayPause}
                label="pulseFM Radio"
                songTimeRemaining={formattedSongTime}
                activeListeners={activeListeners}
                volume={volume}
                onVolumeChange={setVolume}
              />
            </div>

            <div className="hidden md:block w-px h-16 bg-stone-700/30" />
            <div className="md:hidden h-px w-full bg-stone-700/30" />

            <div className="flex-1 md:max-w-md">
              <VotePanel
                voteData={voteData}
                formattedTime={formattedTime}
                isExpired={isExpired}
                hasVoted={hasVoted}
                selectedOption={selectedOption}
                isSubmitting={isSubmittingVote}
                error={voteError || streamError}
                onSubmitVote={submitVote}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
