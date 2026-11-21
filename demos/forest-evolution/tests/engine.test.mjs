import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SIZE, canMove, createRun, move, slide } from '../engine.mjs';
import { createGame, restoreGame, takeTurn, undoTurn, restartGame } from '../storage.mjs';

function run(levels) {
  return { board: Array.from({ length: SIZE * SIZE }, (_, i) => levels[i] ? { id: i + 1, level: levels[i] } : null),
    score: 0, moves: 0, nextId: 17, won: false };
}
const row = (board) => board.slice(0, 4).map((tile) => tile?.level ?? 0);
const contents = (board) => board.map((tile) => tile?.level ?? 0);
const zero = () => 0;

test('a fresh 4 × 4 board starts with two distinct ladybugs', () => {
  const start = createRun(zero);
  assert.equal(start.board.length, 16);
  assert.deepEqual(start.board.filter(Boolean), [{ id: 1, level: 1 }, { id: 2, level: 1 }]);
});

test('moves in each of the four directions to the correct edge', () => {
  const start = run([0, 0, 0, 0, 0, 0, 3]);
  for (const [direction, index] of Object.entries({ left: 4, right: 7, up: 2, down: 14 })) {
    const result = slide(start, direction);
    assert.equal(result.run.board[index].level, 3);
    assert.equal(result.changed, true);
    assert.deepEqual(contents(start.board).slice(4, 8), [0, 0, 3, 0]);
  }
});

test('pairs merge once and cannot chain within a single move', () => {
  for (const [levels, expected] of [
    [[1, 1, 1, 1], [2, 2, 0, 0]],
    [[1, 1, 2, 0], [2, 2, 0, 0]],
    [[1, 1, 1, 0], [2, 1, 0, 0]],
    [[2, 0, 2, 3], [3, 3, 0, 0]],
  ]) assert.deepEqual(row(slide(run(levels), 'left').run.board), expected);
  assert.deepEqual(row(slide(run([1, 1, 1]), 'right').run.board), [0, 0, 1, 2]);
  assert.deepEqual(row(slide(run([11, 11, 0, 0]), 'left').run.board), [11, 11, 0, 0]);
});

test('invalid moves consume no RNG and valid moves spawn exactly one animal', () => {
  const start = run([1]);
  assert.equal(move(start, 'left', () => { throw Error('random called'); }).run, start);
  const shifted = move(start, 'right', zero);
  assert.equal(shifted.run.board.filter(Boolean).length, 2);
  assert.equal(shifted.run.moves, 1);
  assert.equal(shifted.run.board[3].id, 1);
});

test('merge points, discovery and one-time victory', () => {
  const normal = slide(run([1, 1, 1, 1]), 'left');
  assert.equal(normal.run.score, 8);
  assert.deepEqual(normal.merges.map((entry) => entry.level), [2, 2]);
  const king = move(run([10, 10]), 'left', zero);
  assert.equal(king.run.board[0].level, 11);
  assert.equal(king.run.score, 2048);
  assert.equal(king.victory, true);
  assert.equal(move(king.run, 'right', zero).victory, false);
});

test('game over checks empty, horizontal and vertical possibilities', () => {
  const dead = run([1, 2, 1, 2, 2, 1, 2, 1, 1, 2, 1, 2, 2, 1, 2, 1]);
  assert.equal(canMove(dead.board), false);
  assert.equal(canMove(run([1, 1, ...contents(dead.board).slice(2)]).board), true);
  assert.equal(canMove(run([2, ...contents(dead.board).slice(1)]).board), true);
  assert.equal(canMove(run([1]).board), true);
});

test('save, undo and restart retain lifetime records and restore the active board', () => {
  const initial = createGame(zero);
  const merged = takeTurn({ ...initial, run: run([1, 1]) }, 'left', zero);
  assert.equal(merged.game.best, 4);
  assert.equal(merged.game.discovered, 2);
  const restored = restoreGame(JSON.stringify(merged.game), zero);
  assert.deepEqual(restored, merged.game);
  const undone = undoTurn(restored);
  assert.deepEqual(row(undone.run.board), [1, 1, 0, 0]);
  assert.equal(undone.run.score, 0);
  assert.equal(undone.best, 4);
  assert.equal(undone.discovered, 2);
  assert.equal(undone.previous, null);
  const restarted = restartGame(restored, zero);
  assert.equal(restarted.best, 4);
  assert.equal(restarted.discovered, 2);
  assert.equal(restarted.run.moves, 0);
});

test('corrupt or unsupported saved state starts a valid run', () => {
  for (const value of ['{', '{}', '{"version":1,"run":{"board":[1]}}']) {
    const game = restoreGame(value, zero);
    assert.equal(game.version, 1);
    assert.equal(game.run.board.filter(Boolean).length, 2);
  }
});
