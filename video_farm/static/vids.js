/**
 * Google Vids 连续生成工作台前端核心逻辑
 * Version: 20261001_v10 (极简流式单栏 + 抽屉预设 + 全屏灯箱 + 原地成片回显)
 * 支持：1080p画质、Omni/Veo模型、首尾帧/图生视频多模态、JSON批量导入/导出、本地绝对路径一键复制
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

// 元素兼容获取辅助函数
function getEl(id1, id2) {
  return document.getElementById(id1) || (id2 ? document.getElementById(id2) : null);
}

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

// 工具函数：HTML 安全转义
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(str) {
  return escapeHtml(str);
}

// 占位破损图 SVG
const BROKEN_IMG_SVG = "data:image/svg+xml," + encodeURIComponent("<svg xmlns='http://www.w3.org/2000/svg' width='120' height='70' viewBox='0 0 120 70'><rect width='100%' height='100%' fill='#1e293b'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' fill='#94a3b8' font-size='11' font-family='sans-serif'>未找到本地图片</text></svg>");

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

// --- 抽屉折叠控制 ---
function toggleAssetsDrawer() {
  const drawer = document.getElementById('assets-drawer');
  const arrow = document.getElementById('drawer-arrow');
  if (!drawer) return;
  drawer.classList.toggle('open');
  if (arrow) {
    arrow.textContent = drawer.classList.contains('open') ? '▴' : '▾';
  }
}

// --- 全屏高清灯箱控制 ---
function openLightbox(imgSrc, title = '图片高清预览') {
  if (!imgSrc) return;
  const modal = document.getElementById('lightbox-modal');
  const img = document.getElementById('lightbox-img');
  const caption = document.getElementById('lightbox-caption');
  if (!modal || !img) return;
  img.src = imgSrc;
  if (caption) caption.textContent = title;
  modal.classList.add('active');
}

function closeLightbox() {
  const modal = document.getElementById('lightbox-modal');
  if (modal) modal.classList.remove('active');
}

// 监听键盘 ESC 键关闭灯箱与弹窗
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeLightbox();
    closeJsonModal();
  }
});

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  appendLog('正在连接 Google Vids 工作流服务...', 'info');
  try {
    await loadOverview();
    await loadPresets();
    await loadInitialWorkflow();
    startAutoRefresh();
    appendLog('系统初始化完毕，1080p画质、首尾帧多模态与极简流水线工作台已就绪。', 'success');
  } catch (err) {
    console.error('初始化失败:', err);
    appendLog('初始化失败: ' + err.message, 'error');
  }
});

// 加载概览
async function loadOverview() {
  try {
    const overview = await api('/overview');
    const badge = getEl('doc-timeline-badge', 'vids-doc-title');
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

  const promptInput = getEl('wf-style-prompt', 'global-style-prompt');
  if (promptInput) {
    promptInput.value = preset.style_prompt || '';
  }

  const aspectSelect = getEl('wf-aspect-ratio', 'workflow-aspect-ratio');
  if (aspectSelect && preset.aspect_ratio) {
    aspectSelect.value = preset.aspect_ratio;
  }

  const durationSelect = getEl('wf-duration', 'workflow-shot-duration');
  if (durationSelect && preset.duration_per_shot) {
    durationSelect.value = String(preset.duration_per_shot);
  }

  const badge = document.getElementById('preset-badge');
  if (badge) {
    badge.textContent = title;
  }

  appendLog(`已应用风格预设资产包：「${title}」`, 'highlight');
}

// 刷新并渲染顶部工作流下拉选择菜单
async function refreshWorkflowSelect(targetId) {
  const selectEl = document.getElementById("workflow-select");
  if (!selectEl) return;
  try {
    const data = await api("/workflows");
    const workflows = data.workflows || [];
    selectEl.innerHTML = "";

    workflows.forEach((w) => {
      const total = w.total_shots !== undefined ? w.total_shots : ((w.shots || []).length);
      const completed = w.completed_shots !== undefined ? w.completed_shots : ((w.shots || []).filter(s => s.status === "completed" || s.video_url).length);
      const opt = document.createElement("option");
      opt.value = w.id;

      let badge = "";
      if (completed > 0) {
        badge = `🎬 [已成片 ${completed}/${total}] `;
      } else if (total > 0) {
        badge = `⏳ [待生成 0/${total}] `;
      } else {
        badge = `📁 [空工程] `;
      }
      opt.textContent = `${badge}${w.title} (${w.resolution || "1080p"})`;
      if (w.id === targetId) {
        opt.selected = true;
      }
      selectEl.appendChild(opt);
    });

    if (targetId) {
      selectEl.value = targetId;
    }
  } catch (err) {
    console.error("刷新工作流下拉菜单失败:", err);
  }
}

// 用户在下拉菜单切换工作流事件
async function onWorkflowSelectChange(workflowId) {
  if (!workflowId || workflowId === state.currentWorkflowId) return;
  appendLog(`正在切换工作流至: ${workflowId}...`, "info");
  await selectWorkflow(workflowId);
}

// 加载初始工作流（智能选取：记忆 > 有成片 > 镜头最多 > 首个）
async function loadInitialWorkflow() {
  const data = await api("/workflows");
  const workflows = data.workflows || [];
  if (workflows.length === 0) {
    // 自动创建一个默认示范工作流（1080p，Omni多模态）
    const newWf = await api("/workflows", {
      method: "POST",
      body: {
        title: "示例工程 · 电影感多镜头连续连拍工作流 (1080p)",
        doc_url: "https://docs.google.com/videos/d/1EXFiC89I2CzVObDNGCXejn-FYySYoaKPjRIG8Fa6nS4/edit",
        style_prompt: "Cinematic 8k, Unreal Engine 5 render, anamorphic lens, high contrast, atmospheric lighting, ultra-detailed.",
        aspect_ratio: "16:9",
        duration_per_shot: 10,
        resolution: "1080p",
        model_name: "Omni"
      }
    });
    await selectWorkflow(newWf.id);
    return;
  }

  // 1. 尝试从 localStorage 恢复用户上次查看或生成的工程
  const savedId = localStorage.getItem("vids_last_workflow_id");
  let targetWf = workflows.find(w => w.id === savedId);

  // 2. 如果没有记忆或该工作流已被删除，优先寻找拥有已生成成片的工作流（如刚生成的抗逆防卫 vw_ac70a427c2）
  if (!targetWf) {
    targetWf = workflows.find(w => (w.completed_shots || 0) > 0 || ((w.shots || []).some(s => s.status === "completed" || s.video_url)));
  }

  // 3. 如果都没有成片，优先寻找包含分镜镜头数最多的工作流
  if (!targetWf) {
    let maxShots = -1;
    workflows.forEach(w => {
      const count = w.total_shots !== undefined ? w.total_shots : ((w.shots || []).length);
      if (count > maxShots) {
        maxShots = count;
        targetWf = w;
      }
    });
  }

  // 4. 兜底取第一个
  if (!targetWf) {
    targetWf = workflows[0];
  }

  await selectWorkflow(targetWf.id);
}

// 选择/加载工作流详情
async function selectWorkflow(workflowId) {
  state.currentWorkflowId = workflowId;
  localStorage.setItem("vids_last_workflow_id", workflowId);

  const wf = await api(`/workflows/${workflowId}`);
  state.workflow = wf;

  // 刷新并同步下拉框选中状态
  await refreshWorkflowSelect(workflowId);

  // 更新顶部标题与描述
  const titleEl = getEl("workflow-title-display", "current-workflow-title");
  if (titleEl) titleEl.textContent = wf.title;

  const docTitleEl = document.getElementById("vids-doc-title");
  if (docTitleEl) docTitleEl.textContent = `当前工程: ${wf.title}`;

  const descEl = getEl("workflow-meta-desc", "current-workflow-desc");
  if (descEl) {
    const res = wf.resolution || "1080p";
    const model = wf.model_name || "Omni";
    descEl.textContent = `画幅 ${wf.aspect_ratio || "16:9"} · 清晰度 ${res} · 模型 ${model} · 单镜头 ${wf.duration_per_shot || 10}秒 · 包含 ${(wf.shots || []).length} 个分镜 · 原地即显即播并支持绝对路径直接导入 Google Vids`;
  }

  const promptInput = getEl("wf-style-prompt", "global-style-prompt");
  if (promptInput) promptInput.value = wf.style_prompt || "";

  const aspectSelect = getEl("wf-aspect-ratio", "workflow-aspect-ratio");
  if (aspectSelect) aspectSelect.value = wf.aspect_ratio || "16:9";

  const durationSelect = getEl("wf-duration", "workflow-shot-duration");
  if (durationSelect) durationSelect.value = String(wf.duration_per_shot || 10);

  const resSelect = getEl("wf-resolution", "workflow-resolution");
  if (resSelect) resSelect.value = wf.resolution || "1080p";

  const modelSelect = getEl("wf-model-name", "workflow-model-name");
  if (modelSelect) modelSelect.value = wf.model_name || "Omni";

  const docUrlInput = getEl("wf-doc-url", "workflow-doc-url");
  if (docUrlInput && wf.doc_url) docUrlInput.value = wf.doc_url;

  renderShots(wf.shots || []);
  updateOverallProgress(wf.shots || []);
  appendLog(`已载入工作流 [${wf.title}] (画质: ${wf.resolution || "1080p"}, 模型: ${wf.model_name || "Omni"})，共 ${(wf.shots || []).length} 个分镜卡片。`, "info");
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
          可点击上方快捷栏「📥 批量导入 JSON」直接导入现成资产，或在「⚙️ 资产预设与剧本拆解」中粘贴文案智能拆解
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
                  value="${escapeAttr(shot.image_url || '')}"
                  placeholder="输入本地图片路径、URL或点击上传"
                  onchange="updateShotField('${shot.id}', 'image_url', this.value)" />
                <label class="btn btn-secondary btn-sm" style="cursor: pointer; margin: 0; padding: 4px 10px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;">
                  📁 本地上传
                  <input type="file" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'image_url')" />
                </label>
                ${hasStartImg ? `
                  <button class="btn btn-secondary btn-sm" style="padding: 4px 8px; font-size: 11px;" onclick="openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 首帧/参考图')" title="全屏大图预览">🔍</button>
                  <button class="btn btn-secondary btn-sm" style="padding: 4px 8px; font-size: 11px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'image_url')" title="清除图片">❌</button>
                ` : ''}
              </div>
              ${hasStartImg ? `
                <div style="margin-top: 6px; position: relative;">
                  <img src="${getAssetDisplayUrl(shot.image_url)}" class="frame-asset-thumb" title="点击全屏高清查看" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 首帧/参考图')" style="cursor: pointer;" />
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
            <!-- 起始首帧 -->
            <div class="frame-asset-box ${hasStartImg ? 'has-image' : ''}">
              <div class="frame-asset-header">
                <span>🖼️ 起始首帧 (Start Frame)</span>
                <span style="font-size: 10px; color: var(--text-muted);">镜头开头画面</span>
              </div>
              <div class="frame-asset-input-row">
                <input type="text" class="form-input" style="font-size: 11px; padding: 3px 6px; flex: 1;"
                  value="${escapeAttr(shot.image_url || '')}"
                  placeholder="起始帧路径或URL"
                  onchange="updateShotField('${shot.id}', 'image_url', this.value)" />
                <label class="btn btn-secondary btn-sm" style="cursor: pointer; margin: 0; padding: 3px 8px; font-size: 11px;">
                  📁 上传
                  <input type="file" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'image_url')" />
                </label>
                ${hasStartImg ? `
                  <button class="btn btn-secondary btn-sm" style="padding: 3px 6px; font-size: 11px;" onclick="openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 起始首帧')" title="全屏查看">🔍</button>
                  <button class="btn btn-secondary btn-sm" style="padding: 3px 6px; font-size: 11px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'image_url')" title="清除">❌</button>
                ` : ''}
              </div>
              ${hasStartImg ? `
                <div style="margin-top: 6px;">
                  <img src="${getAssetDisplayUrl(shot.image_url)}" class="frame-asset-thumb" title="点击全屏高清查看" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 起始首帧')" style="cursor: pointer;" />
                </div>
              ` : `
                <div class="frame-asset-thumb-placeholder">未设置起始帧</div>
              `}
            </div>

            <!-- 目标尾帧 -->
            <div class="frame-asset-box ${hasEndImg ? 'has-image' : ''}">
              <div class="frame-asset-header">
                <span>🎞️ 目标尾帧 (End Frame)</span>
                <span style="font-size: 10px; color: var(--text-muted);">平滑过渡终点</span>
              </div>
              <div class="frame-asset-input-row">
                <input type="text" class="form-input" style="font-size: 11px; padding: 3px 6px; flex: 1;"
                  value="${escapeAttr(shot.end_image_url || '')}"
                  placeholder="尾帧路径或URL"
                  onchange="updateShotField('${shot.id}', 'end_image_url', this.value)" />
                <label class="btn btn-secondary btn-sm" style="cursor: pointer; margin: 0; padding: 3px 8px; font-size: 11px;">
                  📁 上传
                  <input type="file" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'end_image_url')" />
                </label>
                ${hasEndImg ? `
                  <button class="btn btn-secondary btn-sm" style="padding: 3px 6px; font-size: 11px;" onclick="openLightbox('${getAssetDisplayUrl(shot.end_image_url)}', '分镜 #${index + 1} 目标尾帧')" title="全屏查看">🔍</button>
                  <button class="btn btn-secondary btn-sm" style="padding: 3px 6px; font-size: 11px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'end_image_url')" title="清除">❌</button>
                ` : ''}
              </div>
              ${hasEndImg ? `
                <div style="margin-top: 6px;">
                  <img src="${getAssetDisplayUrl(shot.end_image_url)}" class="frame-asset-thumb" title="点击全屏高清查看" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="openLightbox('${getAssetDisplayUrl(shot.end_image_url)}', '分镜 #${index + 1} 目标尾帧')" style="cursor: pointer;" />
                </div>
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
      const localPathAttr = escapeAttr(shot.local_video_path || '');
      mediaPreview = `
        <div class="shot-preview-container">
          <video controls autoplay muted loop src="${shot.video_url}" style="width: 100%; border-radius: 8px; max-height: 240px; background: #000; box-shadow: 0 4px 12px rgba(0,0,0,0.4);"></video>
          <div style="margin-top: 8px; display: flex; flex-direction: column; gap: 6px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
              <a href="${shot.video_url}" target="_blank" download class="btn btn-sm btn-primary" style="font-size: 11px; padding: 4px 10px; text-decoration: none; font-weight: 600;">
                ⬇️ 下载 1080p MP4 原片
              </a>
              <button class="btn btn-sm btn-secondary" style="font-size: 11px; padding: 4px 10px; font-weight: 600;" onclick="copyLocalVideoPath('${shot.video_url}', this, '${localPathAttr}')" title="复制本地绝对路径，在 Google Vids 插入/选择视频窗口中直接粘贴">
                📋 复制本地绝对路径 (Google Vids直接粘贴)
              </button>
            </div>
            <div style="font-size: 11px; color: #10b981; background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.25); border-radius: 6px; padding: 5px 8px; display: flex; align-items: center; justify-content: space-between;">
              <span>💡 已完成生成并下载 · 自动化窗口已安全退出以释放 ~800MB 内存</span>
              <span style="font-size: 10px; color: var(--text-muted);">可直接拖入或粘贴至 Google Vids 场景 ${shot.scene_index || index + 1}</span>
            </div>
          </div>
        </div>
      `;
    } else {
      // 如果没有生成视频，但有首尾帧资产，展示资产微缩预览
      if (hasStartImg && hasEndImg && mode === 'first_last_frame') {
        mediaPreview = `
          <div style="padding: 12px; border-radius: 8px; background: rgba(0,0,0,0.25); border: 1px dashed var(--border-color); display: flex; flex-direction: column; gap: 8px; align-items: center; justify-content: center;">
            <div style="font-size: 11px; color: var(--cyan-accent); font-weight: 600;">🎞️ 首尾帧过渡设计预览 (点击可全屏查看)</div>
            <div style="display: flex; align-items: center; gap: 8px; width: 100%; justify-content: center;">
              <img src="${getAssetDisplayUrl(shot.image_url)}" style="width: 44%; height: 64px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color); cursor: pointer;" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 起始首帧')" title="点击全屏高清查看" />
              <span style="font-size: 14px; color: var(--blue-primary); font-weight: 700;">➔</span>
              <img src="${getAssetDisplayUrl(shot.end_image_url)}" style="width: 44%; height: 64px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color); cursor: pointer;" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="openLightbox('${getAssetDisplayUrl(shot.end_image_url)}', '分镜 #${index + 1} 目标尾帧')" title="点击全屏高清查看" />
            </div>
            <div style="font-size: 11px; color: var(--text-muted); text-align: center;">
              已就绪首尾双锚点，点击下方「⚡ 单独生成」或上方「🚀 开始连续连拍生成」
            </div>
          </div>
        `;
      } else if (hasStartImg && (mode === 'image2video' || mode === 'extend')) {
        mediaPreview = `
          <div style="padding: 12px; border-radius: 8px; background: rgba(0,0,0,0.25); border: 1px dashed var(--border-color); display: flex; flex-direction: column; gap: 8px; align-items: center; justify-content: center;">
            <div style="font-size: 11px; color: var(--cyan-accent); font-weight: 600;">🖼️ 参考首帧已绑定 (点击可全屏查看)</div>
            <img src="${getAssetDisplayUrl(shot.image_url)}" style="width: 80%; height: 70px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color); cursor: pointer;" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" onclick="openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 参考首帧')" title="点击全屏高清查看" />
            <div style="font-size: 11px; color: var(--text-muted); text-align: center;">
              将以此图为画面基底驱动运动生成
            </div>
          </div>
        `;
      } else {
        mediaPreview = `
          <div class="shot-preview-empty">
            <div style="font-size: 28px; margin-bottom: 6px; opacity: 0.6;">🎞️</div>
            <div style="font-size: 12px; font-weight: 600; color: var(--text-sub);">等待生成 1080p 视频成片</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px; line-height: 1.4;">
              生成完成后将在此原地回显播放器，并提供绝对物理路径一键复制，无缝接入 Google Vids 时间线。
            </div>
          </div>
        `;
      }
    }

    card.innerHTML = `
      <div class="shot-card-header">
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <span class="shot-seq-badge">#${index + 1} 场景 ${shot.scene_index || index + 1}</span>
          <input type="text" class="form-input" style="padding: 2px 8px; height: 26px; font-weight: 600; width: 170px;" value="${escapeAttr(shot.name || '')}" onchange="updateShotField('${shot.id}', 'name', this.value)" />
          <span class="badge" style="font-size: 11px; padding: 2px 6px;">⏱️ ${shot.duration || 10}s</span>
          <span class="${shotRes === '1080p' ? 'badge-1080p' : 'badge-720p'}">${shotRes}</span>
          <span class="badge" style="background: rgba(59,130,246,0.15); color: var(--blue-primary); font-size: 11px;">${shotModel}</span>
          <span class="badge-mode">${getModeLabel(mode)}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div class="shot-status-badge-wrap">${statusBadge}</div>
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
            <select class="form-select" style="width: 90px; padding: 3px 8px; font-size: 11px; height: 28px; font-weight: 700; color: #10b981;" onchange="updateShotField('${shot.id}', 'resolution', this.value)">
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

          <div class="shot-error-box" style="${shot.error_message && !isDone ? '' : 'display: none; '}font-size: 11px; color: #fbbf24; background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.25); border-radius: 4px; padding: 4px 8px; margin-bottom: 6px;">
            ⚠️ 状态提示: ${escapeHtml(shot.error_message || '')} (可点击下方单独生成或上方连续生成)
          </div>

          <div>
            <label style="font-size: 12px; color: var(--text-sub); font-weight: 500; display: block; margin-bottom: 4px;">镜头提示词 (Prompt):</label>
            <textarea class="form-textarea" rows="2" style="font-size: 13px;" onchange="updateShotField('${shot.id}', 'prompt', this.value)">${escapeHtml(shot.prompt || '')}</textarea>
          </div>
          ${shot.narration ? `
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
              <label style="font-size: 11px; color: var(--text-sub);">旁白/台词 (Google Vids 场景旁白):</label>
              <button class="btn btn-secondary btn-sm" style="padding: 1px 6px; font-size: 10px;" onclick="copyNarrationText('${shot.id}', this)" title="一键复制台词，粘贴至 Google Vids 场景旁白">📋 复制旁白</button>
            </div>
            <input type="text" class="form-input" style="font-size: 12px; padding: 4px 8px;" value="${escapeAttr(shot.narration)}" onchange="updateShotField('${shot.id}', 'narration', this.value)" />
          </div>` : ''}

          <!-- 进度条 -->
          <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
            <div class="progress-bar-container" style="flex: 1; height: 6px; margin: 0;">
              <div class="progress-bar-fill" style="width: ${shot.progress || 0}%;"></div>
            </div>
            <span class="progress-text-label" style="font-size: 11px; font-weight: 600; width: 36px; text-align: right;">${shot.progress || 0}%</span>
          </div>

          <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px;">
            <button class="btn btn-secondary btn-sm" onclick="resetShot('${shot.id}')">🔄 设为待生成</button>
            <button class="btn btn-primary btn-sm" onclick="runSingleShot('${shot.id}')">⚡ 单独生成</button>
          </div>
        </div>

        <div class="shot-media-preview-box" id="shot-media-preview-${shot.id}">
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
  const prompt = getEl('wf-style-prompt', 'global-style-prompt')?.value || '';
  const aspect = getEl('wf-aspect-ratio', 'workflow-aspect-ratio')?.value || '16:9';
  const duration = parseInt(getEl('wf-duration', 'workflow-shot-duration')?.value || '10');
  const res = getEl('wf-resolution', 'workflow-resolution')?.value || '1080p';
  const model = getEl('wf-model-name', 'workflow-model-name')?.value || 'Omni';
  const docUrl = getEl('wf-doc-url', 'workflow-doc-url')?.value || '';

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
        default_duration: parseInt(getEl('wf-duration', 'workflow-shot-duration')?.value || '10'),
        style_preset: state.selectedPresetKey || ''
      }
    });

    const parsedShots = res.shots || [];
    appendLog(`拆解成功，识别到 ${parsedShots.length} 个镜头分镜，正在追加到工作流...`, 'success');

    const defaultRes = getEl('wf-resolution', 'workflow-resolution')?.value || '1080p';
    const defaultModel = getEl('wf-model-name', 'workflow-model-name')?.value || 'Omni';

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
  const defaultRes = getEl('wf-resolution', 'workflow-resolution')?.value || '1080p';
  const defaultModel = getEl('wf-model-name', 'workflow-model-name')?.value || 'Omni';
  const defaultDuration = parseInt(getEl('wf-duration', 'workflow-shot-duration')?.value || '10');

  try {
    await api(`/workflows/${state.currentWorkflowId}/shots`, {
      method: 'POST',
      body: {
        name: `分镜 ${count}`,
        prompt: 'A cinematic high quality scene, detailed 8k, photorealistic.',
        duration: defaultDuration,
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
  if (!confirm('确定要重置所有分镜的状态为待生成吗？已生成的视频链接将保留备份。')) return;
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
      btn.innerHTML = '🚀 开始连续连拍生成';
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

  const pctEl = getEl('overall-progress-pct', 'overall-percentage-text');
  if (pctEl) pctEl.textContent = `${pct}%`;

  const fillEl = document.getElementById('overall-progress-fill');
  if (fillEl) fillEl.style.width = `${pct}%`;
}

// 一键复制场景旁白台词至剪贴板（供直接置入 Google Vids 场景）
function copyNarrationText(shotId, btnEl) {
  const shot = (state.workflow?.shots || []).find(s => s.id === shotId);
  if (!shot || !shot.narration) {
    alert('该分镜暂无旁白文案');
    return;
  }
  navigator.clipboard.writeText(shot.narration).then(() => {
    const orig = btnEl ? btnEl.innerHTML : '';
    if (btnEl) btnEl.innerHTML = '✅ 已复制';
    appendLog(`分镜 [${shot.name || shotId}] 旁白台词已复制，可直接粘贴到 Google Vids 场景旁白栏。`, 'success');
    setTimeout(() => {
      if (btnEl) btnEl.innerHTML = orig;
    }, 2000);
  }).catch(() => {
    appendLog('复制旁白失败，请手动选取复制', 'warn');
  });
}

// 一键复制本地视频原片绝对路径（供在 Google Vids 插入视频时快速粘贴选择）
function copyLocalVideoPath(videoUrl, btnEl, localPath) {
  let path = localPath;
  if (!path && videoUrl) {
    const filename = videoUrl.split('/').pop().split('?')[0];
    path = 'C:\\Users\\win10\\Documents\\ChatGPT\\视频制作\\video_farm_data\\outputs\\' + filename;
  }
  if (!path) return;
  navigator.clipboard.writeText(path).then(() => {
    const orig = btnEl ? btnEl.innerHTML : '';
    if (btnEl) btnEl.innerHTML = '✅ 已复制绝对路径';
    appendLog(`已复制视频物理绝对路径: ${path} (在 Google Vids 选择视频窗口直接 Ctrl+V)`, 'success');
    setTimeout(() => {
      if (btnEl) btnEl.innerHTML = orig;
    }, 2500);
  }).catch(() => {
    prompt('请复制成片本地绝对路径：', path);
  });
}

// 增量细粒度 DOM 状态同步（不全量刷新 DOM，保护正在输入的焦点并原地挂载视频回显）
function syncShotsDOM(shots) {
  const container = document.getElementById('shots-cards-container');
  if (!container) return;

  const existingCards = container.querySelectorAll('.shot-card');
  if (existingCards.length !== shots.length) {
    renderShots(shots);
    return;
  }

  const defaultRes = state.workflow?.resolution || '1080p';

  shots.forEach((shot, index) => {
    const card = document.getElementById(`shot-card-${shot.id}`);
    if (!card) {
      renderShots(shots);
      return;
    }

    const currentStatus = shot.status || 'pending';
    const isDone = currentStatus === 'completed';
    const isRunning = currentStatus === 'running';
    const isFailed = currentStatus === 'failed';
    const shotRes = shot.resolution || defaultRes;

    // 1. 同步卡片 class
    const expectedClass = `shot-card status-${currentStatus}`;
    if (card.className !== expectedClass) {
      card.className = expectedClass;
    }

    // 2. 同步状态 Badge
    let statusBadge = '<span class="shot-status-badge status-pending">待生成</span>';
    if (isRunning) statusBadge = `<span class="shot-status-badge status-running">⏳ 生成中 ${shot.progress || 0}%</span>`;
    if (isDone) statusBadge = '<span class="shot-status-badge status-completed">✅ 已生成置入</span>';
    if (isFailed) statusBadge = '<span class="shot-status-badge status-failed">❌ 失败</span>';

    const badgeContainer = card.querySelector('.shot-status-badge-wrap');
    if (badgeContainer && badgeContainer.innerHTML !== statusBadge) {
      badgeContainer.innerHTML = statusBadge;
    }

    // 3. 同步进度条与文本
    const progressFill = card.querySelector('.progress-bar-fill');
    if (progressFill) {
      progressFill.style.width = `${shot.progress || 0}%`;
    }
    const progressText = card.querySelector('.progress-text-label');
    if (progressText) {
      progressText.textContent = `${shot.progress || 0}%`;
    }

    // 4. 同步媒体回显（核心：视频就绪时立即原地挂载播放器与释放内存提示）
    const previewBox = card.querySelector(`#shot-media-preview-${shot.id}`);
    if (previewBox) {
      const existingVideo = previewBox.querySelector('video');
      const currentVideoSrc = existingVideo ? (existingVideo.getAttribute('src') || '') : '';
      const targetVideoUrl = shot.video_url || '';

      if (targetVideoUrl) {
        if (!existingVideo || currentVideoSrc !== targetVideoUrl) {
          const localPathAttr = escapeAttr(shot.local_video_path || '');
          previewBox.innerHTML = `
            <div class="shot-preview-container">
              <video controls autoplay muted loop src="${targetVideoUrl}" style="width: 100%; border-radius: 8px; max-height: 240px; background: #000; box-shadow: 0 4px 12px rgba(0,0,0,0.4);"></video>
              <div style="margin-top: 8px; display: flex; flex-direction: column; gap: 6px;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                  <a href="${targetVideoUrl}" target="_blank" download class="btn btn-sm btn-primary" style="font-size: 11px; padding: 4px 10px; text-decoration: none; font-weight: 600;">
                    ⬇️ 下载 1080p MP4 原片
                  </a>
                  <button class="btn btn-sm btn-secondary" style="font-size: 11px; padding: 4px 10px; font-weight: 600;" onclick="copyLocalVideoPath('${targetVideoUrl}', this, '${localPathAttr}')" title="复制本地绝对路径，在 Google Vids 插入/选择视频窗口中直接粘贴">
                    📋 复制本地绝对路径 (Google Vids直接粘贴)
                  </button>
                </div>
                <div style="font-size: 11px; color: #10b981; background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.25); border-radius: 6px; padding: 5px 8px; display: flex; align-items: center; justify-content: space-between;">
                  <span>💡 已完成生成并下载 · 自动化窗口已安全退出以释放 ~800MB 内存</span>
                  <span style="font-size: 10px; color: var(--text-muted);">可直接拖入或粘贴至 Google Vids 场景 ${shot.scene_index || index + 1}</span>
                </div>
              </div>
            </div>
          `;
          appendLog(`分镜 [${shot.name || shot.id}] 1080p 视频成片已回显就绪！`, 'success');
        }
      } else {
        if (existingVideo) {
          renderShots(shots);
          return;
        }
      }
    }

    // 5. 错误提示框同步
    const errBox = card.querySelector('.shot-error-box');
    if (errBox) {
      if (shot.error_message && !isDone) {
        errBox.style.display = 'block';
        errBox.textContent = `⚠️ 状态提示: ${shot.error_message} (可点击下方单独生成或上方连续生成)`;
      } else {
        errBox.style.display = 'none';
      }
    }
  });
}

// 定时自动同步最新状态（移除 isEditing 阻断，采用细粒度 DOM 增量同步）
function startAutoRefresh() {
  if (state.autoRefreshTimer) clearInterval(state.autoRefreshTimer);
  state.autoRefreshTimer = setInterval(async () => {
    if (state.currentWorkflowId) {
      try {
        const wf = await api(`/workflows/${state.currentWorkflowId}`);
        state.workflow = wf;
        syncShotsDOM(wf.shots || []);
        updateOverallProgress(wf.shots || []);
      } catch (e) {
        // 静默刷新
      }
    }
  }, 3000);
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
        doc_url: getEl('wf-doc-url', 'workflow-doc-url')?.value || '',
        style_prompt: getEl('wf-style-prompt', 'global-style-prompt')?.value || '',
        aspect_ratio: getEl('wf-aspect-ratio', 'workflow-aspect-ratio')?.value || '16:9',
        duration_per_shot: parseInt(getEl('wf-duration', 'workflow-shot-duration')?.value || '10'),
        resolution: getEl('wf-resolution', 'workflow-resolution')?.value || '1080p',
        model_name: getEl('wf-model-name', 'workflow-model-name')?.value || 'Omni'
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
    const autoStartBox = document.getElementById('import-auto-start-checkbox');
    const autoStart = autoStartBox ? Boolean(autoStartBox.checked) : true;

    const res = await api('/batch_import', {
      method: 'POST',
      body: {
        workflow_id: state.currentWorkflowId,
        import_mode: importMode,
        auto_start: autoStart,
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
  const textarea = getEl('batch-export-textarea', 'export-json-textarea');
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
  const textarea = getEl('batch-export-textarea', 'export-json-textarea');
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
  const textarea = getEl('batch-export-textarea', 'export-json-textarea');
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
