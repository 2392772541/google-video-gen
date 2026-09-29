/**
 * Google Vids 连续生成工作台前端核心逻辑
 * Version: 20260929_v4
 * 支持：1080p画质、Omni/Veo模型、首尾帧/图生视频多模态、JSON批量导入/导出
 */

// 全局状态
let state = {
  currentWorkflowId: null,
  workflow: null,
  presets: [],
  selectedPresetKey: null,
  isContinuousRunning: false,
  autoRefreshTimer: null
};

// 工具函数：网络请求
async function api(path, options = {}) {
  const url = '/api/vids' + path;
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  };
  if (options.body && typeof options.body === 'object') {
    config.body = JSON.stringify(options.body);
  }
  const res = await fetch(url, config);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API ${res.status}: ${errText}`);
  }
  return await res.json();
}

const BROKEN_IMG_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='70' viewBox='0 0 120 70'%3E%3Crect width='100%25' height='100%25' fill='%231e293b'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23ef4444' font-size='11' font-family='sans-serif'%3E未找到本地图片%3C/text%3E%3C/svg%3E";

// 转换首尾帧资产为可正常在浏览器展示的 URL
function getAssetDisplayUrl(raw) {
  if (!raw) return '';
  let s = String(raw).trim().replace(/^["']|["']$/g, '');
  if (!s) return '';
  if (s.startsWith('http://') || s.startsWith('https://') || s.startsWith('data:') || s.startsWith('/api/') || s.startsWith('/media/')) {
    return s;
  }
  let cleanPath = s;
  if (cleanPath.startsWith('file:///')) cleanPath = cleanPath.slice(8);
  else if (cleanPath.startsWith('file://')) cleanPath = cleanPath.slice(7);
  cleanPath = cleanPath.replace(/\\/g, '/');
  return `/media/file?path=${encodeURIComponent(cleanPath)}`;
}

// 格式化时间戳
function getTimestamp() {
  const now = new Date();
  return now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0');
}

// 追加实时日志
function appendLog(msg, type = 'info') {
  const logBox = document.getElementById('vids-live-log');
  if (!logBox) return;
  const line = document.createElement('div');
  const colorMap = {
    info: 'var(--text-sub)',
    success: 'var(--green-ok)',
    warn: 'var(--orange-warn)',
    error: '#ef4444',
    highlight: 'var(--blue-primary)'
  };
  line.style.color = colorMap[type] || 'var(--text-sub)';
  line.innerHTML = `<span style="opacity: 0.6; font-size: 11px;">[${getTimestamp()}]</span> ${msg}`;
  logBox.appendChild(line);
  logBox.scrollTop = logBox.scrollHeight;
}

// 模式中文标签映射
function getModeLabel(mode) {
  switch (mode) {
    case 'first_last_frame':
      return '🎞️ 首尾帧过渡';
    case 'image2video':
      return '🖼️ 图生/首帧参考';
    case 'extend':
      return '⏩ 尾帧画面延续';
    case 'text2video':
    default:
      return '💬 文生视频';
  }
}

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  appendLog('正在连接 Google Vids 工作流服务...', 'info');
  try {
    await loadOverview();
    await loadPresets();
    await loadInitialWorkflow();
    startAutoRefresh();
    appendLog('系统初始化完毕，1080p画质、首尾帧多模态与批量导入引擎已就绪。', 'success');
  } catch (err) {
    console.error('初始化失败:', err);
    appendLog('初始化失败: ' + err.message, 'error');
  }
});

// 加载概览
async function loadOverview() {
  try {
    const overview = await api('/overview');
    const badge = document.getElementById('doc-timeline-badge');
    if (badge) {
      badge.textContent = `共 ${overview.workflows_count} 工作流 · ${overview.completed_shots}/${overview.total_shots} 镜头已成片`;
    }
  } catch (e) {
    console.warn('获取概览失败', e);
  }
}

// 加载风格资产包预设
async function loadPresets() {
  try {
    const data = await api('/presets');
    state.presets = data.presets || [];
    renderPresetChips();
  } catch (e) {
    console.error('加载预设失败:', e);
  }
}

// 渲染预设标签
function renderPresetChips() {
  const container = document.getElementById('preset-chips-container');
  if (!container) return;
  container.innerHTML = '';

  const iconMap = {
    cyberpunk: '🏙️',
    nature_epic: '🦅',
    oriental_myth: '🏔️',
    tech_product: '✨',
    vertical_story: '📱'
  };

  state.presets.forEach(p => {
    const key = p.id || p.key;
    const title = p.name || p.title;
    const icon = p.icon || iconMap[p.id] || '🎨';
    const chip = document.createElement('div');
    chip.className = 'preset-chip' + (state.selectedPresetKey === key ? ' selected' : '');
    chip.innerHTML = `<span>${icon}</span> <span>${title}</span>`;
    chip.onclick = () => selectPreset(p);
    container.appendChild(chip);
  });
}

// 选择预设
function selectPreset(preset) {
  const key = preset.id || preset.key;
  const title = preset.name || preset.title;
  state.selectedPresetKey = key;
  renderPresetChips();

  const promptInput = document.getElementById('global-style-prompt');
  if (promptInput) {
    promptInput.value = preset.style_prompt || '';
  }

  const aspectSelect = document.getElementById('workflow-aspect-ratio');
  if (aspectSelect && preset.aspect_ratio) {
    aspectSelect.value = preset.aspect_ratio;
  }

  const durationSelect = document.getElementById('workflow-shot-duration');
  if (durationSelect && preset.duration_per_shot) {
    durationSelect.value = String(preset.duration_per_shot);
  }

  const badge = document.getElementById('preset-badge');
  if (badge) {
    badge.textContent = title;
  }

  appendLog(`已应用风格预设资产包：「${title}」`, 'highlight');
}

// 加载初始工作流
async function loadInitialWorkflow() {
  const data = await api('/workflows');
  const workflows = data.workflows || [];
  if (workflows.length > 0) {
    await selectWorkflow(workflows[0].id);
  } else {
    // 自动创建一个默认示范工作流（1080p，Omni多模态）
    const newWf = await api('/workflows', {
      method: 'POST',
      body: {
        title: '示例工程 · 电影感多镜头连续连拍工作流 (1080p)',
        doc_url: 'https://docs.google.com/videos/d/1EXFiC89I2CzVObDNGCXejn-FYySYoaKPjRIG8Fa6nS4/edit',
        style_prompt: 'Cinematic 8k, Unreal Engine 5 render, anamorphic lens, high contrast, atmospheric lighting, ultra-detailed.',
        aspect_ratio: '16:9',
        duration_per_shot: 10,
        resolution: '1080p',
        model_name: 'Omni'
      }
    });
    await selectWorkflow(newWf.id);
  }
}

// 选择/加载工作流详情
async function selectWorkflow(workflowId) {
  state.currentWorkflowId = workflowId;
  const wf = await api(`/workflows/${workflowId}`);
  state.workflow = wf;

  // 更新顶部标题与描述
  const titleEl = document.getElementById('current-workflow-title');
  if (titleEl) titleEl.textContent = wf.title;

  const descEl = document.getElementById('current-workflow-desc');
  if (descEl) {
    const res = wf.resolution || '1080p';
    const model = wf.model_name || 'Omni';
    descEl.textContent = `画幅 ${wf.aspect_ratio || '16:9'} · 清晰度 ${res} · 模型 ${model} · 单镜头 ${wf.duration_per_shot || 10}秒 · 包含 ${(wf.shots || []).length} 个镜头 · 连续自动建场景并置入画布`;
  }

  const promptInput = document.getElementById('global-style-prompt');
  if (promptInput) promptInput.value = wf.style_prompt || '';

  const aspectSelect = document.getElementById('workflow-aspect-ratio');
  if (aspectSelect) aspectSelect.value = wf.aspect_ratio || '16:9';

  const durationSelect = document.getElementById('workflow-shot-duration');
  if (durationSelect) durationSelect.value = String(wf.duration_per_shot || 10);

  const resSelect = document.getElementById('workflow-resolution');
  if (resSelect) resSelect.value = wf.resolution || '1080p';

  const modelSelect = document.getElementById('workflow-model-name');
  if (modelSelect) modelSelect.value = wf.model_name || 'Omni';

  const docUrlInput = document.getElementById('workflow-doc-url');
  if (docUrlInput && wf.doc_url) docUrlInput.value = wf.doc_url;

  renderShots(wf.shots || []);
  updateOverallProgress(wf.shots || []);
  appendLog(`已载入工作流 [${wf.title}] (画质: ${wf.resolution || '1080p'}, 模型: ${wf.model_name || 'Omni'})，共 ${(wf.shots || []).length} 个分镜镜头。`, 'info');
}

// 渲染分镜卡片
function renderShots(shots) {
  const container = document.getElementById('shots-cards-container');
  if (!container) return;
  container.innerHTML = '';

  if (shots.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 48px; background: var(--bg-surface); border-radius: var(--radius-lg); border: 1px dashed var(--border-color);">
        <div style="font-size: 36px; margin-bottom: 12px;">🎬</div>
        <div style="font-size: 16px; font-weight: 600; color: var(--text-main);">当前工作流暂无分镜卡片</div>
        <div style="font-size: 13px; color: var(--text-sub); margin-top: 6px;">
          可在上方剧本框粘贴文案智能拆解，或点击右上角「📋 JSON 批量导入/导出」一键导入全套镜头资产
        </div>
      </div>
    `;
    return;
  }

  const defaultRes = state.workflow?.resolution || '1080p';
  const defaultModel = state.workflow?.model_name || 'Omni';

  shots.forEach((shot, index) => {
    const card = document.createElement('div');
    card.className = `shot-card status-${shot.status || 'pending'}`;
    card.id = `shot-card-${shot.id}`;

    const isDone = shot.status === 'completed';
    const isRunning = shot.status === 'running';
    const isFailed = shot.status === 'failed';

    let statusBadge = '<span class="shot-status-badge status-pending">待生成</span>';
    if (isRunning) statusBadge = `<span class="shot-status-badge status-running">⏳ 生成中 ${shot.progress || 0}%</span>`;
    if (isDone) statusBadge = '<span class="shot-status-badge status-completed">✅ 已生成置入</span>';
    if (isFailed) statusBadge = '<span class="shot-status-badge status-failed">❌ 失败</span>';

    const mode = shot.mode || 'text2video';
    const shotRes = shot.resolution || defaultRes;
    const shotModel = shot.model_name || defaultModel;

    // 首尾帧资产区域 HTML
    let frameAssetHtml = '';
    const hasStartImg = Boolean(shot.image_url);
    const hasEndImg = Boolean(shot.end_image_url);

    if (mode === 'image2video' || mode === 'extend') {
      frameAssetHtml = `
        <div class="frame-asset-container">
          <div class="frame-asset-grid single-col">
            <div class="frame-asset-box ${hasStartImg ? 'has-image' : ''}">
              <div class="frame-asset-header">
                <span>🖼️ 首帧 / 视觉参考图 (Start / Reference Frame)</span>
                <span style="font-size: 10px; color: var(--text-muted);">图生视频指引画面风格与主体</span>
              </div>
              <div class="frame-asset-input-row">
                <input type="text" class="form-input" style="font-size: 12px; padding: 4px 8px; flex: 1;"
                  value="${shot.image_url || ''}"
                  placeholder="输入本地图片路径、URL或点击上传"
                  onchange="updateShotField('${shot.id}', 'image_url', this.value)" />
                <label class="btn btn-secondary btn-sm" style="cursor: pointer; margin: 0; padding: 4px 10px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;">
                  📁 本地上传
                  <input type="file" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'image_url')" />
                </label>
                ${hasStartImg ? `
                  <button class="btn btn-secondary btn-sm" style="padding: 4px 8px; font-size: 11px;" onclick="window.open('${getAssetDisplayUrl(shot.image_url)}', '_blank')" title="大图预览">👁️</button>
                  <button class="btn btn-secondary btn-sm" style="padding: 4px 8px; font-size: 11px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'image_url')" title="清除图片">❌</button>
                ` : ''}
              </div>
              ${hasStartImg ? `
                <div style="margin-top: 4px;">
                  <img src="${getAssetDisplayUrl(shot.image_url)}" class="frame-asset-thumb" title="点击新窗口预览" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="window.open('${getAssetDisplayUrl(shot.image_url)}', '_blank')" />
                </div>
              ` : `
                <div class="frame-asset-thumb-placeholder">暂未绑定首帧（可贴入路径或点击上传）</div>
              `}
            </div>
          </div>
        </div>
      `;
    } else if (mode === 'first_last_frame') {
      frameAssetHtml = `
        <div class="frame-asset-container">
          <div class="frame-asset-grid">
            <!-- 起始帧 -->
            <div class="frame-asset-box ${hasStartImg ? 'has-image' : ''}">
              <div class="frame-asset-header">
                <span>🖼️ 起始首帧 (Start Frame)</span>
                <span style="font-size: 10px; color: var(--text-muted);">镜头开头画面</span>
              </div>
              <div class="frame-asset-input-row">
                <input type="text" class="form-input" style="font-size: 11px; padding: 3px 6px; flex: 1;"
                  value="${shot.image_url || ''}"
                  placeholder="起始帧路径或URL"
                  onchange="updateShotField('${shot.id}', 'image_url', this.value)" />
                <label class="btn btn-secondary btn-sm" style="cursor: pointer; margin: 0; padding: 3px 8px; font-size: 11px;">
                  📁 上传
                  <input type="file" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'image_url')" />
                </label>
                ${hasStartImg ? `
                  <button class="btn btn-secondary btn-sm" style="padding: 3px 6px; font-size: 11px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'image_url')" title="清除">❌</button>
                ` : ''}
              </div>
              ${hasStartImg ? `
                <img src="${getAssetDisplayUrl(shot.image_url)}" class="frame-asset-thumb" title="点击查看大图" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="window.open('${getAssetDisplayUrl(shot.image_url)}', '_blank')" />
              ` : `
                <div class="frame-asset-thumb-placeholder">未设置起始帧</div>
              `}
            </div>

            <!-- 结束尾帧 -->
            <div class="frame-asset-box ${hasEndImg ? 'has-image' : ''}">
              <div class="frame-asset-header">
                <span>🎞️ 目标尾帧 (End Frame)</span>
                <span style="font-size: 10px; color: var(--text-muted);">视频平滑过渡终点</span>
              </div>
              <div class="frame-asset-input-row">
                <input type="text" class="form-input" style="font-size: 11px; padding: 3px 6px; flex: 1;"
                  value="${shot.end_image_url || ''}"
                  placeholder="尾帧路径或URL"
                  onchange="updateShotField('${shot.id}', 'end_image_url', this.value)" />
                <label class="btn btn-secondary btn-sm" style="cursor: pointer; margin: 0; padding: 3px 8px; font-size: 11px;">
                  📁 上传
                  <input type="file" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'end_image_url')" />
                </label>
                ${hasEndImg ? `
                  <button class="btn btn-secondary btn-sm" style="padding: 3px 6px; font-size: 11px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'end_image_url')" title="清除">❌</button>
                ` : ''}
              </div>
              ${hasEndImg ? `
                <img src="${getAssetDisplayUrl(shot.end_image_url)}" class="frame-asset-thumb" title="点击查看大图" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="window.open('${getAssetDisplayUrl(shot.end_image_url)}', '_blank')" />
              ` : `
                <div class="frame-asset-thumb-placeholder">未设置目标尾帧</div>
              `}
            </div>
          </div>
        </div>
      `;
    }

    // 视频预览区域
    let mediaPreview = '';
    if (shot.video_url) {
      mediaPreview = `
        <div class="shot-preview-container">
          <video controls autoplay muted loop src="${shot.video_url}" style="width: 100%; border-radius: 8px; max-height: 240px; background: #000;"></video>
          <div style="margin-top: 6px; display: flex; justify-content: space-between; align-items: center;">
            <a href="${shot.video_url}" target="_blank" class="btn btn-sm btn-secondary" style="font-size: 11px; padding: 2px 8px; text-decoration: none;">
              ⬇️ 下载原片 (MP4 · ${shotRes})
            </a>
            <span style="font-size: 11px; color: var(--text-sub);">已置入 Google Vids 场景 ${shot.scene_index || index + 1}</span>
          </div>
        </div>
      `;
    } else {
      // 如果没有生成视频，但有首尾帧资产，展示资产微缩预览
      if (hasStartImg && hasEndImg && mode === 'first_last_frame') {
        mediaPreview = `
          <div style="padding: 12px; border-radius: 8px; background: rgba(0,0,0,0.25); border: 1px dashed var(--border-color); display: flex; flex-direction: column; gap: 8px; align-items: center; justify-content: center;">
            <div style="font-size: 11px; color: var(--cyan-accent); font-weight: 600;">🎞️ 首尾帧过渡设计预览</div>
            <div style="display: flex; align-items: center; gap: 8px; width: 100%; justify-content: center;">
              <img src="${getAssetDisplayUrl(shot.image_url)}" style="width: 44%; height: 60px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color);" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" />
              <span style="font-size: 14px; color: var(--blue-primary); font-weight: 700;">➔</span>
              <img src="${getAssetDisplayUrl(shot.end_image_url)}" style="width: 44%; height: 60px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color);" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" />
            </div>
            <span style="font-size: 11px; color: var(--text-sub);">待触发 1080p 连续流水线生成</span>
          </div>
        `;
      } else if (hasStartImg && mode === 'image2video') {
        mediaPreview = `
          <div style="padding: 12px; border-radius: 8px; background: rgba(0,0,0,0.25); border: 1px dashed var(--border-color); display: flex; flex-direction: column; gap: 6px; align-items: center; justify-content: center;">
            <div style="font-size: 11px; color: var(--cyan-accent); font-weight: 600;">🖼️ 首帧参考设计</div>
            <img src="${getAssetDisplayUrl(shot.image_url)}" style="width: 80%; height: 64px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color);" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" />
            <span style="font-size: 11px; color: var(--text-sub);">待触发 1080p 图生视频渲染</span>
          </div>
        `;
      } else {
        mediaPreview = `
          <div style="height: 120px; border-radius: 8px; background: rgba(0,0,0,0.15); border: 1px dashed var(--border-color); display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 6px; color: var(--text-sub); font-size: 12px;">
            <span style="font-size: 24px; opacity: 0.6;">📽️</span>
            <span>等待自动化流水线触发渲染 (${shotRes})</span>
          </div>
        `;
      }
    }

    card.innerHTML = `
      <div class="shot-card-header">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <span class="shot-seq-badge">#${index + 1} 场景 ${shot.scene_index || index + 1}</span>
          <input type="text" class="form-input" style="padding: 2px 8px; height: 26px; font-weight: 600; width: 170px;" value="${shot.name || ''}" onchange="updateShotField('${shot.id}', 'name', this.value)" />
          <span class="badge" style="font-size: 11px; padding: 2px 6px;">⏱️ ${shot.duration || 10}s</span>
          <span class="${shotRes === '1080p' ? 'badge-1080p' : 'badge-720p'}">${shotRes}</span>
          <span class="badge" style="background: rgba(59,130,246,0.15); color: var(--blue-primary); font-size: 11px;">${shotModel}</span>
          <span class="badge-mode">${getModeLabel(mode)}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          ${statusBadge}
          <button class="btn btn-secondary btn-sm" onclick="moveShot('${shot.id}', 'up')" title="上移">⬆️</button>
          <button class="btn btn-secondary btn-sm" onclick="moveShot('${shot.id}', 'down')" title="下移">⬇️</button>
          <button class="btn btn-secondary btn-sm" onclick="deleteShot('${shot.id}')" title="删除" style="color: #ef4444;">🗑️</button>
        </div>
      </div>

      <div class="shot-card-body">
        <div style="display: flex; flex-direction: column; gap: 8px;">
          <!-- 镜头生成模式与清晰度选择栏 -->
          <div style="display: flex; align-items: center; gap: 8px; background: rgba(0,0,0,0.15); padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05); flex-wrap: wrap;">
            <span style="font-size: 12px; color: var(--text-sub); font-weight: 600;">生成模式:</span>
            <select class="form-select" style="width: 170px; padding: 3px 8px; font-size: 12px; height: 28px; font-weight: 600;" onchange="updateShotMode('${shot.id}', this.value)">
              <option value="text2video" ${mode === 'text2video' ? 'selected' : ''}>💬 文生视频</option>
              <option value="image2video" ${mode === 'image2video' ? 'selected' : ''}>🖼️ 图生/首帧参考</option>
              <option value="first_last_frame" ${mode === 'first_last_frame' ? 'selected' : ''}>🎞️ 首尾帧过渡</option>
              <option value="extend" ${mode === 'extend' ? 'selected' : ''}>⏩ 尾帧画面延续</option>
            </select>

            <span style="font-size: 12px; color: var(--text-sub); font-weight: 600; margin-left: 8px;">画质:</span>
            <select class="form-select" style="width: 90px; padding: 3px 8px; font-size: 11px; height: 28px;" onchange="updateShotField('${shot.id}', 'resolution', this.value)">
              <option value="1080p" ${shotRes === '1080p' ? 'selected' : ''}>1080p</option>
              <option value="720p" ${shotRes === '720p' ? 'selected' : ''}>720p</option>
            </select>

            <span style="font-size: 12px; color: var(--text-sub); font-weight: 600; margin-left: 8px;">模型:</span>
            <select class="form-select" style="width: 90px; padding: 3px 8px; font-size: 11px; height: 28px;" onchange="updateShotField('${shot.id}', 'model_name', this.value)">
              <option value="Omni" ${shotModel === 'Omni' ? 'selected' : ''}>Omni</option>
              <option value="Veo" ${shotModel === 'Veo' ? 'selected' : ''}>Veo</option>
              <option value="Veo-Lite" ${shotModel === 'Veo-Lite' ? 'selected' : ''}>Veo-Lite</option>
            </select>
          </div>

          <!-- 首尾帧资产展示区 -->
          ${frameAssetHtml}

          <div>
            <label style="font-size: 12px; color: var(--text-sub); font-weight: 500; display: block; margin-bottom: 4px;">镜头提示词 (Prompt):</label>
            <textarea class="form-textarea" rows="2" style="font-size: 13px;" onchange="updateShotField('${shot.id}', 'prompt', this.value)">${shot.prompt || ''}</textarea>
          </div>
          ${shot.narration ? `
          <div>
            <label style="font-size: 11px; color: var(--text-sub); display: block; margin-bottom: 2px;">旁白/台词:</label>
            <input type="text" class="form-input" style="font-size: 12px; padding: 4px 8px;" value="${shot.narration}" onchange="updateShotField('${shot.id}', 'narration', this.value)" />
          </div>` : ''}

          <!-- 进度条 -->
          <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
            <div class="progress-bar-container" style="flex: 1; height: 6px; margin: 0;">
              <div class="progress-bar-fill" style="width: ${shot.progress || 0}%;"></div>
            </div>
            <span style="font-size: 11px; font-weight: 600; width: 36px; text-align: right;">${shot.progress || 0}%</span>
          </div>

          <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px;">
            <button class="btn btn-secondary btn-sm" onclick="resetShot('${shot.id}')">🔄 设为待生成</button>
            <button class="btn btn-primary btn-sm" onclick="runSingleShot('${shot.id}')">⚡ 单独生成</button>
          </div>
        </div>

        <div>
          ${mediaPreview}
        </div>
      </div>
    `;

    container.appendChild(card);
  });
}

