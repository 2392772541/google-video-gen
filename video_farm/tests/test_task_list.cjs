'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise the production renderer and refresh path, without a server, browser,
// scheduler, real database, or user-media writes.
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
function section(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `Production seam not found: ${start}`);
  return source.slice(from, to);
}
const escaping = section('  function escapeJs(', '  // 统一刷新按钮');
const rendering = section('  function renderTasks()', '  function getCurrentFilteredTasks()');
const refreshing = section('  let taskPage = 0;', '  function updateTaskFilterCounts()');
function decode(value) {
  return value.replace(/&quot;/g, '"').replace(/&#039;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
class Element {
  constructor(tag = 'div') {
    this.tagName = tag;
    this.children = [];
    this.attrs = {};
    this.events = {};
    this.className = '';
    this.textContent = '';
    this._html = '';
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: name => { if (!this.classList.contains(name)) this.className += ` ${name}`; },
      remove: name => { this.className = this.className.split(/\s+/).filter(n => n !== name).join(' '); }
    };
  }
  set innerHTML(html) {
    this._html = html;
    this.children = [];
    // Only model the nodes queried by production event binding; the full card
    // template still executes, including escaping both path attributes.
    for (const match of html.matchAll(/<(button|input|div|a)\b([^>]*?)>/g)) {
      const child = new Element(match[1]);
      for (const attr of match[2].matchAll(/([\w:-]+)="([^"]*)"/g)) child.attrs[attr[1]] = decode(attr[2]);
      child.className = child.attrs.class || '';
      child.checked = /\bchecked\b/.test(match[2]);
      child.card = this;
      if (child.className) this.children.push(child);
    }
  }
  get innerHTML() { return this._html; }
  appendChild(child) {
    if (child.tagName === '#fragment') this.children.push(...child.children);
    else this.children.push(child);
    return child;
  }
  replaceChildren(...children) {
    this._html = '';
    this.children = [];
    children.forEach(child => this.appendChild(child));
  }
  querySelectorAll(selector) {
    const classes = selector.split(',').map(s => s.trim().slice(1));
    const result = [];
    const visit = node => node.children.forEach(child => {
      if (classes.some(c => child.classList.contains(c))) result.push(child);
      visit(child);
    });
    visit(this);
    return result;
  }
  getAttribute(name) { return this.attrs[name] ?? null; }
  addEventListener(name, listener) { (this.events[name] ??= []).push(listener); }
  closest(selector) { return selector === '.task-card' ? this.card : null; }
  async fire(name) {
    for (const listener of this.events[name] || []) await listener({stopPropagation() {}});
  }
}
function task(id, extra = {}) {
  return {
    id: `task_${id}`, task_type: 'video', engine: 'flow', status: 'completed',
    human_status: '已完成', prompt: `测试 ${id}`, has_video: true,
    output_video_path: `C:\\outputs\\${id}.mp4`, video_url: `/media/outputs/${id}.mp4`,
    first_frame_url: `/media/outputs/${id}.jpg`, ...extra
  };
}
function response(tasks, total = tasks.length) {
  return {ok: true, status: 200, headers: {get: () => String(total)}, json: async () => tasks};
}
function harness(tasks = []) {
  const container = new Element();
  const pager = new Element();
  const prev = new Element('button');
  const next = new Element('button');
  prev.className = 'btn-task-prev';
  next.className = 'btn-task-next';
  const view = new Element();
  view.className = 'active';
  const h = {
    container, pager, prev, next, tasks, requests: [], errors: [], toasts: [],
    plays: [], copied: [], confirmMessages: [], confirmed: true,
    renders: 0, imageRenders: 0, batchUpdates: 0, creations: 0, failCreationAt: 0
  };
  const context = vm.createContext({
    state: {tasks, selectedTaskIds: new Set(), currentFilter: 'all'},
    el: {tasksContainer: container, badgeTotalTasks: new Element()},
    document: {
      getElementById: id => id === 'view-tasks' ? view : null,
      createElement: tag => {
        h.creations++;
        if (h.creations === h.failCreationAt) throw new Error('fixture render failure');
        return new Element(tag);
      },
      createDocumentFragment: () => new Element('#fragment'),
      querySelectorAll: selector => ({
        '.task-page-info': [pager], '.btn-task-prev': [prev], '.btn-task-next': [next],
        '.btn-task-prev, .btn-task-next': [prev, next]
      }[selector] || [])
    },
    window: {},
    navigator: {clipboard: {writeText: async value => h.copied.push(value)}},
    console: {error: (...args) => h.errors.push(args)},
    showToast: (...args) => h.toasts.push(args),
    updateTaskFilterCounts: () => h.renders++,
    renderImageGallery: () => h.imageRenders++,
    updateBatchActionBar: () => h.batchUpdates++,
    openVideoPlayer: (...args) => h.plays.push(args),
    openQAModal: () => {}, openLogModal: () => {}, fetchOverview: () => {},
    confirm: message => { h.confirmMessages.push(message); return h.confirmed; },
    prompt: () => {},
    fetch: async (url, options) => {
      h.requests.push({url, options});
      if (h.onFetch) return h.onFetch(url, options);
      return response(h.tasks);
    }
  });
  vm.runInContext(escaping + rendering + refreshing + `
    globalThis.taskList = {renderTasks, fetchTasks,
      inspect: () => ({lastTasksSnapshot, tasksRequest, taskPage}),
      setPage: value => {taskPage = value;}};
  `, context);
  h.context = context;
  h.api = context.taskList;
  return h;
}

test('all 100 mixed cards render, with video playback, delete and copy handlers bound', () => {
  const tasks = Array.from({length: 100}, (_, i) => task(i,
    i % 5 === 0 ? {task_type: 'audio', has_video: false, has_audio: true, audio_url: '/media/outputs/a.mp3'} :
    i % 5 === 1 ? {task_type: 'image', has_video: false, image_urls: ['/media/outputs/i.png'], image_paths: ['C:/outputs/i.png']} : {}));
  const h = harness(tasks);
  h.api.renderTasks();
  assert.equal(h.container.children.length, 100, 'A completed video must not abort the remaining cards');
  for (const [selector, expected] of [['.btn-play-video', 60], ['.btn-copy-video-path', 60], ['.btn-delete-task', 100]]) {
    const buttons = h.container.querySelectorAll(selector);
    assert.equal(buttons.length, expected);
    assert.ok(buttons.every(b => b.events.click?.length === 1), `${selector} must be interactive`);
  }
});

test('completed video paths are escaped in both HTML attributes and copy back exactly', async () => {
  const outputPath = 'C:\\outputs\\测试 & <frame> "quoted" \'single\'.mp4';
  const h = harness([task('quoted', {output_video_path: outputPath})]);
  h.api.renderTasks();
  const html = h.container.children[0].innerHTML;
  const escaped = 'C:\\outputs\\测试 &amp; &lt;frame&gt; &quot;quoted&quot; &#039;single&#039;.mp4';
  assert.ok(html.includes(`title="${escaped}"`));
  assert.ok(html.includes(`data-path="${escaped}"`));
  const copy = h.container.querySelectorAll('.btn-copy-video-path')[0];
  assert.equal(copy.getAttribute('data-path'), outputPath);
  await copy.fire('click');
  assert.deepEqual(h.copied, [outputPath]);
});

test('a video without an output path still renders and opens its media URL', async () => {
  const t = task('no-path', {output_video_path: null});
  const h = harness([t]);
  h.api.renderTasks();
  await h.container.querySelectorAll('.btn-play-video')[0].fire('click');
  assert.equal(h.plays[0][0], t.id);
  assert.equal(h.plays[0][1], t.video_url);
});

test('deleting a completed card calls DELETE once and refreshes unchanged cached data', async () => {
  const t = task('delete-fixture');
  const h = harness([t]);
  await h.api.fetchTasks();
  h.context.state.selectedTaskIds.add(t.id);
  h.onFetch = (url, options) => {
    if (options?.method === 'DELETE') { h.tasks = []; return response([]); }
    return response(h.tasks);
  };
  await h.container.querySelectorAll('.btn-delete-task')[0].fire('click');
  await h.api.fetchTasks();
  assert.equal(h.requests.filter(r => r.options?.method === 'DELETE').length, 1);
  assert.equal(h.requests.find(r => r.options?.method === 'DELETE').url, `/api/tasks/${t.id}`);
  assert.equal(h.context.state.selectedTaskIds.has(t.id), false);
  assert.match(h.container.innerHTML, /暂无匹配/);
});

test('dismissing delete confirmation sends no deletion', async () => {
  const h = harness([task('keep-fixture')]);
  h.confirmed = false;
  h.api.renderTasks();
  await h.container.querySelectorAll('.btn-delete-task')[0].fire('click');
  assert.equal(h.requests.length, 0);
  assert.equal(h.container.children.length, 1);
});

test('unchanged polling does not recreate cards or video elements', async () => {
  const h = harness([task('stable')]);
  await h.api.fetchTasks();
  const card = h.container.children[0];
  await h.api.fetchTasks();
  assert.equal(h.container.children[0], card);
  assert.equal(h.creations, 1);
  assert.equal(h.api.inspect().tasksRequest, null);
});

test('failed rendering does not poison the snapshot; the same payload is retried', async () => {
  const h = harness([task('retry-render', {has_video: false})]);
  h.failCreationAt = 1;
  await h.api.fetchTasks();
  assert.equal(h.errors.length, 1);
  assert.equal(h.api.inspect().lastTasksSnapshot, '', 'Only a successful render can commit the response snapshot');
  await h.api.fetchTasks();
  assert.equal(h.container.children.length, 1);
  assert.equal(h.api.inspect().lastTasksSnapshot, JSON.stringify(h.tasks));
  assert.match(h.pager.textContent, /本页 1 条/);
});

test('building a failed update leaves the previous complete list and its buttons intact', () => {
  const h = harness([task('existing', {has_video: false})]);
  h.api.renderTasks();
  const previousCard = h.container.children[0];
  h.context.state.tasks = [task('new-one', {has_video: false}), task('new-two', {has_video: false})];
  h.failCreationAt = h.creations + 2;
  assert.throws(() => h.api.renderTasks(), /fixture render failure/);
  assert.equal(h.container.children.length, 1);
  assert.equal(h.container.children[0], previousCard);
  assert.equal(h.container.querySelectorAll('.btn-delete-task')[0].events.click.length, 1);
});

test('concurrent non-forced refreshes share a single request', async () => {
  const h = harness([task('request', {has_video: false})]);
  let resolve;
  h.onFetch = () => new Promise(r => { resolve = r; });
  const first = h.api.fetchTasks();
  const second = h.api.fetchTasks();
  assert.equal(h.requests.length, 1);
  resolve(response(h.tasks));
  await Promise.all([first, second]);
  assert.equal(h.container.children.length, 1);
  assert.equal(h.api.inspect().tasksRequest, null);
});

test('filtering keeps video, image and audio views distinct and clears an empty view', () => {
  const h = harness([task('v', {has_video: false}), task('i', {task_type: 'image', has_video: false}), task('a', {task_type: 'audio', has_video: false})]);
  for (const filter of ['video', 'image', 'audio']) {
    h.context.state.currentFilter = filter;
    h.api.renderTasks();
    assert.equal(h.container.children.length, 1, filter);
  }
  h.context.state.currentFilter = 'failed';
  h.api.renderTasks();
  assert.match(h.container.innerHTML, /暂无匹配/);
});
test('a next-page click during background polling is not discarded', async () => {
  const h = harness([task('page-one', {has_video: false})]);
  h.onFetch = () => response(h.tasks, 201);
  await h.api.fetchTasks();
  let resolvePoll;
  const pageTwo = [task('page-two', {has_video: false})];
  h.onFetch = url => url.includes('offset=0')
    ? new Promise(resolve => { resolvePoll = resolve; })
    : response(pageTwo, 201);
  const poll = h.api.fetchTasks();
  const click = h.next.fire('click');
  resolvePoll(response(h.tasks, 201));
  await Promise.all([poll, click]);
  assert.equal(h.api.inspect().taskPage, 1);
  assert.match(h.pager.textContent, /第 2 页/);
  assert.match(h.container.children[0].innerHTML, /page-two/);
  assert.deepEqual(h.requests.map(r => r.url), [
    '/api/tasks?limit=100&offset=0',
    '/api/tasks?limit=100&offset=0',
    '/api/tasks?limit=100&offset=100'
  ]);
});

test('page navigation cannot exceed the available page range', async () => {
  const h = harness([task('only-page', {has_video: false})]);
  h.onFetch = () => response(h.tasks, 1);
  await h.api.fetchTasks();
  await h.prev.fire('click');
  assert.equal(h.api.inspect().taskPage, 0);
  await h.next.fire('click');
  assert.equal(h.api.inspect().taskPage, 0);
  assert.equal(h.requests.length, 1);
});

test('record-parse failures explain cloud result recovery and never offer duplicate submit', () => {
  const h = harness([task('response-error', {status: 'failed', human_status: '失败', has_video: false,
    error_code: 'FLOW_RESPONSE_UNREADABLE', error_message: '请先核对原 Flow 项目；可能已扣额度。'})]);
  h.api.renderTasks();
  const html = h.container.children[0].innerHTML;
  assert.ok(html.includes('原 Flow 项目'));
  assert.ok(!html.includes('模型 / 参数不兼容'));
  assert.equal(h.container.querySelectorAll('.btn-retry-task').length, 0);
});

test('legacy wire failure is no longer described as model incompatibility', () => {
  const h = harness([task('legacy-wire', {status: 'failed', has_video: false, error_code: 'WIRE_FORMAT_MISMATCH'})]);
  h.api.renderTasks();
  assert.ok(!h.container.children[0].innerHTML.includes('模型 / 参数不兼容'));
  assert.equal(h.container.querySelectorAll('.btn-retry-task').length, 0);
});
