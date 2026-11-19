import { signals, emergencyCopy, urgentText } from './signals.js';

const $ = (id) => document.getElementById(id);
const form = $('ask');
const question = $('question');
const conversation = $('conversation');
const modelState = $('model-state');
const connectionNote = $('connection-note');
const send = $('send');
const api = new URL(document.documentElement.dataset.apiBase || location.origin);
let activeRequest;
let screenActive = false;
let modelReady = false;
let statusProbe;

function setConnection(ready) {
  modelReady = ready;
  modelState.textContent = ready ? 'DeepSeek 可用' : '实时问答未连接';
  connectionNote.hidden = ready;
  return ready;
}

function checkConnection() {
  if (!statusProbe) {
    statusProbe = fetch(new URL('/api/status', api), { signal: AbortSignal.timeout(5000) })
      .then(async response => setConnection(response.ok && (await response.json()).configured === true))
      .catch(() => setConnection(false))
      .finally(() => { statusProbe = undefined; });
  }
  return statusProbe;
}

for (const signal of signals) {
  const item = document.createElement('li');
  item.textContent = signal;
  $('signals').append(item);
}

function message(text, kind) {
  const element = document.createElement('div');
  element.className = 'message ' + kind;
  element.textContent = text;
  conversation.append(element);
  conversation.scrollTop = conversation.scrollHeight;
  return element;
}

function appendText(parent, tag, text) {
  const child = document.createElement(tag);
  child.textContent = text;
  parent.append(child);
  return child;
}

function appendSource(parent, source, answered = '') {
  const item = document.createElement('article');
  const types = {guideline: '临床指南', 'guide-index': '指南目录', 'health-topic': '健康科普'};
  if (types[source.type]) appendText(item, 'small', types[source.type]);
  const context = answered ? source.fact.replace(answered, '').trim() : source.fact;
  if (context) appendText(item, 'p', context);
  const link = appendText(item, 'a', source.publisher + ' · ' + source.title + ' ↗');
  link.href = source.url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  appendText(item, 'small', [source.version, source.credit || source.attribution, source.license, source.copyright].filter(Boolean).join(' · '));
  if (source.licenseUrl) {
    const license = appendText(item, 'a', '资料许可');
    license.href = source.licenseUrl;
    license.rel = 'noopener noreferrer';
    license.target = '_blank';
  }
  parent.append(item);
}

let library = [];
let visibleCount = 12;
function renderLibrary() {
  const query = $('library-query').value.trim().toLowerCase();
  const type = $('library-type').value;
  const matches = library.filter(record => (!type || type === record.type) &&
    (!query || [record.title, record.publisher, ...record.terms].join(' ').toLowerCase().includes(query)));
  const shown = matches.slice(0, visibleCount);
  $('library-count').textContent = '匹配 ' + matches.length + ' 条 · 已显示 ' + shown.length + ' 条';
  const fragment = document.createDocumentFragment();
  for (const record of shown) appendSource(fragment, record);
  $('catalog').replaceChildren(fragment);
  $('more-records').hidden = shown.length >= matches.length;
}
for (const id of ['library-query', 'library-type']) {
  $(id).addEventListener('input', () => { visibleCount = 12; renderLibrary(); });
}
$('more-records').addEventListener('click', () => { visibleCount += 12; renderLibrary(); });

$('library').addEventListener('toggle', async () => {
  if (!$('library').open || $('catalog').dataset.loaded) return;
  const catalog = $('catalog');
  catalog.textContent = '正在读取来源…';
  try {
    const response = await fetch('./knowledge.json');
    if (!response.ok) throw new Error('unavailable');
    library = await response.json();
    renderLibrary();
    catalog.dataset.loaded = 'true';
  } catch {
    catalog.textContent = '暂时无法读取资料。收起后再次展开可重试。';
  }
});

function screenResult(mode) {
  screenActive = true;
  const result = $('screen-result');
  result.replaceChildren();
  const text = document.createElement('div');
  text.textContent = mode === 'emergency'
    ? '出现任一危险信号时，请立即联系急救。'
    : mode === 'keywords'
      ? emergencyCopy
      : '请尽快联系医疗专业人员判断。若症状严重、突然出现或迅速加重，请立即拨打当地急救号码。';
  const link = document.createElement('a');
  link.href = 'tel:120';
  link.textContent = '中国大陆拨打 120 ↗';
  result.append(text, link);
  result.hidden = false;
  result.focus();
}

for (const button of document.querySelectorAll('[data-choice]')) {
  button.addEventListener('click', () => {
    activeRequest?.abort();
    if (button.dataset.choice === 'emergency') question.value = '';
    screenResult(button.dataset.choice);
  });
}

$('examples').addEventListener('click', (event) => {
  const example = event.target.closest('[data-example]');
  if (!example) return;
  question.value = example.dataset.example;
  question.focus();
});

$('clear').addEventListener('click', () => {
  activeRequest?.abort();
  activeRequest = undefined;
  send.disabled = false;
  conversation.replaceChildren();
  question.value = '';
  screenActive = false;
  $('screen-result').hidden = true;
  question.focus();
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (activeRequest) return;
  if (screenActive) {
    message('危险信号提示已显示。要开始一条新的科普问题，请先清空问答。', 'error');
    return;
  }
  const text = question.value.trim();
  if (!text) return;
  if (urgentText.test(text)) {
    screenResult('keywords');
    return;
  }

  const controller = new AbortController();
  activeRequest = controller;
  send.disabled = true;
  message(text, 'user');
  const pending = message('正在处理…', 'assistant');
  try {
    if (!modelReady && !await checkConnection()) {
      if (controller.signal.aborted) pending.remove();
      else {
        pending.classList.add('error');
        pending.textContent = '当前网络未能连接实时问答。问题仍在输入框，可重试或查看下方的预置示例。';
      }
      return;
    }
    const response = await fetch(new URL('/api/ask', api), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text }),
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(38000)]),
    });
    const result = await response.json();
    if (result.kind === 'emergency') {
      pending.remove();
      screenResult('keywords');
    } else if (result.kind === 'answer') {
      if (result.sources?.length) {
        pending.replaceChildren();
        appendText(pending, 'strong', result.answer);
        appendText(pending, 'h3', '依据与出处');
        for (const source of result.sources) appendSource(pending, source, result.answer);
        appendText(pending, 'h3', '下一步建议');
        appendText(pending, 'p', result.suggestion);
      } else if (result.mode === 'model') {
        pending.replaceChildren();
        appendText(pending, 'strong', result.answer);
        appendText(pending, 'h3', 'DeepSeek 补充 · 未匹配到充分的知识库依据');
        appendText(pending, 'p', result.suggestion);
      } else {
        pending.textContent = result.answer;
      }
      question.value = '';
    } else {
      pending.classList.add('error');
      pending.textContent = result.message || '暂时无法获取回答，请稍后再试。';
    }
  } catch (error) {
    if (error.name === 'AbortError') pending.remove();
    else {
      setConnection(false);
      pending.classList.add('error');
      pending.textContent = '连接中断，问题仍保留在输入框，可稍后重试。';
    }
  } finally {
    if (activeRequest === controller) {
      activeRequest = undefined;
      send.disabled = false;
    }
  }
});

checkConnection();
