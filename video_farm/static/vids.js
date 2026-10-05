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
function getEl(...ids) {
  return ids.map(id => document.getElementById(id)).find(Boolean) || null;
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
  line.innerHTML = `<span style="opacity: 0.6; font-size: 11px;">[${getTimestamp()}]</span> ${escapeHtml(msg)}`;
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
  drawer.classList.toggle('active');
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
    appendLog('工作台初始化完成。可配置目标画质与首尾帧模式；实际成片规格以输出文件为准。', 'success');
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
    chip.innerHTML = `<span>${escapeHtml(icon)}</span> <span>${escapeHtml(title)}</span>`;
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
    const engLabel = (wf.engine === "flow") ? "⚡ Google Flow" : "🎬 Google Vids";
    descEl.textContent = `【${engLabel}】 画幅 ${wf.aspect_ratio || "16:9"} · 清晰度 ${res} · 模型 ${model} · 单镜头 ${wf.duration_per_shot || 10}秒 · 包含 ${(wf.shots || []).length} 个分镜 · 原地即显即播并支持绝对路径直接导入 Google Vids`;
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

  const engineSelect = getEl("wf-engine");
  if (engineSelect && wf.engine) engineSelect.value = wf.engine;

  const docUrlInput = getEl("wf-doc-url", "workflow-doc-url");
  if (docUrlInput && wf.doc_url) docUrlInput.value = wf.doc_url;

  renderShots(wf.shots || []);
  updateOverallProgress(wf.shots || []);
  appendLog(`已载入工作流 [${wf.title}] (画质: ${wf.resolution || "1080p"}, 模型: ${wf.model_name || "Omni"})，共 ${(wf.shots || []).length} 个分镜卡片。`, "info");
}

// 渲染分镜卡片
// 渲染分镜卡片 (规整紧凑高密度布局，物理限制图片尺寸，彻底消除乱图堆叠)
function getShotMediaPreviewHtml(shot, index, isDone, isRunning, isFailed, shotRes) {
  const mode = shot.mode || "text2video";
  if (isDone && shot.video_url) {
    const localPathAttr = escapeAttr(shot.local_video_path || "");
    const downloadName = `Scene${String(shot.scene_index || index + 1).padStart(2, "0")}_${(shot.name || "Shot").replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, "_")}_${shotRes}.mp4`;
    return `
      <div class="stage-video-box" style="display: flex; flex-direction: column; gap: 4px; width: 100%; height: 100%; justify-content: center; position: relative;">
        <video controls preload="metadata" style="max-width: 100%; max-height: 102px; width: 100%; object-fit: contain; border-radius: 4px; background: #000; border: 1px solid rgba(255,255,255,0.1);" src="${escapeAttr(shot.video_url)}" onerror="this.parentElement.querySelector('.shot-file-spec').innerHTML='<span style=\x22color:#ef4444\x22>⚠️ 视频加载异常，请点击下载或重新渲染</span>';"></video>
        <div class="shot-file-spec" style="font-size: 10px; color: var(--text-sub); text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">正在读取实际文件规格…</div>
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 4px; margin-top: 2px;">
          <a href="${shot.video_url}" download="${downloadName}" target="_blank" class="btn btn-primary btn-sm" style="font-size: 10px; padding: 2px 6px; text-decoration: none;" title="下载成片到本地">
            📥 下载
          </a>
          <button class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;" onclick="copyLocalVideoPath('${shot.video_url}', this, '${localPathAttr}')" title="复制本地绝对路径，在 Google Vids 中直接粘贴使用">
            📋 路径
          </button>
          <button class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px; color: #10b981;" onclick="generateSingleShot('${shot.id}')" title="重新渲染该镜头">
            🔄 重渲
          </button>
        </div>
        <div style="font-size: 9px; color: #10b981; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
          ✅ Google Vids 原生成片就绪
        </div>
      </div>
    `;
  } else if (isRunning) {
    return `
      <div class="stage-running-box" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 6px; padding: 8px 12px; background: rgba(59,130,246,0.06); border-radius: 6px; border: 1px dashed rgba(59,130,246,0.3);">
        <div class="pulse-radar-loader" style="font-size: 22px; animation: spin 2s linear infinite;">⚙️</div>
        <div style="font-size: 12px; font-weight: 700; color: #60a5fa;">Google Vids 渲染中</div>
        <div style="width: 100%; background: rgba(255,255,255,0.1); border-radius: 999px; height: 6px; overflow: hidden; position: relative;">
          <div style="width: ${shot.progress || 15}%; height: 100%; background: linear-gradient(90deg, #3b82f6, #06b6d4); border-radius: 999px; transition: width 0.3s;"></div>
        </div>
        <div style="font-size: 10px; color: var(--text-sub); display: flex; justify-content: space-between; width: 100%;">
          <span>进度: ${shot.progress || 10}%</span>
          <span>云端渲染同步中</span>
        </div>
        <button class="btn btn-danger btn-sm" style="font-size: 10px; padding: 2px 10px; margin-top: 4px; background: #dc2626; border-color: #b91c1c; font-weight: 700;" onclick="stopRunningShot('${shot.id}')" title="强行中止渲染并释放资源">
          ⏹ 停止当前渲染
        </button>
      </div>
    `;
  } else if (isFailed) {
    const errBrief = (shot.error_message || "视频生成遇到异常").slice(0, 48);
    return `
      <div class="stage-failed-box" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 4px; padding: 8px 10px; background: rgba(239,68,68,0.08); border-radius: 6px; border: 1px dashed rgba(239,68,68,0.35);">
        <div style="font-size: 20px;">⚠️</div>
        <div style="font-size: 11px; font-weight: 700; color: #f87171; text-align: center;">渲染未完成</div>
        <div style="font-size: 10px; color: #fca5a5; text-align: center; line-height: 1.2; max-height: 32px; overflow: hidden; text-overflow: ellipsis;" title="${escapeAttr(shot.error_message || "")}">
          ${escapeHtml(errBrief)}
        </div>
        <button class="btn btn-primary btn-sm" style="font-size: 11px; padding: 3px 12px; background: #dc2626; border-color: #ef4444; margin-top: 4px;" onclick="generateSingleShot('${shot.id}')" title="清空错误并重新下发干净任务">
          🔄 重新生成此镜头
        </button>
      </div>
    `;
  } else {
    return `
      <div class="stage-waiting-box" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 4px;">
        <div style="font-size: 20px; opacity: 0.6;">🎬</div>
        <div style="font-size: 12px; font-weight: 600; color: var(--text-main);">等待镜头成片</div>
        <div style="font-size: 10px; color: var(--text-muted); line-height: 1.2;">
          ${mode === "first_last_frame" ? "首尾帧过渡 · 1080p 原生插值" : (mode === "image2video" ? "单图参考生成" : "纯提示词渲染")}
        </div>
        <button class="btn btn-primary btn-sm" style="margin-top: 4px; font-size: 10px; padding: 2px 12px;" onclick="generateSingleShot('${shot.id}')">
          ⚡ 单独渲染
        </button>
      </div>
    `;
  }
}

