"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { DotMatrixVisualizer } from "./DotMatrixVisualizer";
import { PlayerControls } from "./PlayerControls";
import { cn } from "@/lib/utils";

// Test audio URL - public domain music
const TEST_AUDIO_URL = "https://ff258a6047be6eb9ff3fc3e87f6939d6078f1b1df9aab909058c8f8-apidata.googleusercontent.com/download/storage/v1/b/pulsefm-generated-songs/o/raw%2Ftest.wav?jk=AUzyfrh6YtyrNhmrGrlledPJeBr-1wd8s-kVIDO37rc0tSiX7j7NnxJ2FisikFRZkJZsHTnlRdm6RDy822vj8bYE3MkNQhGnxZuHwfaeX4IGlBDPMtZjdyprqnx296EjEtGzDiaWYOzuheJ536y4mFO8A4p25J_PrAX1v8Om0XncGfCMFWj-YSsXr3QsShs1jcwv3SrPmKg4SDfFiDc-OUa10W6w5B4MnfH2h_b9zAf7f7ypEX8SzsOWDopAINiaN30M8kteuHe1u3DkTbobOUjkNPiYJwAYfl1xhHQIdchSkjZLe-n34W1vzqP7EwJqVoCWTjP6ML7-NCzS-IB26xXtHRM4Tu7prke25qQQ6UvAFXbFMpgxnGBsKyYoY6ZEU3ZyFQ_NjyIS8vBDUu0Pge5c89uk9LDnTc8_cpbP0rC_N7gwsG2BjVLlmuK2thwy84-W9ajLfn7sI9aAkiaFbFDJRKTj3gDYlzGLbOEZcegKVI89IQRbD07g9MadAe1WsmoUsdLtb1_zpZJfoQk_7-ClLL-bkjoxPTuq7wndOAJYKcAndIIxlnpdNBYiFenjTWNVNMDN9cqm5dY0Vz76WYlkK3v2RH7r0usdf5MEoCcpbu805NXyrcBQcl2HTnRUclYqKKOxtsQY6DSssqtklLRozGCpSZJPOsDnVqR3P5HWANnGZfllYXw94p_6hmAPZOw4Y83AgNRN7ehnHPUI_5EnwpAU0bGxg9ZXjW35tq-6robYhDze4uiHqD9FedQnZ3HysfHpa6ODcYop_dvL5Yk0uIJTY3Gjd4hWZzTpMOQO8X6TrkD5qVbNj1Mo_GWh0Thtx4bUrnlU6hDmHsjVwVrvnVz9Ho206zR-KesHSAVtPo3rKqG5HXoiRY6Nwh-gbM_4Q8axn0NViRHTfrF3DwvXBDsKRsM_d47ZBxyHMoPX52KaB3DTLu8c4am5pyjoIFz_9yEJg7L9n9ePgRuXb-8ENSPRb31CmibPRWSJT7eZx2yTuBieHqUC5Jpbm5Vcn8BkneYcBa3LOep14t0-YjuaJZbNAE-hpiZ-KV0IjXi_P-TIvXz7yfcW4nVfpxppWwFn0SwLhn6A2ouGX9cmKAHwf9SWv-EvmWCg8j-iKnDAfm-WYa5n02IvUbMsrjx55E1ghXhcYQbGS8R_rJEEbOxz2JEkHt0bEXmz_XyLK5qDJ8o1LMhFhiCey5TWhc-u45AnCXL-0-_95Q&isca=1";

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
        "grid grid-rows-[1fr_auto] h-full w-full",
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

      {/* Dot Matrix Visualizer - fills remaining space */}
      <div className="w-full h-full min-h-0 px-4 pt-4 pb-4 sm:px-6 sm:pt-6 sm:pb-6 md:px-8 md:pt-8 md:pb-6">
        <DotMatrixVisualizer
          frequencyData={frequencyData}
          isActive={isAnalysing}
        />
      </div>

      {/* Player Controls - fixed height at bottom */}
      <div className="w-full px-4 pb-4 sm:px-6 sm:pb-6 md:px-8 md:pb-8">
        <div className="w-full p-4 sm:p-5 rounded-2xl bg-slate-900/50 border border-slate-800/30">
          <PlayerControls
            isPlaying={isPlaying}
            onPlayPause={handlePlayPause}
            label="pulseFM Radio"
          />
        </div>
      </div>
    </div>
  );
}

