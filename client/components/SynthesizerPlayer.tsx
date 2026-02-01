"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { DotMatrixVisualizer } from "./DotMatrixVisualizer";
import { WaveformVisualizer } from "./WaveformVisualizer";
import { PlayerControls } from "./PlayerControls";
import { RequestForm } from "./RequestForm";
import { AuroraText } from "./ui/aurora-text";
import { cn } from "@/lib/utils";

type VisualizerType = "waveform" | "dotmatrix";

// Test audio URL - public domain music
const TEST_AUDIO_URL = "https://ff737b904534f861a307e21e393a68128338b82a52ff9378279f705-apidata.googleusercontent.com/download/storage/v1/b/pulsefm-generated-songs/o/raw%2Ftest.wav?jk=AUzyfrgOrBRO7Nc0rXf3DpSX5Mj2uQRYK8-bdLe1UDPFkZmgxX-K9Oplw6XdK36f2cm9XzPcDT5I48a_Z2DZsruqHeHw1a6gvGpQm05oVMqMVgPPQcDT4AqNeiY-G6ImFgROFU3sXZPveCBn7aukW35DWfPZ003h36potbNxQPYMHfGECstJOEZjDD1LVDH4kOnbvFXXaYPos4Qt9pXREVUQPBPuAZWXgvd1VS33W_cLHwDwhJS9baFNPU9YFKQ_m3rtDvhaDBu-_nS4liXkqM3TYQjP0dbWJ8FjA1by_5iVl9SxX9XSSOruSRckQOat8xvbyb4fsGwUZPJHcZrxnvPp8JbfM8M-s7Np0RtHgI9TAaqLlyhaPOZkPMLXy_RqDPi0pbQraa3vszCwHBkyV38vuhtJFACrG-cxoSN11enlPJhRYqnS19ad8s7I1UxEShrrxS38S7hlmzIpeYm6qAPDU_xv_CMaFfutzpqjyJ9i14HwD3JNvSi16k4ZYKn9leZ9eIRfRS6jjx4aG4V32S3pYz8H3ys0lMpgC-NP0vGyCxDtlyUvBR4LRbQ3z4OkQ79n_VHfJdeayMGP18Rc2TI0zt8KbFQQRUOEDQ5KzWsly7N4MXFC72eebeYEwtezHUBflbGuwbKoaUxDyTKWeSs0PM8CfWSbvfi0afcZQEf8SuU7PtlaH2FBYoPccA-x1dPxU4Ge1CbEQFS5RV3sJ3X-ZhQnDcJnNvnYk5ewsRF7R28Vufudossm9hwPeRWl4h2L40FVLjLzxY9VxXQJbXt23WeUrefuueKuOj_tcWA3SWI_f1GlPYlRaIU-KfP9c_cdeSoM50pMMqU3yPFJlb74p0_sjTXlOijtDk873YYn5mn0wJm2hMTxzsrQWhaCSyczwqsm7c6SzIH7Mq3HwD-tAfplGzspmQ30cmFuhVZcmxniLU5IVhVE2UBi3_hheK9Ho2kc3Zdh7H4Pu6C7SQ1OWWmX1ocjuF2NwhJIWmJ707W1D-kLBwP6S_jJSw7d8FkSyYL_r_LE-uyJjh3JK1kFvC4FkD-oLfE3YqzNNO94KWtMn8Na-hO1tHjaHH0vWwO0yeYelKYDRSzWtonLCy6_bDnYTbKJikRAuQ32OCuAs9bjlZwQLc39LAcfOkq5RtUR3lKFdIkFw78kE2iH-lgnFddWg-y648mWNQoT7JZtTuMrmT5_u8c5pKnXtIxBg2N0dgS1VCC40w&isca=1";

interface SynthesizerPlayerProps {
  className?: string;
}