function renderShots(shots) {
  const container = document.getElementById('shots-cards-container');
  if (!container) return;
  container.innerHTML = '';
  renderShotIndex(shots);

  if (shots.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 36px; background: var(--bg-surface); border-radius: var(--radius-md); border: 1px dashed var(--border-color);">
        <div style="font-size: 32px; margin-bottom: 8px;">🎬</div>
        <div style="font-size: 15px; font-weight: 600; color: var(--text-main);">当前工程暂无分镜镜头</div>
        <div style="font-size: 12px; color: var(--text-sub); margin-top: 4px;">
          可点击上方快捷栏「📥 导入 JSON」导入分镜资产，或点击「➕ 新增镜头」手动创建
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
    const isQueued = shot.status === 'queued';
    const isFailed = shot.status === 'failed';

    let statusBadge = '<span class="shot-status-badge status-pending">待生成</span>';
    if (isRunning) statusBadge = `<span class="shot-status-badge status-running">生成中 ${shot.progress || 0}%</span>`;
    if (isDone) statusBadge = '<span class="shot-status-badge status-completed">已成片</span>';
    if (isFailed) statusBadge = '<span class="shot-status-badge status-failed">失败</span>';

    const mode = shot.mode || 'text2video';
    const shotRes = shot.resolution || defaultRes;
    const shotModel = shot.model_name || defaultModel;

    const hasStartImg = Boolean(shot.image_url);
    const hasEndImg = Boolean(shot.end_image_url);

    // 左列：资产横向胶囊排布 (严控尺寸，首尾帧并排一行)
    let frameAssetHtml = '';
    if (mode === 'first_last_frame') {
      frameAssetHtml = `
        <div class="frame-duo-strip">
          <div class="frame-capsule">
            <span class="frame-capsule-tag">首帧</span>
            <div class="frame-capsule-thumb" onclick="${hasStartImg ? `openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 起始首帧')` : `document.getElementById('file-upload-${shot.id}-start').click()`}" title="${hasStartImg ? '点击全屏高清查看' : '点击上传本地图片'}">
              ${hasStartImg ? `
                <img loading="lazy" decoding="async" src="${getAssetDisplayUrl(shot.image_url)}" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" />
              ` : `
                <div class="frame-capsule-empty">+首帧</div>
              `}
            </div>
            <input type="text" class="frame-capsule-input" aria-label="参考画面路径" value="${escapeAttr(shot.image_url || '')}" placeholder="首帧绝对路径或URL" onchange="updateShotField('${shot.id}', 'image_url', this.value)" />
            <label class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 5px; font-size: 10px; cursor: pointer; margin: 0;" title="选择本地文件">
              📁<input type="file" id="file-upload-${shot.id}-start" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'image_url')" />
            </label>
            ${hasStartImg ? `
              <button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 4px; font-size: 10px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'image_url')" title="清除图片">✕</button>
            ` : ''}
          </div>

          <div class="frame-duo-arrow" title="平滑镜头过渡">➔</div>

          <div class="frame-capsule">
            <span class="frame-capsule-tag">尾帧</span>
            <div class="frame-capsule-thumb" onclick="${hasEndImg ? `openLightbox('${getAssetDisplayUrl(shot.end_image_url)}', '分镜 #${index + 1} 目标尾帧')` : `document.getElementById('file-upload-${shot.id}-end').click()`}" title="${hasEndImg ? '点击全屏高清查看' : '点击上传本地图片'}">
              ${hasEndImg ? `
                <img loading="lazy" decoding="async" src="${getAssetDisplayUrl(shot.end_image_url)}" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" />
              ` : `
                <div class="frame-capsule-empty">+尾帧</div>
              `}
            </div>
            <input type="text" class="frame-capsule-input" aria-label="参考画面路径" value="${escapeAttr(shot.end_image_url || '')}" placeholder="尾帧绝对路径或URL" onchange="updateShotField('${shot.id}', 'end_image_url', this.value)" />
            <label class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 5px; font-size: 10px; cursor: pointer; margin: 0;" title="选择本地文件">
              📁<input type="file" id="file-upload-${shot.id}-end" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'end_image_url')" />
            </label>
            ${hasEndImg ? `
              <button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 4px; font-size: 10px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'end_image_url')" title="清除图片">✕</button>
            ` : ''}
          </div>
        </div>
      `;
    } else if (mode === 'image2video' || mode === 'extend') {
      frameAssetHtml = `
        <div class="frame-duo-strip">
          <div class="frame-capsule" style="flex: 1;">
            <span class="frame-capsule-tag">参考图</span>
            <div class="frame-capsule-thumb" onclick="${hasStartImg ? `openLightbox('${getAssetDisplayUrl(shot.image_url)}', '分镜 #${index + 1} 参考图')` : `document.getElementById('file-upload-${shot.id}-start').click()`}" title="${hasStartImg ? '点击全屏高清查看' : '点击上传本地图片'}">
              ${hasStartImg ? `
                <img loading="lazy" decoding="async" src="${getAssetDisplayUrl(shot.image_url)}" onerror="this.onerror=null; this.src=BROKEN_IMG_SVG;" />
              ` : `
                <div class="frame-capsule-empty">+选图</div>
              `}
            </div>
            <input type="text" class="frame-capsule-input" aria-label="参考画面路径" value="${escapeAttr(shot.image_url || '')}" placeholder="参考图绝对路径或URL" onchange="updateShotField('${shot.id}', 'image_url', this.value)" />
            <label class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 5px; font-size: 10px; cursor: pointer; margin: 0;">
              📁 上传<input type="file" id="file-upload-${shot.id}-start" accept="image/*" style="display: none;" onchange="handleAssetUpload(this, '${shot.id}', 'image_url')" />
            </label>
            ${hasStartImg ? `
              <button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 4px; font-size: 10px; color: #ef4444;" onclick="clearShotAsset('${shot.id}', 'image_url')" title="清除">✕</button>
            ` : ''}
          </div>
        </div>
      `;
    } else {
      frameAssetHtml = `
        <div style="font-size: 11px; color: var(--text-muted); background: rgba(0,0,0,0.2); padding: 4px 8px; border-radius: 4px; border: 1px dashed rgba(255,255,255,0.06);">
          💬 纯提示词文生视频模式 (无需附加参考图资产)
        </div>
      `;
    }

    // 右列：监视器与交付舞台 (状态化原生回显)
    const mediaPreview = getShotMediaPreviewHtml(shot, index, isDone, isRunning, isFailed, shotRes);

card.innerHTML = `
      <div class="shot-card-header">
        <div class="shot-header-left">
          <span class="shot-seq-badge">#${index + 1} 场景 ${shot.scene_index || index + 1}</span>
          <input type="text" class="form-input shot-name-input" aria-label="镜头名称" style="padding: 1px 6px; height: 24px; font-weight: 600; width: 140px; font-size: 11px;" value="${escapeAttr(shot.name || '')}" onchange="updateShotField('${shot.id}', 'name', this.value)" />
          <span class="badge" style="font-size: 10px; padding: 1px 5px;">请求 ${shot.duration || 8}s</span>
          <span class="${shotRes === '1080p' ? 'badge-1080p' : 'badge-720p'}">请求 ${shotRes}</span>
          <span class="badge" style="background: rgba(59,130,246,0.15); color: var(--blue-primary); font-size: 10px; padding: 1px 5px;">${shotModel}</span>
        </div>
        <div class="shot-header-actions">
          <div class="shot-status-badge-wrap">${statusBadge}</div>
          ${(isRunning || isQueued) ? `<button class="btn btn-danger btn-sm btn-dynamic-stop" style="height: 22px; padding: 0 6px; font-size: 10px; background: #dc2626; border-color: #b91c1c; font-weight:700;" onclick="stopRunningShot('${shot.id}')" title="强行中止当前镜头渲染并释放资源">⏹ 停止</button>` : ''}
          ${isFailed ? `<button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 6px; font-size: 10px; color: #f87171; border-color: rgba(239,68,68,0.4);" onclick="generateSingleShot('${shot.id}')" title="重试该镜头">🔄 重试</button>` : ''}
          ${isDone ? `<button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 6px; font-size: 10px; color: #10b981;" onclick="generateSingleShot('${shot.id}')" title="重新渲染该镜头">🔄 重渲</button>` : ''}
          <button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 5px;" onclick="moveShot('${shot.id}', 'up')" title="上移" aria-label="上移镜头">↑</button>
          <button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 5px;" onclick="moveShot('${shot.id}', 'down')" title="下移" aria-label="下移镜头">↓</button>
          <button class="btn btn-danger btn-sm" style="height: 22px; padding: 0 5px;" onclick="deleteShot('${shot.id}')" title="删除" aria-label="删除镜头">×</button>
        </div>
      </div>

      <div class="shot-body-layout">
        <!-- 左列：模式选择、资产条带、提示词与旁白 -->
        <div class="shot-params-col">
          <div class="shot-config-row" style="display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.25); padding: 3px 6px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05); flex-wrap: wrap;">
            <span style="font-size: 10px; color: var(--text-sub); font-weight: 600;">模式:</span>
            <select class="form-select" style="width: 125px; padding: 1px 4px; font-size: 10px; height: 22px; font-weight: 600;" onchange="updateShotMode('${shot.id}', this.value)">
              <option value="first_last_frame" ${mode === 'first_last_frame' ? 'selected' : ''}>🎞️ 首尾帧过渡</option>
              <option value="image2video" ${mode === 'image2video' ? 'selected' : ''}>🖼️ 图生/首帧参考</option>
              <option value="text2video" ${mode === 'text2video' ? 'selected' : ''}>💬 文生视频</option>
              <option value="extend" ${mode === 'extend' ? 'selected' : ''}>⏩ 尾帧画面延续</option>
            </select>

            <span style="font-size: 10px; color: var(--text-sub); font-weight: 600; margin-left: 2px;">画质:</span>
            <select class="form-select" style="width: 75px; padding: 1px 4px; font-size: 10px; height: 22px; font-weight: 700; color: #10b981;" onchange="updateShotField('${shot.id}', 'resolution', this.value)">
              <option value="1080p" ${shotRes === '1080p' ? 'selected' : ''}>1080p</option>
              <option value="720p" ${shotRes === '720p' ? 'selected' : ''}>720p</option>
            </select>

            <span style="font-size: 10px; color: var(--text-sub); font-weight: 600; margin-left: 2px;">模型:</span>
            <select class="form-select" style="width: 75px; padding: 1px 4px; font-size: 10px; height: 22px;" onchange="updateShotField('${shot.id}', 'model_name', this.value)">
              <option value="Omni" ${shotModel === 'Omni' ? 'selected' : ''}>Omni</option>
              <option value="Veo" ${shotModel === 'Veo' ? 'selected' : ''}>Veo</option>
              <option value="Veo-Lite" ${shotModel === 'Veo-Lite' ? 'selected' : ''}>Veo-Lite</option>
            </select>

            <span style="font-size: 10px; color: var(--text-sub); font-weight: 600; margin-left: 2px;">途径:</span>
            <select class="form-select" style="width: 80px; padding: 1px 4px; font-size: 10px; height: 22px; font-weight: 600; color: #38bdf8;" onchange="updateShotField('${shot.id}', 'engine', this.value)">
              <option value="vids" ${(shot.engine || state.workflow?.engine || 'vids') === 'vids' ? 'selected' : ''}>🎬 Vids</option>
              <option value="flow" ${(shot.engine || state.workflow?.engine || 'vids') === 'flow' ? 'selected' : ''}>⚡ Flow</option>
            </select>
          </div>

          <!-- 资产胶囊条带 (严控高、首尾帧并排) -->
          ${frameAssetHtml}

          <!-- 当首尾帧与 Vids 冲突时的显式提示 -->
          ${((mode === 'first_last_frame' || Boolean(shot.end_image_url)) && (shot.engine || state.workflow?.engine || 'vids') === 'vids') ? `
            <div class="vids-engine-warn-pill" style="font-size: 10px; color: #f59e0b; background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3); border-radius: 4px; padding: 2px 6px; display: flex; align-items: center; justify-content: space-between; gap: 4px; margin-top: 2px;">
              <span>⚠️ <strong>提示：</strong>Google Vids 仅支持首帧微动（无法约束尾帧）。如需首尾两端关键帧插值，请将途径切换为 ⚡ Flow</span>
              <button class="btn btn-secondary btn-sm" style="font-size: 9px; padding: 1px 5px; height: 18px; color: #38bdf8; border-color: rgba(56,189,248,0.4);" onclick="updateShotField('${shot.id}', 'engine', 'flow'); this.parentElement.style.display='none';">切为Flow</button>
            </div>
          ` : `
            <div class="vids-engine-warn-pill" style="display: none;"></div>
          `}

          <div class="shot-error-box" style="${shot.error_message && !isDone ? '' : 'display: none; '}font-size: 10px; color: #fbbf24; background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.25); border-radius: 4px; padding: 2px 6px;">
            ⚠️ ${escapeHtml(shot.error_message || '')}
          </div>

          <div>
            <textarea aria-label="镜头提示词" class="form-textarea" rows="2" style="font-size: 11px; padding: 4px 6px; width: 100%; height: 46px;" placeholder="镜头英文/中文提示词..." onchange="updateShotField('${shot.id}', 'prompt', this.value)">${escapeHtml(shot.prompt || '')}</textarea>
          </div>

          ${shot.narration ? `
          <div style="display: flex; align-items: center; gap: 6px;">
            <input type="text" class="form-input" style="font-size: 11px; padding: 2px 6px; height: 24px; flex: 1; color: var(--text-sub);" value="${escapeAttr(shot.narration)}" placeholder="剪辑旁白/台词" onchange="updateShotField('${shot.id}', 'narration', this.value)" />
            <button class="btn btn-secondary btn-sm" style="height: 22px; padding: 0 6px; font-size: 10px;" onclick="copyNarrationText('${shot.id}', this)" title="复制台词">复制台词</button>
          </div>
          ` : ''}
        </div>

        <!-- 右列：监视器与交付舞台 (严格固定 175px 高度) -->
        <div class="shot-media-preview-box" id="shot-media-preview-${shot.id}">
          ${mediaPreview}
        </div>
      </div>
    `;

    container.appendChild(card);
  });
  bindShotMedia(container);
}


// Presentation-only shot directory: source IDs and content remain in the existing cards.
function renderShotIndex(shots) {
  const host = document.getElementById('shot-index-items');
  const count = document.getElementById('shot-index-count');
  if (!host) return;
  const signature = JSON.stringify(shots.map(s => [s.id, s.name, s.title, s.status]));
  if (host.dataset.signature === signature) return;
  host.dataset.signature = signature;
  const selected = host.querySelector('[aria-current="true"]')?.dataset.shotId;
  host.replaceChildren();
  if (count) count.textContent = String(shots.length);
  const statuses = {completed:'已成片',running:'生成中',failed:'失败',pending:'待生成'};
  shots.forEach((shot, i) => {
    const link = document.createElement('a');
    link.className = 'shot-index-link';link.href = '#shot-card-' + shot.id;link.dataset.shotId = shot.id;
    link.dataset.status = shot.status || 'pending';
    if (shot.id === selected) { link.classList.add('active'); link.setAttribute('aria-current','true'); }
    const number = document.createElement('i');number.textContent = String(i + 1).padStart(2, '0');
    const title = document.createElement('span');title.textContent = shot.name || shot.title || ('镜头 ' + (i + 1));
    link.title = title.textContent + ' · ' + (statuses[shot.status] || '待检查');link.append(number, title);
    link.setAttribute('aria-label',link.title);
    link.addEventListener('click', event => {
      event.preventDefault();
      document.getElementById('shot-card-' + shot.id)?.scrollIntoView({block: 'start', behavior: 'auto'});
      host.querySelectorAll('a').forEach(a => {a.classList.toggle('active', a === link); if(a === link) a.setAttribute('aria-current','true'); else a.removeAttribute('aria-current');});
    });
    host.append(link);
  });
}

function bindShotMedia(container) {
  container.querySelectorAll('video').forEach(video => {
    if (video.dataset.metadataBound) return;
    video.dataset.metadataBound = 'true';
    const label = video.parentElement.querySelector('.shot-file-spec');
    const showSpecs = () => {
      if (label) label.textContent = `实际 ${video.videoWidth} × ${video.videoHeight} · ${Number.isFinite(video.duration) ? video.duration.toFixed(1) + ' 秒' : '时长未知'}`;
    };
    video.addEventListener('loadedmetadata', showSpecs);
    video.addEventListener('error', () => { if (label) label.textContent = '文件预览失败，请检查原片'; });
    if (video.readyState >= 1) showSpecs();
  });
}

// 保存工作流资产全局配置 (包含1080p画质、模型等)
async function saveWorkflowSettings() {
  if (!state.currentWorkflowId) return;
  const prompt = getEl('wf-style-prompt', 'global-style-prompt')?.value || '';
  const aspect = getEl('wf-aspect-ratio', 'workflow-aspect-ratio')?.value || '16:9';
  const duration = parseInt(getEl('wf-duration', 'workflow-shot-duration')?.value || '10');
  const res = getEl('wf-resolution', 'workflow-resolution')?.value || '1080p';
  const model = getEl('wf-model-name', 'workflow-model-name')?.value || 'Omni';
  const engine = getEl('wf-engine')?.value || 'vids';
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
        engine: engine,
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
  const hasActive = shots.some(s => s.status === 'running' || s.status === 'queued');
  const stopBtn = document.getElementById('btn-stop-continuous');
  if (stopBtn) {
    stopBtn.style.display = hasActive ? 'inline-flex' : 'none';
  }
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
  renderShotIndex(shots);
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
    if (isRunning) statusBadge = `<span class="shot-status-badge status-running">生成中 ${shot.progress || 0}%</span>`;
    if (isDone) statusBadge = '<span class="shot-status-badge status-completed">已成片</span>';
    if (isFailed) statusBadge = '<span class="shot-status-badge status-failed">失败</span>';

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

    // 4. 同步媒体回显（统一调用 getShotMediaPreviewHtml，状态机驱动）
    const previewBox = card.querySelector(`#shot-media-preview-${shot.id}`);
    if (previewBox) {
      const currentBoxState = previewBox.dataset.state || "";
      const targetState = isDone && shot.video_url ? "done" : (isRunning ? "running" : (isFailed ? "failed" : "pending"));
      const existingVideo = previewBox.querySelector("video");
      const currentVideoSrc = existingVideo ? (existingVideo.getAttribute("src") || "") : "";
      const targetVideoUrl = shot.video_url || "";

      if (currentBoxState !== targetState || (targetState === "done" && currentVideoSrc !== targetVideoUrl)) {
        previewBox.dataset.state = targetState;
        previewBox.innerHTML = getShotMediaPreviewHtml(shot, index, isDone, isRunning, isFailed, shotRes);
        if (targetState === "done") {
          appendLog(`分镜 [${shot.name || shot.id}] 成片已就绪！`, "success");
        }
      } else if (targetState === "running") {
        const pFill = previewBox.querySelector(".stage-running-box div div");
        if (pFill) pFill.style.width = `${shot.progress || 15}%`;
        const pTxt = previewBox.querySelector(".stage-running-box div span:first-child");
        if (pTxt) pTxt.textContent = `进度: ${shot.progress || 10}%`;
      }
    }

    // 头部重试按钮同步
    const headerActions = card.querySelector(".shot-header-actions");
    if (headerActions) {
      const oldRetryBtn = headerActions.querySelector(".btn-dynamic-retry");
      if (isFailed && !oldRetryBtn) {
        const btn = document.createElement("button");
        btn.className = "btn btn-secondary btn-sm btn-dynamic-retry";
        btn.style.cssText = "height: 22px; padding: 0 6px; font-size: 10px; color: #f87171; border-color: rgba(239,68,68,0.4);";
        btn.title = "重试该镜头";
        btn.textContent = "🔄 重试";
        btn.onclick = () => generateSingleShot(shot.id);
        headerActions.insertBefore(btn, headerActions.children[1] || null);
      } else if (!isFailed && oldRetryBtn) {
        oldRetryBtn.remove();
      }

      const oldStopBtn = headerActions.querySelector(".btn-dynamic-stop");
      if ((isRunning || isQueued) && !oldStopBtn) {
        const btn = document.createElement("button");
        btn.className = "btn btn-danger btn-sm btn-dynamic-stop";
        btn.style.cssText = "height: 22px; padding: 0 6px; font-size: 10px; background: #dc2626; border-color: #b91c1c; font-weight:700;";
        btn.title = "强行中止当前镜头渲染并释放资源";
        btn.textContent = "⏹ 停止";
        btn.onclick = () => stopRunningShot(shot.id);
        headerActions.insertBefore(btn, headerActions.children[1] || null);
      } else if (!(isRunning || isQueued) && oldStopBtn) {
        oldStopBtn.remove();
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
  bindShotMedia(container);
}

// 定时自动同步最新状态（移除 isEditing 阻断，采用细粒度 DOM 增量同步）
let autoRefreshInFlight = false;
function startAutoRefresh() {
  if (state.autoRefreshTimer) clearInterval(state.autoRefreshTimer);
  state.autoRefreshTimer = setInterval(async () => {
    if (document.hidden || autoRefreshInFlight || !state.currentWorkflowId) return;
    const workflowId = state.currentWorkflowId;
    autoRefreshInFlight = true;
    try {
      const wf = await api(`/workflows/${workflowId}`);
      if (workflowId !== state.currentWorkflowId) return;
      state.workflow = wf;
      syncShotsDOM(wf.shots || []);
      updateOverallProgress(wf.shots || []);
    } catch (e) {
      // Foreground operations still report errors; background refresh preserves the current editor.
    } finally { autoRefreshInFlight = false; }
  }, 3000);
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) document.querySelectorAll('#shots-cards-container video').forEach(v => v.pause());
});
document.addEventListener('play', event => {
  if (event.target.tagName === 'VIDEO') document.querySelectorAll('#shots-cards-container video').forEach(v => {if (v !== event.target) v.pause();});
}, true);

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
    const textarea = getEl('json-import-textarea', 'batch-import-textarea');
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
  const textarea = getEl('json-import-textarea', 'batch-import-textarea');
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
    const textarea = getEl('json-import-textarea', 'batch-import-textarea');
    if (textarea) {
      textarea.value = e.target.result;
      appendLog(`已成功从本地读取文件: ${file.name}`, 'info');
    }
  };
  reader.readAsText(file, 'utf-8');
}

