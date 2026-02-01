import { useRef, useCallback, useState, useEffect } from "react";

interface AudioAnalyserState {
  frequencyData: Uint8Array;
  isAnalysing: boolean;
}

export function useAudioAnalyser() {
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodesRef = useRef<Map<HTMLAudioElement, MediaElementAudioSourceNode>>(new Map());
  const animationFrameRef = useRef<number | null>(null);
  
  const [frequencyData, setFrequencyData] = useState<Uint8Array>(new Uint8Array(32));
  const [isAnalysing, setIsAnalysing] = useState(false);

  // Initialize AudioContext and AnalyserNode
  const initializeAudioContext = useCallback(() => {
    if (audioContextRef.current) return audioContextRef.current;

    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    
    // Configure analyser for visualizer
    analyser.fftSize = 64; // Results in 32 frequency bins
    analyser.smoothingTimeConstant = 0.8;
    analyser.minDecibels = -90;
    analyser.maxDecibels = -10;
    
    analyser.connect(audioContext.destination);
    
    audioContextRef.current = audioContext;
    analyserRef.current = analyser;
    
    return audioContext;
  }, []);

  // Connect an audio element to the analyser
  const connectAudioElement = useCallback((audioElement: HTMLAudioElement) => {
    const audioContext = initializeAudioContext();
    
    // Check if already connected
    if (sourceNodesRef.current.has(audioElement)) {
      return;
    }
    
    try {
      const source = audioContext.createMediaElementSource(audioElement);
      source.connect(analyserRef.current!);
      sourceNodesRef.current.set(audioElement, source);
    } catch (error) {
      // Element might already be connected to a different context
      console.warn("Audio element already connected:", error);
    }
  }, [initializeAudioContext]);

  // Start analysing frequency data
  const startAnalysing = useCallback(() => {
    if (!analyserRef.current || isAnalysing) return;
    
    // Resume context if suspended (browser autoplay policy)
    if (audioContextRef.current?.state === "suspended") {
      audioContextRef.current.resume();
    }
    
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
  }, [isAnalysing]);

  // Stop analysing
  const stopAnalysing = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    setIsAnalysing(false);
    // Reset frequency data to show inactive state
    setFrequencyData(new Uint8Array(32));
  }, []);

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

  return {
    frequencyData,
    isAnalysing,
    connectAudioElement,
    startAnalysing,
    stopAnalysing,
    initializeAudioContext,
  };
}