// 切换分镜模式 (text2video, image2video, first_last_frame, extend)
async function updateShotMode(shotId, newMode) {
  try {
    await api(`/shots/${shotId}`, {
      method: 'PUT',
      body: { mode: newMode }
    });
    appendLog(`分镜 [${shotId.slice(0, 6)}] 已切换模式为「${getModeLabel(newMode)}」`, 'info');
    await selectWorkflow(state.currentWorkflowId);
  } catch (e) {
    appendLog(`切换分镜模式失败: ${e.message}`, 'error');
  }
}

// 清除分镜图片资产
async function clearShotAsset(shotId, field) {
  try {
    await api(`/shots/${shotId}`, {
      method: 'PUT',
      body: { [field]: '' }
    });
    appendLog(`已清除分镜 [${shotId.slice(0, 6)}] 的 ${field === 'image_url' ? '首帧图' : '尾帧图'}`, 'info');
    await selectWorkflow(state.currentWorkflowId);
  } catch (e) {
    appendLog(`清除失败: ${e.message}`, 'error');
  }
}

// 上传图片资产并绑定至镜头
async function handleAssetUpload(inputEl, shotId, field) {
  const file = inputEl.files && inputEl.files[0];
  if (!file) return;
  appendLog(`正在上传素材图片: ${file.name}...`, 'info');
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/vids/upload_asset', {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error('上传失败: ' + res.statusText);
    const data = await res.json();
    const assetUrl = data.url;
    await updateShotField(shotId, field, assetUrl);
    await selectWorkflow(state.currentWorkflowId);
    appendLog(`素材上传成功，已绑定至镜头 [${field === 'image_url' ? '起始首帧' : '目标尾帧'}]: ${data.filename}`, 'success');
  } catch (err) {
    appendLog('上传素材失败: ' + err.message, 'error');
    alert('上传素材失败: ' + err.message);
  }
}