// 执行批量导入
async function executeBatchImport() {
  const textarea = getEl('json-import-textarea', 'batch-import-textarea');
  const msgBox = document.getElementById('import-msg-box');
  const rawText = textarea?.value?.trim();

  if (!rawText) {
    alert('请先输入或粘贴 JSON 数据！');
    return;
  }

  // 获取导入模式 (new, append, replace)
  const radio = document.querySelector('input[name="import-mode-radio"]:checked');
  const importMode = radio ? radio.value : 'new';

  // 获取生成引擎途径 (vids, flow) - 解耦设计
  const engineRadio = document.querySelector('input[name="import-engine-radio"]:checked');
  let selectedEngine = 'vids';
  if (engineRadio && ['vids', 'flow', 'gemini'].includes(engineRadio.value)) {
    selectedEngine = engineRadio.value;
  }

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
  const originalButtonText = btn?.textContent;
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
        engine: selectedEngine,
        auto_start: autoStart,
        data: parsed
      }
    });

    if (res.success) {
      const importedCount = res.imported_count || 0;
      const wf = res.workflow;
      const engineLabel = selectedEngine === 'flow' ? '⚡ Google Flow 首尾帧模式' : '🎬 Google Vids 原生工作流';
      if (msgBox) {
        msgBox.style.display = 'block';
        msgBox.style.background = 'rgba(16, 185, 129, 0.15)';
        msgBox.style.color = '#10b981';
        msgBox.style.border = '1px solid #10b981';
        msgBox.innerHTML = `✅ 批量导入成功！共导入 <strong>${importedCount}</strong> 个镜头（途径：${engineLabel}，模式：${importMode === 'new' ? '新建工作流' : (importMode === 'append' ? '追加镜头' : '覆盖镜头')}，画质：${wf.resolution || '1080p'}）`;
      }
      appendLog(`【批量导入成功】已写入 ${importedCount} 个镜头资产至工作流 [${wf.title}]，生成引擎: ${engineLabel}`, 'success');

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
      btn.textContent = originalButtonText;
    }
  }
}

