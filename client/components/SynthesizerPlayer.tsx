"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { DotMatrixVisualizer } from "./DotMatrixVisualizer";
import { PlayerControls } from "./PlayerControls";
import { cn } from "@/lib/utils";

// Test audio URL - public domain music
const TEST_AUDIO_URL = "https://ff3213bfd0a636af35a36442f16029ad976cf16a70c6e6c881a0bb3-apidata.googleusercontent.com/download/storage/v1/b/pulsefm-generated-songs/o/raw%2Ftest.wav?jk=AUzyfrhGToS_TmPHHA3kgalv3-jtdoOeuoRNqYFWjh0vYcW9Sh25SELPw-D5qcoKABBux4evnnVKwsyZYLHkf96-LJHo_4SbFajuKbeOMyTRypNvZ0PtDTKLEVJASPSB15HKpL3LqKkQqH4mhFZEmAgpiEL-MQiepsn0k-hNiNOtT0RT0-DGEsKfOvGmKTaeU8WkblmEIPzgu4avGwqVPeIyg3dXLbH3ECeH5emtl7GWKfUW4kTc_nET5L5X1iClZRPPB46s3boy3-meYeGKukMCtFGUMp-f8lx1cBw3lX2y5BArk9YUiZ2uTmEEeisnisRz287FwNg6Uq2a_AbvlhzOdzlbGDR6n3WlgpgfHnAeXpjyuXxlUkg-o3lxUfL6PoYOwvyVqdg32cNga3vifJ8aVUQ4kDjDag_fcImAEO2Qzg1aTUb5dS4PgSe55-srhc2JQwhYoo3El_f9z0V2lV6CQMdL0zr7N-cBSxtrMijnfXeB_jB4UOAxUU-hjjv182U-G3-uPbNP_4i2u-lYOlrypiOV01k9xX3Wv2XgEOklPCR07pYhayT-AjAsypkryEhSrn7Oa6Nz7XIkwKvmnnmARpDk7d6WPJjpSolfDAdeudtuJyssC6jy00k0Ny838IsudiEovXZ4gAFf6UxTgjrRI7t_mBHvRAV0NbDYc5iCJRo00xkUOpS3hDToilmWQD2KMMgF1Ln1caW9l5tZla0skaXL6evpODtHzFm1-n2YnSgOql5z0MT7sjRwzd0BTcgyXZSfY-npgTgAnl6Fk-Ml0QktzBhhBddlXwKHekqeGeqHhmTN6KU0CvDeZekbGhXiWNLb3hswwtNlZhLWt4XqB8d9sJqyuPStpVoRq3BTuns8gXYGvGWR73O9MHQoeO3O5fBjIbpMsmiQMmFFxHkTz_CgBwRBeueL4Xfnt8Y3PK7pTvOzb5BWE7JlUlqbPJTcuruNDzvNxe6pWTr8OsRf6pR-V67Maei7_m9HkWOE90cxQbpjJOu-IYdAU2VZGOI9zHIb9K7SBllv0E3d8qf_OlNa6R0InQiPev4AuyN1NOTUZJ6xxXn6oh0uPlqKohU3g7sMi9wGdhZWEW9lgtdAHqnjLk3-S-uz8ZMFQqKvp-y03yzxp9Liv3A6AtD6Tpy4jjnJ4CQ7a9nvbwUebzess-HvgVfpJFv3orLKKwFZeIj48JzxmYh5pPnsRUo59Lm8_qywWzFk&isca=1";

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
        "grid grid-rows-[1fr_auto] min-h-screen h-screen w-full",
        "bg-slate-950",
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
      <div className="w-full h-full min-h-0 p-4 sm:p-6 md:p-8">
        <DotMatrixVisualizer
          frequencyData={frequencyData}
          isActive={isAnalysing}
        />
      </div>

      {/* Player Controls - fixed height at bottom */}
      <div className="w-full px-4 pb-6 sm:px-6 sm:pb-8 md:px-8 md:pb-10">
        <div className="w-full p-4 sm:p-5 rounded-2xl bg-slate-900/80 border border-slate-800/50 backdrop-blur-sm">
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