// 更新分镜属性
async function updateShotField(shotId, field, value) {
  try {
    await api(`/shots/${shotId}`, {
      method: 'PUT',
      body: { [field]: value }
    });
    appendLog(`分镜 [${shotId.slice(0, 6)}] 已更新 ${field}`, 'info');
    // 若修改了媒体帧或关键属性，即刻重绘分镜卡片，提供无缝即时反馈
    if (['image_url', 'end_image_url', 'mode', 'resolution', 'model_name'].includes(field)) {
      if (state.currentWorkflowId) {
        const wf = await api(`/workflows/${state.currentWorkflowId}`);
        state.workflow = wf;
        renderShots(wf.shots || []);
      }
    }
  } catch (e) {
    appendLog(`更新分镜失败: ${e.message}`, 'error');
  }
}

// 保存工作流资产全局配置 (包含1080p画质、模型等)
async function saveWorkflowSettings() {
  if (!state.currentWorkflowId) return;
  const prompt = document.getElementById('global-style-prompt')?.value || '';
  const aspect = document.getElementById('workflow-aspect-ratio')?.value || '16:9';
  const duration = parseInt(document.getElementById('workflow-shot-duration')?.value || '10');
  const res = document.getElementById('workflow-resolution')?.value || '1080p';
  const model = document.getElementById('workflow-model-name')?.value || 'Omni';
  const docUrl = document.getElementById('workflow-doc-url')?.value || '';

  try {
    await api(`/workflows/${state.currentWorkflowId}`, {
      method: 'PUT',
      body: {
        style_prompt: prompt,
        aspect_ratio: aspect,
        duration_per_shot: duration,
        resolution: res,
        model_name: model,
        doc_url: docUrl
      }
    });
    appendLog(`资产套件全局设置已成功保存！画质: ${res} · 模型: ${model}`, 'success');
    await selectWorkflow(state.currentWorkflowId);
  } catch (e) {
    appendLog('保存设置失败: ' + e.message, 'error');
  }
}