// 导出当前工程为标准化 JSON
async function loadWorkflowExportJson() {
  if (!state.currentWorkflowId) return;
  const textarea = getEl('json-export-textarea', 'batch-export-textarea', 'export-json-textarea');
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
  const textarea = getEl('json-export-textarea', 'batch-export-textarea', 'export-json-textarea');
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
  const textarea = getEl('json-export-textarea', 'batch-export-textarea', 'export-json-textarea');
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

// 日志面板折叠与清空
function toggleLiveLogExpand() {
  const box = document.getElementById('vids-live-log');
  const btn = document.getElementById('btn-toggle-log');
  if (!box) return;
  box.classList.toggle('expanded');
  if (btn) {
    btn.textContent = box.classList.contains('expanded') ? '收起 ⤡' : '展开 ⤢';
  }
}

function clearLiveLog() {
  const box = document.getElementById('vids-live-log');
  if (box) {
    box.innerHTML = '<div style="color: var(--text-muted);">[日志已清空]</div>';
  }
}


// 一键打包成片与剪辑清单 ZIP
function downloadWorkflowPackageZip() {
  if (!state.currentWorkflowId) {
    alert("请先选择或创建一个工程！");
    return;
  }
  appendLog(`正在打包下载当前工程成片与剪辑清单 ZIP...`, "info");
  window.location.href = `/api/vids/workflows/${state.currentWorkflowId}/package_zip`;
}

// 打开工程管理中心弹窗
async function openProjectManagerModal() {
  const modal = document.getElementById('project-modal-backdrop');
  if (!modal) return;
  modal.classList.add('active');
  await refreshProjectListModal();
}

function closeProjectModal() {
  const modal = document.getElementById('project-modal-backdrop');
  if (modal) modal.classList.remove('active');
}

// 刷新工程列表
async function refreshProjectListModal() {
  const container = document.getElementById('project-list-container');
  if (!container) return;
  container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px; text-align: center;">载入工程列表中...</div>';
  try {
    const res = await api('/workflows');
    const list = res.workflows || [];
    if (list.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px; text-align: center;">暂无工程记录</div>';
      return;
    }
    container.innerHTML = '';
    list.forEach(w => {
      const isCurrent = w.id === state.currentWorkflowId;
      const total = w.total_shots || 0;
      const done = w.completed_shots || 0;
      const item = document.createElement('div');
      item.style.cssText = `display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: ${isCurrent ? 'rgba(59,130,246,0.12)' : 'var(--bg-card)'}; border: 1px solid ${isCurrent ? 'var(--blue-primary)' : 'var(--border-color)'}; border-radius: 6px; gap: 10px;`;
      item.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <strong style="font-size: 13px; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(w.title || '未命名工程')}</strong>
            ${isCurrent ? '<span class="badge" style="font-size: 10px; background: rgba(59,130,246,0.2); color: var(--blue-primary);">当前查看</span>' : ''}
          </div>
          <div style="font-size: 11px; color: var(--text-sub);">
            ID: <code>${w.id}</code> · 分镜镜头: <strong>${total}</strong> 个 · 成片: <strong style="color: #10b981;">${done}</strong> · 画质: ${w.resolution || '1080p'}
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
          ${!isCurrent ? `<button class="btn btn-secondary btn-sm" onclick="selectWorkflowFromModal('${w.id}')">切换查看</button>` : ''}
          <button class="btn btn-secondary btn-sm" onclick="openRenameWorkflowModal('${w.id}', '${escapeAttr(w.title || '')}')">改名</button>
          <button class="btn btn-danger btn-sm" onclick="deleteWorkflowFromModal('${w.id}')">删除</button>
        </div>
      `;
      container.appendChild(item);
    });
  } catch (e) {
    container.innerHTML = `<div style="color: #ef4444; font-size: 12px;">加载失败: ${e.message}</div>`;
  }
}

async function selectWorkflowFromModal(wfId) {
  closeProjectModal();
  await selectWorkflow(wfId);
}

async function deleteWorkflowFromModal(wfId) {
  if (!confirm(`确定要彻底删除该工程吗？删除后不可恢复。`)) return;
  try {
    await api(`/workflows/${wfId}`, { method: 'DELETE' });
    appendLog(`工程 ${wfId} 已删除`, "info");
    if (wfId === state.currentWorkflowId) {
      state.currentWorkflowId = null;
      await loadWorkflowList();
    }
    await refreshProjectListModal();
  } catch (e) {
    alert(`删除失败: ${e.message}`);
  }
}

// 一键清理无分镜空工程
async function cleanEmptyProjects() {
  if (!confirm("确定要一键清理所有分镜数为 0 的废弃与空工程吗？")) return;
  try {
    const res = await api('/workflows/clean_empty', { method: 'POST' });
    alert(res.message || `清理完成！`);
    appendLog(res.message, "info");
    await loadWorkflowList();
    await refreshProjectListModal();
  } catch (e) {
    alert(`清理失败: ${e.message}`);
  }
}

// 重命名工程 Modal
let renamingWorkflowId = null;
function openRenameWorkflowModal(wfId, currentTitle) {
  renamingWorkflowId = wfId || state.currentWorkflowId;
  const modal = document.getElementById('rename-modal-backdrop');
  const input = document.getElementById('rename-input');
  if (!modal || !input) return;
  input.value = currentTitle || state.workflow?.title || '';
  modal.classList.add('active');
  setTimeout(() => input.focus(), 100);
}

function closeRenameModal() {
  const modal = document.getElementById('rename-modal-backdrop');
  if (modal) modal.classList.remove('active');
  renamingWorkflowId = null;
}

async function submitRenameWorkflow() {
  const input = document.getElementById('rename-input');
  if (!input) return;
  const newTitle = input.value.trim();
  if (!newTitle) {
    alert("工程名称不能为空！");
    return;
  }
  const targetId = renamingWorkflowId || state.currentWorkflowId;
  if (!targetId) return;
  try {
    await api(`/workflows/${targetId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle })
    });
    appendLog(`工程重命名为: ${newTitle}`, "info");
    closeRenameModal();
    if (targetId === state.currentWorkflowId) {
      await selectWorkflow(targetId);
    } else {
      await refreshProjectListModal();
    }
  } catch (e) {
    alert(`重命名失败: ${e.message}`);
  }
}

