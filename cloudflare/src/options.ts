export type Descriptor = {
  genre: string;
  mood: string;
  energy: string;
};

export const DESCRIPTORS: Record<string, Descriptor> = {
  ambient: { genre: "electronic", mood: "happy", energy: "low" },
  bittersweet: { genre: "pop", mood: "sad", energy: "mid" },
  bouncy: { genre: "hip_hop", mood: "party", energy: "low" },
  bubbly: { genre: "pop", mood: "happy", energy: "high" },
  cathartic: { genre: "pop", mood: "sad", energy: "high" },
  chill: { genre: "hip_hop", mood: "happy", energy: "low" },
  cozy: { genre: "rock", mood: "romantic", energy: "mid" },
  dreamy: { genre: "pop", mood: "happy", energy: "low" },
  driving: { genre: "rock", mood: "exciting", energy: "mid" },
  dynamic: { genre: "pop", mood: "exciting", energy: "mid" },
  eclectic: { genre: "electronic", mood: "happy", energy: "mid" },
  energetic: { genre: "rock", mood: "happy", energy: "high" },
  ethereal: { genre: "electronic", mood: "sad", energy: "low" },
  festive: { genre: "pop", mood: "party", energy: "mid" },
  fiery: { genre: "jazz", mood: "exciting", energy: "high" },
  floating: { genre: "electronic", mood: "calm", energy: "low" },
  groovy: { genre: "hip_hop", mood: "happy", energy: "mid" },
  hypnotic: { genre: "electronic", mood: "calm", energy: "mid" },
  introspective: { genre: "hip_hop", mood: "sad", energy: "low" },
  jazzy: { genre: "jazz", mood: "happy", energy: "high" },
  laidback: { genre: "jazz", mood: "calm", energy: "mid" },
  lively: { genre: "jazz", mood: "party", energy: "mid" },
  mellow: { genre: "rnb", mood: "happy", energy: "low" },
  nostalgic: { genre: "jazz", mood: "romantic", energy: "low" },
  peaceful: { genre: "pop", mood: "calm", energy: "mid" },
  playful: { genre: "pop", mood: "party", energy: "low" },
  pulsing: { genre: "electronic", mood: "calm", energy: "high" },
  relaxed: { genre: "hip_hop", mood: "calm", energy: "mid" },
  silky: { genre: "hip_hop", mood: "romantic", energy: "mid" },
  smooth: { genre: "jazz", mood: "happy", energy: "low" },
  soulful: { genre: "rnb", mood: "happy", energy: "mid" },
  sunny: { genre: "pop", mood: "happy", energy: "mid" },
  sweet: { genre: "pop", mood: "romantic", energy: "mid" },
  tender: { genre: "pop", mood: "romantic", energy: "low" },
  tranquil: { genre: "rock", mood: "calm", energy: "low" },
  turnt: { genre: "hip_hop", mood: "party", energy: "high" },
  uplifting: { genre: "rock", mood: "happy", energy: "mid" },
  vibrant: { genre: "hip_hop", mood: "happy", energy: "high" },
  warm: { genre: "rnb", mood: "calm", energy: "mid" },
  wistful: { genre: "rnb", mood: "sad", energy: "low" },
  zen: { genre: "hip_hop", mood: "calm", energy: "low" }
};

export function sampleOptions(size: number): string[] {
  const keys = Object.keys(DESCRIPTORS);
  const pool = [...keys];
  const selection: string[] = [];
  while (selection.length < size && pool.length > 0) {
    const index = Math.floor(Math.random() * pool.length);
    selection.push(pool.splice(index, 1)[0]);
  }
  return selection;
}