// 填入示例文案
function fillSampleScript() {
  const sample = `镜头一：浩瀚深空与星环飞船
画面：一艘流线型的深空科幻探索飞船缓缓划过紫色的土星光环，发动机喷射出幽蓝色的等离子推进光芒。
旁白：人类探索深空的脚步，从未停止。

镜头二：飞船驾驶舱与全息星图
画面：飞船内部高科技驾驶舱，巨大的环形全息星图在宇航员面前旋转闪烁，操作台各色指示灯流转。
旁白：每一组坐标，都是通向未知的航道。

镜头三：未知地表着陆与极光
画面：探索飞船轻巧降落在一个未知的冰川星球表面，巨大的极光在绿色的大气层中波浪般翻涌。
旁白：当我们抵达这里，新的黎明即将破晓。`;

  const input = document.getElementById('script-input-text');
  if (input) {
    input.value = sample;
    appendLog('已填入示例文案，点击「⚡ 智能拆解并追加分镜」即可自动分解。', 'info');
  }
}

// 智能拆解并追加分镜
async function parseAndAppendShots() {
  const scriptText = document.getElementById('script-input-text')?.value?.trim();
  if (!scriptText) {
    alert('请先输入或粘贴剧本文案！');
    return;
  }
  if (!state.currentWorkflowId) {
    alert('请先选择工作流！');
    return;
  }

  appendLog('正在调用分镜拆解器分析剧本文案...', 'info');
  try {
    const res = await api('/parse_script', {
      method: 'POST',
      body: {
        script: scriptText,
        default_duration: parseInt(document.getElementById('workflow-shot-duration')?.value || '10'),
        style_preset: state.selectedPresetKey || ''
      }
    });

    const parsedShots = res.shots || [];
    appendLog(`拆解成功，识别到 ${parsedShots.length} 个镜头分镜，正在追加到工作流...`, 'success');

    const defaultRes = document.getElementById('workflow-resolution')?.value || '1080p';
    const defaultModel = document.getElementById('workflow-model-name')?.value || 'Omni';

    for (const s of parsedShots) {
      s.resolution = defaultRes;
      s.model_name = defaultModel;
      await api(`/workflows/${state.currentWorkflowId}/shots`, {
        method: 'POST',
        body: s
      });
    }

    await selectWorkflow(state.currentWorkflowId);
    appendLog(`已成功追加 ${parsedShots.length} 个分镜卡片！`, 'success');
  } catch (e) {
    appendLog('剧本拆解失败: ' + e.message, 'error');
  }
}