// 删除当前工作流
async function confirmDeleteCurrentWorkflow() {
  if (!state.currentWorkflowId) return;
  if (!confirm(`确定要删除当前工作流工程「${state.workflow?.title || state.currentWorkflowId}」吗？`)) return;
  try {
    await api(`/workflows/${state.currentWorkflowId}`, { method: 'DELETE' });
    appendLog(`工作流已成功删除`, 'info');
    state.currentWorkflowId = null;
    await loadWorkflowList();
  } catch (e) {
    alert(`删除失败: ${e.message}`);
  }
}

// 日志面板切换
function toggleLiveLogExpand() {
  const panel = document.getElementById('live-log-panel-wrap');
  if (!panel) return;
  panel.classList.toggle('visible');
}



// 动态字段更新与模式切换函数
async function updateShotField(shotId, field, value) {
  try {
    const payload = {};
    payload[field] = value;
    await api(`/shots/${shotId}`, {
      method: 'PUT',
      body: payload
    });
    if (state.workflow && state.workflow.shots) {
      const s = state.workflow.shots.find(x => x.id === shotId);
      if (s) {
        s[field] = value;
        if (field === 'engine' || field === 'image_url' || field === 'end_image_url') {
          const card = document.getElementById(`shot-card-${shotId}`);
          if (card) {
            const warnBox = card.querySelector('.vids-engine-warn-pill');
            const curEng = s.engine || state.workflow?.engine || 'vids';
            const shouldWarn = (s.mode === 'first_last_frame' || Boolean(s.end_image_url)) && curEng === 'vids';
            if (warnBox) {
              warnBox.style.display = shouldWarn ? 'flex' : 'none';
            }
          }
        }
      }
    }
  } catch (e) {
    appendLog(`更新分镜字段 [${field}] 失败: ${e.message}`, 'error');
  }
}

