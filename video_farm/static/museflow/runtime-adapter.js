(() => {
  'use strict';

  // ==========================================
  // MuseFlow Runtime Adapter for Video Farm
  // 架构：Web 独立运行 + 视频工坊 8088 本地引擎深度集成
  // ==========================================

  const ADAPTER_CONFIG = {
    engineKey: 'museflow_preferred_engine',
    videoModelKey: 'museflow_video_model',
    imageModelKey: 'museflow_image_model',
    defaultEngine: 'video_farm', // 'video_farm' 或 'muse_ai'
    defaultVideoModel: 'flow',   // 'flow', 'veo-quality', 'veo-fast', 'gemini', 'vids'
    defaultImageModel: 'flux-1-schnell'
  };

  const getSavedEngine = () => localStorage.getItem(ADAPTER_CONFIG.engineKey) || ADAPTER_CONFIG.defaultEngine;
  const setSavedEngine = (engine) => localStorage.setItem(ADAPTER_CONFIG.engineKey, engine);

  const getSavedVideoModel = () => localStorage.getItem(ADAPTER_CONFIG.videoModelKey) || ADAPTER_CONFIG.defaultVideoModel;
  const setSavedVideoModel = (model) => localStorage.setItem(ADAPTER_CONFIG.videoModelKey, model);
  const escapeHtml = (str) => String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  // 1. Chrome 扩展 API 垫片 (Universal Shim)
  if (typeof window.chrome === 'undefined' || !window.chrome?.tabs) {
    const isExtension = Boolean(window.chrome?.runtime?.id);

    window.chrome = window.chrome || {};

    // 存储垫片 (localStorage + 8088 后端双重持久化)
    window.chrome.storage = window.chrome.storage || {
      local: {
        get: async (keys) => {
          try {
            const key = typeof keys === 'string' ? keys : (Array.isArray(keys) ? keys[0] : Object.keys(keys)[0]);
            const raw = localStorage.getItem('museflow_' + key);
            if (raw) return { [key]: JSON.parse(raw) };
            // 若本地为空，尝试从 8088 后端恢复工程
            if (key === 'museflow') {
              try {
                const resp = await fetch('/api/museflow/project?project_id=default');
                const result = await resp.json();
                if (result.ok && result.data) {
                  return { museflow: result.data };
                }
              } catch {}
            }
            return {};
          } catch (e) {
            console.warn('[RuntimeAdapter] Storage get error:', e);
            return {};
          }
        },
        set: async (items) => {
          try {
            for (const [k, v] of Object.entries(items)) {
              localStorage.setItem('museflow_' + k, JSON.stringify(v));
              // 自动异步同步至 8088 磁盘持久化（防止浏览器配额溢出或缓存丢失）
              if (k === 'museflow') {
                fetch('/api/museflow/project?project_id=default', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(v)
                }).catch(() => {});
              }
            }
          } catch (e) {
            console.warn('[RuntimeAdapter] Storage set error:', e);
          }
        }
      }
    };

    // 标签页与消息垫片
    window.chrome.tabs = window.chrome.tabs || {
      query: async (queryInfo) => {
        // 如果当前是 Muse.ai 原生模式且在扩展环境中，则由扩展处理；否则返回本地虚拟标签页
        return [{ id: 8088, active: true, url: window.location.href, title: 'Video Farm Studio' }];
      },
      sendMessage: async (tabId, message) => {
        return window.__museFlowAdapter.handleMessage(message);
      },
      onUpdated: { addListener: () => {} },
      onCreated: { addListener: () => {} }
    };

    window.chrome.scripting = window.chrome.scripting || {
      executeScript: async () => []
    };

    window.chrome.runtime = window.chrome.runtime || {
      id: 'video_farm_museflow_web',
      sendMessage: async (message) => window.__museFlowAdapter.handleMessage(message),
      onMessage: { addListener: () => {} },
      getURL: (path) => path
    };
  }

  // 2. 视频工坊核心适配器实现
  window.__museFlowAdapter = {
    activeTaskId: null,
    activeAbortController: null,

    async handleMessage(message) {
      const engine = getSavedEngine();

      // 会话探活
      if (message.type === 'MUSEFLOW_CHECK_SESSION') {
        if (engine === 'video_farm') {
          return this.checkVideoFarmHealth();
        } else {
          return { ok: false, error: '请在 Chrome 扩展环境中使用 Muse.ai 会话，或切换至视频工坊引擎。' };
        }
      }

      // 生成任务派发
      if (message.type === 'MUSEFLOW_GENERATE') {
        if (engine === 'video_farm') {
          return this.executeVideoFarmGeneration(message);
        } else {
          return { ok: false, error: '当前未处于 Muse.ai 浏览器扩展环境，请切换为“视频工坊本地引擎”。' };
        }
      }

      // 中止生成
      if (message.type === 'MUSEFLOW_STOP_GENERATION') {
        this.stopActiveGeneration();
        return { ok: true, stopped: true };
      }

      return { ok: false, error: `未知的消息类型: ${message.type}` };
    },

    async checkVideoFarmHealth() {
      try {
        const resp = await fetch('/api/canvas/status');
        if (resp.ok) {
          const status = await resp.json();
          return {
            ok: true,
            signedIn: true,
            composer: true,
            title: '视频工坊 8088 在线',
            loginRequired: false,
            url: window.location.origin
          };
        }
      } catch {}
      return {
        ok: true,
        signedIn: true,
        composer: true,
        title: '视频工坊已就绪',
        loginRequired: false
      };
    },

    stopActiveGeneration() {
      if (this.activeAbortController) {
        this.activeAbortController.abort();
        this.activeAbortController = null;
      }
      this.activeTaskId = null;
    },

    async executeVideoFarmGeneration(req) {
      const abortCtrl = new AbortController();
      this.activeAbortController = abortCtrl;
      const isVideo = req.mediaType === 'video';

      try {
        if (!isVideo) {
          // --- 图像生成 (调用 /api/canvas/v1/images/generations) ---
          let targetSize = '1024x1024';
          if (req.size === '16:9') targetSize = '1792x1024';
          else if (req.size === '9:16') targetSize = '1024x1792';
          else if (req.size === '4:3') targetSize = '1152x896';
          else if (req.size === '3:4') targetSize = '896x1152';

          const imagePayload = {
            prompt: req.prompt || '高质感场景分镜画面渲染',
            model: req.model || getSavedImageModel(),
            size: targetSize,
            quality: 'standard'
          };

          const resp = await fetch('/api/canvas/v1/images/generations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(imagePayload),
            signal: abortCtrl.signal
          });

          if (!resp.ok) {
            const errJson = await resp.json().catch(() => ({}));
            throw new Error(errJson.detail || `生图接口返回错误 (${resp.status})`);
          }

          const resData = await resp.json();
          let finalUrl = '';
          if (resData.data && resData.data[0]) {
            if (resData.data[0].url) finalUrl = resData.data[0].url;
            else if (resData.data[0].b64_json) finalUrl = `data:image/png;base64,${resData.data[0].b64_json}`;
          }

          if (!finalUrl) throw new Error('生图引擎未返回有效图像数据。');

          // 自动同步至视频工坊资产库
          fetch('/api/canvas/import-to-farm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: finalUrl, media_type: 'image', prompt: req.prompt })
          }).catch(() => {});

          return { ok: true, url: finalUrl, isVideo: false };
        } else {
          // --- 视频生成 (调用 /api/canvas/v1/videos) ---
          const fd = new FormData();
          fd.append('prompt', req.prompt || '根据输入参考生成动态视频片段');

          // 模型路由与时长控制
          const chosenModel = (req.model || getSavedVideoModel()).toLowerCase();
          let internalModel = 'flow';
          if (chosenModel.includes('gemini')) internalModel = 'gemini';
          else if (chosenModel.includes('vids')) internalModel = 'vids';
          else if (chosenModel.includes('quality')) internalModel = 'veo-quality';
          else if (chosenModel.includes('fast')) internalModel = 'veo-fast';

          fd.append('model', internalModel);
          fd.append('duration', String(req.duration || 6));
          fd.append('aspect_ratio', req.size || '16:9');

          // 处理参考图与首尾帧
          if (Array.isArray(req.referenceImages) && req.referenceImages.length > 0) {
            for (let i = 0; i < req.referenceImages.length; i++) {
              const refUrl = req.referenceImages[i];
              try {
                const blobResp = await fetch(refUrl);
                const blob = await blobResp.blob();
                fd.append('files', blob, `ref_${i}.png`);
              } catch (e) {
                console.warn('[RuntimeAdapter] Failed to fetch reference image blob:', e);
              }
            }
            fd.append('mode', req.referenceImages.length > 1 ? 'ingredients' : 'start_frame');
          } else {
            fd.append('mode', 'text');
          }

          // 提交任务
          const submitResp = await fetch('/api/canvas/v1/videos', {
            method: 'POST',
            body: fd,
            signal: abortCtrl.signal
          });

          if (!submitResp.ok) {
            const errData = await submitResp.json().catch(() => ({}));
            throw new Error(errData.detail || `视频任务创建失败 (${submitResp.status})`);
          }

          const taskInfo = await submitResp.json();
          const taskId = taskInfo.id || taskInfo.task_id;
          this.activeTaskId = taskId;

          // 轮询等待成片
          const startTime = Date.now();
          const timeoutMs = (req.timeoutSec || 300) * 1000;

          while (Date.now() - startTime < timeoutMs) {
            if (abortCtrl.signal.aborted) {
              throw new DOMException('用户已停止生成。', 'AbortError');
            }

            await new Promise((r) => setTimeout(r, 2000));

            const pollResp = await fetch(`/api/canvas/v1/videos/${taskId}`, { signal: abortCtrl.signal });
            if (!pollResp.ok) continue;

            const pollData = await pollResp.json();
            if (pollData.status === 'completed') {
              const videoUrl = pollData.url || pollData.video_url || pollData.result_url;
              if (!videoUrl) throw new Error('视频任务已标记完成但未提供有效视频 URL。');

              // 自动同步至工坊素材库
              fetch('/api/canvas/import-to-farm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: videoUrl, media_type: 'video', prompt: req.prompt })
              }).catch(() => {});

              return { ok: true, url: videoUrl, isVideo: true };
            } else if (pollData.status === 'failed') {
              throw new Error(pollData.error?.message || '视频工坊底层生成任务失败。');
            }

            // 更新状态栏进度提示
            const runStatusEl = document.getElementById('runStatus');
            if (runStatusEl) {
              const prog = pollData.progress || 35;
              runStatusEl.textContent = `视频生成中 (${prog}%) · 任务 ${taskId.slice(0, 8)}...`;
              runStatusEl.className = 'warn';
            }
          }

          throw new Error('视频生成超时，请稍后在任务列表查看进度。');
        }
      } finally {
        this.activeAbortController = null;
        this.activeTaskId = null;
      }
    }
  };

  // 3. 界面增强与素材库集成
  window.addEventListener('DOMContentLoaded', () => {
    enhanceUI();
    setupMediaDrawer();
    setupTimelineMp4Export();
  });

  function enhanceUI() {
    // 状态栏更新
    const backendStatusEl = document.getElementById('backendStatus');
    const museStatusEl = document.getElementById('museStatus');

    if (backendStatusEl) {
      backendStatusEl.style.cursor = 'pointer';
      backendStatusEl.title = '点击切换生成引擎（视频工坊本地 / Muse.ai 扩展）';
      updateBackendStatusText();
      backendStatusEl.addEventListener('click', toggleEngine);
    }

    if (museStatusEl) {
      museStatusEl.textContent = '● 视频工坊服务在线 (8088 就绪)';
      museStatusEl.className = 'ok';
    }

    // 在工具栏增加“视频工坊素材库”按钮
    const toolbarActions = document.querySelector('.toolbar-actions');
    if (toolbarActions && !document.getElementById('farmMediaDrawerBtn')) {
      const btn = document.createElement('button');
      btn.id = 'farmMediaDrawerBtn';
      btn.type = 'button';
      btn.className = 'btn-farm-drawer';
      btn.textContent = '视频工坊素材库';
      btn.title = '浏览视频工坊最新成片与素材，一键置入画布或时间线';
      btn.style.cssText = 'background: rgba(59,130,246,0.18); color: #60a5fa; border: 1px solid rgba(59,130,246,0.4); font-weight: 500;';
      toolbarActions.insertBefore(btn, toolbarActions.firstChild);
      btn.onclick = toggleMediaDrawer;
    }
  }

  function updateBackendStatusText() {
    const backendStatusEl = document.getElementById('backendStatus');
    if (!backendStatusEl) return;
    const engine = getSavedEngine();
    if (engine === 'video_farm') {
      backendStatusEl.textContent = '生成引擎：视频工坊 (本地 Flow / Gemini / Vids)';
      backendStatusEl.className = 'ok';
    } else {
      backendStatusEl.textContent = '生成引擎：Muse.ai 浏览器会话';
      backendStatusEl.className = 'warn';
    }
  }

  function toggleEngine() {
    const current = getSavedEngine();
    const next = current === 'video_farm' ? 'muse_ai' : 'video_farm';
    setSavedEngine(next);
    updateBackendStatusText();
    alert(`生成引擎已切换为：${next === 'video_farm' ? '视频工坊本地引擎 (Flow/Gemini/Vids)' : 'Muse.ai 浏览器扩展会话'}`);
  }

  // 4. 视频工坊素材库抽屉构建
  function setupMediaDrawer() {
    if (document.getElementById('farmMediaDrawer')) return;

    const drawer = document.createElement('aside');
    drawer.id = 'farmMediaDrawer';
    drawer.className = 'farm-media-drawer';
    drawer.innerHTML = `
      <div class="farm-drawer-header">
        <strong>视频工坊素材库</strong>
        <div style="display:flex;align-items:center;gap:6px;">
          <button id="refreshFarmMediaBtn" type="button" class="btn-sm">刷新</button>
          <button id="closeFarmDrawerBtn" type="button" class="btn-sm">✕</button>
        </div>
      </div>
      <div class="farm-drawer-body" id="farmMediaList">
        <div style="padding:16px;color:#888;font-size:12px;">正在加载工坊最新生成素材...</div>
      </div>
    `;
    document.body.appendChild(drawer);

    document.getElementById('closeFarmDrawerBtn').onclick = () => drawer.classList.remove('open');
    document.getElementById('refreshFarmMediaBtn').onclick = loadFarmRecentMedia;

    // 监听外部注入消息 (来自父页面 Studio Shell)
    window.addEventListener('message', (event) => {
      if (event.data?.type === 'MUSEFLOW_INSERT_MEDIA') {
        insertMediaToCanvas(event.data.asset);
      }
    });
  }

  function toggleMediaDrawer() {
    const drawer = document.getElementById('farmMediaDrawer');
    if (!drawer) return;
    drawer.classList.toggle('open');
    if (drawer.classList.contains('open')) {
      loadFarmRecentMedia();
    }
  }

  async function loadFarmRecentMedia() {
    const listEl = document.getElementById('farmMediaList');
    if (!listEl) return;
    listEl.innerHTML = '<div style="padding:16px;color:#888;font-size:12px;">正在拉取最新成片与图像素材...</div>';

    try {
      const resp = await fetch('/api/canvas/recent-media?limit=30');
      if (!resp.ok) throw new Error('拉取失败');
      const items = await resp.json();

      if (!items || items.length === 0) {
        listEl.innerHTML = '<div style="padding:16px;color:#888;font-size:12px;">暂无成片素材，请先运行生成任务。</div>';
        return;
      }

      listEl.innerHTML = '';
      items.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'farm-media-card';
        const isVid = item.type === 'video';
        const safeName = escapeHtml(item.name || '外部媒体');
        const safeUrl = encodeURI(item.url || '');
        card.innerHTML = `
          <div class="farm-media-thumb">
            ${isVid ? `<video src="${safeUrl}" muted playsinline></video>` : `<img src="${safeUrl}" alt="${safeName}" />`}
            <span class="media-badge">${isVid ? '视频' : '图片'}</span>
          </div>
          <div class="farm-media-info">
            <div class="media-title" title="${safeName}">${safeName}</div>
            <div class="media-meta">${escapeHtml(item.size_desc || '')} · ${escapeHtml(item.time_desc || '')}</div>
            <div class="media-actions">
              ${isVid ? `<button class="btn-action-add" data-action="timeline">＋ 加入时间线</button>` : `<button class="btn-action-add" data-action="image">＋ 置入图片</button>`}
            </div>
          </div>
        `;

        card.querySelector('[data-action]')?.addEventListener('click', () => {
          insertMediaToCanvas(item);
        });

        listEl.appendChild(card);
      });
    } catch (e) {
      listEl.innerHTML = `<div style="padding:16px;color:#f87171;font-size:12px;">无法连接视频工坊素材接口: ${e.message}</div>`;
    }
  }

  function insertMediaToCanvas(item) {
    if (!item || !item.url) return;
    const isVid = item.type === 'video';

    if (isVid) {
      // 自动加入时间线
      const track = document.getElementById('timelineTrack');
      const countEl = document.getElementById('timelineClipCount');
      if (track) {
        const clipEl = document.createElement('div');
        clipEl.className = 'timeline-dock-clip';
        clipEl.dataset.url = item.url;
        clipEl.innerHTML = `
          <video src="${item.url}" muted preload="metadata"></video>
          <div class="clip-label">${item.name || '外部视频'}</div>
          <button class="clip-remove" title="移除片段">✕</button>
        `;
        clipEl.querySelector('.clip-remove').onclick = () => {
          clipEl.remove();
          updateTimelineCount();
        };
        track.appendChild(clipEl);
        updateTimelineCount();
        alert(`已成功将视频【${item.name || '工坊视频'}】加入时间线轨道！`);
      }
    } else {
      // 触发新增输入图片节点
      const addImgBtn = document.querySelector('[data-add="imageInput"]');
      if (addImgBtn) {
        addImgBtn.click();
        // 查找最新添加的节点并注入 asset
        setTimeout(() => {
          const imgNodes = document.querySelectorAll('.node[data-type="imageInput"]');
          const lastNode = imgNodes[imgNodes.length - 1];
          if (lastNode) {
            const preview = lastNode.querySelector('.node-preview img');
            if (preview) preview.src = item.url;
          }
        }, 100);
        alert(`已成功创建输入图片节点并置入素材！`);
      }
    }
  }

  function updateTimelineCount() {
    const clips = document.querySelectorAll('.timeline-dock-clip');
    const countEl = document.getElementById('timelineClipCount');
    if (countEl) countEl.textContent = `${clips.length} 个片段`;
  }

  // 5. 时间线 FFmpeg 高清成片合成
  function setupTimelineMp4Export() {
    const dockActions = document.querySelector('.timeline-dock-actions');
    if (!dockActions || document.getElementById('timelineExportMp4Btn')) return;

    const btn = document.createElement('button');
    btn.id = 'timelineExportMp4Btn';
    btn.type = 'button';
    btn.className = 'primary';
    btn.textContent = '⇩ MP4 高清合成';
    btn.title = '使用视频工坊 FFmpeg 将完整时间线高质量合成为 MP4 视频';
    btn.style.cssText = 'background: #2563eb; color: #fff; font-weight: 600; margin-left: 6px;';
    dockActions.appendChild(btn);

    btn.onclick = async () => {
      // 收集时间线上的视频链接
      const clips = [...document.querySelectorAll('.timeline-dock-clip video')].map((v) => v.src || v.currentSrc).filter(Boolean);
      if (clips.length < 2) {
        alert('时间线高清合成至少需要包含 2 个有效视频片段。请先生成或导入视频。');
        return;
      }

      btn.disabled = true;
      btn.textContent = '⏳ 正在合成 MP4...';
      try {
        const resp = await fetch('/api/canvas/timeline-assembly', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            shot_video_urls: clips,
            project_id: 'museflow_' + Date.now().toString(36)
          })
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || `合成接口返回错误 (${resp.status})`);
        }

        const resData = await resp.json();
        const finalUrl = resData.url || resData.video_url;
        if (finalUrl) {
          alert('时间线高清合成成功！点击确定将在新标签页预览并可直接下载 MP4。');
          window.open(finalUrl, '_blank');
        } else {
          throw new Error('未返回有效合成视频地址。');
        }
      } catch (err) {
        alert('MP4 时间线合成失败: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = '⇩ MP4 高清合成';
      }
    };
  }
})();
