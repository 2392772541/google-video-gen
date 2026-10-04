/* Real output presentation, fed by the existing guarded task refresh. No extra timer or API requests. */
(function (root) {
  'use strict';
  function mediaURL(value, origin) {
    if (typeof value !== 'string' || !value.startsWith('/media/') || /[\\\u0000-\u001f]/.test(value)) return null;
    try {
      const url = new URL(value, origin);
      return url.origin === origin && url.pathname.startsWith('/media/') ? url.href : null;
    } catch (_) { return null; }
  }
  function playableTasks(tasks, origin) {
    if (!Array.isArray(tasks)) return [];
    return tasks.filter(t => t && /^task_[a-zA-Z0-9_-]+$/.test(t.id) && t.status === 'completed' &&
      t.task_type !== 'audio' && t.task_type !== 'image' && t.has_video && mediaURL(t.video_url, origin)).slice(0, 5);
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {mediaURL, playableTasks};
  if (!root.document) return;
  const doc = root.document;
  let tasks = [], currentId = null, currentURL = null, signature = '', initialized = false;
  const $ = id => doc.getElementById(id);
  function selectTask(task) {
    const video = $('workbench-video');
    if (!video || !task) return;
    const url = mediaURL(task.video_url, location.origin);
    if (!url) return;
    currentId = task.id;
    if (currentURL !== url) {
      video.pause();
      currentURL = url;
      video.poster = mediaURL(task.first_frame_url || task.start_image_url, location.origin) || '';
      video.src = url;
      $('workbench-measured').textContent = '正在读取实际文件规格…';
    }
    video.hidden = false;
    $('workbench-empty').hidden = true;
    $('workbench-state').textContent = '已完成 · 本机文件';
    $('workbench-output-title').textContent = '最近的创作成果';
    $('workbench-task-id').textContent = task.id;
    $('workbench-prompt').textContent = task.prompt || '此任务没有保存提示词。';
    $('workbench-prompt').title = task.prompt || '';
    $('workbench-requested').textContent = `请求 ${task.aspect_ratio || '未指定'} · ${task.duration_sec || '未指定'} 秒`;
    const download = $('workbench-download');
    download.href = `/api/tasks/${encodeURIComponent(task.id)}/download`;
    download.hidden = false;
    $('workbench-recents').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.taskId === task.id)));
  }
  function render() {
    if (!initialized) return;
    const host = $('workbench-recents');
    host.replaceChildren();
    tasks.forEach((task, index) => {
      const button = doc.createElement('button');
      button.type = 'button'; button.className = 'recent-output'; button.dataset.taskId = task.id;
      button.setAttribute('aria-label', `预览成片 ${index + 1}：${task.id}`);
      button.setAttribute('aria-pressed', String(task.id === currentId));
      const imageURL = mediaURL(task.first_frame_url || task.start_image_url, location.origin);
      if (imageURL) {
        const img = doc.createElement('img'); img.src = imageURL; img.alt = ''; img.loading = 'lazy'; img.decoding = 'async';
        img.addEventListener('error', () => { img.removeAttribute('src'); img.alt = '缩略图不可用'; }, {once:true});
        button.append(img);
      } else {
        const fallback = doc.createElement('span'); fallback.className = 'recent-fallback'; fallback.textContent = '视频';button.append(fallback);
      }
      const caption = doc.createElement('span');
      caption.textContent = `${String(index + 1).padStart(2, '0')}  ${task.prompt || task.id}`;
      button.title = task.prompt || task.id;button.append(caption);
      button.addEventListener('click', () => selectTask(task));host.append(button);
    });
    if (tasks.length) selectTask(tasks.find(t => t.id === currentId) || tasks[0]);
    else {
      const video = $('workbench-video');video.pause();video.removeAttribute('src');video.load();video.hidden = true;
      currentId = currentURL = null;$('workbench-empty').hidden = false;$('workbench-download').hidden = true;
      $('workbench-state').textContent = '等待成片';$('workbench-output-title').textContent = '你的下一支作品，从这里开始';
      $('workbench-measured').textContent = '尚无可预览成片';$('workbench-task-id').textContent = '';
      $('workbench-prompt').textContent = '这里展示真实任务的成片，而不是演示素材。';$('workbench-requested').textContent = '';
    }
  }
  function update(rows) {
    const next = playableTasks(rows, location.origin);
    const nextSignature = JSON.stringify(next.map(t => [t.id,t.video_url,t.first_frame_url,t.start_image_url,t.prompt,t.duration_sec,t.aspect_ratio]));
    if (signature === nextSignature) return;
    signature = nextSignature; tasks = next;render();
  }
  function pauseHiddenMedia() {
    doc.querySelectorAll('video,audio').forEach(media => {
      if (doc.hidden || !media.closest('.view-pane.active') || media.closest('[hidden]')) media.pause();
    });
  }
  doc.addEventListener('DOMContentLoaded', () => {
    const video = $('workbench-video'); if (!video) return;
    initialized = true;
    video.addEventListener('loadedmetadata', () => {
      const duration = Number.isFinite(video.duration) ? video.duration.toFixed(1) + ' 秒' : '时长未知';
      $('workbench-measured').textContent = `实际文件  ${video.videoWidth} × ${video.videoHeight} · ${duration}`;
    });
    video.addEventListener('error', () => {
      if (!currentURL) return;
      $('workbench-state').textContent = '预览不可用';$('workbench-measured').textContent = '文件加载失败，可下载原片或前往任务检查';
    });
    $('workbench-go-tasks').addEventListener('click', () => doc.querySelector('[data-target="view-tasks"]')?.click());
    doc.querySelectorAll('button.tab-button[data-target]').forEach(b => b.addEventListener('click', () => queueMicrotask(pauseHiddenMedia)));
    $('btn-mode-batch')?.addEventListener('click', () => video.pause());
    doc.addEventListener('visibilitychange', pauseHiddenMedia);
    render();
  });
  root.VideoWorkbench = {update};
})(typeof window !== 'undefined' ? window : {});
