export const SIZE = 4;
export const MAX_LEVEL = 11;
const CELLS = SIZE * SIZE;

const LINES = Object.fromEntries(['left', 'right', 'up', 'down'].map((direction) => [
  direction,
  Array.from({ length: SIZE }, (_, line) => Array.from({ length: SIZE }, (_, index) => {
    const offset = ['right', 'down'].includes(direction) ? SIZE - 1 - index : index;
    return ['left', 'right'].includes(direction) ? line * SIZE + offset : offset * SIZE + line;
  })),
]));

export function highest(board) {
  return Math.max(0, ...board.map((tile) => tile?.level ?? 0));
}

export function canMove(board) {
  if (board.includes(null)) return true;
  return board.some(({ level }, index) => level < MAX_LEVEL && (
    (index % SIZE < SIZE - 1 && board[index + 1].level === level)
    || (index < CELLS - SIZE && board[index + SIZE].level === level)
  ));
}

function emptyResult(run) {
  return { run, changed: false, trajectories: [], merges: [], spawned: null,
    victory: false, over: !canMove(run.board) };
}

export function slide(run, direction) {
  const lines = LINES[direction];
  if (!Array.isArray(lines)) return emptyResult(run);
  const board = Array(CELLS).fill(null);
  const trajectories = [];
  const merges = [];
  let score = run.score;
  let nextId = run.nextId;

  for (const line of lines) {
    const occupied = line.filter((index) => run.board[index]);
    let output = 0;
    for (let index = 0; index < occupied.length; index += 1) {
      const from = occupied[index];
      const next = occupied[index + 1];
      const tile = run.board[from];
      const to = line[output++];
      if (tile.level < MAX_LEVEL && run.board[next]?.level === tile.level) {
        const merged = { id: nextId++, level: tile.level + 1 };
        board[to] = merged;
        score += 2 ** merged.level;
        merges.push({ ...merged, to });
        trajectories.push({ tile, from, to, merged: true },
          { tile: run.board[next], from: next, to, merged: true });
        index += 1;
      } else {
        board[to] = tile;
        if (from !== to) trajectories.push({ tile, from, to, merged: false });
      }
    }
  }

  if (!trajectories.length) return emptyResult(run);
  const victory = !run.won && merges.some(({ level }) => level === MAX_LEVEL);
  return { run: { board, score, nextId, moves: run.moves + 1, won: run.won || victory },
    changed: true, trajectories, merges, spawned: null, victory, over: !canMove(board) };
}

function spawn(run, random, maxSpawnLevel) {
  const empty = run.board.flatMap((tile, index) => tile ? [] : [index]);
  if (!empty.length) return { run, spawned: null };
  const to = empty[Math.floor(random() * empty.length)];
  const tile = { id: run.nextId, level: maxSpawnLevel >= 2 && random() < 0.1 ? 2 : 1 };
  const board = run.board.slice();
  board[to] = tile;
  return { run: { ...run, board, nextId: run.nextId + 1 }, spawned: { ...tile, to } };
}

export function createRun(random = Math.random) {
  const empty = { board: Array(CELLS).fill(null), score: 0, moves: 0, nextId: 1, won: false };
  return spawn(spawn(empty, random, 1).run, random, 1).run;
}

export function move(run, direction, random = Math.random, maxSpawnLevel = 1) {
  const result = slide(run, direction);
  if (!result.changed) return result;
  const next = spawn(result.run, random, maxSpawnLevel);
  return { ...result, ...next, over: !canMove(next.run.board) };
}
