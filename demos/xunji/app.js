import { apiBase } from './config.js';
import { signals, emergencyCopy, urgentText } from './signals.js';

const $ = (id) => document.getElementById(id);
const question = $('question');
const conversation = $('conversation');
const library = $('library');
const catalog = $('catalog');
const api = new URL(apiBase || location.origin);
const types = {
  guideline: '临床指南', 'guide-index': '指南目录', 'health-topic': '健康科普',
  study: '医学研究', laboratory_reference: '检查指标', medication_information: '药物资料',
};
const collectionTypes = {
  clinical_guidelines: 'guideline', medical_literature: 'study',
  laboratory_reference: 'laboratory_reference', medication_information: 'medication_information',
};
let activeRequest;
let screenActive = false;
let statusProbe;
let responseCount = 0;
let records = [];
let visibleCount = 12;
let loadingLibrary;

function setConnection(label, online) {
  $('model-state').textContent = label;
  $('connection-note').hidden = online;
}

function checkConnection() {
  statusProbe ??= fetch(new URL('/api/health', api), {
    signal: AbortSignal.timeout(6000), cache: 'no-store',
  }).then(async (response) => {
    if (!response.ok) throw new Error('unavailable');
    const health = await response.json();
    if (health.connected) setConnection('百炼问答可用', true);
    else if (health.can_query) setConnection('可以提交问题', true);
    else setConnection('实时问答暂不可用', false);
  }).catch(() => setConnection('实时问答暂不可用', false))
    .finally(() => { statusProbe = undefined; });
  return statusProbe;
}

function appendText(parent, tag, text) {
  const child = document.createElement(tag);
  child.textContent = text;
  parent.append(child);
  return child;
}

function appendLink(parent, text, href) {
  try {
    const url = new URL(href);
    if (url.protocol !== 'https:') return;
    const link = appendText(parent, 'a', text + ' ↗');
    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  } catch { /* The source link was invalid. */ }
}

function appendSource(parent, source, anchor) {
  const item = document.createElement('article');
  if (anchor) {
    item.id = anchor;
    item.tabIndex = -1;
  }
  const type = source.type || collectionTypes[source.collection] || 'health-topic';
  const status = {superseded: '已被替代', unverified: '待审核'}[source.status];
  if (source.fact) appendText(item, 'p', source.fact);
  appendLink(item, source.title, source.url);
  const published = source.year || source.version;
  appendText(item, 'small', [source.publisher, published, types[type], status].filter(Boolean).join(' · '));
  appendText(item, 'small', [
    source.year && source.version, source.doi && 'DOI ' + source.doi, source.pmid && 'PMID ' + source.pmid,
  ].filter(Boolean).join(' · '));

  for (const passage of source.passages || (source.text ? [source] : [])) {
    const details = document.createElement('details');
    const label = passage.excerpt_kind === 'original' ? '原文片段' : '证据摘要';
    const targets = passage.paragraphs?.length ? ' · 对应第 ' + passage.paragraphs.join('、') + ' 段' : '';
    appendText(details, 'summary', label + targets);
    appendText(details, 'small', [passage.section, passage.page_number && '第 ' + passage.page_number + ' 页'].filter(Boolean).join(' · '));
    appendText(details, 'p', passage.text);
    if (passage.source_url && passage.source_url !== source.url) appendLink(details, '片段出处', passage.source_url);
    item.append(details);
  }
  appendText(item, 'small', [source.license, source.verified_at && '核验 ' + source.verified_at].filter(Boolean).join(' · '));
  if (source.licenseUrl) appendLink(item, '资料许可', source.licenseUrl);
  parent.append(item);
}

function message(text, kind) {
  const element = appendText(conversation, 'div', text);
  element.className = 'message ' + kind;
  return element;
}

function renderAnswer(parent, result) {
  const number = ++responseCount;
  const indexes = new Map(result.sources.map((source, index) => [source.document_id, index + 1]));
  parent.replaceChildren();
  for (const paragraph of result.paragraphs) {
    appendText(parent, 'h3', paragraph.section);
    const body = appendText(parent, 'p', paragraph.text + ' ');
    for (const id of paragraph.citations) {
      const index = indexes.get(id);
      const reference = appendText(body, 'a', '[' + index + ']');
      reference.className = 'citation';
      reference.href = '#answer-' + number + '-source-' + index;
      reference.setAttribute('aria-label', '参考来源 ' + index);
    }
  }
  appendText(parent, 'h3', '相关证据与参考来源');
  for (const source of result.sources) appendSource(parent, source, 'answer-' + number + '-source-' + indexes.get(source.document_id));
}

function renderLibrary() {
  const query = $('library-query').value.trim().toLowerCase();
  const type = $('library-type').value;
  const collection = $('library-collection').value;
  const matches = records.filter((record) =>
    (!type || type === (record.type || collectionTypes[record.collection] || 'health-topic')) &&
    (!collection || collection === record.collection) &&
    (!query || [record.title, record.publisher, ...record.terms].join(' ').toLowerCase().includes(query))
  );
  const shown = matches.slice(0, visibleCount);
  $('library-count').textContent = '匹配 ' + matches.length + ' 条 · 已显示 ' + shown.length + ' 条';
  const fragment = document.createDocumentFragment();
  if (!shown.length) appendText(fragment, 'p', '没有匹配资料。试试更短的关键词。');
  for (const record of shown) appendSource(fragment, record);
  catalog.replaceChildren(fragment);
  $('more-records').hidden = shown.length >= matches.length;
}