// 手动添加单个分镜
async function addNewShotCard() {
  if (!state.currentWorkflowId) return;
  const count = (state.workflow?.shots || []).length + 1;
  const defaultRes = document.getElementById('workflow-resolution')?.value || '1080p';
  const defaultModel = document.getElementById('workflow-model-name')?.value || 'Omni';

  try {
    await api(`/workflows/${state.currentWorkflowId}/shots`, {
      method: 'POST',
      body: {
        name: `分镜 ${count}`,
        prompt: 'A cinematic high quality scene, detailed 8k, photorealistic.',
        duration: parseInt(document.getElementById('workflow-shot-duration')?.value || '10'),
        sequence: count,
        scene_index: count,
        mode: 'text2video',
        resolution: defaultRes,
        model_name: defaultModel
      }
    });
    await selectWorkflow(state.currentWorkflowId);
    appendLog(`已新增分镜 #${count} (${defaultRes} · ${defaultModel})`, 'success');
  } catch (e) {
    appendLog('新增分镜失败: ' + e.message, 'error');
  }
}

// 删除分镜
async function deleteShot(shotId) {
  if (!confirm('确定要删除这个分镜吗？')) return;
  try {
    await api(`/shots/${shotId}`, { method: 'DELETE' });
    await selectWorkflow(state.currentWorkflowId);
    appendLog('分镜已删除', 'info');
  } catch (e) {
    appendLog('删除失败: ' + e.message, 'error');
  }
}

