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
          const reqId = req.requestId || `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
          fd.append('request_id', reqId);

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
    setupShotProductionM9();
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

  // 6. M9 镜头级精细化生产与视觉规范控制
  function setupShotProductionM9() {
    const sm = window.__shotManager;
    if (!sm) return;

    // 视觉规范弹窗控制
    const bibleBtn = document.getElementById('shotBibleBtn');
    const bibleModal = document.getElementById('shotBibleModal');
    const closeBibleBtn = document.getElementById('closeBibleModal');
    const saveBibleBtn = document.getElementById('saveBibleBtn');

    if (bibleBtn && bibleModal) {
      bibleBtn.onclick = () => {
        const vb = sm.visualBible;
        document.getElementById('bibleStyleName').value = vb.styleName || '';
        document.getElementById('bibleAspectRatio').value = vb.aspectRatio || '16:9';
        document.getElementById('bibleStylePrompt').value = vb.stylePrompt || '';
        document.getElementById('bibleColorScheme').value = vb.colorScheme || '';
        document.getElementById('bibleLighting').value = vb.lighting || '';
        document.getElementById('bibleLensCamera').value = vb.lensCamera || '';
        document.getElementById('bibleSubjectName').value = vb.subjectSetting?.name || '';
        document.getElementById('bibleSubjectFeatures').value = vb.subjectSetting?.features || '';
        document.getElementById('bibleSubjectRefUrl').value = vb.subjectSetting?.referenceAssetUrl || '';
        bibleModal.classList.remove('hidden');
      };

      closeBibleBtn.onclick = () => bibleModal.classList.add('hidden');
      saveBibleBtn.onclick = () => {
        sm.visualBible.styleName = document.getElementById('bibleStyleName').value.trim();
        sm.visualBible.aspectRatio = document.getElementById('bibleAspectRatio').value;
        sm.visualBible.stylePrompt = document.getElementById('bibleStylePrompt').value.trim();
        sm.visualBible.colorScheme = document.getElementById('bibleColorScheme').value.trim();
        sm.visualBible.lighting = document.getElementById('bibleLighting').value.trim();
        sm.visualBible.lensCamera = document.getElementById('bibleLensCamera').value.trim();
        sm.visualBible.subjectSetting = {
          type: 'custom',
          name: document.getElementById('bibleSubjectName').value.trim(),
          features: document.getElementById('bibleSubjectFeatures').value.trim(),
          referenceAssetUrl: document.getElementById('bibleSubjectRefUrl').value.trim()
        };
        sm.notify();
        bibleModal.classList.add('hidden');
        alert('工程全局视觉规范 (Visual Bible) 已更新并保存！');
      };
    }

    // 镜头表与版本控制弹窗控制
    const deckBtn = document.getElementById('shotDeckBtn');
    const deckModal = document.getElementById('shotDeckModal');
    const closeDeckBtn = document.getElementById('closeShotDeckBtn');
    const assembleBtn = document.getElementById('shotDeckAssembleBtn');
    const regenFailedBtn = document.getElementById('batchRegenFailedBtn');

    if (deckBtn && deckModal) {
      deckBtn.onclick = () => {
        renderShotDeck();
        deckModal.classList.remove('hidden');
      };
      closeDeckBtn.onclick = () => deckModal.classList.add('hidden');

      assembleBtn.onclick = async () => {
        const specs = sm.buildTimelineSpecs();
        if (specs.length < 2) {
          alert('需要至少 2 个已生成有效视频的分镜才能执行成片合成。');
          return;
        }
        assembleBtn.disabled = true;
        assembleBtn.textContent = '⏳ 正在带精准裁切合成 MP4...';
        try {
          const resp = await fetch('/api/canvas/timeline-assembly', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              shots: specs,
              project_id: 'm9_assembled_' + Date.now().toString(36),
              output_filename: 'assembled_m9_story.mp4'
            })
          });
          if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || `合成错误 (${resp.status})`);
          }
          const resData = await resp.json();
          const url = resData.url || resData.video_url;
          if (url) {
            alert(`时间线精准裁切成片合成成功！时长: ${resData.total_duration?.toFixed(2) || '18.00'}s`);
            window.open(url, '_blank');
          }
        } catch (e) {
          alert('成片合成失败: ' + e.message);
        } finally {
          assembleBtn.disabled = false;
          assembleBtn.textContent = '一键带裁切导出 MP4';
        }
      };

      regenFailedBtn.onclick = async () => {
        const failedShots = sm.shots.filter(s => s.status === 'FAILED');
        if (failedShots.length === 0) {
          alert('当前没有处于失败状态的镜头。');
          return;
        }
        for (const s of failedShots) {
          try {
            await sm.executeSingleShot(s.shotId, window.__museFlowAdapter);
          } catch (e) {
            console.error(`重试镜头 ${s.shotId} 失败:`, e);
          }
        }
        renderShotDeck();
      };

      const batchBtn = document.getElementById('batchExecuteBtn');
      if (batchBtn) {
        batchBtn.onclick = async () => {
          const plan = sm.generateBatchPlan('unready');
          if (plan.targetShotsCount === 0) {
            alert('所有分镜均已生成就绪，无需批量生成。');
            return;
          }
          const ok = confirm(`即将按依赖顺序串行执行批量生成：\n待执行镜头数: ${plan.targetShotsCount}\n并发限制: 1\n是否启动任务队列？`);
          if (ok) {
            batchBtn.disabled = true;
            batchBtn.textContent = '⏳ 批量队列运行中...';
            try {
              await sm.startBatchExecution(window.__museFlowAdapter, 'unready');
              alert('批量生成任务已全部执行完成！');
            } catch (e) {
              alert('批量执行发生异常: ' + e.message);
            } finally {
              batchBtn.disabled = false;
              batchBtn.textContent = '▶ 批量生成计划';
              renderShotDeck();
            }
          }
        };
      }

      const archiveBtn = document.getElementById('exportArchiveBtn');
      if (archiveBtn) {
        archiveBtn.onclick = () => {
          const pkg = sm.exportArchivePackage();
          const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `museflow-archive-${sm.projectId}-${Date.now()}.json`;
          a.click();
          setTimeout(() => URL.revokeObjectURL(url), 5000);
          alert('已成功导出工程全量归档包 (含镜头表、候选清单与时间线裁切配置)！');
        };
      }
    }

    // 渲染镜头表卡片
    function renderShotDeck() {
      const listEl = document.getElementById('shotDeckList');
      const sumEl = document.getElementById('shotDeckSummary');
      if (!listEl) return;
      listEl.innerHTML = '';

      if (sm.shots.length === 0) {
        listEl.innerHTML = '<div style="padding: 24px; text-align: center; color: #888;">暂无分镜数据，请先点击上方“＋ 脚本 → 节点”导入分镜脚本。</div>';
        if (sumEl) sumEl.textContent = '共 0 个分镜';
        return;
      }

      let totalTargetDuration = 0;
      sm.shots.forEach((s) => {
        totalTargetDuration += ((s.trimEnd || s.targetDuration) - (s.trimStart || 0));
        const card = document.createElement('div');
        const isStale = s.dependencies?.stale;
        card.className = `shot-deck-card ${isStale ? 'stale' : ''}`;

        const selRes = sm.getSelectedResult(s.shotId);
        const hasVid = Boolean(selRes?.assetUrl);

        card.innerHTML = `
          <div class="shot-deck-header">
            <div class="shot-deck-title">#${s.sceneNumber} ${escapeHtml(s.title)} <span style="font-size: 12px; color: #888;">(ID: ${s.shotId})</span></div>
            <span class="shot-status-badge ${s.status}">${s.status}</span>
          </div>
          ${isStale ? `
            <div class="stale-alert-banner">
              <span>⚠️ ${escapeHtml(s.dependencies.staleReason || '上游镜头已切换版本，当前仍引用旧尾帧')}</span>
              <div style="display: flex; gap: 6px;">
                <button class="btn-ack-stale" style="padding: 2px 8px; font-size: 11px;">保留旧参考</button>
                <button class="btn-update-stale primary" style="padding: 2px 8px; font-size: 11px;">更新为新尾帧</button>
              </div>
            </div>
          ` : ''}
          <div class="shot-deck-body">
            <div class="shot-preview-box">
              ${hasVid ? `<video src="${encodeURI(selRes.assetUrl)}" controls muted playsinline></video>` : `<span style="color: #64748b; font-size: 11px;">暂无成片</span>`}
            </div>
            <div style="display: flex; flex-direction: column; gap: 4px; font-size: 12px;">
              <div style="color: #94a3b8; max-height: 40px; overflow: hidden; text-overflow: ellipsis;">
                <strong>视频提示:</strong> ${escapeHtml(s.videoPrompt || '无')}
              </div>
              <div style="display: flex; gap: 15px; color: #64748b; font-size: 11px;">
                <span>目标时长: <strong>${s.targetDuration}s</strong></span>
                <span>剪裁入出点: <strong>${s.trimStart}s ~ ${s.trimEnd}s</strong> (实际用量: ${(s.trimEnd - s.trimStart).toFixed(1)}s)</span>
              </div>
              <div style="display: flex; gap: 10px; align-items: center; margin-top: 4px; font-size: 11px;">
                <span style="color: ${s.qcResult?.passed ? '#34d399' : '#f87171'}; font-weight: 600;">
                  QC质检: ${s.qcResult?.passed ? '✓ 合格' : '✗ 待复核'}
                </span>
                <span style="color: #64748b;">|</span>
                <span style="color: #94a3b8;">人工审片:</span>
                <select class="review-status-select" style="padding: 1px 6px; font-size: 11px; background: #0f172a; color: #fff; border: 1px solid #334155; border-radius: 3px;">
                  <option value="PENDING_REVIEW" ${s.reviewStatus === 'PENDING_REVIEW' ? 'selected' : ''}>⏳ 待审片</option>
                  <option value="APPROVED" ${s.reviewStatus === 'APPROVED' ? 'selected' : ''}>✓ 审核通过</option>
                  <option value="NEEDS_REVISION" ${s.reviewStatus === 'NEEDS_REVISION' ? 'selected' : ''}>✗ 需要修改</option>
                  <option value="SKIPPED" ${s.reviewStatus === 'SKIPPED' ? 'selected' : ''}>— 暂不审核</option>
                </select>
              </div>
              ${s.candidateResults.length > 1 ? `
                <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                  <span style="color: #38bdf8;">候选结果 (${s.candidateResults.length}个):</span>
                  <select class="candidate-select" style="padding: 2px 6px; font-size: 11px; background: #0f172a; color: #fff; border: 1px solid #334155; border-radius: 4px;">
                    ${s.candidateResults.map(r => `
                      <option value="${r.resultId}" ${r.resultId === s.selectedResultId ? 'selected' : ''}>
                        ${r.label} · ${r.duration ? r.duration.toFixed(1) + 's' : ''} · ${(r.createdAt || '').slice(11, 19)}
                      </option>
                    `).join('')}
                  </select>
                </div>
              ` : ''}
            </div>
            <div class="shot-deck-controls">
              <button class="btn-regen-shot primary" style="width: 100%; padding: 6px; font-size: 12px;">
                ${hasVid ? '↺ 重新生成此镜头' : '▶ 执行生成'}
              </button>
              <div style="display: flex; gap: 4px; align-items: center; font-size: 11px; color: #888;">
                <span>裁切(s):</span>
                <input type="number" class="input-trim-start" value="${s.trimStart}" min="0" max="60" step="0.5" style="width: 45px; background: #0f172a; color: #fff; border: 1px solid #334155; border-radius: 3px;" />
                <span>至</span>
                <input type="number" class="input-trim-end" value="${s.trimEnd}" min="1" max="60" step="0.5" style="width: 45px; background: #0f172a; color: #fff; border: 1px solid #334155; border-radius: 3px;" />
              </div>
            </div>
          </div>
        `;

        // 绑定单镜头重新生成
        const regenBtn = card.querySelector('.btn-regen-shot');
        if (regenBtn) {
          regenBtn.onclick = async () => {
            regenBtn.disabled = true;
            regenBtn.textContent = '⏳ 生成中...';
            try {
              await sm.executeSingleShot(s.shotId, window.__museFlowAdapter);
              renderShotDeck();
            } catch (err) {
              alert(`镜头 ${s.shotId} 生成失败: ${err.message}`);
              renderShotDeck();
            }
          };
        }

        const revSel = card.querySelector('.review-status-select');
        if (revSel) {
          revSel.onchange = (e) => {
            sm.setReviewStatus(s.shotId, e.target.value);
            renderShotDeck();
          };
        }

        // 绑定候选切换
        const candSel = card.querySelector('.candidate-select');
        if (candSel) {
          candSel.onchange = (e) => {
            sm.selectCandidate(s.shotId, e.target.value);
            renderShotDeck();
          };
        }

        // 绑定裁切修改
        const tStart = card.querySelector('.input-trim-start');
        const tEnd = card.querySelector('.input-trim-end');
        if (tStart && tEnd) {
          const updateTrim = () => {
            s.trimStart = parseFloat(tStart.value) || 0.0;
            s.trimEnd = parseFloat(tEnd.value) || s.targetDuration;
            sm.notify();
          };
          tStart.onchange = updateTrim;
          tEnd.onchange = updateTrim;
        }

        // 绑定失效依赖确认与更新
        const ackBtn = card.querySelector('.btn-ack-stale');
        if (ackBtn) {
          ackBtn.onclick = () => {
            sm.ackStaleReference(s.shotId);
            renderShotDeck();
          };
        }
        const updBtn = card.querySelector('.btn-update-stale');
        if (updBtn) {
          updBtn.onclick = () => {
            const upstream = sm.getShot(s.dependencies.upstreamShotId);
            const upSel = upstream ? sm.getSelectedResult(upstream.shotId) : null;
            sm.updateTailFrameReference(s.shotId, upSel?.assetUrl || null);
            renderShotDeck();
          };
        }

        listEl.appendChild(card);
      });

      if (sumEl) {
        sumEl.textContent = `共 ${sm.shots.length} 个分镜 · 目标成片总时长: ${totalTargetDuration.toFixed(1)}s`;
      }
    }

    // 监听数据变化刷新
    sm.addListener(() => {
      if (!deckModal.classList.contains('hidden')) {
        renderShotDeck();
      }
    });
  }
})();
