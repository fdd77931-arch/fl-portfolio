let audio;

export function playSound(type, level = 1) {
  const Context = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!Context) return;
  try {
    audio ??= new Context();
    if (audio.state === 'suspended') void audio.resume().catch(() => {});
    const now = audio.currentTime;
    const base = 293.66 * 2 ** (Math.min(level - 1, 9) / 12);
    const notes = type === 'win' ? [1, 1.25, 1.5, 2]
      : type === 'merge' ? [1, 1.5]
      : type === 'over' ? [1, .75]
      : [1];
    notes.forEach((ratio, index) => {
      const oscillator = audio.createOscillator();
      const volume = audio.createGain();
      const start = now + index * .077;
      oscillator.type = 'sine';
      oscillator.frequency.value = base * ratio;
      volume.gain.setValueAtTime(.0001, start);
      volume.gain.exponentialRampToValueAtTime(type === 'move' ? .018 : .052, start + .022);
      volume.gain.exponentialRampToValueAtTime(.0001, start + .24);
      oscillator.connect(volume).connect(audio.destination);
      oscillator.start(start);
      oscillator.stop(start + .25);
    });
  } catch { /* Browsers may restrict Web Audio; the board keeps working. */ }
}
