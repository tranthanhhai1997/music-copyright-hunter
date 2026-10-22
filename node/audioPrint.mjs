// Audio fingerprint for finding re-uploads: a chroma sequence (12 pitch classes, ~5 frames / s) and a
// matcher that survives what re-uploaders do to dodge Content ID — key shifted (the 12 classes are
// rotated), speed changed (the candidate's time axis is stretched), cut / re-encoded / louder (each frame
// is normalised, and the score is a correlation of the mean-removed sequences, so a quiet intro or a
// louder master does not count). Pure: decoding is done by ffmpeg in main.

export const FP_RATE = 11025
const N = 2048
const HOP = 2205 // 0.2 s
export const FP_FPS = FP_RATE / HOP

/** chroma frames, 12 values each, flattened */


function fft(re, im): void {
  const n = re.length
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1
    for (; j & bit; bit >>= 1) j ^= bit
    j ^= bit
    if (i < j) {
      ;[re[i], re[j]] = [re[j], re[i]]
      ;[im[i], im[j]] = [im[j], im[i]]
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len
    const wr = Math.cos(ang)
    const wi = Math.sin(ang)
    for (let i = 0; i < n; i += len) {
      let cr = 1
      let ci = 0
      for (let k = 0; k < len / 2; k++) {
        const a = i + k
        const b = a + len / 2
        const tr = re[b] * cr - im[b] * ci
        const ti = re[b] * ci + im[b] * cr
        re[b] = re[a] - tr
        im[b] = im[a] - ti
        re[a] += tr
        im[a] += ti
        const nr = cr * wr - ci * wi
        ci = cr * wi + ci * wr
        cr = nr
      }
    }
  }
}

/** FFT bin → pitch class (−1 = outside 80 Hz – 4 kHz, where the melody and chords live) */
const BIN_CLASS = (() => {
  const out = new Int8Array(N / 2)
  for (let k = 0; k < N / 2; k++) {
    const f = (k * FP_RATE) / N
    out[k] = f < 80 || f > 4000 ? -1 : (((Math.round(12 * Math.log2(f / 440)) % 12) + 12 + 9) % 12)
  }
  return out
})()
const WINDOW = (() => {
  const w = new Float64Array(N)
  for (let i = 0; i < N; i++) w[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (N - 1))
  return w
})()

/** Chroma of mono PCM at FP_RATE. Silent frames come out as zeros (they never count in a match). */
export function fingerprint(pcm) {
  const frames = Math.max(0, Math.floor((pcm.length - N) / HOP) + 1)
  const data = new Float32Array(frames * 12)
  const re = new Float64Array(N)
  const im = new Float64Array(N)
  for (let f = 0; f < frames; f++) {
    const o = f * HOP
    for (let i = 0; i < N; i++) {
      re[i] = pcm[o + i] * WINDOW[i]
      im[i] = 0
    }
    fft(re, im)
    const c = new Float64Array(12)
    for (let k = 1; k < N / 2; k++) {
      const pc = BIN_CLASS[k]
      if (pc >= 0) c[pc] += Math.sqrt(re[k] * re[k] + im[k] * im[k])
    }
    let norm = 0
    for (let i = 0; i < 12; i++) {
      c[i] = Math.log1p(c[i])
      norm += c[i] * c[i]
    }
    norm = Math.sqrt(norm)
    if (norm < 1e-3) continue
    for (let i = 0; i < 12; i++) data[f * 12 + i] = c[i] / norm
  }
  return { frames, data }
}



/** The candidate's frames resampled to the reference's speed, chroma rotated back by `rot`. */
function prepare(c, tempo, rot) {
  const frames = Math.floor(c.frames * tempo)
  const out = new Float32Array(frames * 12)
  for (let f = 0; f < frames; f++) {
    const src = Math.min(c.frames - 1, Math.round(f / tempo))
    for (let i = 0; i < 12; i++) out[f * 12 + i] = c.data[src * 12 + ((i + rot) % 12)]
  }
  return out
}