async function updateShotMode(shotId, mode) {
  try {
    const payload = { mode: mode };
    if (mode === 'first_last_frame') {
      const s = state.workflow?.shots?.find(x => x.id === shotId);
      if (s && (!s.engine || s.engine === 'vids')) {
        appendLog(`[分镜 #${s.sequence || ''}] 切换为首尾帧过渡模式。提示：Google Vids 原生仅支持首帧微动，建议将途径切换为 ⚡ Flow (Veo 3.1) 实现两端关键帧插值`, 'info');
      }
    }
    await api(`/shots/${shotId}`, {
      method: 'PUT',
      body: payload
    });
    if (state.currentWorkflowId) {
      await selectWorkflow(state.currentWorkflowId);
    }
    appendLog(`分镜模式已更新为: ${getModeLabel(mode)}`, 'success');
  } catch (e) {
    appendLog(`更新分镜模式失败: ${e.message}`, 'error');
  }
}

// 别名与补齐函数 (由次智能体审查指出)
function generateSingleShot(shotId) {
  return runSingleShot(shotId);
}

async function clearShotAsset(shotId, field) {
  if (!state.currentWorkflowId) return;
  try {
    await updateShotField(shotId, field, '');
    appendLog(`已清除分镜素材: ${field}`, "info");
    const wf = await api(`/workflows/${state.currentWorkflowId}`);
    state.workflow = wf;
    renderShots(wf.shots || []);
  } catch (e) {
    appendLog(`清除素材失败: ${e.message}`, "error");
  }
}

