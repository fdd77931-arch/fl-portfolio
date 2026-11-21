import { animals } from './animals.mjs';
import { playSound } from './audio.mjs';
import { MAX_LEVEL, SIZE, canMove, highest } from './engine.mjs';
import { loadGame, restartGame, saveGame, takeTurn, undoTurn } from './storage.mjs';

const $ = (id) => document.getElementById(id);
const board = $('board');
const slots = $('slots');
const pieces = $('pieces');
const motion = matchMedia('(prefers-reduced-motion: reduce)');
const format = new Intl.NumberFormat('zh-CN');
const directionKeys = new Map([
  ['ArrowLeft', 'left'], ['ArrowRight', 'right'], ['ArrowUp', 'up'], ['ArrowDown', 'down'],
  ['a', 'left'], ['d', 'right'], ['w', 'up'], ['s', 'down'],
]);
const directions = { left: '左', right: '右', up: '上', down: '下' };
let game = loadGame();
let currentDialog;
let pendingResult;
let toastTimer;
let gesture;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function art(animal, className = '') {
  const image = node('img', className);
  image.src = animal.image;
  image.alt = '';
  image.draggable = false;
  image.decoding = 'async';
  return image;
}

function setCell(element, index) {
  element.style.setProperty('--col', index % SIZE);
  element.style.setProperty('--row', Math.floor(index / SIZE));
}

for (let index = 0; index < SIZE ** 2; index += 1) {
  const slot = node('div', 'slot');
  setCell(slot, index);
  slots.append(slot);
}

function tileAt(tile, position, ghost = false) {
  const animal = animals[tile.level - 1];
  const element = node('div', ghost ? 'tile ghost' : 'tile');
  setCell(element, position);
  element.dataset.level = tile.level;
  element.style.setProperty('--tile', animal.color);
  if (ghost) element.setAttribute('aria-hidden', 'true');
  else {
    element.setAttribute('role', 'img');
    element.setAttribute('aria-label', `第 ${Math.floor(position / SIZE) + 1} 行，第 ${position % SIZE + 1} 列，${animal.name}，等级 ${animal.level}`);
    element.dataset.index = position;
  }
  const level = node('b', '', `Lv. ${animal.level}`);
  level.setAttribute('aria-hidden', 'true');
  element.append(art(animal), level);
  return element;
}

function renderBoard(action) {
  const byId = new Map();
  const fragment = document.createDocumentFragment();
  game.run.board.forEach((tile, index) => {
    if (!tile) return;
    const element = tileAt(tile, index);
    byId.set(tile.id, element);
    fragment.append(element);
  });
  pieces.replaceChildren(fragment);
  if (!action || motion.matches || !board.animate) return;

  const offset = slots.children[1].offsetLeft - slots.children[0].offsetLeft;
  const translation = (from, to) => {
    const dx = (from % SIZE - to % SIZE) * offset;
    const dy = (Math.floor(from / SIZE) - Math.floor(to / SIZE)) * offset;
    return `translate(${dx}px,${dy}px)`;
  };
  for (const step of action.trajectories) {
    const { tile, from, to, merged } = step;
    if (!merged) {
      byId.get(tile.id).animate([{ transform: translation(from, to) }, { transform: 'none' }],
        { duration: 145, easing: 'ease-out' });
      continue;
    }
    const ghost = tileAt(tile, to, true);
    pieces.append(ghost);
    const effect = ghost.animate([{ transform: translation(from, to), opacity: 1 }, { transform: 'none', opacity: .2 }],
      { duration: 130, easing: 'ease-out' });
    effect.onfinish = () => ghost.remove();
  }
  for (const merge of action.merges) {
    byId.get(merge.id).animate([
      { scale: '.76', opacity: .2 },
      { scale: merge.level >= 7 ? '1.18' : '1.1', opacity: 1, offset: .52 },
      { scale: '1', opacity: 1 },
    ], { delay: 103, duration: merge.level >= 7 ? 280 : 200, fill: 'backwards', easing: 'ease-out' });
  }
  if (action.spawned) byId.get(action.spawned.id).animate(
    [{ opacity: 0, scale: '.72' }, { opacity: 1, scale: '1' }],
    { delay: 60, duration: 165, fill: 'backwards', easing: 'ease-out' }
  );
}

function renderJournal() {
  const recent = animals[game.discovered - 1];
  const next = animals[game.discovered];
  const card = node('div');
  card.append(node('span', '', next ? `下一次发现 · Lv. ${next.level}` : '收藏进度'),
    node('strong', '', next?.name || '全图鉴已收集'),
    node('small', '', next ? `合并两只${recent.name}` : '继续探索，挑战最高分'));
  $('next').replaceChildren(card, art(next || recent, next ? 'silhouette' : ''));
  $('progress').value = game.discovered;
  $('collection-count').textContent = `${game.discovered} / ${MAX_LEVEL}`;

  const start = Math.min(Math.max(0, game.discovered - 3), MAX_LEVEL - 5);
  const rows = animals.slice(start, start + 5).map((animal) => {
    const locked = animal.level > game.discovered;
    const line = node('li', locked ? 'locked' : '');
    const name = node('div');
    name.append(node('strong', '', animal.name), node('span', '', animal.english));
    line.append(art(animal), name, node('span', 'flag', `Lv. ${animal.level}`));
    return line;
  });
  $('trail').replaceChildren(...rows);
}