/** the candidate with each pitch class's mean removed (so it sums to 0 per class) and its energy */
function centre(x, frames): { a; aa } {
  const mean = new Float64Array(12)
  for (let f = 0; f < frames; f++) for (let i = 0; i < 12; i++) mean[i] += x[f * 12 + i]
  for (let i = 0; i < 12; i++) mean[i] /= frames || 1
  const a = new Float32Array(frames * 12)
  let aa = 0
  for (let f = 0; f < frames; f++)
    for (let i = 0; i < 12; i++) {
      const v = x[f * 12 + i] - mean[i]
      a[f * 12 + i] = v
      aa += v * v
    }
  return { a, aa }
}

/** running sums of the reference per class (and of squares): any stretch's centred energy in O(12) */
function prefix(ref): { s; q } {
  const s = new Float64Array((ref.frames + 1) * 12)
  const q = new Float64Array((ref.frames + 1) * 12)
  for (let f = 0; f < ref.frames; f++)
    for (let i = 0; i < 12; i++) {
      const v = ref.data[f * 12 + i]
      s[(f + 1) * 12 + i] = s[f * 12 + i] + v
      q[(f + 1) * 12 + i] = q[f * 12 + i] + v * v
    }
  return { s, q }
}

/** speed of the suspect ÷ the original's: re-uploads are usually sped up or slowed down a few % */
const TEMPOS = [1, 1.03, 0.97, 1.06, 0.94, 1.09, 0.91, 1.12, 0.88]

/**
 * Best alignment of a candidate window (a few tens of seconds of the suspect video) inside the reference.
 * Every key rotation × the usual speed changes; offsets step one frame (0.2 s). The score is the Pearson
 * correlation of the two stretches with each pitch class centred — chords and melody moving together,
 * not merely "both in A minor".
 */
export function matchFingerprint(ref, cand) {
  const empty = { score: 0, refAt: 0, semitones: 0, tempo: 1 }
  if (cand.frames < 25 || ref.frames < 25) return empty
  const pre = prefix(ref)
  // coarse: every key × speeds 3 % apart; then the speed refined in 0.5 % steps around the best one
  // (a 5 % speed-up scored 0.63 on the coarse grid alone, 0.9+ once refined)
  const coarse = search(ref, cand, pre, TEMPOS, [...Array(12).keys()], empty)
  const fine[] = []
  for (let d = -0.02; d <= 0.0201; d += 0.005) fine.push(Math.round((coarse.tempo + d) * 1000) / 1000)
  const rot = (coarse.semitones + 12) % 12
  return search(ref, cand, pre, fine, [rot], coarse)
}

function search(
  ref,
  cand,
  { s, q }: { s; q },
  speeds[],
  rots[],
  start
) {
  let best = start
  for (const speed of speeds) {
    for (const rot of rots) {
      const c = prepare(cand, speed, rot)
      const len = Math.min(c.length / 12, ref.frames)
      if (len < 25) continue
      const { a, aa } = centre(c, len)
      if (aa <= 0) continue
      for (let o = 0; o + len <= ref.frames; o++) {
        // Σ a·(b − mean b) = Σ a·b, because a sums to 0 in every class
        let ab = 0
        const base = o * 12
        for (let k = 0; k < len * 12; k++) ab += a[k] * ref.data[base + k]
        if (ab <= 0) continue
        let bb = 0
        for (let i = 0; i < 12; i++) {
          const sum = s[(o + len) * 12 + i] - s[o * 12 + i]
          bb += q[(o + len) * 12 + i] - q[o * 12 + i] - (sum * sum) / len
        }
        if (bb <= 0) continue
        const r = ab / Math.sqrt(aa * bb)
        if (r > best.score)
          best = { score: r, refAt: o / FP_FPS, semitones: rot > 6 ? rot - 12 : rot, tempo: speed }
      }
    }
  }
  return best
}
