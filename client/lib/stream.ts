import { PlayingResponse, NextResponse } from '@/lib/types';

export async function fetchPlayingTrack(): Promise<PlayingResponse> {
  const response = await fetch("/api/stream/playing");
  if (!response.ok) {
    throw new Error("Failed to fetch stream");
  }
  return response.json();
}

export async function fetchNextTrack(): Promise<NextResponse> {
  const response = await fetch("/api/stream/next");
  if (!response.ok) {
    throw new Error("Failed to fetch next track");
  }
  return response.json();
}