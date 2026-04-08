/**
 * Web Audio–based alert tones for the agent portal (volume/duration per product spec).
 */

export type AgentSoundKind =
  | 'customer_message'
  | 'mention'
  | 'new_dm'
  | 'assignment'
  | 'escalation';

let sharedCtx: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AC) return null;
  if (!sharedCtx) sharedCtx = new AC();
  if (sharedCtx.state === 'suspended') {
    void sharedCtx.resume();
  }
  return sharedCtx;
}

function playTone(
  ctx: AudioContext,
  when: number,
  freq: number,
  durationSec: number,
  peakVolume: number,
  type: OscillatorType = 'sine',
) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, when);
  const v = Math.min(1, Math.max(0, peakVolume));
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.linearRampToValueAtTime(v, when + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + durationSec);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(when);
  osc.stop(when + durationSec + 0.04);
}

/** Play one shot; callers handle debounce. */
export function playAgentSound(kind: AgentSoundKind): void {
  const ctx = getAudioContext();
  if (!ctx) return;
  const t0 = ctx.currentTime;

  switch (kind) {
    case 'customer_message': {
      // Soft chime: 2 notes, ~0.5s total, medium pitch, ~40%
      playTone(ctx, t0, 523.25, 0.22, 0.4, 'sine');
      playTone(ctx, t0 + 0.26, 659.25, 0.22, 0.4, 'sine');
      break;
    }
    case 'mention': {
      // Single ping, higher pitch, ~60%, ~0.3s
      playTone(ctx, t0, 1046.5, 0.28, 0.6, 'triangle');
      break;
    }
    case 'new_dm': {
      // Soft pop, low, ~30%, ~0.3s
      playTone(ctx, t0, 320, 0.12, 0.25, 'sine');
      playTone(ctx, t0 + 0.08, 400, 0.14, 0.22, 'sine');
      break;
    }
    case 'assignment': {
      // Short click, ~30%, ~0.2s
      playTone(ctx, t0, 720, 0.09, 0.3, 'square');
      break;
    }
    case 'escalation': {
      // Double beep, rising, ~50%, ~0.8s total
      playTone(ctx, t0, 440, 0.18, 0.45, 'sine');
      playTone(ctx, t0 + 0.32, 660, 0.22, 0.52, 'sine');
      break;
    }
    default:
      break;
  }
}
