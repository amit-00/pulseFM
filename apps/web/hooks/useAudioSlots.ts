import { useRef, useMemo, useCallback } from "react";

type Slot = "first" | "second";

export function useAudioSlots() {
  const firstSlotAudioRef = useRef<HTMLAudioElement>(null);
  const secondSlotAudioRef = useRef<HTMLAudioElement>(null);

  const slotMap = useMemo(() => ({
    first: firstSlotAudioRef,
    second: secondSlotAudioRef,
  }), []);

  const getInactiveSlot = useCallback((activeSlot: Slot): Slot => {
    return activeSlot === "first" ? "second" : "first";
  }, []);

  const getActiveAudioRef = useCallback((activeSlot: Slot) => {
    return slotMap[activeSlot];
  }, [slotMap]);

  const getInactiveAudioRef = useCallback((activeSlot: Slot) => {
    return slotMap[getInactiveSlot(activeSlot)];
  }, [slotMap, getInactiveSlot]);

  const loadTrackToSlot = useCallback((slot: Slot, signedUrl: string) => {
    const audioRef = slotMap[slot];
    if (audioRef.current) {
      audioRef.current.src = signedUrl;
      audioRef.current.currentTime = 0;
    }
  }, [slotMap]);

  const setTrackTime = useCallback((slot: Slot, timeSeconds: number) => {
    const audioRef = slotMap[slot];
    if (audioRef.current) {
      audioRef.current.currentTime = timeSeconds;
    }
  }, [slotMap]);

  return {
    firstSlotAudioRef,
    secondSlotAudioRef,
    getActiveAudioRef,
    getInactiveAudioRef,
    loadTrackToSlot,
    setTrackTime,
    getInactiveSlot,
  };
}