// 重置分镜为待生成
async function resetShot(shotId) {
  try {
    await api(`/shots/${shotId}`, {
      method: 'PUT',
      body: { status: 'pending', progress: 0, error_message: '', video_url: '', task_id: '' }
    });
    await selectWorkflow(state.currentWorkflowId);
    appendLog(`分镜 [${shotId.slice(0, 6)}] 已重置为待生成`, 'info');
  } catch (e) {
    appendLog('重置失败: ' + e.message, 'error');
  }
}

// 重置所有分镜状态
async function resetAllShotsStatus() {
  if (!state.currentWorkflowId) return;
  if (!confirm('确定要重置所有分镜的状态为待生成吗？')) return;
  try {
    const res = await api(`/workflows/${state.currentWorkflowId}/reset_status`, { method: 'POST' });
    appendLog(`✅ ${res.message || '所有分镜状态已重置为待生成'}`, 'success');
    await selectWorkflow(state.currentWorkflowId);
  } catch (e) {
    appendLog('重置全部状态失败: ' + e.message, 'error');
  }
}

// 移动分镜 (up / down)
async function moveShot(shotId, direction) {
  const shots = state.workflow?.shots || [];
  const idx = shots.findIndex(s => s.id === shotId);
  if (idx < 0) return;
  if (direction === 'up' && idx === 0) return;
  if (direction === 'down' && idx === shots.length - 1) return;

  const targetIdx = direction === 'up' ? idx - 1 : idx + 1;
  const shotIds = shots.map(s => s.id);
  const temp = shotIds[idx];
  shotIds[idx] = shotIds[targetIdx];
  shotIds[targetIdx] = temp;

  try {
    await api(`/workflows/${state.currentWorkflowId}/reorder`, {
      method: 'POST',
      body: { shot_ids: shotIds }
    });
    await selectWorkflow(state.currentWorkflowId);
  } catch (e) {
    appendLog('重排分镜失败: ' + e.message, 'error');
  }
}

// 单独测试生成一个镜头
async function runSingleShot(shotId) {
  appendLog(`正在下发单镜头生成任务 [${shotId.slice(0, 6)}]...`, 'highlight');
  try {
    const res = await api(`/shots/${shotId}/generate`, { method: 'POST' });
    appendLog(`✅ ${res.message || '任务已成功加入调度队列'} (Task ID: ${res.task_id})`, 'success');
    await selectWorkflow(state.currentWorkflowId);
  } catch (e) {
    appendLog('触发单镜头失败: ' + e.message, 'error');
  }
}