function executeBatchJsonImport() {
  return executeBatchImport();
}

function fillSampleJson(mode) {
  const textarea = document.getElementById('json-import-textarea') || document.getElementById('batch-import-textarea');
  if (!textarea) return;
  if (mode === 'first_last_frame') {
    const flowRadio = document.getElementById('import-engine-flow');
    if (flowRadio) flowRadio.checked = true;
  } else {
    const vidsRadio = document.getElementById('import-engine-vids');
    if (vidsRadio) vidsRadio.checked = true;
  }
  let sampleData = [];
  if (mode === 'first_last_frame') {
    sampleData = [
      {
        "name": "镜头01·活磷固定",
        "mode": "first_last_frame",
        "image_url": "E:/BaiduNetdiskDownload/麟活矛_01_start.png",
        "end_image_url": "E:/BaiduNetdiskDownload/麟活矛_01_end.png",
        "prompt": "镜头01: 固定机位缓慢推进悬浮土壤小岛，矿物微粒与金色标记平滑流动，1080p高质量",
        "narration": "偏碱的土壤里，磷容易与钙结合固定。",
        "duration": 8,
        "resolution": "1080p",
        "model_name": "Omni"
      },
      {
        "name": "镜头02·活磷释放",
        "mode": "first_last_frame",
        "image_url": "E:/BaiduNetdiskDownload/麟活矛_02_start.png",
        "end_image_url": "E:/BaiduNetdiskDownload/麟活矛_02_end.png",
        "prompt": "镜头02: 沿同一麦苗与根毛运镜，矿物颗粒逐渐解离释放为游离磷素，平滑过渡",
        "narration": "活磷，就是提高土壤中已有磷的有效性。",
        "duration": 8,
        "resolution": "1080p",
        "model_name": "Omni"
      }
    ];
  } else if (mode === 'image2video') {
    sampleData = [
      {
        "name": "镜头01·幼苗特写",
        "mode": "image2video",
        "image_url": "E:/BaiduNetdiskDownload/sample_plant.png",
        "prompt": "微距摄影，阳光透过温室玻璃照射在深绿麦叶上，露珠晶莹，缓慢运镜",
        "narration": "健康的根际环境是丰收的基石。",
        "duration": 8,
        "resolution": "1080p",
        "model_name": "Omni"
      }
    ];
  } else {
    sampleData = [
      {
        "name": "镜头01·宏观航拍",
        "mode": "text2video",
        "prompt": "Cinematic aerial view of endless golden wheat fields at golden hour, 4k 1080p photorealistic",
        "narration": "广袤的原野见证科技的力量。",
        "duration": 8,
        "resolution": "1080p",
        "model_name": "Omni"
      }
    ];
  }
  textarea.value = JSON.stringify(sampleData, null, 2);
  appendLog('已载入示范 JSON 数据 (' + mode + ')', 'info');
}