async function jsonAt(url) {
  const response = await fetch(url, {signal: AbortSignal.timeout(8000)});
  if (!response.ok) throw new Error('unavailable');
  return response.json();
}

async function structuredSources() {
  try {
    const pageSize = 60;
    const path = (offset) => new URL('/api/sources?limit=' + pageSize + '&offset=' + offset, api);
    const first = await jsonAt(path(0));
    if (!Array.isArray(first.sources)) throw new Error('invalid catalog');
    const curated = [...first.sources];
    for (let offset = pageSize; offset < first.total; offset += pageSize) {
      curated.push(...(await jsonAt(path(offset))).sources);
    }
    return curated;
  } catch {
    return jsonAt('./evidence.json');
  }
}

function loadLibrary() {
  if (catalog.dataset.loaded) return;
  if (loadingLibrary) return;
  catalog.textContent = '正在读取来源…';
  loadingLibrary = Promise.allSettled([structuredSources(), jsonAt('./knowledge.json')]).then(([current, existing]) => {
    if (current.status === 'rejected' && existing.status === 'rejected') {
      catalog.textContent = '暂时无法读取资料。收起后再次展开可重试。';
      return;
    }
    const curated = current.status === 'fulfilled' ? current.value : [];
    const curatedIds = new Set(curated.map(({id}) => id));
    const legacy = existing.status === 'fulfilled'
      ? existing.value.filter((item) => !curatedIds.has(item.id)).map((item) => ({...item, status: 'unverified'})) : [];
    records = [...curated, ...legacy];
    catalog.dataset.loaded = 'true';
    renderLibrary();
  }).finally(() => { loadingLibrary = undefined; });
}

for (const id of ['library-query', 'library-type', 'library-collection']) {
  $(id).addEventListener('input', () => { visibleCount = 12; renderLibrary(); });
}
$('more-records').addEventListener('click', () => { visibleCount += 12; renderLibrary(); });
library.addEventListener('toggle', () => { if (library.open) loadLibrary(); });
for (const link of document.querySelectorAll('a[href="#library"]')) {
  link.addEventListener('click', () => {
    $('library-collection').value = link.dataset.collection || '';
    $('library-type').value = '';
    $('library-query').value = '';
    visibleCount = 12;
    library.open = true;
    if (catalog.dataset.loaded) renderLibrary();
    else loadLibrary();
  });
}
for (const signal of signals) appendText($('signals'), 'li', signal);

function screenResult(mode, copy) {
  screenActive = true;
  const result = $('screen-result');
  result.replaceChildren();
  const text = copy || (mode === 'emergency'
    ? '出现任一危险信号时，请立即联系急救。'
    : mode === 'keywords'
      ? emergencyCopy
      : '请尽快联系医疗专业人员判断。若症状严重、突然出现或迅速加重，请立即拨打当地急救号码。');
  appendText(result, 'div', text);
  appendText(result, 'a', '中国大陆拨打 120 ↗').href = 'tel:120';
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
  $('send').disabled = false;
  conversation.replaceChildren();
  question.value = '';
  screenActive = false;
  $('screen-result').hidden = true;
  question.focus();
});

$('ask').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (activeRequest) return;
  if (screenActive) {
    message('危险信号提示已显示。开始新的科普问题前，请先清空问答。', 'error');
    return;
  }
  const text = question.value.trim();
  if (text.length < 2) return;
  if (urgentText.test(text.normalize('NFKC').replace(/(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])/gu, ''))) {
    screenResult('keywords');
    return;
  }

  const controller = new AbortController();
  activeRequest = controller;
  $('send').disabled = true;
  message(text, 'user');
  const pending = message('正在检索医学依据…', 'assistant');
  try {
    const response = await fetch(new URL('/api/chat', api), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text }),
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(85000)]),
    });
    const result = await response.json();
    if (controller.signal.aborted) {
      pending.remove();
      return;
    }
    if (response.ok && result.kind === 'emergency') {
      pending.remove();
      screenResult('keywords', result.message);
    } else if (response.ok && result.kind === 'answer') {
      renderAnswer(pending, result);
      setConnection('百炼问答可用', true);
      if (question.value.trim() === text) question.value = '';
    } else {
      if (result.kind === 'unavailable') setConnection('实时问答暂不可用', false);
      pending.classList.toggle('error', !response.ok);
      pending.textContent = result.message || result.detail || '暂时无法获取回答，请稍后再试。';
    }
  } catch (error) {
    if (error.name === 'AbortError') pending.remove();
    else {
      setConnection('实时问答暂不可用', false);
      pending.classList.add('error');
      pending.textContent = '连接中断，问题仍保留在输入框，可稍后重试。';
    }
  } finally {
    if (activeRequest === controller) {
      activeRequest = undefined;
      $('send').disabled = false;
    }
  }
});

checkConnection();