// 开始连续连拍生成
async function startContinuousGeneration() {
  if (!state.currentWorkflowId) {
    alert('请先选择工作流！');
    return;
  }
  const pendingShots = (state.workflow?.shots || []).filter(s => s.status === 'pending' || s.status === 'failed');
  if (pendingShots.length === 0) {
    const nonDone = (state.workflow?.shots || []).filter(s => s.status !== 'completed');
    if (nonDone.length === 0) {
      alert('当前工作流所有镜头均已生成完成！如需全量重新生成，请先点击「🔄 重置全部状态」。');
      return;
    }
  }

  const btn = document.getElementById('btn-start-continuous');
  if (btn) {
    btn.innerHTML = '⚡ 任务已下发调度中...';
    btn.classList.add('loading');
  }

  appendLog(`【开始连续流水线调度】正在排队下发全量待生成镜头...`, 'highlight');
  try {
    const res = await api(`/workflows/${state.currentWorkflowId}/generate_all`, { method: 'POST' });
    appendLog(`✅ ${res.message || '连续生成任务已全部入库并启动调度'}`, 'success');
    await selectWorkflow(state.currentWorkflowId);
  } catch (e) {
    appendLog('连续生成下发失败: ' + e.message, 'error');
  } finally {
    if (btn) {
      btn.innerHTML = '⚡ 开始连续生成并置入画布';
      btn.classList.remove('loading');
    }
  }
}

// 刷新总进度条
function updateOverallProgress(shots) {
  const total = shots.length;
  const done = shots.filter(s => s.status === 'completed').length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  const textEl = document.getElementById('overall-progress-text');
  if (textEl) textEl.textContent = `连拍进度: ${done} / ${total} 镜头已完成`;

  const pctEl = document.getElementById('overall-percentage-text');
  if (pctEl) pctEl.textContent = `${pct}%`;

  const fillEl = document.getElementById('overall-progress-fill');
  if (fillEl) fillEl.style.width = `${pct}%`;
}

// 定时自动同步最新状态
function startAutoRefresh() {
  if (state.autoRefreshTimer) clearInterval(state.autoRefreshTimer);
  state.autoRefreshTimer = setInterval(async () => {
    if (state.currentWorkflowId) {
      try {
        const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
        const isEditing = (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select');
        
        const wf = await api(`/workflows/${state.currentWorkflowId}`);
        state.workflow = wf;
        if (!isEditing) {
          renderShots(wf.shots || []);
        }
        updateOverallProgress(wf.shots || []);
      } catch (e) {
        // 静默刷新失败不打扰
      }
    }
  }, 4000);
}

// 切换工作流弹窗
async function loadWorkflowList() {
  try {
    const data = await api('/workflows');
    const wfs = data.workflows || [];
    if (wfs.length === 0) {
      alert('当前还没有其他工作流，请先点击「新建工作流」！');
      return;
    }
    const names = wfs.map((w, idx) => `${idx + 1}. [${w.title}] (${(w.shots || []).length}镜头 · ${w.resolution || '1080p'})`).join('\n');
    const input = prompt(`请输入要切换的工作流序号 (1-${wfs.length}):\n\n${names}`);
    if (input) {
      const idx = parseInt(input.trim()) - 1;
      if (idx >= 0 && idx < wfs.length) {
        await selectWorkflow(wfs[idx].id);
      } else {
        alert('输入的序号无效！');
      }
    }
  } catch (e) {
    alert('加载工作流列表失败: ' + e.message);
  }
}

// 新建工作流弹窗
async function showNewWorkflowModal() {
  const title = prompt('请输入新工作流标题：', '我的新故事 · 连续连拍工程 (1080p)');
  if (!title) return;

  try {
    const newWf = await api('/workflows', {
      method: 'POST',
      body: {
        title: title.trim(),
        doc_url: document.getElementById('workflow-doc-url')?.value || '',
        style_prompt: document.getElementById('global-style-prompt')?.value || '',
        aspect_ratio: document.getElementById('workflow-aspect-ratio')?.value || '16:9',
        duration_per_shot: parseInt(document.getElementById('workflow-shot-duration')?.value || '10'),
        resolution: document.getElementById('workflow-resolution')?.value || '1080p',
        model_name: document.getElementById('workflow-model-name')?.value || 'Omni'
      }
    });
    await selectWorkflow(newWf.id);
    appendLog(`已成功创建并载入新工作流: ${newWf.title}`, 'success');
  } catch (e) {
    alert('创建工作流失败: ' + e.message);
  }
}

// --- JSON 批量导入与导出功能实现 ---

// 打开 JSON 模态弹窗
function openJsonModal(tab = 'import') {
  const backdrop = document.getElementById('json-modal-backdrop');
  if (!backdrop) return;
  backdrop.classList.add('active');
  switchJsonTab(tab);
}

// 关闭 JSON 模态弹窗
function closeJsonModal() {
  const backdrop = document.getElementById('json-modal-backdrop');
  if (backdrop) backdrop.classList.remove('active');
  const msgBox = document.getElementById('import-msg-box');
  if (msgBox) msgBox.style.display = 'none';
}

// 处理点击遮罩关闭
function handleBackdropClick(event) {
  if (event.target.id === 'json-modal-backdrop') {
    closeJsonModal();
  }
}

// 切换导入/导出 Tab
function switchJsonTab(tab) {
  const tabBtnImport = document.getElementById('tab-btn-import');
  const tabBtnExport = document.getElementById('tab-btn-export');
  const contentImport = document.getElementById('tab-content-import');
  const contentExport = document.getElementById('tab-content-export');

  if (tab === 'import') {
    if (tabBtnImport) tabBtnImport.classList.add('active');
    if (tabBtnExport) tabBtnExport.classList.remove('active');
    if (contentImport) contentImport.classList.add('active');
    if (contentExport) contentExport.classList.remove('active');
  } else {
    if (tabBtnImport) tabBtnImport.classList.remove('active');
    if (tabBtnExport) tabBtnExport.classList.add('active');
    if (contentImport) contentImport.classList.remove('active');
    if (contentExport) contentExport.classList.add('active');
    loadWorkflowExportJson();
  }
}

// 填入 1080p 首尾帧示例 JSON
async function fillSampleImportJson() {
  try {
    const sample = await api('/sample_import_json');
    const textarea = document.getElementById('batch-import-textarea');
    if (textarea) {
      textarea.value = JSON.stringify(sample, null, 2);
      appendLog('已载入 1080p、Omni、首尾帧过渡及图生视频标准示范数据！', 'info');
    }
  } catch (e) {
    console.error('获取示例失败，使用本地兜底:', e);
  }
}

// 清空导入输入框
function clearImportTextarea() {
  const textarea = document.getElementById('batch-import-textarea');
  if (textarea) textarea.value = '';
  const msgBox = document.getElementById('import-msg-box');
  if (msgBox) msgBox.style.display = 'none';
}

// 从本地 JSON 文件加载内容
function loadJsonFileToTextarea(inputEl) {
  const file = inputEl.files && inputEl.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const textarea = document.getElementById('batch-import-textarea');
    if (textarea) {
      textarea.value = e.target.result;
      appendLog(`已成功从本地读取文件: ${file.name}`, 'info');
    }
  };
  reader.readAsText(file, 'utf-8');
}