// 新建工程 Modal 交互
function showNewWorkflowModal() {
  const modal = document.getElementById('new-wf-modal-backdrop');
  if (!modal) return;
  const titleInput = document.getElementById('new-wf-title');
  if (titleInput) titleInput.value = `我的新工程 · 1080p 连续流水线 (${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })})`;
  modal.classList.add('active');
  if (titleInput) setTimeout(() => titleInput.focus(), 100);
}

function closeNewWorkflowModal() {
  const modal = document.getElementById('new-wf-modal-backdrop');
  if (modal) modal.classList.remove('active');
}

async function submitCreateNewWorkflow() {
  const titleInput = document.getElementById('new-wf-title');
  const aspectSelect = document.getElementById('new-wf-aspect');
  const resSelect = document.getElementById('new-wf-resolution');
  
  const title = (titleInput?.value || '').trim() || '未命名视频工程';
  const aspect = aspectSelect?.value || '16:9';
  const res = resSelect?.value || '1080p';
  const engineSelect = document.getElementById('new-wf-engine');
  const engine = engineSelect?.value || 'vids';
  
  try {
    const newWf = await api('/workflows', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        doc_url: "https://docs.google.com/videos/",
        style_prompt: "Cinematic, photorealistic lighting, ultra-detailed 1080p render",
        aspect_ratio: aspect,
        duration_per_shot: 8,
        resolution: res,
        model_name: "Omni",
        engine: engine
      })
    });
    appendLog(`创建新工作流成功: [${newWf.title}]`, 'info');
    closeNewWorkflowModal();
    await selectWorkflow(newWf.id);
  } catch (e) {
    alert(`创建工程失败: ${e.message}`);
  }
}

// 强行中止镜头与连续生成
async function stopRunningShot(shotId) {
  if (!confirm('确定要强行中止该镜头的渲染任务吗？将立即终止底层执行进程并释放资源。')) return;
  try {
    const res = await api(`/shots/${shotId}/cancel`, { method: 'POST' });
    appendLog(`⏹ ${res.message || '镜头生成任务已强行停止'}`, 'info');
    if (state.currentWorkflowId) {
      await selectWorkflow(state.currentWorkflowId);
    }
  } catch (e) {
    appendLog(`停止镜头失败: ${e.message}`, 'error');
  }
}

async function stopContinuousGeneration() {
  if (!state.currentWorkflowId) return;
  if (!confirm('确定要强行中止当前工程的所有生成任务吗？正在运行与排队中的镜头都将被立即停止。')) return;
  try {
    const res = await api(`/workflows/${state.currentWorkflowId}/stop_all`, { method: 'POST' });
    appendLog(`⏹ ${res.message || '连续生成已成功停止'}`, 'info');
    if (state.currentWorkflowId) {
      await selectWorkflow(state.currentWorkflowId);
    }
  } catch (e) {
    appendLog(`停止连续生成失败: ${e.message}`, 'error');
  }
}