export function SynthesizerPlayer({ className }: SynthesizerPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [frequencyData, setFrequencyData] = useState<Uint8Array>(new Uint8Array(32));
  const [isAnalysing, setIsAnalysing] = useState(false);
  const [volume, setVolume] = useState(1); // Volume range: 0 to 1
  const [visualizer, setVisualizer] = useState<VisualizerType>("waveform"); // Default to waveform

  // Initialize audio context and analyser
  const initializeAudio = useCallback(() => {
    if (!audioRef.current || audioContextRef.current) return;

    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();

    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.8;
    analyser.minDecibels = -90;
    analyser.maxDecibels = -10;

    const source = audioContext.createMediaElementSource(audioRef.current);
    source.connect(analyser);
    analyser.connect(audioContext.destination);

    audioContextRef.current = audioContext;
    analyserRef.current = analyser;
    sourceRef.current = source;
  }, []);

  // Start frequency analysis loop
  const startAnalysing = useCallback(() => {
    if (!analyserRef.current) return;

    setIsAnalysing(true);
    const analyser = analyserRef.current;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const updateFrequencyData = () => {
      analyser.getByteFrequencyData(dataArray);
      setFrequencyData(new Uint8Array(dataArray));
      animationFrameRef.current = requestAnimationFrame(updateFrequencyData);
    };

    updateFrequencyData();
  }, []);

  // Stop frequency analysis
  const stopAnalysing = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    setIsAnalysing(false);
    setFrequencyData(new Uint8Array(32));
  }, []);

  // Handle play/pause
  const handlePlayPause = useCallback(async () => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
      stopAnalysing();
      return;
    }

    try {
      initializeAudio();

      // Resume audio context if suspended
      if (audioContextRef.current?.state === "suspended") {
        await audioContextRef.current.resume();
      }

      await audioRef.current.play();
      setIsPlaying(true);
      startAnalysing();
    } catch (error) {
      console.error("Error playing audio:", error);
    }
  }, [isPlaying, initializeAudio, startAnalysing, stopAnalysing]);

  // Handle volume change
  const handleVolumeChange = useCallback((newVolume: number) => {
    setVolume(newVolume);
    if (audioRef.current) {
      audioRef.current.volume = newVolume;
    }
  }, []);

  // Sync volume with audio element
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = volume;
    }
  }, [volume]);

  // Handle audio ended
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleEnded = () => {
      setIsPlaying(false);
      stopAnalysing();
    };

    audio.addEventListener("ended", handleEnded);
    return () => audio.removeEventListener("ended", handleEnded);
  }, [stopAnalysing]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  return (
    <div
      className={cn(
        "relative h-full w-full",
        className
      )}
    >
      {/* Hidden audio element for testing */}
      <audio
        ref={audioRef}
        src={TEST_AUDIO_URL}
        crossOrigin="anonymous"
        preload="auto"
        style={{ display: "none" }}
      />

      {/* Visualizer - fills entire container */}
      <div className="absolute inset-0">
        {visualizer === "waveform" ? (
          <WaveformVisualizer
            frequencyData={frequencyData}
            isActive={isAnalysing}
          />
        ) : (
          <DotMatrixVisualizer
            frequencyData={frequencyData}
            isActive={isAnalysing}
          />
        )}
      </div>

      {/* Pulse FM Widget - top left */}
      <div className="absolute top-4 left-4 sm:top-6 sm:left-6 md:top-8 md:left-8 pointer-events-none">
        <div
          className={cn(
            "px-4 py-2 md:px-6 md:py-3 lg:px-8 lg:py-4",
            "rounded-lg md:rounded-xl lg:rounded-2xl",
            "bg-stone-950/50 backdrop-blur-sm border border-stone-800/30"
          )}
        >
          <span className="text-lg md:text-2xl lg:text-3xl xl:text-4xl font-bold tracking-tight text-stone-100">
            Pulse{" "}
            <AuroraText className="italic" active={isPlaying}>
              FM
            </AuroraText>
          </span>
        </div>
      </div>

      {/* Top right widgets - Visualizer Toggle + Live Indicator */}
      <div className="absolute top-4 right-4 sm:top-6 sm:right-6 md:top-8 md:right-8 flex items-center gap-2 md:gap-3">
        {/* Visualizer Toggle Button */}
        <button
          onClick={() => setVisualizer(visualizer === "waveform" ? "dotmatrix" : "waveform")}
          className={cn(
            "flex items-center gap-2",
            "px-3 py-2 md:px-4 md:py-2.5",
            "rounded-lg md:rounded-xl",
            "bg-stone-950/50 backdrop-blur-sm border border-stone-700/30",
            "text-stone-400 hover:text-stone-200 hover:border-stone-600/50",
            "transition-all duration-200"
          )}
        >
          {visualizer === "waveform" ? (
            <>
              {/* Grid/Matrix icon */}
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
              {/* Waveform icon */}
              <svg className="w-4 h-4 md:w-5 md:h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M2 12h2l2-6 3 12 3-8 2 4 2-2h6" />
              </svg>
              <span className="text-xs md:text-sm font-medium">Wave</span>
            </>
          )}
        </button>

        {/* Live Indicator */}
        <div
          className={cn(
            "flex items-center gap-2 md:gap-3",
            "px-3 py-2 md:px-4 md:py-2.5 lg:px-5 lg:py-3",
            "rounded-lg md:rounded-xl",
            "bg-stone-950/50 backdrop-blur-sm border",
            "transition-all duration-300 pointer-events-none",
            isPlaying
              ? "border-red-500/30 shadow-lg shadow-red-500/10"
              : "border-stone-700/30 opacity-50"
          )}
        >
          <span className="relative flex h-2.5 w-2.5 md:h-3 md:w-3 lg:h-3.5 lg:w-3.5">
            {isPlaying && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            )}
            <span
              className={cn(
                "relative inline-flex rounded-full h-2.5 w-2.5 md:h-3 md:w-3 lg:h-3.5 lg:w-3.5 transition-colors duration-300",
                isPlaying ? "bg-red-500" : "bg-stone-500"
              )}
            />
          </span>
          <span
            className={cn(
              "text-xs md:text-sm lg:text-base font-semibold uppercase tracking-wider transition-colors duration-300",
              isPlaying ? "text-red-400" : "text-stone-500"
            )}
          >
            Live
          </span>
        </div>
      </div>

      {/* Overlay - unified controls panel */}
      <div className="absolute inset-x-0 bottom-0 px-4 pb-4 sm:px-6 sm:pb-6 md:px-8 md:pb-8 pointer-events-none">
        <div className="w-full p-4 sm:p-5 rounded-2xl bg-stone-950/50 backdrop-blur-sm border border-stone-800/20 pointer-events-auto">
          <div className="flex flex-col md:flex-row gap-4 md:gap-6 md:items-center">
            {/* Player Controls */}
            <div className="flex-1">
              <PlayerControls
                isPlaying={isPlaying}
                onPlayPause={handlePlayPause}
                label="pulseFM Radio"
                volume={volume}
                onVolumeChange={handleVolumeChange}
              />
            </div>

            {/* Divider */}
            <div className="hidden md:block w-px h-16 bg-stone-700/30" />
            <div className="md:hidden h-px w-full bg-stone-700/30" />

            {/* Request Form - inline */}
            <div className="flex-1 md:max-w-md">
              <RequestForm isPlaying={isPlaying} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

