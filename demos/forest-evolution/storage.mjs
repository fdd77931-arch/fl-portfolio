import { MAX_LEVEL, SIZE, createRun, highest, move } from './engine.mjs';

export const SAVE_KEY = 'forest-evolution.save.v1';

const whole = (value, min = 0, max = Number.MAX_SAFE_INTEGER) =>
  Number.isSafeInteger(value) && value >= min && value <= max;

function validRun(run) {
  if (!run || !Array.isArray(run.board) || run.board.length !== SIZE * SIZE
      || !whole(run.score) || !whole(run.moves) || !whole(run.nextId, 1) || typeof run.won !== 'boolean') return false;
  const tiles = run.board.filter(Boolean);
  return tiles.length > 0
    && run.board.every((tile) => tile === null || (tile && whole(tile.id, 1, run.nextId - 1) && whole(tile.level, 1, MAX_LEVEL)))
    && new Set(tiles.map((tile) => tile.id)).size === tiles.length
    && run.won === (highest(run.board) === MAX_LEVEL);
}

export function createGame(random = Math.random) {
  return { version: 1, run: createRun(random), previous: null, best: 0, discovered: 1, sound: false };
}

export function restoreGame(value, random = Math.random) {
  try {
    const saved = JSON.parse(value);
    if (saved?.version === 1 && validRun(saved.run)) {
      const previous = validRun(saved.previous) && saved.previous.moves + 1 === saved.run.moves
        ? saved.previous : null;
      return { version: 1, run: saved.run, previous,
        best: Math.max(saved.run.score, whole(saved.best) ? saved.best : 0),
        discovered: Math.max(highest(saved.run.board), whole(saved.discovered, 1, MAX_LEVEL) ? saved.discovered : 1),
        sound: saved.sound === true };
    }
  } catch { /* Replace obsolete or corrupt saves. */ }
  return createGame(random);
}

export function loadGame() {
  try { return restoreGame(localStorage.getItem(SAVE_KEY)); }
  catch { return createGame(); }
}

export function saveGame(game) {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(game)); return true; }
  catch { return false; }
}

export function takeTurn(game, direction, random = Math.random) {
  const action = move(game.run, direction, random, game.discovered);
  if (!action.changed) return { ...action, game, unlocked: [] };
  const discovered = Math.max(game.discovered, highest(action.run.board));
  const unlocked = Array.from({ length: discovered - game.discovered }, (_, index) => game.discovered + index + 1);
  return { ...action, unlocked, game: { ...game, run: action.run, previous: game.run,
    best: Math.max(game.best, action.run.score), discovered } };
}

export function undoTurn(game) {
  return game.previous ? { ...game, run: game.previous, previous: null } : game;
}

export function restartGame(game, random = Math.random) {
  return { ...game, run: createRun(random), previous: null };
}
