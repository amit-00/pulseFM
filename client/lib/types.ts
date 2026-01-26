export interface PlayingResponse {
  request_id: string;
  signed_url: string;
  duration_ms: number;
  duration_elapsed_ms: number;
  stubbed: boolean;
}

export interface NextResponse {
  signed_url: string;
  duration_ms: number;
  duration_elapsed_ms: number;
  stubbed: boolean;
}