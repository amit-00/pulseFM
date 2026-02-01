"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { DotMatrixVisualizer } from "./DotMatrixVisualizer";
import { PlayerControls } from "./PlayerControls";
import { RequestForm } from "./RequestForm";
import { cn } from "@/lib/utils";

// Test audio URL - public domain music
const TEST_AUDIO_URL = "https://ff13b79853fba51a1afc6264bde53f65a70611ff7e5b026bc3a8837-apidata.googleusercontent.com/download/storage/v1/b/pulsefm-generated-songs/o/raw%2Ftest.wav?jk=AUzyfrjEMSNxHj4BzgSXyCrjgUOAisw1oeDWyhA3yICWyWKuegrtLfB32yIc9vi7peWARm3UC1PGSHW_r8LBzVVz_dzDfQ4BLboBZT-shJP0B8d22xphU93s41eHiK4PYfXoasE3K_tTk5vwPKmKqwN7GXmiprq_hkhz2gRn9xM81rm_0VidYXtzxxQv2T9rQWKq3pWzlLxnSTUwvlmw8nfcKMuBcFceoYo4NuoAmqWcvcuqpF_fdjq5L3yokSjHspoj3BfVXu0Ma_E_Kvkvu2oCbaH2ZFon0hzk--iQIivOSXUE00NPrORtDHUHZDlcc3n-rQzsBvH8QcjpsHtkHIbSt5l4py2h7XltmkyrmR1aY2LX99_TUVEMoX0FlS_ymJSO1JnYxaAekSL2zV1HeP9EwCS3zSUWG3zRK3bZOaHCHbsR5Al6YJ6IoBOeHOIdTp37qoWEndqdadQFfPPmEDBkBU4JlXZUEHmdsUe-n0FpFl-JURnPp0_HV-Z8FQs3edqIzxsTP2LR1-8lCmV4aYEWL1o79mEG9MpYJMsTTrMbe2skLFfHEkckYw13y5rUrrLnfoi_wd1tVNdXym0f08xmP8R_6UuSNAd7krSwEImaBLzKBBil_AOiAZhlcc5sYfDTVgJRUZXh-JM3sp4AVhaia3Hqxo2BZ1mAImpDou3E8EKl5flZ0Mp_cGyaUTsU8VXmKdBn0fBbn4soffzfPC00vsaCbUIaLpA1axR1U13AoWHC2fFUZISP0t7MP3L10Vd9P2yR3bbRLeoKFNEoJrWrGBtoroYy-DPJD_6UyIoRtpkxOgOxxe5JgXx61A8N23bb9VqtB_PLYIYQ9cK0AiJ9unFs2d7LjEqpM8S7523zZ_iMLIkfwdXB_4EdiQXvtdbLe_d-d4E37q-cppS5hjd5PqMVn8aoN1k_Q406H7QmyjX0nlmcu8wIy3scNIgt0kS8cYhu-c4yjG4nRIooDzNoIWaPSQNzlXcDaDcnyPFG1WDO61R42J9YiWhEjH0qSSyon3XXMsP5hDwVdbyPifqzbtvH02s-3SST9xjD5h0j9iV-zN_-YrukUuIbmx-RXW9KXouKLCgtxlpNfX7UkrArfk3TLnAvilDW6K4Eyvn-wcy0cULY8nNjvBjt7LQTx5arBawKOr0HbmugwRrQpnmVPqjF_uFL3zddXN-0mGPRZV-ofugBSFHIk1PmpfPR0HUmQQiAvokEEA&isca=1";

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
        "relative min-h-[400px] h-full w-full",
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

      {/* Dot Matrix Visualizer - fills entire container */}
      <div className="absolute inset-0">
        <DotMatrixVisualizer
          frequencyData={frequencyData}
          isActive={isAnalysing}
        />
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
              />
            </div>

            {/* Divider */}
            <div className="hidden md:block w-px h-16 bg-stone-700/30" />
            <div className="md:hidden h-px w-full bg-stone-700/30" />

            {/* Request Form - inline */}
            <div className="flex-1 md:max-w-md">
              <RequestForm />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

