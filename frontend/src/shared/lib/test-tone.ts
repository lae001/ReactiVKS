/**
 * Короткий тон для проверки выбранного динамика в лобби: генератор → MediaStream → <audio> с
 * `setSinkId`. Через AudioContext.setSinkId не идем: он есть не везде, а setSinkId у <audio> – там,
 * где вообще можно выбрать динамик (Chrome, Edge).
 */
export async function playTestTone(sinkId: string): Promise<void> {
  if (typeof AudioContext === 'undefined') return;
  const ctx = new AudioContext();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const dest = ctx.createMediaStreamDestination();
  osc.frequency.value = 440;
  gain.gain.value = 0.15;
  osc.connect(gain).connect(dest);

  const audio = new Audio();
  audio.srcObject = dest.stream;
  const sink = (audio as HTMLAudioElement & { setSinkId?: (id: string) => Promise<void> })
    .setSinkId;
  if (sink && sinkId) await sink.call(audio, sinkId);

  osc.start();
  await audio.play();
  await new Promise((resolve) => setTimeout(resolve, 700));
  osc.stop();
  audio.pause();
  audio.srcObject = null;
  await ctx.close();
}
