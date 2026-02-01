"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { DotMatrixVisualizer } from "./DotMatrixVisualizer";
import { PlayerControls } from "./PlayerControls";
import { cn } from "@/lib/utils";

// Test audio URL - public domain music
const TEST_AUDIO_URL = "https://ff7d565e616bdfbf9951ec238af246ffaee3187d9615a5d92a02a56-apidata.googleusercontent.com/download/storage/v1/b/pulsefm-generated-songs/o/raw%2Ftest.wav?jk=AUzyfrjBMciPiXyFJGrJHuKklGvH4S21m8E8TL4pd_fRuvFK-yynNbUMsUyOZDn60sFyJMfEoGWqvOmnIFPh3CoLhsB2WxoCR-iHgyzifNWLL6jCBQfM01Bqo2Z0U1AHCwY71QkvBsPboxPp3Gc-kQ2ocrNwd8YJMVWNv3OpNK34sw24EHQ4bZP9f1dXO_fEw6ZzGh6OVADVjXbfDsKmCXLqjGmiRRPlbP_v-qDL0fvQBzz9sE2u9Q-4NjjpbnuRLk3digeok8Ei6O1BZn_CBoDG21QhpAnFXZWRyhnt7baqe8jMPwJsk2u7k_mygB62xFfVwO-QiTnE5h_e4KuknCLUvyWtxW5VIDLHf9RWNOSAj8f_AOPg37umyE0lpgDq0iG17BsDmmbu7auMG3YbA7YW2r9bJ-MY5Q2OmVkCAd7dxWKI9K1giQhb7rmQLtZNWSvOzXorzBU3mRNXfVTMosTZkpBAat_bmPPhdj42oBfj6ATvGT1oJvebiWMFbzuI99-8evp-xm-LlWDfGVz_pNE7WI7Lk5MmrBjuRGawrwlM3Hx-UdJVZm3t7p661dFXylP7lCZOo_K9D7g58gx3VlykMyk4Xn2BYyBG1BbcJdZ3SlxJv2Dobqu5VHae4oCZ-yxN2rUqhpRTZGte25V1j94Iv7M4-_Oy_L_wET2jjdhK8-4s9MODPhgmivtHGmdGOrGQ6u_eUskurO9jEWM1a6TjM3KZuUq8sgT533E0r6XhoHIYCyFeQAHL-Dahd70MyVMbNkInMR1veRJX4mKGg9uurjh01XCJlt3YB1p8EUDjbWnINqqXR5AwMlKQDBm5NDfnnCGm6Ks57sS1KUSWzq1Tb0CEwjKc23zztsBQGz7cr1ygpTnH1vJIGC_aL8unx9C2ciBCDzRLdoeHrR-GJpTPWv2IeZrZE3PrkiKo8q8RudyKxVJ5yRolhm-x4IWshoTL14jFTHt74AY0_xdCKi5uAvWtTnqHFk6qg_Yn1wZjCsQsKGKTCWtoMJfwkV1u5nci7p2l-74a-7vFVFCIWmpVD53pOa2xqJO9cxKEVnIS1MWYvSDJmioMyTr_ckCtATvMcjTyjyLYNJc7_T1K94mBEyyZGXRMs7JP4UdPnpIIVN1ZDt2_SRm5odTe0daogmUHzf3iQYyrfkru5x--06TSiZdMshjYR_Q0PTdIV6YGN4U6fr9P7w_wn8ewCzxSr7AwqpzckradjA&isca=1";

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
        "grid grid-rows-[1fr_auto] min-h-[400px] h-full w-full",
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