function renderDex() {
  $('dex-summary').textContent = `已收录 ${game.discovered} / ${MAX_LEVEL} · 第一次合成新动物时解锁`;
  const cards = animals.map((animal) => {
    const locked = animal.level > game.discovered;
    const card = node('article', locked ? 'dex-card locked' : 'dex-card');
    card.style.setProperty('--tile', animal.color);
    const portrait = node('div', 'portrait');
    portrait.append(art(animal));
    card.append(portrait, node('span', 'number', `Lv. ${animal.level} · ${locked ? '未解锁' : '已解锁'}`),
      node('h3', '', animal.name), node('small', '', animal.english),
      node('p', '', locked ? `合并两只${animals[animal.level - 2].name}后解锁。` : animal.description));
    return card;
  });
  $('dex-list').replaceChildren(...cards);
}

function renderResult(container) {
  const level = highest(game.run.board);
  $('over-animal').src = animals[level - 1].image;
  const stats = [
    ['当前分数', format.format(game.run.score)], ['历史最高', format.format(game.best)], ['本局最高', `Lv. ${level}`],
  ].map(([label, value]) => {
    const group = node('div');
    group.append(node('dt', '', label), node('dd', '', value));
    return group;
  });
  $(`${container}-scores`).replaceChildren(...stats);
}

function update(action) {
  $('score').textContent = format.format(game.run.score);
  $('best').textContent = format.format(game.best);
  $('highest').textContent = 'Lv. ' + highest(game.run.board);
  $('sound').setAttribute('aria-pressed', String(game.sound));
  $('sound-label').textContent = game.sound ? '音效开' : '音效关';
  $('undo').disabled = !game.previous;
  $('over').querySelector('[data-undo]').disabled = !game.previous;
  const over = !canMove(game.run.board);
  $('ended').hidden = !over;
  for (const control of document.querySelectorAll('[data-direction]')) control.disabled = over;
  renderBoard(action);
  renderJournal();
}

function announce(text) {
  $('announcement').textContent = text;
}

function notify(level) {
  const animal = animals[level - 1];
  $('toast-art').src = animal.image;
  $('toast-name').textContent = `解锁 ${animal.name} · Lv. ${level}`;
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3100);
}

function openDialog(id) {
  clearTimeout(pendingResult);
  if (currentDialog?.open) currentDialog.close();
  if (id === 'dex') renderDex();
  if (id === 'over' || id === 'win') renderResult(id);
  currentDialog = $(id);
  currentDialog.showModal();
}

function applyDirection(direction) {
  if (currentDialog?.open) return;
  const action = takeTurn(game, direction);
  if (!action.changed) {
    if (action.over) openDialog('over');
    return;
  }
  clearTimeout(pendingResult);
  game = action.game;
  saveGame(game);
  update(action);
  const level = Math.max(1, ...action.merges.map((merge) => merge.level));
  if (game.sound) playSound(action.victory ? 'win' : action.over ? 'over' : action.merges.length ? 'merge' : 'move', level);
  const discovered = action.unlocked.at(-1);
  if (discovered && !action.victory) notify(discovered);
  announce(discovered ? `已解锁${animals[discovered - 1].name}，当前分数 ${game.run.score}`
    : `向${directions[direction]}移动，当前分数 ${game.run.score}`);
  if (action.victory) {
    board.classList.add('is-victory');
    openDialog('win');
    setTimeout(() => board.classList.remove('is-victory'), 750);
  } else if (action.over) {
    pendingResult = setTimeout(() => openDialog('over'), motion.matches ? 0 : 185);
  }
}

function reset(undo = false) {
  clearTimeout(pendingResult);
  clearTimeout(toastTimer);
  $('toast').hidden = true;
  game = undo ? undoTurn(game) : restartGame(game);
  saveGame(game);
  update();
  announce(undo ? '已撤销上一步' : '已开始新一局');
  board.focus({ preventScroll: true });
}

for (const dialog of document.querySelectorAll('dialog')) {
  dialog.addEventListener('close', () => {
    if (currentDialog === dialog && !dialog.open) currentDialog = undefined;
  });
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.direction) applyDirection(button.dataset.direction);
  if (button.hasAttribute('data-close')) button.closest('dialog')?.close();
  if (button.dataset.open) openDialog(button.dataset.open);
  if (button.hasAttribute('data-restart')) {
    currentDialog?.close();
    reset();
  }
  if (button.id === 'undo' || button.hasAttribute('data-undo')) reset(true);
  if (button.id === 'sound') {
    game = { ...game, sound: !game.sound };
    saveGame(game);
    button.setAttribute('aria-pressed', String(game.sound));
    $('sound-label').textContent = game.sound ? '音效开' : '音效关';
    if (game.sound) playSound('merge');
  }
});

document.addEventListener('keydown', (event) => {
  if (currentDialog?.open || event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return;
  const focus = document.activeElement;
  if (focus !== document.body && focus !== document.documentElement && !focus?.closest('.tabletop')) return;
  const direction = directionKeys.get(event.key) || directionKeys.get(event.key.toLowerCase());
  if (!direction) return;
  event.preventDefault();
  applyDirection(direction);
});

board.addEventListener('pointerdown', (event) => {
  if (!event.isPrimary || event.button !== 0) return;
  gesture = { id: event.pointerId, x: event.clientX, y: event.clientY };
  board.setPointerCapture(event.pointerId);
});
board.addEventListener('pointercancel', () => { gesture = undefined; });
board.addEventListener('pointerup', (event) => {
  if (gesture?.id !== event.pointerId) return;
  const dx = event.clientX - gesture.x;
  const dy = event.clientY - gesture.y;
  gesture = undefined;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < 18) return;
  applyDirection(Math.abs(dx) > Math.abs(dy) ? dx > 0 ? 'right' : 'left' : dy > 0 ? 'down' : 'up');
});

saveGame(game);
update();
