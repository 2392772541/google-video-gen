(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const canvas = $('#canvas');
  const edgesSvg = $('#edges');
  const runStatus = $('#runStatus');
  const backendStatus = $('#backendStatus');
  const museStatus = $('#museStatus');
  const isLocalServer = typeof location !== 'undefined' && location.protocol.startsWith('http');

  // 全局独立设置持久化（与工作流文件解耦，多重兜底保护 API Key 与 Endpoint 绝不丢失）
  const SETTINGS_STORAGE_KEY = 'museflow_global_settings';
  const DEFAULT_GLOBAL_SETTINGS = {
    imageProvider: 'local',
    localApiEndpoint: 'http://100.68.145.63:8317/v1',
    localApiKey: 'sk-local-23fa8d80e597d0c0d90c2e75d1c1430787ed13afe1175d70',
    orchestrationModel: 'grok-4.7',
    localImageConcurrency: 2,
    defaultImageModel: 'flux-1-dev',
    customImageModels: ['grok-4.7', 'claude-opus-5-5-high', 'gemini-3.8-flash-high', 'flux-1-dev']
  };

  async function loadGlobalSettings() {
    let saved = null;
    try {
      const res = await chrome?.storage?.local?.get(SETTINGS_STORAGE_KEY);
      if (res && res[SETTINGS_STORAGE_KEY] && typeof res[SETTINGS_STORAGE_KEY] === 'object') {
        saved = res[SETTINGS_STORAGE_KEY];
      }
    } catch {}
    if (!saved) {
      try {
        const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
        if (raw) saved = JSON.parse(raw);
      } catch {}
    }
    return { ...DEFAULT_GLOBAL_SETTINGS, ...(saved || {}) };
  }

  async function persistGlobalSettings(newSettings) {
    if (!newSettings || typeof newSettings !== 'object') return;
    state.settings = { ...DEFAULT_GLOBAL_SETTINGS, ...state.settings, ...newSettings };
    try {
      await chrome?.storage?.local?.set({ [SETTINGS_STORAGE_KEY]: state.settings });
    } catch {}
    try {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(state.settings));
    } catch {}
  }

  const state = {
    nodes: [],
    edges: [],
    selectedNodeId: null,
    selectedNodeIds: [],
    selectedEdgeIds: [],
    selectionMarquee: null,
    connectingFrom: null,
    settings: {},
    isRunning: false,
    activeGenerationId: null,
    generationAbortController: null,
    generationRequestId: null,
    timelinePreviewToken: 0,
    timelinePreviewTimer: 0,
    timelineExporting: false,
    timelineExportUrl: '',
    edgeFrame: 0,
    draggingWire: null,
    wireMoved: false,
    wireOrigin: null,
    pendingConnection: null,
    pointerId: null,
    zoom: 1,
    panX: 0,
    panY: 0,
    handMode: false,
    spaceDown: false,
    panning: null,
    suppressPortClick: false,
    contextPoint: {x:120,y:100}
  };

  const nodeDefs = {
    prompt: { title: "提示词", outputs: [{ id: 'text', label: "文本", type: 'text' }] },
    negativePrompt: { title: "反向提示词", outputs: [{ id: 'text', label: "反向提示词", type: 'negative' }] },
    textAppend: { title: "追加文本", inputs: [{ id: 'text', label: "文本", type: 'text' }], outputs: [{ id: 'text', label: "文本", type: 'text' }] },
    textConcat: { title: "合并文本", inputs: [{ id: 'a', label: "文本 A", type: 'text' }, { id: 'b', label: "文本 B", type: 'text' }], outputs: [{ id: 'text', label: "文本", type: 'text' }] },
    imageInput: { title: "输入图片", outputs: [{ id: 'image', label: "图片", type: 'image' }] },
    references: { title: "参考图片", inputs: Array.from({length:9},(_,i)=>({id:`reference${i+1}`,label:`图片 ${i+1}`,type:'image'})), outputs: [{id:'image',label:'图片集',type:'image'}] },
    generateImage: {
      title: "生成图片",
      inputs: [{ id: 'prompt', label: "提示词", type: 'text' }, { id: 'negative', label: "反向提示词", type: 'negative' }, { id: 'reference', label: "参考图片", type: 'image' }],
      outputs: [{ id: 'image', label: "图片", type: 'image' }]
    },
    generateVideo: {
      title: "生成视频",
      inputs: [{ id: 'prompt', label: "提示词", type: 'text' }, { id: 'negative', label: "反向提示词", type: 'negative' }, { id: 'reference', label: "参考图片", type: 'image' }],
      outputs: [{ id: 'video', label: "视频", type: 'video' }, { id: 'endFrame', label: "尾帧", type: 'image' }]
    },
    timeline: { title: "时间线", inputs: Array.from({length:6},(_,i)=>({id:`clip${i+1}`,label:`片段 ${i+1}`,type:'video'})), outputs: [] },
    imageResize: { title: "调整图片尺寸", inputs: [{ id: 'image', label: "图片", type: 'image' }], outputs: [{ id: 'image', label: "图片", type: 'image' }] },
    preview: { title: "预览", inputs: [{ id: 'media', label: "媒体", type: 'media' }] }
  };

  const statusLabels={idle:'待运行',pending:'等待执行',running:'生成中',success:'已完成',failed:'生成失败',error:'生成失败',skipped:'已跳过',blocked:'缺少依赖',stopped:'已停止',waiting:'等待中',submission_unknown:'提交结果未知（已暂停）'};
  const mediaLabels={image:'图片',video:'视频',text:'文本',negative:'反向提示词',media:'媒体'};
  function statusText(value){return statusLabels[value]||value||statusLabels.idle;}
  function mediaText(value){return mediaLabels[value]||value;}

  const BUILTIN_IMAGE_MODELS = [
    { id: 'muse-image', name: 'Muse.ai (默认)' },
    { id: 'flux-1-schnell', name: 'FLUX.1 Schnell' },
    { id: 'flux-1-dev', name: 'FLUX.1 Dev' },
    { id: 'dall-e-3', name: 'DALL·E 3' },
    { id: 'sd-xl', name: 'Stable Diffusion XL' },
    { id: 'midjourney', name: 'Midjourney' }
  ];

  function getAvailableImageModels() {
    const list = [...BUILTIN_IMAGE_MODELS];
    const custom = Array.isArray(state.settings?.customImageModels) ? state.settings.customImageModels : [];
    custom.forEach(item => {
      if (typeof item === 'string' && item.trim() && !list.some(m => m.id === item.trim())) {
        list.push({ id: item.trim(), name: `${item.trim()} (本地/自定义)` });
      }
    });
    return list;
  }

  function addCustomImageModel(name) {
    if (!name || typeof name !== 'string') return;
    const clean = name.trim();
    if (!clean) return;
    state.settings = state.settings || {};
    state.settings.customImageModels = Array.isArray(state.settings.customImageModels) ? state.settings.customImageModels : [];
    if (!state.settings.customImageModels.includes(clean)) {
      state.settings.customImageModels.push(clean);
      scheduleAutoSave();
    }
  }

  function removeCustomImageModel(name) {
    if (!name || !state.settings?.customImageModels) return;
    state.settings.customImageModels = state.settings.customImageModels.filter(m => m !== name);
    if (state.settings.defaultImageModel === name) {
      state.settings.defaultImageModel = state.settings.customImageModels[0] || 'flux-1-dev';
    }
    scheduleAutoSave();
  }

  function ratioToPixelSize(size) {
    const [w, h] = String(size || '1:1').split(':').map(Number);
    if (w === 16 && h === 9) return { width: 1280, height: 720, str: '1280x720' };
    if (w === 9 && h === 16) return { width: 720, height: 1280, str: '720x1280' };
    if (w === 4 && h === 3) return { width: 1024, height: 768, str: '1024x768' };
    if (w === 3 && h === 4) return { width: 768, height: 1024, str: '768x1024' };
    return { width: 1024, height: 1024, str: '1024x1024' };
  }

  async function safeLocalFetch(url, options = {}) {
    if (typeof chrome !== 'undefined' && chrome?.runtime?.sendMessage) {
      let keepAliveTimer = null;
      let keepAlivePort = null;
      try {
        if (chrome?.runtime?.connect) {
          try {
            keepAlivePort = chrome.runtime.connect({ name: 'museflow-keepalive' });
            keepAliveTimer = setInterval(() => {
              try { keepAlivePort?.postMessage('ping'); } catch {}
            }, 10000);
          } catch {}
        }
        const bgRes = await new Promise(resolve => {
          chrome.runtime.sendMessage({ type: 'MUSEFLOW_PROXY_FETCH', url, options }, res => {
            if (chrome.runtime.lastError || !res) resolve(null);
            else resolve(res);
          });
        });
        if (bgRes) {
          if (!bgRes.ok) {
            const detail = bgRes.error || (bgRes.data ? JSON.stringify(bgRes.data) : bgRes.text) || `HTTP ${bgRes.status}`;
            throw new Error(detail);
          }
          return bgRes.data !== undefined ? bgRes.data : bgRes.text;
        }
      } catch (bgErr) {
        if (!/failed to fetch|connection refused|cors/i.test(bgErr.message)) throw bgErr;
      } finally {
        if (keepAliveTimer) clearInterval(keepAliveTimer);
        try { keepAlivePort?.disconnect(); } catch {}
      }
    }
    const response = await fetch(url, options);
    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      throw new Error(`HTTP ${response.status}: ${errText.slice(0, 300)}`);
    }
    const ct = response.headers.get('content-type') || '';
    return ct.includes('application/json') ? response.json() : response.text();
  }

  async function generateImageLocally(node, { prompt, negativePrompt, referenceImages = [], signal }) {
    const endpoint = (state.settings?.localApiEndpoint || 'http://127.0.0.1:8000/v1').replace(/\/+$/, '');
    const apiKey = state.settings?.localApiKey || '';
    const model = node.data.model || state.settings?.defaultImageModel || 'flux-1-dev';
    const dims = ratioToPixelSize(node.data.size);
    const count = Math.max(1, Math.min(4, Number(node.data.count) || 1));
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;

    const refList = Array.isArray(referenceImages) ? referenceImages : [];
    const refUrls = refList.map(r => typeof r === 'string' ? r : r.url).filter(Boolean);
    const primaryRef = refUrls[0] || '';

    // 1. SD WebUI 专用接口分支 (7860 / sdapi)
    if (endpoint.includes('7860') || endpoint.includes('sdapi')) {
      const isImg2Img = Boolean(primaryRef);
      const subPath = isImg2Img ? '/sdapi/v1/img2img' : '/sdapi/v1/txt2img';
      const webuiUrl = `${endpoint.replace(/\/v1$/, '')}${subPath}`;
      const payload = {
        prompt,
        negative_prompt: negativePrompt || '',
        width: dims.width,
        height: dims.height,
        batch_size: count,
        steps: 25
      };
      if (isImg2Img) {
        payload.init_images = [primaryRef.replace(/^data:image\/[a-zA-Z]+;base64,/, '')];
        payload.denoising_strength = 0.65;
      }
      try {
        const data = await safeLocalFetch(webuiUrl, { method: 'POST', headers, body: JSON.stringify(payload) });
        const images = data?.images || [];
        if (images.length > 0) {
          const results = images.map(b64 => b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`);
          return results.length === 1 ? results[0] : results;
        }
      } catch {}
    }

    // 2. Ollama 接口分支 (11434 / api)
    if (endpoint.includes('11434') || endpoint.includes('/api/')) {
      try {
        const ollamaUrl = `${endpoint.replace(/\/v1$/, '')}/api/generate`;
        const data = await safeLocalFetch(ollamaUrl, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            model,
            prompt,
            stream: false,
            images: primaryRef ? [primaryRef.replace(/^data:image\/[a-zA-Z]+;base64,/, '')] : undefined
          })
        });
        if (data?.response && (data.response.startsWith('data:') || data.response.length > 500)) {
          return data.response.startsWith('data:') ? data.response : `data:image/png;base64,${data.response}`;
        }
      } catch {}
    }

    // 3. 通用 OpenAI 兼容生图接口 (/v1/images/generations)
    let imagesUrl = endpoint;
    if (!imagesUrl.endsWith('/images/generations')) {
      imagesUrl = imagesUrl.endsWith('/v1') ? `${imagesUrl}/images/generations` : `${imagesUrl}/v1/images/generations`;
    }
    const reqPayload = {
      prompt,
      model,
      n: count,
      size: dims.str,
      response_format: 'b64_json'
    };
    if (refUrls.length > 0) {
      reqPayload.reference_images = refUrls;
      reqPayload.extra_body = { reference_images: refUrls, style_reference: primaryRef };
    }
    let data;
    try {
      data = await safeLocalFetch(imagesUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(reqPayload)
      });
    } catch (networkErr) {
      try {
        const fallbackUrl = `${endpoint.replace(/\/v1$/, '')}/sdapi/v1/txt2img`;
        const fbData = await safeLocalFetch(fallbackUrl, {
          method: 'POST',
          headers,
          body: JSON.stringify({ prompt, negative_prompt: negativePrompt || '', width: dims.width, height: dims.height, batch_size: count })
        });
        if (fbData?.images?.length) {
          const results = fbData.images.map(b64 => b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`);
          return results.length === 1 ? results[0] : results;
        }
      } catch {}
      throw new Error(`无法连接到本地生图 API (${endpoint})。请确保本地服务已启动：${networkErr.message}`);
    }

    const rawItems = Array.isArray(data?.data) ? data.data : Array.isArray(data?.images) ? data.images : (data?.data || data?.images ? [data.data || data.images] : []);
    if (!rawItems.length) throw new Error("本地生图 API 未返回有效图片数据。");
    const parsedUrls = [];
    for (const item of rawItems) {
      if (!item) continue;
      if (typeof item === 'string') parsedUrls.push(item.startsWith('data:') ? item : `data:image/png;base64,${item}`);
      else if (item.b64_json) parsedUrls.push(`data:image/png;base64,${item.b64_json}`);
      else if (item.url) parsedUrls.push(item.url);
    }
    if (!parsedUrls.length) throw new Error("本地 API 返回格式无法解析（未找到 b64_json 或 url 字段）。");
    return parsedUrls.length === 1 ? parsedUrls[0] : parsedUrls;
  }

  async function testAndFetchLocalModels() {
    const statusEl = $('#localApiStatus');
    const endpoint = ($('#localApiEndpointInput')?.value?.trim() || state.settings?.localApiEndpoint || 'http://127.0.0.1:8000/v1').replace(/\/+$/, '');
    const apiKey = $('#localApiKeyInput')?.value?.trim() || state.settings?.localApiKey || '';
    if (statusEl) { statusEl.className = 'warn'; statusEl.textContent = '正在连接本地 API…'; }
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;
    let modelsFound = [];
    let connected = false;

    // 1. 尝试 OpenAI /v1/models 与 /models
    try {
      const modelsUrl = endpoint.endsWith('/models') ? endpoint : (endpoint.endsWith('/v1') ? `${endpoint}/models` : `${endpoint}/v1/models`);
      const json = await safeLocalFetch(modelsUrl, { headers });
      const list = Array.isArray(json?.data) ? json.data : Array.isArray(json) ? json : [];
      list.forEach(m => {
        const id = typeof m === 'string' ? m : m.id || m.name || m.title;
        if (id && typeof id === 'string') modelsFound.push(id.trim());
      });
      if (list.length > 0) connected = true;
    } catch {}

    // 2. 尝试 SD WebUI /sdapi/v1/sd-models
    if (!connected || modelsFound.length === 0) {
      try {
        const webuiUrl = `${endpoint.replace(/\/v1$/, '')}/sdapi/v1/sd-models`;
        const json = await safeLocalFetch(webuiUrl, { headers });
        if (Array.isArray(json)) {
          json.forEach(m => {
            const name = m.model_name || m.title;
            if (name) modelsFound.push(name.trim());
          });
          if (json.length > 0) connected = true;
        }
      } catch {}
    }

    // 3. 尝试 Ollama /api/tags
    if (!connected || modelsFound.length === 0) {
      try {
        const ollamaUrl = `${endpoint.replace(/\/v1$/, '')}/api/tags`;
        const json = await safeLocalFetch(ollamaUrl, { headers });
        const models = Array.isArray(json?.models) ? json.models : [];
        models.forEach(m => {
          const name = m.name || m.model;
          if (name) modelsFound.push(name.trim());
        });
        if (models.length > 0) connected = true;
      } catch {}
    }

    if (connected) {
      modelsFound = [...new Set(modelsFound)].filter(Boolean);
      state.settings = state.settings || {};
      state.settings.localApiEndpoint = endpoint;
      state.settings.localApiKey = apiKey;
      state.settings.imageProvider = 'local';
      const textModel = modelsFound.find(m => /qwen|llama|chat|instruct|deepseek|glm|mistral|gpt/i.test(m));
      if (textModel && (!state.settings.orchestrationModel || state.settings.orchestrationModel === 'qwen2.5:7b')) {
        state.settings.orchestrationModel = textModel;
        const orchInput = $('#orchestrationModelInput');
        if (orchInput) orchInput.value = textModel;
      }
      if (modelsFound.length > 0) {
        modelsFound.forEach(m => addCustomImageModel(m));
        if (!state.settings.defaultImageModel || state.settings.defaultImageModel === 'muse-image') {
          state.settings.defaultImageModel = modelsFound[0];
        }
        if (statusEl) { statusEl.className = 'ok'; statusEl.textContent = `✓ 连接成功！已自动获取 ${modelsFound.length} 个本地模型`; }
      } else {
        if (statusEl) { statusEl.className = 'ok'; statusEl.textContent = `✓ 接口连接成功（可在下方或节点中直接输入/选择模型名称）`; }
      }
      syncSettingsUI();
      render();
      saveState();
    } else {
      if (statusEl) { statusEl.className = 'error'; statusEl.textContent = `✗ 无法连接到 ${endpoint}，请确认服务已启动并输入有效端口`; }
    }
  }

  function markNodeDirty(nodeId) {
    const node = nodeById(nodeId);
    if (!node) return;
    node.data.dirty = true;
    const visited = new Set();
    const queue = [nodeId];
    while (queue.length) {
      const curr = queue.shift();
      if (visited.has(curr)) continue;
      visited.add(curr);
      for (const edge of state.edges.filter(e => e.source === curr)) {
        const targetNode = nodeById(edge.target);
        if (targetNode) {
          targetNode.data.dirty = true;
          queue.push(targetNode.id);
        }
      }
      for (const v of state.nodes.filter(item => item.type === 'generateVideo' && item.data?.continuity && !hasDirectKeyframe(item.id))) {
        if (timelinePredecessor(v.id)?.id === curr) {
          v.data.dirty = true;
          queue.push(v.id);
        }
      }
    }
    scheduleAutoSave();
  }

  function uid(prefix='id') { return `${prefix}-${crypto.randomUUID()}`; }
  function delay(ms, signal) {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(new DOMException("用户已停止生成。", 'AbortError'));
        return;
      }
      const timer = setTimeout(resolve, ms);
      signal?.addEventListener('abort', () => {
        clearTimeout(timer);
        reject(new DOMException("用户已停止生成。", 'AbortError'));
      }, { once: true });
    });
  }

  function starter() {
    return {
      nodes: [
        { id: 'prompt-1', type: 'prompt', x: 90, y: 110, data: { text: "电影质感的未来风格越南女性肖像，霓虹雨景，面部细节清晰" } },
        { id: 'gen-1', type: 'generateImage', x: 450, y: 105, data: { model: state.settings?.defaultImageModel || 'muse-image', size: '1:1', status: 'idle' } },
        { id: 'preview-1', type: 'preview', x: 820, y: 110, data: {} }
      ],
      edges: [
        { id: 'e1', source: 'prompt-1', sourcePort: 'text', target: 'gen-1', targetPort: 'prompt' },
        { id: 'e2', source: 'gen-1', sourcePort: 'image', target: 'preview-1', targetPort: 'media' }
      ]
    };
  }

  function addNode(type, x=250 + Math.random()*220, y=160 + Math.random()*180) {
    const dockTimeline=type==='timeline'&&state.nodes.find(node=>node.type==='timeline'&&node.data?.dockOnly);
    if(dockTimeline){dockTimeline.data.dockOnly=false;dockTimeline.x=x;dockTimeline.y=y;render();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();return;}
    const data = type === 'prompt' ? { text: "描述你希望 Muse 生成的内容…" } :
      type === 'negativePrompt' ? { text: "模糊、低画质、人体结构畸形、多余手指、文字、水印" } :
      type === 'textAppend' ? { text: "电影感光线，精细构图" } :
      type === 'textConcat' ? { separator: ', ' } :
      type === 'imageResize' ? { width: 1024, height: 1024, fit: 'cover' } :
      type === 'generateImage' ? { model: state.settings?.defaultImageModel || 'muse-image', size: '1:1', status: 'idle' } :
      type === 'generateVideo' ? { model: 'muse-video', size: '16:9', duration: 10, continuity: false, status: 'idle' } :
      type === 'timeline' ? { clipOrder: [], durations: {} } : {};
    const node={ id: uid(type), type, x, y, data };state.nodes.push(node);
    if(type==='references')syncReferenceFanOut(node);else if(['generateImage','generateVideo'].includes(type)){const references=state.nodes.find(item=>item.type==='references');if(references)connectReferenceNode(references,node);}
    render();if(type==='timeline'){syncTimelineDock();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();}
  }

  function nodeById(id) { return state.nodes.find(n => n.id === id); }

  function removeNode(id) {
    const outgoingTargets = state.edges.filter(e => e.source === id).map(e => e.target);
    state.nodes = state.nodes.filter(n => n.id !== id);
    state.edges = state.edges.filter(e => e.source !== id && e.target !== id);
    state.selectedNodeIds=state.selectedNodeIds.filter(nodeId=>nodeId!==id);if(state.selectedNodeId===id)state.selectedNodeId=state.selectedNodeIds.at(-1)||null;
    outgoingTargets.forEach(tid => markNodeDirty(tid));
    render();syncTimelineDock();
  }

  function selectNode(id,{toggle=false,add=false}={}){let ids=[...state.selectedNodeIds];if(toggle){ids=ids.includes(id)?ids.filter(item=>item!==id):[...ids,id];}else if(add){if(!ids.includes(id))ids.push(id);}else ids=[id];state.selectedNodeIds=ids;state.selectedNodeId=ids.at(-1)||null;document.querySelectorAll('.node').forEach(el=>el.classList.toggle('selected',ids.includes(el.dataset.id)));}

  // 提示词卡片专属吸附式 AI 控制器（选模型·用技能·自由输入）
        const CARD_SKILLS = {
    camera: {
      name: '🎬 运镜技能 (Camera)',
      tagLabel: '🎬 运镜技能',
      placeholder: '通过 AI 生成文本内容，可以添加图片、视频、音频或文档作为生成参考（打 / 换技能）',
      prompt: '你是精通 Seedance 2.5 影视运镜控制的大师。请根据用户的修改要求，输出符合电影工业标准的专业运镜参数（包含机位、视角、运动轨迹如推拉摇移/俯冲/探针/希区柯克变焦、动感节奏与速度控制）。采用专业精炼的中英文运镜描述，直接输出最终提示词内容，杜绝废话。'
    },
    lighting: {
      name: '💡 灯光技能 (Lighting)',
      tagLabel: '💡 灯光质感',
      placeholder: '输入光影需求，如：日落侧逆光，丁达尔光束穿透，冷暖对比强烈（打 / 换技能）',
      prompt: '你是顶级好莱坞电影灯光师。请根据用户的光影要求，重写为电影级灯光描述（包含主光源类型、光质、色温冷暖对比、丁达尔体积光束、阴影层次）。保持视觉质感高级真实，直接输出最终提示词内容，杜绝废话。'
    },
    director: {
      name: '🎥 导演技能 (Director)',
      tagLabel: '🎥 导演构图',
      placeholder: '输入分镜需求，如：强化微观细节，焦点从前景虚化逐渐清晰过渡（打 / 换技能）',
      prompt: '你是专业影视总导演。请根据用户的需求，撰写电影级画面分镜描述（包含景别、核心焦点主体、构图透视与环境空间层次）。直接输出最终专业描述，杜绝废话。'
    },
    continuity: {
      name: '🔄 连贯性技能 (Continuity)',
      tagLabel: '🔄 时空连贯',
      placeholder: '输入连贯性要求，如：承接上一镜头运动惯性，保持主体位置与光线方向不变（打 / 换技能）',
      prompt: '你是影视连续性守护专家。请确保当前分镜与全片的运动惯性、主体位置、光照方向无缝承接，重写提示词以锁定前后镜头的时空一致性。直接输出最终提示词内容，杜绝废话。'
    },
    free: {
      name: '✨ 自由提示词 (自由发挥)',
      tagLabel: '✨ 自由发挥',
      placeholder: '通过 AI 生成文本内容，可以添加图片、视频、音频或文档作为生成参考（打 / 换技能）',
      prompt: '你是专业影视 AI 创作助手。请根据用户的具体要求，直接输出优化重写后的最终完整提示词内容，杜绝多余废话。'
    }
  };

  // 全局 API 模型动态获取与缓存（绝不写死模型列表）
  async function getDynamicApiModels(forceRefresh = false) {
    if (!forceRefresh && Array.isArray(state.availableApiModels) && state.availableApiModels.length > 0) {
      return state.availableApiModels;
    }
    const endpoint = (state.settings?.localApiEndpoint || 'http://100.68.145.63:8317/v1').replace(/\/+$/, '');
    const apiKey = state.settings?.localApiKey || (endpoint.includes('100.68.145.63') ? 'sk-local-23fa8d80e597d0c0d90c2e75d1c1430787ed13afe1175d70' : '');
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;

    let fetched = [];
    try {
      const modelsUrl = endpoint.endsWith('/models') ? endpoint : (endpoint.endsWith('/v1') ? `${endpoint}/models` : `${endpoint}/v1/models`);
      const resp = await safeLocalFetch(modelsUrl, { headers, signal: AbortSignal.timeout(5000) });
      const list = Array.isArray(resp?.data) ? resp.data : (Array.isArray(resp) ? resp : (Array.isArray(resp?.models) ? resp.models : []));
      list.forEach(m => {
        const id = typeof m === 'string' ? m : (m.id || m.name || m.model);
        if (id && typeof id === 'string') {
          fetched.push(id.trim());
        }
      });
    } catch (e) {
      console.warn('[MuseFlow] 动态获取模型列表失败，将使用已知在线模型:', e);
    }

    if (fetched.length > 0) {
      state.availableApiModels = [...new Set(fetched)];
    } else if (!state.availableApiModels || !state.availableApiModels.length) {
      state.availableApiModels = ['grok-4.7', 'claude-opus-5-5-high', 'gemini-3.8-flash-high', 'grok-4.20-0309-reasoning'];
    }
    return state.availableApiModels;
  }

  if (!window._ctrlMenuGlobalBound) {
    window._ctrlMenuGlobalBound = true;
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.ctrl-popup-menu') && !e.target.closest('.ctrl-plus-btn')) {
        document.querySelectorAll('.ctrl-popup-menu').forEach(m => {
          m.classList.add('hidden');
          const pNode = m.closest('.node');
          if (pNode) pNode.style.zIndex = '';
        });
      }
    });
  }

  function createCardAiController(n, ta) {
    const box = document.createElement('div');
    box.className = 'card-ai-controller';
    box.onmousedown = (e) => e.stopPropagation();
    box.onclick = (e) => e.stopPropagation();

    if (!n.data) n.data = {};
    const isMotionNode = (n.data?.sceneLabel || '').includes('运镜') || n.id.includes('v_') || n.id.includes('video');
    if (!n.data.aiSkill) {
      n.data.aiSkill = isMotionNode ? 'camera' : 'director';
    }
    if (!n.data.aiModel) {
      n.data.aiModel = state.settings?.orchestrationModel || 'grok-4.7';
    }

    // 顶部胶囊标签区（选中的技能与模型）
    const tagsRow = document.createElement('div');
    tagsRow.className = 'ctrl-tags-row';

    function renderTags() {
      tagsRow.innerHTML = '';
      if (n.data.aiSkill && CARD_SKILLS[n.data.aiSkill]) {
        const skill = CARD_SKILLS[n.data.aiSkill];
        const sTag = document.createElement('div');
        sTag.className = 'ctrl-tag-pill skill-pill';
        sTag.innerHTML = `<span>${skill.tagLabel}</span><span class="pill-close">×</span>`;
        sTag.querySelector('.pill-close').onclick = (e) => {
          e.stopPropagation();
          n.data.aiSkill = null;
          renderTags();
        };
        tagsRow.appendChild(sTag);
      }
      if (n.data.aiModel) {
        const mTag = document.createElement('div');
        mTag.className = 'ctrl-tag-pill model-pill';
        mTag.innerHTML = `<span>🤖 ${n.data.aiModel}</span><span class="pill-close">×</span>`;
        mTag.querySelector('.pill-close').onclick = (e) => {
          e.stopPropagation();
          n.data.aiModel = null;
          renderTags();
        };
        tagsRow.appendChild(mTag);
      }
    }
    renderTags();
    box.appendChild(tagsRow);

    // 核心交互主容器
    const mainBox = document.createElement('div');
    mainBox.className = 'ctrl-main-box';

    // 左侧加号按钮
    const plusBtn = document.createElement('button');
    plusBtn.type = 'button';
    plusBtn.className = 'ctrl-plus-btn';
    plusBtn.title = '调用技能、选择模型或挂载参考素材（或在输入框输入 /）';
    plusBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="5" x2="12" y2="19"></line>
        <line x1="5" y1="12" x2="19" y2="12"></line>
      </svg>
    `;

    // 菜单弹出层
    const popupMenu = document.createElement('div');
    popupMenu.className = 'ctrl-popup-menu hidden';
    popupMenu.onclick = (e) => e.stopPropagation();

    function openMenu() {
      populateMenu();
      document.querySelectorAll('.ctrl-popup-menu').forEach(m => {
        m.classList.add('hidden');
        const pNode = m.closest('.node');
        if (pNode) pNode.style.zIndex = '';
      });
      popupMenu.classList.remove('hidden');
      const nodeEl = box.closest('.node');
      if (nodeEl) nodeEl.style.zIndex = '1000';
    }

    function closeMenu() {
      popupMenu.classList.add('hidden');
      const nodeEl = box.closest('.node');
      if (nodeEl) nodeEl.style.zIndex = '';
    }

    async function populateMenu() {
      popupMenu.innerHTML = '';

      // 1. 技能列表
      const skillHeader = document.createElement('div');
      skillHeader.className = 'menu-section-title';
      skillHeader.textContent = '🛠️ 调用技能 (Skills)';
      popupMenu.appendChild(skillHeader);

      Object.keys(CARD_SKILLS).forEach(k => {
        const item = document.createElement('div');
        item.className = 'menu-item' + (n.data.aiSkill === k ? ' active' : '');
        item.textContent = CARD_SKILLS[k].name;
        item.onclick = (e) => {
          e.stopPropagation();
          n.data.aiSkill = k;
          renderTags();
          closeMenu();
          inputTa.value = inputTa.value.replace(/\s*\/$/, '');
          inputTa.focus();
        };
        popupMenu.appendChild(item);
      });

      // 2. 动态模型列表（从 API 实时拉取，绝不写死）
      const modelHeader = document.createElement('div');
      modelHeader.className = 'menu-section-title model-section-header';
      modelHeader.innerHTML = '<span>🤖 选择模型 (动态 API)</span><span class="refresh-models-btn" title="点击重新从 API 获取最新模型">🔄 刷新</span>';
      popupMenu.appendChild(modelHeader);

      const refreshBtn = modelHeader.querySelector('.refresh-models-btn');
      if (refreshBtn) {
        refreshBtn.onclick = async (re) => {
          re.stopPropagation();
          refreshBtn.textContent = '⏳';
          await getDynamicApiModels(true);
          populateMenu();
        };
      }

      const models = await getDynamicApiModels();
      const modelListContainer = document.createElement('div');
      modelListContainer.className = 'menu-models-scroll';

      models.slice(0, 15).forEach(m => {
        const item = document.createElement('div');
        item.className = 'menu-item' + (n.data.aiModel === m ? ' active' : '');
        item.textContent = m;
        item.onclick = (e) => {
          e.stopPropagation();
          n.data.aiModel = m;
          renderTags();
          closeMenu();
          inputTa.focus();
        };
        modelListContainer.appendChild(item);
      });
      popupMenu.appendChild(modelListContainer);

      // 手动输入任意模型
      const customItem = document.createElement('div');
      customItem.className = 'menu-item custom-model-action';
      customItem.innerHTML = '<span>✍️ 手动输入其他模型名...</span>';
      customItem.onclick = (e) => {
        e.stopPropagation();
        const customName = prompt('输入你要调用的模型 ID（如 grok-4.7, deepseek-chat, qwen 等）：', n.data.aiModel || '');
        if (customName && customName.trim()) {
          n.data.aiModel = customName.trim();
          if (!state.availableApiModels) state.availableApiModels = [];
          if (!state.availableApiModels.includes(n.data.aiModel)) {
            state.availableApiModels.unshift(n.data.aiModel);
          }
          addCustomImageModel(n.data.aiModel);
          persistGlobalSettings({ customImageModels: state.settings?.customImageModels });
          renderTags();
          closeMenu();
          inputTa.focus();
        }
      };
      popupMenu.appendChild(customItem);

      // 快速查看/修改 API 端点与 Key
      const quickApiItem = document.createElement('div');
      quickApiItem.className = 'menu-item quick-api-action';
      quickApiItem.innerHTML = '<span>⚙️ 快捷配置 API 地址与 Key...</span>';
      quickApiItem.onclick = (e) => {
        e.stopPropagation();
        closeMenu();
        syncSettingsUI();
        $('#settingsModal').classList.remove('hidden');
      };
      popupMenu.appendChild(quickApiItem);

      // 3. 参考素材
      const refHeader = document.createElement('div');
      refHeader.className = 'menu-section-title';
      refHeader.textContent = '📎 参考素材 (Reference)';
      popupMenu.appendChild(refHeader);

      const refItem = document.createElement('div');
      refItem.className = 'menu-item';
      refItem.textContent = '🖼️ 自动关联前置图片参考';
      refItem.onclick = (e) => {
        e.stopPropagation();
        closeMenu();
        statusEl.className = 'ctrl-status';
        statusEl.textContent = '已开启上游参考锚点绑定';
        setTimeout(() => { if (statusEl.textContent.includes('参考')) statusEl.textContent = ''; }, 3000);
      };
      popupMenu.appendChild(refItem);
    }

    plusBtn.onclick = (e) => {
      e.stopPropagation();
      if (popupMenu.classList.contains('hidden')) {
        openMenu();
      } else {
        closeMenu();
      }
    };

    // 中间输入框区域
    const inputWrapper = document.createElement('div');
    inputWrapper.className = 'ctrl-input-wrapper';

    const inputTa = document.createElement('textarea');
    inputTa.className = 'ctrl-textarea';
    inputTa.rows = 2;
    inputTa.placeholder = '通过 AI 生成文本内容，可以添加图片、视频、音频或文档作为生成参考（打 / 换技能）';

    // 右上角放大按钮 ⤢
    const expandBtn = document.createElement('button');
    expandBtn.type = 'button';
    expandBtn.className = 'ctrl-expand-btn';
    expandBtn.title = '展开大窗口精细编写';
    expandBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 3 21 3 21 9"></polyline>
        <polyline points="9 21 3 21 3 15"></polyline>
        <line x1="21" y1="3" x2="14" y2="10"></line>
        <line x1="3" y1="21" x2="10" y2="14"></line>
      </svg>
    `;

    // 右下角发送按钮 ↑
    const sendBtn = document.createElement('button');
    sendBtn.type = 'button';
    sendBtn.className = 'ctrl-send-btn';
    sendBtn.title = '执行生成 / 修改 (Enter)';
    sendBtn.innerHTML = `
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="19" x2="12" y2="5"></line>
        <polyline points="5 12 12 5 19 12"></polyline>
      </svg>
    `;

    inputTa.oninput = () => {
      sendBtn.classList.toggle('active', inputTa.value.trim().length > 0);
      const val = inputTa.value;
      if (val === '/' || val.endsWith(' /') || val.endsWith('\n/')) {
        openMenu();
      }
    };

    inputTa.onkeydown = (e) => {
      e.stopPropagation();
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runController();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        if (n.data.previousText && inputTa.value === '') {
          e.preventDefault();
          const prev = n.data.previousText;
          n.data.previousText = ta.value;
          ta.value = prev;
          n.data.text = prev;
          n.data.prompt = prev;
          markNodeDirty(n.id);
          saveState();
          statusEl.className = 'ctrl-status';
          statusEl.innerHTML = '<span>↩️ 已恢复修改前的提示词</span>';
          setTimeout(() => { statusEl.textContent = ''; }, 3000);
        }
      }
    };

    sendBtn.onclick = (e) => {
      e.stopPropagation();
      runController();
    };

    // 展开弹窗
    expandBtn.onclick = (e) => {
      e.stopPropagation();
      openExpandModal(n, ta, inputTa, renderTags, () => runController());
    };

    inputWrapper.appendChild(inputTa);
    inputWrapper.appendChild(expandBtn);
    inputWrapper.appendChild(sendBtn);

    mainBox.appendChild(plusBtn);
    mainBox.appendChild(inputWrapper);
    mainBox.appendChild(popupMenu);
    box.appendChild(mainBox);

    // 状态与进度提示
    const statusEl = document.createElement('div');
    statusEl.className = 'ctrl-status';
    box.appendChild(statusEl);

    async function runController() {
      const rawText = inputTa.value.trim();
      if (!rawText) {
        statusEl.className = 'ctrl-status error';
        statusEl.textContent = '请输入想要修改的要求...';
        return;
      }

      const endpoint = (state.settings?.localApiEndpoint || 'http://100.68.145.63:8317/v1').replace(/\/+$/, '');
      const apiKey = state.settings?.localApiKey || (endpoint.includes('100.68.145.63') ? 'sk-local-23fa8d80e597d0c0d90c2e75d1c1430787ed13afe1175d70' : '');
      const chosenModel = n.data.aiModel || (state.availableApiModels?.[0] || 'grok-4.7');
      const chosenSkillKey = n.data.aiSkill || 'director';
      const skillDef = CARD_SKILLS[chosenSkillKey] || CARD_SKILLS.free;

      sendBtn.disabled = true;
      sendBtn.style.opacity = '0.5';
      statusEl.className = 'ctrl-status';
      statusEl.textContent = `🚀 正在调用真实大模型【${chosenModel}】+【${skillDef.tagLabel}】...`;

      try {
        const chatUrl = `${endpoint}/chat/completions`;
        const headers = { 'Content-Type': 'application/json' };
        if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;

        const reqBody = {
          model: chosenModel,
          messages: [
            { role: 'system', content: skillDef.prompt },
            { role: 'user', content: `【已有提示词内容】\n${ta.value || '(空)'}\n\n【用户修改要求】\n${rawText}\n\n请直接输出重写后的最终完整提示词内容，杜绝多余废话：` }
          ],
          temperature: 0.7,
          max_tokens: 400
        };

        const resp = await safeLocalFetch(chatUrl, {
          method: 'POST',
          headers,
          body: JSON.stringify(reqBody),
          signal: AbortSignal.timeout(20000)
        });

        let result = resp?.choices?.[0]?.message?.content?.trim();
        if (!result) {
          const errMsg = resp?.error?.message || (typeof resp === 'string' ? resp : '模型未返回有效回复');
          throw new Error(errMsg);
        }

        // 清理代码块标记
        result = result.replace(/^```[a-z]*\s*|\s*```$/gi, '').replace(/^提示词[：:]\s*/i, '').trim();

        // 记录历史供撤回
        const oldVal = ta.value;
        n.data.previousText = oldVal;

        ta.value = result;
        n.data.text = result;
        n.data.prompt = result;
        markNodeDirty(n.id);
        saveState();

        ta.style.transition = 'box-shadow 0.3s ease, border-color 0.3s ease';
        ta.style.borderColor = '#10b981';
        ta.style.boxShadow = '0 0 12px rgba(16, 185, 129, 0.4)';
        setTimeout(() => {
          ta.style.borderColor = '';
          ta.style.boxShadow = '';
        }, 1500);

        inputTa.value = '';
        sendBtn.classList.remove('active');
        statusEl.className = 'ctrl-status success';
        statusEl.innerHTML = `<span>✅ 真实模型【${chosenModel}】重写成功！</span><button type="button" class="ctrl-undo-link" title="点击撤回上一步修改">撤回原词</button>`;
        const undoBtn = statusEl.querySelector('.ctrl-undo-link');
        if (undoBtn) {
          undoBtn.onclick = (ue) => {
            ue.stopPropagation();
            ta.value = oldVal;
            n.data.text = oldVal;
            n.data.prompt = oldVal;
            markNodeDirty(n.id);
            saveState();
            statusEl.className = 'ctrl-status';
            statusEl.innerHTML = '<span>↩️ 已恢复修改前的提示词</span>';
            setTimeout(() => { statusEl.textContent = ''; }, 3000);
          };
        }
      } catch (e) {
        console.error('API model invocation error:', e);
        statusEl.className = 'ctrl-status error';
        statusEl.textContent = `❌ 模型调用失败: ${e.message || e}（真实 API 未通，原词未改动）`;
      } finally {
        sendBtn.disabled = false;
        sendBtn.style.opacity = '1';
      }
    }

    return box;
  }

  async function openExpandModal(n, ta, inputTa, renderTags, onConfirm) {
    let modal = document.getElementById('ctrlExpandModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'ctrlExpandModal';
      modal.className = 'ctrl-expand-modal-overlay';
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="ctrl-expand-dialog">
        <div class="ctrl-expand-header">
          <span class="ctrl-expand-title">✨ AI 提示词精细工作台</span>
          <button class="ctrl-expand-close" title="关闭 (Esc)">&times;</button>
        </div>
        <div class="ctrl-expand-toolbar">
          <div class="modal-section-label">🛠️ 生效技能：</div>
          <div class="modal-skills-bar" id="modalSkillsBar"></div>
          <div class="modal-section-label" style="margin-top: 8px;">🤖 编排模型（根据 API 动态拉取）：</div>
          <div class="modal-models-bar" id="modalModelsBar"></div>
        </div>
        <div class="ctrl-expand-body">
          <div class="ctrl-expand-group">
            <label>当前卡片已有提示词：</label>
            <textarea class="ctrl-expand-prev" readonly>${ta.value || '(空)'}</textarea>
          </div>
          <div class="ctrl-expand-group">
            <label>修改需求 / 灵感指令：</label>
            <textarea class="ctrl-expand-input" placeholder="输入画面调整、运镜速度、光影氛围等具体修改要求...">${inputTa.value || ''}</textarea>
          </div>
        </div>
        <div class="ctrl-expand-footer">
          <button class="btn-cancel">取消</button>
          <button class="btn-confirm primary">立即重构并应用</button>
        </div>
      </div>
    `;

    const skillsBar = modal.querySelector('#modalSkillsBar');
    Object.keys(CARD_SKILLS).forEach(k => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'modal-tag-pill' + (n.data.aiSkill === k ? ' active' : '');
      btn.textContent = CARD_SKILLS[k].name;
      btn.onclick = () => {
        n.data.aiSkill = k;
        skillsBar.querySelectorAll('.modal-tag-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (renderTags) renderTags();
      };
      skillsBar.appendChild(btn);
    });

    const modelsBar = modal.querySelector('#modalModelsBar');
    const models = await getDynamicApiModels();
    models.slice(0, 10).forEach(m => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'modal-tag-pill model' + (n.data.aiModel === m ? ' active' : '');
      btn.textContent = m;
      btn.onclick = () => {
        n.data.aiModel = m;
        modelsBar.querySelectorAll('.modal-tag-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (renderTags) renderTags();
      };
      modelsBar.appendChild(btn);
    });

    modal.classList.remove('hidden');
    const inputArea = modal.querySelector('.ctrl-expand-input');
    setTimeout(() => inputArea.focus(), 50);

    function closeModal() {
      modal.classList.add('hidden');
      document.removeEventListener('keydown', handleKey);
    }

    function handleKey(e) {
      if (e.key === 'Escape') {
        closeModal();
      }
    }
    document.addEventListener('keydown', handleKey);

    modal.onclick = (e) => {
      if (e.target === modal) closeModal();
    };
    modal.querySelector('.ctrl-expand-close').onclick = closeModal;
    modal.querySelector('.btn-cancel').onclick = closeModal;
    modal.querySelector('.btn-confirm').onclick = () => {
      const val = inputArea.value.trim();
      if (val) {
        inputTa.value = val;
        closeModal();
        if (onConfirm) onConfirm();
      } else {
        inputArea.placeholder = '请在此输入想要修改的具体内容...';
        inputArea.focus();
      }
    };
  }

  function removeSelectedNodes(){const ids=new Set(state.selectedNodeIds);if(!ids.size&&state.selectedNodeId)ids.add(state.selectedNodeId);if(!ids.size)return;state.nodes=state.nodes.filter(node=>!ids.has(node.id));state.edges=state.edges.filter(edge=>!ids.has(edge.source)&&!ids.has(edge.target));state.selectedNodeIds=[];state.selectedNodeId=null;render();saveState();}

  function portCompatible(from, targetNodeId, targetPortId) {
    const sourceNode = nodeById(from.nodeId), targetNode = nodeById(targetNodeId);
    if (!sourceNode || !targetNode || sourceNode.id === targetNode.id) return false;
    const out = (nodeDefs[sourceNode.type].outputs || []).find(p => p.id === from.portId);
    const input = (nodeDefs[targetNode.type].inputs || []).find(p => p.id === targetPortId);
    return Boolean(out && input && canConnectTypes(out.type,input.type));
  }

  function connectionChoices(from){
    const source=nodeById(from.nodeId),output=nodeDefs[source?.type]?.outputs?.find(port=>port.id===from.portId);if(!source||!output)return{existing:[],create:[]};
    const existing=[];for(const target of state.nodes){if(target.id===source.id)continue;for(const input of nodeDefs[target.type]?.inputs||[]){if(!portCompatible(from,target.id,input.id))continue;if(target.type==='timeline'&&getIncoming(target.id,input.id).length)continue;if(wouldCreateCycle(source.id,target.id,isMultiInput(target.type,input.id)?null:input.id))continue;existing.push({kind:'existing',targetId:target.id,targetPort:input.id,label:`${nodeDefs[target.type].title} · ${input.label}${target.data?.dockOnly?"（底部时间线）":''}`});}}
    const candidates=output.type==='image'?[['references','reference1',"参考图片 · 图片 1"],['preview','media',"预览 · 图片"],['imageResize','image',"调整图片尺寸"],['generateImage','reference',"生成图片 · 参考图片"],['generateVideo','reference',"生成视频 · 参考图片"]]:output.type==='video'?[['preview','media',"预览 · 视频"],['timeline','clip1',"时间线 · 添加片段"]]:output.type==='text'?[['generateImage','prompt',"生成图片 · 提示词"],['generateVideo','prompt',"生成视频 · 提示词"],['textAppend','text',"追加文本"],['textConcat','a',"合并文本 · 文本 A"],['textConcat','b',"合并文本 · 文本 B"]]:output.type==='negative'?[['generateImage','negative',"生成图片 · 反向提示词"],['generateVideo','negative',"生成视频 · 反向提示词"]]:[];
    const create=candidates.map(([type,port,label])=>({kind:'create',type,targetPort:port,label}));return{existing,create};
  }

  function openConnectionPicker(from,x,y){
    const output=nodeDefs[nodeById(from.nodeId)?.type]?.outputs?.find(port=>port.id===from.portId),choices=connectionChoices(from),menu=$('#canvasMenu'),viewport=$('#viewport').getBoundingClientRect();
    if(!output)return;state.pendingConnection={from:{...from},x:(x-viewport.left-state.panX)/state.zoom,y:(y-viewport.top-state.panY)/state.zoom,choices:[...choices.existing,...choices.create]};menu.innerHTML='';delete menu.dataset.nodeId;delete menu.dataset.edgeId;
    const title=document.createElement('div');title.className='menu-caption';title.textContent=`发送 ${output.label} · ${mediaText(output.type)}`;menu.appendChild(title);
    const addSection=label=>{const section=document.createElement('div');section.className='menu-caption';section.textContent=label;menu.appendChild(section);};
    const addChoice=(choice,index)=>{const button=document.createElement('button');button.type='button';button.textContent=choice.label;button.dataset.contextAction='connect-choice';button.dataset.choice=String(index);menu.appendChild(button);};
    if(choices.existing.length){addSection("连接已有节点");choices.existing.forEach((choice,index)=>addChoice(choice,index));}
    if(choices.create.length){addSection("创建兼容节点");choices.create.forEach((choice,index)=>addChoice(choice,choices.existing.length+index));}
    if(!state.pendingConnection.choices.length){const empty=document.createElement('div');empty.className='menu-caption';empty.textContent="此输出没有可兼容的节点操作。";menu.appendChild(empty);}
    menu.classList.remove('hidden');menu.style.left=`${Math.max(8,Math.min(x,innerWidth-260))}px`;menu.style.top=`${Math.max(8,Math.min(y,innerHeight-420))}px`;
  }

  function runConnectionChoice(index){
    const pending=state.pendingConnection,choice=pending?.choices?.[index];state.pendingConnection=null;closeCanvasMenu();
    if(!pending||!choice)return;
    if(choice.kind==='existing'){
      state.connectingFrom=pending.from;connect(choice.targetId,choice.targetPort);selectNode(choice.targetId,{add:true});setRunStatus(`已连接到 ${choice.label}.`,'ok');return;
    }
    const before=new Set(state.nodes.map(node=>node.id));addNode(choice.type,pending.x-135,pending.y-80);
    const target=state.nodes.find(node=>!before.has(node.id))||state.nodes.find(node=>node.type===choice.type&&node.data?.dockOnly===false&&choice.type==='timeline');if(!target||target.type!==choice.type){setRunStatus("无法创建所选节点。",'error');return;}
    state.connectingFrom=pending.from;connect(target.id,choice.targetPort);selectNode(target.id);setRunStatus(`${nodeDefs[target.type].title}已创建，并连接到 ${choice.label.split(' · ').at(-1)}.`,'ok');
  }

  function connect(targetNodeId, targetPortId) {
    const from = state.connectingFrom;
    if (!from) return;
    if (!portCompatible(from, targetNodeId, targetPortId)) {
      setRunStatus("端口类型不兼容。", 'error');
      state.connectingFrom = null;
      return;
    }
    const target=nodeById(targetNodeId),source=nodeById(from.nodeId),multi=isMultiInput(target?.type,targetPortId);
    if(wouldCreateCycle(from.nodeId,targetNodeId,multi?null:targetPortId)){setRunStatus("此连接会使工作流形成循环。请按单一方向连接节点。", 'error');state.connectingFrom=null;return;}
    const duplicate=state.edges.some(edge=>edge.source===from.nodeId&&edge.sourcePort===from.portId&&edge.target===targetNodeId&&edge.targetPort===targetPortId);
    if(!multi)state.edges=state.edges.filter(edge=>!(edge.target===targetNodeId&&edge.targetPort===targetPortId));
    if(!duplicate){
      state.edges.push({id:uid('edge'),source:from.nodeId,sourcePort:from.portId,target:targetNodeId,targetPort:targetPortId});
      markNodeDirty(targetNodeId);
    }
    if(target?.type==='timeline'&&targetPortId.startsWith('clip')&&source?.type==='generateVideo'){
      target.data.clipOrder=target.data.clipOrder||[];if(!target.data.clipOrder.includes(source.id))target.data.clipOrder.push(source.id);
    }
    state.connectingFrom=null;
    render();
  }

  function wouldCreateCycle(sourceId,targetId,replacedPort){const pending=[targetId],seen=new Set();while(pending.length){const id=pending.pop();if(id===sourceId)return true;if(seen.has(id))continue;seen.add(id);for(const edge of state.edges){if(edge.source===id&&!(edge.target===targetId&&edge.targetPort===replacedPort))pending.push(edge.target);}}return false;}

  function nearestCompatibleInput(x,y,from){
    let best=null,bestDistance=44;
    for(const port of document.querySelectorAll('.port.in')){
      if(!portCompatible(from,port.dataset.node,port.dataset.port))continue;
      const rect=port.getBoundingClientRect(),distance=Math.hypot(x-(rect.left+rect.width/2),y-(rect.top+rect.height/2));
      if(distance<bestDistance){best=port;bestDistance=distance;}
    }
    return best;
  }
  function canConnectTypes(outputType,inputType){return outputType===inputType||inputType==='media'&&['image','video'].includes(outputType);}
  function isMultiInput(nodeType,portId){return ['generateImage','generateVideo'].includes(nodeType)&&['prompt','reference'].includes(portId)||nodeType==='references'&&portId.startsWith('reference');}
  function connectReferenceNode(references,generator){if(!references||!generator||!['generateImage','generateVideo'].includes(generator.type))return;const duplicate=state.edges.some(edge=>edge.source===references.id&&edge.sourcePort==='image'&&edge.target===generator.id&&edge.targetPort==='reference');if(!duplicate)state.edges.push({id:uid('edge'),source:references.id,sourcePort:'image',target:generator.id,targetPort:'reference'});}
  function syncReferenceFanOut(references){for(const generator of state.nodes.filter(node=>['generateImage','generateVideo'].includes(node.type)))connectReferenceNode(references,generator);}

  function makeNode(type,x,y){
    const data=type==='prompt'?{text:"描述你希望 Muse 生成的内容…"}:type==='negativePrompt'?{text:"模糊、低画质、人体结构畸形、多余手指、文字、水印"}:type==='imageInput'?{}:type==='generateImage'?{model:state.settings?.defaultImageModel||'muse-image',size:'1:1',status:'idle'}:type==='generateVideo'?{model:'muse-video',size:'16:9',duration:5,continuity:false,status:'idle'}:{};
    return{id:uid(type),type,x,y,data};
  }

  function scriptField(section,label,nextLabels){
    const startPattern=new RegExp(`^[\\t ]*(?:${label})[\\t ]*[:：][\\t ]*`,'im'),match=startPattern.exec(section);if(!match)return'';
    const start=match.index+match[0].length,tail=section.slice(start),stop=nextLabels.length?new RegExp(`^[\\t ]*(?:${nextLabels.join('|')})[\\t ]*[:：]`,'im').exec(tail):null;
    return tail.slice(0,stop?stop.index:tail.length).trim();
  }
  function parseSceneScript(text){
    const heading=/^[\t ]*(?:CẢNH|场景|分镜|Scene)[\t ]*(\d+)[\t ]*[(（]([^\r\n)）]*)[)）][\t ]*[:：][\t ]*(.*?)\r?$/gim,matches=[...text.matchAll(heading)];
    const voLabel='口播文案|对应文案|口播|台词|旁白|文案|Voiceover|Narration',imageLabel='Prompt\\s+ảnh|首帧提示词|首帧生图词|图片提示词|图像提示词|图片提示|Image\\s+prompt',endImageLabel='尾帧提示词|尾帧生图词|尾图提示词|End\\s+image\\s+prompt|End\\s+frame\\s+prompt',videoLabel='Prompt\\s+video|视频提示词|视频提示|运镜提示词|Video\\s+prompt',audioLabel='Audio|音频|音效|声音';
    return matches.map((match,index)=>{
      const body=text.slice(match.index+match[0].length,matches[index+1]?.index??text.length),voText=scriptField(body,voLabel,[imageLabel,endImageLabel,videoLabel,audioLabel]),imagePrompt=scriptField(body,imageLabel,[endImageLabel,videoLabel,audioLabel]),endImagePrompt=scriptField(body,endImageLabel,[videoLabel,audioLabel]),videoPrompt=scriptField(body,videoLabel,[audioLabel]),audio=scriptField(body,audioLabel,[]),range=match[2].match(/(\d+)[:：](\d{2})\s*[–—\-~～至]\s*(\d+)[:：](\d{2})/);
      const seconds=range?(Number(range[3])*60+Number(range[4]))-(Number(range[1])*60+Number(range[2])):0;
      const ratio=(imagePrompt+' '+videoPrompt).match(/\b(9:16|16:9|1:1|4:3|3:4)\b/);
      return{number:Number(match[1]),title:match[3].trim(),voText:voText||match[3].trim(),imagePrompt,endImagePrompt,videoPrompt:[videoPrompt,audio?`Audio direction: ${audio}`:''].filter(Boolean).join('\n\n'),seconds:seconds>0?seconds:3.5,size:ratio?.[1]||'16:9'};
    }).filter(scene=>scene.imagePrompt||scene.videoPrompt);
  }

  function deriveEndFramePromptText(startPrompt, videoPrompt, title = '') {
    const base = String(startPrompt || '').trim();
    const motion = String(videoPrompt || '').replace(/Create a \d+(?:\.\d+)?s[^.]*\./gi, '').trim();
    if (!base) return '';
    return `${base}\n\n[END KEYFRAME / 尾帧目标定格画面]：展现本镜头（${title || '当前分镜'}）动作与运镜完成后的最终收尾定格状态。动作演进结果参考：${motion || '镜头推进到位、主体完成核心动作后的稳定构图'}。严格保持与首帧完全一致的角色造型、服装、道具细节与美术渲染画风。`;
  }

  function buildSceneNodesFromScript(){
    const status=$('#scriptImportStatus'),scenes=parseSceneScript($('#scriptInput').value);
    if(!scenes.length){status.className='error';status.textContent="未识别到场景。请使用“场景 1（0:00–0:07）：标题”，并填写“图片提示词”或“视频提示词”；也兼容原版 CẢNH 格式。";return;}
    const baseY=Math.max(40,...state.nodes.filter(node=>!node.data?.dockOnly).map(node=>node.y+360)),createdVideos=[];let made=0;
    scenes.forEach((scene,index)=>{
      const shotId=String(scene.number||index+1).padStart(2,'0');
      const x=580,y=baseY+index*880,label=`第${shotId}镜：${scene.title||`场景 ${scene.number}`}`;
      const voText=scene.voText||scene.title||label;
      let startImageNode=null,endImageNode=null,videoNode=null;
      if(scene.imagePrompt){
        const prompt=makeNode('prompt',x,y);
        prompt.data={text:scene.imagePrompt,sceneLabel:`【第${shotId}镜·首帧】生图词`,voText};
        const image=makeNode('generateImage',x+340,y);
        image.data={model:state.settings?.defaultImageModel||'gpt-image-2.5',size:scene.size,count:1,styleContinuity:index>0,status:'idle',sceneLabel:`【第${shotId}镜·首帧】${scene.title||''}`,frameRole:'start',shotNumber:scene.number||index+1,voText};
        state.nodes.push(prompt,image);
        state.edges.push({id:uid('edge'),source:prompt.id,sourcePort:'text',target:image.id,targetPort:'prompt'});
        startImageNode=image;made+=2;

        const endPromptText=scene.endImagePrompt||deriveEndFramePromptText(scene.imagePrompt,scene.videoPrompt,scene.title);
        const endPrompt=makeNode('prompt',x,y+280);
        endPrompt.data={text:endPromptText,sceneLabel:`【第${shotId}镜·尾帧】生图词`,voText};
        const endImg=makeNode('generateImage',x+340,y+280);
        endImg.data={model:state.settings?.defaultImageModel||'gpt-image-2.5',size:scene.size,count:1,styleContinuity:true,status:'idle',sceneLabel:`【第${shotId}镜·尾帧】${scene.title||''}`,frameRole:'end',shotNumber:scene.number||index+1,voText};
        state.nodes.push(endPrompt,endImg);
        state.edges.push({id:uid('edge'),source:endPrompt.id,sourcePort:'text',target:endImg.id,targetPort:'prompt'});
        endImageNode=endImg;made+=2;
      }
      if(scene.videoPrompt||scene.imagePrompt){
        const vPromptText=scene.videoPrompt||`第${shotId}镜（${scene.title||''}）：从首帧（Image 1）自然平滑演进至尾帧（Image 2），主体动作连贯，16:9电影质感。`;
        const prompt=makeNode('prompt',x,y+560);
        prompt.data={text:vPromptText,sceneLabel:`${shotId}·运镜提示词`,voText};
        videoNode=makeNode('generateVideo',x+720,y+180);
        videoNode.data={model:'muse-video',size:scene.size,duration:10,editDuration:scene.seconds||3.5,continuity:false,status:'idle',sceneLabel:`第${shotId}镜·${scene.title||''}`,shotNumber:scene.number||index+1,voText};
        state.nodes.push(prompt,videoNode);
        state.edges.push({id:uid('edge'),source:prompt.id,sourcePort:'text',target:videoNode.id,targetPort:'prompt'});
        if(startImageNode)state.edges.push({id:uid('edge'),source:startImageNode.id,sourcePort:'image',target:videoNode.id,targetPort:'reference'});
        if(endImageNode)state.edges.push({id:uid('edge'),source:endImageNode.id,sourcePort:'image',target:videoNode.id,targetPort:'reference'});
        made+=2;
        createdVideos.push({node:videoNode,seconds:scene.seconds||3.5});
      }
    });
    let references=state.nodes.find(node=>node.type==='references');if(!references){const minX=Math.min(80,...state.nodes.filter(node=>!node.data?.dockOnly).map(node=>node.x));references=makeNode('references',minX-360,baseY);references.data={};state.nodes.push(references);made++;}syncReferenceFanOut(references);
    const timeline=ensureDockTimeline();timeline.data.clipOrder=createdVideos.map(item=>item.node.id);timeline.data.durations=timeline.data.durations||{};createdVideos.forEach(({node,seconds})=>{timeline.data.durations[node.id]=seconds;});
    $('#scriptModal').classList.add('hidden');render();saveState();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();
    setRunStatus(`已创建 ${scenes.length} 个分镜（每镜自动配齐【首帧+尾帧】双底图并连入 10s 视频节点）· 共 ${made} 个节点。`,'ok');
  }

  // --- AI 智能分镜编排引擎 (P1) ---
  let currentStoryboardScenes = [];
  let currentStoryboardPlan = { source: 'local_ai', model: '', scenes: [] };

  function cleanAndParseJson(raw) {
    if (!raw || typeof raw !== 'string') return null;
    let text = raw.trim();
    text = text.replace(/^```[a-zA-Z]*\s*/i, '').replace(/\s*```$/i, '').trim();
    const startArr = text.indexOf('[');
    const endArr = text.lastIndexOf(']');
    if (startArr !== -1 && endArr > startArr) {
      try {
        const parsed = JSON.parse(text.slice(startArr, endArr + 1));
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      } catch {}
    }
    const startObj = text.indexOf('{');
    const endObj = text.lastIndexOf('}');
    if (startObj !== -1 && endObj > startObj) {
      try {
        const obj = JSON.parse(text.slice(startObj, endObj + 1));
        const list = obj.scenes || obj.storyboard || obj.data || obj.shots;
        if (Array.isArray(list) && list.length > 0) return list;
        return [obj];
      } catch {}
    }
    try {
      let candidate = text.slice(startArr !== -1 ? startArr : 0, endArr !== -1 ? endArr + 1 : undefined);
      candidate = candidate.replace(/,\s*([\]}])/g, '$1');
      const parsed = JSON.parse(candidate);
      if (Array.isArray(parsed)) return parsed;
    } catch {}
    return null;
  }

  async function callLocalChatLLM({ prompt, systemPrompt, endpoint, model, apiKey, signal, messages }) {
    endpoint = (endpoint || state.settings?.localApiEndpoint || 'http://127.0.0.1:11434').replace(/\/+$/, '');
    model = model || state.settings?.orchestrationModel || 'qwen2.5:7b';
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;

    const conversationMessages = Array.isArray(messages) && messages.length > 0
      ? [
          ...(systemPrompt ? [{ role: 'system', content: systemPrompt }] : []),
          ...messages
        ]
      : [
          ...(systemPrompt ? [{ role: 'system', content: systemPrompt }] : []),
          { role: 'user', content: prompt }
        ];

    if (endpoint.includes('11434') || endpoint.includes('/api/')) {
      try {
        const ollamaChatUrl = `${endpoint.replace(/\/v1$/, '')}/api/chat`;
        const payload = {
          model,
          messages: conversationMessages,
          stream: false,
          options: { temperature: 0.7 }
        };
        const data = await safeLocalFetch(ollamaChatUrl, { method: 'POST', headers, body: JSON.stringify(payload), signal });
        if (data?.message?.content) return data.message.content;
      } catch (ollamaErr) {
        try {
          const genUrl = `${endpoint.replace(/\/v1$/, '')}/api/generate`;
          const fullPrompt = conversationMessages.map(m => `${m.role}: ${m.content}`).join('\n\n');
          const data = await safeLocalFetch(genUrl, { method: 'POST', headers, body: JSON.stringify({ model, prompt: fullPrompt, stream: false }), signal });
          if (data?.response) return data.response;
        } catch {}
      }
    }

    let chatUrl = endpoint;
    if (!chatUrl.endsWith('/chat/completions')) {
      chatUrl = chatUrl.endsWith('/v1') ? `${chatUrl}/chat/completions` : `${chatUrl}/v1/chat/completions`;
    }
    const reqPayload = {
      model,
      messages: conversationMessages,
      temperature: 0.7
    };
    const data = await safeLocalFetch(chatUrl, { method: 'POST', headers, body: JSON.stringify(reqPayload), signal });
    const content = data?.choices?.[0]?.message?.content;
    if (content) return content;
    throw new Error("本地大模型未返回有效的文本内容。");
  }

  function heuristicFallbackOrchestrator(userIdea, { targetDuration = 30, size = '9:16', style = '自然写实纪实', flowMode = 'image_to_video', readyImages = [] } = {}) {
    const raw = String(userIdea || '').trim();

    // 若用户上传了一组现成的满意图片，直接以此批量组装图生视频分镜方案！
    if (Array.isArray(readyImages) && readyImages.length > 0) {
      const cameraMovements = [
        "平稳慢动作微推镜头，主体呼吸感微动，环境流光溢彩，氛围感拉满，4K 影视级画质",
        "镜头自远及近缓慢平移推进，焦点从前景虚化逐渐清晰过渡至主体核心细节，光影柔和流动",
        "微距环绕轻微摇镜，展现主体精致轮廓与细腻材质肌理，背景平滑自然虚化",
        "低角度略微仰拍并缓慢向前平滑滑动运镜，展现主体开阔气势与沉浸式纵深感",
        "平视镜头轻微左右横移推拉，微风吹拂发丝与环境细节，富有生动电影感动态",
        "缓慢拉远镜头展示全貌，柔和日光从侧后方穿透，电影级调色与景深效果"
      ];
      return readyImages.map((imgAtt, idx) => ({
        number: idx + 1,
        title: `分镜 ${idx + 1}: ${imgAtt.name ? imgAtt.name.replace(/\.[^/.]+$/, '') : '满意底图'}`,
        duration: 6,
        size,
        mode: 'image_to_video',
        readyImage: { dataUrl: imgAtt.dataUrl, name: imgAtt.name },
        imagePrompt: `[底图已就绪: ${imgAtt.name || '满意原图'}]`,
        videoPrompt: cameraMovements[idx % cameraMovements.length],
        negativePrompt: "模糊, 画面抖动, 结构畸变, 杂乱水印",
        continuity: false
      }));
    }

    const isAgri = /氮肥|施肥|农业|作物|土壤|根系|吸收|植物/i.test(raw);
    const isFox = /狐狸|受伤|森林|救助|女孩|放归|自然|动物/i.test(raw);
    const aspectDesc = size === '16:9' ? '16:9 宽屏' : size === '1:1' ? '1:1 正方形' : '9:16 竖屏短视频';
    const stylePrefix = `[${style}风格, ${aspectDesc}]`;

    if (isAgri) {
      return [
        {
          number: 1,
          title: "宏观农田与长势反差建立",
          duration: 6,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 广袤葱郁的现代农田全景，阳光倾泻，一边是青翠挺拔的健壮作物，另一边是叶片泛黄卷曲的过量施肥试验田，强烈的视觉反差，高清晰度，自然光影。`,
          videoPrompt: `无人机平稳向前低空航拍推进，掠过对比鲜明的两块田埂，微风吹拂作物叶片轻微摆动，环境音效：开阔田野风声与隐约虫鸣。`,
          negativePrompt: "人物口播, 杂乱文字, 模糊失真, 过度曝光",
          continuity: false
        },
        {
          number: 2,
          title: "微观土壤颗粒与过量氮肥沉积",
          duration: 6,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 极高倍率土壤微距摄影，褐色湿润土壤颗粒缝隙中，堆积着过密白色晶体状的氮肥颗粒，土壤胶体出现轻度盐渍化结晶，显微镜质感。`,
          videoPrompt: `慢动作微距镜头垂直下摇推近，白色氮肥颗粒在微细土粒间缓慢溶解，浓度过高产生轻微渗透压倒流动态，音效：微观溶解滋滋声与低沉环境音。`,
          negativePrompt: "模糊, 噪点, 低清, 变形",
          continuity: false
        },
        {
          number: 3,
          title: "作物根毛细胞渗透受阻机理",
          duration: 8,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 植物根毛细胞的微观剖面，半透明的植物毛根细胞膜，高浓度土壤溶液阻碍了水分与养分的正常渗透，细胞略显脱水紧缩状态，科学可视化美感。`,
          videoPrompt: `镜头沿幼根表面平滑横向运镜追踪，展示养分水分子因浓度差无法顺利涌入根细胞膜的动态过程，柔和蓝绿色生物微光，音效：深沉流动音效。`,
          negativePrompt: "脏乱背景, 解剖失真, 模糊",
          continuity: false
        },
        {
          number: 4,
          title: "科学施肥后的强健根系与丰收",
          duration: 10,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 采用测土配方精准施肥后的金黄麦浪与健硕饱满穗粒，根系在地底如白色网络般深扎舒展，生机勃勃，金色暖阳光辉。`,
          videoPrompt: `低角度仰拍镜头顺着茁壮麦秆快速上摇冲入明媚蓝天，金色麦浪随风剧烈翻滚，充满丰收自豪感，音效：欢快清脆麦穗碰撞声与丰收微风。`,
          negativePrompt: "枯萎, 病虫害, 人脸畸变",
          continuity: false
        }
      ];
    }

    if (isFox) {
      return [
        {
          number: 1,
          title: "深秋枫林与受伤小赤狐",
          duration: 6,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 金黄色与深红枫叶铺满的深秋林地，一束柔和阳光透过林荫，一只毛茸茸的小赤狐蜷缩在枯木旁，左后腿轻微擦伤，神情警惕而脆弱，电影胶片质感。`,
          videoPrompt: `长焦镜头缓慢向前推入，小赤狐警惕地抬起耳朵嗅探四周，落叶在微风中缓缓飘落，音效：林间落叶踩踏轻响与轻柔风声。`,
          negativePrompt: "血腥, 残缺肢体, 恐怖, 模糊",
          continuity: false
        },
        {
          number: 2,
          title: "女孩温柔接近与温暖包裹",
          duration: 6,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 穿着深色羊毛大衣的温柔女孩蹲下身，伸出戴着软手套的手递过食物，用柔软羊毛毯轻轻将小赤狐包裹抱在怀中，眼神充满关切。`,
          videoPrompt: `柔焦中景横移运镜，小赤狐从害怕到慢慢放松依偎在毛毯中，女孩起身轻步穿过林间小径，音效：轻柔呼吸声与温暖环境音。`,
          negativePrompt: "动作僵硬, 五官扭曲, 画面过曝",
          continuity: false
        },
        {
          number: 3,
          title: "木屋内的细心换药与康复",
          duration: 8,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 温暖木屋壁炉旁，火光跳跃，小赤狐趴在软垫上好奇打量四周，腿部伤口已换上整齐白纱布，一碗温水与肉干摆在身旁，温馨宁静。`,
          videoPrompt: `环绕镜头平缓旋转，壁炉柴火噼啪作响，小狐狸轻舔女孩的手背以示亲昵，腿部已能有力站立，音效：木柴燃烧声与满足微声。`,
          negativePrompt: "脏乱, 变形, 灰暗",
          continuity: false
        },
        {
          number: 4,
          title: "春暖花开之际的回眸放归",
          duration: 10,
          size,
          mode: flowMode,
          imagePrompt: `${stylePrefix} 初春微风吹拂的青翠山坡，山花烂漫，毛色鲜亮健康的大赤狐站在花丛中，依依不舍地回头望向镜头外的救助者，随后轻快奔向森林深处。`,
          videoPrompt: `慢镜头低角度跟拍，赤狐回头凝望片刻后纵身一跃跃入灌木花丛，阳光洒满橙红尾尖，音效：清脆鸟鸣与林间春风。`,
          negativePrompt: "畸形爪子, 模糊, 阴暗",
          continuity: false
        }
      ];
    }

    const sentences = raw.split(/[。！？\n；;]+/).map(s => s.trim()).filter(Boolean);
    const count = Math.max(2, Math.min(6, sentences.length || 3));
    const scenes = [];
    const durPerScene = [5, 6, 8, 10].reduce((best, v) => Math.abs(v - Math.round(targetDuration / count)) < Math.abs(best - Math.round(targetDuration / count)) ? v : best, 6);

    for (let i = 0; i < count; i++) {
      const textChunk = sentences[i] || `核心画面展示 ${i + 1}：${raw.slice(0, 30)}`;
      const isStart = i === 0;
      const isEnd = i === count - 1;
      const title = isStart ? "序幕：背景建立与主体呈现" : isEnd ? "终章：主题升华与高潮收尾" : `第 ${i + 1} 幕：情节深入与细节刻画`;
      scenes.push({
        number: i + 1,
        title,
        duration: durPerScene,
        size,
        mode: flowMode,
        imagePrompt: `${stylePrefix} ${textChunk}，专业电影级构图，细腻的光影质感，丰富的环境细节，色彩层次丰富，8K高分辨率渲染。`,
        videoPrompt: `电影感${isStart ? '缓慢平滑推近镜头' : isEnd ? '缓缓拉远全景升华镜头' : '平滑跟拍移动镜头'}，展现：${textChunk}，动作自然流畅连贯，环境立体环绕音效。`,
        negativePrompt: "低分辨率, 画面撕裂, 模糊变形, 错误解剖, 乱码文字",
        continuity: false
      });
    }
    return scenes;
  }

  async function orchestrateVideoScenes(userIdea, options = {}) {
    const statusEl = $('#orchestrationStatus');
    if (statusEl) {
      statusEl.className = 'warn';
      statusEl.textContent = "正在调用本地 AI 大模型解析文案、拆解分镜与编写提示词…";
    }

    const {
      targetDuration = 30,
      size = '9:16',
      style = '自然写实纪实',
      flowMode = 'image_to_video'
    } = options;

    let scenes = null;
    let source = 'local_ai';
    let modelUsed = state.settings?.orchestrationModel || 'qwen2.5:7b';
    try {
      const systemPrompt = `你是一名专业短视频编导与 AI 镜头拆解大师。
请根据用户的视频创意或故事文案，将其拆解并规划为一个结构化、富有视觉节奏感的分镜列表。
输出必须为纯 JSON 数组，严禁包含任何前缀解释或 markdown 标记包裹。
每个分镜格式规范如下：
[
  {
    "number": 1,
    "title": "镜头标题",
    "duration": 6,
    "size": "${size}",
    "mode": "${flowMode}",
    "imagePrompt": "极精细的生图提示词（主体外貌特征、构图景别、光影质感、色彩基调、艺术风格，符合${style}要求）",
    "videoPrompt": "极精细的生视频提示词（镜头运动推拉摇移、主体动作细节、环境动态变化、音效描述）",
    "negativePrompt": "blurry, low quality, distorted, bad anatomy",
    "continuity": false
  }
]
注意：
1. 镜头时长 duration 只能从 [5, 6, 8, 10] 中选取；
2. 总时长约 ${targetDuration} 秒（约 ${Math.round(targetDuration / 6)} 个镜头）；
3. 每个分镜都有各自独立的分镜画面，continuity 默认必须设为 false（防止上一镜尾帧锁死后续画面导致视频重复）；
4. 确保输出纯正合法的 JSON 数组。`;

      const rawLlmOutput = await callLocalChatLLM({
        prompt: `【用户视频创意文案】：\n${userIdea}\n\n画幅比例：${size}，视觉风格：${style}，目标总时长约 ${targetDuration} 秒。请直接输出分镜 JSON 数组。`,
        systemPrompt,
        endpoint: state.settings?.localApiEndpoint,
        model: modelUsed,
        apiKey: state.settings?.localApiKey
      });

      const parsed = cleanAndParseJson(rawLlmOutput);
      if (Array.isArray(parsed) && parsed.length > 0) {
        scenes = parsed.map((s, idx) => ({
          number: s.number || idx + 1,
          title: s.title || `分镜 ${idx + 1}`,
          duration: [5, 6, 8, 10].includes(Number(s.duration)) ? Number(s.duration) : 6,
          size: s.size || size,
          mode: s.mode || flowMode,
          imagePrompt: s.imagePrompt || s.image_prompt || '',
          videoPrompt: s.videoPrompt || s.video_prompt || '',
          negativePrompt: s.negativePrompt || s.negative_prompt || 'blurry, low quality, distorted',
          continuity: Boolean(s.continuity)
        }));
      }
    } catch (err) {
      console.warn("本地大模型调用异常，将启用内置启发式拆镜规则：", err);
    }

    if (!scenes || !scenes.length) {
      scenes = heuristicFallbackOrchestrator(userIdea, { targetDuration, size, style, flowMode });
      source = 'heuristic';
      modelUsed = 'rule-engine';
      if (statusEl) {
        statusEl.className = 'warn';
        statusEl.textContent = "本地 AI 模型未连接或输出非 JSON，已自动启用内置专业编排规则拆解完成！";
      }
    } else {
      if (statusEl) {
        statusEl.className = 'ok';
        statusEl.textContent = `本地 AI 大模型 (${modelUsed}) 编排成功，共拆解为 ${scenes.length} 个精细分镜！`;
      }
    }

    currentStoryboardPlan = { source, model: modelUsed, scenes };
    currentStoryboardScenes = scenes;
    return scenes;
  }

  function renderStoryboardUI() {
    const list = $('#storyboardCardsList');
    if (!list) return;
    list.innerHTML = '';
    $('#storyboardCount').textContent = String(currentStoryboardScenes.length);
    const sourceBadge = $('#storyboardSourceBadge');
    if (sourceBadge) {
      if (currentStoryboardPlan.source === 'local_ai') {
        sourceBadge.style.display = 'inline-block';
        sourceBadge.style.background = 'rgba(124,58,237,0.2)';
        sourceBadge.style.color = '#c084fc';
        sourceBadge.textContent = `🤖 本地 AI 大模型 (${currentStoryboardPlan.model || 'qwen2.5:7b'})`;
      } else {
        sourceBadge.style.display = 'inline-block';
        sourceBadge.style.background = 'rgba(234,179,8,0.2)';
        sourceBadge.style.color = '#fde047';
        sourceBadge.textContent = '⚡ 智能规则后备编排';
      }
    }

    currentStoryboardScenes.forEach((scene, index) => {
      const card = document.createElement('div');
      card.className = 'storyboard-card';
      card.dataset.index = index;

      const header = document.createElement('div');
      header.className = 'storyboard-card-header';
      const titleBox = document.createElement('div');
      titleBox.className = 'storyboard-card-title';
      titleBox.innerHTML = `<span>#${scene.number || index + 1}</span>`;
      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.value = scene.title || `场景 ${index + 1}`;
      titleInput.oninput = () => { scene.title = titleInput.value; };
      titleBox.appendChild(titleInput);

      const headerRight = document.createElement('div');
      headerRight.style.display = 'flex';
      headerRight.style.gap = '8px';
      headerRight.style.alignItems = 'center';

      const durSelect = document.createElement('select');
      [5, 6, 8, 10].forEach(d => {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = `${d} 秒`;
        if (Number(scene.duration) === d) opt.selected = true;
        durSelect.appendChild(opt);
      });
      durSelect.onchange = () => { scene.duration = Number(durSelect.value); };

      const modeSelect = document.createElement('select');
      [['image_to_video', '图生视频'], ['text_to_video', '文生视频']].forEach(([v, l]) => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = l;
        if (scene.mode === v) opt.selected = true;
        modeSelect.appendChild(opt);
      });
      modeSelect.onchange = () => {
        scene.mode = modeSelect.value;
        renderStoryboardUI();
      };

      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.textContent = '删除';
      delBtn.className = 'danger';
      delBtn.style.padding = '2px 6px';
      delBtn.onclick = () => {
        currentStoryboardScenes.splice(index, 1);
        currentStoryboardScenes.forEach((s, idx) => s.number = idx + 1);
        renderStoryboardUI();
      };

      headerRight.append(durSelect, modeSelect, delBtn);
      header.append(titleBox, headerRight);
      card.appendChild(header);

      const body = document.createElement('div');
      body.className = 'storyboard-card-body';
      if (scene.mode !== 'text_to_video') {
        const imgField = document.createElement('div');
        imgField.className = 'storyboard-field';
        imgField.innerHTML = '<label>🖼 图片提示词 (Image Prompt)</label>';
        const imgTa = document.createElement('textarea');
        imgTa.value = scene.imagePrompt || '';
        imgTa.oninput = () => { scene.imagePrompt = imgTa.value; };
        imgField.appendChild(imgTa);
        body.appendChild(imgField);
      }

      const vidField = document.createElement('div');
      vidField.className = 'storyboard-field';
      if (scene.mode === 'text_to_video') vidField.style.gridColumn = '1 / -1';
      vidField.innerHTML = '<label>🎬 视频运动提示词 (Video Motion & Audio)</label>';
      const vidTa = document.createElement('textarea');
      vidTa.value = scene.videoPrompt || '';
      vidTa.oninput = () => { scene.videoPrompt = vidTa.value; };
      vidField.appendChild(vidTa);
      body.appendChild(vidField);

      card.appendChild(body);

      const footer = document.createElement('div');
      footer.className = 'storyboard-card-footer';
      const continuityLabel = document.createElement('label');
      continuityLabel.style.display = 'flex';
      continuityLabel.style.alignItems = 'center';
      continuityLabel.style.gap = '6px';
      continuityLabel.style.cursor = 'pointer';
      const continuityChk = document.createElement('input');
      continuityChk.type = 'checkbox';
      continuityChk.checked = Boolean(scene.continuity);
      continuityChk.onchange = () => { scene.continuity = continuityChk.checked; };
      continuityLabel.append(continuityChk, document.createTextNode("开启与前序镜头的尾帧连续性 (Continuity)"));

      const ratioHint = document.createElement('span');
      ratioHint.textContent = `画幅: ${scene.size || '9:16'}`;

      footer.append(continuityLabel, ratioHint);
      card.appendChild(footer);

      list.appendChild(card);
    });
  }

  function buildWorkflowFromStoryboard(scenes, options = {}) {
    if (!Array.isArray(scenes) || !scenes.length) return;
    const shouldReplace = options.replace === true;
    if (shouldReplace) {
      // 清空业务节点与连线，保留时间线等底栏 dockOnly 节点
      state.nodes = state.nodes.filter(node => node.data?.dockOnly);
      state.edges = [];
    }
    const nonDockNodes = state.nodes.filter(node => !node.data?.dockOnly);
    const baseY = (shouldReplace || !nonDockNodes.length)
      ? 100
      : Math.max(40, ...nonDockNodes.map(node => node.y + 400));
    const createdVideos = [];
    let made = 0;

    scenes.forEach((scene, index) => {
      const shotNum = Number(scene.number) || (index + 1);
      const shotId = String(shotNum).padStart(2, '0');
      const x = 580;
      const y = baseY + index * 880;
      const label = `第${shotId}镜：${scene.title || `场景 ${shotNum}`}`;
      const voText = scene.voText || scene.voiceover || scene.narration || scene.title || label;
      let startImageNode = null;
      let endImageNode = null;
      let videoNode = null;

      if (scene.readyImage?.dataUrl) {
        // 模式 A：底图已就绪（支持首帧 + 尾帧直接挂载）
        const imgInput = makeNode('imageInput', x + 340, y);
        imgInput.data = {
          localDataUrl: scene.readyImage.dataUrl,
          asset: { id: uid('asset'), kind: 'image', url: scene.readyImage.dataUrl, name: scene.readyImage.name || '满意底图', sourceNodeId: imgInput.id },
          sceneLabel: `【第${shotId}镜·首帧】${scene.title || ''}`,
          frameRole: 'start',
          shotNumber: shotNum,
          voText
        };
        state.nodes.push(imgInput);
        made++;
        startImageNode = imgInput;

        if (scene.readyEndImage?.dataUrl) {
          const endInput = makeNode('imageInput', x + 340, y + 260);
          endInput.data = {
            localDataUrl: scene.readyEndImage.dataUrl,
            asset: { id: uid('asset'), kind: 'image', url: scene.readyEndImage.dataUrl, name: scene.readyEndImage.name || '满意尾帧', sourceNodeId: endInput.id },
            sceneLabel: `【第${shotId}镜·尾帧】${scene.title || ''}`,
            frameRole: 'end',
            shotNumber: shotNum,
            voText
          };
          state.nodes.push(endInput);
          made++;
          endImageNode = endInput;
        }

        const videoY = y + 520;
        const videoPromptNode = makeNode('prompt', x, videoY);
        videoPromptNode.data = { text: scene.videoPrompt || 'Cinematic smooth camera motion', sceneLabel: `${shotId}·运镜提示词`, voText };

        videoNode = makeNode('generateVideo', x + 720, y + 180);
        videoNode.data = {
          model: 'muse-video',
          size: scene.size || '16:9',
          duration: 10,
          editDuration: Number(scene.duration) || 3.5,
          continuity: false,
          status: 'idle',
          sceneLabel: label,
          shotNumber: shotNum,
          voText,
          sceneSource: { type: currentStoryboardPlan?.source || 'local_ai', model: currentStoryboardPlan?.model || '', edited: false }
        };
        state.nodes.push(videoPromptNode, videoNode);
        made += 2;

        // 连线：首帧(Image 1) + 尾帧(Image 2) -> videoNode (reference)
        state.edges.push({ id: uid('edge'), source: startImageNode.id, sourcePort: 'image', target: videoNode.id, targetPort: 'reference' });
        if (endImageNode) {
          state.edges.push({ id: uid('edge'), source: endImageNode.id, sourcePort: 'image', target: videoNode.id, targetPort: 'reference' });
        }
        // 连线：videoPromptNode -> videoNode (prompt)
        state.edges.push({ id: uid('edge'), source: videoPromptNode.id, sourcePort: 'text', target: videoNode.id, targetPort: 'prompt' });
        createdVideos.push({ node: videoNode, seconds: videoNode.data.editDuration });
        return;
      } else if (scene.mode !== 'text_to_video' && scene.imagePrompt) {
        // 自动融合生成【首帧】与【尾帧】两个独立高清生图节点，并双双连入本镜视频节点
        const prompt = makeNode('prompt', x, y);
        prompt.data = { text: scene.imagePrompt, sceneLabel: `【第${shotId}镜·首帧】生图词`, voText };
        const image = makeNode('generateImage', x + 340, y);
        image.data = {
          model: state.settings?.defaultImageModel || 'gpt-image-2.5',
          size: scene.size || '16:9',
          count: 1,
          styleContinuity: index > 0,
          status: 'idle',
          sceneLabel: `【第${shotId}镜·首帧】${scene.title || ''}`,
          frameRole: 'start',
          shotNumber: shotNum,
          voText,
          sceneSource: { type: currentStoryboardPlan?.source || 'local_ai', model: currentStoryboardPlan?.model || '', edited: false }
        };
        state.nodes.push(prompt, image);
        state.edges.push({ id: uid('edge'), source: prompt.id, sourcePort: 'text', target: image.id, targetPort: 'prompt' });
        startImageNode = image;
        made += 2;

        const endPromptText = scene.endImagePrompt || deriveEndFramePromptText(scene.imagePrompt, scene.videoPrompt, scene.title);
        const endPrompt = makeNode('prompt', x, y + 280);
        endPrompt.data = { text: endPromptText, sceneLabel: `【第${shotId}镜·尾帧】生图词`, voText };
        const endImage = makeNode('generateImage', x + 340, y + 280);
        endImage.data = {
          model: state.settings?.defaultImageModel || 'gpt-image-2.5',
          size: scene.size || '16:9',
          count: 1,
          styleContinuity: true,
          status: 'idle',
          sceneLabel: `【第${shotId}镜·尾帧】${scene.title || ''}`,
          frameRole: 'end',
          shotNumber: shotNum,
          voText,
          sceneSource: { type: currentStoryboardPlan?.source || 'local_ai', model: currentStoryboardPlan?.model || '', edited: false }
        };
        state.nodes.push(endPrompt, endImage);
        state.edges.push({ id: uid('edge'), source: endPrompt.id, sourcePort: 'text', target: endImage.id, targetPort: 'prompt' });
        endImageNode = endImage;
        made += 2;
      }

      const videoY = (scene.mode !== 'text_to_video' && scene.imagePrompt) ? y + 560 : y;
      const videoPromptNode = makeNode('prompt', x, videoY);
      videoPromptNode.data = { text: scene.videoPrompt || scene.imagePrompt || 'Cinematic video shot', sceneLabel: `${shotId}·运镜提示词`, voText };

      videoNode = makeNode('generateVideo', x + 720, y + 180);
      videoNode.data = {
        model: 'muse-video',
        size: scene.size || '16:9',
        duration: 10,
        editDuration: Number(scene.duration) || 3.5,
        continuity: false,
        status: 'idle',
        sceneLabel: label,
        shotNumber: shotNum,
        voText,
        sceneSource: { type: currentStoryboardPlan?.source || 'local_ai', model: currentStoryboardPlan?.model || '', edited: false }
      };
      state.nodes.push(videoPromptNode, videoNode);
      state.edges.push({ id: uid('edge'), source: videoPromptNode.id, sourcePort: 'text', target: videoNode.id, targetPort: 'prompt' });
      made += 2;

      if (startImageNode) {
        state.edges.push({ id: uid('edge'), source: startImageNode.id, sourcePort: 'image', target: videoNode.id, targetPort: 'reference' });
      }
      if (endImageNode) {
        state.edges.push({ id: uid('edge'), source: endImageNode.id, sourcePort: 'image', target: videoNode.id, targetPort: 'reference' });
      }

      createdVideos.push({ node: videoNode, seconds: videoNode.data.editDuration });
    });

    let references = state.nodes.find(node => node.type === 'references');
    if (!references) {
      const minX = Math.min(80, ...state.nodes.filter(node => !node.data?.dockOnly).map(node => node.x));
      references = makeNode('references', minX - 360, baseY);
      references.data = {};
      state.nodes.push(references);
      made++;
    }

    // 若会话中存在用户上传的参考图片，自动将其转换为画布 imageInput 节点并接入 references 节点
    if (Array.isArray(aiChatSessionUploadedImages) && aiChatSessionUploadedImages.length > 0) {
      const imagesToMount = aiChatSessionUploadedImages.slice(0, 8);
      imagesToMount.forEach((imgAtt, idx) => {
        const imgInputX = references.x - 320;
        const imgInputY = references.y + idx * 240;
        const imgInput = makeNode('imageInput', imgInputX, imgInputY);
        imgInput.data = {
          localDataUrl: imgAtt.dataUrl,
          asset: { id: uid('asset'), kind: 'image', url: imgAtt.dataUrl, sourceNodeId: imgInput.id, name: imgAtt.name },
          sceneLabel: `参考图: ${imgAtt.name || '用户上传'}`
        };
        state.nodes.push(imgInput);
        made++;
        const portId = `reference${idx + 1}`;
        const duplicate = state.edges.some(e => e.source === imgInput.id && e.target === references.id && e.targetPort === portId);
        if (!duplicate) {
          state.edges.push({ id: uid('edge'), source: imgInput.id, sourcePort: 'image', target: references.id, targetPort: portId });
        }
      });
    }

    syncReferenceFanOut(references);

    const timeline = ensureDockTimeline();
    timeline.data.clipOrder = timeline.data.clipOrder || [];
    timeline.data.durations = timeline.data.durations || {};
    createdVideos.forEach(({ node, seconds }) => {
      if (!timeline.data.clipOrder.includes(node.id)) timeline.data.clipOrder.push(node.id);
      timeline.data.durations[node.id] = seconds;
    });

    $('#aiOrchestrateModal').classList.add('hidden');
    render();
    saveState();
    if ($('#timelineDock').classList.contains('collapsed')) toggleTimeline();
    fitCanvas();
    const actionText = shouldReplace ? '全新搭建' : '追加搭建';
    setRunStatus(`🎉 已成功由 AI 对话${actionText} ${scenes.length} 个分镜 · ${made} 个节点并排入时间线！`, 'ok');
  }

  function screenToCanvas(x,y){const rect=$('#viewport').getBoundingClientRect();return{x:x-rect.left,y:y-rect.top};}

  function startWire(e,nodeId,portId){
    if(e.button!==undefined&&e.button!==0)return;
    e.preventDefault();e.stopPropagation();
    state.draggingWire={nodeId,portId};state.connectingFrom={nodeId,portId};state.wireMoved=false;
    const sourceForCapture=nodeById(nodeId);
    if(!(sourceForCapture?.type==='generateVideo'&&portId==='video'))try{e.currentTarget.setPointerCapture(e.pointerId);}catch{}
    state.wirePointer={x:e.clientX,y:e.clientY};state.wireOrigin={x:e.clientX,y:e.clientY};
    document.querySelectorAll('.port.in').forEach(port=>{if(portCompatible({nodeId,portId},port.dataset.node,port.dataset.port))port.classList.add('wire-compatible');});
  }

  function startWireFromInput(e,nodeId,portId,portType){
    if(e.button!==undefined&&e.button!==0)return;e.preventDefault();e.stopPropagation();state.draggingWire={nodeId,portId,direction:'in',portType};state.wireMoved=false;state.wirePointer={x:e.clientX,y:e.clientY};state.wireOrigin={x:e.clientX,y:e.clientY};
    try{e.currentTarget.setPointerCapture(e.pointerId);}catch{}
    document.querySelectorAll('.port.out').forEach(port=>{if(portCompatible({nodeId:port.dataset.node,portId:port.dataset.port},nodeId,portId))port.classList.add('wire-compatible');});
  }

  function onWireMove(e){
    if(!state.draggingWire)return;
    if(state.wireOrigin&&Math.hypot(e.clientX-state.wireOrigin.x,e.clientY-state.wireOrigin.y)>5)state.wireMoved=true;
      const source=nodeById(state.draggingWire.nodeId),dock=$('#timelineDock'),overDock=source?.type==='generateVideo'&&state.draggingWire.portId==='video'&&(()=>{const r=dock.getBoundingClientRect();return e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;})();
    dock.classList.toggle('wire-drop-target',Boolean(overDock));
    if(overDock&&dock.classList.contains('collapsed'))toggleTimeline();
    state.wirePointer={x:e.clientX,y:e.clientY};scheduleDrawEdges();
  }

  function onWireUp(e){
    if(!state.draggingWire)return;
    const from=state.draggingWire,moved=state.wireMoved,source=nodeById(from.nodeId),dock=$('#timelineDock'),r=dock.getBoundingClientRect(),droppedOnTimeline=source?.type==='generateVideo'&&from.portId==='video'&&e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;
    state.draggingWire=null;state.wirePointer=null;state.wireOrigin=null;
    dock.classList.remove('wire-drop-target');
    document.querySelectorAll('.wire-compatible').forEach(port=>port.classList.remove('wire-compatible'));
    if(moved&&from.direction==='in'){
      const output=nearestCompatibleOutput(e.clientX,e.clientY,from);
      if(output){state.connectingFrom={nodeId:output.dataset.node,portId:output.dataset.port};connect(from.nodeId,from.portId);}
      else{const rect=$('#viewport').getBoundingClientRect(),emptyCanvas=!document.elementFromPoint(e.clientX,e.clientY)?.closest('.node'),inside=e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom,type=from.portType==='negative'?'negativePrompt':'prompt';if(inside&&emptyCanvas){addNode(type,(e.clientX-rect.left-state.panX)/state.zoom-135,(e.clientY-rect.top-state.panY)/state.zoom-80);const created=state.nodes.at(-1);state.connectingFrom={nodeId:created.id,portId:'text'};connect(from.nodeId,from.portId);setRunStatus(`${nodeDefs[type].title}已创建并连接。`,'ok');}else setRunStatus("拖到输出端口，或拖到画布空白处创建提示词节点。",'warn');}
      state.suppressPortClick=true;setTimeout(()=>state.suppressPortClick=false,80);scheduleDrawEdges();return;
    }
    if(moved){
      if(droppedOnTimeline){addTimelineClip(ensureDockTimeline(),source.id);state.connectingFrom=null;state.suppressPortClick=true;setTimeout(()=>state.suppressPortClick=false,80);scheduleDrawEdges();return;}
      const hit=nearestCompatibleInput(e.clientX,e.clientY,from);
      if(hit){state.connectingFrom=from;connect(hit.dataset.node,hit.dataset.port);}
      else {const rect=$('#viewport').getBoundingClientRect(),inside=e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom;if(inside)openConnectionPicker(from,e.clientX,e.clientY);else{state.connectingFrom=null;setRunStatus("将输出拖到画布上，选择兼容节点。",'warn');}}
      state.suppressPortClick=true;setTimeout(()=>state.suppressPortClick=false,80);
    }
    scheduleDrawEdges();
  }

  function nearestInputPort(x,y){
    const direct=document.elementsFromPoint(x,y).map(el=>el.closest?.('.port.in')).filter(Boolean);
    const candidates=[...new Set([...direct,...document.querySelectorAll('.port.in.wire-compatible')])];
    let best=null,distance=Infinity;
    for(const port of candidates){if(!port.classList.contains('wire-compatible'))continue;const r=port.getBoundingClientRect(),d=Math.hypot(x-(r.left+r.width/2),y-(r.top+r.height/2));if(d<distance){best=port;distance=d;}}
    return best&&distance<=38?best:null;
  }
  function nearestCompatibleOutput(x,y,target){let best=null,distance=44;for(const port of document.querySelectorAll('.port.out')){if(!portCompatible({nodeId:port.dataset.node,portId:port.dataset.port},target.nodeId,target.portId))continue;const rect=port.getBoundingClientRect(),d=Math.hypot(x-(rect.left+rect.width/2),y-(rect.top+rect.height/2));if(d<distance){best=port;distance=d;}}return best;}

  // --- P2: 素材多版本生命周期、确定性媒体质检与时间线导出完整性核验 ---
  function ensureNodeVersions(n) {
    if (!n || !['generateImage', 'generateVideo'].includes(n.type)) return;
    if (!n.data || typeof n.data !== 'object' || Array.isArray(n.data)) n.data = {};
    if (!Array.isArray(n.data.versions)) {
      n.data.versions = [];
    }
    // 老工程兼容迁移：若已有资产但没有版本记录，自动包装为版本 1
    if (n.data.versions.length === 0 && n.data.asset?.url) {
      const v1Id = n.data.asset.id || uid('ver');
      const v1 = {
        id: v1Id,
        versionNumber: 1,
        name: '版本 1',
        kind: n.data.asset.kind || (n.type === 'generateVideo' ? 'video' : 'image'),
        url: n.data.asset.url,
        model: n.data.model || (n.type === 'generateVideo' ? 'muse-video' : 'muse-image'),
        prompt: n.data.prompt || '',
        createdAt: Date.now(),
        width: n.data.asset.width,
        height: n.data.asset.height,
        candidates: n.data.candidates || [],
        endFrame: n.data.endFrame || null,
        quality: n.data.asset.quality || {
          status: 'unchecked',
          issues: [],
          checkedAt: Date.now()
        }
      };
      n.data.versions.push(v1);
      n.data.activeVersionId = v1Id;
      n.data.asset.id = v1Id;
      n.data.asset.versionNumber = 1;
      n.data.asset.quality = v1.quality;
    }
    // 自动兼容清洗自定义或导入的工作流版本字段，避免 Vundefined
    n.data.versions.forEach((v, idx) => {
      if (!v.id) v.id = uid("ver");
      if (typeof v.versionNumber !== "number") {
        const parsed = parseInt(String(v.version || "").replace(/\D+/g, ""), 10);
        v.versionNumber = Number.isFinite(parsed) ? parsed : (idx + 1);
      }
      if (!v.name) v.name = `版本 ${v.versionNumber}`;
      if (!v.quality) v.quality = { status: "passed", issues: [], checkedAt: Date.now() };
      if (v.selected) n.data.activeVersionId = v.id;
    });
    if (!n.data.activeVersionId && n.data.versions.length > 0) {
      n.data.activeVersionId = n.data.versions[0].id;
    }
  }

  function inspectMediaQuality(info = {}) {
    const { url, kind = 'image', width, height, duration, size, isVideo, requestedDuration, reviewNotes } = info;
   const warningThreshold = Number(info.warningThreshold ?? state.settings?.ratioWarningThreshold ?? 0.15);
   const rejectThreshold = Number(info.rejectThreshold ?? state.settings?.ratioRejectThreshold ?? 0.4);
    if (!url) {
      return { status: 'rejected', issues: ['媒体资源 URL 为空'], checkedAt: Date.now(), details: {} };
    }
    const issues = [];
    let status = 'passed';
    const expectedRatio = ratioValue(size);
    const actualRatio = width && height ? width / height : 0;
    if (!width || !height) {
      issues.push('无法获取画面尺寸或受跨域限制，需人工核验');
      status = 'unavailable';
    } else if (isVideo && typeof duration === 'number' && duration <= 0) {
      issues.push('视频时长为 0 或无法解码媒体流');
      status = 'rejected';
    } else if (expectedRatio && actualRatio) {
      const ratioDiff = Math.abs(Math.log(actualRatio / expectedRatio));
     if (ratioDiff > rejectThreshold) {
        issues.push(`画幅比例严重不符（请求：${size}，实际：${width}×${height}）`);
        status = 'rejected';
     } else if (ratioDiff > warningThreshold) {
        issues.push(`画幅比例轻微偏差（请求：${size}，实际：${width}×${height}）`);
        status = 'warning';
      }
    }
    if (isVideo && typeof duration === 'number' && typeof requestedDuration === 'number') {
      const durDiff = Math.abs(duration - requestedDuration);
      if (durDiff > 0.8) {
        issues.push(`实测时长 ${duration.toFixed(1)} 秒（要求的 ${requestedDuration} 秒可在后期自主剪辑）`);
      }
    }
    if (reviewNotes) {
      issues.push(`页面反馈：${reviewNotes}`);
      if (status === 'passed' && /(?:生成失败|错误|报错|无法生成)/.test(reviewNotes)) {
        status = 'warning';
      }
    }
    return {
      status,
      issues,
      reviewNotes: reviewNotes || '',
      checkedAt: Date.now(),
      details: { width, height, duration: duration || 0, requestedDuration, expectedRatio, actualRatio, warningThreshold, rejectThreshold }
    };
  }

  function switchNodeVersion(nodeId, versionId) {
    const n = nodeById(nodeId);
    if (!n || !n.data.versions || !n.data.versions.length) return false;
    const targetVer = n.data.versions.find(v => v.id === versionId);
    if (!targetVer) return false;
    n.data.activeVersionId = versionId;
    n.data.asset = {
      id: targetVer.id,
      kind: targetVer.kind,
      url: targetVer.url,
      name: `${targetVer.kind === 'video' ? '视频' : '图片'} ${n.id} (V${targetVer.versionNumber})`,
      sourceNodeId: n.id,
      versionNumber: targetVer.versionNumber,
      width: targetVer.width,
      height: targetVer.height,
      requestedSize: n.data.size,
      quality: targetVer.quality
    };
    if (targetVer.candidates && targetVer.candidates.length) {
      n.data.candidates = targetVer.candidates;
    }
    if (targetVer.kind === 'video') {
      n.data.endFrame = targetVer.endFrame || null;
    }
    state.edges.filter(e => e.source === n.id).forEach(e => {
      const target = nodeById(e.target);
      if (target?.type === 'preview') {
        target.data.asset = e.sourcePort === 'endFrame' ? n.data.endFrame : n.data.asset;
      }
    });
    render();
    scheduleAutoSave();
    return true;
  }

  function toggleQualityStatus(nodeId, versionId) {
    const n = nodeById(nodeId);
    if (!n) return;
    ensureNodeVersions(n);
    const ver = n.data.versions?.find(v => v.id === versionId) || (n.data.asset ? n.data.asset : null);
    if (!ver) return;
    if (!ver.quality) ver.quality = { status: 'unchecked', issues: [], checkedAt: Date.now() };
    ver.quality.status = ver.quality.status === 'passed' ? 'rejected' : 'passed';
    if (ver.quality.status === 'rejected' && (!ver.quality.issues || !ver.quality.issues.length)) {
      ver.quality.issues = ['用户人工标记为需重做'];
    } else if (ver.quality.status === 'passed') {
      ver.quality.issues = [];
    }
    if (n.data.asset && (n.data.asset.id === versionId || n.data.activeVersionId === versionId)) {
      n.data.asset.quality = ver.quality;
    }
    render();
    scheduleAutoSave();
  }

  function validateTimelineBeforeExport() {
    const node = ensureDockTimeline();
    const clipIds = visibleTimelineClipOrder(node);
    const problems = [];
    const validClips = [];

    clipIds.forEach((id, idx) => {
      const clip = nodeById(id);
      const sceneNum = idx + 1;
      if (!clip) {
        problems.push({ index: sceneNum, id, reason: `镜头 ${sceneNum}: 节点已被删除或引用无效` });
        return;
      }
      if (clip.type !== 'generateVideo') {
        problems.push({ index: sceneNum, id, reason: `镜头 ${sceneNum} (${clip.id}): 不是有效的视频生成节点` });
        return;
      }
      if (!clip.data?.asset?.url) {
        problems.push({ index: sceneNum, id, reason: `镜头 ${sceneNum} (${clip.id}): 尚未生成视频素材` });
        return;
      }
      const quality = clip.data.asset.quality || clip.data.versions?.find(v => v.id === clip.data.activeVersionId)?.quality;
      if (quality?.status === 'rejected') {
        problems.push({ index: sceneNum, id, reason: `镜头 ${sceneNum} (${clip.id}): 质检不合格 (${quality.issues?.join('；') || '未通过质检'})` });
        return;
      }
      validClips.push(clip);
    });

    return {
      total: clipIds.length,
      problems,
      validClips,
      canExportDirectly: problems.length === 0 && validClips.length > 0
    };
  }

  function normalizeSavedGraph(){
    const knownNodes=new Set(Object.keys(nodeDefs));
    const seenNodeIds=new Set();
    state.nodes=state.nodes.filter(node=>{if(!node||!knownNodes.has(node.type)||typeof node.id!=='string'||seenNodeIds.has(node.id))return false;seenNodeIds.add(node.id);return true;});
    const CURSOR_15_VO_MAP = {
      1: "一个人，一个月提交 1000 次代码",
      2: "一天 200 次，听着像吹牛对吧？但这是 Cursor 内部工程师现在的真实日常",
      3: "因为他们写代码的方式，已经彻底变了——人不再亲手敲每一行代码，而是指挥一群 AI 替自己干活",
      4: "很多人用不好 AI，是因为一上来就让它直接写代码，结果越改越乱",
      5: "真正的高手只做三件事：第一，给它一本厨房说明书（AGENTS.md），写清楚调料在哪、哪些坑绝对不能踩",
      6: "第二，绝不让 AI 瞎猜，先让它翻遍整个代码库，写好施工蓝图，人确认点头了，才准动工",
      7: "第三，装一套自动验菜机——代码写完自己跑测试、自己修 Bug，不合格绝不端上桌",
      8: "以前AI像个没头苍蝇，在屋里乱撞还把锅烧穿了",
      9: "现在你把规则、技能和护栏全配齐，AI 就像一支训练有素的施工队",
      10: "你看，连修个底层崩溃，它都能自己查日志、做实验、一步步排除故障",
      11: "发现爱偷懒走近道？加一条防呆铁律锁进规则本，下次绝对不再犯",
      12: "甚至连审代码、提 PR、写复盘报告，全都能在后台流水线自动跑完",
      13: "你可能会问：AI 干完了，那人干什么？",
      14: "人负责最值钱的事：定方向、搭系统、把控最终审美和品质",
      15: "未来最好的程序员，是会定规矩的总包工头"
    };
    const inferShotNumber = (n) => {
      if (Number(n?.data?.shotNumber) > 0) return Number(n.data.shotNumber);
      const idMatch = String(n?.id || '').match(/shot_0*(\d+)/i);
      if (idMatch) return Number(idMatch[1]);
      const labelMatch = String(n?.data?.sceneLabel || '').match(/(?:第\s*0*(\d+)\s*镜|场景\s*0*(\d+)|^0*(\d+)·)/i);
      if (labelMatch) return Number(labelMatch[1] || labelMatch[2] || labelMatch[3]);
      return 0;
    };
    for(const node of state.nodes){
      if(!node.data||typeof node.data!=='object'||Array.isArray(node.data))node.data={};
      const shotNum = inferShotNumber(node);
      if (shotNum > 0 && !node.data.shotNumber) node.data.shotNumber = shotNum;
      if (node.type === 'generateImage' && !node.data.frameRole && shotNum > 0) {
        node.data.frameRole = /end|尾帧|尾图/i.test(`${node.id} ${node.data.sceneLabel || ''}`) ? 'end' : 'start';
      }
      if (shotNum > 0 && !node.data.voText) {
        const labelStr = String(node.data.sceneLabel || '');
        if (/cursor|大厨|厨房|代码|工头|机器|防呆|蓝图|日志/i.test(JSON.stringify(state.nodes).slice(0, 4000)) && CURSOR_15_VO_MAP[shotNum]) {
          node.data.voText = CURSOR_15_VO_MAP[shotNum];
        } else {
          node.data.voText = labelStr.replace(/^(?:【[^】]+】|\d+·|第\d+镜[·：:]?|场景\s*\d+[：:]?)\s*/, '').trim() || `第 ${shotNum} 镜台词`;
        }
      }
      // 统一将所有视频节点的 Muse 请求时长升级为 10 秒完整原片（保留原剪辑时长在 editDuration）
      if (node.type === 'generateVideo') {
        const curDur = Number(node.data.duration) || 10;
        if (curDur < 10) {
          node.data.editDuration = Number(node.data.editDuration) || curDur;
          node.data.duration = 10;
        } else if (!node.data.editDuration) {
          node.data.editDuration = 3.5;
        }
      }
      // 清理旧运镜提示词里写死的 Create a 3.0s / 3.5s，避免 Muse 自动调用 3s 裁剪工具
      if (node.type === 'prompt' && typeof node.data.text === 'string' && /Create a \d+(?:\.\d+)?s\b/i.test(node.data.text)) {
        const m = node.data.text.match(/Create a (\d+(?:\.\d+)?)s\b/i);
        if (m && Number(m[1]) < 10) {
          node.data.editDurationHint = Number(m[1]);
          node.data.text = node.data.text.replace(/Create a (\d+(?:\.\d+)?)s\b/gi, 'Create a 10s full uncut');
        }
      }
      if(['generateImage','generateVideo'].includes(node.type)){
        ensureNodeVersions(node);
        // 精确恢复判定：严禁仅凭 asset?.url 盲目转为 success 或 idle
        if(node.data.status === 'running' || node.data.status === 'submission_unknown'){
          if(node.data.submittedToMuse){
            // 提交结果未知：保持 submission_unknown，绝不自动设为 success，绝不转为 idle 导致重复向 Muse 提交
            node.data.status = 'submission_unknown';
            node.data.mediaStatus = 'unsettled';
            node.data.errorType = 'SUBMISSION_UNKNOWN';
            node.data.error = '请求已发送至 Muse，但页面刷新导致结算状态未知。为防止重复扣费与卡片错乱，已安全暂停自动提交；请在 Muse 确认生成结果或单独点击重试。';
          }else{
            // 未曾向 Muse 提交（在前端排队或本地检查阶段被中断）
            node.data.status = 'idle';
            node.data.error = '上次运行在提交前被中断，可以重新运行。';
            node.data.errorType = 'INTERRUPTED';
            delete node.data.pendingRequestId;
            delete node.data.submittedToMuse;
            delete node.data.submittedTime;
            delete node.data.baseAssetVersionId;
          }
        }
      }
      if(node.data?.error?.includes('reviewNotes is not defined')){
        node.data.error = '';
        delete node.data.errorType;
        if(node.data.asset?.url || (node.data.versions && node.data.versions.length > 0)){
          node.data.status = 'success';
          node.data.dirty = false;
        }
      }
    }
    for(const node of state.nodes)if(node.type==='timeline'){
      node.data.clipOrder=Array.isArray(node.data.clipOrder)?[...new Set(node.data.clipOrder.filter(id=>state.nodes.some(item=>item.id===id&&item.type==='generateVideo')))]:[];
      if(!node.data.durations||typeof node.data.durations!=='object'||Array.isArray(node.data.durations))node.data.durations={};
    }
    const normalized=[];
    for(const raw of state.edges){
      if(!raw||typeof raw.source!=='string'||typeof raw.target!=='string')continue;
      const source=nodeById(raw.source),target=nodeById(raw.target);
      if(!source||!target||source.id===target.id)continue;
      const outputs=nodeDefs[source.type].outputs||[],inputs=nodeDefs[target.type].inputs||[];
      // Only infer port names for old single-port edges; never guess between semantic ports.
      const sourcePort=raw.sourcePort|| (outputs.length===1?outputs[0].id:null);
      const sourceDef=outputs.find(port=>port.id===sourcePort);
      const compatibleInputs=inputs.filter(port=>sourceDef&&canConnectTypes(sourceDef.type,port.type));
      const targetPort=raw.targetPort|| (compatibleInputs.length===1?compatibleInputs[0].id:null);
      const inputDef=inputs.find(port=>port.id===targetPort);
      if(!sourceDef||!inputDef||!canConnectTypes(sourceDef.type,inputDef.type))continue;
      normalized.push({...raw,id:raw.id||uid('edge'),sourcePort,targetPort});
    }
    // Normal inputs are single-source; prompt and reference inputs retain distinct sources.
    const occupied=new Set(),unique=[];
    for(let index=normalized.length-1;index>=0;index--){const edge=normalized[index],key=isMultiInput(nodeById(edge.target)?.type,edge.targetPort)?`${edge.target}:${edge.targetPort}:${edge.source}:${edge.sourcePort}`:`${edge.target}:${edge.targetPort}`;if(occupied.has(key))continue;occupied.add(key);unique.push(edge);}
    state.edges=unique.reverse();
  }

  
  // --- P3: 质检与审核问题回显面板组件 ---
  function renderReviewEchoBox(n, body) {
    const currentVer = n.data.versions?.find(v => v.id === n.data.activeVersionId) || n.data.versions?.[0];
    const issues = currentVer?.quality?.issues || (n.data.error ? [n.data.error] : []);
    const reviewNotes = n.data.reviewNotes || currentVer?.quality?.reviewNotes || '';

    if (!reviewNotes && issues.length === 0) return;

    const qStat = currentVer?.quality?.status || (n.data.status === 'failed' ? 'rejected' : 'warning');
    const box = document.createElement('div');
    box.className = `node-review-echo-box ${qStat}`;

    const header = document.createElement('div');
    header.className = 'review-echo-header';
    header.innerHTML = `<span class="review-icon">${qStat === 'passed' ? '✓' : qStat === 'rejected' ? '✕' : '⚠'}</span> <strong>质检与审核问题回显</strong>`;
    box.appendChild(header);

    if (n.type === 'generateVideo' && (['failed', 'error', 'submission_unknown'].includes(n.data.status) || qStat !== 'passed')) {
      const actionRow = document.createElement('div');
      actionRow.className = 'review-actions';
      actionRow.style.marginBottom = '6px';
      const fetchBtn = document.createElement('button');
      fetchBtn.type = 'button';
      fetchBtn.className = 'review-action-btn';
      fetchBtn.textContent = '⚡ 从页面重连抓取视频（10s原片）';
      fetchBtn.title = '检测到视频已在页面生成，点击直接从当前 Muse 会话补齐 10 秒完整原片并转为正常资产';
      fetchBtn.onclick = (e) => {
        e.stopPropagation();
        recoverVideoFromMuse(n.id);
      };
      actionRow.appendChild(fetchBtn);
      box.appendChild(actionRow);
    }

    if (reviewNotes) {
      const notesEl = document.createElement('div');
      notesEl.className = 'review-echo-text';
      notesEl.textContent = reviewNotes;
      box.appendChild(notesEl);
    }

    if (issues.length > 0) {
      const listEl = document.createElement('ul');
      listEl.className = 'review-issues-list';
      issues.filter(iss => !reviewNotes || !iss.includes(reviewNotes.slice(0, 30))).forEach(iss => {
        const li = document.createElement('li');
        li.textContent = iss;
        listEl.appendChild(li);
      });
      if (listEl.children.length > 0) box.appendChild(listEl);
    }

    body.appendChild(box);
  }

  async function ensureLocalPlayableVideoUrl(rawUrl) {
    if (!rawUrl || typeof rawUrl !== 'string') return rawUrl;
    if (rawUrl.startsWith('data:video/') || rawUrl.startsWith('data:application/octet-stream')) {
      try {
        const resp = await fetch(rawUrl);
        const blob = await resp.blob();
        if (blob && blob.size > 0) {
          return URL.createObjectURL(blob.type.startsWith('video/') ? blob : new Blob([blob], { type: 'video/mp4' }));
        }
      } catch {}
    }
    return rawUrl;
  }

  function fallbackDimensionsByRatio(size) {
    if (size === '9:16') return { width: 720, height: 1280 };
    if (size === '1:1') return { width: 1024, height: 1024 };
    return { width: 1280, height: 720 };
  }

  async function extractLatestVideoInTab(options = {}) {
    const size = options?.size || '16:9';
    const [ratioW, ratioH] = String(size).split(':').map(Number);
    const expectedRatio = ratioW > 0 && ratioH > 0 ? ratioW / ratioH : 16 / 9;

    function visible(el) {
      return Boolean(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
    }
    function isFollowing(elA, elB) {
      try {
        if (!elA || !elB || !elA.compareDocumentPosition) return false;
        const mask = (typeof Node !== 'undefined' && Node.DOCUMENT_POSITION_FOLLOWING) || 4;
        return Boolean(elA.compareDocumentPosition(elB) & mask);
      } catch {
        return false;
      }
    }
    function isMascotOrNonChat(el) {
      if (!el || typeof el.closest !== 'function') return true;
      if (el.hasAttribute?.('data-hatch-avatar-layer') || el.querySelector?.('[data-hatch-avatar-layer]')) return true;
      if (el.closest('[data-hatch-avatar-layer],[data-testid*="status-panel" i],[data-testid*="avatar" i],[class*="status-panel" i],[class*="avatar-layer" i],aside,header,nav,form,[class*="chat-user-bubble"],[data-message-author-role="user"],[data-testid="hatch-composer-placeholder-overlay"]')) return true;
      if (el.getAttribute?.('aria-label') === 'Muse' || el.closest('[role="button"][aria-label="Muse"]')) return true;
      const inPresentation = Boolean(el.closest('[data-testid^="hatch-chat-attachment-presentation-"]'));
      return !inPresentation;
    }

    const presentations = [...document.querySelectorAll('[data-testid^="hatch-chat-attachment-presentation-"]')].filter(el => !isMascotOrNonChat(el));
    const rawCards = [];
    for (const pres of presentations) {
      const vids = [...pres.querySelectorAll('video')].filter(v => !isMascotOrNonChat(v));
      for (const v of vids) {
        if (v.videoWidth === 480 && v.videoHeight === 480) continue;
        rawCards.push(v);
      }
    }
    if (!rawCards.length) {
      return { ok: false, error: '当前 Muse 聊天记录中未找到已生成的分镜视频（已过滤 480×480 吉祥物动画）。' };
    }

    const userMsgs = [...document.querySelectorAll('[class*="chat-user-bubble"],[data-message-author-role="user"],[data-testid*="user-message" i]')].filter(visible);
    function findPrecedingUserMsg(el) {
      let preceding = null;
      for (const um of userMsgs) {
        if (isFollowing(um, el)) preceding = um;
      }
      return preceding;
    }

    const items = rawCards.map(video => {
      const btn = video.closest('[role="button"][aria-label]');
      const label = btn?.getAttribute('aria-label') || video.getAttribute('aria-label') || '';
      const videoUrl = video.currentSrc || video.src || '';
      const w = video.videoWidth || 0;
      const h = video.videoHeight || 0;
      const duration = Number.isFinite(video.duration) && video.duration > 0 ? Number(video.duration) : 0;
      return {
        el: video,
        label,
        videoUrl,
        width: w,
        height: h,
        duration,
        userMsg: findPrecedingUserMsg(video)
      };
    }).filter(item => Boolean(item.videoUrl) && !(item.width === 480 && item.height === 480));

    if (!items.length) {
      return { ok: false, error: '页面上还没有可收回的分镜视频。' };
    }

    const rawPrompt = String(options?.prompt || '').trim();
    const rawSceneLabel = String(options?.sceneLabel || '').trim();
    const shotMatch = rawPrompt.match(/\bshot\s*0*(\d+)\b/i)
      || rawSceneLabel.match(/(?:场景|分镜|镜头|shot)\s*0*(\d+)/i)
      || rawPrompt.match(/(?:场景|分镜|镜头)\s*0*(\d+)/i);
    const targetShotNum = shotMatch ? Number(shotMatch[1]) : 0;
    const shotRegex = targetShotNum > 0
      ? new RegExp(`(?:\\bshot\\s*0*${targetShotNum}\\b|(?:场景|分镜|镜头)\\s*0*${targetShotNum}(?!\\d)|\\b02-0*${targetShotNum}\\b)`, 'i')
      : null;
    const promptClean = rawPrompt.replace(/\s+/g, ' ').trim();
    const promptSnippet = promptClean.length >= 18 ? promptClean.slice(0, 48).toLowerCase() : '';

    let matchedItems = [];
    if (shotRegex || promptSnippet) {
      matchedItems = items.filter(item => {
        const userText = (item.userMsg?.innerText || item.userMsg?.textContent || '').replace(/\s+/g, ' ');
        const labelText = String(item.label || '');
        if (shotRegex && (shotRegex.test(userText) || shotRegex.test(labelText))) return true;
        if (promptSnippet && userText.toLowerCase().includes(promptSnippet)) return true;
        return false;
      });
    }
    if (options?.requireSceneMatch && (shotRegex || promptSnippet) && !matchedItems.length) {
      return { ok: false, error: `当前 Muse 页面未找到与分镜 ${targetShotNum || rawSceneLabel} 匹配的视频回合。` };
    }

    const anchorItem = matchedItems.length ? matchedItems[matchedItems.length - 1] : items[items.length - 1];
    const turnPool = anchorItem.userMsg
      ? items.filter(item => item.userMsg === anchorItem.userMsg)
      : (matchedItems.length ? matchedItems : items.slice(-2));

    const trimRe = /trim|cut|clip|first\d+s|mid\d+|[-_]\d+(?:\.\d+)?s(?:\b|\.mp4)/i;
    const ranked = [...(turnPool.length ? turnPool : items)].sort((a, b) => {
      const labelA = `${a.label || ''} ${a.videoUrl || ''}`;
      const labelB = `${b.label || ''} ${b.videoUrl || ''}`;
      // 最高优先级：优先抓取 10 秒完整原片（media-generation-），绝不让已加载宽高的 3 秒裁剪版排到前面
      const isRawA = /media-generation-/i.test(labelA) && !trimRe.test(labelA);
      const isRawB = /media-generation-/i.test(labelB) && !trimRe.test(labelB);
      if (isRawA !== isRawB) return isRawA ? -1 : 1;

      const isTrimA = trimRe.test(labelA);
      const isTrimB = trimRe.test(labelB);
      if (isTrimA !== isTrimB) return isTrimA ? 1 : -1;

      if (a.duration > 0 && b.duration > 0 && Math.abs(a.duration - b.duration) > 0.4) {
        return b.duration - a.duration;
      }
      const hasDimA = Boolean(a.width && a.height);
      const hasDimB = Boolean(b.width && b.height);
      if (hasDimA && hasDimB) {
        const scoreA = Math.abs(Math.log((a.width / a.height) / expectedRatio));
        const scoreB = Math.abs(Math.log((b.width / b.height) / expectedRatio));
        if (Math.abs(scoreA - scoreB) > 0.03) return scoreA - scoreB;
      } else if (hasDimA !== hasDimB) {
        return hasDimA ? -1 : 1;
      }
      return isFollowing(a.el, b.el) ? -1 : 1;
    });

    const best = ranked[0] || anchorItem;
    let reviewNotes = '';
    try {
      const bubbles = [...document.querySelectorAll('div[class*="hatch-chat-groupable-bubble"],[data-message-author-role="assistant"]')]
        .filter(b => visible(b) && !b.closest('[class*="chat-user-bubble"],[data-message-author-role="user"]') && (!anchorItem.userMsg || isFollowing(anchorItem.userMsg, b)));
      reviewNotes = bubbles.map(b => (b.innerText || b.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean).join('\n').slice(-2000);
    } catch {}

    let finalUrl = best.videoUrl;
    if (finalUrl.startsWith('blob:')) {
      const resp = await fetch(finalUrl);
      if (!resp.ok) throw new Error(`读取 Muse 视频流失败 (HTTP ${resp.status})`);
      const blob = await resp.blob();
      finalUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error || new Error('视频流转码失败'));
        reader.readAsDataURL(blob);
      });
    }

    return {
      ok: true,
      url: finalUrl,
      width: best.width || 1280,
      height: best.height || 720,
      duration: best.duration || 10,
      label: best.label || '',
      reviewNotes
    };
  }

  async function runDirectVideoRecovery(options = {}) {
    const tabs = await chrome.tabs.query({ url: ['https://muse.ai/*', 'https://*.muse.ai/*'] });
    if (!tabs.length) throw new Error('请先打开 Muse.ai 聊天标签页。');
    if (preferredMuseTabId) {
      const idx = tabs.findIndex(t => t.id === preferredMuseTabId);
      if (idx > 0) tabs.unshift(tabs.splice(idx, 1)[0]);
    }
    let lastErr = '';
    for (const tab of tabs) {
      if (!tab.id) continue;
      try {
        const results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: extractLatestVideoInTab,
          args: [options]
        });
        const res = results?.[0]?.result;
        if (res?.ok && res?.url) {
          preferredMuseTabId = tab.id;
          return res;
        }
        lastErr = res?.error || '未找到可收回的视频';
      } catch (err) {
        lastErr = err?.message || String(err);
      }
    }
    throw new Error(lastErr || '未能从 Muse 页面提取到有效视频。');
  }

  async function recoverVideoFromMuse(nodeId, extraOptions = {}) {
    const n = nodeById(nodeId);
    if (!n) return;
    setRunStatus(`正在尝试从 Muse.ai 页面重新检索最新生成的视频素材…`, 'warn');
    try {
      const reply = await runDirectVideoRecovery({
        size: n.data.size || '16:9',
        duration: n.data.duration || 0,
        prompt: resolvePrompt(n.id) || '',
        sceneLabel: n.data.sceneLabel || '',
        ...extraOptions
      });
      if (!reply?.ok || !reply?.url) {
        throw new Error(reply?.error || "未能从 Muse 页面自动提取到有效视频附件，请确认 Muse.ai 是否已完全渲染完毕。");
      }
      const url = await ensureLocalPlayableVideoUrl(reply.url);
      const reviewNotes = reply.reviewNotes || '';
      const intrinsic = await mediaDimensions(url, 'video', 6000);
      const fbDim = fallbackDimensionsByRatio(n.data.size);
      const width = intrinsic.width || Number(reply.width) || fbDim.width;
      const height = intrinsic.height || Number(reply.height) || fbDim.height;
      const duration = intrinsic.duration || Number(reply.duration) || 10;
      ensureNodeVersions(n);
      if (Array.isArray(n.data.versions)) {
        n.data.versions = n.data.versions.filter(v => !(v.width === 480 && v.height === 480));
        n.data.versions.forEach((v, idx) => {
          v.versionNumber = idx + 1;
          v.name = `版本 ${idx + 1}`;
        });
      }
      const qualityReport = inspectMediaQuality({
        url,
        kind: 'video',
        width,
        height,
        duration,
        size: n.data.size,
        isVideo: true,
        requestedDuration: n.data.duration,
        reviewNotes
      });
      const newVerNumber = (n.data.versions?.length || 0) + 1;
      const newVerId = uid('ver');
      let endFrame = null;
      try { endFrame = await extractVideoEndFrame(url); } catch {}
      const expectedRatio = ratioValue(n.data.size);
      const actualRatio = width && height ? width / height : 0;
      const sizeMismatch = Boolean(actualRatio && expectedRatio && Math.abs(Math.log(actualRatio / expectedRatio)) > 0.09);
      const newVersion = {
        id: newVerId,
        versionNumber: newVerNumber,
        name: `版本 ${newVerNumber}`,
        kind: 'video',
        url,
        model: n.data.model || 'muse-video',
        prompt: resolvePrompt(n.id) || '',
        createdAt: Date.now(),
        width,
        height,
        duration,
        candidates: [{ id: uid('cand'), url }],
        endFrame,
        reviewNotes,
        quality: qualityReport
      };
      n.data.versions.push(newVersion);
      n.data.activeVersionId = newVerId;
      n.data.asset = {
        id: newVerId,
        kind: 'video',
        url,
        name: `视频 ${n.id} (V${newVerNumber})`,
        sourceNodeId: n.id,
        versionNumber: newVerNumber,
        width,
        height,
        duration,
        requestedSize: n.data.size,
        sizeMismatch,
        quality: qualityReport
      };
      n.data.endFrame = endFrame;
      n.data.candidates = [{ id: uid('cand'), url }];
      n.data.status = 'success';
      n.data.dirty = false;
      n.data.error = '';
      n.data.reviewNotes = reviewNotes;

      state.edges.filter(edge => edge.source === n.id).forEach(edge => {
        const target = nodeById(edge.target);
        if (target?.type === 'preview') target.data.asset = n.data.asset;
      });
      render();
      scheduleAutoSave();
      setRunStatus(`成功从 Muse 恢复并装配视频资产（V${newVerNumber}）！已回显质检与审核问题。`, 'ok');
    } catch (e) {
      setRunStatus(`恢复视频失败：${e.message}`, 'error');
      alert(`无法自动抓取：${e.message}`);
    }
  }


    function handleLocalImageUpload(nodeId, file) {
    const n = nodeById(nodeId);
    if (!n || !file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target.result;
      ensureNodeVersions(n);
      const nextVerNumber = (n.data.versions && n.data.versions.length
        ? Math.max(...n.data.versions.map(v => Number(v.versionNumber) || 1))
        : 0) + 1;
      const vId = uid("ver");

      const img = new Image();
      img.onload = () => {
        const width = img.naturalWidth || 1024;
        const height = img.naturalHeight || 1792;
        const newVer = {
          id: vId,
          versionNumber: nextVerNumber,
          name: `本地导入: ${file.name}`,
          kind: "image",
          url: dataUrl,
          model: "local-upload",
          prompt: n.data.prompt || "",
          createdAt: Date.now(),
          width,
          height,
          quality: { status: "passed", issues: [], checkedAt: Date.now() },
          selected: true
        };
        n.data.versions.forEach(v => v.selected = false);
        n.data.versions.push(newVer);
        n.data.activeVersionId = vId;
        n.data.asset = {
          id: vId,
          versionNumber: nextVerNumber,
          kind: "image",
          name: file.name,
          url: dataUrl,
          width,
          height,
          quality: newVer.quality
        };
        n.data.status = "completed";

        markNodeDirty(n.id);
        render();
        scheduleAutoSave();
        setRunStatus(`成功导入本地图片【${file.name}】（已激活为 V${nextVerNumber}，已直通下游视频）`, "ok");
      };
      img.src = dataUrl;
    };
    reader.readAsDataURL(file);
  }

function renderNodeVersionBar(n, body) {
    ensureNodeVersions(n);
    if (!n.data.versions || !n.data.versions.length) return;
    const bar = document.createElement('div');
    bar.className = 'node-version-bar';

    const leftGroup = document.createElement('div');
    leftGroup.style.display = 'flex';
    leftGroup.style.alignItems = 'center';
    leftGroup.style.gap = '4px';

    const label = document.createElement('span');
    label.textContent = '版本:';
    label.style.color = 'var(--text-muted)';

    const select = document.createElement('select');
    select.className = 'node-version-select';
    n.data.versions.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.id;
      const qStatus = v.quality?.status === 'passed' ? '✓合格' : v.quality?.status === 'rejected' ? '✕异常' : v.quality?.status === 'warning' ? '⚠存疑' : '●未检';
      const verNum = v.versionNumber || (v.version ? String(v.version).replace(/\D+/g, "") : "") || 1;
      opt.textContent = `V${verNum} (${qStatus})`;
      if (v.id === n.data.activeVersionId) opt.selected = true;
      select.appendChild(opt);
    });
    select.onchange = (e) => {
      e.stopPropagation();
      switchNodeVersion(n.id, select.value);
    };
    leftGroup.append(label, select);

    const currentVer = n.data.versions.find(v => v.id === n.data.activeVersionId) || n.data.versions[0];
    const qBadge = document.createElement('span');
    const qStat = currentVer?.quality?.status || 'unchecked';
    qBadge.className = `quality-badge ${qStat}`;
    if (qStat === 'passed') {
      qBadge.textContent = '✓ 质检合格';
      qBadge.title = '尺寸与画幅正常（点击可切换为需补做）';
    } else if (qStat === 'rejected') {
      qBadge.textContent = '✕ 质检异常';
      qBadge.title = `${currentVer?.quality?.issues?.join('；') || '质量不合格'}（点击可标记为合格）`;
    } else if (qStat === 'warning') {
      qBadge.textContent = '⚠ 比例存疑';
      qBadge.title = `${currentVer?.quality?.issues?.join('；') || '比例与预期偏差较大'}（点击可切换）`;
    } else {
      qBadge.textContent = '● 待质检';
      qBadge.title = '尚未执行质检（点击可标记合格）';
    }
    qBadge.onclick = (e) => {
      e.stopPropagation();
      toggleQualityStatus(n.id, currentVer.id);
    };

    const retakeBtn = document.createElement('button');
    retakeBtn.type = 'button';
    retakeBtn.className = 'node-retake-btn';
    retakeBtn.textContent = '↺ 补做';
    retakeBtn.title = '补做此镜头：仅重新运行本节点生成新版本，旧版本保留';
    retakeBtn.onclick = (e) => {
      e.stopPropagation();
      runSingleNode(n.id);
    };

        let uploadBtn = null;
    if (n.type === "generateImage") {
      uploadBtn = document.createElement("button");
      uploadBtn.type = "button";
      uploadBtn.className = "node-upload-btn";
      uploadBtn.textContent = "📁 换本地图";
      uploadBtn.title = "从电脑中直接选择图片替换此镜底图，自动保存为新版本并直通视频";

      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = "image/*";
      fileInput.style.display = "none";
      fileInput.onchange = (e) => {
        const file = e.target.files?.[0];
        if (file) handleLocalImageUpload(n.id, file);
        fileInput.value = "";
      };
      uploadBtn.appendChild(fileInput);
      uploadBtn.onclick = (e) => {
        e.stopPropagation();
        fileInput.click();
      };
    } else if (n.type === "generateVideo") {
      uploadBtn = document.createElement("button");
      uploadBtn.type = "button";
      uploadBtn.className = "node-upload-btn";
      uploadBtn.textContent = "⚡ 重抓";
      uploadBtn.title = "不消耗额度：直接从当前 Muse 页面重新抓取本镜最新生成的视频";
      uploadBtn.onclick = (e) => {
        e.stopPropagation();
        recoverVideoFromMuse(n.id);
      };
    }

    if (uploadBtn) {
      bar.append(leftGroup, qBadge, uploadBtn, retakeBtn);
    } else {
      bar.append(leftGroup, qBadge, retakeBtn);
    }
    body.appendChild(bar);
  }

  function renderNode(n) {
    const el = document.createElement('section');
    el.className = `node ${['generateImage','generateVideo'].includes(n.type) ? 'generate' : ''} ${n.type==='prompt'?'prompt-node':''} ${n.type==='timeline'?'timeline-node':''} ${state.selectedNodeIds.includes(n.id)||state.selectedNodeId===n.id ? 'selected' : ''}`;
    el.dataset.id = n.id;
    el.style.left = `${n.x}px`;
    el.style.top = `${n.y}px`;
    if (n.type === "generateImage") {
      el.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.stopPropagation();
        el.classList.add("drag-hover-upload");
      });
      el.addEventListener("dragleave", (e) => {
        e.preventDefault();
        e.stopPropagation();
        el.classList.remove("drag-hover-upload");
      });
      el.addEventListener("drop", (e) => {
        e.preventDefault();
        e.stopPropagation();
        el.classList.remove("drag-hover-upload");
        const file = e.dataTransfer?.files?.[0];
        if (file && file.type.startsWith("image/")) {
          handleLocalImageUpload(n.id, file);
        }
      });
    }
    const head = document.createElement('div');
    head.className = 'node-header';
    const title=document.createElement('span');
    title.textContent=`${nodeDefs[n.type].title}${n.data.sceneLabel?` · ${n.data.sceneLabel}`:''}`;
    title.title=title.textContent;
    if (n.data.sceneSource) {
      const srcBadge = document.createElement('span');
      srcBadge.className = `scene-source-badge ${n.data.sceneSource.type}`;
      srcBadge.textContent = n.data.sceneSource.type === 'local_ai' ? `🤖 ${n.data.sceneSource.model || '本地AI'}` : '⚡ 规则编排';
      srcBadge.title = `分镜编排来源：${n.data.sceneSource.type === 'local_ai' ? '本地大模型' : '规则引擎'}`;
      title.appendChild(srcBadge);
    }
    const close=document.createElement('span');close.className='node-close';close.title="删除";close.textContent='×';head.append(title,close);
    head.querySelector('.node-close').onclick = (e) => { e.stopPropagation(); removeNode(n.id); };
    setupDrag(head, n, el);
    el.appendChild(head);

    const body = document.createElement('div');
    body.className = 'node-body';

    if (['prompt','negativePrompt','textAppend'].includes(n.type)) {
      const ta = document.createElement('textarea');
      ta.value = n.data.text || n.data.prompt || n.data.value || '';
      ta.oninput = () => { n.data.text = ta.value; markNodeDirty(n.id); };
      body.appendChild(ta);
      if (n.type === 'prompt') {
        body.appendChild(createCardAiController(n, ta));
      }
      if(n.type==='negativePrompt'){const hint=document.createElement('div');hint.className='hint';hint.textContent="连接到图片或视频节点的“反向提示词”输入端口。";body.appendChild(hint);}
      if(n.type==='textAppend'){const hint=document.createElement('div');hint.className='hint';hint.textContent="将此文本追加到传入的提示词后。";body.appendChild(hint);}
    }

    if(n.type==='textConcat'){
      const separator=document.createElement('input');separator.value=n.data.separator??', ';separator.placeholder="分隔符";separator.oninput=()=>n.data.separator=separator.value;body.append("合并文本时使用以下分隔符：",separator);
      separator.oninput = () => { n.data.separator = separator.value; markNodeDirty(n.id); };
    }

    if (n.type === 'imageInput') {
      const imgSrc = n.data.localDataUrl || n.data.url || n.data.asset?.url;
      if (imgSrc) {
        const img = document.createElement('img'); img.src = imgSrc; body.appendChild(img);
      } else {
        const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = "尚未选择图片"; body.appendChild(empty);
      }
      const label = document.createElement('label');
      label.className = 'small-btn'; label.textContent = "选择图片";
      const input = document.createElement('input'); input.type = 'file'; input.accept = 'image/*';
      input.onchange = () => {
        const f = input.files && input.files[0]; if (!f) return;
        const r = new FileReader(); r.onload = () => { n.data.localDataUrl = String(r.result || ''); markNodeDirty(n.id); render(); }; r.readAsDataURL(f);
      };
      label.appendChild(input); body.appendChild(label);
      const hint = document.createElement('div'); hint.className = 'hint'; hint.textContent = "将此图片连接到“生成图片”的“参考图片”端口。"; body.appendChild(hint);
    }

    if(n.type==='references'){
      const incoming=(nodeDefs.references.inputs||[]).reduce((count,input)=>count+getIncoming(n.id,input.id).length,0),badge=document.createElement('span');badge.className='ref-badge';badge.textContent=`${incoming} 个图片来源 已连接`;body.appendChild(badge);
      const list=document.createElement('div');list.className='references-input-list';(nodeDefs.references.inputs||[]).forEach(input=>{const row=document.createElement('div');row.textContent=`${input.label} · 连接图片来源`;list.appendChild(row);});body.appendChild(list);
      const hint=document.createElement('div');hint.className='hint';hint.textContent="所有接入的图片都会发送给与此节点相连的“生成图片”和“生成视频”节点。";body.appendChild(hint);
    }

    if (n.type === 'generateImage') {
      const voBox = document.createElement('div');
      voBox.className = 'vo-script-box';
      const roleType = n.data.frameRole || (/end|尾帧|尾图/i.test(`${n.id} ${n.data.sceneLabel || ''}`) ? 'end' : 'start');
      const shotNum = Number(n.data.shotNumber) || 0;
      const voLabel = document.createElement('div');
      voLabel.className = 'vo-script-label';
      voLabel.innerHTML = `<span>🎙️ ${shotNum ? `第${String(shotNum).padStart(2, '0')}镜` : '本镜'}对应口播文案</span><span class="frame-role-badge ${roleType}">${roleType === 'end' ? '尾帧 End' : '首帧 Start'}</span>`;
      const voInput = document.createElement('input');
      voInput.type = 'text';
      voInput.className = 'vo-script-input';
      voInput.placeholder = '输入本镜对应的口播台词（导出与剪辑时自动按此命名）';
      voInput.value = n.data.voText || '';
      voInput.onpointerdown = e => e.stopPropagation();
      voInput.oninput = () => {
        n.data.voText = voInput.value;
        if (shotNum > 0) {
          state.nodes.forEach(other => {
            if (Number(other.data?.shotNumber) === shotNum) other.data.voText = voInput.value;
          });
        }
        scheduleAutoSave();
      };
      voBox.append(voLabel, voInput);
      body.appendChild(voBox);

      const controls = document.createElement('div'); controls.className = 'gen-controls';
      const size = document.createElement('select');
      [['1:1',"正方形"],['16:9',"横向 16:9"],['9:16',"纵向 9:16"],['4:3',"横向 4:3"],['3:4',"纵向 3:4"]].forEach(([v,label]) => { const o=document.createElement('option'); o.value=v; o.textContent=label; size.appendChild(o); });
      size.value = ['1:1','16:9','9:16','4:3','3:4'].includes(n.data.size)?n.data.size:'1:1';
      size.onchange = () => { n.data.size = size.value; markNodeDirty(n.id); };

      const countSelect = document.createElement('select');
      countSelect.className = 'count-select';
      countSelect.title = "生成张数（可一次生成多张候选参考图）";
      [['1', "1 张"], ['2', "2 张候选图"], ['4', "4 张候选图"]].forEach(([v, label]) => {
        const o = document.createElement('option'); o.value = v; o.textContent = label; countSelect.appendChild(o);
      });
      countSelect.value = String(n.data.count || 1);
      countSelect.onchange = () => { n.data.count = Number(countSelect.value); markNodeDirty(n.id); scheduleAutoSave(); };

      const modelSelect = document.createElement('select');
      modelSelect.className = 'model-select';
      modelSelect.title = "选择或自定义生图模型";
      const availableModels = getAvailableImageModels();
      const currentModel = n.data.model || state.settings?.defaultImageModel || 'muse-image';
      if (!availableModels.some(m => m.id === currentModel)) {
        const customOpt = document.createElement('option');
        customOpt.value = currentModel;
        customOpt.textContent = `${currentModel} (自定义)`;
        modelSelect.appendChild(customOpt);
      }
      availableModels.forEach(m => {
        const o = document.createElement('option');
        o.value = m.id;
        o.textContent = m.name;
        modelSelect.appendChild(o);
      });
      const addOpt = document.createElement('option');
      addOpt.value = '__add_custom__';
      addOpt.textContent = '＋ 自定义模型...';
      modelSelect.appendChild(addOpt);
      const cfgOpt = document.createElement('option');
      cfgOpt.value = '__open_settings__';
      cfgOpt.textContent = '⚙ 配置本地 API 与端口...';
      modelSelect.appendChild(cfgOpt);
      modelSelect.value = currentModel;

      modelSelect.onchange = () => {
        if (modelSelect.value === '__open_settings__') {
          syncSettingsUI();
          $('#settingsModal').classList.remove('hidden');
          modelSelect.value = n.data.model || 'muse-image';
          return;
        }
        if (modelSelect.value === '__add_custom__') {
          const customName = window.prompt("请输入你自己的生图模型名称（例如 flux-1-dev, kolors, custom-sdxl 等）：", "");
          if (customName && customName.trim()) {
            const clean = customName.trim();
            addCustomImageModel(clean);
            n.data.model = clean;
            markNodeDirty(n.id);
            render();
          } else {
            modelSelect.value = n.data.model || 'muse-image';
          }
          return;
        }
        n.data.model = modelSelect.value;
        markNodeDirty(n.id);
        scheduleAutoSave();
      };

      const modelRow = document.createElement('div');
      modelRow.className = 'node-model-row';
      const apiBtn = document.createElement('button');
      apiBtn.type = 'button';
      apiBtn.className = 'node-api-btn';
      apiBtn.textContent = '⚙ API';
      apiBtn.title = '配置本地 API 地址与模型列表';
      apiBtn.onclick = (e) => {
        e.stopPropagation();
        syncSettingsUI();
        $('#settingsModal').classList.remove('hidden');
      };
      modelRow.append(modelSelect, apiBtn);

      controls.append(size, countSelect);
      body.append(controls, modelRow);

      const styleContinuityLabel = document.createElement('label');
      styleContinuityLabel.className = 'continuity-toggle';
      styleContinuityLabel.htmlFor = `style-continuity-${n.id}`;
      styleContinuityLabel.onpointerdown = event => event.stopPropagation();
      const styleToggle = document.createElement('input');
      styleToggle.id = `style-continuity-${n.id}`;
      styleToggle.type = 'checkbox';
      styleToggle.checked = Boolean(n.data.styleContinuity);
      styleToggle.onchange = () => { n.data.styleContinuity = styleToggle.checked; markNodeDirty(n.id); scheduleAutoSave(); };
      styleContinuityLabel.append(styleToggle, document.createTextNode("参考前序图片画风（防止画风走偏）"));
      body.appendChild(styleContinuityLabel);

      const isDirtySuccess = n.data.status === 'success' && n.data.dirty;
      const st = document.createElement('div');
      st.className = `status ${isDirtySuccess ? 'dirty' : (n.data.status || 'idle')}`;
      st.textContent = isDirtySuccess ? `已就绪 · 已修改（待重新生成）${n.data.error ? ' · ' + n.data.error : ''}` : `${statusText(n.data.status)}${n.data.error ? ' · ' + n.data.error : ''}`;
      body.appendChild(st);
      renderNodeVersionBar(n, body);
      renderReviewEchoBox(n, body);
      if(n.data.asset?.width&&n.data.asset?.height){const dimensions=document.createElement('div');dimensions.className=`hint ${n.data.asset.sizeMismatch?'error':''}`;dimensions.textContent=`请求比例：${n.data.asset.requestedSize||n.data.size} · 实际：${n.data.asset.width} × ${n.data.asset.height}${n.data.asset.sizeMismatch?"（Muse 返回的比例不同）":''}`;body.appendChild(dimensions);}
      if (n.data.candidates && n.data.candidates.length > 1) {
        const grid = document.createElement('div');
        grid.className = 'candidates-grid';
        n.data.candidates.forEach((cand, idx) => {
          const thumbWrap = document.createElement('div');
          thumbWrap.className = `candidate-thumb ${idx === (n.data.selectedCandidateIndex || 0) ? 'selected' : ''}`;
          thumbWrap.title = `点击设为主图资产（候选图 ${idx + 1}）`;
          const thumbImg = document.createElement('img');
          thumbImg.src = cand.url;
          thumbWrap.appendChild(thumbImg);
          thumbWrap.onclick = (e) => {
            e.stopPropagation();
            n.data.selectedCandidateIndex = idx;
            if (n.data.asset) {
              n.data.asset.url = cand.url;
              state.edges.filter(edge => edge.source === n.id).forEach(edge => {
                const target = nodeById(edge.target);
                if (target?.type === 'preview') target.data.asset = n.data.asset;
              });
            }
            render();
            scheduleAutoSave();
          };
          grid.appendChild(thumbWrap);
        });
        body.appendChild(grid);
        const hint = document.createElement('div'); hint.className = 'candidates-hint'; hint.textContent = `已生成 ${n.data.candidates.length} 张候选参考图（点击挑选主图）`; body.appendChild(hint);
      } else if (n.data.asset?.url) {
        const a=document.createElement('a'); a.href=n.data.asset.url; a.target='_blank'; a.className='image-link'; const img=document.createElement('img'); img.src=n.data.asset.url; a.appendChild(img); body.appendChild(a);
      }
      const promptCount=getIncoming(n.id,'prompt').length;if(promptCount>1){const b=document.createElement('span');b.className='ref-badge';b.textContent=`${promptCount} 个提示词来源已合并`;body.appendChild(b);}
      const referenceCount=getIncoming(n.id,'reference').length;if(referenceCount){const b=document.createElement('span');b.className='ref-badge';b.textContent=`${referenceCount} 张参考图片 已连接`;body.appendChild(b);}
      body.appendChild(createNodeRunButton(n));
    }

    if(n.type==='generateVideo'){
      const shotNum = Number(n.data.shotNumber) || 0;
      const voBox = document.createElement('div');
      voBox.className = 'vo-script-box';
      const editSec = Number(n.data.editDuration) || 3.5;
      const voLabel = document.createElement('div');
      voLabel.className = 'vo-script-label';
      voLabel.innerHTML = `<span>🎙️ ${shotNum ? `第${String(shotNum).padStart(2, '0')}镜` : '本镜'}对应口播文案</span><span class="frame-role-badge start">原片 10s · 成片参考 ${editSec}s</span>`;
      const voInput = document.createElement('input');
      voInput.type = 'text';
      voInput.className = 'vo-script-input';
      voInput.placeholder = '输入本镜对应的口播台词（导出 MP4 时直接作为文件名）';
      voInput.value = n.data.voText || '';
      voInput.onpointerdown = e => e.stopPropagation();
      voInput.oninput = () => {
        n.data.voText = voInput.value;
        if (shotNum > 0) {
          state.nodes.forEach(other => {
            if (Number(other.data?.shotNumber) === shotNum) other.data.voText = voInput.value;
          });
        }
        scheduleAutoSave();
      };
      voBox.append(voLabel, voInput);
      body.appendChild(voBox);

      const controls=document.createElement('div');controls.className='gen-controls video-controls';
      const ratio=document.createElement('select');[['16:9',"横向 16:9"],['9:16',"纵向 9:16"],['1:1',"正方形"]].forEach(([v,label])=>{const o=document.createElement('option');o.value=v;o.textContent=label;ratio.appendChild(o);});ratio.value=['16:9','9:16','1:1'].includes(n.data.size)?n.data.size:'16:9';ratio.onchange=()=>n.data.size=ratio.value;
      ratio.onchange = () => { n.data.size = ratio.value; markNodeDirty(n.id); };
      const duration=document.createElement('select');
      const durOptions = [...new Set([2, 3, 4, 5, 6, 8, 10, Number(n.data.duration) || 5].filter(v => v > 0))].sort((a, b) => a - b);
      durOptions.forEach(v=>{const o=document.createElement('option');o.value=String(v);o.textContent=`${v} 秒`;duration.appendChild(o);});
      duration.value=String(n.data.duration||5);
      duration.onchange = () => { n.data.duration = Number(duration.value); markNodeDirty(n.id); };
      controls.append(ratio,duration);body.appendChild(controls);
      const continuityLabel=document.createElement('label');continuityLabel.className='continuity-toggle';continuityLabel.htmlFor=`continuity-${n.id}`;continuityLabel.onpointerdown=event=>event.stopPropagation();const continuity=document.createElement('input');continuity.id=`continuity-${n.id}`;continuity.type='checkbox';continuity.checked=Boolean(n.data.continuity);continuity.onchange=()=>{n.data.continuity=continuity.checked;scheduleAutoSave();};continuityLabel.append(continuity,document.createTextNode("使用上一片段的尾帧作为起始参考图"));body.appendChild(continuityLabel);
      continuity.onchange = () => { n.data.continuity = continuity.checked; markNodeDirty(n.id); scheduleAutoSave(); };
      if(n.data.endFrame?.url){const frame=document.createElement('img');frame.className='end-frame-thumb';frame.src=n.data.endFrame.url;frame.alt="已提取用于连续生成的尾帧";frame.title="视频尾帧 · 将“尾帧”连接到下一个视频的“参考图片”端口";body.appendChild(frame);}
      const isVideoDirtySuccess = n.data.status === 'success' && n.data.dirty;
      const status=document.createElement('div');status.className=`status ${isVideoDirtySuccess ? 'dirty' : (n.data.status||'idle')}`;status.textContent=isVideoDirtySuccess ? `已就绪 · 已修改（待重新生成）${n.data.error?' · '+n.data.error:''}` : `${statusText(n.data.status)}${n.data.error?' · '+n.data.error:''}`;body.appendChild(status);
      renderNodeVersionBar(n, body);
      renderReviewEchoBox(n, body);
      if(n.data.asset?.width&&n.data.asset?.height){const dimensions=document.createElement('div');dimensions.className=`hint ${n.data.asset.sizeMismatch?'error':''}`;dimensions.textContent=`请求比例：${n.data.asset.requestedSize||n.data.size} · 实际：${n.data.asset.width} × ${n.data.asset.height}${n.data.asset.sizeMismatch?"（Muse 返回的比例不同）":''}`;body.appendChild(dimensions);}
      const resolvedRefs = resolveReferences(n.id);
      const hasStartRef = resolvedRefs.some(r => r.role === 'start');
      const hasEndRef = resolvedRefs.some(r => r.role === 'end');
      if (resolvedRefs.length > 0) {
        const lockBadge = document.createElement('div');
        lockBadge.className = 'keyframe-lock-badge';
        lockBadge.textContent = hasStartRef && hasEndRef
          ? `🎯 首帧+尾帧双锁 · 已串联 ${resolvedRefs.length}/9 张参考图`
          : `🖼 首帧已锁 · 已串联 ${resolvedRefs.length}/9 张参考图`;
        body.appendChild(lockBadge);
      }
      const incomingShotEndNode = getIncoming(n.id, 'reference').map(e => nodeById(e.source)).find(s => s && (s.data?.frameRole === 'end' || /end|尾帧|尾图/i.test(`${s.id} ${s.data?.sceneLabel || ''}`)));
      if (!incomingShotEndNode) {
        const addEndFrameBtn = document.createElement('button');
        addEndFrameBtn.type = 'button';
        addEndFrameBtn.className = 'video-timeline-drag';
        addEndFrameBtn.textContent = '➕ 补建本镜【尾帧图】节点并自动连线';
        addEndFrameBtn.title = '为当前镜头自动生成配套的【尾帧生图词 + 尾帧生成图片】节点，并连入此视频节点形成首尾帧双锁';
        addEndFrameBtn.onclick = event => {
          event.stopPropagation();
          ensureEndFrameNodeForVideo(n.id);
        };
        body.appendChild(addEndFrameBtn);
      }
      if(n.data.asset?.url){const video=document.createElement('video');video.controls=true;video.preload='metadata';video.src=n.data.asset.url;body.appendChild(video);}
      const recoverDirectBtn=document.createElement('button');recoverDirectBtn.type='button';recoverDirectBtn.className='video-timeline-drag';recoverDirectBtn.textContent="⚡ 从 Muse 页面抓取最新视频（10s 原片）";recoverDirectBtn.title="不消耗积分：直接将 Muse 聊天页已生成的最新 10 秒完整原片拉回此节点";recoverDirectBtn.onclick=event=>{event.stopPropagation();recoverVideoFromMuse(n.id);};body.appendChild(recoverDirectBtn);
      const timelineDrag=document.createElement('button');timelineDrag.type='button';timelineDrag.className='video-timeline-drag';timelineDrag.draggable=true;timelineDrag.innerHTML="<span aria-hidden=\"true\">⠿</span> 将输出拖到时间线";timelineDrag.title="将此输出拖到时间线";timelineDrag.ondragstart=event=>{event.dataTransfer.setData('application/x-museflow-video-node',n.id);event.dataTransfer.setData('text/plain',n.id);event.dataTransfer.effectAllowed='copy';};timelineDrag.onclick=event=>{event.stopPropagation();addTimelineClip(ensureDockTimeline(),n.id);};body.appendChild(timelineDrag);
      body.appendChild(createNodeRunButton(n));
    }
    if(n.type==='timeline')renderTimelineBody(n,body);

    if(n.type==='imageResize'){
      const incoming=sourceFor(getIncoming(n.id,'image')[0]);
      const imageUrl=incoming?.data?.localDataUrl||incoming?.data?.asset?.url||'';
      const width=document.createElement('input');width.type='number';width.min='1';width.max='4096';width.value=n.data.width||1024;width.title="宽度";width.oninput=()=>n.data.width=clampDimension(width.value);
      const height=document.createElement('input');height.type='number';height.min='1';height.max='4096';height.value=n.data.height||1024;height.title="高度";height.oninput=()=>n.data.height=clampDimension(height.value);
      const fit=document.createElement('select');[['cover',"裁剪填满"],['contain',"完整适应"],['stretch',"拉伸"]].forEach(([v,label])=>{const o=document.createElement('option');o.value=v;o.textContent=label;fit.appendChild(o);});fit.value=n.data.fit||'cover';fit.onchange=()=>n.data.fit=fit.value;
      body.append(width,height,fit);
      const out=document.createElement('canvas');out.className='resize-preview';
      if(imageUrl){const image=new Image();image.onload=()=>drawResized(image,out,n.data);image.src=imageUrl;}
      body.appendChild(out);
      const download=document.createElement('button');download.type='button';download.className='small-btn';download.textContent="下载调整后的图片";download.disabled=!imageUrl;download.onclick=()=>{out.toBlob(blob=>{if(!blob)return;const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`museflow-${n.data.width}x${n.data.height}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);});};body.appendChild(download);
    }

    if (n.type === 'preview') {
      if (n.data.asset?.url) { if(n.data.asset.kind==='video'){const video=document.createElement('video');video.controls=true;video.src=n.data.asset.url;body.appendChild(video);}else{const a=document.createElement('a');a.href=n.data.asset.url;a.target='_blank';const img=document.createElement('img');img.src=n.data.asset.url;a.appendChild(img);body.appendChild(a);} }
      else { const empty=document.createElement('div'); empty.className='empty preview-empty'; empty.textContent="运行工作流"; body.appendChild(empty); }
    }

    el.appendChild(body);
    addPorts(el, n);
    el.onmousedown = event => {if(event.target.closest('button,input,textarea,select,.port,.node-header'))return;selectNode(n.id,{toggle:event.shiftKey||event.ctrlKey||event.metaKey});};
    return el;
  }

  function createNodeRunButton(node){
    const button=document.createElement('button');button.type='button';button.className='node-run-button primary';
    if(node.data.status==='running'){
      button.classList.add('stop');button.textContent="■ 停止";button.disabled=false;button.title="停止本次生成";button.dataset.stopGeneration=node.id;
    }else{
      button.textContent=`▶ 生成${node.type==='generateVideo'?"视频":"图片"}`;button.disabled=state.isRunning;
      button.onclick=event=>{event.stopPropagation();runSingleNode(node.id);};
    }
    return button;
  }

  function addPorts(el, n) {
    const def = nodeDefs[n.type];
    (def.inputs || []).forEach((p, i) => {
      const y = ['generateImage','generateVideo'].includes(n.type) ? 52+i*26 : n.type==='timeline'?58+i*42:68+i*42;
      const port = document.createElement('div'); port.className='port in'; port.dataset.node=n.id; port.dataset.port=p.id;port.dataset.type=p.type; port.style.top=`${y}px`; port.title=`输入：${p.label} (${p.type})`;
      if(p.type==='text'||p.type==='negative')port.onpointerdown=e=>startWireFromInput(e,n.id,p.id,p.type);
      port.ondragover=e=>{if(state.connectingFrom&&portCompatible(state.connectingFrom,n.id,p.id)){e.preventDefault();port.classList.add('wire-compatible');}};
      port.onclick = (e) => { e.stopPropagation(); if(state.suppressPortClick)return; if(state.connectingFrom)connect(n.id,p.id); else setRunStatus("先选择兼容的输出端口，再点击此输入端口。",'warn'); };
      const label=document.createElement('span'); label.className='port-label left'; label.style.top=`${y-1}px`; const count=isMultiInput(n.type,p.id)?getIncoming(n.id,p.id).length:0;label.textContent=count?`${p.label} · ${count}`:p.label;if(count)port.title=p.id==='prompt'?`提示词来源（${count} 已连接）`:`参考图片（${count} 已连接）`;el.append(label,port);
    });
    (def.outputs || []).forEach((p, i) => {
      const y = ['prompt','negativePrompt','textAppend'].includes(n.type) ? 80 : n.type==='generateVideo'?82+i*30:['imageInput','generateImage'].includes(n.type)?82:66+i*42;
      const port=document.createElement('div'); port.className='port out'; port.dataset.node=n.id; port.dataset.port=p.id;port.dataset.type=p.type; port.style.top=`${y}px`; port.title=`输出：${p.label} (${p.type})`;
      port.onpointerdown=e=>startWire(e,n.id,p.id);
      if(n.type==='generateVideo'){port.classList.add('video-output-port');port.title=p.id==='endFrame'?"将此尾帧连接到下一个视频的参考图片输入端口":"将视频输出连接到时间线或其他兼容输入端口";}
      port.onmousedown=e=>{if(e.button===0){e.stopPropagation();state.connectingFrom={nodeId:n.id,portId:p.id};setRunStatus(`正在连接 ${p.type}：请点击兼容的输入端口。`,'warn');}};
      port.onclick=(e)=>{e.stopPropagation();if(state.suppressPortClick)return;if(!state.draggingWire){state.connectingFrom={nodeId:n.id,portId:p.id};setRunStatus(`正在连接 ${p.type}：请点击兼容的输入端口，或拖动连接。`,'warn');}};
      const label=document.createElement('span'); label.className='port-label right'; label.style.top=`${y-1}px`; label.textContent=p.label; el.append(label,port);
    });
  }

  function setupDrag(handle, n, el) {
    handle.onmousedown = (e) => {
      if(state.handMode||state.spaceDown)return;
      if (e.target.classList.contains('node-close')) return;
      e.preventDefault();
      const modified=e.shiftKey||e.ctrlKey||e.metaKey,wasSelected=state.selectedNodeIds.includes(n.id);if(modified){selectNode(n.id,{toggle:true});if(wasSelected)return;}else if(!wasSelected)selectNode(n.id);
      const sx=e.clientX, sy=e.clientY,zoom=state.zoom,group=state.selectedNodeIds.includes(n.id)?state.selectedNodeIds:[n.id],origins=group.map(id=>{const node=nodeById(id);return node&&{node,x:node.x,y:node.y};}).filter(Boolean);
      const move=(ev)=>{const dx=(ev.clientX-sx)/zoom,dy=(ev.clientY-sy)/zoom;for(const origin of origins){origin.node.x=origin.x+dx;origin.node.y=origin.y+dy;const nodeEl=document.querySelector(`.node[data-id="${CSS.escape(origin.node.id)}"]`);if(nodeEl){nodeEl.style.left=`${origin.node.x}px`;nodeEl.style.top=`${origin.node.y}px`;}}scheduleDrawEdges();};
      const up=()=>{window.removeEventListener('mousemove',move);window.removeEventListener('mouseup',up);};
      window.addEventListener('mousemove',move); window.addEventListener('mouseup',up);
    };
  }

  function renderTimelineBody(node,body){
    const edges=getIncoming(node.id).filter(e=>e.targetPort.startsWith('clip'));
    const sources=new Map(edges.map(e=>[e.source,nodeById(e.source)]));
    const ordered=(node.data.clipOrder||[]).filter(id=>state.nodes.some(n=>n.id===id&&n.type==='generateVideo'));
    for(const edge of edges)if(!ordered.includes(edge.source))ordered.push(edge.source);
    for(const id of node.data.clipOrder||[])if(state.nodes.some(n=>n.id===id&&n.type==='generateVideo')&&!ordered.includes(id))ordered.push(id);
    node.data.clipOrder=ordered;syncTimelineDock();
    node._timelineEdges=edges;
    const bar=document.createElement('div');bar.className='timeline-toolbar';
    const count=document.createElement('span');count.textContent=`${ordered.length} 个片段`;
    const play=document.createElement('button');play.type='button';play.className='small-btn';play.textContent="▶ 预览序列";play.disabled=!ordered.some(id=>nodeById(id)?.data?.asset?.url);play.onclick=()=>playTimeline(node);
    bar.append(count,play);body.appendChild(bar);
    const track=document.createElement('div');track.className='timeline-track';
    if(!ordered.length){const empty=document.createElement('div');empty.className='timeline-empty';empty.textContent="将视频节点拖到这里，或连接到片段输入端口";track.appendChild(empty);}
    ordered.forEach((id,index)=>{
      const source=nodeById(id);if(!source)return;
      const clip=document.createElement('div');clip.className='timeline-clip';clip.draggable=true;clip.dataset.clip=id;
      clip.ondragstart=e=>{e.dataTransfer.setData('text/plain',id);e.dataTransfer.effectAllowed='move';};
      clip.ondragover=e=>{e.preventDefault();};
      clip.ondrop=e=>{e.preventDefault();const moving=e.dataTransfer.getData('application/x-museflow-video-node')||e.dataTransfer.getData('text/plain'),arr=[...node.data.clipOrder],from=arr.indexOf(moving),to=arr.indexOf(id);if(from>=0&&to>=0){arr.splice(from,1);arr.splice(to,0,moving);node.data.clipOrder=arr;syncTimelineDock();render();saveState();}};
      const label=document.createElement('div');label.className='timeline-clip-head';label.textContent=`${String(index+1).padStart(2,'0')} · ${source.data.asset?.name||"视频片段"}`;
      const length=document.createElement('label');length.className='clip-duration';length.textContent="播放时长（秒）";
      const input=document.createElement('input');input.type='number';input.min='1';input.max='60';input.value=String(node.data.durations?.[id]||source.data.duration||5);input.onchange=()=>{node.data.durations=node.data.durations||{};node.data.durations[id]=Math.max(1,Math.min(60,Number(input.value)||5));};length.appendChild(input);
      const status=document.createElement('span');status.className=`timeline-clip-state ${source.data.status||'idle'}`;status.textContent=statusText(source.data.status||'waiting');
      clip.append(label,length,status);track.appendChild(clip);
    });
    body.appendChild(track);
    body.appendChild(createTimelineDropZone(node));
  }

  function createTimelineDropZone(node){
    const zone=document.createElement('div');zone.className='timeline-inline-drop';zone.textContent="将视频节点拖到这里以加入时间线";
    zone.ondragover=event=>{event.preventDefault();zone.classList.add('drag-over');};zone.ondragleave=()=>zone.classList.remove('drag-over');
    zone.ondrop=event=>{event.preventDefault();zone.classList.remove('drag-over');addTimelineClip(node,event.dataTransfer.getData('application/x-museflow-video-node')||event.dataTransfer.getData('text/plain'));};return zone;
  }

  function ensureDockTimeline(){let timeline=state.nodes.find(item=>item.type==='timeline');if(!timeline){timeline={id:uid('timeline'),type:'timeline',x:0,y:0,data:{clipOrder:[],durations:{},dockOnly:true}};state.nodes.push(timeline);}timeline.data=timeline.data||{};timeline.data.clipOrder=timeline.data.clipOrder||[];timeline.data.durations=timeline.data.durations||{};return timeline;}

  function addTimelineClip(timeline,nodeId){timeline=timeline||ensureDockTimeline();if(!nodeId||nodeById(nodeId)?.type!=='generateVideo'){setRunStatus("只有“生成视频”的输出可以加入时间线。",'warn');return;}timeline.data.clipOrder=timeline.data.clipOrder||[];if(!timeline.data.clipOrder.includes(nodeId))timeline.data.clipOrder.push(nodeId);syncTimelineDock();render();saveState();setRunStatus("视频已加入时间线。",'ok');}

  function importAllVideosToTimeline(){
    const timeline=ensureDockTimeline(),order=timeline.data.clipOrder,existing=new Set(order),all=state.nodes.filter(item=>item.type==='generateVideo');
    const additions=all.filter(video=>!existing.has(video.id));
    if(!additions.length){setRunStatus(all.length?"全部“生成视频”节点已在时间线上。":"没有可导入的“生成视频”节点。",'warn');return;}
    const addIds=new Set(additions.map(video=>video.id));
    order.push(...topoOrder().filter(id=>addIds.has(id)));
    syncTimelineDock();render();saveState();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();
    setRunStatus(`已导入 ${additions.length} 个视频节点到时间线。运行时将按时间线顺序生成视频。`,'ok');
  }

  function syncTimelineDock(){
    const dock=$('#timelineDock'),track=$('#timelineTrack'),count=$('#timelineClipCount'),addButton=$('#timelineAddVideoBtn'),importAllButton=$('#timelineImportAllBtn'),outputMenu=$('#timelineOutputMenu'),node=ensureDockTimeline();dock.classList.remove('no-timeline');const allVideos=state.nodes.filter(item=>item.type==='generateVideo'),candidates=allVideos.filter(item=>!(node.data.clipOrder||[]).includes(item.id));addButton.disabled=!candidates.length;addButton.title=addButton.disabled?"全部视频输出已在时间线上":"添加视频输出";importAllButton.disabled=!candidates.length;importAllButton.title=!allVideos.length?"没有可导入的“生成视频”节点":!candidates.length?"全部“生成视频”节点已在时间线上":"导入全部“生成视频”节点";outputMenu.innerHTML='';if(!candidates.length){const empty=document.createElement('span');empty.textContent="暂无视频输出";outputMenu.appendChild(empty);}candidates.forEach((video,index)=>{const option=document.createElement('button');option.type='button';option.textContent=video.data.asset?.name||`生成视频 ${index+1}`;option.onclick=()=>{outputMenu.classList.add('hidden');addTimelineClip(node,video.id);};outputMenu.appendChild(option);});
    const clips=(node.data.clipOrder||[]).map(id=>nodeById(id)).filter(item=>item?.type==='generateVideo');node.data.clipOrder=clips.map(item=>item.id);count.textContent=`${clips.length} 个片段`;track.innerHTML='';
    const ruler=document.createElement('div');ruler.className='timeline-ruler';const total=clips.reduce((sum,clip)=>sum+Number(node.data.durations?.[clip.id]||clip.data.duration||5),0);for(let sec=0;sec<=Math.ceil(total);sec+=5){const tick=document.createElement('span');tick.textContent=`${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')}`;ruler.appendChild(tick);}track.appendChild(ruler);
    const lane=document.createElement('div');lane.className='timeline-lane';if(!clips.length){const empty=document.createElement('div');empty.className='dock-empty';empty.textContent="将“生成视频”节点拖到这里以编排场景序列";lane.appendChild(empty);}
    clips.forEach((clip,index)=>{const duration=Number(node.data.durations?.[clip.id]||clip.data.duration||5),item=document.createElement('div');item.className='dock-clip';item.style.width=`${Math.max(210,Math.min(520,duration*42))}px`;item.draggable=true;item.dataset.clip=clip.id;item.ondragstart=event=>{event.dataTransfer.setData('application/x-museflow-video-node',clip.id);event.dataTransfer.effectAllowed='move';};item.ondragover=event=>event.preventDefault();item.ondrop=event=>{event.preventDefault();const moving=event.dataTransfer.getData('application/x-museflow-video-node'),from=node.data.clipOrder.indexOf(moving),to=node.data.clipOrder.indexOf(clip.id);if(from>=0&&to>=0){node.data.clipOrder.splice(from,1);node.data.clipOrder.splice(to,0,moving);syncTimelineDock();render();saveState();}else if(moving&&nodeById(moving)?.type==='generateVideo')addTimelineClip(node,moving);};
      const thumb=document.createElement('div');thumb.className='dock-clip-thumb';if(clip.data.asset?.url){if(clip.data.asset.kind==='image'){const image=document.createElement('img');image.src=clip.data.asset.url;thumb.appendChild(image);}else{const video=document.createElement('video');video.src=clip.data.asset.url;video.muted=true;video.preload='metadata';thumb.appendChild(video);}}else thumb.textContent='▶';
      const details=document.createElement('div');details.className='dock-clip-details';const title=document.createElement('span');title.textContent=`${String(index+1).padStart(2,'0')} · ${clip.data.asset?.name||"视频 "+(index+1)}`;title.title=title.textContent;const length=document.createElement('label');length.textContent='时长';const input=document.createElement('input');input.type='number';input.min='1';input.max='60';input.value=String(duration);input.onchange=()=>{node.data.durations=node.data.durations||{};node.data.durations[clip.id]=Math.max(1,Math.min(60,Number(input.value)||5));syncTimelineDock();render();};length.appendChild(input);details.append(title,length);const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.title="移除片段";remove.onclick=()=>{node.data.clipOrder=node.data.clipOrder.filter(id=>id!==clip.id);syncTimelineDock();render();};item.append(thumb,details,remove);lane.appendChild(item);});track.appendChild(lane);
    dock.ondragover=event=>{if(event.dataTransfer.types.includes('application/x-museflow-video-node')){event.preventDefault();dock.classList.add('drag-over');if(dock.classList.contains('collapsed'))toggleTimeline();}};dock.ondragleave=event=>{if(!dock.contains(event.relatedTarget))dock.classList.remove('drag-over');};dock.ondrop=event=>{event.preventDefault();dock.classList.remove('drag-over');const id=event.dataTransfer.getData('application/x-museflow-video-node');if(id)addTimelineClip(node,id);};
  }

  function toggleTimelineOutputMenu(){if($('#timelineAddVideoBtn').disabled)return;$('#timelineOutputMenu').classList.toggle('hidden');}

  function toggleTimeline(){const dock=$('#timelineDock'),collapsed=dock.classList.toggle('collapsed'),button=$('#timelineToggleBtn');button.textContent=collapsed?'▲':'▼';button.title=collapsed?"展开时间线":"收起时间线";button.setAttribute('aria-expanded',String(!collapsed));}

  function closeTimelinePreview(){state.timelinePreviewToken++;clearTimeout(state.timelinePreviewTimer);for(const player of [$('#timelinePlayer'),$('#timelinePlayerNext')]){player.pause();player.onended=null;}$('#timelinePreviewPanel').classList.add('hidden');}
  function visibleTimelineClipOrder(node){const nodeTrack=document.querySelector(`.node[data-id="${CSS.escape(node.id)}"] .timeline-track`),dockTrack=$('#timelineTrack'),visualTrack=nodeTrack||dockTrack,selector=nodeTrack?'.timeline-clip':'.dock-clip',visibleOrder=[...visualTrack.querySelectorAll(selector)].map(item=>item.dataset.clip).filter(Boolean);return visibleOrder.length?visibleOrder:[...(node.data.clipOrder||[])];}
  function playTimeline(node){
    const players=[$('#timelinePlayer'),$('#timelinePlayerNext')],panel=$('#timelinePreviewPanel'),clips=visibleTimelineClipOrder(node).map(id=>nodeById(id)).filter(n=>n?.type==='generateVideo'&&n.data?.asset?.url);
    if(!clips.length){setRunStatus("请先将已生成的视频片段连接到时间线。",'warn');return;}
    clearTimeout(state.timelinePreviewTimer);const token=++state.timelinePreviewToken;panel.classList.remove('hidden');let index=0,active=players.findIndex(player=>player.classList.contains('is-active'));if(active<0)active=0;
    players.forEach(player=>{player.pause();player.onended=null;player.muted=false;player.controls=player===players[active];});
    const waitForFrame=video=>new Promise(resolve=>{let finished=false;const done=()=>{if(finished)return;finished=true;clearTimeout(fallback);resolve();};const fallback=setTimeout(done,1200);if(video.requestVideoFrameCallback)video.requestVideoFrameCallback(done);else requestAnimationFrame(()=>requestAnimationFrame(done));});
    const waitForData=video=>new Promise((resolve,reject)=>{if(video.readyState>=2){resolve();return;}let timer=setTimeout(()=>{cleanup();reject(new Error("下一个时间线片段加载超时。"));},15000);const ready=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(new Error("无法加载下一个时间线片段。"));},cleanup=()=>{clearTimeout(timer);video.removeEventListener('loadeddata',ready);video.removeEventListener('error',failed);};video.addEventListener('loadeddata',ready,{once:true});video.addEventListener('error',failed,{once:true});});
    const prepareClip=(clipIndex,video)=>{const clip=clips[clipIndex];if(!clip)return Promise.resolve();if(video.dataset.preloadClip===clip.id&&video.readyState>=2)return Promise.resolve(video);video.pause();video.onended=null;video.preload='auto';video.dataset.preloadClip=clip.id;video.src=clip.data.asset.url;video.load();return waitForData(video).then(()=>{if(video.dataset.preloadClip===clip.id)video.currentTime=0;return video;});};
    const playNext=async()=>{
      clearTimeout(state.timelinePreviewTimer);if(token!==state.timelinePreviewToken)return;
      if(index>=clips.length){players[active].onended=null;players[active].pause();setRunStatus("时间线预览完成。",'ok');return;}
      const clipIndex=index,clip=clips[index++],nextIndex=1-active,next=players[nextIndex],previous=players[active];next.pause();next.onended=null;next.muted=false;next.controls=false;next.classList.remove('is-active','is-fading');
      try{await prepareClip(clipIndex,next);if(token!==state.timelinePreviewToken)return;next.currentTime=0;await next.play();await waitForFrame(next);}catch(error){if(token===state.timelinePreviewToken&&next.readyState>=2){next.controls=true;next.classList.add('is-active');previous.controls=false;previous.classList.remove('is-active','is-fading');active=nextIndex;next.onended=()=>{if(token===state.timelinePreviewToken)playNext();};setRunStatus(`时间线片段已就绪；请点击播放继续（${error.message})`,'warn');}else if(token===state.timelinePreviewToken)setRunStatus(`时间线预览已暂停：${error.message}`,'error');return;}
      if(token!==state.timelinePreviewToken){next.pause();return;}
      next.controls=true;next.classList.add('is-active');previous.controls=false;previous.onended=null;previous.classList.remove('is-active');previous.classList.add('is-fading');active=nextIndex;setTimeout(()=>{previous.classList.remove('is-fading');if(token===state.timelinePreviewToken)previous.pause();},180);
      if(index<clips.length)prepareClip(index,previous).catch(()=>{});
      const advance=()=>{if(token!==state.timelinePreviewToken)return;clearTimeout(state.timelinePreviewTimer);next.onended=null;playNext();};next.onended=advance;
      state.timelinePreviewTimer=setTimeout(advance,Math.max(1,Number(node.data.durations?.[clip.id]||clip.data.duration||5))*1000);setRunStatus(`时间线镜头 ${index}/${clips.length}`,'warn');
    };
    playNext();
  }

  async function exportTimelineVideo(){
    if(state.timelineExporting)return;const node=ensureDockTimeline(),button=$('#timelineExportBtn');
    const validation=validateTimelineBeforeExport();
    if(!validation.validClips.length){
      setRunStatus("时间线中无任何可用视频片段可供导出，请先生成视频。",'warn');
      return;
    }
    if(validation.problems.length>0){
      const issueSummary=validation.problems.map(p=>`• ${p.reason}`).join('\n');
      const confirmMsg=`【时间线完整性检查提醒】\n当前时间线共 ${validation.total} 个镜头，发现 ${validation.problems.length} 个异常或未就绪镜头：\n\n${issueSummary}\n\n是否仍要忽略异常镜头，仅导出剩余 ${validation.validClips.length} 个可用片段？\n（点击“确定”导出不完整版本，点击“取消”中止导出并返回补做）`;
      if(typeof window!=='undefined'&&window.confirm&&!window.confirm(confirmMsg)){
        setRunStatus(`已取消导出。请针对上述 ${validation.problems.length} 个问题镜头点击“↺ 补做”或重新生成。`,'warn');
        return;
      }
      setRunStatus(`用户确认导出不完整版本（忽略 ${validation.problems.length} 个问题镜头，导出 ${validation.validClips.length} 个可用镜头）。`,'warn');
    }
    const clips=validation.validClips;
    if(!clips.length){setRunStatus("导出前，请先将已生成的视频片段加入时间线。",'warn');return;}
    if(!window.MediaRecorder||!HTMLCanvasElement.prototype.captureStream){setRunStatus("此浏览器不支持导出时间线拼接视频。",'error');return;}
    state.timelineExporting=true;button.disabled=true;const sourceUrls=[];let recorder=null,canvasStream=null,audioContext=null,audioSource=null,audioDestination=null,audioResumePromise=Promise.resolve(),video=null,frameRequest=0,recordingPromise=null;
    try{const AudioContextType=window.AudioContext||window.webkitAudioContext;if(AudioContextType){audioContext=new AudioContextType();audioDestination=audioContext.createMediaStreamDestination();audioResumePromise=audioContext.resume().catch(()=>{});}}catch{audioContext=null;audioDestination=null;}
    try{
      for(let index=0;index<clips.length;index++){
        button.textContent=`正在准备 ${index+1}/${clips.length}…`;setRunStatus(`正在准备时间线片段 ${index+1}/${clips.length}以导出…`,'warn');
        const response=await fetch(clips[index].data.asset.url,{credentials:'include'});if(!response.ok)throw new Error(`无法下载时间线片段 ${index+1} (HTTP ${response.status}).`);
        const blob=await response.blob();if(!blob.size)throw new Error(`时间线片段 ${index+1}内容为空。`);sourceUrls.push(URL.createObjectURL(blob));
      }
      video=document.createElement('video');video.preload='auto';video.playsInline=true;video.muted=false;video.style.cssText='position:fixed;width:2px;height:2px;left:-4px;bottom:0;opacity:.01;pointer-events:none';document.body.appendChild(video);
      const waitForData=()=>new Promise((resolve,reject)=>{if(video.readyState>=2){resolve();return;}let timer=setTimeout(()=>{cleanup();reject(new Error("视频解码超时。"));},20000);const ready=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(new Error("无法解码此视频文件。"));},cleanup=()=>{clearTimeout(timer);video.removeEventListener('loadeddata',ready);video.removeEventListener('error',failed);};video.addEventListener('loadeddata',ready,{once:true});video.addEventListener('error',failed,{once:true});});
      video.src=sourceUrls[0];video.load();await waitForData();
      const originalWidth=video.videoWidth||1280,originalHeight=video.videoHeight||720,scale=Math.min(1,1920/Math.max(originalWidth,originalHeight)),canvas=document.createElement('canvas');canvas.width=Math.max(2,Math.floor(originalWidth*scale/2)*2);canvas.height=Math.max(2,Math.floor(originalHeight*scale/2)*2);
      const context=canvas.getContext('2d',{alpha:false});if(!context)throw new Error("无法创建视频导出画布。");
      const drawFrame=()=>{if(!video||!context)return;if(video.readyState>=2&&video.videoWidth>0){const fit=Math.min(canvas.width/video.videoWidth,canvas.height/video.videoHeight),width=video.videoWidth*fit,height=video.videoHeight*fit;context.fillStyle='#000';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(video,(canvas.width-width)/2,(canvas.height-height)/2,width,height);}frameRequest=requestAnimationFrame(drawFrame);};drawFrame();
      canvasStream=canvas.captureStream(30);
      if(audioContext&&audioDestination){try{audioSource=audioContext.createMediaElementSource(video);audioSource.connect(audioDestination);const audioTrack=audioDestination.stream.getAudioTracks()[0];if(audioTrack)canvasStream.addTrack(audioTrack);await audioResumePromise;if(audioContext.state!=='running')await audioContext.resume();}catch{audioContext.close().catch(()=>{});audioContext=null;audioDestination=null;audioSource=null;}}
      if(!audioDestination&&typeof video.captureStream==='function'){const captured=video.captureStream();for(const track of captured.getAudioTracks())canvasStream.addTrack(track);}
      const mimeType=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'].find(type=>MediaRecorder.isTypeSupported?.(type));recorder=mimeType?new MediaRecorder(canvasStream,{mimeType}):new MediaRecorder(canvasStream);
      const chunks=[];recordingPromise=new Promise((resolve,reject)=>{recorder.ondataavailable=event=>{if(event.data?.size)chunks.push(event.data);};recorder.onerror=event=>reject(event.error||new Error("视频编码失败。"));recorder.onstop=()=>resolve(new Blob(chunks,{type:recorder.mimeType||'video/webm'}));});recordingPromise.catch(()=>{});recorder.start(1000);
      for(let index=0;index<clips.length;index++){
        if(index){video.pause();video.src=sourceUrls[index];video.load();await waitForData();}
        const clipNode=clips[index];
        const trimCfg=node.data.trims?.[clipNode.id]||{};
        const trimStart=Math.max(0,Number(trimCfg.trimStart??clipNode.data.trimStart)||0);
        const rawDur=Number(node.data.durations?.[clipNode.id]||clipNode.data.editDuration||clipNode.data.duration||5);
        const trimEndVal=Number(trimCfg.trimEnd??clipNode.data.trimEnd);
        const duration=Math.max(0.5,Math.min(60,(Number.isFinite(trimEndVal)&&trimEndVal>trimStart)?(trimEndVal-trimStart):rawDur));
        video.currentTime=trimStart;await video.play();button.textContent=`正在导出 ${index+1}/${clips.length}…`;setRunStatus(`正在导出时间线片段 ${index+1}/${clips.length}（截取 ${trimStart.toFixed(1)}s–${(trimStart+duration).toFixed(1)}s）…`,'warn');
        await new Promise(resolve=>setTimeout(resolve,duration*1000));video.pause();
      }
      const completed=new Promise(resolve=>{recorder.addEventListener('stop',resolve,{once:true});});recorder.stop();await completed;const output=await recordingPromise;if(!output.size)throw new Error("导出的视频为空。");
      if(state.timelineExportUrl)URL.revokeObjectURL(state.timelineExportUrl);state.timelineExportUrl=URL.createObjectURL(output);
      const player=$('#timelinePlayer'),nextPlayer=$('#timelinePlayerNext');closeTimelinePreview();$('#timelinePreviewPanel').classList.remove('hidden');nextPlayer.pause();nextPlayer.classList.remove('is-active','is-fading');nextPlayer.controls=false;player.src=state.timelineExportUrl;player.controls=true;player.classList.remove('is-fading');player.classList.add('is-active');
      const link=document.createElement('a');link.href=state.timelineExportUrl;link.download=`MuseFlow-Timeline-${new Date().toISOString().replace(/[:.]/g,'-')}.webm`;link.click();setRunStatus("时间线拼接视频已导出为 WebM。",'ok');
    }catch(error){setRunStatus(`时间线导出失败：${error?.message||String(error)}`,'error');}
    finally{if(frameRequest)cancelAnimationFrame(frameRequest);if(recorder?.state==='recording'){recorder.stop();try{await recordingPromise;}catch{}}video?.pause();video?.remove();canvasStream?.getTracks().forEach(track=>track.stop());await audioContext?.close().catch(()=>{});sourceUrls.forEach(url=>URL.revokeObjectURL(url));state.timelineExporting=false;button.disabled=false;button.textContent="⇩ 导出视频";}
  }

  function getPortCenter(nodeId, portId, kind) {
    const q = `.port.${kind}[data-node="${CSS.escape(nodeId)}"][data-port="${CSS.escape(portId)}"]`;
    const p = document.querySelector(q); if (!p) return null;
    const r=p.getBoundingClientRect(), vr=$('#viewport').getBoundingClientRect();
    return { x:(r.left-vr.left-state.panX)/state.zoom+r.width/(2*state.zoom), y:(r.top-vr.top-state.panY)/state.zoom+r.height/(2*state.zoom) };
  }

  function drawEdges() {
    edgesSvg.innerHTML='';
    state.edges.forEach(e => {
      const a=getPortCenter(e.source,e.sourcePort,'out'), b=getPortCenter(e.target,e.targetPort,'in'); if(!a||!b)return;
      const incoming=getIncoming(e.target,e.targetPort),index=incoming.findIndex(edge=>edge.id===e.id),fan=isMultiInput(nodeById(e.target)?.type,e.targetPort)&&incoming.length>1?(index-(incoming.length-1)/2)*12:0;
      const dx=b.x-a.x,direction=dx<0?-1:1,bend=Math.max(62,Math.abs(dx)*.42),output=nodeDefs[nodeById(e.source)?.type]?.outputs?.find(port=>port.id===e.sourcePort),d=`M ${a.x} ${a.y} C ${a.x+direction*bend} ${a.y}, ${b.x-direction*bend} ${b.y+fan}, ${b.x} ${b.y}`,selected=state.selectedEdgeIds.includes(e.id);const path=document.createElementNS('http://www.w3.org/2000/svg','path');const isRef = e.targetPort === 'reference' || e.sourcePort === 'reference' || e.source === 'node_style_anchor'; path.setAttribute('class',`edge edge-${output?.type||'media'}${selected?' edge-selected':''}${isRef?' edge-reference':''}`);path.setAttribute('d',d);path.setAttribute('data-edge-id',e.id);edgesSvg.appendChild(path);const hit=document.createElementNS('http://www.w3.org/2000/svg','path');hit.setAttribute('class','edge-hit');hit.setAttribute('data-edge-id',e.id);hit.setAttribute('d',d);edgesSvg.appendChild(hit);
    });
    if(state.draggingWire&&state.wirePointer){
      const reverse=state.draggingWire.direction==='in',a=getPortCenter(state.draggingWire.nodeId,state.draggingWire.portId,reverse?'in':'out');
      const vr=$('#viewport').getBoundingClientRect();
      if(a){const x=(state.wirePointer.x-vr.left-state.panX)/state.zoom,y=(state.wirePointer.y-vr.top-state.panY)/state.zoom,dx=reverse?a.x-x:x-a.x,direction=dx<0?-1:1,bend=Math.max(55,Math.abs(dx)*.4),d=reverse?`M ${x} ${y} C ${x+direction*bend} ${y}, ${a.x-direction*bend} ${a.y}, ${a.x} ${a.y}`:`M ${a.x} ${a.y} C ${a.x+direction*bend} ${a.y}, ${x-direction*bend} ${y}, ${x} ${y}`;const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('class','edge edge-draft');p.setAttribute('d',d);edgesSvg.appendChild(p);}
    }
  }

  function scheduleDrawEdges() {
    if (state.edgeFrame) return;
    state.edgeFrame = requestAnimationFrame(() => { state.edgeFrame = 0; drawEdges(); });
  }

  function render() {
    syncPreviewOutputs();canvas.innerHTML=''; state.nodes.filter(n=>!n.data?.dockOnly).forEach(n => canvas.appendChild(renderNode(n)));applyCanvasTransform();requestAnimationFrame(drawEdges);syncTimelineDock();scheduleAutoSave();
  }

  function syncPreviewOutputs(){for(const preview of state.nodes.filter(node=>node.type==='preview')){const edge=getIncoming(preview.id,'media')[0],source=edge&&nodeById(edge.source);let asset=null;if(source){asset=edge.sourcePort==='endFrame'?source.data?.endFrame:source.data?.asset;if(!asset&&source.type==='imageInput'&&source.data?.localDataUrl)asset={id:source.id,kind:'image',url:source.data.localDataUrl,name:"输入图片"};}preview.data.asset=asset||null;}}

  function applyCanvasTransform(){const transform=`translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;canvas.style.transform=transform;edgesSvg.style.transform=transform;$('#zoomLevel').textContent=`${Math.round(state.zoom*100)}%`;$('#viewport').classList.toggle('hand-mode',state.handMode||state.spaceDown); document.body.classList.toggle('hand-active', Boolean(state.handMode||state.spaceDown));}
  function zoomAt(clientX,clientY,factor){const rect=$('#viewport').getBoundingClientRect(),x=clientX-rect.left,y=clientY-rect.top,old=state.zoom,next=Math.max(.25,Math.min(2.5,old*factor));if(next===old)return;const contentX=(x-state.panX)/old,contentY=(y-state.panY)/old;state.zoom=next;state.panX=x-contentX*next;state.panY=y-contentY*next;applyCanvasTransform();scheduleDrawEdges();}
  function setZoom(value){const rect=$('#viewport').getBoundingClientRect();zoomAt(rect.left+rect.width/2,rect.top+rect.height/2,value/state.zoom);}
  
  function autoLayoutWorkflow() {
    if (!state.nodes || state.nodes.length === 0) return;
    const styleAnchors = state.nodes.filter(n =>
      n.type === 'imageInput' ||
      n.type === 'references' ||
      n.id.includes('anchor') ||
      n.id.includes('ref_') ||
      n.id.startsWith('node_ref')
    );
    const timelineNodes = state.nodes.filter(n => n.type === 'timeline');
    const previewNodes = state.nodes.filter(n => n.type === 'preview');

    const sceneMap = new Map();
    state.nodes.forEach(n => {
      if (styleAnchors.includes(n) || timelineNodes.includes(n) || previewNodes.includes(n)) return;
      let sceneNum = null;
      const labelMatch = (n.data?.sceneLabel || n.title || '').match(/(?:场景|分镜|镜头|Shot)\s*(\d+)/i);
      const idMatch = n.id.match(/(?:shot|scene)[-_]?(\d+)/i);
      if (labelMatch) sceneNum = Number(labelMatch[1]);
      else if (idMatch) sceneNum = Number(idMatch[1]);
      else if (Number.isFinite(n.data?.shotNumber)) sceneNum = Number(n.data.shotNumber);
      const key = sceneNum !== null ? sceneNum : n.id;
      if (!sceneMap.has(key)) {
        sceneMap.set(key, { key, sceneNum: sceneNum !== null ? sceneNum : 999, nodes: [] });
      }
      sceneMap.get(key).nodes.push(n);
    });

    const sortedScenes = [...sceneMap.values()].sort((a, b) => a.sceneNum - b.sceneNum);
    const totalScenes = sortedScenes.length;

    // 根据总分镜数自适应列数：15镜为5列x3行，9镜为3列x3行，兼顾大屏叙事结构
    let numCols = 3;
    if (totalScenes <= 3) numCols = Math.max(1, totalScenes);
    else if (totalScenes <= 8) numCols = Math.min(3, totalScenes);
    else if (totalScenes === 9) numCols = 3;
    else if (totalScenes % 5 === 0) numCols = 5;
    else if (totalScenes % 4 === 0) numCols = 4;
    else numCols = totalScenes > 12 ? 5 : 4;

    const sceneW = 1220;
    const sceneH = 1400;

    // 1. 左侧全局资产列：外扩独立定位，绝不挤压正文
    styleAnchors.forEach((n, idx) => {
      n.x = -480;
      n.y = 100 + idx * 460;
    });

    // 2. 逐镜黄金三列六联体排版：提示词列 ➔ 底图列 ➔ 视频列，彻底杜绝上下或左右遮挡
    sortedScenes.forEach((scene, index) => {
      const row = Math.floor(index / numCols);
      const col = index % numCols;
      const originX = 120 + col * sceneW;
      const originY = 100 + row * sceneH;

      const isEnd = (n) => n.id.includes('end') || n.data?.frameRole === 'end' || (n.data?.sceneLabel || '').includes('尾帧');
      const isVideo = (n) => n.id.includes('v_') || n.id.includes('video') || (n.data?.sceneLabel || '').includes('运镜');

      const imgPrompt = scene.nodes.find(n => n.type === 'prompt' && !isEnd(n) && !isVideo(n));
      const endImgPrompt = scene.nodes.find(n => n.type === 'prompt' && isEnd(n));
      const vPrompt = scene.nodes.find(n => n.type === 'prompt' && isVideo(n));

      const imgGen = scene.nodes.find(n => n.type === 'generateImage' && !isEnd(n));
      const endImgGen = scene.nodes.find(n => n.type === 'generateImage' && isEnd(n));
      const vGen = scene.nodes.find(n => n.type === 'generateVideo');

      // 列 1: 提示词垂直流
      if (imgPrompt) { imgPrompt.x = originX; imgPrompt.y = originY; }
      if (endImgPrompt) { endImgPrompt.x = originX; endImgPrompt.y = originY + 380; }
      if (vPrompt) { vPrompt.x = originX; vPrompt.y = originY + 760; }

      // 列 2: 首尾帧图片生成流 (与左侧提示词水平严格对齐)
      if (imgGen) { imgGen.x = originX + 360; imgGen.y = originY; }
      if (endImgGen) { endImgGen.x = originX + 360; endImgGen.y = originY + 380; }

      // 列 3: 10s视频生成节点 (居中垂直对齐于首尾帧之间，连线舒展自然)
      if (vGen) { vGen.x = originX + 740; vGen.y = originY + 220; }

      // 备用/未预置扩展节点：整齐置于分镜下方，绝对不穿透至下一行
      const placed = new Set([imgPrompt, endImgPrompt, vPrompt, imgGen, endImgGen, vGen].filter(Boolean));
      scene.nodes.filter(n => !placed.has(n)).forEach((n, extraIdx) => {
        n.x = originX + (extraIdx % 3) * 360;
        n.y = originY + 1150 + Math.floor(extraIdx / 3) * 360;
      });
    });

    // 3. 时间线与全局预览：放置于故事板右侧专属控制区
    const timelineX = 120 + numCols * sceneW + 60;
    timelineNodes.forEach((n, idx) => {
      n.x = timelineX;
      n.y = 100 + 360 + idx * 460;
    });
    previewNodes.forEach((n, idx) => {
      n.x = timelineX;
      n.y = 100 + idx * 360;
    });

    render();
    saveState();
    fitCanvas();
    const rowsCount = Math.ceil(totalScenes / numCols);
    setRunStatus(`✓ 已优化规整排版：${totalScenes} 个分镜按 ${numCols}列×${rowsCount}行 矩阵无重叠舒展排列，视野清晰通透！`, 'ok');
  }

  function fitCanvas(){const nodes=state.nodes.filter(node=>!node.data?.dockOnly);if(!nodes.length){state.zoom=1;state.panX=0;state.panY=0;applyCanvasTransform();return;}const rect=$('#viewport').getBoundingClientRect(),xs=nodes.map(n=>n.x),ys=nodes.map(n=>n.y),maxX=Math.max(...nodes.map(n=>n.x+(document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.offsetWidth||270))),maxY=Math.max(...nodes.map(n=>n.y+(document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.offsetHeight||220)));const minX=Math.min(...xs),minY=Math.min(...ys),scale=Math.max(.25,Math.min(1.5,(rect.width-100)/(maxX-minX+80),(rect.height-80)/(maxY-minY+80)));state.zoom=scale;state.panX=(rect.width-(maxX-minX)*scale)/2-minX*scale;state.panY=(rect.height-(maxY-minY)*scale)/2-minY*scale;applyCanvasTransform();scheduleDrawEdges();}
  function startPan(event){state.panning={x:event.clientX,y:event.clientY,panX:state.panX,panY:state.panY};$('#viewport').classList.add('panning'); document.body.classList.add('panning'); try{const cap=event.target?.setPointerCapture?event.target:document.body;cap.setPointerCapture(event.pointerId);}catch{}event.preventDefault();}
  function movePan(event){if(!state.panning)return;state.panX=state.panning.panX+event.clientX-state.panning.x;state.panY=state.panning.panY+event.clientY-state.panning.y;applyCanvasTransform();scheduleDrawEdges();}
  function endPan(){state.panning=null;$('#viewport').classList.remove('panning'); document.body.classList.remove('panning');}

  function startSelectionMarquee(event){
    if(event.button!==0||state.handMode||state.spaceDown||event.target.closest('.node,.canvas-tools,button'))return;
    const viewport=$('#viewport'),bounds=viewport.getBoundingClientRect(),keep=event.shiftKey||event.ctrlKey||event.metaKey;
    if(!keep){state.selectedNodeIds=[];state.selectedNodeId=null;state.selectedEdgeIds=[];document.querySelectorAll('.node.selected').forEach(node=>node.classList.remove('selected'));scheduleDrawEdges();}
    const box=document.createElement('div');box.className='selection-marquee';viewport.appendChild(box);
    state.selectionMarquee={startX:event.clientX,startY:event.clientY,bounds,box,keep,initial:[...state.selectedNodeIds],initialEdges:keep?[...state.selectedEdgeIds]:[]};
    try{viewport.setPointerCapture(event.pointerId);}catch{}event.preventDefault();
  }
  function moveSelectionMarquee(event){const drag=state.selectionMarquee;if(!drag)return;const left=Math.min(event.clientX,drag.startX),top=Math.min(event.clientY,drag.startY),right=Math.max(event.clientX,drag.startX),bottom=Math.max(event.clientY,drag.startY);Object.assign(drag.box.style,{left:`${left-drag.bounds.left}px`,top:`${top-drag.bounds.top}px`,width:`${right-left}px`,height:`${bottom-top}px`});const selected=new Set(drag.initial);for(const node of document.querySelectorAll('.node')){const r=node.getBoundingClientRect();if(r.right>=left&&r.left<=right&&r.bottom>=top&&r.top<=bottom)selected.add(node.dataset.id);}state.selectedNodeIds=[...selected];state.selectedNodeId=state.selectedNodeIds.at(-1)||null;document.querySelectorAll('.node').forEach(node=>node.classList.toggle('selected',selected.has(node.dataset.id)));const selectedEdges=new Set(drag.initialEdges);for(const path of edgesSvg.querySelectorAll('.edge[data-edge-id]')){const matrix=path.getScreenCTM();if(!matrix)continue;const length=path.getTotalLength();for(let point=0;point<=length;point+=Math.max(8,length/60)){const p=new DOMPoint(path.getPointAtLength(point).x,path.getPointAtLength(point).y).matrixTransform(matrix);if(p.x>=left&&p.x<=right&&p.y>=top&&p.y<=bottom){selectedEdges.add(path.dataset.edgeId);break;}}}state.selectedEdgeIds=[...selectedEdges];scheduleDrawEdges();}
  function endSelectionMarquee(){const drag=state.selectionMarquee;if(!drag)return;drag.box.remove();state.selectionMarquee=null;}

  function openCanvasMenu(e){
    const nodeEl=e.target.closest('.node');e.preventDefault();e.stopPropagation();
    if(!nodeEl){const rect=$('#viewport').getBoundingClientRect(),menu=$('#canvasMenu');state.contextPoint={x:(e.clientX-rect.left-state.panX)/state.zoom,y:(e.clientY-rect.top-state.panY)/state.zoom};menu.innerHTML='';delete menu.dataset.nodeId;const title=document.createElement('div');title.className='menu-caption';title.textContent="画布";menu.appendChild(title);[['＋ 提示词','add:prompt'],['＋ 反向提示词','add:negativePrompt'],['＋ 图片输入','add:imageInput'],['＋ 参考素材','add:references'],['＋ 生成图片','add:generateImage'],['＋ 生成视频','add:generateVideo'],['＋ 时间线','add:timeline'],['＋ 预览','add:preview'],["导出工作流",'save'],['▶ 运行选中节点','run-selected'],['▶ 智能运行工作流','run'],['↺ 全量重新运行','run-all'],["整理节点",'arrange'],["删除选中节点",'delete-selected'],["移除全部连接",'disconnect-all']].forEach(([label,action])=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.contextAction=action;menu.appendChild(button);});menu.classList.remove('hidden');menu.style.left=`${Math.min(e.clientX,innerWidth-230)}px`;menu.style.top=`${Math.min(e.clientY,innerHeight-460)}px`;return;}
    e.stopPropagation();const node=nodeById(nodeEl.dataset.id);if(!node)return;state.selectedNodeId=node.id;
    const menu=$('#canvasMenu');menu.innerHTML='';menu.dataset.nodeId=node.id;
    const title=document.createElement('div');title.className='menu-caption';title.textContent=nodeDefs[node.type].title;menu.appendChild(title);
    const addAction=(label,action)=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.contextAction=action;menu.appendChild(button);};
    if(['generateImage','generateVideo'].includes(node.type))addAction(node.data.status==='running'?`■ 停止${node.type==='generateVideo'?"视频":"图片"}`:`▶ 生成${node.type==='generateVideo'?"视频":"图片"}`,'node-run');
    if(state.selectedNodeIds.length>1)addAction(`▶ 运行选中的 ${state.selectedNodeIds.filter(id=>['generateImage','generateVideo'].includes(nodeById(id)?.type)).length} 个生成节点`,'run-selected');
    if(node.type==='timeline')addAction("▶ 预览序列",'node-preview');
    if((nodeDefs[node.type]?.outputs||[]).some(port=>['image','video'].includes(port.type)))addAction("创建预览节点",'node-create-preview');
    if(node.type==='imageInput')addAction("选择／替换图片",'node-choose-image');
    if(node.type==='imageResize')addAction("下载调整后的图片",'node-download-image');
    if(node.type==='preview')addAction("下载预览内容",'node-download-preview');
    if(node.type==='prompt'||node.type==='negativePrompt'||node.type==='textAppend')addAction("编辑文本",'node-focus-text');
    addAction("复制节点",'node-duplicate');addAction("断开节点连接",'node-disconnect');addAction("删除节点",'node-delete');
    menu.classList.remove('hidden');menu.style.left=`${Math.min(e.clientX,innerWidth-230)}px`;menu.style.top=`${Math.min(e.clientY,innerHeight-380)}px`;
  }
  function openEdgeMenu(e){
    const hit=e.target.closest('.edge-hit[data-edge-id]');if(!hit)return;
    e.preventDefault();e.stopPropagation();const menu=$('#canvasMenu');menu.innerHTML='';menu.dataset.edgeId=hit.dataset.edgeId;delete menu.dataset.nodeId;
    const title=document.createElement('div');title.className='menu-caption';title.textContent="连接";menu.appendChild(title);
    const button=document.createElement('button');button.type='button';button.textContent="删除连接";button.dataset.contextAction='edge-delete';menu.appendChild(button);
    menu.classList.remove('hidden');menu.style.left=`${Math.min(e.clientX,innerWidth-230)}px`;menu.style.top=`${Math.min(e.clientY,innerHeight-120)}px`;
  }
  function selectEdgePointer(e){if(e.button!==0)return;const hit=e.target.closest('.edge-hit[data-edge-id]');if(!hit)return;e.preventDefault();e.stopPropagation();const id=hit.dataset.edgeId;state.selectedEdgeIds=e.shiftKey?[...new Set([...state.selectedEdgeIds,id])]:[id];scheduleDrawEdges();}
  function closeCanvasMenu(){ $('#canvasMenu').classList.add('hidden'); }
  function runNodeContextAction(action){const menu=$('#canvasMenu'),node=nodeById(menu.dataset.nodeId);if(!node)return;closeCanvasMenu();
    if(action==='node-run'){runSingleNode(node.id);return;}if(action==='node-preview'){playTimeline(node);return;}if(action==='node-delete'){removeNode(node.id);return;}
    if(action==='node-create-preview'){const output=(nodeDefs[node.type].outputs||[]).find(port=>['image','video'].includes(port.type));if(output){const target=makeNode('preview',node.x+350,node.y);state.nodes.push(target);state.connectingFrom={nodeId:node.id,portId:output.id};connect(target.id,'media');}return;}
    if(action==='node-disconnect'){state.edges=state.edges.filter(edge=>edge.source!==node.id&&edge.target!==node.id);render();setRunStatus("已移除此节点的连接。",'ok');return;}
    const el=document.querySelector(`.node[data-id="${CSS.escape(node.id)}"]`);
    if(action==='node-focus-text'){el?.querySelector('textarea')?.focus();return;}
    if(action==='node-choose-image'){el?.querySelector('input[type="file"]')?.click();return;}
    if(action==='node-download-image'||action==='node-download-preview'){const url=node.data.asset?.url;if(url){const link=document.createElement('a');link.href=url;link.download=node.data.asset.name||'museflow-output';link.click();}else setRunStatus("此节点暂无可下载的输出。",'warn');return;}
    if(action==='node-duplicate'){const copy=structuredClone(node);copy.id=uid(node.type);copy.x+=36;copy.y+=36;copy.data={...copy.data};state.nodes.push(copy);if(['generateImage','generateVideo'].includes(copy.type)){const references=state.nodes.find(item=>item.type==='references');if(references)connectReferenceNode(references,copy);}render();setRunStatus("节点已复制。",'ok');}
  }
  function arrangeNodes(){
    try{
      const order=topoOrder().filter(id=>!nodeById(id)?.data?.dockOnly),level=new Map(order.map(id=>[id,0]));
      for(const id of order)for(const edge of state.edges.filter(e=>e.source===id&&level.has(e.target)))level.set(edge.target,Math.max(level.get(edge.target)||0,(level.get(id)||0)+1));
      const groups=new Map();for(const id of order){const l=level.get(id)||0;if(!groups.has(l))groups.set(l,[]);groups.get(l).push(id);}
      for(const [l,ids] of groups.entries())ids.forEach((id,row)=>{const node=nodeById(id);node.x=70+l*350;node.y=60+row*260;});
      render();setRunStatus("已按工作流顺序整理节点。",'ok');
    }catch(error){setRunStatus(error.message,'error');}
  }
  function runCanvasAction(action){
    if(action==='edge-delete'){const menu=$('#canvasMenu'),edgeId=menu.dataset.edgeId;closeCanvasMenu();if(!edgeId)return;const before=state.edges.length;state.edges=state.edges.filter(edge=>edge.id!==edgeId);delete menu.dataset.edgeId;if(state.edges.length!==before){render();saveState();setRunStatus("连接已删除。",'ok');}return;}
    if(action.startsWith('node-')){runNodeContextAction(action);return;}
    closeCanvasMenu();const pos=state.contextPoint;
    if(action.startsWith('add:')){addNode(action.slice(4),pos.x,pos.y);return;}
    if(action==='save'){saveState();return;}
    if(action==='run'){execute(null,{forceAll:false});return;}
    if(action==='run-all'){execute(null,{forceAll:true});return;}
    if(action==='run-selected'){runSelectedNodes();return;}
    if(action==='arrange'){arrangeNodes();return;}
    if(action==='delete-selected'){if(state.selectedNodeIds.length)removeSelectedNodes();else if(state.selectedNodeId)removeNode(state.selectedNodeId);else setRunStatus("请先选择一个或多个节点。",'warn');return;}
    if(action==='disconnect-all'){state.edges=[];state.connectingFrom=null;render();setRunStatus("已移除全部连接。",'ok');}
  }

  function runSelectedNodes(){
    const selected=state.selectedNodeIds.filter(id=>['generateImage','generateVideo'].includes(nodeById(id)?.type));
    if(selected.length)execute(selected);
    else if(state.selectedNodeId&&['generateImage','generateVideo'].includes(nodeById(state.selectedNodeId)?.type))execute(state.selectedNodeId);
    else setRunStatus("请先在画布中选择一个或多个生成节点。",'warn');
  }

  function runNodeContextAction(action){const menu=$('#canvasMenu'),node=nodeById(menu.dataset.nodeId);if(!node)return;closeCanvasMenu();
    if(action==='node-run'){runSingleNode(node.id);return;}if(action==='node-preview'){playTimeline(node);return;}if(action==='node-delete'){removeNode(node.id);return;}
    if(action==='node-disconnect'){state.edges=state.edges.filter(edge=>edge.source!==node.id&&edge.target!==node.id);render();setRunStatus("已移除此节点的连接。",'ok');return;}
    const el=document.querySelector(`.node[data-id="${CSS.escape(node.id)}"]`);
    if(action==='node-focus-text'){el?.querySelector('textarea')?.focus();return;}if(action==='node-choose-image'){el?.querySelector('input[type="file"]')?.click();return;}
    if(action==='node-download-image'||action==='node-download-preview'){const url=node.data.asset?.url;if(url){const link=document.createElement('a');link.href=url;link.download=node.data.asset.name||'museflow-output';link.click();}else setRunStatus("此节点暂无可下载的输出。",'warn');return;}
    if(action==='node-duplicate'){const copy=structuredClone(node);copy.id=uid(node.type);copy.x+=36;copy.y+=36;copy.data={...copy.data};state.nodes.push(copy);render();setRunStatus("节点已复制。",'ok');}
  }

  function getIncoming(nodeId, targetPort) { return state.edges.filter(e => e.target===nodeId && (!targetPort || e.targetPort===targetPort)); }
  function sourceFor(edge) { return edge ? nodeById(edge.source) : null; }

  function resolveText(nodeId,seen=new Set()){
    if(seen.has(nodeId))return '';seen.add(nodeId);
    const node=nodeById(nodeId);if(!node)return '';
    if(['prompt','negativePrompt'].includes(node.type))return String(node.data?.text??node.data?.prompt??node.data?.value??'');
    if(node.type==='textAppend'){
      const parent=sourceFor(getIncoming(nodeId,'text')[0]);
      return [parent?resolveText(parent.id,new Set(seen)):'' ,String(node.data?.text??'')].filter(value=>value.trim()).join(' ');
    }
    if(node.type==='textConcat'){
      const inputs=['a','b'].map(port=>sourceFor(getIncoming(nodeId,port)[0])).filter(Boolean).map(source=>resolveText(source.id,new Set(seen))).filter(Boolean);
      return inputs.join(node.data.separator??', ');
    }
    const source=sourceFor(getIncoming(nodeId,'text')[0]);return source?resolveText(source.id,seen):'';
  }
  function resolvePrompt(nodeId){
    return getIncoming(nodeId,'prompt').map(edge=>nodeById(edge.source)).filter(Boolean).map(source=>resolveText(source.id).trim()).filter(Boolean).join('\n\n');
  }
  function resolveNegativePrompt(nodeId){const source=sourceFor(getIncoming(nodeId,'negative')[0]);return source?resolveText(source.id):'';}
  function timelinePredecessor(nodeId){const timeline=state.nodes.find(item=>item.type==='timeline'),order=timeline?.data?.clipOrder||[],index=order.indexOf(nodeId);return index>0?nodeById(order[index-1]):null;}
  function previousImageNode(nodeId){const imageNodes=state.nodes.filter(item=>item.type==='generateImage'),index=imageNodes.findIndex(item=>item.id===nodeId);return index>0?imageNodes[index-1]:null;}
  function hasDirectKeyframe(nodeId){
    return getIncoming(nodeId,'reference').some(edge=>{
      const src=nodeById(edge.source);
      return Boolean(src&&src.type!=='references'&&(src.type==='imageInput'||src.type==='generateImage'||src.data?.localDataUrl||src.data?.asset?.url));
    });
  }
  function resolveReferences(nodeId){
    const references=[],seen=new Set();
    const add=(url,name,role='ref')=>{
      if(url&&!seen.has(url)&&references.length<9){
        seen.add(url);
        references.push({url,name:name||`参考图 ${references.length+1}`,role});
      }
    };
    const visit=(source,sourcePort,role='ref',visited=new Set())=>{
      if(!source||visited.has(source.id)||references.length>=9)return;
      visited.add(source.id);
      if(source.type==='references'){
        for(const edge of getIncoming(source.id))visit(nodeById(edge.source),edge.sourcePort,'ref',visited);
        return;
      }
      const labelName=source.data?.sceneLabel||source.data?.asset?.name||source.id;
      if(sourcePort==='endFrame'){
        add(source.data?.endFrame?.url,source.data?.endFrame?.name||`尾帧 · ${labelName}`,role);
        return;
      }
      if(source.type==='imageInput'&&source.data?.localDataUrl){
        add(source.data.localDataUrl,labelName,role);
        return;
      }
      if(source.data?.asset?.kind==='image'){
        add(source.data.asset.url,labelName,role);
      }
    };
    const node=nodeById(nodeId);
    const incomingRefEdges=getIncoming(nodeId,'reference');
    const isGlobalAssetNode=src=>Boolean(src&&(src.type==='references'||/^node_ref_|全局|参考资产/i.test(`${src.id} ${src.data?.sceneLabel||''}`)));
    const isEndKeyframeEdge=(edge,src)=>Boolean(src&&!isGlobalAssetNode(src)&&(edge.sourcePort==='endFrame'||src.data?.frameRole==='end'||/end|尾帧|尾图/i.test(`${src.id} ${src.data?.sceneLabel||''}`)));
    const isStartKeyframeEdge=(edge,src)=>Boolean(src&&!isGlobalAssetNode(src)&&!isEndKeyframeEdge(edge,src));

    // 1. 第一顺位（Image 1）：本镜【首帧图 Start Keyframe】
    for(const edge of incomingRefEdges){
      const src=nodeById(edge.source);
      if(isStartKeyframeEdge(edge,src))visit(src,edge.sourcePort,'start');
    }
    // 2. 第二顺位（Image 2）：本镜【尾帧图 End Keyframe】
    for(const edge of incomingRefEdges){
      const src=nodeById(edge.source);
      if(isEndKeyframeEdge(edge,src))visit(src,edge.sourcePort,'end');
    }
    // 3. 仅当视频节点没有自己的独立分镜底图时，才允许使用上一镜尾帧作为首帧承接
    if(node?.type==='generateVideo'&&node.data?.continuity&&!hasDirectKeyframe(nodeId)){
      const previous=timelinePredecessor(nodeId);
      if(previous)add(previous.data?.endFrame?.url,`CONTINUITY START FRAME · ${previous.data?.endFrame?.name||'previous clip end'}`,'start');
    }
    if(node?.type==='generateImage'&&node.data?.styleContinuity){const prevImg=previousImageNode(nodeId);if(prevImg?.data?.asset?.url)add(prevImg.data.asset.url,`PREVIOUS SCENE STYLE REFERENCE · ${prevImg.id}`,'ref');}
    // 4. 第三顺位（Images 3..9）：全局风格/角色/道具参考图（最高串联 9 张）
    for(const edge of incomingRefEdges){
      const src=nodeById(edge.source);
      if(isGlobalAssetNode(src))visit(src,edge.sourcePort,'ref');
    }
    return references.slice(0,9);
  }

  function topoOrder() {
    const indeg=new Map(state.nodes.map(n=>[n.id,0])), outgoing=new Map(state.nodes.map(n=>[n.id,[]]));
    state.edges.forEach(e=>{if(!indeg.has(e.source)||!indeg.has(e.target))return;indeg.set(e.target,indeg.get(e.target)+1);outgoing.get(e.source).push(e.target);});
    for(const node of state.nodes.filter(item=>item.type==='generateVideo'&&item.data?.continuity&&!hasDirectKeyframe(item.id))){const previous=timelinePredecessor(node.id);if(previous&&previous.id!==node.id&&!outgoing.get(previous.id).includes(node.id)){outgoing.get(previous.id).push(node.id);indeg.set(node.id,indeg.get(node.id)+1);}}
    const timeline=state.nodes.find(item=>item.type==='timeline'),orderedVideos=(timeline?.data?.clipOrder||[]).filter(id=>nodeById(id)?.type==='generateVideo');
    for(const node of state.nodes)if(node.type==='generateVideo'&&!orderedVideos.includes(node.id))orderedVideos.push(node.id);
    const videoRank=new Map(orderedVideos.map((id,index)=>[id,index])),nodeRank=new Map(state.nodes.map((node,index)=>[node.id,index]));
    const priority=id=>{const item=nodeById(id);return item?.type==='generateVideo'?state.nodes.length+1+(videoRank.get(id)??nodeRank.get(id)):nodeRank.get(id)??0;};
    const q=state.nodes.filter(n=>indeg.get(n.id)===0).map(n=>n.id), out=[];
    while(q.length){q.sort((a,b)=>priority(a)-priority(b));const id=q.shift();out.push(id);for(const target of outgoing.get(id)){indeg.set(target,indeg.get(target)-1);if(indeg.get(target)===0)q.push(target);}}
    if(out.length!==state.nodes.length) throw new Error("工作流存在循环，请先移除循环连接。"); return out;
  }

  function requiredNodeOrder(targetId){
    return requiredNodesFor(targetId);
  }

  function requiredNodesFor(targets){
    const targetSet=targets instanceof Set?targets:new Set(Array.isArray(targets)?targets:[targets]);
    const required=new Set();
    const isSelectiveRun=Boolean(targetSet.size);
    const visit=id=>{
      if(required.has(id))return;
      required.add(id);
      for(const edge of state.edges.filter(item=>item.target===id)){
        const src=nodeById(edge.source);
        if(!src)continue;
        // 1. 文本与基础数据节点始终递归遍历解析
        if(['prompt','negativePrompt','textAppend','textConcat','imageInput','imageResize','references'].includes(src.type)){
          visit(edge.source);
          continue;
        }
        // 2. 生成类节点（图片/视频）：区分已就绪资产与选择性运行策略
        if(['generateImage','generateVideo'].includes(src.type)){
          if(isSelectiveRun && !targetSet.has(src.id)){
            const hasExistingAsset = Boolean(src.data?.asset?.url || (edge.sourcePort === 'endFrame' && src.data?.endFrame?.url));
            if(hasExistingAsset){
              // 上游产出已存在，直接供下游使用，无需将其重新加入待跑列表
              continue;
            }
            // 上游视频未就绪时，单节点运行不递归级联拉入前序视频（运行时平滑降级）
            if(src.type==='generateVideo'){
              continue;
            }
            // 上游图片若未就绪且下游视频需要其作为参考图，则必须先生成该图片
            if(src.type==='generateImage'){
              visit(edge.source);
              continue;
            }
          }
          visit(edge.source);
        }
      }
    };
    targetSet.forEach(id=>visit(id));return topoOrder().filter(id=>required.has(id));
  }

  function validateTargetPrompt(targetId){
    const target=nodeById(targetId);if(!target||!['generateImage','generateVideo'].includes(target.type))throw new Error("所选生成节点已不存在。");
    const prompt=resolvePrompt(targetId);if(prompt.trim())return prompt;
    const edge=getIncoming(targetId,'prompt')[0],source=edge&&nodeById(edge.source);
    const detail=!edge?"请将提示词或文本节点连接到此节点的提示词输入端口。":!source?"相连的提示词节点已不存在。":`相连的 ${nodeDefs[source.type]?.title||'text'}节点没有文本内容。`;
    target.data.status='error';target.data.error=detail;
    render();throw new Error(`${nodeDefs[target.type]?.title||"生成节点"} ${target.id}: ${detail}`);
  }

  let preferredMuseTabId=null;
  function t05Probe(stage, fields = {}) {
    try {
      const record = {
        testId: "T05",
        source: "app",
        stage,
        ts: Date.now(),
        requestId: String(fields.requestId || ""),
        nodeId: String(fields.nodeId || ""),
        status: String(fields.status || ""),
        width: Number(fields.width || 0),
        height: Number(fields.height || 0),
        errorCode: String(fields.errorCode || "").replace(/[^\w.-]/g, "").slice(0, 80),
        hasMedia: Boolean(fields.hasMedia)
      };
      const key = `t05_diag:${record.requestId}:${Math.random().toString(36).slice(2, 8)}`;
      void chrome.storage.local.set({ [key]: record }).catch(() => {});
      console.log(`[T05-PROBE] ${stage}: ` + JSON.stringify(record));
    } catch {}
  }
  async function museTabMessage(message, preferredTabId, signal) {
    if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');
    const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
    if(!tabs.length)throw new Error("请打开 Muse.ai 并登录，然后重试。");
    const preferred=preferredTabId??preferredMuseTabId;
    if(preferred){const index=tabs.findIndex(tab=>tab.id===preferred);if(index>0)tabs.unshift(tabs.splice(index,1)[0]);}
    let lastError='';
    for(const tab of tabs){
      if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');
      if(!tab.id)continue;
      try{await chrome.scripting.executeScript({target:{tabId:tab.id},files:['muse-bridge.js']});}catch{}
      try{const response=await sendMuseTabMessage(tab.id,message,signal);preferredMuseTabId=tab.id;return response;}catch(error){if(error?.name==='AbortError')throw error;lastError=error?.message||String(error);}
      if(message?.type === 'MUSEFLOW_GENERATE' || message?.type === 'MUSEFLOW_GENERATE_V3') {
        throw new Error(`生成请求已发出但响应未确认（防止重复提交扣除额度）：${lastError||"通信异常"}`);
      }
      try{
        await chrome.scripting.executeScript({target:{tabId:tab.id},files:['muse-bridge.js']});
        const response=await sendMuseTabMessage(tab.id,message,signal);preferredMuseTabId=tab.id;return response;
      }catch(error){if(error?.name==='AbortError')throw error;lastError=error?.message||String(error);}
    }
    throw new Error(`已找到 Muse 标签页，但 MuseFlow 无法连接页面桥接脚本：${lastError||"未知浏览器错误"}。请在浏览器扩展设置中检查 Muse 网站访问权限，然后重试。`);
  }

  function sendMuseTabMessage(tabId,message,signal){
    if(!signal)return chrome.tabs.sendMessage(tabId,message);
    if(signal.aborted)return Promise.reject(new DOMException("用户已停止生成。",'AbortError'));
    return new Promise((resolve,reject)=>{
      let settled=false;
      const finish=(fn,value)=>{if(settled)return;settled=true;signal.removeEventListener('abort',onAbort);fn(value);};
      const onAbort=()=>finish(reject,new DOMException("用户已停止生成。",'AbortError'));
      signal.addEventListener('abort',onAbort,{once:true});
      chrome.tabs.sendMessage(tabId,message).then(value=>finish(resolve,value),error=>finish(reject,error));
    });
  }

  function stopGeneration(nodeId=state.activeGenerationId){
    if(!nodeId)return;
    const node=nodeById(nodeId);
    if(!node||node.data.status!=='running')return;
    const requestId=state.activeGenerationId===nodeId?state.generationRequestId:null;
    if(state.activeGenerationId===nodeId)state.generationAbortController?.abort();
    if(node){node.data.status='stopped';node.data.error="用户已停止生成。";}
    setRunStatus(`已停止 ${node?.type==='generateVideo'?'视频':'图片'}生成：${nodeId}`,'warn');
    render();
    // Cancellation is best-effort for Muse, but never wait for its response to unlock the UI.
    void sendMuseStop(requestId);
    try{clearTimeout(autoSaveTimer);void queueWorkflowSave();}catch{}
  }

  async function sendMuseStop(requestId){
    try{
      const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
      const ordered=preferredMuseTabId?tabs.sort((a,b)=>(b.id===preferredMuseTabId)-(a.id===preferredMuseTabId)):tabs;
      await Promise.allSettled(ordered.filter(tab=>tab.id).map(tab=>chrome.tabs.sendMessage(tab.id,{type:'MUSEFLOW_STOP_GENERATION',requestId})));
    }catch{}
  }

  async function testMuseSession(preferredTabId) {
    const button=$('#testMuseBtn'),status=$('#connectionStatus');
    if(button)button.disabled=true;
    status.className='warn';status.textContent="正在检查 Muse 会话…";
    try{
      const result=await museTabMessage({type:'MUSEFLOW_CHECK_SESSION'},preferredTabId);
      const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
      const checked=tabs.find(tab=>tab.id===preferredTabId)||tabs.find(tab=>tab.active)||tabs[0];
      if(checked?.id)preferredMuseTabId=checked.id;
      const ready=Boolean(result.composer&&result.signedIn);
      status.className=ready?'ok':'warn';
      status.textContent=ready?"Muse 会话已连接。":result.loginRequired?"Muse 要求登录。请在 Muse 标签页登录后重新检查。":result.composer?"Muse 聊天已就绪，暂时无法确认会话状态；可以尝试生成。":"已找到 Muse 标签页，但聊天输入框尚未就绪。请打开 Muse 聊天后重试。";
      museStatus.textContent=ready?"● Muse 会话已就绪":"● 请检查 Muse 会话";
      museStatus.className=ready?'ok':result.loginRequired?'warn':'ok';
      if(!ready&&!result.loginRequired){museStatus.textContent="● Muse 聊天已就绪 · 会话未确认";}
      return ready||Boolean(result.composer&&!result.loginRequired);
    }catch(error){
      status.className='error';status.textContent=error.message;
      museStatus.textContent="● Muse 会话检查失败";museStatus.className='error';
      return false;
    }finally{if(button)button.disabled=false;}
  }

  async function execute(targetId=null,{forceAll=false,onlyType=null}={}) {
    if(state.isRunning)return;
    // Keep runtime graph references valid even if an older saved workflow or
    // an interrupted UI action left stale node IDs behind.
    normalizeSavedGraph();
    // 由 normalizeSavedGraph() 统一执行精确恢复，杜绝盲目重置
    const targetSet=targetId?(Array.isArray(targetId)||targetId instanceof Set?new Set(targetId):new Set([targetId])):null;
    const abortController=new AbortController();state.generationAbortController=abortController;state.activeGenerationId=targetSet?[...targetSet][0]:null;state.isRunning=true;$('#runBtn').disabled=false;$('#runBtn').textContent="■ 停止";
    const defaultModeText = onlyType==='generateImage'?"正在阶段一运行：仅批量生成分镜图片（不生成视频）…":onlyType==='generateVideo'?"正在阶段二运行：仅依据底图生成视频（跳过生图）…":forceAll?"正在全量重新运行工作流…":"正在智能运行工作流（跳过未变更节点）…";
    setRunStatus(targetSet?(targetSet.size===1?`正在运行所选节点：${[...targetSet][0]}…`:`正在运行 ${targetSet.size} 个所选节点…`):defaultModeText,'warn');
    try{
      if(targetSet){for(const tid of targetSet)validateTargetPrompt(tid);}
      const order=targetSet?requiredNodesFor(targetSet):topoOrder();
      for(const n of state.nodes){
        if(n.type==='imageInput'&&n.data.localDataUrl)n.data.asset={id:n.data.asset?.id||uid('asset'),kind:'image',url:n.data.localDataUrl,sourceNodeId:n.id};
      }
      const nodesToGenerate=[];
      let skippedCount=0;
      for(const id of order){
        const n=nodeById(id);
        if(!n||!['generateImage','generateVideo'].includes(n.type))continue;
        if(onlyType&&n.type!==onlyType)continue;
        const isTarget=targetSet?targetSet.has(n.id):false;

        // 关键安全防线：若节点处于 submission_unknown 状态，且未被用户单独显式选中：
        // 绝对禁止全量工作流自动重新向 Muse 发起生成请求！
        if(n.data.status==='submission_unknown' && !isTarget){
          console.warn(`[MuseFlow] 节点 ${n.id} 处于 submission_unknown 状态，跳过自动提交以防重复生成。`);
          skippedCount++;
          continue;
        }

        const hasAsset=Boolean(n.data.asset?.url);
        const isSuccess=n.data.status==='success';
        const isDirty=Boolean(n.data.dirty);
        let shouldRun=false;
        if(isTarget)shouldRun=true;
        else if(targetSet)shouldRun=false;
        else if(forceAll)shouldRun=true;
        else shouldRun=!hasAsset||!isSuccess||isDirty;
        if(shouldRun)nodesToGenerate.push(n.id);
        else{
          skippedCount++;
          if(n.type==='generateVideo'&&n.data.asset?.url&&!n.data.endFrame){
            try{n.data.endFrame=await extractVideoEndFrame(n.data.asset.url);}catch{}
          }
        }
      }
      if(nodesToGenerate.length===0){
        setRunStatus(skippedCount>0?`所有 ${skippedCount} 个生成节点均已完成且未变更，已跳过。`:"没有需要生成的节点。",'ok');
        return;
      }
      for(const id of nodesToGenerate){
        const targetNode=nodeById(id);
        if(targetNode&&targetNode.data.status!=='running')targetNode.data.status='pending';
      }
      render();
      let generationStep=0;
      const totalGenerations=nodesToGenerate.length;
      const succeededNodes=[];
      const failedNodes=[];
      const skippedDependencyNodes=[];
      // 先同步运行 imageResize 尺寸调整节点
      for(const id of order){
        const n=nodeById(id);
        if(n&&n.type==='imageResize'){
          const source=sourceFor(getIncoming(n.id,'image')[0]);const url=source?.data?.localDataUrl||source?.data?.asset?.url;
          if(!url){setRunStatus("“调整图片尺寸”节点正在等待输入图片。",'warn');continue;}
          const image=await loadImage(url),canvas=document.createElement('canvas');drawResized(image,canvas,n.data);
          const resized=canvas.toDataURL('image/png');n.data.asset={id:uid('asset'),kind:'image',url:resized,name:`已调整尺寸：${n.data.width}×${n.data.height}`,width:canvas.width,height:canvas.height,sourceNodeId:n.id};
          state.edges.filter(e=>e.source===n.id).forEach(e=>{const target=nodeById(e.target);if(target?.type==='preview')target.data.asset=n.data.asset;});
          render();
        }
      }

      // 受控并发池设置 (AC-010: 本地生图模型多图并发制作·系统显存与内存安全保护)
      const configuredConc = Number(state.settings?.localImageConcurrency);
      const maxLocalConcurrency = Math.max(1, Math.min(4, Number.isFinite(configuredConc) ? configuredConc : 2));

      function isLocalImageNode(node) {
        if (!node || node.type !== 'generateImage') return false;
        const isLocalProvider = (state.settings?.imageProvider || 'local') === 'local';
        const isLocalModel = node.data.model !== 'muse-image' && (isLocalProvider || !BUILTIN_IMAGE_MODELS.some(m => m.id === node.data.model));
        return isLocalProvider || isLocalModel;
      }

      function getPendingDependencies(nodeId) {
        const n = nodeById(nodeId);
        if (!n) return [];
        const deps = [];
        // 1. 连线上游中待生成但尚未成功的节点
        for (const edge of state.edges) {
          if (edge.target === nodeId) {
            const src = nodeById(edge.source);
            if (src && nodesToGenerate.includes(src.id)) {
              if (!succeededNodes.includes(src.id) && (src.data?.status !== 'success' || !src.data?.asset?.url)) {
                if (!failedNodes.some(f => f.id === src.id)) {
                  deps.push(src.id);
                }
              }
            }
          }
        }
        // 2. 视频连续性依赖
        if (n.type === 'generateVideo' && n.data?.continuity && !hasDirectKeyframe(n.id)) {
          const prevVid = timelinePredecessor(n.id);
          if (prevVid && nodesToGenerate.includes(prevVid.id)) {
            if (!succeededNodes.includes(prevVid.id) && (prevVid.data?.status !== 'success' || !prevVid.data?.asset?.url)) {
              if (!failedNodes.some(f => f.id === prevVid.id)) {
                deps.push(prevVid.id);
              }
            }
          }
        }
        // 3. 图片画风连续性依赖 (styleContinuity: 防止画风走偏，严格等待前置底图就绪)
        if (n.type === 'generateImage' && n.data?.styleContinuity) {
          const prevImg = previousImageNode(n.id);
          if (prevImg && nodesToGenerate.includes(prevImg.id)) {
            if (!succeededNodes.includes(prevImg.id) && (prevImg.data?.status !== 'success' || !prevImg.data?.asset?.url)) {
              if (!failedNodes.some(f => f.id === prevImg.id)) {
                deps.push(prevImg.id);
              }
            }
          }
        }
        return [...new Set(deps)];
      }

      async function executeSingleNode(n) {
        if (abortController.signal.aborted) throw new DOMException("用户已停止生成。", 'AbortError');
        const isVideo = n.type === 'generateVideo';
        generationStep++;
        const prompt = resolvePrompt(n.id);
        const negativePrompt = resolveNegativePrompt(n.id);
        const ownKeyframe = isVideo && hasDirectKeyframe(n.id);
        const usePrevEndFrame = Boolean(isVideo && n.data.continuity && !ownKeyframe);
        const continuityPrevious = usePrevEndFrame ? timelinePredecessor(n.id) : null;
        let continuityStartFrame = continuityPrevious?.data?.endFrame?.url ? continuityPrevious.data.endFrame : null;
        if (usePrevEndFrame && !continuityStartFrame && continuityPrevious?.data?.asset?.url) {
          try {
            continuityPrevious.data.endFrame = await extractVideoEndFrame(continuityPrevious.data.asset.url);
            continuityStartFrame = continuityPrevious.data.endFrame;
          } catch {}
        }
        let continuityNotice = '';
        if (usePrevEndFrame && !continuityStartFrame) {
          if (continuityPrevious?.data?.endFrameStatus === 'failed') {
            n.data.status = 'blocked';
            n.data.errorType = 'CONTINUITY_FRAME_FAILED';
            n.data.error = `前序镜头 ${continuityPrevious.id} 尾帧提取失败，无法进行首尾帧连续生成。`;
            skippedDependencyNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
            render();
            setRunStatus(`节点 ${n.id} 依赖的前序尾帧提取失败，已安全阻断；请先重试前序镜头尾帧。`, 'warn');
            return { ok: false, skipped: true };
          }
          n.data.continuityDegraded = true;
          continuityStartFrame = null;
          continuityNotice = '（前置未就绪，按独立分镜生成）';
        }
        const referenceImages = resolveReferences(n.id);
        if (!String(prompt).trim() && referenceImages.length === 0) {
          n.data.status = 'blocked';
          n.data.errorType = 'MISSING_DEPENDENCY';
          n.data.error = `${nodeDefs[n.type].title} ${n.id}：缺少提示词输入且无有效参考图。`;
          skippedDependencyNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
          render();
          setRunStatus(`节点 ${n.id} 因缺少输入已阻断并跳过；正在推进后续节点…`, 'warn');
          return { ok: false, skipped: true };
        }
        state.activeGenerationId = n.id;
        const currentRunToken = uid('runToken');
        n.data.activeRunToken = currentRunToken;
        const currentRevision = (n.data.sourceRevision || 0) + 1;
        n.data.sourceRevision = currentRevision;
        const diagItem = {
          id: uid('diag'),
          workflowId: state.workflowId || 'default-workflow',
          nodeId: n.id,
          nodeType: n.type,
          attemptId: currentRunToken,
          startTime: Date.now(),
          status: 'running',
          model: n.data.model || (isVideo ? 'muse-video' : 'muse-image'),
          versionId: null,
          qualityStatus: 'unchecked',
          durationMs: 0,
          errorType: null,
          errorMessage: null
        };
        if (!Array.isArray(state.executionDiagnostics)) state.executionDiagnostics = [];
        state.executionDiagnostics.push(diagItem);
        n.data.status = 'running';
        n.data.error = '';
        ensureNodeVersions(n);
        state.edges.filter(edge => edge.source === n.id).forEach(edge => {
          const target = nodeById(edge.target);
          if (target?.type === 'preview') target.data.asset = null;
        });
        render();

        try {
          let kind = isVideo ? 'video' : 'image';
          let url = '';
          let candidates = [];
          let reviewNotes = n.data?.reviewNotes || '';
          let bridgeWidth = 0, bridgeHeight = 0, bridgeDuration = 0;
          const isLocalProvider = (state.settings?.imageProvider || 'local') === 'local';
          const isLocalModel = n.data.model !== 'muse-image' && (isLocalProvider || !BUILTIN_IMAGE_MODELS.some(m => m.id === n.data.model));
          const styleConsistencyGuide = (!isVideo && referenceImages.length > 0) ? '\n\n[STYLE & VISUAL CONTINUITY]: Match the exact artistic style, character features, color palette, lighting and rendering quality of the attached reference image(s). Prevent any style drift or quality deviation across scenes.' : '';
          const compiledPrompt = `${prompt}${styleConsistencyGuide}`;

          if (!isVideo && (isLocalProvider || isLocalModel)) {
            const modelName = n.data.model || state.settings?.defaultImageModel || 'flux-1-dev';
            const localRes = await generateImageLocally(n, { prompt: compiledPrompt, negativePrompt, referenceImages, signal: abortController.signal });
            if (!localRes) throw new Error("本地生图 API 未返回图片内容。");
            if (Array.isArray(localRes)) {
              candidates = localRes.map(u => ({ id: uid('cand'), url: u }));
              url = candidates[0].url;
            } else {
              candidates = [{ id: uid('cand'), url: localRes }];
              url = localRes;
            }
          } else {
            const museVideoDuration = 10;
            const sanitizedVideoPrompt = isVideo
              ? String(prompt || '')
                  .replace(/Create a \d+(?:\.\d+)?s\b/gi, 'Create a 10s full uncut')
                  .replace(/\b[2-6](?:\.\d+)?\s*(?:s|sec|seconds)\b/gi, '10s')
              : prompt;
            const startRef = referenceImages.find(r => r.role === 'start');
            const endRef = referenceImages.find(r => r.role === 'end');
            const extraRefs = referenceImages.filter(r => r !== startRef && r !== endRef);
            const sizeInstruction = `Output aspect ratio: ${n.data.size}. Match this frame shape exactly. ${n.data.size === '16:9' ? 'Use a wide landscape composition.' : n.data.size === '9:16' ? 'Use a tall portrait composition.' : n.data.size === '1:1' ? 'Use a square composition.' : n.data.size === '4:3' ? 'Use a standard landscape composition.' : 'Use a standard portrait composition.'}`;
            const continuityInstruction = continuityStartFrame ? 'CONTINUITY LOCK: Attached image 1 is the exact final frame of the previous Timeline clip. Use image 1 as the exact first frame of this video: preserve its subject identity, pose, position, camera angle, crop, lighting, and background. Continue motion naturally from that precise moment. No reset, jump, flash, dissolve, or scene change at the start.' : '';
            const keyframeInstruction = (isVideo && ownKeyframe)
              ? (endRef
                  ? `START & END KEYFRAME LOCK + MULTI-IMAGE REFERENCE (${referenceImages.length}/9 images attached): Attached Image 1 (${startRef?.name || 'Start Frame'}) is the EXACT START KEYFRAME (0.0s opening frame). Attached Image 2 (${endRef.name || 'End Frame'}) is the TARGET END KEYFRAME (closing frame state). Smoothly animate the subject and camera movement from Image 1 toward the final composition of Image 2 over the full 10-second shot.${extraRefs.length ? ` Attached Image${extraRefs.length === 1 ? ' 3 is a' : `s 3 to ${referenceImages.length} are`} character, prop, Chinese text, and 3D style reference sheet(s) — maintain strict visual and character consistency.` : ''}`
                  : `PRIMARY SHOT KEYFRAME + MULTI-IMAGE REFERENCE (${referenceImages.length}/9 images attached): Attached Image 1 (${startRef?.name || 'Start Frame'}) is the dedicated opening keyframe for THIS shot. Base the opening frame, scene setting, subject placement, and action directly on Image 1 and the prompt below (do NOT stay in a previous shot's scene).${extraRefs.length ? ` Attached Image${extraRefs.length === 1 ? ' 2 is a' : `s 2 to ${referenceImages.length} are`} character, prop, and style consistency reference sheet(s).` : ''}`)
              : '';
            const audioRequirement = isVideo ? 'AUDIO IS REQUIRED: Return a video with audible, synchronized sound; do not make a silent clip. Follow the requested audio direction and make its music and sound effects clearly audible. Do not add spoken dialogue unless the prompt asks for it.' : '';
            const modelDirective = (!isVideo && n.data.model && n.data.model !== 'muse-image') ? `\n\n[Model: ${n.data.model}] Use ${n.data.model} model.` : '';
            const musePrompt = isVideo ? `Create a ${n.data.size} aspect ratio video clip, ${museVideoDuration} seconds long (return the full 10-second raw generated video directly; do NOT trim or cut into a shorter 3s clip). ${sizeInstruction}\n\n${audioRequirement}${continuityInstruction ? `\n\n${continuityInstruction}` : ''}${keyframeInstruction ? `\n\n${keyframeInstruction}` : ''}${referenceImages.length ? `\n\nUse the attached reference image${referenceImages.length === 1 ? '' : 's'} as visual guidance${continuityStartFrame ? ' while keeping image 1 as the exact opening frame.' : ownKeyframe ? (endRef ? ' with Image 1 as the exact opening frame and Image 2 as the target closing frame.' : ' with Image 1 as this shot\'s primary scene keyframe.') : '.'}` : ''}\n\nPrompt: ${sanitizedVideoPrompt}${negativePrompt ? `\n\nAvoid: ${negativePrompt}` : ''}` : `${prompt}${referenceImages.length ? '\n\nUse the attached reference image' + (referenceImages.length === 1 ? '' : 's') + ' as visual guidance; follow the prompt while preserving relevant subject details.' : ''}${styleConsistencyGuide}\n\n${sizeInstruction}${negativePrompt ? `\n\nAvoid the following (negative prompt): ${negativePrompt}` : ''}${modelDirective}`;
            const generationRequest = { type: 'MUSEFLOW_GENERATE_V3', requestId: uid('generation'), prompt: musePrompt, negativePrompt, size: n.data.size, model: n.data.model || 'muse-image', duration: isVideo ? museVideoDuration : n.data.duration, mediaType: isVideo ? 'video' : 'image', referenceImages: referenceImages.slice(0, 9).map(item => item.url), timeoutSec: 300 };
            state.generationRequestId = generationRequest.requestId;

            // 写入提交指纹与三元组版本锁
            n.data.pendingRequestId = generationRequest.requestId;
            n.data.submittedToMuse = true;
            n.data.submittedTime = Date.now();
            n.data.baseAssetVersionId = n.data.activeVersionId || n.data.asset?.id || null;
            queueWorkflowSave();

            let reply = await museTabMessage(generationRequest, preferredMuseTabId, abortController.signal);
            if (abortController.signal.aborted) throw new DOMException("用户已停止生成。", 'AbortError');
            if (!reply?.ok && reply?.code === 'SCENE_REFUSED') {
              setRunStatus(`Muse 无法生成 ${n.data.sceneLabel || "此场景"}；正在使用接近原意且符合要求的方案重试一次…`, 'warn');
              const retryRequest = { ...generationRequest, prompt: `${musePrompt}\n\nSAFE EQUIVALENT RETRY: The previous version could not be generated. Create a close, allowed alternative for the same scene now. Stay faithful to the script's story purpose, characters, relationship, setting, action, mood, visual style, framing, continuity, and requested duration/aspect ratio. Change only the specific detail that prevents generation, replacing it with the nearest safe equivalent. Keep this scene in the story; do not skip it or change what it needs to accomplish. Do not ask a follow-up question or ask permission; generate the alternative in this attempt. Follow all content and safety rules.` };
              reply = await museTabMessage(retryRequest, preferredMuseTabId, abortController.signal);
            }
            if (abortController.signal.aborted) throw new DOMException("用户已停止生成。", 'AbortError');
            if (!reply?.ok && reply?.code === 'SCENE_REFUSED') {
              n.data.status = 'failed';
              diagItem.status = 'failed';
              diagItem.errorType = 'SCENE_REFUSED';
              diagItem.errorMessage = n.data.error;
              diagItem.durationMs = Date.now() - diagItem.startTime;
              n.data.errorType = 'SCENE_REFUSED';
              n.data.error = 'Muse AI 拒绝生成此场景（已尝试合规替代重试）。';
              failedNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
              render();
              setRunStatus(`节点 ${n.id} 被 AI 拒绝生成，已跳过；正在推进后续节点…`, 'warn');
              return { ok: false, error: n.data.error };
            }
            if (!reply?.ok && (reply?.code === 'OUT_OF_CREDITS' || reply?.code === 'LOGIN_REQUIRED' || /out of credits|insufficient credits|额度不足|登录/i.test(reply?.error || ''))) {
              n.data.status = 'failed';
              diagItem.status = 'failed';
              diagItem.errorType = reply?.code || 'OUT_OF_CREDITS';
              diagItem.errorMessage = n.data.error;
              diagItem.durationMs = Date.now() - diagItem.startTime;
              n.data.errorType = reply?.code || 'OUT_OF_CREDITS';
              n.data.error = reply?.error || (reply?.code === 'OUT_OF_CREDITS' ? "Muse 账号额度已耗尽。" : "Muse 登录已失效。");
              failedNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
              render();
              setRunStatus(`工作流已安全暂停：${n.data.error}。已保存当前所有成功结果。`, 'error');
              return { ok: false, fatal: true, error: n.data.error };
            }
            if (!reply?.ok) {
              if (reply?.reviewNotes) n.data.reviewNotes = reply.reviewNotes;
              throw new Error(reply?.error || `Muse.ai 未返回生成的${isVideo ? 'video' : 'image'}.`);
            }
            const replyLooksTrimmed = isVideo && (
              (Number(reply.width) === 480 && Number(reply.height) === 480) ||
              (Number(reply.duration) > 0 && Number(reply.duration) < 8) ||
              /trim|cut|clip|first\d+s|mid\d+|[-_]\d+(?:\.\d+)?s(?:\b|\.mp4)/i.test(`${reply.label || ''} ${reply.url || ''}`) ||
              String(reply.url || '').startsWith('blob:https://muse.ai/')
            );
            if (replyLooksTrimmed) {
              try {
                const directReply = await runDirectVideoRecovery({ size: n.data.size || '16:9', duration: 10, prompt: prompt || '', sceneLabel: n.data.sceneLabel || '' });
                if (directReply?.ok && directReply?.url) reply = directReply;
              } catch {}
            }
            bridgeWidth = Number(reply.width) || 0;
            bridgeHeight = Number(reply.height) || 0;
            bridgeDuration = Number(reply.duration) || 0;
            url = isVideo ? await ensureLocalPlayableVideoUrl(reply.url) : await persistImage(reply.url);
            reviewNotes = reply.reviewNotes || '';
            n.data.reviewNotes = reviewNotes;
            if (!url) throw new Error(`Muse.ai 返回了空的${mediaText(kind)}附件。`);
            candidates = [{ id: uid('cand'), url }];
          }

          const expectedRequestId = n.data.pendingRequestId;
          // 异步版本隔离检查 1：校验 runToken、sourceRevision 与 pendingRequestId
          if (n.data.activeRunToken !== currentRunToken || n.data.sourceRevision !== currentRevision || (expectedRequestId && n.data.pendingRequestId !== expectedRequestId)) {
            console.warn(`[MuseFlow] 检测到已过期的晚到结果 (runToken/revision/requestId 不匹配)，已自动丢弃以防串入新任务：节点 ${n.id}`);
            diagItem.status = 'discarded_late';
            diagItem.errorType = 'LATE_RESULT_DISCARDED';
            diagItem.errorMessage = '检测到已过期的晚到结果，已自动丢弃';
            diagItem.durationMs = Date.now() - diagItem.startTime;
            return { ok: false, discarded: true };
          }

          let intrinsic = await mediaDimensions(url, isVideo ? 'video' : 'image', 10000);
          if (isVideo && ((intrinsic.width === 480 && intrinsic.height === 480) || (Number(intrinsic.duration) > 0 && Number(intrinsic.duration) < 8))) {
            const directReply = await runDirectVideoRecovery({ size: n.data.size || '16:9', duration: 10, prompt: prompt || '', sceneLabel: n.data.sceneLabel || '' });
            if (directReply?.ok && directReply?.url) {
              url = await ensureLocalPlayableVideoUrl(directReply.url);
              candidates = [{ id: uid('cand'), url }];
              bridgeWidth = Number(directReply.width) || 1280;
              bridgeHeight = Number(directReply.height) || 720;
              bridgeDuration = Number(directReply.duration) || 10;
              intrinsic = await mediaDimensions(url, 'video', 6000);
            }
          }
          if (isVideo && intrinsic.timeout) {
            if (bridgeWidth > 0 && bridgeHeight > 0) {
              intrinsic = { width: bridgeWidth, height: bridgeHeight, duration: bridgeDuration || 10 };
            } else {
              console.warn(`[MuseFlow] 首次视频元数据探测超时 (10s)，对同一视频资产进行单次受控重试探测...`);
              await delay(600, abortController.signal);
              intrinsic = await mediaDimensions(url, 'video', 6000);
            }
          }
          if (isVideo && (!intrinsic.width || !intrinsic.height)) {
            const fbDim = fallbackDimensionsByRatio(n.data.size);
            intrinsic = {
              width: bridgeWidth || fbDim.width,
              height: bridgeHeight || fbDim.height,
              duration: intrinsic.duration || bridgeDuration || 10
            };
          }

          // 异步版本隔离检查 2：媒体验证耗时后的抢占与版本隔离校验
          if (n.data.activeRunToken !== currentRunToken || n.data.sourceRevision !== currentRevision || (expectedRequestId && n.data.pendingRequestId !== expectedRequestId)) {
            console.warn(`[MuseFlow] 媒体验证期间任务已被抢占或版本已迭代，放弃资产回填：节点 ${n.id}`);
            diagItem.status = 'discarded_late';
            diagItem.errorType = 'LATE_RESULT_DISCARDED';
            diagItem.errorMessage = '媒体验证期间任务已被抢占，放弃资产回填';
            diagItem.durationMs = Date.now() - diagItem.startTime;
            return { ok: false, discarded: true };
          }

          if (isVideo && intrinsic.timeout) {
            n.data.status = 'failed';
            n.data.mediaStatus = 'metadata_timeout';
            n.data.errorType = 'MEDIA_METADATA_TIMEOUT';
            n.data.error = '已获取 Muse 视频链接，但视频流元数据加载超时（可能受限于网络或跨域加载延迟）。已保留视频地址，可在节点中尝试预览或刷新重试。';
            diagItem.status = 'failed';
            diagItem.errorType = 'MEDIA_METADATA_TIMEOUT';
            diagItem.errorMessage = n.data.error;
            diagItem.durationMs = Date.now() - diagItem.startTime;
            n.data.candidates = candidates;
            n.data.unverifiedUrl = url;
            failedNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
            render();
            setRunStatus(`节点 ${n.id} 媒体验证超时：${n.data.error}`, 'warn');
            return { ok: false, error: n.data.error };
          }

          const actualRatio = intrinsic.width && intrinsic.height ? intrinsic.width / intrinsic.height : 0;
          const expectedRatio = ratioValue(n.data.size);
          const sizeMismatch = Boolean(actualRatio && isVideo && Math.abs(Math.log(actualRatio / expectedRatio)) > 0.09);
          if (sizeMismatch) {
            console.warn(`[MuseFlow] 节点 ${n.id} 视频实际尺寸为 ${intrinsic.width} × ${intrinsic.height}，与请求的 ${n.data.size}宽高比不符，已作为容错警告记录并保留视频成果`);
            setRunStatus(`节点 ${n.id} 生成的视频比例与请求略有不同（实际 ${intrinsic.width}×${intrinsic.height}，请求 ${n.data.size}），已正常回填可供预览使用`, 'warn');
          }
          
          t05Probe('VIDEO_READY', { requestId: currentRunToken, nodeId: n.id, width: intrinsic.width, height: intrinsic.height, status: 'ready', hasMedia: true });

          ensureNodeVersions(n);
          const qualityReport = inspectMediaQuality({
            url,
            kind,
            width: intrinsic.width,
            height: intrinsic.height,
            duration: intrinsic.duration,
            size: n.data.size,
            isVideo,
            requestedDuration: n.data.duration,
            reviewNotes
          });
          const newVerNumber = (n.data.versions?.length || 0) + 1;
          const newVerId = uid('ver');
          
          const newVersion = {
            id: newVerId,
            versionNumber: newVerNumber,
            name: `版本 ${newVerNumber}`,
            kind,
            url,
            model: n.data.model || (isVideo ? 'muse-video' : 'muse-image'),
            prompt,
            createdAt: Date.now(),
            width: intrinsic.width,
            height: intrinsic.height,
            candidates: candidates || [],
            quality: qualityReport
          };
          n.data.versions.push(newVersion);
          n.data.activeVersionId = newVerId;
          n.data.candidates = candidates;
          n.data.selectedCandidateIndex = 0;
          n.data.asset = {
            id: newVerId,
            kind,
            url,
            name: `${isVideo ? "视频" : "图片"} ${n.id} (V${newVerNumber})`,
            sourceNodeId: n.id,
            versionNumber: newVerNumber,
            width: intrinsic.width,
            height: intrinsic.height,
            requestedSize: n.data.size,
            sizeMismatch: sizeMismatch,
            quality: qualityReport
          };
          // 遵守评审规范：保留原有 status='success' 兼容性，附加独立媒体状态
          n.data.status = 'success';
          n.data.mediaStatus = 'verified';
          // 资产已成功回填并就绪，清理提交状态与待处理标记
          delete n.data.submittedToMuse;
          delete n.data.pendingRequestId;
          delete n.data.submittedTime;
          delete n.data.baseAssetVersionId;
          // 资产已成功回填并就绪，清理提交状态与待处理标记
          delete n.data.submittedToMuse;
          delete n.data.pendingRequestId;
          delete n.data.submittedTime;
          delete n.data.baseAssetVersionId;
          n.data.endFrameStatus = isVideo ? 'pending' : 'none';
          n.data.persistStatus = 'pending';
          diagItem.status = 'succeeded';
          diagItem.versionId = newVerId;
          diagItem.qualityStatus = qualityReport?.status || 'passed';
          diagItem.durationMs = Date.now() - diagItem.startTime;
          n.data.dirty = false;
          succeededNodes.push(n.id);
          
          state.edges.filter(e => e.source === n.id).forEach(e => {
            const target = nodeById(e.target);
            if (target?.type === 'preview') target.data.asset = n.data.asset;
          });
          render();

          // 附属任务独立管理 (P0-5: 尾帧与持久化独立运行与错误隔离)
          t05Probe('POSTPROCESS_STARTED', { requestId: currentRunToken, nodeId: n.id });
          let endFrame = null;
          if (isVideo) {
            try {
              endFrame = await extractVideoEndFrame(url);
              // 异步版本隔离检查 3：校验 activeVersionId、sourceRevision 与 activeRunToken
              if (endFrame) {
                if (n.data.activeVersionId === newVerId && n.data.sourceRevision === currentRevision && n.data.activeRunToken === currentRunToken) {
                  n.data.endFrame = endFrame;
                  n.data.endFrameStatus = 'success';
                  newVersion.endFrame = endFrame;
                  state.edges.filter(e => e.source === n.id && e.sourcePort === 'endFrame').forEach(e => {
                    const target = nodeById(e.target);
                    if (target?.type === 'preview') target.data.asset = endFrame;
                  });
                } else {
                  console.warn(`[MuseFlow] 尾帧截取完成但资产版本已变更 (activeVersion=${n.data.activeVersionId}, expected=${newVerId})，丢弃过期尾帧。`);
                }
              } else {
                if (n.data.activeVersionId === newVerId) {
                  n.data.endFrameStatus = 'failed';
                  n.data.endFrameError = '尾帧截取超时或跨域限制';
                }
              }
            } catch (efErr) {
              if (n.data.activeVersionId === newVerId) {
                n.data.endFrameStatus = 'failed';
                n.data.endFrameError = efErr?.message || String(efErr);
              }
            }
          }
          if (n.data.activeVersionId === newVerId && n.data.sourceRevision === currentRevision) {
            n.data.persistStatus = 'verified';
          }
          t05Probe('POSTPROCESS_FINISHED', { requestId: currentRunToken, nodeId: n.id, endFrameStatus: n.data.endFrameStatus });
          t05Probe('JOB_SETTLED', { requestId: currentRunToken, nodeId: n.id, status: 'settled' });
          render();
          return { ok: true, id: n.id };
        } catch (err) {
          delete n.data.submittedToMuse;
          delete n.data.pendingRequestId;
          delete n.data.submittedTime;
          delete n.data.baseAssetVersionId;
          if (err?.name === 'AbortError' || abortController.signal.aborted) {
            diagItem.status = 'stopped';
            diagItem.errorType = 'USER_ABORTED';
            diagItem.errorMessage = '用户已停止生成。';
            diagItem.durationMs = Date.now() - diagItem.startTime;
            n.data.status = 'stopped'; n.data.error = "用户已停止生成。"; render();
            throw new DOMException("用户已停止生成。", 'AbortError');
          }
          n.data.status = 'failed';
          diagItem.status = 'failed';
          diagItem.errorType = err?.code || 'GENERATION_FAILED';
          diagItem.errorMessage = err?.message || String(err);
          diagItem.durationMs = Date.now() - diagItem.startTime;
          n.data.error = err?.message || String(err);
          n.data.errorType = err?.code || 'GENERATION_FAILED';
          failedNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
          render();
          setRunStatus(`节点 ${n.id} 生成失败：${n.data.error}。正在继续推进后续独立节点…`, 'warn');
          return { ok: false, error: n.data.error };
        }
      }

      // 受控并发池循环调度 (AC-010: 本地生图多图并发 + 独占互斥 + 动态补位)
      const remainingNodeIds = [...nodesToGenerate];
      const runningMap = new Map(); // nodeId -> Promise
      let activeLocalImageCount = 0;
      let activeExclusiveCount = 0;
      let hasFatalPause = false;

      function updateConcurrencyStatus() {
        const skipHint = skippedCount > 0 ? ` (跳过 ${skippedCount} 项)` : '';
        if (runningMap.size > 1) {
          const labels = [...runningMap.keys()].map(k => {
            const nd = nodeById(k);
            return nd?.data?.sceneLabel || k;
          }).join(', ');
          setRunStatus(`正在并发制作本地图片 (并发: ${runningMap.size}/${maxLocalConcurrency} · 运行中: ${labels} · 已完成 ${succeededNodes.length}/${totalGenerations}${skipHint})…`, 'warn');
        } else if (runningMap.size === 1) {
          const singleId = [...runningMap.keys()][0];
          const singleNode = nodeById(singleId);
          const isVid = singleNode?.type === 'generateVideo';
          const modelName = singleNode?.data?.model || (isVid ? 'muse-video' : (state.settings?.defaultImageModel || 'flux-1-dev'));
          const prefix = targetSet ? "所选节点" : `生成 ${succeededNodes.length + 1}/${totalGenerations}${skipHint}`;
          setRunStatus(`${prefix} · 正在生成 ${isVid ? '视频' : `本地图片(${modelName})`}: ${singleNode?.data?.sceneLabel || singleId}`, 'warn');
        }
      }

      while (remainingNodeIds.length > 0 || runningMap.size > 0) {
        if (abortController.signal.aborted) throw new DOMException("用户已停止生成。", 'AbortError');
        if (hasFatalPause) break;

        let dispatchedAny = false;
        for (let i = 0; i < remainingNodeIds.length; i++) {
          const candidateId = remainingNodeIds[i];
          const candidateNode = nodeById(candidateId);
          if (!candidateNode) {
            remainingNodeIds.splice(i, 1);
            i--;
            continue;
          }
          const pendingDeps = getPendingDependencies(candidateId);
          if (pendingDeps.length > 0) {
            // 存在未就绪前置，等待其完成后再调度
            continue;
          }
          const isLocal = isLocalImageNode(candidateNode);
          if (isLocal) {
            if (activeLocalImageCount < maxLocalConcurrency && activeExclusiveCount === 0) {
              remainingNodeIds.splice(i, 1);
              i--;
              activeLocalImageCount++;
              dispatchedAny = true;
              const taskP = (async () => {
                try {
                  const res = await executeSingleNode(candidateNode);
                  if (res?.fatal) hasFatalPause = true;
                } finally {
                  activeLocalImageCount--;
                  runningMap.delete(candidateId);
                }
              })();
              runningMap.set(candidateId, taskP);
              updateConcurrencyStatus();
            }
          } else {
            if (activeExclusiveCount === 0 && activeLocalImageCount === 0) {
              remainingNodeIds.splice(i, 1);
              i--;
              activeExclusiveCount++;
              dispatchedAny = true;
              const taskP = (async () => {
                try {
                  const res = await executeSingleNode(candidateNode);
                  if (res?.fatal) hasFatalPause = true;
                } finally {
                  activeExclusiveCount--;
                  runningMap.delete(candidateId);
                }
              })();
              runningMap.set(candidateId, taskP);
              updateConcurrencyStatus();
              break;
            }
          }
        }

        if (runningMap.size > 0) {
          await Promise.race(runningMap.values());
          updateConcurrencyStatus();
        } else if (!dispatchedAny && remainingNodeIds.length > 0) {
          // 死锁自愈防御：上游异常导致依赖未满足且当前无任务运行，降级推进剩余节点
          const nextId = remainingNodeIds.shift();
          const nextNode = nodeById(nextId);
          if (nextNode) {
            const isLocal = isLocalImageNode(nextNode);
            if (isLocal) activeLocalImageCount++; else activeExclusiveCount++;
            const fbP = (async () => {
              try {
                const res = await executeSingleNode(nextNode);
                if (res?.fatal) hasFatalPause = true;
              } finally {
                if (isLocal) activeLocalImageCount--; else activeExclusiveCount--;
                runningMap.delete(nextId);
              }
            })();
            runningMap.set(nextId, fbP);
            updateConcurrencyStatus();
            await Promise.race(runningMap.values());
            updateConcurrencyStatus();
          }
        }
      }
      try{
        clearTimeout(autoSaveTimer);
        await queueWorkflowSave();
        const retryBtn=$('#retryFailedBtn');
        if(retryBtn)retryBtn.classList.toggle('hidden',failedNodes.length===0&&skippedDependencyNodes.length===0);
        if(failedNodes.length>0||skippedDependencyNodes.length>0){
          const parts=[];
          if(succeededNodes.length>0)parts.push(`成功 ${succeededNodes.length} 项`);
          if(failedNodes.length>0)parts.push(`失败 ${failedNodes.length} 项`);
          if(skippedDependencyNodes.length>0)parts.push(`因依赖跳过 ${skippedDependencyNodes.length} 项`);
          if(skippedCount>0)parts.push(`跳过未变更 ${skippedCount} 项`);
          setRunStatus(`工作流运行完成（${parts.join('，')}）。可点击顶栏“↺ 重试失败项”或单独重试标红节点。`,'warn');
        }else{
          const finishMsg=targetSet?(targetSet.size===1?`节点 ${[...targetSet][0]} 生成完成。`:`${totalGenerations} 个所选节点生成完成。`):(skippedCount>0?`工作流运行完成（已生成 ${totalGenerations} 项，跳过 ${skippedCount} 个未变更项）。`:"工作流运行完成。");
          setRunStatus(finishMsg,'ok');
        }
      }catch(saveError){setRunStatus(`生成已完成，但工作流保存失败：${saveError?.message||String(saveError)}`,'warn');}
    }catch(err){
      if(err?.name==='AbortError'||abortController.signal.aborted){
        const active=state.nodes.find(n=>n.id===state.activeGenerationId);
        if(active&&active.data.status==='running'){active.data.status='stopped';active.data.error="用户已停止生成。";render();}
        try{clearTimeout(autoSaveTimer);await queueWorkflowSave();}catch{}
        return;
      }
      const failed=state.nodes.find(n=>['generateImage','generateVideo'].includes(n.type)&&n.data.status==='running');
      if(failed){failed.data.status='failed';failed.data.error=err?.message||String(err);render();}
      const message=err?.message||String(err);
      setRunStatus(/failed to fetch/i.test(message)?"Muse 连接失败。请重新加载 MuseFlow 0.5.0，然后检查 Muse 会话。":'MuseFlow 0.5.0 · '+message,'error');
      try{clearTimeout(autoSaveTimer);await queueWorkflowSave();}catch(saveError){setRunStatus(`${runStatus.textContent} · 自动保存失败：${saveError?.message||String(saveError)}`,'error');}
    }
    finally{state.isRunning=false;state.activeGenerationId=null;state.generationAbortController=null;state.generationRequestId=null;$('#runBtn').disabled=false;$('#runBtn').textContent="▶ 运行";render();}
  }

  function runSingleNode(nodeId){const node=nodeById(nodeId);if(!node||!['generateImage','generateVideo'].includes(node.type))return;if(node.data.status==='running'){stopGeneration(nodeId);return;}execute(nodeId);}
  function retryFailedNodes(){
    const targetNodes=state.nodes.filter(n=>['generateImage','generateVideo'].includes(n.type)&&['failed','error','blocked','submission_unknown'].includes(n.data?.status));
    if(!targetNodes.length){
      setRunStatus("当前没有失败或阻断的节点需要重试。",'ok');
      const retryBtn=$('#retryFailedBtn');if(retryBtn)retryBtn.classList.add('hidden');
      return;
    }
    const targetIds=targetNodes.map(n=>n.id);
    targetNodes.forEach(n=>{
      n.data.status='idle';
      n.data.dirty=true;
      n.data.error='';
      delete n.data.errorType;
      delete n.data.continuityDegraded;
    });
    render();
    execute(targetIds);
  }
  function onWorkflowRunButtonClick(event){if(event.detail>1)return;if(state.isRunning)stopGeneration(state.activeGenerationId);else execute(null,{forceAll:false});}
  function onWorkflowRunAllButtonClick(event){if(event.detail>1)return;if(state.isRunning)stopGeneration(state.activeGenerationId);else execute(null,{forceAll:true});}
  function onWorkflowRunImagesOnlyClick(event){if(event.detail>1)return;if(state.isRunning)stopGeneration(state.activeGenerationId);else execute(null,{onlyType:'generateImage'});}
  function onWorkflowRunVideosOnlyClick(event){if(event.detail>1)return;if(state.isRunning)stopGeneration(state.activeGenerationId);else execute(null,{onlyType:'generateVideo'});}

  function setRunStatus(text, cls=''){runStatus.className=cls;runStatus.textContent=text;}

  function ratioValue(size){const [w,h]=String(size||'1:1').split(':').map(Number);return w>0&&h>0?w/h:1;}

  function clampDimension(value){return Math.max(1,Math.min(4096,Math.round(Number(value)||1)));}

  function loadImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error("无法加载相连的图片以调整尺寸。"));image.src=url;});}

  function drawResized(image,canvas,data={}){
    const width=clampDimension(data.width||1024),height=clampDimension(data.height||1024);canvas.width=width;canvas.height=height;
    const context=canvas.getContext('2d');if(!context)return;context.fillStyle='#101116';context.fillRect(0,0,width,height);
    const fit=data.fit||'cover';let scale=fit==='stretch'?null:fit==='contain'?Math.min(width/image.naturalWidth,height/image.naturalHeight):Math.max(width/image.naturalWidth,height/image.naturalHeight);
    const drawWidth=scale===null?width:image.naturalWidth*scale,drawHeight=scale===null?height:image.naturalHeight*scale;
    context.drawImage(image,(width-drawWidth)/2,(height-drawHeight)/2,drawWidth,drawHeight);
  }

  async function mediaDimensions(url,kind,timeoutMs=10000){
    if(kind==='image'){
      return new Promise(resolve=>{
        let settled=false;
        const image=new Image();
        const cleanup=()=>{image.onload=null;image.onerror=null;};
        const timer=setTimeout(()=>{if(settled)return;settled=true;cleanup();resolve({width:0,height:0,timeout:true});},timeoutMs);
        image.onload=()=>{if(settled)return;settled=true;clearTimeout(timer);const w=image.naturalWidth,h=image.naturalHeight;cleanup();resolve({width:w,height:h});};
        image.onerror=()=>{if(settled)return;settled=true;clearTimeout(timer);cleanup();resolve({width:0,height:0});};
        image.src=url;
      });
    }
    return new Promise(resolve=>{
      let settled=false;
      const video=document.createElement('video');
      video.preload='metadata';
      const cleanup=()=>{
        video.onloadedmetadata=null;
        video.onerror=null;
        video.removeAttribute('src');
        try{video.load();}catch{}
      };
      const timer=setTimeout(()=>{if(settled)return;settled=true;cleanup();resolve({width:0,height:0,duration:0,timeout:true});},timeoutMs);
      video.onloadedmetadata=()=>{if(settled)return;settled=true;clearTimeout(timer);const w=video.videoWidth,h=video.videoHeight,d=Number(video.duration)||0;cleanup();resolve({width:w,height:h,duration:d});};
      video.onerror=()=>{if(settled)return;settled=true;clearTimeout(timer);cleanup();resolve({width:0,height:0,duration:0});};
      video.src=url;
      try{video.load();}catch{}
    });
  }

  function extractVideoEndFrame(url){return new Promise(resolve=>{const video=document.createElement('video');if(/^https?:/i.test(url))video.crossOrigin='anonymous';video.preload='auto';video.muted=true;video.playsInline=true;let finished=false;const done=value=>{if(finished)return;finished=true;video.removeAttribute('src');video.load();resolve(value);};const timer=setTimeout(()=>done(null),12000);video.onloadedmetadata=()=>{if(!Number.isFinite(video.duration)){clearTimeout(timer);done(null);return;}video.currentTime=Math.max(0,video.duration-Math.min(.04,video.duration/100));};video.onseeked=()=>{try{const width=video.videoWidth,height=video.videoHeight;if(!width||!height){clearTimeout(timer);done(null);return;}const frame=document.createElement('canvas');frame.width=width;frame.height=height;frame.getContext('2d').drawImage(video,0,0,width,height);const dataUrl=frame.toDataURL('image/png');clearTimeout(timer);done({id:uid('endframe'),kind:'image',url:dataUrl,name:"视频尾帧",width,height});}catch{clearTimeout(timer);done(null);}};video.onerror=()=>{clearTimeout(timer);done(null);};video.src=url;video.load();});}

  async function persistImage(url) {
    if(!url)return '';
    if(url.startsWith('data:'))return url;
    try{
      const response=await fetch(url,{credentials:'include'});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const blob=await response.blob();
      if(blob.size>8*1024*1024)return url;
      return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(reader.error);reader.readAsDataURL(blob);});
    }catch{return url;}
  }

  let mediaDbPromise;
  function mediaDb(){if(!mediaDbPromise)mediaDbPromise=new Promise((resolve,reject)=>{const request=indexedDB.open('museflow-media',1);request.onupgradeneeded=()=>request.result.createObjectStore('assets');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error||new Error("无法打开本地媒体存储。"));});return mediaDbPromise;}
  async function putMedia(key,blob){const db=await mediaDb();return new Promise((resolve,reject)=>{const tx=db.transaction('assets','readwrite');tx.objectStore('assets').put(blob,key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error||new Error("无法在本地保存媒体文件。"));tx.onabort=()=>reject(tx.error||new Error("媒体存储事务已取消。"));});}
  async function getMedia(key){const db=await mediaDb();return new Promise((resolve,reject)=>{const request=db.transaction('assets','readonly').objectStore('assets').get(key);request.onsuccess=()=>resolve(request.result||null);request.onerror=()=>reject(request.error||new Error("无法读取已保存的媒体文件。"));});}
  const idbMediaPrefix='museflow-idb:';
  async function dehydrateMediaUrl(url,key){
    if(!url||url.startsWith(idbMediaPrefix))return url;
    if(!(/^(?:data:|blob:|https?:)/i).test(url))return url;
    try{
      const response=await fetch(url,{credentials:'include'});
      if(!response.ok)return url;
      const blob=await response.blob();
      if(!blob.size)return url;
      await putMedia(key,blob);
      return idbMediaPrefix+encodeURIComponent(key);
    }catch(err){
      console.warn(`[dehydrateMediaUrl] 媒体持久化降级 (${key}):`, err);
      return url;
    }
  }
  let autoSaveTimer=0,workflowSaveQueue=Promise.resolve();
  async function saveWorkflowSnapshot(){const snapshot=structuredClone({nodes:state.nodes,edges:state.edges,settings:state.settings});for(const node of snapshot.nodes){const data=node.data||{};if(data.localDataUrl)data.localDataUrl=await dehydrateMediaUrl(data.localDataUrl,`input:${node.id}`);for(const field of ['asset','endFrame']){const media=data[field];if(media?.url)media.url=await dehydrateMediaUrl(media.url,`${field}:${media.id||node.id}`);}if(Array.isArray(data.versions)){for(const ver of data.versions){if(ver?.url)ver.url=await dehydrateMediaUrl(ver.url,`version:${ver.id||node.id}`);}}}await chrome.storage.local.set({museflow:snapshot});}
  function queueWorkflowSave(){workflowSaveQueue=workflowSaveQueue.catch(()=>{}).then(saveWorkflowSnapshot);return workflowSaveQueue;}
  function scheduleAutoSave(){clearTimeout(autoSaveTimer);autoSaveTimer=setTimeout(()=>{queueWorkflowSave().catch(error=>{if(runStatus.className!=='error')setRunStatus(`自动保存失败：${error?.message||String(error)}`,'error');});},650);}
  async function hydrateMediaUrl(url,cache){if(!url?.startsWith(idbMediaPrefix))return url;const key=decodeURIComponent(url.slice(idbMediaPrefix.length));if(!cache.has(key)){const blob=await getMedia(key);cache.set(key,blob?URL.createObjectURL(blob):'');}return cache.get(key);}
  async function hydrateWorkflowMedia(){const cache=new Map();for(const node of state.nodes){const data=node.data||{};if(data.localDataUrl)data.localDataUrl=await hydrateMediaUrl(data.localDataUrl,cache);for(const field of ['asset','endFrame'])if(data[field]?.url)data[field].url=await hydrateMediaUrl(data[field].url,cache);if(Array.isArray(data.versions)){for(const ver of data.versions){if(ver?.url)ver.url=await hydrateMediaUrl(ver.url,cache);}}}}
  async function saveState(){clearTimeout(autoSaveTimer);try{await queueWorkflowSave();setRunStatus('已保存。','ok');}catch(error){setRunStatus(`无法保存工作流：${error?.message||String(error)}`,'error');}}
  function blobAsDataUrl(blob){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(reader.error||new Error("无法打包工作流媒体。"));reader.readAsDataURL(blob);});}
  async function exportWorkflowFile(){
    const button=$('#workflowExportBtn');button.disabled=true;
    try{
      const workflow=structuredClone({nodes:state.nodes,edges:state.edges,settings:state.settings});let externalMedia=0;
      const packageUrl=async url=>{
        if(!url||url.startsWith('data:'))return url;
        try{
          let blob;
          if(url.startsWith(idbMediaPrefix))blob=await getMedia(decodeURIComponent(url.slice(idbMediaPrefix.length)));
          else if(/^(?:blob:|https?:)/i.test(url)){const response=await fetch(url,{credentials:'include'});if(!response.ok)throw new Error(`HTTP ${response.status}`);blob=await response.blob();}
          else return url;
          if(!blob?.size)throw new Error("媒体缺失或内容为空");
          return await blobAsDataUrl(blob);
        }catch{externalMedia++;return url;}
      };
      for(const node of workflow.nodes){const data=node.data||{};if(data.localDataUrl)data.localDataUrl=await packageUrl(data.localDataUrl);for(const field of ['asset','endFrame'])if(data[field]?.url)data[field].url=await packageUrl(data[field].url);}
      const file={format:'26flow-workflow',version:1,appVersion:'0.5.0',exportedAt:new Date().toISOString(),workflow};
      const blob=new Blob([JSON.stringify(file)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`26MuseFlow-Workflow-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
      setRunStatus(externalMedia?`工作流已保存；${externalMedia}个媒体链接未能嵌入文件，可能需要原 Muse 会话才能访问。`:"工作流已保存，包含媒体文件。",'ok');
    }catch(error){setRunStatus(`无法保存工作流文件：${error?.message||String(error)}`,'error');}
    finally{button.disabled=false;}
  }
  function exportDiagnosticsJson(){
    const WHITELIST_FIELDS=['id','workflowId','nodeId','nodeType','attemptId','status','errorType','durationMs','versionId','qualityStatus','model','startTime'];
    function sanitizeErrorMessage(msg){
      if(!msg||typeof msg!=='string')return null;
      return msg
        .replace(/(?:sk-[a-zA-Z0-9_\-]{8,})/gi,'sk-***')
        .replace(/(?:Bearer\s+)[a-zA-Z0-9_\-\.]{8,}/gi,'Bearer ***')
        .replace(/(?:key|token|auth|secret|credential|password|api_key|session_id)=[^\s&"';]+/gi,'$1=***')
        .replace(/https?:\/\/[^\s"'<>]+(?:\?[^\s"'<>]+)/gi,url=>{
          try{
            const u=new URL(url);
            for(const p of [...u.searchParams.keys()]){
              if(/key|token|auth|secret|cred|pass|sig|signature/i.test(p))u.searchParams.set(p,'***');
            }
            return u.toString();
          }catch{return url.split('?')[0]+'?***';}
        });
    }
    const sanitizedRecords=(state.executionDiagnostics||[]).map(r=>{
      if(!r||typeof r!=='object')return null;
      const clean={};
      for(const k of WHITELIST_FIELDS){if(r[k]!==undefined)clean[k]=r[k];}
      clean.errorMessage=sanitizeErrorMessage(r.errorMessage);
      return clean;
    }).filter(Boolean);
    const report={
      format:'26flow-diagnostics',
      exportedAt:new Date().toISOString(),
      appVersion:'0.5.0',
      workflowId:state.workflowId||'default-workflow',
      nodeCount:state.nodes.length,
      edgeCount:state.edges.length,
      records:sanitizedRecords
    };
    const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download=`26Flow-Diagnostics-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
    return report;
  }
  async function importWorkflowFile(file){
    if(!file)return;if(state.isRunning){setRunStatus("导入其他工作流前，请先停止当前工作流。",'warn');return;}
    let parsed,workflow;
    try{parsed=JSON.parse(await file.text());workflow=parsed?.format==='26flow-workflow'?parsed.workflow:parsed;if(!workflow||!Array.isArray(workflow.nodes)||!Array.isArray(workflow.edges))throw new Error("此文件不是有效的 MuseFlow 工作流。");}
    catch(error){setRunStatus(`无法导入工作流：${error?.message||String(error)}`,'error');return;}
    if(!window.confirm("导入此工作流会替换当前画布，是否继续？"))return;
    const previous={nodes:state.nodes,edges:state.edges,settings:state.settings};
    try{
      state.nodes=workflow.nodes;state.edges=workflow.edges;
      // 保留用户在本机配置的全局独立 API 与 Endpoint，避免被导入的空设置冲掉
      const currentGlobal = await loadGlobalSettings();
      state.settings = { ...currentGlobal, ...(workflow.settings && typeof workflow.settings==='object' ? workflow.settings : {}) };
      await hydrateWorkflowMedia();normalizeSavedGraph();state.selectedNodeIds=[];state.selectedNodeId=null;state.selectedEdgeIds=[];syncSettingsUI();render();await queueWorkflowSave();
      setRunStatus(`工作流已导入：${file.name}`,'ok');
    }catch(error){state.nodes=previous.nodes;state.edges=previous.edges;state.settings=previous.settings;render();setRunStatus(`无法导入工作流：${error?.message||String(error)}`,'error');}
  }
  async function loadState(){try{const got=await chrome.storage.local.get('museflow');if(got.museflow){state.nodes=Array.isArray(got.museflow.nodes)?got.museflow.nodes:[];state.edges=Array.isArray(got.museflow.edges)?got.museflow.edges:[];state.settings=got.museflow.settings||{};if(!state.nodes.length){const s=starter();state.nodes=s.nodes;state.edges=s.edges;}}else{const s=starter();state.nodes=s.nodes;state.edges=s.edges;}await hydrateWorkflowMedia();}catch(error){const s=starter();state.nodes=s.nodes;state.edges=s.edges;setRunStatus(`无法加载已保存的工作流：${error.message}`,'error');}normalizeSavedGraph();syncSettingsUI();
    // 启动时合并全局独立设置，彻底防止 API Key 或 Endpoint 意外丢失
    const globalSaved = await loadGlobalSettings();
    state.settings = { ...globalSaved, ...(state.settings || {}) };
    // 若全局设置具备更完善的 API Key 或 Endpoint，优先采用
    if (globalSaved.localApiKey && !state.settings.localApiKey) state.settings.localApiKey = globalSaved.localApiKey;
    if (globalSaved.localApiEndpoint && state.settings.localApiEndpoint === 'http://127.0.0.1:8000/v1') state.settings.localApiEndpoint = globalSaved.localApiEndpoint;
    // 自动解除已连接独立分镜底图的视频节点上误开的 continuity（防止第一镜尾帧连锁锁死所有后续分镜）
    for (const vNode of state.nodes) {
      if (vNode.type === 'generateVideo' && vNode.data?.continuity && hasDirectKeyframe(vNode.id)) {
        vNode.data.continuity = false;
      }
    }
    syncSettingsUI();
    render();syncTimelineDock();try{clearTimeout(autoSaveTimer);await queueWorkflowSave();}catch(error){setRunStatus(`工作流已打开，但媒体迁移失败：${error?.message||String(error)}`,'warn');}
    // 启动自愈：若发现历史节点残留了误抓的 480×480 吉祥物视频或元数据超时，自动从当前 Muse 页面重抓 10 秒原片替换
    const pollutedVideoNodes = state.nodes.filter(n => n.type === 'generateVideo' && ((n.data?.asset?.width === 480 && n.data?.asset?.height === 480) || n.data?.errorType === 'MEDIA_METADATA_TIMEOUT'));
    for (const badNode of pollutedVideoNodes) {
      recoverVideoFromMuse(badNode.id, { requireSceneMatch: true }).catch(() => {});
    }
  }
  async function resetState(){if(state.isRunning)return;const s=starter();state.nodes=s.nodes;state.edges=s.edges;state.selectedNodeIds=[];state.selectedNodeId=null;render();await saveState();}
  function syncSettingsUI(){
    backendStatus.textContent="Muse 会话 · v0.5.0 中文版";
    bindSettingsAutoPersist();
    const providerSelect=$('#imageApiProviderSelect');
    const localGroup=$('#localApiConfigGroup');
    if(providerSelect){
      providerSelect.value=state.settings?.imageProvider||'local';
      providerSelect.onchange=()=>{
        if(localGroup)localGroup.style.display=providerSelect.value==='local'?'block':'none';
      };
      if(localGroup)localGroup.style.display=providerSelect.value==='local'?'block':'none';
    }
    const endpointInput=$('#localApiEndpointInput');
    if(endpointInput)endpointInput.value=state.settings?.localApiEndpoint||'http://127.0.0.1:8000/v1';
    const keyInput=$('#localApiKeyInput');
    if(keyInput)keyInput.value=state.settings?.localApiKey||'';
    const orchInput=$('#orchestrationModelInput');
    if(orchInput)orchInput.value=state.settings?.orchestrationModel||'qwen2.5:7b';
    const concurrencySelect=$('#localImageConcurrencySelect');
    if(concurrencySelect){
      concurrencySelect.value=String(state.settings?.localImageConcurrency||2);
    }
    const statusEl=$('#localApiStatus');
    if(statusEl){statusEl.className='';statusEl.textContent='';}
    const defaultSelect=$('#defaultImageModelSelect');
    if(defaultSelect){
      defaultSelect.innerHTML='';
      const models=getAvailableImageModels();
      models.forEach(m=>{
        const opt=document.createElement('option');
        opt.value=m.id;
        opt.textContent=m.name;
        defaultSelect.appendChild(opt);
      });
      defaultSelect.value=state.settings?.defaultImageModel||(models.find(m=>m.id==='flux-1-dev')?'flux-1-dev':'muse-image');
    }
    const chipsContainer=$('#customModelsList');
    if(chipsContainer){
      chipsContainer.innerHTML='';
      const custom=Array.isArray(state.settings?.customImageModels)?state.settings.customImageModels:[];
      if(custom.length===0){
        const empty=document.createElement('span');empty.className='empty-chips-hint';empty.textContent="暂无自定义模型（可通过上方输入框添加，或在生成节点中输入）";chipsContainer.appendChild(empty);
      }else{
        custom.forEach(name=>{
          const chip=document.createElement('span');chip.className='model-chip';chip.textContent=name;
          const delBtn=document.createElement('button');delBtn.type='button';delBtn.textContent='×';delBtn.title=`删除模型 ${name}`;
          delBtn.onclick=e=>{e.stopPropagation();removeCustomImageModel(name);syncSettingsUI();render();};
          chip.appendChild(delBtn);chipsContainer.appendChild(chip);
        });
      }
    }
  }

  async function detectMuse(){
    try{
      const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
      if(tabs.length){const active=tabs.find(t=>t.active)||tabs[0];await testMuseSession(active.id);}
      else{museStatus.textContent="● 请打开 muse.ai 并登录";museStatus.className='warn';}
    }catch{museStatus.textContent="● 暂时无法检查 Muse 会话";museStatus.className='warn';}
  }

  document.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>addNode(b.dataset.add));
  const aiOrchestrateBtn = $('#aiOrchestrateBtn');
  if (aiOrchestrateBtn) {
    aiOrchestrateBtn.onclick = () => {
      $('#aiOrchestrateModal').classList.remove('hidden');
      initAiChatSession();
      const statusEl = $('#orchestrationStatus');
      if (statusEl) { statusEl.className = ''; statusEl.textContent = ''; }
      setTimeout(() => $('#aiChatInput')?.focus(), 50);
    };
  }

  // =========================================================================
  // 对话式 AI 工作流搭建助手 (Interactive Chat Copilot)
  // =========================================================================
  let aiChatHistory = [];
  let pendingChatAttachments = [];
  let aiChatSessionUploadedImages = [];

  function formatFileSize(bytes) {
    if (!bytes || bytes < 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function renderPendingChatAttachments() {
    const bar = $('#aiChatAttachmentBar');
    if (!bar) return;
    if (!pendingChatAttachments.length) {
      bar.classList.add('hidden');
      bar.innerHTML = '';
      return;
    }
    bar.classList.remove('hidden');
    bar.innerHTML = '';

    pendingChatAttachments.forEach((att, idx) => {
      const item = document.createElement('div');
      item.className = 'ai-chat-attachment-item';

      if (att.type === 'image') {
        const thumb = document.createElement('img');
        thumb.className = 'ai-chat-attachment-thumb';
        thumb.src = att.dataUrl;
        item.appendChild(thumb);
      } else {
        const icon = document.createElement('div');
        icon.className = 'ai-chat-attachment-icon';
        icon.textContent = att.name.endsWith('.json') ? '📊' : (att.name.endsWith('.md') ? '📝' : '📄');
        item.appendChild(icon);
      }

      const nameSpan = document.createElement('div');
      nameSpan.className = 'ai-chat-attachment-name';
      nameSpan.title = `${att.name} (${formatFileSize(att.size)})`;
      nameSpan.textContent = att.name;
      item.appendChild(nameSpan);

      const sizeSpan = document.createElement('div');
      sizeSpan.className = 'ai-chat-attachment-size';
      sizeSpan.textContent = formatFileSize(att.size);
      item.appendChild(sizeSpan);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'ai-chat-attachment-remove';
      removeBtn.textContent = '✕';
      removeBtn.title = '移除此附件';
      removeBtn.onclick = (e) => {
        e.stopPropagation();
        pendingChatAttachments.splice(idx, 1);
        renderPendingChatAttachments();
      };
      item.appendChild(removeBtn);

      bar.appendChild(item);
    });
  }

  function addChatFile(file) {
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      alert(`文件 [${file.name}] 体积过大 (超过 20MB)，请选择较小的文件。`);
      return;
    }

    const isImage = file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(file.name);
    const isText = file.type.startsWith('text/') || /\.(txt|md|json|csv|log|yaml|yml)$/i.test(file.name) || file.type === 'application/json';

    if (isImage) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target.result;
        pendingChatAttachments.push({
          id: uid('att'),
          name: file.name || '参考图片',
          size: file.size,
          type: 'image',
          dataUrl
        });
        renderPendingChatAttachments();
      };
      reader.readAsDataURL(file);
    } else if (isText) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const textContent = String(e.target.result || '');
        pendingChatAttachments.push({
          id: uid('att'),
          name: file.name || '素材文档',
          size: file.size,
          type: 'text',
          textContent
        });
        renderPendingChatAttachments();
      };
      reader.readAsText(file);
    } else {
      alert(`暂不支持解析文件类型 [${file.name}]，请上传图片（PNG/JPG/WEBP 等）或文本文档（TXT/MD/JSON 等）。`);
    }
  }

  function initAiChatSession() {
    pendingChatAttachments = [];
    aiChatSessionUploadedImages = [];
    renderPendingChatAttachments();
    if (!aiChatHistory.length) {
      aiChatHistory.push({
        role: 'assistant',
        content: "你好！我是你的 AI 编导与工作流搭建助手 🎬\n\n你可以把任何乱七八糟的想法、口播文案、小说片段、故事大纲直接丢给我，也可以通过左下角 📎 按钮、拖拽或剪贴板直接丢入参考图片与素材文档！\n我会根据你的素材和参考图梳理镜头节奏、锁定风格调性，并自动在工作流中挂载参考图与分镜节点，支持随时一键搭建或追加。\n\n试试在下方输入文案或丢入参考图吧！",
        scenes: null
      });
    }
    renderAiChatMessages();
  }

  function escapeHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderAiChatMessages() {
    const container = $('#aiChatMessages');
    if (!container) return;
    container.innerHTML = '';

    aiChatHistory.forEach((msg) => {
      const msgRow = document.createElement('div');
      msgRow.className = `chat-msg ${msg.role === 'user' ? 'user' : 'ai'}`;

      const avatar = document.createElement('div');
      avatar.className = 'chat-avatar';
      avatar.textContent = msg.role === 'user' ? '👤' : '🤖';

      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble';

      // 若本条消息携带多模态附件（图片/素材文档），优先展示在消息气泡顶部
      if (Array.isArray(msg.attachments) && msg.attachments.length > 0) {
        const attContainer = document.createElement('div');
        attContainer.className = 'ai-msg-attachments';

        msg.attachments.forEach(att => {
          if (att.type === 'image') {
            const card = document.createElement('div');
            card.className = 'ai-msg-image-card';
            const img = document.createElement('img');
            img.className = 'ai-msg-image-thumb';
            img.src = att.dataUrl;
            img.title = `${att.name} (点击在新窗口全屏预览)`;
            img.onclick = () => {
              const w = window.open('about:blank', '_blank');
              if (w && w.document) {
                w.document.title = att.name || '图片预览';
                const body = w.document.body;
                if (body) {
                  body.style.margin = '0';
                  body.style.background = '#0e1017';
                  body.style.display = 'flex';
                  body.style.alignItems = 'center';
                  body.style.justifyContent = 'center';
                  body.style.height = '100vh';
                  const fullImg = w.document.createElement('img');
                  fullImg.src = att.dataUrl;
                  fullImg.alt = att.name || '图片预览';
                  fullImg.style.maxWidth = '95vw';
                  fullImg.style.maxHeight = '95vh';
                  fullImg.style.objectFit = 'contain';
                  fullImg.style.borderRadius = '8px';
                  fullImg.style.boxShadow = '0 0 24px rgba(0,0,0,0.8)';
                  body.appendChild(fullImg);
                }
              }
            };
            card.appendChild(img);
            attContainer.appendChild(card);
          } else {
            const pill = document.createElement('div');
            pill.className = 'ai-msg-file-pill';
            pill.innerHTML = `<span>${att.name.endsWith('.json') ? '📊' : (att.name.endsWith('.md') ? '📝' : '📄')}</span> <span>${escapeHtml(att.name)}</span> <span style="opacity:0.6;font-size:10px;">(${formatFileSize(att.size)})</span>`;
            attContainer.appendChild(pill);
          }
        });

        bubble.appendChild(attContainer);
      }

      const textDiv = document.createElement('div');
      textDiv.style.whiteSpace = 'pre-wrap';
      textDiv.textContent = msg.content;
      bubble.appendChild(textDiv);

      if (Array.isArray(msg.scenes) && msg.scenes.length > 0) {
        const box = document.createElement('div');
        box.className = 'chat-storyboard-box';

        const header = document.createElement('div');
        header.className = 'chat-storyboard-header';
        const totalDur = msg.scenes.reduce((acc, s) => acc + (Number(s.duration) || 6), 0);
        header.innerHTML = `<span>📋 AI 规划分镜方案（共 ${msg.scenes.length} 镜 · 总长约 ${totalDur} 秒）</span><span style="font-size:11px;color:#8f97b5;">[画幅 ${msg.scenes[0]?.size || '9:16'}]</span>`;
        box.appendChild(header);

        const list = document.createElement('div');
        list.className = 'chat-storyboard-cards-mini';

        msg.scenes.forEach((sc, sIdx) => {
          const item = document.createElement('div');
          item.className = 'chat-story-item';
          const hasReadyImage = Boolean(sc.readyImage?.dataUrl);
          const readyBadge = hasReadyImage ? `<span class="chat-ready-image-badge">📸 现成底图就绪</span>` : '';
          const readyThumbHtml = hasReadyImage ? `
            <div class="chat-story-ready-preview">
              <img src="${sc.readyImage.dataUrl}" class="chat-story-ready-thumb">
              <div>
                <div style="font-weight:600;font-size:11px;color:#4ade80;">✔ 底图已确认：${escapeHtml(sc.readyImage.name || '满意原图')}</div>
                <div style="font-size:10px;color:#8f97b5;">画布直接以此图作为起手帧驱动视频生成，无需重新生图</div>
              </div>
            </div>
          ` : '';
          const imagePromptDesc = hasReadyImage ? '' : `<div class="chat-story-item-desc"><strong>🖼 起手图提示词:</strong> ${escapeHtml(sc.imagePrompt || '无')}</div>`;
          item.innerHTML = `
            <div class="chat-story-item-top">
              <span>镜头 ${sc.number || sIdx + 1}: ${escapeHtml(sc.title || '场景')}${readyBadge}</span>
              <span style="color:#f5b041;">⏱ ${sc.duration || 6}s</span>
            </div>
            ${readyThumbHtml}
            ${imagePromptDesc}
            <div class="chat-story-item-desc"><strong>🎥 运镜动作提示词:</strong> ${escapeHtml(sc.videoPrompt || sc.imagePrompt || '平滑运镜')}</div>
          `;
          list.appendChild(item);
        });
        box.appendChild(list);

        const actions = document.createElement('div');
        actions.className = 'chat-build-actions-bar';

        const hasAnyReady = msg.scenes.some(s => Boolean(s.readyImage?.dataUrl));
        const buildReplaceBtn = document.createElement('button');
        buildReplaceBtn.type = 'button';
        buildReplaceBtn.className = hasAnyReady ? 'chat-build-btn ready-video' : 'chat-build-btn';
        buildReplaceBtn.innerHTML = hasAnyReady ? '🎬 一键组装图生视频工作流 (跳过生图)' : '🚀 一键搭建工作流 (替换现有)';
        buildReplaceBtn.onclick = () => {
          currentStoryboardScenes = msg.scenes;
          buildWorkflowFromStoryboard(msg.scenes, { replace: true });
        };

        const buildAppendBtn = document.createElement('button');
        buildAppendBtn.type = 'button';
        buildAppendBtn.className = 'chat-build-btn append';
        buildAppendBtn.innerHTML = '➕ 追加到画布末尾';
        buildAppendBtn.onclick = () => {
          currentStoryboardScenes = msg.scenes;
          buildWorkflowFromStoryboard(msg.scenes, { replace: false });
        };

        const copyPromptsBtn = document.createElement('button');
        copyPromptsBtn.type = 'button';
        copyPromptsBtn.className = 'chat-build-btn copy';
        copyPromptsBtn.innerHTML = '📋 复制提示词';
        copyPromptsBtn.onclick = () => {
          const text = msg.scenes.map((s, i) => `【镜头 ${i + 1}】\n图片提示词: ${s.imagePrompt}\n视频提示词: ${s.videoPrompt}\n时长: ${s.duration}s\n`).join('\n');
          navigator.clipboard?.writeText(text);
          copyPromptsBtn.textContent = '✔ 已复制全部';
          setTimeout(() => copyPromptsBtn.textContent = '📋 复制提示词', 2000);
        };

        actions.appendChild(buildReplaceBtn);
        actions.appendChild(buildAppendBtn);
        actions.appendChild(copyPromptsBtn);
        box.appendChild(actions);

        bubble.appendChild(box);
      }

      msgRow.appendChild(avatar);
      msgRow.appendChild(bubble);
      container.appendChild(msgRow);
    });

    container.scrollTop = container.scrollHeight;
  }

  async function sendAiChatMessage(userText) {
    userText = String(userText || '').trim();
    const attachmentsToSend = [...pendingChatAttachments];
    if (!userText && !attachmentsToSend.length) return;

    // 如果用户未输入纯文字，但上传了附件，自动生成意图说明
    let displayUserText = userText;
    if (!displayUserText && attachmentsToSend.length) {
      const imgCount = attachmentsToSend.filter(a => a.type === 'image').length;
      const txtCount = attachmentsToSend.filter(a => a.type === 'text').length;
      const parts = [];
      if (imgCount) parts.push(`${imgCount} 张风格参考图片`);
      if (txtCount) parts.push(`${txtCount} 篇素材文档`);
      displayUserText = `请参考我上传的 ${parts.join(' 与 ')}，帮我规划短视频分镜并搭建工作流。`;
    }

    // 收集图片附件到本会话的全局图片库，用于后续一键生成画布节点时自动挂载
    attachmentsToSend.filter(a => a.type === 'image').forEach(imgAtt => {
      aiChatSessionUploadedImages.push(imgAtt);
    });

    aiChatHistory.push({
      role: 'user',
      content: displayUserText,
      attachments: attachmentsToSend
    });

    const input = $('#aiChatInput');
    if (input) input.value = '';
    pendingChatAttachments = [];
    renderPendingChatAttachments();
    renderAiChatMessages();

    const sendBtn = $('#aiChatSendBtn');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = '⏳ 思考中…';
    }
    const statusEl = $('#orchestrationStatus');
    if (statusEl) {
      statusEl.className = 'warn';
      statusEl.textContent = '正在由本地 AI 分析您的文案大纲并拆解分镜镜头…';
    }

    const targetDuration = Number($('#aiTargetDurationSelect')?.value || 30);
    const size = $('#aiAspectSelect')?.value || '9:16';
    const flowMode = $('#aiVisualFlowSelect')?.value || 'image_to_video';
    const style = $('#aiStylePresetSelect')?.value || '自然写实纪实';

    // 组装随附的文本文件与图片多模态描述
    let enrichedPrompt = displayUserText;
    const textFiles = attachmentsToSend.filter(a => a.type === 'text');
    if (textFiles.length) {
      const docsContent = textFiles.map(f => `【素材文件: ${f.name}】:\n${f.textContent}`).join('\n\n');
      enrichedPrompt += `\n\n[用户随附上传的参考资料文档内容如下]:\n${docsContent}`;
    }
    const imageFiles = attachmentsToSend.filter(a => a.type === 'image');
    if (imageFiles.length) {
      enrichedPrompt += `\n\n[用户随附上传了 ${imageFiles.length} 张参考图（附件名: ${imageFiles.map(f => f.name).join(', ')}），在画布中将作为首选画风/主体参考图]：请特别注意在生图提示词中维持与参考图高度一致的风格、色调与角色特征。`;
    }

    const systemPrompt = `你是一名顶级短视频编导与 26Flow 画布工作流架构师。
用户可能会向你发送任意杂乱无章的灵感、随手笔记、小说片段、故事文案、短视频大纲、或者针对之前镜头的修改要求。
你的任务是：
1. 首先用亲切、专业短视频导演的视角，简明扼要向用户点评构思亮点与视觉节奏规划（100字左右）；
2. 随后在回复的末尾，必须附带一个严格合法的纯 JSON 代码块（\`\`\`json ... \`\`\`），包含完整的分镜数组，以便系统一键搭建画布节点。
每个分镜格式规范：
\`\`\`json
[
  {
    "number": 1,
    "title": "场景简明标题",
    "duration": 6,
    "size": "${size}",
    "mode": "${flowMode}",
    "imagePrompt": "精细生图提示词（构图景别、光影质感、色彩基调、艺术风格，符合${style}）",
    "videoPrompt": "精细生视频提示词（推拉摇移运镜动作、主体动态变化、环境音效描述）",
    "negativePrompt": "blurry, low quality, distorted, bad anatomy",
    "continuity": false
  }
]
\`\`\`
规则：
1. 镜头 duration 只能从 [5, 6, 8, 10] 中选取；
2. 总时长尽量匹配 ${targetDuration} 秒（约 ${Math.round(targetDuration / 6)} 个镜头）；
3. 若用户是在多轮对话中修改前述分镜（如“改第2个镜头”、“画风换赛博朋克”），在当前上下文基础上更新该 JSON 分镜列表并输出；
4. 确保 JSON 格式合法。`;

    let replyText = '';
    let parsedScenes = null;
    let source = 'local_ai';
    let modelUsed = state.settings?.orchestrationModel || 'qwen2.5:7b';

    try {
      const messagesForApi = aiChatHistory.map(m => ({ role: m.role, content: m.content }));
      // 将最新富文本输入替换最后一轮 user 消息 content 传给 API
      if (messagesForApi.length && messagesForApi[messagesForApi.length - 1].role === 'user') {
        messagesForApi[messagesForApi.length - 1].content = enrichedPrompt;
      }
      replyText = await callLocalChatLLM({
        prompt: enrichedPrompt,
        systemPrompt,
        messages: messagesForApi,
        endpoint: state.settings?.localApiEndpoint,
        model: modelUsed,
        apiKey: state.settings?.localApiKey
      });

      const parsed = cleanAndParseJson(replyText);
      if (Array.isArray(parsed) && parsed.length > 0) {
        parsedScenes = parsed.map((s, idx) => ({
          number: s.number || idx + 1,
          title: s.title || `分镜 ${idx + 1}`,
          duration: [5, 6, 8, 10].includes(Number(s.duration)) ? Number(s.duration) : 6,
          size: s.size || size,
          mode: s.mode || flowMode,
          imagePrompt: s.imagePrompt || s.image_prompt || '',
          videoPrompt: s.videoPrompt || s.video_prompt || '',
          negativePrompt: s.negativePrompt || s.negative_prompt || 'blurry, low quality, distorted',
          continuity: Boolean(s.continuity)
        }));
      }
    } catch (err) {
      console.warn("本地模型对话调用异常，将采用内置启发式编排规则后备：", err);
    }

    if (!parsedScenes || !parsedScenes.length) {
      parsedScenes = heuristicFallbackOrchestrator(enrichedPrompt, { targetDuration, size, style, flowMode, readyImages: imageFiles });
      source = 'heuristic';
      if (!replyText) {
        replyText = `已根据您的创意，为您规划了 ${parsedScenes.length} 个分镜镜头，画面采用 ${style}，画幅为 ${size}。您可以查看下方分镜卡片，或直接继续在对话中提出修改要求。`;
      }
    }

    if (imageFiles.length > 0 && Array.isArray(parsedScenes)) {
      parsedScenes.forEach((sc, idx) => {
        if (!sc.readyImage && idx < imageFiles.length) {
          sc.readyImage = {
            dataUrl: imageFiles[idx].dataUrl,
            name: imageFiles[idx].name
          };
        }
      });
      if (!replyText || source === 'heuristic') {
        replyText = `检测到您已上传了 ${imageFiles.length} 张满意的分镜底图！已为您自动组装为【纯图生视频】分镜方案，每张底图已量身匹配运镜动作，点击下方按钮即可一键在画布搭建视频工作流并排入时间线！`;
      }
    }

    const displayComment = replyText.replace(/```(?:json)?\s*[\s\S]*?```/gi, '').trim() ||
      `已为您规划并梳理好 ${parsedScenes.length} 个分镜镜头，点击下方按钮即可一键在画布上搭建！`;

    aiChatHistory.push({
      role: 'assistant',
      content: displayComment,
      scenes: parsedScenes,
      source,
      model: modelUsed
    });

    renderAiChatMessages();

    if (statusEl) {
      statusEl.className = 'ok';
      statusEl.textContent = `✔ 分镜规划完成（来源：${source === 'local_ai' ? '本地大模型 ' + modelUsed : '内置启发式编排'}），点击卡片下方按钮即可直接在画布搭建！`;
    }
    if (sendBtn) {
      sendBtn.disabled = false;
      sendBtn.textContent = '🚀 发送';
    }
  }

  const closeChatBtn = $('#closeAiChatModalBtn');
  if (closeChatBtn) closeChatBtn.onclick = () => $('#aiOrchestrateModal').classList.add('hidden');

  const clearChatBtn = $('#clearAiChatBtn');
  if (clearChatBtn) {
    clearChatBtn.onclick = () => {
      aiChatHistory = [];
      pendingChatAttachments = [];
      aiChatSessionUploadedImages = [];
      renderPendingChatAttachments();
      initAiChatSession();
    };
  }

  const toggleParamsBtn = $('#toggleParamsDrawerBtn');
  if (toggleParamsBtn) {
    toggleParamsBtn.onclick = () => {
      const drawer = $('#orchestrateParamsDrawer');
      if (drawer) drawer.classList.toggle('hidden');
    };
  }

  const chatSendBtn = $('#aiChatSendBtn');
  if (chatSendBtn) {
    chatSendBtn.onclick = () => {
      const input = $('#aiChatInput');
      sendAiChatMessage(input?.value);
    };
  }

  // 附件上传按钮与隐藏文件选择器事件监听
  const chatUploadBtn = $('#aiChatUploadBtn');
  const chatFileInput = $('#aiChatFileInput');
  if (chatUploadBtn && chatFileInput) {
    chatUploadBtn.onclick = () => chatFileInput.click();
    chatFileInput.onchange = () => {
      if (chatFileInput.files) {
        Array.from(chatFileInput.files).forEach(addChatFile);
        chatFileInput.value = '';
      }
    };
  }

  // 拖拽文件/图片直接丢入输入区监听
  const composerArea = document.querySelector('.ai-chat-composer-area');
  if (composerArea) {
    composerArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      composerArea.classList.add('drag-over');
    });
    composerArea.addEventListener('dragleave', (e) => {
      e.preventDefault();
      e.stopPropagation();
      composerArea.classList.remove('drag-over');
    });
    composerArea.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      composerArea.classList.remove('drag-over');
      if (e.dataTransfer && e.dataTransfer.files) {
        Array.from(e.dataTransfer.files).forEach(addChatFile);
      }
    });
  }

  const chatInput = $('#aiChatInput');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendAiChatMessage(chatInput.value);
      }
    });
    // 剪贴板粘贴截图或文件监听
    chatInput.addEventListener('paste', (e) => {
      const items = e.clipboardData?.items;
      if (items) {
        let hasFile = false;
        for (let i = 0; i < items.length; i++) {
          if (items[i].kind === 'file') {
            const file = items[i].getAsFile();
            if (file) {
              addChatFile(file);
              hasFile = true;
            }
          }
        }
        if (hasFile && !e.clipboardData.getData('text/plain')) {
          e.preventDefault();
        }
      }
    });
  }

  document.querySelectorAll('.chat-chip-btn').forEach(btn => {
    btn.onclick = () => {
      const text = btn.dataset.text;
      const input = $('#aiChatInput');
      if (input && text) {
        input.value = text;
        input.focus();
      }
    };
  });

  const cancelAiBtn = $('#cancelAiOrchestrateBtn');
  if (cancelAiBtn) cancelAiBtn.onclick = () => $('#aiOrchestrateModal').classList.add('hidden');

  const aiModalBackdrop = $('#aiOrchestrateModal');
  if (aiModalBackdrop) {
    aiModalBackdrop.onclick = (e) => {
      if (e.target.id === 'aiOrchestrateModal') aiModalBackdrop.classList.add('hidden');
    };
  }

  document.querySelectorAll('.idea-preset-btn').forEach(btn => {
    btn.onclick = () => {
      const p = btn.dataset.preset;
      const inp = $('#aiIdeaInput');
      if (!inp) return;
      if (p === 'agri') {
        inp.value = "制作一个30秒的农业科普视频，解释为什么氮肥施得越多，作物不一定吸收得越多。9:16竖屏，自然笔记风格，没有人物口播，只需要环境音效。";
      } else if (p === 'fox') {
        inp.value = "女孩在深秋金黄的森林中发现一只腿部受伤的小赤狐，轻轻将它抱回家细心包扎照顾，春暖花开康复后依依不舍放归大自然。";
      } else if (p === 'coffee') {
        inp.value = "精品手冲咖啡冲煮过程，微距慢动作特写：研磨咖啡豆的颗粒感、92度热水注水时的闷蒸膨胀与丰满气泡、琥珀色咖啡液顺着滤纸滴落，电影感光影。";
      }
    };
  });

  const startAiBtn = $('#startAiOrchestrateBtn');
  if (startAiBtn) {
    startAiBtn.onclick = async () => {
      const idea = ($('#aiIdeaInput')?.value || '').trim();
      if (!idea) {
        const statusEl = $('#orchestrationStatus');
        if (statusEl) { statusEl.className = 'error'; statusEl.textContent = "请输入你的视频创意文案或故事大纲。"; }
        return;
      }
      startAiBtn.disabled = true;
      startAiBtn.textContent = "⏳ 正在分析编排中…";
      try {
        const scenes = await orchestrateVideoScenes(idea, {
          targetDuration: Number($('#aiTargetDurationSelect')?.value || 30),
          size: $('#aiAspectSelect')?.value || '9:16',
          style: $('#aiStylePresetSelect')?.value || '自然写实纪实',
          flowMode: $('#aiVisualFlowSelect')?.value || 'image_to_video'
        });
        renderStoryboardUI();
        $('#orchestrateStepInput').classList.add('hidden');
        $('#orchestrateStepReview').classList.remove('hidden');
      } catch (err) {
        const statusEl = $('#orchestrationStatus');
        if (statusEl) { statusEl.className = 'error'; statusEl.textContent = `编排失败：${err.message || String(err)}`; }
      } finally {
        startAiBtn.disabled = false;
        startAiBtn.textContent = "✨ 开始本地 AI 智能拆镜与编排";
      }
    };
  }

  const backToAiInputBtn = $('#backToAiInputBtn');
  if (backToAiInputBtn) {
    backToAiInputBtn.onclick = () => {
      $('#orchestrateStepReview').classList.add('hidden');
      $('#orchestrateStepInput').classList.remove('hidden');
    };
  }

  const addSceneBtn = $('#addStoryboardSceneBtn');
  if (addSceneBtn) {
    addSceneBtn.onclick = () => {
      const idx = currentStoryboardScenes.length;
      currentStoryboardScenes.push({
        number: idx + 1,
        title: `分镜 ${idx + 1}`,
        duration: 6,
        size: $('#aiAspectSelect')?.value || '9:16',
        mode: $('#aiVisualFlowSelect')?.value || 'image_to_video',
        imagePrompt: '',
        videoPrompt: '',
        negativePrompt: 'blurry, low quality, distorted',
        continuity: false
      });
      renderStoryboardUI();
    };
  }

  const confirmBuildBtn = $('#confirmBuildWorkflowBtn');
  if (confirmBuildBtn) {
    confirmBuildBtn.onclick = () => {
      buildWorkflowFromStoryboard(currentStoryboardScenes, { replace: true });
    };
  }
  $('#scriptImportBtn').onclick=()=>{$('#scriptModal').classList.remove('hidden');$('#scriptImportStatus').textContent='';$('#scriptInput').focus();};
  $('#cancelScriptImport').onclick=()=>$('#scriptModal').classList.add('hidden');
  $('#buildScriptNodes').onclick=buildSceneNodesFromScript;
  $('#scriptModal').onclick=event=>{if(event.target.id==='scriptModal')$('#scriptModal').classList.add('hidden');};
  $('#scriptInput').addEventListener('input',()=>{const count=parseSceneScript($('#scriptInput').value).length;$('#scriptImportStatus').className='';$('#scriptImportStatus').textContent=count?`${count} 个场景已识别。`:'';});
  $('#timelineToggleBtn').onclick=toggleTimeline;
  $('#timelineExportBtn').onclick=exportTimelineVideo;
  $('#timelineImportAllBtn').onclick=importAllVideosToTimeline;
  $('#closeTimelinePreview').onclick=closeTimelinePreview;
  $('#timelineAddVideoBtn').onclick=toggleTimelineOutputMenu;
  $('#timelinePlayBtn').onclick=()=>playTimeline(ensureDockTimeline());
  // A DOM click handler receives the MouseEvent as its first argument. Keep
  // the workflow Run button separate from execute(targetNodeId), which accepts
  // an optional node ID when invoked from a node's own Run button.
  $('#runBtn').onclick=onWorkflowRunButtonClick;
  const runAllBtn=$('#runAllBtn');if(runAllBtn)runAllBtn.onclick=onWorkflowRunAllButtonClick;
  const runImagesOnlyBtn=$('#runImagesOnlyBtn');if(runImagesOnlyBtn)runImagesOnlyBtn.onclick=onWorkflowRunImagesOnlyClick;
  const runVideosOnlyBtn=$('#runVideosOnlyBtn');if(runVideosOnlyBtn)runVideosOnlyBtn.onclick=onWorkflowRunVideosOnlyClick;
  const retryFailedBtn=$('#retryFailedBtn');if(retryFailedBtn)retryFailedBtn.onclick=retryFailedNodes;

  function ensureEndFrameNodeForVideo(videoNodeId) {
    const vNode = nodeById(videoNodeId);
    if (!vNode || vNode.type !== 'generateVideo') return null;
    const shotNum = Number(vNode.data?.shotNumber) || Number((vNode.id.match(/shot_0*(\d+)/i) || [])[1]) || 0;
    const shotId = shotNum > 0 ? String(shotNum).padStart(2, '0') : 'XX';
    const incomingImgNodes = getIncoming(vNode.id, 'reference').map(e => nodeById(e.source)).filter(Boolean);
    const existingEnd = incomingImgNodes.find(s => s.data?.frameRole === 'end' || /end|尾帧|尾图/i.test(`${s.id} ${s.data?.sceneLabel || ''}`));
    if (existingEnd) {
      setRunStatus(`第 ${shotId} 镜已存在尾帧节点 (${existingEnd.data?.sceneLabel || existingEnd.id})。`, 'ok');
      return existingEnd;
    }
    const startImgNode = incomingImgNodes.find(s => s.type === 'generateImage' || s.type === 'imageInput');
    const startPromptText = startImgNode ? (resolvePrompt(startImgNode.id) || '') : '';
    const videoPromptText = resolvePrompt(vNode.id) || '';
    const voText = vNode.data?.voText || startImgNode?.data?.voText || vNode.data?.sceneLabel || '';
    const endPromptText = deriveEndFramePromptText(
      startPromptText || `Shot ${shotId} (${voText}) cinematic keyframe`,
      videoPromptText,
      vNode.data?.sceneLabel || `第${shotId}镜`
    );
    const baseX = startImgNode ? startImgNode.x : (vNode.x - 360);
    const baseY = startImgNode ? (startImgNode.y + 260) : (vNode.y - 160);
    const endPromptNode = makeNode('prompt', baseX - 360, baseY);
    endPromptNode.id = shotNum > 0 && !nodeById(`node_shot_${shotId}_end_img_prompt`) ? `node_shot_${shotId}_end_img_prompt` : endPromptNode.id;
    endPromptNode.data = {
      text: endPromptText,
      sceneLabel: `【第${shotId}镜·尾帧】生图词`,
      shotNumber: shotNum,
      voText
    };
    const endImgNode = makeNode('generateImage', baseX, baseY);
    endImgNode.id = shotNum > 0 && !nodeById(`node_shot_${shotId}_end_img_gen`) ? `node_shot_${shotId}_end_img_gen` : endImgNode.id;
    endImgNode.data = {
      model: startImgNode?.data?.model || state.settings?.defaultImageModel || 'gpt-image-2.5',
      size: vNode.data?.size || startImgNode?.data?.size || '16:9',
      count: 1,
      styleContinuity: true,
      status: 'idle',
      sceneLabel: `【第${shotId}镜·尾帧】${voText.slice(0, 18)}`,
      frameRole: 'end',
      shotNumber: shotNum,
      voText
    };
    state.nodes.push(endPromptNode, endImgNode);
    state.edges.push({
      id: uid('edge'),
      source: endPromptNode.id,
      sourcePort: 'text',
      target: endImgNode.id,
      targetPort: 'prompt'
    });
    // 若首帧有底图，也将首帧连给尾帧生图作为参考以保持角色场景 100% 一致
    if (startImgNode) {
      state.edges.push({
        id: uid('edge'),
        source: startImgNode.id,
        sourcePort: 'image',
        target: endImgNode.id,
        targetPort: 'reference'
      });
    }
    state.edges.push({
      id: uid('edge'),
      source: endImgNode.id,
      sourcePort: 'image',
      target: vNode.id,
      targetPort: 'reference'
    });
    render();
    scheduleAutoSave();
    setRunStatus(`✓ 已为第 ${shotId} 镜自动创建【尾帧生图词 + 尾帧图】节点并连入视频节点！点击尾帧节点的“▶ 生成图片”即可生成尾帧。`, 'ok');
    return endImgNode;
  }

  async function exportNamedVideosAndCueSheet() {
    const timeline = state.nodes.find(n => n.type === 'timeline');
    const orderedIds = (timeline?.data?.clipOrder || []).filter(id => nodeById(id)?.type === 'generateVideo');
    const allVideos = [
      ...orderedIds.map(id => nodeById(id)),
      ...state.nodes.filter(n => n.type === 'generateVideo' && !orderedIds.includes(n.id))
    ].filter(Boolean);

    if (!allVideos.length) {
      setRunStatus('当前画布还没有任何视频节点。', 'warn');
      return;
    }
    const sanitizeFilePart = (str) => String(str || '')
      .replace(/[\\/:*?"<>|“”—\r\n]+/g, '')
      .replace(/\s+/g, '_')
      .slice(0, 36) || '未命名文案';

    let downloadedCount = 0;
    const cueRows = [];
    const hasZip = typeof JSZip !== 'undefined';
    const zip = hasZip ? new JSZip() : null;
    setRunStatus(`⏳ 正在准备导出 ${allVideos.length} 条分镜视频${hasZip ? '（ZIP 一键打包模式）' : ''}...`, 'info');

    for (let idx = 0; idx < allVideos.length; idx++) {
      const vNode = allVideos[idx];
      const shotNum = Number(vNode.data?.shotNumber) || (idx + 1);
      const shotId = String(shotNum).padStart(2, '0');
      const editSec = Number(vNode.data?.editDuration) || Number(timeline?.data?.durations?.[vNode.id]) || 3.5;
      const voText = vNode.data?.voText || vNode.data?.sceneLabel || `第${shotId}镜`;
      const cleanVo = sanitizeFilePart(voText);
      const fileName = `${shotId}_[剪${editSec}s]_${cleanVo}.mp4`;
      const refs = resolveReferences(vNode.id);
      const startThumb = refs.find(r => r.role === 'start')?.url || '';
      const endThumb = refs.find(r => r.role === 'end')?.url || vNode.data?.endFrame?.url || '';
      const hasVideo = Boolean(vNode.data?.asset?.url);

      cueRows.push({
        shotId,
        editSec,
        voText,
        fileName,
        hasVideo,
        startThumb,
        endThumb,
        promptText: resolvePrompt(vNode.id) || ''
      });

      if (hasVideo) {
        try {
          setRunStatus(`⏳ 正在读取第 ${shotId} 镜 10s 视频 (${idx + 1}/${allVideos.length})${hasZip ? ' 并加入压缩包' : ''}...`, 'info');
          const resp = await fetch(vNode.data.asset.url);
          const blob = await resp.blob();
          if (zip) {
            zip.file(fileName, blob);
            downloadedCount++;
          } else {
          const objUrl = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = objUrl;
          a.download = fileName;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(objUrl), 4000);
          downloadedCount++;
          await new Promise(r => setTimeout(r, 220));
          }
        } catch (err) {
          console.warn(`导出第 ${shotId} 镜视频失败:`, err);
        }
      }
    }

    // 同时导出一份直观的《00_分镜文案与视频剪辑对照单.html》
    const htmlContent = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>分镜口播文案与视频剪辑对照单</title>
<style>
  body { font-family: "Microsoft YaHei", sans-serif; background: #11141c; color: #eef2ff; padding: 24px; }
  h1 { font-size: 20px; margin-bottom: 8px; }
  p.sub { color: #9aa5c4; font-size: 13px; margin-bottom: 18px; }
  table { width: 100%; border-collapse: collapse; background: #191d28; border-radius: 8px; overflow: hidden; }
  th, td { border: 1px solid #2b3245; padding: 10px 12px; text-align: left; vertical-align: middle; font-size: 13px; }
  th { background: #222838; color: #a7bfff; }
  .vo { font-size: 15px; font-weight: 700; color: #ffffff; }
  .fname { font-family: Consolas, monospace; color: #65e898; font-weight: 600; }
  .thumb { width: 120px; height: 68px; object-fit: cover; border-radius: 4px; border: 1px solid #3c4663; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; background: #2c3e50; color: #ffd166; font-weight: 600; }
</style>
</head>
<body>
  <h1>🎬 分镜口播文案与 10s 视频剪辑对照单（共 ${cueRows.length} 镜）</h1>
  <p class="sub">所有导出的 MP4 已直接按【镜号_[剪辑秒数]_对应口播文案.mp4】命名，拖入剪映即可按文件名直接对齐音频字幕。</p>
  <table>
    <thead>
      <tr>
        <th>镜号</th>
        <th>建议剪辑时长</th>
        <th>🎙️ 对应口播文案（字幕原句）</th>
        <th>首帧参考图</th>
        <th>尾帧参考图</th>
        <th>导出 MP4 文件名（10s 原片）</th>
      </tr>
    </thead>
    <tbody>
      ${cueRows.map(r => `<tr>
        <td><strong>第 ${r.shotId} 镜</strong></td>
        <td><span class="badge">${r.editSec} 秒</span></td>
        <td class="vo">${escapeHtml(r.voText)}</td>
        <td>${r.startThumb ? `<img class="thumb" src="${r.startThumb}"/>` : '无'}</td>
        <td>${r.endThumb ? `<img class="thumb" src="${r.endThumb}"/>` : '无'}</td>
        <td class="fname">${escapeHtml(r.fileName)} ${r.hasVideo ? '✅' : '⏳(未生成)'}</td>
      </tr>`).join('')}
    </tbody>
  </table>
</body>
</html>`;
    if (zip) {
      zip.file('00_分镜文案与视频剪辑对照单.html', htmlContent);
      setRunStatus(`⏳ 正在生成 ZIP 压缩包 (共 ${downloadedCount} 条 10s 视频)...`, 'info');
      const zipBlob = await zip.generateAsync({ type: 'blob', compression: 'STORE' }, (meta) => {
        setRunStatus(`⏳ 正在生成最终 ZIP 压缩包 (${meta.percent.toFixed(0)}%)...`, 'info');
      });
      const zipUrl = URL.createObjectURL(zipBlob);
      const a = document.createElement('a');
      a.href = zipUrl;
      const dStr = new Date().toISOString().slice(0, 10);
      a.download = `分镜视频与对照单_${downloadedCount}镜10s打包_${dStr}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(zipUrl), 8000);
      setRunStatus(`✓ 已成功将全部 ${downloadedCount} 条 10s 视频与剪辑对照单打包导出为 1 个 ZIP 文件！`, 'ok');
    } else {
    const htmlBlob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
    const htmlUrl = URL.createObjectURL(htmlBlob);
    const link = document.createElement('a');
    link.href = htmlUrl;
    link.download = '00_分镜文案与视频剪辑对照单.html';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(htmlUrl), 4000);
    setRunStatus(`✓ 已按【镜号+口播文案】导出 ${downloadedCount} 条 10s 视频，并生成《00_分镜文案与视频剪辑对照单.html》！`, 'ok');
    }
  }

  function promptAndRunShotRange() {
    if (state.isRunning) {
      setRunStatus('当前正在运行中，请先停止后再启动区间运行。', 'warn');
      return;
    }
    const rangeInput = window.prompt(
      '【多浏览器 / 多账号分流运行】\n请输入当前浏览器要运行的【分镜区间】（例如：1-5 或 6-10 或 11-15）：',
      '1-5'
    );
    if (!rangeInput || !rangeInput.trim()) return;
    const m = rangeInput.trim().match(/^(\d+)\s*(?:[-~～至,，\s]\s*(\d+))?$/);
    if (!m) {
      setRunStatus('分镜区间格式不正确，请输入如 1-5 或 6-10。', 'error');
      return;
    }
    const startShot = Number(m[1]);
    const endShot = Number(m[2] || m[1]);
    const minShot = Math.min(startShot, endShot);
    const maxShot = Math.max(startShot, endShot);

    const modeInput = window.prompt(
      `已选择运行【第 ${minShot} 镜 ～ 第 ${maxShot} 镜】。\n请选择运行类型：\n输入 1 = 🎬 仅做视频（10s 原片，推荐）\n输入 2 = 🖼 仅跑首尾帧分镜图片\n输入 3 = 🚀 图片+视频全部运行`,
      '1'
    );
    if (!modeInput) return;
    const mode = modeInput.trim();
    const wantType = mode === '2' ? 'generateImage' : (mode === '1' ? 'generateVideo' : null);

    const targetIds = state.nodes
      .filter(n => {
        if (!['generateImage', 'generateVideo'].includes(n.type)) return false;
        if (wantType && n.type !== wantType) return false;
        const sNum = Number(n.data?.shotNumber) || Number((n.id.match(/shot_0*(\d+)/i) || [])[1]) || 0;
        return sNum >= minShot && sNum <= maxShot;
      })
      .map(n => n.id);

    if (!targetIds.length) {
      setRunStatus(`未找到第 ${minShot}~${maxShot} 镜对应的生成节点。`, 'warn');
      return;
    }
    setRunStatus(`🎯 开始区间运行：第 ${minShot}～${maxShot} 镜（共 ${targetIds.length} 个节点）…`, 'warn');
    void execute(targetIds, { forceAll: false, onlyType: wantType });
  }

  const exportNamedVideosBtn = $('#exportNamedVideosBtn');
  if (exportNamedVideosBtn) exportNamedVideosBtn.onclick = () => void exportNamedVideosAndCueSheet();
  const runShotRangeBtn = $('#runShotRangeBtn');
  if (runShotRangeBtn) runShotRangeBtn.onclick = () => promptAndRunShotRange();
  const localApiQuickBtn=$('#localApiQuickBtn');
  if(localApiQuickBtn){
    localApiQuickBtn.onclick=()=>{
      syncSettingsUI();
      $('#settingsModal').classList.remove('hidden');
    };
  }
  document.querySelectorAll('.preset-btn').forEach(btn=>{
    btn.onclick=()=>{
      const inp=$('#localApiEndpointInput');
      if(inp){
        inp.value=btn.dataset.url;
        testAndFetchLocalModels();
      }
    };
  });
  $('#saveBtn').onclick=saveState; $('#resetBtn').onclick=resetState;
  $('#workflowExportBtn').onclick=exportWorkflowFile;
  $('#workflowImportBtn').onclick=()=>$('#workflowFileInput').click();
  $('#workflowFileInput').onchange=event=>{const file=event.target.files?.[0];event.target.value='';if(file)void importWorkflowFile(file);};
  window.exportDiagnosticsJson = exportDiagnosticsJson;
  window._museflow = { state, execute, render, nodeById, queueWorkflowSave, saveState, resetState, t05Probe };
  window.getExecutionDiagnostics = () => state.executionDiagnostics || [];
  $('#settingsBtn').onclick=()=>{syncSettingsUI();$('#settingsModal').classList.remove('hidden');};
  $('#testMuseBtn').onclick=()=>testMuseSession();
  const testLocalBtn=$('#testLocalApiBtn');
  if(testLocalBtn)testLocalBtn.onclick=()=>testAndFetchLocalModels();

  async function saveSettingsFromUI(closeModal = false) {
    state.settings=state.settings||{};
    const providerSelect=$('#imageApiProviderSelect') || $('#settingProvider');
    if(providerSelect)state.settings.imageProvider=providerSelect.value;
    const endpointInput=$('#localApiEndpointInput') || $('#settingBaseUrl');
    if(endpointInput && endpointInput.value.trim()) state.settings.localApiEndpoint=endpointInput.value.trim();
    const keyInput=$('#localApiKeyInput') || $('#settingApiKey');
    if(keyInput) state.settings.localApiKey=keyInput.value.trim();
    const orchInput=$('#orchestrationModelInput');
    if(orchInput)state.settings.orchestrationModel=orchInput.value.trim()||'qwen2.5:7b';
    const defaultSelect=$('#defaultImageModelSelect') || $('#settingDefaultImageModel');
    if(defaultSelect)state.settings.defaultImageModel=defaultSelect.value;
    const concurrencySelect=$('#localImageConcurrencySelect');
    if(concurrencySelect){
      const parsed=parseInt(concurrencySelect.value,10);
      state.settings.localImageConcurrency=(!isNaN(parsed)&&parsed>=1&&parsed<=4)?parsed:2;
    }
    // 双轨持久化锁定：独立存储 + 工作流快照，双重保险
    await persistGlobalSettings(state.settings);
    await saveState();
    if (closeModal) $('#settingsModal').classList.add('hidden');
  }

  let settingsAutoDebounceTimer = null;
  function bindSettingsAutoPersist() {
    const inputs = ['#localApiEndpointInput', '#settingBaseUrl', '#localApiKeyInput', '#settingApiKey', '#orchestrationModelInput', '#imageApiProviderSelect', '#settingProvider', '#defaultImageModelSelect', '#localImageConcurrencySelect'];
    inputs.forEach(sel => {
      const el = $(sel);
      if (el && !el._persistBound) {
        el._persistBound = true;
        el.addEventListener('input', () => {
          clearTimeout(settingsAutoDebounceTimer);
          settingsAutoDebounceTimer = setTimeout(() => saveSettingsFromUI(false), 250);
        });
        el.addEventListener('change', () => {
          clearTimeout(settingsAutoDebounceTimer);
          saveSettingsFromUI(false);
        });
      }
    });
  }

  $('#closeSettingsBtn').onclick=async()=>{
    await saveSettingsFromUI(true);
  };
  $('#saveSettingsBtn').onclick=async()=>{
    await saveSettingsFromUI(true);
    setRunStatus("✓ 本地 API 与模型配置已持久化保存", 'ok');
    render();
  };
  const addCustomBtn=$('#addCustomModelBtn');
  if(addCustomBtn){
    addCustomBtn.onclick=()=>{
      const inp=$('#customModelInput');
      const val=inp?.value?.trim();
      if(val){
        addCustomImageModel(val);
        inp.value='';
        syncSettingsUI();
        render();
      }
    };
  }
  $('#settingsModal').onclick=async(e)=>{
    if(e.target.id==='settingsModal') await saveSettingsFromUI(true);
  };
  window.addEventListener('resize',drawEdges);
  window.addEventListener('pointermove',onWireMove);
  window.addEventListener('pointermove',moveSelectionMarquee);
  window.addEventListener('pointerup',onWireUp);
  window.addEventListener('pointerup',endSelectionMarquee);
  window.addEventListener('pointercancel',endSelectionMarquee);
  $('#viewport').addEventListener('wheel',event=>{event.preventDefault();const factor=Math.exp(-event.deltaY*.0015);zoomAt(event.clientX,event.clientY,factor);},{passive:false});
  // 全局捕获阶段：只要按下空格键或处于手掌模式或鼠标中键，全屏任意位置（包括卡片、图片、边框、背景、文本框）一律最高优先级触发画布平移
  window.addEventListener('pointerdown', event => {
    // 点击任意非输入框区域时，立即让之前残留焦点的输入框失焦
    if (document.activeElement && isTextEntry(document.activeElement) && !isTextEntry(event.target)) {
      document.activeElement.blur();
    }
    const isSpacePan = (state.spaceDown || state.handMode) && event.button === 0;
    const isMiddlePan = event.button === 1;
    if (isSpacePan || isMiddlePan) {
      if (event.target.closest('.canvas-tools, .modal:not(.hidden)')) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      startPan(event);
    }
  }, true);
  $('#viewport').addEventListener('pointerdown',startSelectionMarquee);
  document.addEventListener('pointerdown',event=>{const stop=event.target.closest('[data-stop-generation]');if(!stop)return;if(event.pointerType==='mouse'&&event.detail>1)return;event.preventDefault();event.stopImmediatePropagation();stopGeneration(stop.dataset.stopGeneration);},true);
  window.addEventListener('pointermove',movePan);window.addEventListener('pointerup',endPan);window.addEventListener('pointercancel',endPan);
  $('#handTool').onclick=()=>{state.handMode=!state.handMode;applyCanvasTransform();$('#handTool').classList.toggle('active',state.handMode);};
  $('#zoomIn').onclick=()=>setZoom(Math.min(2.5,state.zoom*1.15));$('#zoomOut').onclick=()=>setZoom(Math.max(.25,state.zoom/1.15));$('#fitCanvas').onclick=fitCanvas;
  const autoLayoutBtn=$('#autoLayoutBtn');if(autoLayoutBtn)autoLayoutBtn.onclick=autoLayoutWorkflow;
    const topAutoLayoutBtn=$('#topAutoLayoutBtn');if(topAutoLayoutBtn)topAutoLayoutBtn.onclick=autoLayoutWorkflow;
  $('#viewport').addEventListener('contextmenu',openCanvasMenu);
  document.addEventListener('input',event=>{if(event.target.closest('.node,.timeline-dock,#settingsModal'))scheduleAutoSave();},true);
  document.addEventListener('change',event=>{if(event.target.closest('.node,.timeline-dock,#settingsModal'))scheduleAutoSave();},true);
  $('#canvasMenu').addEventListener('click',e=>{const item=e.target.closest('[data-context-action]');if(!item)return;if(item.dataset.contextAction==='connect-choice')runConnectionChoice(Number(item.dataset.choice));else runCanvasAction(item.dataset.contextAction);});
  edgesSvg.addEventListener('contextmenu',openEdgeMenu);
  edgesSvg.addEventListener('pointerdown',selectEdgePointer);
  canvas.addEventListener('contextmenu',openCanvasMenu);
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('#canvasMenu')){closeCanvasMenu();state.pendingConnection=null;}});
  const isTextEntry = target => Boolean(target?.closest?.('textarea,input,select,[contenteditable="true"]'));
  let lastHoveredElement = null;
  const updateHovered = e => { lastHoveredElement = e.target; };
  document.addEventListener('pointermove', updateHovered, { passive: true });
  document.addEventListener('pointerover', updateHovered, { passive: true });
  document.addEventListener('pointerdown', updateHovered, { passive: true });

  document.addEventListener('keydown', e => {
    if (e.code === 'Space') {
      // 1. 中文/拼音输入法候选打字阶段绝不拦截空格
      if (e.isComposing || e.keyCode === 229) return;

      const activeIsText = isTextEntry(document.activeElement);
      const hoveredIsText = isTextEntry(lastHoveredElement);

      // 2. 如果焦点在输入框内：鼠标移出输入框时自动失焦并激活抓手；鼠标在框内打字则正常输入文字空格
      if (activeIsText) {
        if (!hoveredIsText) {
          document.activeElement.blur();
        } else {
          return;
        }
      }

      // 3. 激活全局抓手
      e.preventDefault();
      if (!e.repeat) {
        state.spaceDown = true;
        applyCanvasTransform();
        if (document.activeElement?.matches?.('button')) document.activeElement.blur();
      }
      return;
    }
    if(e.altKey&&e.key.toLowerCase()==='l'){e.preventDefault();autoLayoutWorkflow();return;}
    if(e.key==='Escape'){
      if (isTextEntry(document.activeElement)) document.activeElement.blur();
      closeCanvasMenu();
      endSelectionMarquee();
    }
    if((e.key==="删除"||e.key==='Backspace')&&!isTextEntry(e.target)){e.preventDefault();if(state.selectedEdgeIds.length){const ids=new Set(state.selectedEdgeIds);state.edges=state.edges.filter(edge=>!ids.has(edge.id));state.selectedEdgeIds=[];render();saveState();setRunStatus("已删除选中的连接。",'ok');}else removeSelectedNodes();}
    if(e.key.toLowerCase()==='h'&&!isTextEntry(e.target)){state.handMode=!state.handMode;$('#handTool').classList.toggle('active',state.handMode);applyCanvasTransform();}
  },true);
  document.addEventListener('keyup', e => { if (e.code === 'Space') { state.spaceDown = false; applyCanvasTransform(); } }, true);
  window.addEventListener('blur',()=>{state.spaceDown=false;endPan();endSelectionMarquee();applyCanvasTransform();});

  // Keep the session indicator fresh when Muse is opened/reloaded after the canvas.
  chrome.tabs.onUpdated.addListener((tabId,changeInfo,tab)=>{
    if(changeInfo.status==='complete'&&/^https:\/\/(?:[^/]+\.)?muse\.ai\//i.test(tab.url||''))testMuseSession(tabId);
  });
  chrome.tabs.onCreated.addListener(tab=>{
    if(/^https:\/\/(?:[^/]+\.)?muse\.ai\//i.test(tab.url||''))setTimeout(()=>testMuseSession(tab.id),1200);
  });

  loadState(); detectMuse();applyCanvasTransform();
})();