// 执行批量导入
async function executeBatchImport() {
  const textarea = document.getElementById('batch-import-textarea');
  const msgBox = document.getElementById('import-msg-box');
  const rawText = textarea?.value?.trim();

  if (!rawText) {
    alert('请先输入或粘贴 JSON 数据！');
    return;
  }

  // 获取导入模式 (new, append, replace)
  const radio = document.querySelector('input[name="import-mode-radio"]:checked');
  const importMode = radio ? radio.value : 'new';

  let parsed = null;
  try {
    let clean = rawText;
    if (clean.startsWith('```')) {
      const lines = clean.split('\n');
      if (lines[0].startsWith('```')) lines.shift();
      if (lines.length && lines[lines.length - 1].trim().startsWith('```')) lines.pop();
      clean = lines.join('\n').trim();
    }
    parsed = JSON.parse(clean);
  } catch (err) {
    if (msgBox) {
      msgBox.style.display = 'block';
      msgBox.style.background = 'rgba(239, 68, 68, 0.15)';
      msgBox.style.color = '#ef4444';
      msgBox.style.border = '1px solid #ef4444';
      msgBox.innerHTML = `❌ JSON 格式语法解析失败：${err.message}`;
    }
    return;
  }

  const btn = document.getElementById('btn-submit-import');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ 正在解析并入库...';
  }

  try {
    const res = await api('/batch_import', {
      method: 'POST',
      body: {
        workflow_id: state.currentWorkflowId,
        import_mode: importMode,
        data: parsed
      }
    });

    if (res.success) {
      const importedCount = res.imported_count || 0;
      const wf = res.workflow;
      if (msgBox) {
        msgBox.style.display = 'block';
        msgBox.style.background = 'rgba(16, 185, 129, 0.15)';
        msgBox.style.color = '#10b981';
        msgBox.style.border = '1px solid #10b981';
        msgBox.innerHTML = `✅ 批量导入成功！共导入 <strong>${importedCount}</strong> 个镜头（模式：${importMode === 'new' ? '新建工作流' : (importMode === 'append' ? '追加镜头' : '覆盖镜头')}，画质：${wf.resolution || '1080p'}）`;
      }
      appendLog(`【批量导入成功】已写入 ${importedCount} 个镜头资产至工作流 [${wf.title}]`, 'success');

      // 切换到目标工作流并重新渲染
      await selectWorkflow(wf.id);

      setTimeout(() => {
        closeJsonModal();
      }, 1200);
    }
  } catch (err) {
    if (msgBox) {
      msgBox.style.display = 'block';
      msgBox.style.background = 'rgba(239, 68, 68, 0.15)';
      msgBox.style.color = '#ef4444';
      msgBox.style.border = '1px solid #ef4444';
      msgBox.innerHTML = `❌ 导入失败：${err.message}`;
    }
    appendLog('批量导入失败: ' + err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🚀 立即解析并批量导入';
    }
  }
}

// 导出当前工程为标准化 JSON
async function loadWorkflowExportJson() {
  if (!state.currentWorkflowId) return;
  const textarea = document.getElementById('export-json-textarea');
  if (textarea) textarea.value = '正在拉取工程标准化资产数据...';

  try {
    const exportData = await api(`/workflows/${state.currentWorkflowId}/export_json`);
    if (textarea) {
      textarea.value = JSON.stringify(exportData, null, 2);
      appendLog(`已成功提取工作流 [${exportData.title}] 标准化 JSON 资产`, 'info');
    }
  } catch (e) {
    if (textarea) textarea.value = '导出失败: ' + e.message;
    appendLog('导出工程失败: ' + e.message, 'error');
  }
}

// 复制导出的 JSON
function copyExportJson() {
  const textarea = document.getElementById('export-json-textarea');
  if (!textarea || !textarea.value) return;
  navigator.clipboard.writeText(textarea.value).then(() => {
    alert('已复制当前工程完整 JSON 至剪贴板！');
    appendLog('工程资产 JSON 已复制至剪贴板', 'success');
  }).catch(err => {
    textarea.select();
    document.execCommand('copy');
    alert('已复制当前工程完整 JSON 至剪贴板！');
  });
}

// 下载导出的 JSON 文件
function downloadExportJson() {
  const textarea = document.getElementById('export-json-textarea');
  if (!textarea || !textarea.value) return;
  const title = (state.workflow?.title || 'google_vids_workflow').replace(/[\\/:*?"<>|\s]+/g, '_');
  const blob = new Blob([textarea.value], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title}_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  appendLog(`已触发下载 JSON 文件: ${a.download}`, 'success');
}
