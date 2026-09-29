// Video Farm Studio - Modern Frontend Engine (Dual Engine: Google Flow & Gemini Web)
document.addEventListener("DOMContentLoaded", () => {
  // ==================== 全局状态 ====================
  const state = {
    currentEngine: "flow", // "flow" 或 "gemini"
    currentMode: "single", // "single" 或 "batch"
    overview: null,
    profiles: [],
    tasks: [],
    currentFilter: "all",
    currentAspect: "16:9",
    currentDuration: 8,
    startFile: null,
    startImagePath: null,
    endFile: null,
    endImagePath: null,
    imageRefFile: null,
    currentTaskForQA: null,
    currentTaskForVideo: null,
    currentTaskForLog: null,
    pollTimer: null
  };

  // ==================== DOM 元素映射 ====================
  const el = {
    schedulerDot: document.getElementById("scheduler-dot"),
    schedulerText: document.getElementById("scheduler-status-text"),
    btnToggleScheduler: document.getElementById("btn-toggle-scheduler"),
    statIdleProf: document.getElementById("stat-idle-prof"),
    statRunningTask: document.getElementById("stat-running-task"),
    statQueuedTask: document.getElementById("stat-queued-task"),
    statCompletedTask: document.getElementById("stat-completed-task"),
    badgeTotalTasks: document.getElementById("badge-total-tasks"),
    badgeTotalProfiles: document.getElementById("badge-total-profiles"),
    lastRefreshTime: document.getElementById("last-refresh-time"),

    // Tab 视图
    tabs: document.querySelectorAll(".tab-button"),
    panes: document.querySelectorAll(".view-pane"),

    // 双生成引擎切换
    btnEngineFlow: document.getElementById("btn-engine-flow"),
    btnEngineGemini: document.getElementById("btn-engine-gemini"),

    // 生成模式切换
    btnModeSingle: document.getElementById("btn-mode-single"),
    btnModeBatch: document.getElementById("btn-mode-batch"),
    singleShotPanel: document.getElementById("single-shot-panel"),
    batchShotPanel: document.getElementById("batch-shot-panel"),

    // 首尾帧拖拽卡片
    dropStart: document.getElementById("drop-start-frame"),
    dropEnd: document.getElementById("drop-end-frame"),
    inputStart: document.getElementById("file-input-start"),
    inputEnd: document.getElementById("file-input-end"),
    previewStart: document.getElementById("img-preview-start"),
    previewEnd: document.getElementById("img-preview-end"),
    placeholderStart: document.getElementById("placeholder-start"),
    placeholderEnd: document.getElementById("placeholder-end"),
    aspectTagStart: document.getElementById("aspect-tag-start"),
    aspectTagEnd: document.getElementById("aspect-tag-end"),
    btnSwapFrames: document.getElementById("btn-swap-frames"),
    stageHintText: document.getElementById("stage-hint-text"),

    // 提示词与表单
    inputPrompt: document.getElementById("input-prompt"),
    btnUseDefaultPrompt: document.getElementById("btn-use-default-prompt"),
    quickChips: document.querySelectorAll(".chip-btn"),
    advToggle: document.getElementById("accordion-toggle-adv"),
    advBody: document.getElementById("accordion-body-adv"),
    advArrow: document.getElementById("adv-arrow"),
    selectAspect: document.getElementById("select-aspect"),
    selectDuration: document.getElementById("select-duration"),
    selectPriority: document.getElementById("select-priority"),
    selectAssignedProf: document.getElementById("select-assigned-profile"),
    selectBatchProfile: document.getElementById("select-batch-profile"),
    checkRequireClean: document.getElementById("check-require-clean"),
    btnSubmitTask: document.getElementById("btn-submit-task"),
    btnResetForm: document.getElementById("btn-reset-form"),
    selectVideoModel: document.getElementById("select-video-model"),
    inputCustomModel: document.getElementById("input-custom-model"),
    stagePanelTitle: document.getElementById("stage-panel-title"),
    badgeAspectInfo: document.getElementById("badge-aspect-info"),
    badgeDurationInfo: document.getElementById("badge-duration-info"),
    badgeModelTag: document.getElementById("badge-model-tag"),
    labelModelTitle: document.getElementById("label-model-title"),
    modelDescHint: document.getElementById("model-desc-hint"),

    // 图像工坊 DOM 映射
    inputImagePrompt: document.getElementById("input-image-prompt"),
    selectImageModel: document.getElementById("select-image-model"),
    selectImageAspect: document.getElementById("select-image-aspect"),
    selectImageProfile: document.getElementById("select-image-profile"),
    dropImageRef: document.getElementById("drop-image-ref"),
    fileInputImageRef: document.getElementById("file-input-image-ref"),
    imgPreviewRef: document.getElementById("img-preview-ref"),
    placeholderImageRef: document.getElementById("placeholder-image-ref"),
    btnClearImageRef: document.getElementById("btn-clear-image-ref"),
    btnSubmitImageTask: document.getElementById("btn-submit-image-task"),
    btnImageExampleStart: document.getElementById("btn-image-example-start"),
    btnImageExampleEnd: document.getElementById("btn-image-example-end"),
    imageGalleryList: document.getElementById("image-gallery-list"),
    galleryCount: document.getElementById("gallery-count"),
    btnRefreshImages: document.getElementById("btn-refresh-images"),

    countVideo: document.getElementById("count-video"),
    countImage: document.getElementById("count-image"),

    // 大图预览弹窗
    modalImageViewer: document.getElementById("modal-image-viewer"),
    imageViewerImg: document.getElementById("image-viewer-img"),
    imageViewerTitle: document.getElementById("image-viewer-title"),
    btnViewerSetStart: document.getElementById("btn-viewer-set-start"),
    btnViewerSetEnd: document.getElementById("btn-viewer-set-end"),
    btnViewerDownload: document.getElementById("btn-viewer-download"),

    // 批量导入
    inputBatchJson: document.getElementById("input-batch-json"),
    btnLoadSampleBatch: document.getElementById("btn-load-sample-batch"),
    btnSubmitBatch: document.getElementById("btn-submit-batch"),

    // 任务视图
    filterBtns: document.querySelectorAll(".filter-btn"),
    tasksContainer: document.getElementById("tasks-container"),
    btnRefreshTasks: document.getElementById("btn-refresh-tasks"),
    countAll: document.getElementById("count-all"),
    countRunning: document.getElementById("count-running"),
    countQueued: document.getElementById("count-queued"),
    countCompleted: document.getElementById("count-completed"),
    countFailed: document.getElementById("count-failed"),

    // 账号管理视图
    profilesContainer: document.getElementById("profiles-container"),
    btnOpenAddProfile: document.getElementById("btn-open-add-profile"),
    btnRefreshProfiles: document.getElementById("btn-refresh-profiles"),

    // 弹窗
    modalVideo: document.getElementById("modal-video-player"),
    html5Video: document.getElementById("html5-video"),
    playerTitle: document.getElementById("player-title"),
    playerMeta: document.getElementById("player-meta"),
    btnOpenTaskFile: document.getElementById("btn-open-task-file"),

    modalQA: document.getElementById("modal-qa-detail"),
    qaModalTitle: document.getElementById("qa-modal-title"),
    qaModalSub: document.getElementById("qa-modal-sub"),
    qaFirstBadge: document.getElementById("qa-first-ncc-badge"),
    qaFirstDesc: document.getElementById("qa-first-desc"),
    qaLastBadge: document.getElementById("qa-last-ncc-badge"),
    qaLastDesc: document.getElementById("qa-last-desc"),
    qaImgStartOrigin: document.getElementById("qa-img-start-origin"),
    qaImgFirstExtracted: document.getElementById("qa-img-first-extracted"),
    qaImgEndOrigin: document.getElementById("qa-img-end-origin"),
    qaImgLastExtracted: document.getElementById("qa-img-last-extracted"),
    qaImgWatermarkCorner: document.getElementById("qa-img-watermark-corner"),
    qaWatermarkTitle: document.getElementById("qa-watermark-title"),
    qaWatermarkDetail: document.getElementById("qa-watermark-detail"),
    qaEventsList: document.getElementById("qa-events-list"),

    // 任务日志弹窗
    modalTaskLog: document.getElementById("modal-task-log"),
    logModalTitle: document.getElementById("log-modal-title"),
    logModalSub: document.getElementById("log-modal-sub"),
    logModalContent: document.getElementById("log-modal-content"),

    modalAddProfile: document.getElementById("modal-add-profile"),
    inputProfName: document.getElementById("input-prof-name"),
    inputProfLabel: document.getElementById("input-prof-label"),
    inputProfNotes: document.getElementById("input-prof-notes"),
    btnConfirmAddProfile: document.getElementById("btn-confirm-add-profile"),

    modalSysinfo: document.getElementById("modal-sysinfo"),
    btnOpenSysinfo: document.getElementById("btn-open-sysinfo"),
    btnOpenOutputs: document.getElementById("btn-open-outputs"),
    toastShelf: document.getElementById("toast-shelf")
  };

  // ==================== 工具函数 ====================
  function showToast(msg, type = "info", duration = 3200) {
    const toast = document.createElement("div");
    toast.className = "toast toast-" + type;
    let icon = "ℹ️";
    if (type === "success") icon = "✅";
    if (type === "warn") icon = "⚠️";
    if (type === "error") icon = "❌";

    toast.innerHTML = "<span style=\"font-size:16px;\">" + icon + "</span><span style=\"flex:1;\">" + escapeHtml(msg) + "</span>";
    el.toastShelf.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  function escapeJs(str) {
    if (!str) return "";
    return String(str)
      .replace(/\\/g, "\\\\")
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\"')
      .replace(/\n/g, "\\n")
      .replace(/\r/g, "");
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // 统一刷新按钮动效与防抖辅助函数
  async function triggerRefreshButton(btn, asyncAction, toastMsg) {
    if (!btn || btn.classList.contains("btn-spinning")) return;
    btn.classList.add("btn-spinning");
    const origHtml = btn.innerHTML;
    btn.innerHTML = `<span class="spin-icon">🔄</span> ${origHtml.replace(/🔄\s*/, "")}`;
    const startTime = Date.now();
    try {
      await asyncAction();
      const elapsed = Date.now() - startTime;
      if (elapsed < 400) {
        await new Promise(r => setTimeout(r, 400 - elapsed));
      }
      if (typeof fetchOverview === "function") {
        fetchOverview();
      }
      if (toastMsg) showToast(toastMsg, "info");
    } catch (e) {
      showToast("刷新失败: " + e.message, "error");
    } finally {
      btn.innerHTML = origHtml;
      btn.classList.remove("btn-spinning");
    }
  }

  // ==================== Tab 切换 ====================
  el.tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      el.tabs.forEach(t => t.classList.remove("active"));
      el.panes.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");

      if (targetId === "view-tasks") fetchTasks();
      if (targetId === "view-images") { fetchTasks().then(() => renderImageGallery()); }
      if (targetId === "view-profiles") fetchProfiles();
    });
  });

  // ==================== 模型数据字典与动态联动 ====================
  const VIDEO_ENGINE_MODELS = {
    flow: [
      { value: "veo-lite", label: "Veo 3.1 Lite (推荐 · 经济稳定 · 默认)", desc: "Google Flow 默认模型，综合效果稳定，生成速度快，抗风控好" },
      { value: "veo-quality", label: "Veo 3.1 Quality (高精画质 · 商业旗舰)", desc: "更高分辨率与材质细节，适合高质感商业产品展示与宣传片" },
      { value: "veo-fast", label: "Veo 3.1 Fast (快速响应模式)", desc: "出片速度优先，适合快速调试分镜、镜头轨迹与动态" },
      { value: "omni-flash", label: "Omni Flash (首尾帧支持 · 解锁10秒)", desc: "支持10秒长镜头生成，首尾帧过渡连贯，多场景运动平滑" },
      { value: "veo-lite-lp", label: "Veo 3.1 Lite LP (低功耗备份)", desc: "备用轻量模型，额度或并发紧张时自动分流" },
      { value: "custom", label: "🛠️ 自定义模型代码 (手动指定)...", desc: "自由输入任意已在 Google Flow 开放的内部模型代号" }
    ],
    gemini: [
      { value: "auto", label: "✨ Auto 智能优选 (官方推荐 · 全自动分流)", desc: "由 Gemini 官方算法根据提示词与输入素材，自动分流匹配最佳 Veo 视频引擎" },
      { value: "gemini-3.8-flash", label: "Gemini 3.8 Flash (疾速响应 · 推荐高频版)", desc: "最新 3.8 代高频极速多模态模型，响应极快，高画质生成与高效预览" },
      { value: "gemini-3.8-pro", label: "Gemini 3.8 Pro / Advanced (画质与光影增强 · 商业旗舰)", desc: "最新 3.8 代旗舰架构，超强多模态理解与物理规律模拟，适合高质感视频与复杂镜头" },
      { value: "gemini-3.8-thinking", label: "Gemini 3.8 Flash Thinking (深度物理推演 · 连贯动作)", desc: "具备深度思维链推演能力，强化镜头运动稳定性与物理逻辑一致性" },
      { value: "gemini-3.0-flash", label: "Gemini 3.0 Flash (经典极速标准版)", desc: "经典 3.0 标准版模型，快速响应日常出片任务" },
      { value: "gemini-3.0-pro", label: "Gemini 3.0 Pro (高精画质稳定版)", desc: "经典 3.0 旗舰基座，多模态综合能力均衡" },
      { value: "custom", label: "🛠️ 自定义模型代码 (手动指定)...", desc: "支持输入任意前沿 Gemini 模型代号 (如 gemini-3.8-flash-preview 等)" }
    ]
  };

  function updateModelOptions(engine, selectedValue) {
    if (!el.selectVideoModel) return;
    const models = VIDEO_ENGINE_MODELS[engine] || VIDEO_ENGINE_MODELS.flow;
    el.selectVideoModel.innerHTML = "";
    models.forEach((m, idx) => {
      const opt = document.createElement("option");
      opt.value = m.value;
      opt.textContent = m.label;
      if (selectedValue ? m.value === selectedValue : idx === 0) {
        opt.selected = true;
      }
      el.selectVideoModel.appendChild(opt);
    });
    updateModelHint();
  }

  function updateModelHint() {
    if (!el.selectVideoModel || !el.modelDescHint) return;
    const engine = state.currentEngine || "flow";
    const models = VIDEO_ENGINE_MODELS[engine] || [];
    const curVal = el.selectVideoModel.value;
    const found = models.find(m => m.value === curVal);
    if (found) {
      el.modelDescHint.textContent = `⚡ ${found.desc}`;
    }
    if (el.inputCustomModel) {
      if (curVal === "custom") {
        el.inputCustomModel.style.display = "block";
        el.inputCustomModel.focus();
      } else {
        el.inputCustomModel.style.display = "none";
      }
    }
  }

  if (el.selectVideoModel) {
    el.selectVideoModel.addEventListener("change", updateModelHint);
  }

  // ==================== 画幅比例与时长动态控制 ====================
  const ASPECT_CONFIG = {
    "16:9": { label: "16:9 横屏宽幅", stage: "16:9 横屏", resHint: "推荐 16:9 (如 1280x720 或 1920x1080)" },
    "9:16": { label: "9:16 竖屏长幅", stage: "9:16 竖屏", resHint: "推荐 9:16 (如 720x1280 或 1080x1920)" },
    "1:1":  { label: "1:1 方形画幅",  stage: "1:1 方形",  resHint: "推荐 1:1 (如 1080x1080)" }
  };

  function setAspectRatio(aspect) {
    if (!ASPECT_CONFIG[aspect]) aspect = "16:9";
    state.currentAspect = aspect;
    if (el.selectAspect) el.selectAspect.value = aspect;
    if (el.badgeAspectInfo) el.badgeAspectInfo.textContent = ASPECT_CONFIG[aspect].label;

    document.querySelectorAll(".aspect-pill-btn").forEach(btn => {
      if (btn.getAttribute("data-aspect") === aspect) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    const aspectClass = aspect === "16:9" ? "aspect-16-9" : (aspect === "1:1" ? "aspect-1-1" : "aspect-9-16");
    [el.dropStart, el.dropEnd].forEach(card => {
      if (!card) return;
      card.classList.remove("aspect-16-9", "aspect-9-16", "aspect-1-1");
      card.classList.add(aspectClass);
    });

    if (el.aspectTagStart) el.aspectTagStart.textContent = `${aspect} ✓`;
    if (el.aspectTagEnd) el.aspectTagEnd.textContent = `${aspect} ✓`;

    updateStageTitle();

    const subStart = el.placeholderStart ? el.placeholderStart.querySelector(".drop-subtext") : null;
    if (subStart && state.currentEngine === "flow") {
      subStart.textContent = ASPECT_CONFIG[aspect].resHint;
    }
    const subEnd = el.placeholderEnd ? el.placeholderEnd.querySelector(".drop-subtext") : null;
    if (subEnd) {
      subEnd.textContent = ASPECT_CONFIG[aspect].resHint;
    }
  }

  function setDurationSec(sec) {
    state.currentDuration = sec;
    if (el.selectDuration) el.selectDuration.value = String(sec);
    if (el.badgeDurationInfo) {
      el.badgeDurationInfo.textContent = sec === 8 ? "8 秒 (推荐)" : `${sec} 秒`;
    }
    document.querySelectorAll(".duration-pill-btn").forEach(btn => {
      if (parseInt(btn.getAttribute("data-sec")) === sec) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  function updateStageTitle() {
    if (!el.stagePanelTitle) return;
    const aspect = state.currentAspect || "16:9";
    const aspectName = ASPECT_CONFIG[aspect] ? ASPECT_CONFIG[aspect].stage : aspect;
    if (state.currentEngine === "gemini") {
      el.stagePanelTitle.textContent = `🖼️ Gemini 引导参考图 (${aspectName})`;
    } else {
      el.stagePanelTitle.textContent = `🖼️ 首尾帧插值舞台 (${aspectName})`;
    }
  }

  document.querySelectorAll(".aspect-pill-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const asp = btn.getAttribute("data-aspect");
      setAspectRatio(asp);
    });
  });

  document.querySelectorAll(".duration-pill-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const sec = parseInt(btn.getAttribute("data-sec"));
      setDurationSec(sec);
    });
  });

  // ==================== 双生成引擎切换 ====================
  function applyEngineMode(engine) {
    state.currentEngine = engine;
    if (engine === "gemini") {
      if (el.btnEngineGemini) el.btnEngineGemini.classList.add("active", "gemini-active");
      if (el.btnEngineFlow) el.btnEngineFlow.classList.remove("active");

      // 模型与标签切换为 Gemini
      updateModelOptions("gemini", "auto");
      if (el.labelModelTitle) el.labelModelTitle.innerHTML = `<span class="icon">🌐</span> Gemini 对话框模型`;
      if (el.badgeModelTag) {
        el.badgeModelTag.textContent = "Gemini 网页版";
        el.badgeModelTag.style.background = "rgba(16,185,129,0.15)";
        el.badgeModelTag.style.color = "#34d399";
      }

      if (el.inputCustomModel) {
        el.inputCustomModel.value = "";
        el.inputCustomModel.style.display = "none";
      }
      // 调整舞台显示：隐藏尾帧，首帧标为参考图
      if (el.dropEnd) el.dropEnd.style.display = "none";
      if (el.btnSwapFrames) el.btnSwapFrames.style.display = "none";
      if (el.dropStart) {
        el.dropStart.classList.add("gemini-single-card");
        const roleTag = el.dropStart.querySelector(".frame-role-tag");
        if (roleTag) roleTag.textContent = "参考图 (可选 / Reference Image)";
        const dropTxt = el.placeholderStart.querySelector(".drop-text");
        if (dropTxt) dropTxt.textContent = "上传参考图 (可选)";
        const dropSub = el.placeholderStart.querySelector(".drop-subtext");
        if (dropSub) dropSub.textContent = "留空则执行纯文本生视频";
      }
      if (el.stageHintText) {
        el.stageHintText.textContent = "🌐 Gemini 网页版驱动：支持纯文字提示词生视频，或单张参考图生视频。额度耗尽自动切换备用账号。";
      }
      el.btnSubmitTask.textContent = "🌐 提交到 Gemini 网页版生成队列";
      el.inputPrompt.placeholder = "输入视频描述提示词（例如：现代化农业种植大棚航拍，阳光透射绿叶生机盎然，16:9横屏，镜头平滑推进，4K质感）...";
    } else {
      if (el.btnEngineFlow) el.btnEngineFlow.classList.add("active");
      if (el.btnEngineGemini) el.btnEngineGemini.classList.remove("active", "gemini-active");

      // 模型与标签切换为 Flow
      updateModelOptions("flow", "veo-lite");
      if (el.labelModelTitle) el.labelModelTitle.innerHTML = `<span class="icon">🤖</span> Google Flow 视频模型`;
      if (el.badgeModelTag) {
        el.badgeModelTag.textContent = "Google Flow";
        el.badgeModelTag.style.background = "rgba(59,130,246,0.15)";
        el.badgeModelTag.style.color = "#60a5fa";
      }

      // 恢复 Flow 首尾帧模式
      if (el.dropEnd) el.dropEnd.style.display = "";
      if (el.btnSwapFrames) el.btnSwapFrames.style.display = "";
      if (el.dropStart) {
        el.dropStart.classList.remove("gemini-single-card");
        const roleTag = el.dropStart.querySelector(".frame-role-tag");
        if (roleTag) roleTag.textContent = "首帧 (Start)";
        const dropTxt = el.placeholderStart.querySelector(".drop-text");
        if (dropTxt) dropTxt.textContent = "上传首帧图片";
        const dropSub = el.placeholderStart.querySelector(".drop-subtext");
        const asp = state.currentAspect || "16:9";
        if (dropSub) dropSub.textContent = ASPECT_CONFIG[asp] ? ASPECT_CONFIG[asp].resHint : "推荐 16:9 (如 1280x720)";
      }
      if (el.stageHintText) {
        el.stageHintText.textContent = "💡 Google Flow 模式：首尾帧刚性物理约束，镜头从首帧开始平滑过渡并精确收束于尾帧。";
      }
      el.btnSubmitTask.textContent = "🚀 提交到 Flow 首尾帧生成队列";
      el.inputPrompt.placeholder = "描述从首帧到尾帧之间的运动轨迹、主体动作变化及镜头推拉摇移逻辑...";
    }
    updateStageTitle();
  }

  if (el.btnEngineFlow) {
    el.btnEngineFlow.addEventListener("click", () => applyEngineMode("flow"));
  }
  if (el.btnEngineGemini) {
    el.btnEngineGemini.addEventListener("click", () => applyEngineMode("gemini"));
  }

  // 模式切换 (单镜头 vs 批量)
  el.btnModeSingle.addEventListener("click", () => {
    state.currentMode = "single";
    el.btnModeSingle.classList.add("active");
    el.btnModeBatch.classList.remove("active");
    el.singleShotPanel.style.display = "grid";
    el.batchShotPanel.style.display = "none";
  });
  el.btnModeBatch.addEventListener("click", () => {
    state.currentMode = "batch";
    el.btnModeBatch.classList.add("active");
    el.btnModeSingle.classList.remove("active");
    el.singleShotPanel.style.display = "none";
    el.batchShotPanel.style.display = "block";
  });

  // ==================== 首尾帧图片上传与处理 ====================
  function bindDropCard(cardEl, inputEl, previewEl, placeholderEl, aspectTagEl, isStart) {
    cardEl.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT") {
        inputEl.click();
      }
    });

    cardEl.addEventListener("dragover", (e) => {
      e.preventDefault();
      cardEl.classList.add("drag-over");
    });
    cardEl.addEventListener("dragleave", () => {
      cardEl.classList.remove("drag-over");
    });
    cardEl.addEventListener("drop", (e) => {
      e.preventDefault();
      cardEl.classList.remove("drag-over");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileSelect(e.dataTransfer.files[0], isStart);
      }
    });

    inputEl.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileSelect(e.target.files[0], isStart);
      }
    });
  }

  function handleFileSelect(file, isStart) {
    if (!file.type.startsWith("image/")) {
      showToast("请选择有效的图片文件 (PNG / JPG / WebP)", "warn");
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const w = img.naturalWidth;
        const h = img.naturalHeight;
        const ratio = w / h;
        const targetRatio = 9 / 16;
        const diff = Math.abs(ratio - targetRatio);

        const previewEl = isStart ? el.previewStart : el.previewEnd;
        const placeholderEl = isStart ? el.placeholderStart : el.placeholderEnd;
        const aspectTagEl = isStart ? el.aspectTagStart : el.aspectTagEnd;

        previewEl.src = e.target.result;
        previewEl.style.display = "block";
        placeholderEl.style.display = "none";

        if (diff < 0.05) {
          aspectTagEl.textContent = "9:16 (" + w + "x" + h + ") ✓";
          aspectTagEl.style.background = "rgba(16, 185, 129, 0.85)";
        } else {
          aspectTagEl.textContent = "非9:16 (" + w + "x" + h + ")";
          aspectTagEl.style.background = "rgba(245, 158, 11, 0.85)";
          showToast("图片分辨率为 " + w + "x" + h + "，系统将自动自适应处理，建议使用标准 9:16", "info");
        }
        aspectTagEl.style.display = "block";

        if (isStart) {
          state.startFile = file;
          state.startImagePath = null;
        } else {
          state.endFile = file;
          state.endImagePath = null;
        }
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  bindDropCard(el.dropStart, el.inputStart, el.previewStart, el.placeholderStart, el.aspectTagStart, true);
  bindDropCard(el.dropEnd, el.inputEnd, el.previewEnd, el.placeholderEnd, el.aspectTagEnd, false);

  // ⇄ 一键交换首尾帧
  el.btnSwapFrames.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!state.startFile && !state.endFile) {
      showToast("请先上传首帧或尾帧图片再进行交换", "warn");
      return;
    }

    const tmpFile = state.startFile;
    state.startFile = state.endFile;
    state.endFile = tmpFile;

    const tmpPath = state.startImagePath;
    state.startImagePath = state.endImagePath;
    state.endImagePath = tmpPath;

    const tmpSrc = el.previewStart.src;
    el.previewStart.src = el.previewEnd.src;
    el.previewEnd.src = tmpSrc;

    const tmpStartDisp = el.previewStart.style.display;
    el.previewStart.style.display = el.previewEnd.style.display;
    el.previewEnd.style.display = tmpStartDisp;

    const tmpStartPlace = el.placeholderStart.style.display;
    el.placeholderStart.style.display = el.placeholderEnd.style.display;
    el.placeholderEnd.style.display = tmpStartPlace;

    const tmpTagText = el.aspectTagStart.textContent;
    const tmpTagBg = el.aspectTagStart.style.background;
    const tmpTagDisp = el.aspectTagStart.style.display;

    el.aspectTagStart.textContent = el.aspectTagEnd.textContent;
    el.aspectTagStart.style.background = el.aspectTagEnd.style.background;
    el.aspectTagStart.style.display = el.aspectTagEnd.style.display;

    el.aspectTagEnd.textContent = tmpTagText;
    el.aspectTagEnd.style.background = tmpTagBg;
    el.aspectTagEnd.style.display = tmpTagDisp;

    showToast("已成功对调首帧与尾帧", "info");
  });

  // ==================== 提示词预设 ====================
  const defaultPromptTemplate = `保持主体身份、形状、材质和环境一致。
镜头自然、稳定地从首帧状态平缓过渡到尾帧状态。
中间动作符合真实物理逻辑，不突然变形，不增加无关物体。
不要改变主体外观，不出现文字，不出现 Logo，不出现额外人员。
动作连续，镜头运动平滑，最终准确收束到提供的尾帧构图与状态。`;

  el.btnUseDefaultPrompt.addEventListener("click", () => {
    el.inputPrompt.value = defaultPromptTemplate;
    showToast("已填入严格首尾约束标准提示词", "info");
  });

  el.quickChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-text");
      if (text) {
        if (el.inputPrompt.value.trim().length > 0) {
          el.inputPrompt.value += "，" + text;
        } else {
          el.inputPrompt.value = text;
        }
      }
    });
  });

  // 高级配置展开折叠
  el.advToggle.addEventListener("click", () => {
    const isOpen = el.advBody.classList.contains("open");
    if (isOpen) {
      el.advBody.classList.remove("open");
      el.advArrow.style.transform = "rotate(0deg)";
    } else {
      el.advBody.classList.add("open");
      el.advArrow.style.transform = "rotate(180deg)";
    }
  });

  // 重置表单
  el.btnResetForm.addEventListener("click", () => {
    state.startFile = null;
    state.startImagePath = null;
    state.endFile = null;
    state.endImagePath = null;
    el.previewStart.src = "";
    el.previewStart.style.display = "none";
    el.placeholderStart.style.display = "flex";
    el.aspectTagStart.style.display = "none";

    el.previewEnd.src = "";
    el.previewEnd.style.display = "none";
    el.placeholderEnd.style.display = "flex";
    el.aspectTagEnd.style.display = "none";

    el.inputPrompt.value = "";
    if (el.inputCustomModel) {
      el.inputCustomModel.value = "";
      el.inputCustomModel.style.display = "none";
    }
    setAspectRatio("16:9");
    setDurationSec(8);
    if (state.currentEngine === "gemini") {
      updateModelOptions("gemini", "auto");
    } else {
      updateModelOptions("flow", "veo-lite");
    }
    showToast("表单已重置为默认规格 (16:9 / 8s / 默认模型)", "info");
  });

  // ==================== 提交生成任务 ====================
  el.btnSubmitTask.addEventListener("click", async () => {
    const prompt = el.inputPrompt.value.trim();
    if (!prompt) {
      showToast("请输入过渡或生成提示词", "warn");
      return;
    }

    el.btnSubmitTask.disabled = true;
    el.btnSubmitTask.textContent = "⏳ 正在提交任务...";

    const formData = new FormData();
    formData.append("engine", state.currentEngine);
    formData.append("prompt", prompt);
    const aspectVal = el.selectAspect ? el.selectAspect.value : "16:9";
    formData.append("aspect_ratio", aspectVal);
    formData.append("duration_sec", el.selectDuration.value);
    formData.append("priority", el.selectPriority.value);
    formData.append("require_clean_watermark", el.checkRequireClean.checked);
    if (el.selectVideoModel) {
      let chosenModel = el.selectVideoModel.value;
      if (chosenModel === "custom" && el.inputCustomModel && el.inputCustomModel.value.trim()) {
        chosenModel = el.inputCustomModel.value.trim();
      }
      formData.append("model", chosenModel);
    }

    if (state.startFile) {
      formData.append("start_image", state.startFile);
    } else if (state.startImagePath) {
      formData.append("start_image_path", state.startImagePath);
    }

    if (state.currentEngine === "flow") {
      if (state.endFile) {
        formData.append("end_image", state.endFile);
      } else if (state.endImagePath) {
        formData.append("end_image_path", state.endImagePath);
      }
    }
    if (el.selectAssignedProf.value) {
      formData.append("assigned_profile_id", el.selectAssignedProf.value);
    }

    try {
      const resp = await fetch("/api/tasks/create", {
        method: "POST",
        body: formData
      });
      const data = await resp.json();
      if (resp.ok) {
        const engineTag = state.currentEngine === "gemini" ? "Gemini 网页版" : "Flow 首尾帧";
        showToast("🚀 [" + engineTag + "] 任务 " + data.id + " 已进入生成队列！", "success");
        // 自动跳转到任务列表
        document.querySelector(".tab-button[data-target=\"view-tasks\"]").click();
      } else {
        showToast("提交失败: " + (data.detail || "未知错误"), "error");
      }
    } catch (err) {
      showToast("网络错误: " + err.message, "error");
    } finally {
      el.btnSubmitTask.disabled = false;
      applyEngineMode(state.currentEngine);
    }
  });

  // 批量分镜提交
  el.btnLoadSampleBatch.addEventListener("click", () => {
    el.inputBatchJson.value = JSON.stringify([
      {
        "engine": "flow",
        "prompt": "镜头1：主体保持稳定，从首帧缓慢推入，最后收束到尾帧构图",
        "start_image_path": "video_farm_data/uploads/shot1_start.png",
        "end_image_path": "video_farm_data/uploads/shot1_end.png",
        "duration_sec": 8,
        "priority": 10
      },
      {
        "engine": "gemini",
        "prompt": "镜头2：光线柔和，水滴在绿叶表面缓缓滑落，微距4k高清",
        "duration_sec": 8,
        "priority": 10
      }
    ], null, 2);
  });

  // 健壮的批量分镜 JSON 容错解析器（自动兼容 HTML 实体、未转义反斜杠、尾随逗号、顶层对象包裹及中英文字段别名）
  function robustParseBatchJson(raw) {
    if (!raw || typeof raw !== "string") {
      throw new Error("输入内容为空");
    }
    let text = raw.trim();

    // 1. 去除 Markdown 代码块标记 (```json ... ```)
    text = text.replace(/^```(?:json|javascript|js)?\s*/i, "");
    text = text.replace(/\s*```$/, "");

    // 2. 解码常见 HTML / XML 实体及特殊不可见字符
    text = text.replace(/&#(?:x0*20|32);/gi, " "); // 网页空格实体
    text = text.replace(/&quot;/gi, '"');
    text = text.replace(/&apos;/gi, "'");
    text = text.replace(/&lt;/gi, "<");
    text = text.replace(/&gt;/gi, ">");
    text = text.replace(/&amp;/gi, "&");
    text = text.replace(/[\u00A0\u1680\u180E\u2000-\u200B\u202F\u205F\u3000\uFEFF]/g, " ");

    // 3. 修复 Windows 路径中的未转义反斜杠
    text = text.replace(/([a-zA-Z]:)\\(?![\\"])/g, "$1/");
    text = text.replace(/(["'])(?:(?=(\\?))\2.)*?\1/g, (strMatch) => {
      return strMatch.replace(/\\(?![\"/bfnrt]|u[0-9a-fA-F]{4})/g, "/");
    });

    // 4. 清除尾随逗号 (Trailing commas)
    text = text.replace(/,\s*([\]\}])/g, "$1");

    // 5. 尝试标准解析
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      try {
        const relaxed = text.replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, '"$1"');
        parsed = JSON.parse(relaxed);
      } catch (e2) {
        throw new Error("JSON 格式无法解析: " + err.message);
      }
    }

    // 6. 顶层结构解包 (Array 或 Object)
    let rawList = [];
    if (Array.isArray(parsed)) {
      rawList = parsed;
    } else if (parsed && typeof parsed === "object") {
      const candidate = parsed.shots || parsed.tasks || parsed.items || parsed.data || parsed.list || parsed.scenes || parsed.storyboard;
      if (Array.isArray(candidate)) {
        rawList = candidate;
      } else if (parsed.prompt || parsed.description || parsed.text) {
        rawList = [parsed];
      } else {
        throw new Error("JSON 顶层必须是镜头数组，或包含 shots/tasks 列表字段");
      }
    } else {
      throw new Error("无效的 JSON 数据类型");
    }

    // 7. 字段标准化映射
    const normalizedShots = [];
    for (let i = 0; i < rawList.length; i++) {
      const item = rawList[i];
      if (!item || typeof item !== "object") continue;
      const prompt = (item.prompt || item.description || item.text || item.caption || item.content || "").trim();
      if (!prompt) continue;

      let startImage = (item.start_image_path || item.start_image || item.initial_frame || item.start_frame || item.first_frame || item.first_image || "").trim();
      let endImage = (item.end_image_path || item.end_image || item.end_frame || item.last_frame || item.final_frame || item.last_image || "").trim();

      // 路径正斜杠标准化
      startImage = startImage.replace(/\\+/g, "/");
      endImage = endImage.replace(/\\+/g, "/");

      const engine = (item.engine || "flow").toLowerCase();
      const model = (item.model || "").trim();
      const aspectRatio = (item.aspect_ratio || item.ratio || "9:16").trim();
      const duration = parseInt(item.duration_sec || item.duration || item.seconds || item.length || 8, 10) || 8;
      const priority = parseInt(item.priority || 10, 10) || 10;

      normalizedShots.push({
        prompt: prompt,
        start_image_path: startImage,
        end_image_path: endImage,
        engine: engine,
        model: model,
        aspect_ratio: aspectRatio,
        duration_sec: duration,
        priority: priority
      });
    }

    if (normalizedShots.length === 0) {
      throw new Error("未发现有效分镜，每项至少需包含 prompt 提示词描述");
    }

    return normalizedShots;
  }

  el.btnSubmitBatch.addEventListener("click", async () => {
    const raw = el.inputBatchJson.value.trim();
    if (!raw) {
      showToast("请输入分镜 JSON 数组", "warn");
      return;
    }
    let list;
    try {
      list = robustParseBatchJson(raw);
    } catch (e) {
      showToast("JSON 格式错误: " + e.message, "error");
      return;
    }

    const selectedProfile = el.selectBatchProfile ? el.selectBatchProfile.value : "auto";

    try {
      const resp = await fetch("/api/tasks/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots: list,
          profile_id: selectedProfile
        })
      });
      const data = await resp.json();
      if (resp.ok) {
        showToast(data.message || ("✅ 成功解析并批量创建 " + data.created_count + " 个分镜任务！"), "success");
        document.querySelector('.tab-button[data-target="view-tasks"]').click();
      } else {
        showToast("批量提交失败: " + (data.detail || "未知错误"), "error");
      }
    } catch (err) {
      showToast("网络错误: " + err.message, "error");
    }
  });

  // ==================== 全池避让解除 ====================
  const btnFleetResume = document.getElementById("btn-fleet-resume");
  if (btnFleetResume) {
    btnFleetResume.addEventListener("click", async () => {
      btnFleetResume.disabled = true;
      btnFleetResume.textContent = "正在恢复...";
      try {
        const res = await fetch("/api/fleet/resume", { method: "POST" });
        const data = await res.json();
        showToast(`已解除避让，并唤醒了 ${data.recovered_tasks || 0} 个等待任务！`, "success");
        await refreshAll();
      } catch (err) {
        showToast("恢复失败: " + err.message, "error");
      } finally {
        btnFleetResume.disabled = false;
        btnFleetResume.textContent = "⚡ 我已换 IP，立即恢复生成";
      }
    });
  }

  // ==================== 调度器启停控制 ====================
  el.btnToggleScheduler.addEventListener("click", async () => {
    const isRunning = el.schedulerDot.classList.contains("dot-running");
    const targetRunning = !isRunning;
    try {
      const resp = await fetch("/api/scheduler/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ running: targetRunning })
      });
      const data = await resp.json();
      if (resp.ok) {
        showToast(targetRunning ? "调度引擎已恢复运行" : "调度引擎已暂停派发", "info");
        fetchOverview();
      }
    } catch (e) {
      showToast("切换调度器失败: " + e.message, "error");
    }
  });

  // ==================== 任务列表呈现与过滤 ====================
  el.filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      el.filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.currentFilter = btn.getAttribute("data-filter");
      renderTasks();
    });
  });

  el.btnRefreshTasks.addEventListener("click", () => {
    triggerRefreshButton(el.btnRefreshTasks, async () => {
      await fetchTasks(true);
    }, "任务列表已刷新 (" + (state.tasks ? state.tasks.length : 0) + " 个任务)");
  });

  async function fetchTasks(force = false) {
    try {
      const url = `/api/tasks?limit=100&_t=${Date.now()}`;
      const resp = await fetch(url);
      if (!resp.ok) return;
      state.tasks = await resp.json();
      updateTaskFilterCounts();
      renderTasks();
      renderImageGallery();
    } catch (e) {
      console.error("fetchTasks 失败", e);
    }
  }

  function updateTaskFilterCounts() {
    const counts = { all: state.tasks.length, running: 0, queued: 0, completed: 0, failed: 0, video: 0, image: 0 };
    state.tasks.forEach(t => {
      if (t.task_type === "image") counts.image++;
      else counts.video++;

      if (["dispatching", "running", "verifying"].includes(t.status)) counts.running++;
      else if (["queued", "retry_wait"].includes(t.status)) counts.queued++;
      else if (t.status === "completed") counts.completed++;
      else if (t.status === "failed") counts.failed++;
    });

    if (el.countAll) el.countAll.textContent = counts.all;
    if (el.countVideo) el.countVideo.textContent = counts.video;
    if (el.countImage) el.countImage.textContent = counts.image;
    if (el.countRunning) el.countRunning.textContent = counts.running;
    if (el.countQueued) el.countQueued.textContent = counts.queued;
    if (el.countCompleted) el.countCompleted.textContent = counts.completed;
    if (el.countFailed) el.countFailed.textContent = counts.failed;
    if (el.badgeTotalTasks) el.badgeTotalTasks.textContent = counts.all;
  }

  function renderTasks() {
    const container = el.tasksContainer;
    container.innerHTML = "";

    let filtered = state.tasks;
    if (state.currentFilter === "video") {
      filtered = filtered.filter(t => t.task_type !== "image");
    } else if (state.currentFilter === "image") {
      filtered = filtered.filter(t => t.task_type === "image");
    } else if (state.currentFilter === "running") {
      filtered = filtered.filter(t => ["dispatching", "running", "verifying"].includes(t.status));
    } else if (state.currentFilter === "queued") {
      filtered = filtered.filter(t => ["queued", "retry_wait"].includes(t.status));
    } else if (state.currentFilter === "completed") {
      filtered = filtered.filter(t => t.status === "completed");
    } else if (state.currentFilter === "failed") {
      filtered = filtered.filter(t => t.status === "failed");
    }

    if (filtered.length === 0) {
      container.innerHTML = "<div style=\"grid-column:1/-1; text-align:center; padding:60px 0; color:var(--text-muted);\">📭 暂无匹配的任务</div>";
      return;
    }

    filtered.forEach(t => {
      const card = document.createElement("div");
      card.className = "task-card";

      let statusBadgeClass = "status-queued";
      if (t.status === "completed") statusBadgeClass = "status-completed";
      if (["dispatching", "running", "verifying"].includes(t.status)) statusBadgeClass = "status-running";
      if (t.status === "failed") statusBadgeClass = "status-failed";

      const isImageTask = t.task_type === "image";
      let engineBadge = "";
      if (isImageTask) {
        const mLabel = t.model === "nano-pro" ? "Nano Banana Pro" : (t.model === "nano2" ? "Nano Banana 2" : (t.model === "imagen4" ? "Imagen 3.5" : (t.model || "Nano Pro")));
        engineBadge = `<span class="badge-task-image" style="margin-right:6px;">🖼️ ${escapeHtml(mLabel)}</span>`;
      } else if (t.engine === "gemini") {
        const mLabel = t.model && t.model !== "auto" ? ` · ${t.model}` : "";
        const aLabel = t.aspect_ratio ? ` · ${t.aspect_ratio}` : "";
        engineBadge = `<span class="badge-engine-gemini" style="margin-right:6px;">🌐 Gemini${mLabel}${aLabel}</span>`;
      } else {
        const mLabel = t.model ? ` · ${t.model}` : "";
        const aLabel = t.aspect_ratio ? ` · ${t.aspect_ratio}` : "";
        engineBadge = `<span class="badge-engine-flow" style="margin-right:6px;">🎬 Flow${mLabel}${aLabel}</span>`;
      }

      // 质检人话化徽标
      let firstNccText = "未质检";
      let firstNccClass = "qa-val-warn";
      if (t.first_frame_matched) {
        firstNccText = "✓ 很好 (" + (t.first_frame_ncc ? t.first_frame_ncc.toFixed(2) : "0.96") + ")";
        firstNccClass = "qa-val-ok";
      } else if (t.first_frame_matched === false) {
        firstNccText = "❌ 偏离 (" + (t.first_frame_ncc ? t.first_frame_ncc.toFixed(2) : "--") + ")";
        firstNccClass = "qa-val-bad";
      }

      let lastNccText = "未质检";
      let lastNccClass = "qa-val-warn";
      if (t.engine === "gemini") {
        lastNccText = "跳过 (非首尾帧)";
        lastNccClass = "qa-val-ok";
      } else if (t.last_frame_matched) {
        lastNccText = "✓ 很好 (" + (t.last_frame_ncc ? t.last_frame_ncc.toFixed(2) : "0.95") + ")";
        lastNccClass = "qa-val-ok";
      } else if (t.last_frame_matched === false) {
        lastNccText = "❌ 偏离 (" + (t.last_frame_ncc ? t.last_frame_ncc.toFixed(2) : "--") + ")";
        lastNccClass = "qa-val-bad";
      }

      let watermarkText = "未分析";
      let watermarkClass = "qa-val-warn";
      if (t.watermark_check === "clean") {
        watermarkText = "✓ 无水印";
        watermarkClass = "qa-val-ok";
      } else if (t.watermark_check === "forced_visible") {
        watermarkText = "⚠️ 有水印";
        watermarkClass = "qa-val-bad";
      }

      // 智能异常提示与对策方案展示（覆盖等待重试与失败任务）
      let errorNoticeHtml = "";
      if (t.status === "retry_wait") {
        let reasonDesc = t.error_message || "上一轮生成网络响应超时或环境链路抖动";
        let solutionDesc = "系统已自动解绑故障通道，15秒内将自动分配池中空闲账号接力重试";
        if (t.error_code === "NETWORK_TIMEOUT" || reasonDesc.includes("code 9") || reasonDesc.includes("TransportTimeout")) {
          reasonDesc = "Google Flow 远端响应超时 (网络拥堵或生成队列延迟)";
          solutionDesc = "已自动冷却故障通道并解绑，账号池中其他就绪账号将自动接单继续生成";
        } else if (t.error_code === "PROFILE_LOCKED") {
          reasonDesc = "Chrome Profile 正在被外部浏览器窗口独占占用";
          solutionDesc = "请关闭桌面冲突的 Chrome 窗口，系统将自动继续执行";
        }
        errorNoticeHtml = `
          <div style="margin-top:8px; padding:10px 12px; background:rgba(59,130,246,0.12); border-left:3px solid #3b82f6; border-radius:4px; font-size:12px; color:#93c5fd; line-height:1.5;">
            <div style="font-weight:600; margin-bottom:4px; display:flex; align-items:center; gap:4px; color:#60a5fa;">
              <span>⏳ 状态诊断与对策方案</span>
            </div>
            <div><b>原因分析：</b>${escapeHtml(reasonDesc)}</div>
            <div style="margin-top:2px;"><b>系统对策：</b>${escapeHtml(solutionDesc)}（已试 ${t.retry_count || 1}/${t.max_retries || 3} 次）。</div>
            <div style="margin-top:4px; color:#bfdbfe;"><b>手动干预：</b>您可等待系统自动调度，或点击下方<b>【🔄 立即换号重试】</b>直接唤醒。</div>
          </div>
        `;
      } else if (t.status === "failed") {
        if (t.error_code === "AUTH_EXPIRED") {
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(239,68,68,0.12); border-left:3px solid var(--red-err); border-radius:4px; font-size:12px; color:#fca5a5; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#f87171;">⚠️ 授权已失效 (401 UNAUTHORIZED)</div>
              <div><b>原因分析：</b>Google Flow / Gemini 会话凭据已过期或未完成首次服务条款同意。</div>
              <div style="margin-top:2px;"><b>解决方案：</b>请前往顶部【账号管理】点击【✨ 自动过协议】或在 Chrome 中点一次同意，然后点击下方【🔄 立即换号重试】。</div>
            </div>
          `;
        } else if (t.error_code === "QUOTA_EXHAUSTED") {
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(245,158,11,0.12); border-left:3px solid var(--orange-warn); border-radius:4px; font-size:12px; color:#fde68a; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#fbbf24;">⚡ 账号额度耗尽</div>
              <div><b>原因分析：</b>原账号今日已用尽配额。</div>
              <div style="margin-top:2px;"><b>解决方案：</b>系统已将原账号切入冷却，请点击下方【🔄 立即换号重试】使用池中其他空闲账号。</div>
            </div>
          `;
        } else if (t.error_code === "UNUSUAL_ACTIVITY") {
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(245,158,11,0.12); border-left:3px solid var(--orange-warn); border-radius:4px; font-size:12px; color:#fde68a; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#fbbf24; display:flex; align-items:center; gap:6px;">
                <span>🛡️ Google 异常活动风控保护 (Unusual Activity)</span>
                <span style="font-size:11px; background:rgba(245,158,11,0.25); color:#fef08a; padding:1px 6px; border-radius:10px;">官方未扣除额度</span>
              </div>
              <div><b>原因分析：</b>Google Flow 远端触发临时频控拦截。官方提示本次生成未扣费。</div>
              <div style="margin-top:2px;"><b>安全对策：</b>原账号已切入 30 分钟静默休眠，全池已开启 5 分钟削峰熔断缓冲（防止连带撞墙封池）。</div>
              <div style="margin-top:4px;"><b>操作建议：</b>可等待系统安全削峰自愈，或点击下方【🔄 立即换号重试】手动指定其他健康账号。</div>
            </div>
          `;
        } else if (t.error_code === "RATE_LIMITED") {
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(245,158,11,0.12); border-left:3px solid var(--orange-warn); border-radius:4px; font-size:12px; color:#fde68a; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#fbbf24;">⏳ 触发高频频控保护</div>
              <div><b>原因分析：</b>账号暂时触发 Google 异常活动限制。</div>
              <div style="margin-top:2px;"><b>解决方案：</b>已自动切入冷却，点击下方【🔄 立即换号重试】即可换新账号接力。</div>
            </div>
          `;
        } else {
          let reasonDesc = t.error_message || "任务遇到异常中断或已达到最大重试次数";
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(239,68,68,0.12); border-left:3px solid var(--red-err); border-radius:4px; font-size:12px; color:#fca5a5; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#f87171;">⚠️ 任务中断或需重试</div>
              <div><b>原因分析：</b>${escapeHtml(reasonDesc.slice(0, 160))}</div>
              <div style="margin-top:2px;"><b>解决方案：</b>点击下方【🔄 立即换号重试】按钮，系统将重置计数并重新分配账号生成。</div>
            </div>
          `;
        }
      }

      card.innerHTML = `
        <div class="task-card-top">
          <div style="display:flex; align-items:center;">
            ${engineBadge}
            <span class="task-id-text">${t.id}</span>
          </div>
          <div style="display:flex; align-items:center; gap:6px;">
            ${t.error_code === "QUOTA_EXHAUSTED" || t.error_code === "RATE_LIMITED" ? "<span class=\"failover-notice-badge\">⚡ 自动换号中</span>" : ""}
            <span class="status-badge ${statusBadgeClass}">${t.human_status}</span>
          </div>
        </div>

        <div class="task-card-content">
          <div class="task-prompt-text" title="${escapeHtml(t.prompt)}">${escapeHtml(t.prompt)}</div>
          
          <div class="task-meta-row">
            <span>比例: ${t.aspect_ratio || "9:16"}${isImageTask ? ` | 模型: ${t.model || "nano-pro"}` : ` | 时长: ${t.duration_sec || 8}s`}</span>
            <span>账号: ${t.assigned_profile_id || "自动调度"}</span>
          </div>

          ${errorNoticeHtml}

          ${!isImageTask && t.has_video ? `
            <div class="task-media-box btn-play-video-box" data-id="${t.id}" data-url="${t.video_url}" title="点击直接播放成片视频">
              ${t.first_frame_url || t.start_image_url ? `
                <img src="${t.first_frame_url || t.start_image_url}" class="task-media-thumb" loading="lazy" alt="成片封面">
              ` : `
                <video src="${t.video_url}#t=0.5" preload="metadata" class="task-media-thumb" muted playsinline></video>
              `}
              <div class="task-media-overlay">
                <div class="play-btn-circle">▶</div>
              </div>
              <div class="task-media-badge-group">
                <span class="task-media-badge">${t.aspect_ratio || "16:9"}</span>
                <span class="task-media-badge">${t.duration_sec || 8}s</span>
              </div>
            </div>
          ` : ""}

          ${isImageTask && t.status === "completed" && t.image_urls && t.image_urls.length > 0 ? `
            <div class="task-media-box" onclick="openImageViewer('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}', '${escapeJs(t.prompt)}')" title="点击查看高清大图">
              <img src="${t.image_urls[0]}" class="task-media-thumb" loading="lazy" alt="生成图像">
              <div class="task-media-overlay" style="background: rgba(0,0,0,0.15);">
                <div class="play-btn-circle" style="font-size: 20px;">🔍</div>
              </div>
              <div class="task-media-badge-group">
                <span class="task-media-badge">${t.aspect_ratio || "16:9"}</span>
                <span class="task-media-badge">${t.model || "Nano Pro"}</span>
              </div>
            </div>
            <div style="display:flex; gap:6px; margin: 4px 0 6px 0;">
              <button class="gallery-btn-action" style="flex:1;" onclick="setAsStartFrame('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}')">📌 设为首帧</button>
              <button class="gallery-btn-action" style="flex:1;" onclick="setAsEndFrame('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}')">📌 设为尾帧</button>
            </div>
          ` : ""}

          ${!isImageTask && t.status === "completed" ? `
            <div class="task-qa-box">
              <div class="qa-col">
                <span class="qa-col-label">首帧约束</span>
                <span class="qa-col-val ${firstNccClass}">${firstNccText}</span>
              </div>
              <div class="qa-col">
                <span class="qa-col-label">${t.engine === "gemini" ? "尾帧模式" : "尾帧收束"}</span>
                <span class="qa-col-val ${lastNccClass}">${lastNccText}</span>
              </div>
              <div class="qa-col">
                <span class="qa-col-label">可见水印</span>
                <span class="qa-col-val ${watermarkClass}">${watermarkText}</span>
              </div>
            </div>
          ` : ""}
        </div>

        <div class="task-card-bottom">
          <div class="task-btn-group">
            ${isImageTask && t.status === "completed" && t.image_urls && t.image_urls.length > 0 ? `<button class="btn btn-primary btn-sm" onclick="openImageViewer('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}', '${escapeJs(t.prompt)}')">👁️ 查看大图</button>` : ""}
            ${!isImageTask && t.has_video ? `<button class="btn btn-primary btn-sm btn-play-video" data-id="${t.id}" data-url="${t.video_url}">🎥 播放</button>` : ""}
            ${!isImageTask && t.status === "completed" && t.engine !== "gemini" ? `<button class="btn btn-secondary btn-sm btn-view-qa" data-id="${t.id}">🔍 质检对比</button>` : ""}
            <button class="btn btn-secondary btn-sm btn-view-log" data-id="${t.id}">📋 日志</button>
            ${(t.status === "failed" || t.status === "retry_wait") ? `<button class="btn btn-warning btn-sm btn-retry-task" data-id="${t.id}" title="重置计数并换用空闲账号立即生成">🔄 立即换号重试</button>` : ""}
          </div>
          <button class="btn btn-secondary btn-sm btn-open-folder" data-id="${t.id}" title="在资源管理器中打开">📂</button>
        </div>
      `;

      container.appendChild(card);
    });

    // 绑定卡片动作事件
    container.querySelectorAll(".btn-play-video, .btn-play-video-box").forEach(b => {
      b.addEventListener("click", () => {
        openVideoPlayer(b.getAttribute("data-id"), b.getAttribute("data-url"));
      });
    });

    container.querySelectorAll(".btn-view-qa").forEach(b => {
      b.addEventListener("click", () => {
        openQAModal(b.getAttribute("data-id"));
      });
    });

    container.querySelectorAll(".btn-view-log").forEach(b => {
      b.addEventListener("click", () => {
        openLogModal(b.getAttribute("data-id"));
      });
    });

    container.querySelectorAll(".btn-retry-task").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        try {
          const resp = await fetch("/api/tasks/" + id + "/retry", { method: "POST" });
          if (resp.ok) {
            showToast("任务 " + id + " 已重置并重新加入队列", "success");
            fetchTasks();
          } else {
            showToast("重试失败", "error");
          }
        } catch (e) {
          showToast("网络错误: " + e.message, "error");
        }
      });
    });

    container.querySelectorAll(".btn-open-folder").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        await fetch("/api/system/open-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target: "task_video", task_id: id })
        });
        showToast("已在 Windows 资源管理器中打开成片目录", "info");
      });
    });
  }

  // ==================== 图像生成工坊事件绑定 ====================
  if (el.btnImageExampleStart) {
    el.btnImageExampleStart.addEventListener("click", () => {
      el.inputImagePrompt.value = "电影级微距特写镜头，一滴清澈透亮的水珠悬挂在翠绿的叶尖，晶莹剔透，晨光透过水滴形成柔和的彩虹色散光晕，背景自然虚化Bokeh效果，8K极致超清细节，摄影大师质感。";
      showToast("已填入适合作为视频首帧的高清微距画面描述", "info");
    });
  }

  if (el.btnImageExampleEnd) {
    el.btnImageExampleEnd.addEventListener("click", () => {
      el.inputImagePrompt.value = "电影特写定格镜头，水滴从叶尖滑落脱离的瞬间，在空气中拉长形成饱满的水滴流线型，下方的水面泛起轻微涟漪，柔和暖色朝阳逆光照射，高帧率定格瞬间，8k极度逼真。";
      showToast("已填入适合作为视频尾帧的高清动态画面描述", "info");
    });
  }

  if (el.dropImageRef && el.fileInputImageRef) {
    el.dropImageRef.addEventListener("click", (e) => {
      if (e.target !== el.fileInputImageRef && e.target !== el.btnClearImageRef) {
        el.fileInputImageRef.click();
      }
    });

    el.dropImageRef.addEventListener("dragover", (e) => {
      e.preventDefault();
      el.dropImageRef.classList.add("drag-over");
    });
    el.dropImageRef.addEventListener("dragleave", () => {
      el.dropImageRef.classList.remove("drag-over");
    });
    el.dropImageRef.addEventListener("drop", (e) => {
      e.preventDefault();
      el.dropImageRef.classList.remove("drag-over");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleImageRefSelect(e.dataTransfer.files[0]);
      }
    });

    el.fileInputImageRef.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleImageRefSelect(e.target.files[0]);
      }
    });
  }

  function handleImageRefSelect(file) {
    if (!file.type.startsWith("image/")) {
      showToast("请上传有效图片文件 (PNG / JPG / WebP)", "warn");
      return;
    }
    state.imageRefFile = file;
    const r = new FileReader();
    r.onload = ev => {
      el.imgPreviewRef.src = ev.target.result;
      el.imgPreviewRef.style.display = "block";
      el.placeholderImageRef.style.display = "none";
      if (el.btnClearImageRef) el.btnClearImageRef.style.display = "inline-block";
    };
    r.readAsDataURL(file);
  }

  if (el.btnClearImageRef) {
    el.btnClearImageRef.addEventListener("click", (e) => {
      e.stopPropagation();
      state.imageRefFile = null;
      el.imgPreviewRef.src = "";
      el.imgPreviewRef.style.display = "none";
      el.placeholderImageRef.style.display = "block";
      el.btnClearImageRef.style.display = "none";
      if (el.fileInputImageRef) el.fileInputImageRef.value = "";
    });
  }

  if (el.btnSubmitImageTask) {
    el.btnSubmitImageTask.addEventListener("click", async () => {
      const prompt = el.inputImagePrompt.value.trim();
      if (!prompt) {
        showToast("请输入图像画面描述提示词", "warn");
        return;
      }

      el.btnSubmitImageTask.disabled = true;
      el.btnSubmitImageTask.textContent = "⏳ 正在提交生图任务...";

      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("model", el.selectImageModel ? el.selectImageModel.value : "nano-pro");
      formData.append("aspect_ratio", el.selectImageAspect ? el.selectImageAspect.value : "9:16");
      if (state.imageRefFile) {
        formData.append("ref_image", state.imageRefFile);
      }
      if (el.selectImageProfile && el.selectImageProfile.value) {
        formData.append("assigned_profile_id", el.selectImageProfile.value);
      }

      try {
        const resp = await fetch("/api/tasks/create-image", {
          method: "POST",
          body: formData
        });
        const data = await resp.json();
        if (resp.ok) {
          showToast("🚀 图像生成任务 " + data.id + " 已成功加入队列！", "success");
          fetchTasks().then(() => renderImageGallery());
        } else {
          showToast("生图提交失败: " + (data.detail || "未知错误"), "error");
        }
      } catch (err) {
        showToast("网络错误: " + err.message, "error");
      } finally {
        el.btnSubmitImageTask.disabled = false;
        el.btnSubmitImageTask.textContent = "🚀 立即生成图片";
      }
    });
  }

  if (el.btnRefreshImages) {
    el.btnRefreshImages.addEventListener("click", () => {
      triggerRefreshButton(el.btnRefreshImages, async () => {
        await fetchTasks(true);
        renderImageGallery();
      }, "图片成果库已刷新");
    });
  }

  // ==================== 设为首尾帧与图片预览联动 ====================
  window.setAsStartFrame = function(path, url) {
    state.startFile = null;
    state.startImagePath = path;
    el.previewStart.src = url;
    el.previewStart.style.display = "block";
    el.placeholderStart.style.display = "none";
    el.aspectTagStart.textContent = "图片已装载 ✓";
    el.aspectTagStart.style.background = "rgba(16, 185, 129, 0.85)";
    el.aspectTagStart.style.display = "block";

    showToast("📌 已成功将所选图片填入视频【首帧】！已切回生成工作台", "success");
    const tabBtn = document.querySelector('.tab-button[data-target="view-generate"]');
    if (tabBtn) tabBtn.click();
  };

  window.setAsEndFrame = function(path, url) {
    state.endFile = null;
    state.endImagePath = path;
    el.previewEnd.src = url;
    el.previewEnd.style.display = "block";
    el.placeholderEnd.style.display = "none";
    el.aspectTagEnd.textContent = "图片已装载 ✓";
    el.aspectTagEnd.style.background = "rgba(16, 185, 129, 0.85)";
    el.aspectTagEnd.style.display = "block";

    showToast("📌 已成功将所选图片填入视频【尾帧】！已切回生成工作台", "success");
    const tabBtn = document.querySelector('.tab-button[data-target="view-generate"]');
    if (tabBtn) tabBtn.click();
  };

  let currentViewerImgPath = "";
  let currentViewerImgUrl = "";
  window.openImageViewer = function(path, url, prompt) {
    currentViewerImgPath = path;
    currentViewerImgUrl = url;
    if (el.modalImageViewer) {
      el.imageViewerImg.src = url;
      el.imageViewerTitle.textContent = prompt ? ("图片预览: " + prompt.slice(0, 30) + "...") : "高清图片预览";
      if (el.btnViewerDownload) el.btnViewerDownload.href = url;
      el.modalImageViewer.classList.add("active");
    } else {
      window.open(url, "_blank");
    }
  };

  if (el.btnViewerSetStart) {
    el.btnViewerSetStart.addEventListener("click", () => {
      if (currentViewerImgPath && currentViewerImgUrl) {
        window.setAsStartFrame(currentViewerImgPath, currentViewerImgUrl);
        if (el.modalImageViewer) el.modalImageViewer.classList.remove("active");
      }
    });
  }

  if (el.btnViewerSetEnd) {
    el.btnViewerSetEnd.addEventListener("click", () => {
      if (currentViewerImgPath && currentViewerImgUrl) {
        window.setAsEndFrame(currentViewerImgPath, currentViewerImgUrl);
        if (el.modalImageViewer) el.modalImageViewer.classList.remove("active");
      }
    });
  }

  function renderImageGallery() {
    if (!el.imageGalleryList) return;
    const container = el.imageGalleryList;
    const imageItems = [];
    (state.tasks || []).forEach(t => {
      if (t.status === "completed" && t.image_urls && t.image_urls.length > 0) {
        t.image_urls.forEach((url, idx) => {
          const p = (t.image_paths && t.image_paths[idx]) ? t.image_paths[idx] : "";
          imageItems.push({
            taskId: t.id,
            url: url,
            path: p,
            prompt: t.prompt,
            model: t.model || "nano-pro",
            aspect: t.aspect_ratio || "9:16",
            created_at: t.created_at || ""
          });
        });
      }
    });

    if (el.galleryCount) {
      el.galleryCount.textContent = "(" + imageItems.length + " 张图片)";
    }

    if (imageItems.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1 / -1; text-align:center; padding:60px 0; color:var(--text-muted); font-size:13px;">
          <span style="font-size:28px; display:block; margin-bottom:10px;">🎨</span>
          暂无已生成的图片成果<br>
          在左侧输入画面提示词，选择模型（如 Imagen 3.5 旗舰画质），点击【立即生成图片】开始创作！
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    imageItems.forEach(item => {
      const card = document.createElement("div");
      card.className = "gallery-card";
      const modelLabel = item.model === "nano-pro" ? "Nano Banana Pro" : (item.model === "nano2" ? "Nano Banana 2" : (item.model === "imagen4" ? "Imagen 3.5" : item.model));
      card.innerHTML = `
        <div class="gallery-img-box" onclick="openImageViewer('${escapeJs(item.path)}', '${escapeJs(item.url)}', '${escapeJs(item.prompt)}')">
          <img src="${item.url}" alt="${escapeHtml(item.prompt)}" loading="lazy">
        </div>
        <div class="gallery-info">
          <div class="gallery-tags">
            <span class="badge-task-image">${modelLabel}</span>
            <span class="badge" style="background:rgba(255,255,255,0.06); font-size:10px; padding:2px 5px; border-radius:3px;">${item.aspect}</span>
          </div>
          <div class="gallery-prompt" title="${escapeHtml(item.prompt)}">${escapeHtml(item.prompt)}</div>
          <div class="gallery-actions">
            <button class="gallery-btn-action" onclick="setAsStartFrame('${escapeJs(item.path)}', '${escapeJs(item.url)}')">📌 设为首帧</button>
            <button class="gallery-btn-action" onclick="setAsEndFrame('${escapeJs(item.path)}', '${escapeJs(item.url)}')">📌 设为尾帧</button>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  // ==================== 视频播放器弹窗 ====================
  function openVideoPlayer(taskId, videoUrl) {
    state.currentTaskForVideo = taskId;
    el.playerTitle.textContent = "成片播放 · " + taskId;
    el.playerMeta.textContent = "正在加载视频流...";
    el.html5Video.src = videoUrl;
    el.html5Video.play().catch(() => {});
    el.modalVideo.classList.add("active");

    el.html5Video.onloadedmetadata = () => {
      const dur = el.html5Video.duration.toFixed(1);
      const w = el.html5Video.videoWidth;
      const h = el.html5Video.videoHeight;
      el.playerMeta.textContent = "分辨率: " + w + "x" + h + " (9:16) · 时长: " + dur + "s · MP4 H.264 · 纯净成片";
    };
  }

  el.btnOpenTaskFile.addEventListener("click", async () => {
    if (!state.currentTaskForVideo) return;
    await fetch("/api/system/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "task_video", task_id: state.currentTaskForVideo })
    });
    showToast("已在 Windows 资源管理器中高亮成片文件", "info");
  });

  // ==================== 任务日志弹窗 ====================
  async function openLogModal(taskId) {
    state.currentTaskForLog = taskId;
    if (!el.modalTaskLog) return;
    el.logModalTitle.textContent = "任务执行与调度日志 · " + taskId;
    el.logModalSub.textContent = "正在获取最新控制台与调度器输出...";
    el.logModalContent.textContent = "正在读取日志...";
    el.modalTaskLog.classList.add("active");

    try {
      const resp = await fetch("/api/tasks/" + taskId);
      if (!resp.ok) {
        el.logModalContent.textContent = "获取日志失败 (404)";
        return;
      }
      const t = await resp.json();
      const engName = t.engine === "gemini" ? "Gemini 网页版" : "Google Flow";
      el.logModalSub.textContent = "引擎: " + engName + " · 状态: " + t.status + " · 提交时间: " + (t.submit_time || "--");

      let fullLog = "";
      if (t.events && t.events.length > 0) {
        fullLog += "=== 调度事件记录 (Event Ledger) ===\n";
        t.events.forEach(ev => {
          fullLog += "[" + (ev.created_at || "") + "] [" + ev.event_type + "] " + (ev.message || "") + "\n";
        });
        fullLog += "\n";
      }

      if (t.error_message) {
        fullLog += "=== 异常信息提示 (Error Summary) ===\n";
        fullLog += "[" + (t.error_code || "ERROR") + "] " + t.error_message + "\n\n";
      }

      if (t.logs) {
        fullLog += "=== 进程实时标准输出 (Process Logs) ===\n";
        fullLog += t.logs;
      } else {
        fullLog += "（暂无进程实时输出）";
      }

      el.logModalContent.textContent = fullLog;
    } catch (e) {
      el.logModalContent.textContent = "读取日志失败: " + e.message;
    }
  }

  // ==================== 抽帧对比与质检报告弹窗 ====================
  async function openQAModal(taskId) {
    state.currentTaskForQA = taskId;
    el.qaModalTitle.textContent = "首尾帧抽帧对比与质检 · " + taskId;
    el.qaModalSub.textContent = "正在获取质检切片与相关性数据...";

    // 清空旧图
    el.qaImgStartOrigin.src = "";
    el.qaImgFirstExtracted.src = "";
    el.qaImgEndOrigin.src = "";
    el.qaImgLastExtracted.src = "";
    el.qaImgWatermarkCorner.src = "";

    el.modalQA.classList.add("active");

    try {
      const resp = await fetch("/api/tasks/" + taskId);
      if (!resp.ok) return;
      const t = await resp.json();

      el.qaModalSub.textContent = (t.engine === "gemini" ? "Gemini 网页版" : "Veo 模型") + " · 9:16 竖屏 · 实际生成时长: " + (t.duration_sec || 8) + "s";

      // 渲染图片
      if (t.start_image_url) el.qaImgStartOrigin.src = t.start_image_url;
      if (t.end_image_url) el.qaImgEndOrigin.src = t.end_image_url;
      if (t.qa_files && t.qa_files.first_frame) el.qaImgFirstExtracted.src = t.qa_files.first_frame;
      if (t.qa_files && t.qa_files.last_frame) el.qaImgLastExtracted.src = t.qa_files.last_frame;
      if (t.qa_files && t.qa_files.watermark_corner) el.qaImgWatermarkCorner.src = t.qa_files.watermark_corner;

      // 首帧状态
      if (t.first_frame_matched) {
        el.qaFirstBadge.textContent = "✓ 匹配优秀";
        el.qaFirstBadge.className = "status-badge status-completed";
      } else {
        el.qaFirstBadge.textContent = "❌ 偏离";
        el.qaFirstBadge.className = "status-badge status-failed";
      }
      el.qaFirstDesc.textContent = "首帧 NCC 归一化相似度: " + (t.first_frame_ncc ? t.first_frame_ncc.toFixed(4) : "--") + " (标准基线: ≥0.75)";

      // 尾帧状态
      if (t.engine === "gemini") {
        el.qaLastBadge.textContent = "免测 (Gemini 网页版)";
        el.qaLastBadge.className = "status-badge status-completed";
        el.qaLastDesc.textContent = "Gemini 网页版专注单图/文生视频，不施加尾帧硬性约束。";
      } else if (t.last_frame_matched) {
        el.qaLastBadge.textContent = "✓ 匹配优秀";
        el.qaLastBadge.className = "status-badge status-completed";
        el.qaLastDesc.textContent = "尾帧 NCC 归一化相似度: " + (t.last_frame_ncc ? t.last_frame_ncc.toFixed(4) : "--") + " (与首图区分度: " + (t.last_vs_start_ncc ? t.last_vs_start_ncc.toFixed(4) : "--") + ")";
      } else {
        el.qaLastBadge.textContent = "❌ 偏离";
        el.qaLastBadge.className = "status-badge status-failed";
        el.qaLastDesc.textContent = "尾帧 NCC 归一化相似度: " + (t.last_frame_ncc ? t.last_frame_ncc.toFixed(4) : "--") + " (低于合格基线)";
      }

      // 水印状态
      if (t.watermark_check === "clean") {
        el.qaWatermarkTitle.textContent = "可见水印检测: ✅ 纯净无水印 (Clean)";
        el.qaWatermarkDetail.textContent = "右下角 240x80 像素区域未检测到半透明或实心 Google 水印，符合无水印标准。隐形数字水印 (SynthID) 保留在像素频域中。";
      } else if (t.watermark_check === "forced_visible") {
        el.qaWatermarkTitle.textContent = "可见水印检测: ⚠️ 存在可见水印 (Watermarked)";
        el.qaWatermarkDetail.textContent = "检测到右下角有高对比度水印特征。建议仅作为初版草稿预览使用。";
      } else {
        el.qaWatermarkTitle.textContent = "可见水印检测: --";
        el.qaWatermarkDetail.textContent = "该视频未检出水印特征或处于非标准渲染模式。";
      }

      // 渲染关键事件
      el.qaEventsList.innerHTML = "";
      if (t.events && t.events.length > 0) {
        t.events.forEach(ev => {
          const row = document.createElement("div");
          row.style.marginBottom = "4px";
          row.innerHTML = "<span style=\"color:var(--text-muted);\">[" + (ev.created_at ? ev.created_at.substring(11, 19) : "") + "]</span> <b style=\"color:var(--blue-primary);\">" + ev.event_type + ":</b> " + escapeHtml(ev.message);
          el.qaEventsList.appendChild(row);
        });
      } else {
        el.qaEventsList.innerHTML = "<div style=\"color:var(--text-muted);\">暂无事件记录</div>";
      }
    } catch (e) {
      console.error(e);
    }
  }

  // ==================== 账号管理视图 ====================
  const btnAutoAll = document.getElementById("btn-auto-onboard-all");
  if (btnAutoAll) {
    btnAutoAll.addEventListener("click", async () => {
      btnAutoAll.disabled = true;
      btnAutoAll.innerText = "⏳ 正在批量初始化...";
      showToast("🚀 已开始后台批量处理所有未就绪账号的协议与默认工程...", "info");
      try {
        const resp = await fetch("/api/profiles/auto-onboard-all", { method: "POST" });
        const d = await resp.json();
        if (resp.ok) {
          let succCount = (d.results || []).filter(r => r.result && r.result.success).length;
          showToast(`✨ 批量初始化完成！成功激活 ${succCount} 个账号`, "success");
        } else {
          showToast("批量初始化失败", "error");
        }
      } catch (e) {
        showToast("批量请求异常: " + e.message, "error");
      } finally {
        btnAutoAll.disabled = false;
        btnAutoAll.innerText = "✨ 一键初始化全部账号";
        fetchProfiles();
        fetchOverview();
      }
    });
  }

  el.btnRefreshProfiles.addEventListener("click", () => {
    triggerRefreshButton(el.btnRefreshProfiles, async () => {
      await fetchProfiles(true);
    }, "账号状态已刷新 (" + (state.profiles ? state.profiles.length : 0) + " 个账号)");
  });

  async function fetchProfiles(force = false) {
    try {
      const url = `/api/profiles?_t=${Date.now()}`;
      const resp = await fetch(url);
      if (!resp.ok) return;
      state.profiles = await resp.json();
      el.badgeTotalProfiles.textContent = state.profiles.length;
      renderProfiles();
      updateAssignedProfSelect();
    } catch (e) {
      console.error("fetchProfiles 失败", e);
    }
  }

  function renderProfiles() {
    const container = el.profilesContainer;
    container.innerHTML = "";

    if (state.profiles.length === 0) {
      container.innerHTML = "<div style=\"grid-column:1/-1; text-align:center; padding:60px 0; color:var(--text-muted);\">📭 暂无注册的 Google 账号 Profile，请点击右上角添加。</div>";
      return;
    }

    state.profiles.forEach(p => {
      const box = document.createElement("div");
      box.className = "profile-box";

      let statusBadge = "<span class=\"status-badge status-completed\">空闲就绪</span>";
      if (!p.enabled) statusBadge = "<span class=\"status-badge status-queued\">已停用</span>";
      else if (p.status === "busy") statusBadge = "<span class=\"status-badge status-running\">正在生成</span>";
      else if (p.status === "cooldown") statusBadge = "<span class=\"status-badge\" style=\"background:rgba(245,158,11,0.2); color:var(--orange-warn); border:1px solid var(--orange-warn);\">冷却休眠中</span>";
      else if (p.status === "auth_expired") statusBadge = "<span class=\"status-badge status-failed\">授权已失效</span>";

      let wmBadge = "<span style=\"font-size:11px; color:var(--text-muted);\">未知</span>";
      if (p.watermark_mode === "clean") wmBadge = "<span style=\"font-size:11px; color:var(--green-ok);\">✨ 无水印纯净版</span>";
      else if (p.watermark_mode === "forced_visible") wmBadge = "<span style=\"font-size:11px; color:var(--orange-warn);\">🏷️ 有可见水印</span>";

      let cooldownInfo = "无";
      if (p.cooldown_until) {
        cooldownInfo = "<span style=\"color:var(--orange-warn); font-weight:600;\">至 " + p.cooldown_until.substring(11, 19) + "</span>";
      }

      box.innerHTML = `
        <div class="profile-top">
          <div>
            <div class="prof-title">${p.name}</div>
            <div class="prof-desc">${p.account_label || "独立 Chrome Profile 隔离"}</div>
          </div>
          <div>${statusBadge}</div>
        </div>

        <div class="profile-meta-list">
          <div class="meta-item"><span>水印特性</span>${wmBadge}</div>
          <div class="meta-item"><span>Flow专属工程</span>${p.flow_project_id ? `<span style="font-size:11px; color:var(--green-ok); font-family:monospace; font-weight:600;">✅ 已绑定 (${p.flow_project_id.substring(0,8)}...)</span>` : `<span style="font-size:11px; color:var(--orange-warn);">⚠️ 待就绪 (任务运行自动自愈)</span>`}</div>
          <div class="meta-item"><span>上次成功</span><b>${p.last_success_at ? p.last_success_at.substring(0, 19).replace("T", " ") : "暂无"}</b></div>
          <div class="meta-item"><span>冷却截止</span>${cooldownInfo}</div>
        </div>

        <div class="profile-bottom" style="display:flex; flex-direction:column; gap:8px;">
          <button class="btn btn-primary btn-sm btn-auto-onboard" data-id="${p.id}" data-name="${p.name}" style="width:100%; background:linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); border:none; font-weight:600; color:#fff;" title="针对新添加账号：全自动模拟跳过一次性服务条款/欢迎弹窗，并自动创建默认工程">
            ✨ 自动过协议与初始化
          </button>
          <div style="display:flex; gap:6px; width:100%;">
            <button class="btn btn-secondary btn-sm btn-login-flow" data-id="${p.id}" data-name="${p.name}" style="flex:1;" title="打开真实 Chrome 登录 Google Flow。若有弹窗点一次同意后关闭 Chrome 即可">
              🔑 打开 Flow 点同意
            </button>
            <button class="btn btn-secondary btn-sm btn-login-gemini" data-id="${p.id}" data-name="${p.name}" style="flex:1;" title="打开真实 Chrome 登录 Gemini 网页版">
              🌐 登录 Gemini
            </button>
          </div>
          <div style="display:flex; gap:6px; width:100%;">
            <button class="btn btn-secondary btn-sm btn-verify-profile" data-id="${p.id}" data-name="${p.name}" style="flex:1; border-color:var(--blue-primary); color:var(--blue-primary);" title="无头检测登录凭据状态，有效则直接恢复空闲就绪">
              🔍 验证登录
            </button>
            <button class="btn btn-secondary btn-sm btn-kill-chrome" data-id="${p.id}" data-name="${p.name}" style="flex:1; border-color:var(--orange-warn); color:var(--orange-warn);" title="强制关闭占用该 Profile 的 Chrome 进程并解除锁定">
              ⏹ 关占用 Chrome
            </button>
          </div>
          
          ${(p.status === "cooldown" || p.status === "auth_expired") ? `
            <button class="btn btn-warning btn-sm btn-reset-profile" data-id="${p.id}" data-name="${p.name}" style="width:100%; margin-bottom:4px;" title="清除冷却或异常标记，立即恢复为空闲就绪">
              ⚡ 立即解除冷却/重置就绪
            </button>
          ` : ""}
          <button class="btn ${p.enabled ? "btn-secondary" : "btn-primary"} btn-sm btn-toggle-profile" data-id="${p.id}" data-enabled="${p.enabled}" style="width:100%;">
            ${p.enabled ? "停用此账号" : "启用此账号"}
          </button>
        </div>
      `;

      container.appendChild(box);
    });


    // 绑定验证登录
    container.querySelectorAll(".btn-verify-profile").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const name = b.getAttribute("data-name");
        b.disabled = true;
        b.innerText = "⏳ 正在验证...";
        try {
          const resp = await fetch("/api/profiles/" + id + "/verify-auth", { method: "POST" });
          const d = await resp.json();
          if (resp.ok && d.valid) {
            showToast(d.message || "账号登录有效，已重置为空闲就绪！", "success");
          } else {
            showToast(d.message || "登录态验证未通过", "error");
          }
          fetchProfiles();
          fetchOverview();
        } catch (e) {
          showToast("验证请求异常: " + e.message, "error");
        } finally {
          b.disabled = false;
          b.innerText = "🔍 验证登录";
        }
      });
    });

    // 绑定关闭 Chrome
    container.querySelectorAll(".btn-kill-chrome").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const name = b.getAttribute("data-name");
        try {
          const resp = await fetch("/api/profiles/" + id + "/close-chrome", { method: "POST" });
          const d = await resp.json();
          if (resp.ok) {
            showToast(d.message || ("已释放账号 [" + name + "] 的 Chrome 占用"), "success");
            fetchProfiles();
            fetchOverview();
          } else {
            showToast(d.detail || "关闭失败", "error");
          }
        } catch (e) {
          showToast("错误: " + e.message, "error");
        }
      });
    });

    // 绑定单账号自动过协议与初始化
    container.querySelectorAll(".btn-auto-onboard").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const name = b.getAttribute("data-name");
        b.disabled = true;
        b.innerText = "⏳ 正在自动过协议...";
        try {
          const resp = await fetch("/api/profiles/" + id + "/auto-onboard", { method: "POST" });
          const d = await resp.json();
          if (resp.ok && d.success) {
            showToast(d.message || "🎉 账号 [" + name + "] 协议同意与初始化成功，已就绪！", "success");
          } else {
            showToast(d.message || "自动过协议未能完全通过，可点击【🔑 打开 Flow 点同意】", "error");
          }
        } catch (e) {
          showToast("初始化请求失败: " + e.message, "error");
        } finally {
          b.disabled = false;
          b.innerText = "✨ 自动过协议与初始化";
          fetchProfiles();
          fetchOverview();
        }
      });
    });

    // 绑定账号登录 Flow
    container.querySelectorAll(".btn-login-flow").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const name = b.getAttribute("data-name");
        try {
          const resp = await fetch("/api/profiles/" + id + "/launch-login", { method: "POST" });
          if (resp.ok) {
            showToast("已拉起 Chrome 窗口 [" + name + "]！若弹出【服务条款/欢迎使用】，点一次【同意/继续】后【关闭 Chrome 窗口】即可！", "success");
          } else {
            showToast("启动登录窗口失败", "error");
          }
        } catch (e) {
          showToast("错误: " + e.message, "error");
        }
      });
    });

        // 绑定重置状态/解除冷却
    container.querySelectorAll(".btn-reset-profile").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const name = b.getAttribute("data-name");
        try {
          const resp = await fetch("/api/profiles/" + id + "/reset-status", { method: "POST" });
          const d = await resp.json();
          if (resp.ok) {
            showToast("已成功重置账号 [" + name + "] 为就绪状态", "success");
            fetchProfiles();
            fetchOverview();
          } else {
            showToast(d.detail || "重置失败", "error");
          }
        } catch (e) {
          showToast("错误: " + e.message, "error");
        }
      });
    });

    // 绑定账号登录 Gemini
    container.querySelectorAll(".btn-login-gemini").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const name = b.getAttribute("data-name");
        try {
          const resp = await fetch("/api/profiles/" + id + "/launch-gemini-login", { method: "POST" });
          if (resp.ok) {
            showToast("已拉起 Gemini 网页版 [" + name + "]，请在弹出的 Chrome 中登录 Google 账号", "success");
          } else {
            showToast("启动 Gemini 登录窗口失败", "error");
          }
        } catch (e) {
          showToast("错误: " + e.message, "error");
        }
      });
    });

    // 启用/停用切换
    container.querySelectorAll(".btn-toggle-profile").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const currentEnabled = b.getAttribute("data-enabled") === "true";
        const targetEnabled = !currentEnabled;
        try {
          const resp = await fetch("/api/profiles/" + id + "/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: targetEnabled })
          });
          if (resp.ok) {
            showToast(targetEnabled ? "账号已启用" : "账号已停用", "info");
            fetchProfiles();
            fetchOverview();
          }
        } catch (e) {
          showToast("操作失败: " + e.message, "error");
        }
      });
    });
  }

  function updateAssignedProfSelect() {
    const sel = el.selectAssignedProf;
    const imgSel = el.selectImageProfile;
    const batchSel = el.selectBatchProfile;
    const currentVal = sel ? sel.value : "";
    const currentImgVal = imgSel ? imgSel.value : "";
    const currentBatchVal = batchSel ? batchSel.value : "auto";

    if (sel) {
      sel.innerHTML = '<option value="">自动调度（负载均衡 + 额度耗尽自动轮换）</option>';
      state.profiles.forEach(p => {
        if (p.enabled) {
          const opt = document.createElement("option");
          opt.value = p.id;
          opt.textContent = p.name + " (" + (p.account_label || "无备注") + ") [" + p.status + "]";
          sel.appendChild(opt);
        }
      });
      sel.value = currentVal;
    }

    if (imgSel) {
      imgSel.innerHTML = '<option value="">自动轮询空闲账号</option>';
      state.profiles.forEach(p => {
        if (p.enabled) {
          const opt = document.createElement("option");
          opt.value = p.id;
          opt.textContent = p.name + " (" + (p.account_label || "无备注") + ") [" + p.status + "]";
          imgSel.appendChild(opt);
        }
      });
      imgSel.value = currentImgVal;
    }

    if (batchSel) {
      batchSel.innerHTML = '<option value="auto">🌟 自动锁定最优空闲账号（推荐，整批不切号）</option>';
      state.profiles.forEach(p => {
        if (p.enabled) {
          const opt = document.createElement("option");
          opt.value = p.id;
          const cleanTag = p.watermark_mode === "clean" ? " [无水印]" : "";
          opt.textContent = p.name + " (" + (p.account_label || "无备注") + ")" + cleanTag + " [" + p.status + "]";
          batchSel.appendChild(opt);
        }
      });
      batchSel.value = currentBatchVal || "auto";
    }
  }

  // 添加新 Profile 弹窗
  el.btnOpenAddProfile.addEventListener("click", () => {
    // 自动寻找下一个未使用的代号
    const existingNames = new Set((state.profiles || []).map(p => p.name.toLowerCase()));
    let nextIdx = 2;
    while (existingNames.has("acc" + nextIdx) || existingNames.has("gflow-acc" + nextIdx)) {
      nextIdx++;
    }
    el.inputProfName.value = "acc" + nextIdx;
    el.inputProfLabel.value = "备用账号 " + nextIdx;
    if (el.inputProfNotes) el.inputProfNotes.value = "";
    el.modalAddProfile.classList.add("active");
  });

  el.btnConfirmAddProfile.addEventListener("click", async () => {
    const name = el.inputProfName.value.trim().toLowerCase();
    const label = el.inputProfLabel.value.trim();
    const notes = el.inputProfNotes ? el.inputProfNotes.value.trim() : "";

    if (!name || !/^[a-z0-9_-]+$/.test(name)) {
      showToast("账号代号仅支持小写字母、数字与中划线 (如 acc2)", "warn");
      return;
    }

    try {
      el.btnConfirmAddProfile.disabled = true;
      el.btnConfirmAddProfile.textContent = "创建中...";
      const resp = await fetch("/api/profiles/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, account_label: label, notes })
      });
      const data = await resp.json();
      if (resp.ok) {
        showToast("账号 [" + name + "] 创建成功，正在为你弹出独立登录窗口...", "success");
        el.modalAddProfile.classList.remove("active");
        fetchProfiles();
        fetchOverview();
        // 自动拉起独立 Chrome 登录窗口，无需用户再到卡片上去找
        try {
          await fetch("/api/profiles/" + data.id + "/launch-login", { method: "POST" });
          showToast("已弹出独立 Chrome 窗口，请登录 Google 后直接关闭该窗口即可", "info", 5000);
        } catch (err) {
          console.error("Auto launch login error:", err);
        }
      } else {
        showToast("添加失败: " + (data.detail || "未知错误"), "error");
      }
    } catch (e) {
      showToast("错误: " + e.message, "error");
    } finally {
      el.btnConfirmAddProfile.disabled = false;
      el.btnConfirmAddProfile.textContent = "确定并立即打开 Chrome 登录";
    }
  });

  // ==================== 顶部概览与系统信息 ====================
  async function fetchOverview() {
    try {
      const resp = await fetch("/api/overview");
      if (!resp.ok) return;
      const d = await resp.json();
      state.overview = d;

      // 调度器状态
      const isRunning = (d.scheduler_running !== undefined) ? d.scheduler_running : (d.scheduler && d.scheduler.running);
      const fleetCooldown = d.fleet_cooldown_sec || 0;
      const bannerEl = document.getElementById("fleet-cooldown-banner");
      const countdownEl = document.getElementById("fleet-cooldown-countdown");
      if (bannerEl && countdownEl) {
        if (fleetCooldown > 0) {
          bannerEl.style.display = "block";
          countdownEl.textContent = fleetCooldown;
        } else {
          bannerEl.style.display = "none";
        }
      }
      if (isRunning) {
        if (fleetCooldown > 0) {
          el.schedulerDot.className = "status-dot dot-busy";
          el.schedulerText.textContent = `🛡️ 安全避让中 (${fleetCooldown}s)`;
          el.schedulerText.title = "已触发全池安全避让，暂停新任务派发，保护账号池免受连带风控";
        } else {
          el.schedulerDot.className = "status-dot dot-running";
          el.schedulerText.textContent = "调度器运行中";
          el.schedulerText.title = "调度器正在正常轮询并分发任务";
        }
        el.btnToggleScheduler.textContent = "暂停";
        el.btnToggleScheduler.className = "btn btn-secondary btn-sm";
      } else {
        el.schedulerDot.className = "status-dot dot-idle";
        el.schedulerText.textContent = "调度器已暂停";
        el.btnToggleScheduler.textContent = "恢复";
        el.btnToggleScheduler.className = "btn btn-primary btn-sm";
      }

      // 顶部统计
      el.statIdleProf.textContent = (d.profiles && (d.profiles.idle ?? d.profiles.idle_count)) || 0;
      el.statRunningTask.textContent = (d.tasks && (d.tasks.running ?? d.tasks.running_count)) || 0;
      el.statQueuedTask.textContent = (d.tasks && (d.tasks.queued ?? d.tasks.queued_count)) || 0;
      el.statCompletedTask.textContent = (d.tasks && (d.tasks.completed ?? d.tasks.completed_count)) || 0;

      const now = new Date();
      el.lastRefreshTime.textContent = "最后刷新: " + now.toLocaleTimeString();
    } catch (e) {
      console.error("fetchOverview 失败", e);
    }
  }

  el.btnOpenOutputs.addEventListener("click", async () => {
    await fetch("/api/system/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "outputs" })
    });
    showToast("已在 Windows 资源管理器中打开成片目录", "info");
  });

  el.btnOpenSysinfo.addEventListener("click", async () => {
    el.modalSysinfo.classList.add("active");
    try {
      const resp = await fetch("/api/system/info");
      if (resp.ok) {
        const info = await resp.json();
        document.getElementById("sys-gflow-ver").textContent = info.gflow_version;
        document.getElementById("sys-commit").textContent = info.gflow_commit;
        document.getElementById("sys-py-ver").textContent = info.python_version;
        document.getElementById("sys-platform").textContent = info.platform;
        document.getElementById("sys-db").textContent = info.db_path;
        document.getElementById("sys-output").textContent = info.output_dir;
      }
    } catch (e) {
      console.error(e);
    }
  });

  // 通用弹窗关闭按钮
  document.querySelectorAll("[data-modal]").forEach(b => {
    b.addEventListener("click", () => {
      const mId = b.getAttribute("data-modal");
      const m = document.getElementById(mId);
      if (m) {
        m.classList.remove("active");
        if (mId === "modal-video-player") {
          el.html5Video.pause();
          el.html5Video.src = "";
        }
      }
    });
  });

  // 点击遮罩外部关闭
  document.querySelectorAll(".modal-backdrop").forEach(modal => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        modal.classList.remove("active");
        if (modal.id === "modal-video-player") {
          el.html5Video.pause();
          el.html5Video.src = "";
        }
      }
    });
  });

  
  // ==================== 智能视频生产工坊 (Smart Video Studio) ====================
  let currentStudioMode = "custom";
  let activePipelineJobId = null;
  let pipelinePollTimer = null;
  let currentPlanShots = [];

  // DOM 元素引用
  // 智能一键模式 DOM 元素
  const btnModeSimple = document.getElementById("btn-mode-simple");
  const btnModePro = document.getElementById("btn-mode-pro");
  const creatorModeDescText = document.getElementById("creator-mode-desc-text");
  const panelModeSimple = document.getElementById("panel-mode-simple");
  const panelModePro = document.getElementById("panel-mode-pro");
  const simpleIdeaInput = document.getElementById("simple-idea-input");
  const btnSimpleClearIdea = document.getElementById("btn-simple-clear-idea");
  const simpleMatDir = document.getElementById("simple-mat-dir");
  const btnSimpleScan = document.getElementById("btn-simple-scan");
  const btnSimpleGenerate = document.getElementById("btn-simple-generate");
  const btnSimplePreviewAnimatic = document.getElementById("btn-simple-preview-animatic");

  const btnPipeLoadSampleProducts = document.getElementById("btn-pipe-load-sample-products");
  const btnPipeLoadSampleStoryboard = document.getElementById("btn-pipe-load-sample-storyboard");
  const pipePresetsContainer = document.getElementById("pipe-presets-container");

  const pipeMatDir = document.getElementById("pipe-mat-dir");
  const btnPipeQuickInspect = document.getElementById("btn-pipe-quick-inspect");
  const btnPipeInspectAction = document.getElementById("btn-pipe-inspect-action");

  // 工序 1: 研判与切图
  const stageBlockInspect = document.getElementById("stage-block-inspect");
  const pipeToggleInspect = document.getElementById("pipe-toggle-inspect");
  const pipeInspectStateText = document.getElementById("pipe-inspect-state-text");
  const pipeCheckGridCrop = document.getElementById("pipe-check-grid-crop");

  // 工序 2: 视觉引擎
  const stageBlockVisual = document.getElementById("stage-block-visual");
  const pipeEngineChoice = document.getElementById("pipe-engine-choice");
  const pipeAspect = document.getElementById("pipe-aspect");
  const pipeDuration = document.getElementById("pipe-duration");
  const pipeCustomDurationBox = document.getElementById("pipe-custom-duration-box");
  const pipeCustomDurationInput = document.getElementById("pipe-custom-duration-input");

  // 工序 3: 配音
  const stageBlockVoice = document.getElementById("stage-block-voice");
  const pipeToggleVoice = document.getElementById("pipe-toggle-voice");
  const pipeVoiceStateText = document.getElementById("pipe-voice-state-text");
  const pipeVoiceName = document.getElementById("pipe-voice-name");
  const pipeScriptText = document.getElementById("pipe-script-text");

  // 工序 4: BGM
  const stageBlockBgm = document.getElementById("stage-block-bgm");
  const pipeToggleBgm = document.getElementById("pipe-toggle-bgm");
  const pipeBgmStateText = document.getElementById("pipe-bgm-state-text");
  const pipeBgmMode = document.getElementById("pipe-bgm-mode");
  const pipeCustomBgmBox = document.getElementById("pipe-custom-bgm-box");
  const pipeBgmPath = document.getElementById("pipe-bgm-path");

  // 工序 5: 字幕
  const stageBlockSub = document.getElementById("stage-block-sub");
  const pipeToggleSub = document.getElementById("pipe-toggle-sub");
  const pipeSubStateText = document.getElementById("pipe-sub-state-text");
  const pipeSubMode = document.getElementById("pipe-sub-mode");

  // 动作按钮
  const btnPipePlanConfirm = document.getElementById("btn-pipe-plan-confirm");
  const btnStartPipeline = document.getElementById("btn-start-pipeline");
  const btnPipeExecutePlan = document.getElementById("btn-pipe-execute-plan");

  // 右侧看板
  const tabPipePlan = document.getElementById("tab-pipe-plan");
  const tabPipeMonitor = document.getElementById("tab-pipe-monitor");
  const pipeStatusTag = document.getElementById("pipe-status-tag");
  const pipePanelPlanContent = document.getElementById("pipe-panel-plan-content");
  const pipePanelMonitorContent = document.getElementById("pipe-panel-monitor-content");

  const pipeDiagModeTag = document.getElementById("pipe-diag-mode-tag");
  const pipeDiagConfidence = document.getElementById("pipe-diag-confidence");
  const pipeDiagSummary = document.getElementById("pipe-diag-summary");
  const pipeShotsCount = document.getElementById("pipe-shots-count");
  const pipeShotsList = document.getElementById("pipe-shots-list");
  const btnPipeAddShot = document.getElementById("btn-pipe-add-shot");
  const btnPipeClearShots = document.getElementById("btn-pipe-clear-shots");

  // 双层时间轴 Studio 与四维锚点资产 DOM
  const pipeStoryFlowTrack = document.getElementById("pipe-story-flow-track");
  const pipeTimelineRulerSection = document.getElementById("pipe-timeline-ruler-section");
  const pipeRulerTicks = document.getElementById("pipe-ruler-ticks");
  const pipeRulerVideoTrack = document.getElementById("pipe-ruler-video-track");
  const rulerTotalLabel = document.getElementById("ruler-total-label");

  const pipeDnaLockToggle = document.getElementById("pipe-dna-lock-toggle");
  const dnaSubjectStatus = document.getElementById("dna-subject-status");
  const dnaSubjectThumb = document.getElementById("dna-subject-thumb");
  const dnaSubjectInput = document.getElementById("dna-subject-input");
  const dnaSceneStatus = document.getElementById("dna-scene-status");
  const dnaSceneInput = document.getElementById("dna-scene-input");
  const dnaStyleStatus = document.getElementById("dna-style-status");
  const dnaStyleInput = document.getElementById("dna-style-input");
  const dnaStateStatus = document.getElementById("dna-state-status");
  const dnaStateInput = document.getElementById("dna-state-input");

  const btnPipeAnimaticPreview = document.getElementById("btn-pipe-animatic-preview");
  const btnPipeExportSpec = document.getElementById("btn-pipe-export-spec");
  const btnPipeImportSpec = document.getElementById("btn-pipe-import-spec");

  // 模态框 DOM
  const pipeSpecModal = document.getElementById("pipe-spec-modal");
  const pipeSpecJsonTextarea = document.getElementById("pipe-spec-json-textarea");
  const btnCloseSpecModal = document.getElementById("btn-close-spec-modal");
  const btnCopySpecJson = document.getElementById("btn-copy-spec-json");
  const btnApplySpecJson = document.getElementById("btn-apply-spec-json");

  const pipeAnimaticModal = document.getElementById("pipe-animatic-modal");
  const btnCloseAnimaticModal = document.getElementById("btn-close-animatic-modal");
  const animaticLoadingSpinner = document.getElementById("animatic-loading-spinner");
  const animaticVideoPlayer = document.getElementById("animatic-video-player");
  const animaticModalFooter = document.getElementById("animatic-modal-footer");
  const btnDoneAnimaticModal = document.getElementById("btn-done-animatic-modal");

  const pipeBiteDrawerModal = document.getElementById("pipe-bite-drawer-modal");
  const btnCloseBiteModal = document.getElementById("btn-close-bite-modal");
  const bitePrevLabel = document.getElementById("bite-prev-label");
  const bitePrevImg = document.getElementById("bite-prev-img");
  const biteCurrLabel = document.getElementById("bite-curr-label");
  const biteCurrImg = document.getElementById("bite-curr-img");
  const biteJointBadge = document.getElementById("bite-joint-badge");
  const biteJointDesc = document.getElementById("bite-joint-desc");
  const btnSaveBiteJoint = document.getElementById("btn-save-bite-joint");

  const pipeProgressBar = document.getElementById("pipe-progress-bar");
  const pipeLogBox = document.getElementById("pipe-log-box");
  const pipeResultBox = document.getElementById("pipe-result-box");
  const pipePlayVideoBtn = document.getElementById("pipe-play-video-btn");
  const pipeVideoLink = document.getElementById("pipe-video-link");
  const pipeOpenFolderBtn = document.getElementById("pipe-open-folder-btn");

  // 1. 快捷预设配置表 (点击可一键同步 5 个工序开关，但用户随时可以独立微调)
  const PRESET_CONFIGS = {
    custom: {
      name: "全自由装配"
    },
    ai_commercial: {
      name: "产品包装大片",
      inspect: true,
      grid_crop: false,
      engine: "local",
      aspect: "16:9",
      duration: "natural",
      voice: true,
      voice_name: "zh-CN-YunxiNeural",
      bgm: true,
      bgm_mode: "auto",
      sub: true
    },
    storyboard_motion: {
      name: "科学分镜动效",
      inspect: true,
      grid_crop: true,
      engine: "local",
      aspect: "16:9",
      duration: "natural",
      voice: true,
      voice_name: "zh-CN-YunjianNeural",
      bgm: true,
      bgm_mode: "auto",
      sub: true
    },
    pure_visual: {
      name: "纯视觉 (静音无字)",
      inspect: true,
      grid_crop: false,
      engine: "flow_veo",
      aspect: "16:9",
      duration: "10",
      voice: false,
      bgm: true,
      bgm_mode: "auto",
      sub: false
    },
    media_montage: {
      name: "多素材极速混剪",
      inspect: true,
      grid_crop: false,
      engine: "direct_cut",
      aspect: "16:9",
      duration: "natural",
      voice: false,
      bgm: true,
      bgm_mode: "auto",
      sub: false
    },
    post_wrap: {
      name: "画外音字幕精剪",
      inspect: false,
      grid_crop: false,
      engine: "direct_cut",
      aspect: "16:9",
      duration: "natural",
      voice: true,
      voice_name: "zh-CN-YunxiNeural",
      bgm: true,
      bgm_mode: "auto",
      sub: true
    },
    long_series_30s: {
      name: "30s 连续剧情短片",
      inspect: true,
      grid_crop: false,
      engine: "local",
      aspect: "16:9",
      duration: "30",
      total_duration: 30,
      voice: true,
      voice_name: "zh-CN-YunxiNeural",
      bgm: true,
      bgm_mode: "auto",
      sub: true
    },
    long_series_60s: {
      name: "60s 完整故事大片",
      inspect: true,
      grid_crop: false,
      engine: "local",
      aspect: "16:9",
      duration: "custom",
      custom_duration: 60,
      total_duration: 60,
      voice: true,
      voice_name: "zh-CN-YunxiNeural",
      bgm: true,
      bgm_mode: "auto",
      sub: true
    },
    one_shot_chain: {
      name: "一镜到底尾帧接力",
      inspect: true,
      grid_crop: false,
      engine: "local",
      aspect: "16:9",
      duration: "30",
      total_duration: 30,
      voice: true,
      voice_name: "zh-CN-YunxiNeural",
      bgm: true,
      bgm_mode: "auto",
      sub: true
    }
  };

  function applyPreset(presetKey, isUserClick = true) {
    currentStudioMode = presetKey;
    document.querySelectorAll(".preset-chip").forEach(chip => {
      if (chip.getAttribute("data-preset") === presetKey) {
        chip.classList.add("active");
      } else {
        chip.classList.remove("active");
      }
    });

    const cfg = PRESET_CONFIGS[presetKey];
    if (!cfg || presetKey === "custom") {
      return;
    }

    if (cfg.inspect !== undefined && pipeToggleInspect) pipeToggleInspect.checked = cfg.inspect;
    if (cfg.grid_crop !== undefined && pipeCheckGridCrop) pipeCheckGridCrop.checked = cfg.grid_crop;
    if (cfg.engine && pipeEngineChoice) pipeEngineChoice.value = cfg.engine;
    if (cfg.aspect && pipeAspect) pipeAspect.value = cfg.aspect;
    if (cfg.duration && pipeDuration) {
      pipeDuration.value = cfg.duration;
      if (pipeCustomDurationBox) {
        pipeCustomDurationBox.style.display = (cfg.duration === "custom") ? "block" : "none";
      }
      if (cfg.custom_duration && pipeCustomDurationInput) {
        pipeCustomDurationInput.value = cfg.custom_duration;
      }
    }
    if (cfg.voice !== undefined && pipeToggleVoice) pipeToggleVoice.checked = cfg.voice;
    if (cfg.voice_name && pipeVoiceName) pipeVoiceName.value = cfg.voice_name;
    if (cfg.bgm !== undefined && pipeToggleBgm) pipeToggleBgm.checked = cfg.bgm;
    if (cfg.bgm_mode && pipeBgmMode) {
      pipeBgmMode.value = cfg.bgm_mode;
      if (pipeCustomBgmBox) {
        pipeCustomBgmBox.style.display = (cfg.bgm_mode === "custom") ? "block" : "none";
      }
    }
    if (cfg.sub !== undefined && pipeToggleSub) pipeToggleSub.checked = cfg.sub;

    updateAllStageUIs();
  }

  function markCustomPreset() {
    currentStudioMode = "custom";
    document.querySelectorAll(".preset-chip").forEach(chip => {
      if (chip.getAttribute("data-preset") === "custom") {
        chip.classList.add("active");
      } else {
        chip.classList.remove("active");
      }
    });
  }

  // 2. 5大工序视觉与状态同步
  function updateInspectStageUI() {
    if (!pipeToggleInspect) return;
    const on = pipeToggleInspect.checked;
    if (stageBlockInspect) {
      if (on) stageBlockInspect.classList.remove("disabled-stage");
      else stageBlockInspect.classList.add("disabled-stage");
    }
    if (pipeInspectStateText) {
      pipeInspectStateText.innerText = on ? "已开启自动分析" : "已跳过分析 (直通排产)";
      pipeInspectStateText.style.color = on ? "#10b981" : "#94a3b8";
    }
  }

  function updateVoiceStageUI() {
    if (!pipeToggleVoice) return;
    const on = pipeToggleVoice.checked;
    if (stageBlockVoice) {
      if (on) stageBlockVoice.classList.remove("disabled-stage");
      else stageBlockVoice.classList.add("disabled-stage");
    }
    if (pipeVoiceName) pipeVoiceName.disabled = !on;
    if (pipeVoiceStateText) {
      const vText = pipeVoiceName && pipeVoiceName.selectedIndex >= 0 ? pipeVoiceName.options[pipeVoiceName.selectedIndex].text : "解说";
      const shortName = vText.split(" ")[1] || "解说";
      pipeVoiceStateText.innerText = on ? `已启用 (${shortName})` : "已静音 (纯画面无解说)";
      pipeVoiceStateText.style.color = on ? "#10b981" : "#94a3b8";
    }
  }

  function updateBgmStageUI() {
    if (!pipeToggleBgm) return;
    const on = pipeToggleBgm.checked;
    if (stageBlockBgm) {
      if (on) stageBlockBgm.classList.remove("disabled-stage");
      else stageBlockBgm.classList.add("disabled-stage");
    }
    if (pipeBgmMode) pipeBgmMode.disabled = !on;
    if (pipeBgmStateText) {
      pipeBgmStateText.innerText = on ? "已启用 (智能混音避让)" : "已关闭背景音乐";
      pipeBgmStateText.style.color = on ? "#10b981" : "#94a3b8";
    }
  }

  function updateSubStageUI() {
    if (!pipeToggleSub) return;
    const on = pipeToggleSub.checked;
    if (stageBlockSub) {
      if (on) stageBlockSub.classList.remove("disabled-stage");
      else stageBlockSub.classList.add("disabled-stage");
    }
    if (pipeSubMode) pipeSubMode.disabled = !on;
    if (pipeSubStateText) {
      pipeSubStateText.innerText = on ? "已启用 (ASS居中质感)" : "已关闭字幕 (纯净画幅)";
      pipeSubStateText.style.color = on ? "#10b981" : "#94a3b8";
    }
  }

  function updateAllStageUIs() {
    updateInspectStageUI();
    updateVoiceStageUI();
    updateBgmStageUI();
    updateSubStageUI();
  }

  // 绑定预设点击
  document.querySelectorAll(".preset-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const pk = chip.getAttribute("data-preset");
      if (pk) {
        applyPreset(pk, true);
        if (['long_series_30s', 'long_series_60s', 'one_shot_chain', 'ai_commercial'].includes(pk)) {
          if (!currentPlanShots || currentPlanShots.length === 0 || confirm("是否同步载入该模式的【官方推荐影视分镜流】？")) {
            renderTimelineStudio(getDefaultTemplateShots(pk));
          }
        }
      }
    });
  });

  // 绑定开关手动变更 -> 联动更新并自动转为 custom
  if (pipeToggleInspect) {
    pipeToggleInspect.addEventListener("change", () => {
      updateInspectStageUI();
      markCustomPreset();
    });
  }
  if (pipeCheckGridCrop) {
    pipeCheckGridCrop.addEventListener("change", markCustomPreset);
  }
  if (pipeEngineChoice) {
    pipeEngineChoice.addEventListener("change", markCustomPreset);
  }
  if (pipeAspect) {
    pipeAspect.addEventListener("change", markCustomPreset);
  }
  if (pipeDuration) {
    pipeDuration.addEventListener("change", () => {
      if (pipeCustomDurationBox) {
        pipeCustomDurationBox.style.display = (pipeDuration.value === "custom") ? "block" : "none";
      }
      markCustomPreset();
    });
  }
  if (pipeToggleVoice) {
    pipeToggleVoice.addEventListener("change", () => {
      updateVoiceStageUI();
      markCustomPreset();
    });
  }
  if (pipeVoiceName) {
    pipeVoiceName.addEventListener("change", () => {
      updateVoiceStageUI();
      markCustomPreset();
    });
  }
  if (pipeToggleBgm) {
    pipeToggleBgm.addEventListener("change", () => {
      updateBgmStageUI();
      markCustomPreset();
    });
  }
  if (pipeBgmMode) {
    pipeBgmMode.addEventListener("change", () => {
      if (pipeCustomBgmBox) {
        pipeCustomBgmBox.style.display = (pipeBgmMode.value === "custom") ? "block" : "none";
      }
      updateBgmStageUI();
      markCustomPreset();
    });
  }
  if (pipeToggleSub) {
    pipeToggleSub.addEventListener("change", () => {
      updateSubStageUI();
      markCustomPreset();
    });
  }

  // 右侧看板 Tab 切换
  if (tabPipePlan && tabPipeMonitor) {
    tabPipePlan.addEventListener("click", () => {
      tabPipePlan.classList.add("active");
      tabPipeMonitor.classList.remove("active");
      if (pipePanelPlanContent) pipePanelPlanContent.style.display = "flex";
      if (pipePanelMonitorContent) pipePanelMonitorContent.style.display = "none";
    });

    tabPipeMonitor.addEventListener("click", () => {
      tabPipeMonitor.classList.add("active");
      tabPipePlan.classList.remove("active");
      if (pipePanelPlanContent) pipePanelPlanContent.style.display = "none";
      if (pipePanelMonitorContent) pipePanelMonitorContent.style.display = "flex";
    });
  }

  // 示例填充按钮
  if (btnPipeLoadSampleProducts) {
    btnPipeLoadSampleProducts.addEventListener("click", () => {
      if (pipeMatDir) pipeMatDir.value = "E:\\公司素材\\产品实景图\\最新定稿图\\福联产品包装效果图_9款";
      applyPreset("ai_commercial", true);
      doSmartInspect(pipeMatDir.value.trim());
    });
  }

  if (btnPipeLoadSampleStoryboard) {
    btnPipeLoadSampleStoryboard.addEventListener("click", () => {
      if (pipeMatDir) pipeMatDir.value = "E:\\IDM下载\\压缩\\6BA_10秒脚本与首尾帧";
      applyPreset("storyboard_motion", true);
      doSmartInspect(pipeMatDir.value.trim());
    });
  }

  // 3. 双层全景时间轴 Studio 与分镜头微操 (Timeline Studio & Story Flow)
  const CAMERA_MOTIONS = [
    { value: "zoom_in", label: "🔭 缓慢推进 (Zoom In)", icon: "🔭" },
    { value: "zoom_out", label: "🔍 缓慢拉远 (Zoom Out)", icon: "🔍" },
    { value: "pan_left", label: "⬅️ 向左平移 (Pan Left)", icon: "⬅️" },
    { value: "pan_right", label: "➡️ 向右平移 (Pan Right)", icon: "➡️" },
    { value: "crane_up", label: "⬆️ 升降摇臂 (Crane Up)", icon: "⬆️" },
    { value: "tilt_down", label: "⬇️ 俯视下摇 (Tilt Down)", icon: "⬇️" },
    { value: "orbit", label: "🔄 环绕运镜 (Orbit)", icon: "🔄" },
    { value: "static", label: "⏸️ 固定平视 (Static)", icon: "⏸️" }
  ];

  const CONTINUITY_JOINTS = {
    continue: {
      name: "无缝连贯",
      badge: "🟢 无缝连贯 (衔接上一镜)",
      desc: "平滑接续上一镜头的结束画面与运动，实现前后镜头无缝连贯",
      class: "mode-continue"
    },
    anchor: {
      name: "首尾固定",
      badge: "🔵 首尾固定 (首尾帧约束)",
      desc: "严格约束开始和结束两张画面，中间由AI自动生成自然过渡",
      class: "mode-anchor"
    },
    re_anchor: {
      name: "防走样重置",
      badge: "🟡 防走样重置 (校准主体)",
      desc: "重新注入主体核心特征与光影，重置累积误差，防止长视频多镜后人物或物体变形走样",
      class: "mode-re_anchor"
    },
    cut: {
      name: "自然切镜",
      badge: "🟣 自然切镜 (切换新视角)",
      desc: "切换机位视角或景别，主体一致但切换为新的角度或分镜",
      class: "mode-cut"
    },
    extend: {
      name: "智能延长",
      badge: "⚪ 智能延长 (自动向后推演)",
      desc: "以上一镜头结束画面为起点，AI自动向后推演更多后续动作",
      class: "mode-extend"
    }
  };

  let currentContinuityAnchors = {
    subject_anchor: null,
    scene_anchor: "",
    style_anchor: "",
    state_anchor: "",
    locked: true
  };

  let currentBitePrevIdx = -1;
  let currentBiteCurrIdx = -1;
  let currentBiteSelectedMode = "continue";

  function renderContinuityAnchors(anchors) {
    if (!anchors) return;
    currentContinuityAnchors = { ...currentContinuityAnchors, ...anchors };

    if (dnaSubjectInput) {
      dnaSubjectInput.value = currentContinuityAnchors.subject_anchor || "";
    }
    if (dnaSceneInput) {
      dnaSceneInput.value = currentContinuityAnchors.scene_anchor || "";
    }
    if (dnaStyleInput) {
      dnaStyleInput.value = currentContinuityAnchors.style_anchor || "";
    }
    if (dnaStateInput) {
      dnaStateInput.value = currentContinuityAnchors.state_anchor || "";
    }
    if (pipeDnaLockToggle) {
      pipeDnaLockToggle.checked = currentContinuityAnchors.locked !== false;
    }

    if (dnaSubjectStatus) {
      dnaSubjectStatus.textContent = currentContinuityAnchors.subject_anchor ? "已锁定" : "未设置";
    }
    if (dnaSubjectThumb) {
      const subVal = currentContinuityAnchors.subject_anchor;
      if (subVal && (subVal.startsWith("http") || subVal.includes("/") || subVal.includes("\\"))) {
        const previewSrc = subVal.startsWith("http") ? subVal : `/api/pipeline/file-preview?path=${encodeURIComponent(subVal)}`;
        dnaSubjectThumb.innerHTML = `<img src="${previewSrc}" alt="DNA" onerror="this.parentElement.innerHTML='<span>参考图</span>'">`;
      } else if (currentPlanShots && currentPlanShots[0] && currentPlanShots[0].image_path) {
        const previewSrc = `/api/pipeline/file-preview?path=${encodeURIComponent(currentPlanShots[0].image_path)}`;
        dnaSubjectThumb.innerHTML = `<img src="${previewSrc}" alt="DNA" onerror="this.parentElement.innerHTML='<span>首镜</span>'">`;
      } else {
        dnaSubjectThumb.innerHTML = `<span>无参考图</span>`;
      }
    }
  }

  function syncContinuityAnchorsFromDOM() {
    if (dnaSubjectInput) currentContinuityAnchors.subject_anchor = dnaSubjectInput.value.trim() || null;
    if (dnaSceneInput) currentContinuityAnchors.scene_anchor = dnaSceneInput.value.trim() || null;
    if (dnaStyleInput) currentContinuityAnchors.style_anchor = dnaStyleInput.value.trim() || null;
    if (dnaStateInput) currentContinuityAnchors.state_anchor = dnaStateInput.value.trim() || null;
    if (pipeDnaLockToggle) currentContinuityAnchors.locked = pipeDnaLockToggle.checked;
  }

  
  function getDefaultTemplateShots(mode = "long_series_30s") {
    if (mode === "long_series_60s") {
      return [
        {
          id: "shot_01",
          name: "镜头 1 · 宏观大远景 (环境建置)",
          image_path: "",
          image_name: "场景环境全貌",
          duration: 7.0,
          voice_text: "清晨第一缕阳光穿透薄雾，整片生机盎然的原野在晨光中逐渐苏醒。",
          subtitle_text: "清晨第一缕阳光穿透薄雾，整片生机盎然的原野在晨光中逐渐苏醒。",
          camera_motion: "zoom_in",
          continuity: "cut",
          re_anchor: false
        },
        {
          id: "shot_02",
          name: "镜头 2 · 中景推移 (主体入画)",
          image_path: "",
          image_name: "主体位置与形态",
          duration: 7.5,
          voice_text: "镜头顺着光影与清风平滑向前推移，核心主体在自然动势中清晰显现。",
          subtitle_text: "镜头顺着光影与清风平滑向前推移，核心主体在自然动势中清晰显现。",
          camera_motion: "pan_left",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_03",
          name: "镜头 3 · 环绕微距 (材质肌理)",
          image_path: "",
          image_name: "精细微观细节",
          duration: 8.0,
          voice_text: "环绕微距视角捕捉细微的光泽与表面质感，每一处线条都蕴藏着匠心工艺。",
          subtitle_text: "环绕微距视角捕捉细微的光泽与表面质感，每一处线条都蕴藏着匠心工艺。",
          camera_motion: "orbit_cw",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_04",
          name: "镜头 4 · 动态交互 (能量激发)",
          image_path: "",
          image_name: "功能作用爆发",
          duration: 7.5,
          voice_text: "粒子光晕在空间中自然弥散，活性成分全面渗透，带来澎湃的赋能变化。",
          subtitle_text: "粒子光晕在空间中自然弥散，活性成分全面渗透，带来澎湃的赋能变化。",
          camera_motion: "crane_up",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_05",
          name: "镜头 5 · 空间转换 (防漂移重锚)",
          image_path: "",
          image_name: "场景升维过渡",
          duration: 7.5,
          voice_text: "镜头瞬息流转至开阔的现代科技实验空间，纯净视效精准再现核心价值。",
          subtitle_text: "镜头瞬息流转至开阔的现代科技实验空间，纯净视效精准再现核心价值。",
          camera_motion: "pan_right",
          continuity: "re_anchor",
          re_anchor: true
        },
        {
          id: "shot_06",
          name: "镜头 6 · 仰角仰望 (品质升华)",
          image_path: "",
          image_name: "主体仰视光影",
          duration: 7.5,
          voice_text: "仰角光束倾泻而下，挺拔轮廓在金色光晕衬托下尽显卓越不凡。",
          subtitle_text: "仰角光束倾泻而下，挺拔轮廓在金色光晕衬托下尽显卓越不凡。",
          camera_motion: "tilt_down",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_07",
          name: "镜头 7 · 广角环景 (生态交融)",
          image_path: "",
          image_name: "环境与主体全景",
          duration: 7.5,
          voice_text: "视界再度延展，主体与天地自然和谐共生，交织出充满希望的未来图景。",
          subtitle_text: "视界再度延展，主体与天地自然和谐共生，交织出充满希望的未来图景。",
          camera_motion: "orbit_ccw",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_08",
          name: "镜头 8 · 升腾拉远 (定格终章)",
          image_path: "",
          image_name: "品牌标语终章定格",
          duration: 7.5,
          voice_text: "视线徐徐升腾拉远，在壮阔晨曦中凝炼定格，成就专业信赖的典范。",
          subtitle_text: "视线徐徐升腾拉远，在壮阔晨曦中凝炼定格，成就专业信赖的典范。",
          camera_motion: "zoom_out",
          continuity: "continue",
          re_anchor: false
        }
      ];
    } else if (mode === "one_shot_chain") {
      return [
        {
          id: "shot_01",
          name: "镜头 1 · 空间穿梭 (一镜到底入画)",
          image_path: "",
          image_name: "长镜头起点",
          duration: 7.5,
          voice_text: "摄影机如行云流水般穿梭推进，无断点探索空间的每一寸纵深。",
          subtitle_text: "摄影机如行云流水般穿梭推进，无断点探索空间的每一寸纵深。",
          camera_motion: "zoom_in",
          continuity: "cut",
          re_anchor: false
        },
        {
          id: "shot_02",
          name: "镜头 2 · 360°平滑环绕 (无缝接力)",
          image_path: "",
          image_name: "环绕运镜段",
          duration: 7.5,
          voice_text: "弧形轨道无缝咬合旋转，光影随角度变幻流淌，主体形态完全锁定。",
          subtitle_text: "弧形轨道无缝咬合旋转，光影随角度变幻流淌，主体形态完全锁定。",
          camera_motion: "orbit_cw",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_03",
          name: "镜头 3 · 贴地滑行升腾 (视角变换)",
          image_path: "",
          image_name: "低机位升腾",
          duration: 7.5,
          voice_text: "镜头顺势贴近地面滑行后垂直升腾，视角切换自然流畅，不着痕迹。",
          subtitle_text: "镜头顺势贴近地面滑行后垂直升腾，视角切换自然流畅，不着痕迹。",
          camera_motion: "crane_up",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_04",
          name: "镜头 4 · 平缓后撤定格 (完美收束)",
          image_path: "",
          image_name: "长镜头终点定格",
          duration: 7.5,
          voice_text: "最终平稳拉升至全景构图，首尾如一，达成一气呵成的连续视觉体验。",
          subtitle_text: "最终平稳拉升至全景构图，首尾如一，达成一气呵成的连续视觉体验。",
          camera_motion: "zoom_out",
          continuity: "continue",
          re_anchor: false
        }
      ];
    } else if (mode === "ai_commercial") {
      return [
        {
          id: "shot_01",
          name: "镜头 1 · 破题吸睛 (光芒绽放)",
          image_path: "",
          image_name: "产品破题亮相",
          duration: 4.5,
          voice_text: "以自然科技之名，重新定义高品质专业标杆。",
          subtitle_text: "以自然科技之名，重新定义高品质专业标杆。",
          camera_motion: "zoom_in",
          continuity: "cut",
          re_anchor: false
        },
        {
          id: "shot_02",
          name: "镜头 2 · 核心质感 (微距特写)",
          image_path: "",
          image_name: "包装与工艺质感",
          duration: 5.5,
          voice_text: "严谨选材，严控配比，每一处细节皆为卓越而生。",
          subtitle_text: "严谨选材，严控配比，每一处细节皆为卓越而生。",
          camera_motion: "orbit_cw",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_03",
          name: "镜头 3 · 实景应用 (效能迸发)",
          image_path: "",
          image_name: "田间与实地应用",
          duration: 5.0,
          voice_text: "赋能丰饶大地，见证从根系到果实的每一次蜕变跃迁。",
          subtitle_text: "赋能丰饶大地，见证从根系到果实的每一次蜕变跃迁。",
          camera_motion: "pan_right",
          continuity: "continue",
          re_anchor: false
        },
        {
          id: "shot_04",
          name: "镜头 4 · 品牌定格 (号召信任)",
          image_path: "",
          image_name: "品牌LOGO与标语定格",
          duration: 5.0,
          voice_text: "携手同行，共创现代农业绿色可持续的丰收未来。",
          subtitle_text: "携手同行，共创现代农业绿色可持续的丰收未来。",
          camera_motion: "zoom_out",
          continuity: "re_anchor",
          re_anchor: true
        }
      ];
    }

    // 默认: long_series_30s (4镜头 · 30秒连续短片)
    return [
      {
        id: "shot_01",
        name: "镜头 1 · 宏观远景 (建置环境)",
        image_path: "",
        image_name: "清晨原野全景",
        duration: 7.0,
        voice_text: "清晨第一缕阳光洒落在原野上，天地间苏醒着磅礴生机。",
        subtitle_text: "清晨第一缕阳光洒落在原野上，天地间苏醒着磅礴生机。",
        camera_motion: "zoom_in",
        continuity: "cut",
        re_anchor: false
      },
      {
        id: "shot_02",
        name: "镜头 2 · 中景推移 (主体入画)",
        image_path: "",
        image_name: "主体位置与形态",
        duration: 8.0,
        voice_text: "镜头顺着光影平滑推移，核心形态在自然流动中清晰显现。",
        subtitle_text: "镜头顺着光影平滑推移，核心形态在自然流动中清晰显现。",
        camera_motion: "pan_left",
        continuity: "continue",
        re_anchor: false
      },
      {
        id: "shot_03",
        name: "镜头 3 · 环绕特写 (细节纹理)",
        image_path: "",
        image_name: "微距材质纹理",
        duration: 7.5,
        voice_text: "环绕微距视角捕捉细微纹理，每一处精雕细琢都凝结着极致工艺。",
        subtitle_text: "环绕微距视角捕捉细微纹理，每一处精雕细琢都凝结着极致工艺。",
        camera_motion: "orbit_cw",
        continuity: "continue",
        re_anchor: false
      },
      {
        id: "shot_04",
        name: "镜头 4 · 宏大全景 (升空定格)",
        image_path: "",
        image_name: "大景别定格收束",
        duration: 7.5,
        voice_text: "视线缓缓拉远升腾，在辽阔天地中定格震撼瞬间。",
        subtitle_text: "视线缓缓拉远升腾，在辽阔天地中定格震撼瞬间。",
        camera_motion: "zoom_out",
        continuity: "continue",
        re_anchor: false
      }
    ];
  }

  function renderTimelineStudio(shots) {
    currentPlanShots = shots || [];
    const container = pipeStoryFlowTrack || pipeShotsList;
    if (!container) return;
    container.innerHTML = "";

    const totalDur = currentPlanShots.reduce((acc, s) => acc + (parseFloat(s.duration) || 3.0), 0);

    if (pipeShotsCount) {
      pipeShotsCount.textContent = `(${currentPlanShots.length} 镜头 · ${totalDur.toFixed(1)}s)`;
    }

    if (!currentPlanShots || currentPlanShots.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; color: #94a3b8; font-size: 13px; padding: 48px 20px; width: 100%; background: rgba(15,23,42,0.4); border: 1px dashed rgba(255,255,255,0.1); border-radius: 8px;">
          <div style="font-size: 28px; margin-bottom: 8px;">🎬</div>
          <div style="font-weight: 600; color: #e2e8f0; margin-bottom: 4px;">时间轴空态待命中</div>
          <div style="font-size: 12px; color: #64748b;">
            在左侧输入你的创意想法或选择预设，镜头将自动拆解并在此呈现；也可随时点击上方【➕ 加镜头】手动添加。
          </div>
        </div>
      `;
      renderTimelineRuler([]);
      return;
    }

    let consecutiveContinueCount = 0;

    currentPlanShots.forEach((s, idx) => {
      const isFirst = (idx === 0);
      const isLast = (idx === currentPlanShots.length - 1);
      const shotDur = parseFloat(s.duration) || 3.0;
      const shotMotion = s.camera_motion || s.motion || (idx % 2 === 0 ? "zoom_in" : "pan_left");
      s.camera_motion = shotMotion;
      const motionObj = CAMERA_MOTIONS.find(m => m.value === shotMotion) || CAMERA_MOTIONS[0];

      let continuity = s.continuity || (isFirst ? "cut" : "continue");
      if (s.re_anchor) {
        continuity = "re_anchor";
      }
      s.continuity = continuity;

      // 连续接力漂移预警检测
      if (!isFirst) {
        if (continuity === "continue") {
          consecutiveContinueCount++;
        } else {
          consecutiveContinueCount = 0;
        }

        const showDriftWarning = consecutiveContinueCount >= 2;

        // 插入镜头间互锁咬合胶囊
        const capsule = document.createElement("div");
        capsule.className = "joint-connector-capsule";
        capsule.setAttribute("data-joint-index", idx);
        capsule.setAttribute("title", `点击对比镜头 #${idx} 与 #${idx + 1} 双窗咬合及设置衔接模态`);

        const jointInfo = CONTINUITY_JOINTS[continuity] || CONTINUITY_JOINTS.continue;

        capsule.innerHTML = `
          <div class="joint-capsule-line"></div>
          ${showDriftWarning ? `<div class="drift-warning-pulse" title="已连续 ${consecutiveContinueCount} 镜接力，形态可能发生漂移，建议设置【防漂移重锚】重设主体DNA">⚠️ 漂移预警</div>` : ''}
          <div class="joint-pill ${jointInfo.class}">
            <span>${jointInfo.badge.split(' ')[0]}</span>
            <span style="font-size: 8.5px;">${jointInfo.name}</span>
          </div>
        `;

        capsule.addEventListener("click", () => {
          openBiteDrawerModal(idx - 1, idx);
        });

        container.appendChild(capsule);
      } else {
        consecutiveContinueCount = 0;
      }

      // 创建胶卷卡片 (Film Card)
      const card = document.createElement("div");
      card.className = "shot-film-card";
      card.setAttribute("data-shot-index", idx);
      card.id = `shot-film-card-${idx}`;

      const thumbUrl = s.preview_url || (s.image_path ? `/api/pipeline/file-preview?path=${encodeURIComponent(s.image_path)}` : '');
      const shotTitle = s.name || `镜头 ${idx + 1}`;
      const imgName = s.image_name || (s.image_path ? s.image_path.split(/[\\/]/).pop() : "自定义画面");

      card.innerHTML = `
        <div class="film-sprockets-top"></div>
        <div class="film-thumb-box" title="${escapeHtml(s.image_path || '无本地路径')}">
          ${thumbUrl ? `<img src="${thumbUrl}" alt="Shot ${idx + 1}" onerror="this.style.opacity='0.25'">` : `<span style="font-size:11px;color:#64748b;">🎨 待生成首帧</span>`}
          <span class="film-shot-idx">#${idx + 1}</span>
          <span class="film-dur-badge">${shotDur.toFixed(1)}s</span>
          <span class="camera-motion-badge" data-index="${idx}" title="点击轮换运镜动力学">
            ${motionObj.icon} ${motionObj.label.split(' ')[1] || motionObj.value}
          </span>
          ${s.re_anchor ? `<span class="reanchor-badge">🎯 防走样</span>` : ''}
        </div>
        <div class="film-card-body">
          <div class="film-shot-title-row">
            <span class="film-shot-title" title="${escapeHtml(shotTitle + ' - ' + imgName)}">
              ${escapeHtml(shotTitle)} · ${escapeHtml(imgName)}
            </span>
            <div class="film-shot-actions">
              <button class="film-action-mini-btn shot-btn-reanchor ${s.re_anchor ? 'active' : ''}" data-index="${idx}" title="${s.re_anchor ? '已开启防走样重置（本镜注回核心特征）' : '设为防走样校准点'}">🎯</button>
              <button class="film-action-mini-btn shot-btn-up" data-index="${idx}" title="左移镜头" ${isFirst ? "disabled style='opacity:0.3;cursor:not-allowed;'" : ""}>◀</button>
              <button class="film-action-mini-btn shot-btn-down" data-index="${idx}" title="右移镜头" ${isLast ? "disabled style='opacity:0.3;cursor:not-allowed;'" : ""}>▶</button>
              <button class="film-action-mini-btn btn-del shot-btn-del" data-index="${idx}" title="删除镜头">✕</button>
            </div>
          </div>
          <textarea class="film-prompt-input" data-index="${idx}" placeholder="输入镜头画面描述/台词解说...">${escapeHtml(s.voice_text || s.subtitle_text || '')}</textarea>
          <div class="film-controls-row">
            <div class="film-dur-control">
              <span>时长:</span>
              <input type="number" class="film-dur-input" data-index="${idx}" value="${shotDur}" min="0.5" max="60" step="0.5">
              <span>s</span>
            </div>
            <select class="film-motion-select" data-index="${idx}" style="background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.1);color:#38bdf8;font-size:10px;border-radius:3px;padding:1px 4px;outline:none;">
              ${CAMERA_MOTIONS.map(m => `<option value="${m.value}" ${m.value === shotMotion ? 'selected' : ''}>${m.label}</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="film-sprockets-bottom"></div>
      `;

      container.appendChild(card);
    });

    bindTimelineStudioEvents();
    renderTimelineRuler(currentPlanShots);
  }

  function renderTimelineRuler(shots) {
    if (!pipeRulerTicks || !pipeRulerVideoTrack) return;
    pipeRulerTicks.innerHTML = "";
    pipeRulerVideoTrack.innerHTML = "";

    const totalDur = shots.reduce((acc, s) => acc + (parseFloat(s.duration) || 3.0), 0);
    const rulerDur = Math.max(10.0, Math.ceil(totalDur / 5.0) * 5.0);

    if (rulerTotalLabel) {
      rulerTotalLabel.textContent = `总时长: ${totalDur.toFixed(1)}s / ${rulerDur.toFixed(1)}s`;
    }

    const step = rulerDur <= 20 ? 2.5 : 5.0;
    for (let t = 0; t <= rulerDur; t += step) {
      const pct = (t / rulerDur) * 100;
      const tick = document.createElement("div");
      tick.className = "ruler-tick";
      tick.style.left = `${pct}%`;
      tick.textContent = `${t}s`;
      pipeRulerTicks.appendChild(tick);
    }

    const trackColors = [
      "linear-gradient(90deg, #1e40af, #2563eb)",
      "linear-gradient(90deg, #065f46, #059669)",
      "linear-gradient(90deg, #581c87, #7c3aed)",
      "linear-gradient(90deg, #78350f, #d97706)",
      "linear-gradient(90deg, #155e75, #0891b2)",
      "linear-gradient(90deg, #831843, #db2777)"
    ];

    shots.forEach((s, idx) => {
      const dur = parseFloat(s.duration) || 3.0;
      const widthPct = (dur / rulerDur) * 100;
      const seg = document.createElement("div");
      seg.className = "ruler-shot-segment";
      seg.style.width = `${widthPct}%`;
      seg.style.background = trackColors[idx % trackColors.length];
      seg.setAttribute("data-index", idx);
      seg.title = `#${idx + 1} ${s.name || '镜头'} (${dur.toFixed(1)}s) - 点击在故事流定位`;
      seg.textContent = `#${idx + 1} (${dur.toFixed(1)}s)`;

      seg.addEventListener("click", () => {
        const card = document.getElementById(`shot-film-card-${idx}`);
        if (card) {
          card.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
          document.querySelectorAll('.shot-film-card').forEach(c => c.classList.remove('active-selected'));
          card.classList.add('active-selected');
        }
        document.querySelectorAll('.ruler-shot-segment').forEach(sg => sg.classList.remove('active-segment'));
        seg.classList.add('active-segment');
      });

      pipeRulerVideoTrack.appendChild(seg);
    });
  }

  function bindTimelineStudioEvents() {
    const container = pipeStoryFlowTrack || pipeShotsList;
    if (!container) return;

    // 提示词输入绑定
    container.querySelectorAll(".film-prompt-input").forEach(ta => {
      ta.addEventListener("input", (e) => {
        const idx = parseInt(e.target.getAttribute("data-index"), 10);
        if (currentPlanShots[idx]) {
          currentPlanShots[idx].voice_text = e.target.value;
          currentPlanShots[idx].subtitle_text = e.target.value;
        }
      });
    });

    // 时长调整绑定
    container.querySelectorAll(".film-dur-input").forEach(inp => {
      inp.addEventListener("change", (e) => {
        const idx = parseInt(e.target.getAttribute("data-index"), 10);
        if (currentPlanShots[idx]) {
          const val = parseFloat(e.target.value) || 3.0;
          currentPlanShots[idx].duration = val;
          renderTimelineRuler(currentPlanShots);
          const totalDur = currentPlanShots.reduce((acc, s) => acc + (parseFloat(s.duration) || 3.0), 0);
          if (pipeShotsCount) pipeShotsCount.textContent = `(${currentPlanShots.length} 镜头 · ${totalDur.toFixed(1)}s)`;
          // 更新卡片右上角徽标
          const card = document.getElementById(`shot-film-card-${idx}`);
          if (card) {
            const b = card.querySelector(".film-dur-badge");
            if (b) b.textContent = `${val.toFixed(1)}s`;
          }
        }
      });
    });

    // 运镜下拉选择
    container.querySelectorAll(".film-motion-select").forEach(sel => {
      sel.addEventListener("change", (e) => {
        const idx = parseInt(e.target.getAttribute("data-index"), 10);
        if (currentPlanShots[idx]) {
          currentPlanShots[idx].camera_motion = e.target.value;
          currentPlanShots[idx].motion = e.target.value;
          const motionObj = CAMERA_MOTIONS.find(m => m.value === e.target.value) || CAMERA_MOTIONS[0];
          const card = document.getElementById(`shot-film-card-${idx}`);
          if (card) {
            const badge = card.querySelector(".camera-motion-badge");
            if (badge) badge.innerHTML = `${motionObj.icon} ${motionObj.label.split(' ')[1] || motionObj.value}`;
          }
        }
      });
    });

    // 点击运镜徽标快捷轮换运镜
    container.querySelectorAll(".camera-motion-badge").forEach(badge => {
      badge.addEventListener("click", (e) => {
        const idx = parseInt(e.currentTarget.getAttribute("data-index"), 10);
        if (currentPlanShots[idx]) {
          const cur = currentPlanShots[idx].camera_motion || "zoom_in";
          const curIdx = CAMERA_MOTIONS.findIndex(m => m.value === cur);
          const nextMotion = CAMERA_MOTIONS[(curIdx + 1) % CAMERA_MOTIONS.length];
          currentPlanShots[idx].camera_motion = nextMotion.value;
          currentPlanShots[idx].motion = nextMotion.value;
          badge.innerHTML = `${nextMotion.icon} ${nextMotion.label.split(' ')[1] || nextMotion.value}`;
          const card = document.getElementById(`shot-film-card-${idx}`);
          if (card) {
            const sel = card.querySelector(".film-motion-select");
            if (sel) sel.value = nextMotion.value;
          }
        }
      });
    });

    // 防漂移重锚点切换
    container.querySelectorAll(".shot-btn-reanchor").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.currentTarget.getAttribute("data-index"), 10);
        if (currentPlanShots[idx]) {
          syncCurrentShotsFromDOM();
          currentPlanShots[idx].re_anchor = !currentPlanShots[idx].re_anchor;
          if (currentPlanShots[idx].re_anchor) {
            currentPlanShots[idx].continuity = "re_anchor";
          } else {
            currentPlanShots[idx].continuity = idx === 0 ? "cut" : "continue";
          }
          renderTimelineStudio(currentPlanShots);
        }
      });
    });

    // 左移镜头
    container.querySelectorAll(".shot-btn-up").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.currentTarget.getAttribute("data-index"), 10);
        if (idx > 0) {
          syncCurrentShotsFromDOM();
          const temp = currentPlanShots[idx];
          currentPlanShots[idx] = currentPlanShots[idx - 1];
          currentPlanShots[idx - 1] = temp;
          renderTimelineStudio(currentPlanShots);
        }
      });
    });

    // 右移镜头
    container.querySelectorAll(".shot-btn-down").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.currentTarget.getAttribute("data-index"), 10);
        if (idx < currentPlanShots.length - 1) {
          syncCurrentShotsFromDOM();
          const temp = currentPlanShots[idx];
          currentPlanShots[idx] = currentPlanShots[idx + 1];
          currentPlanShots[idx + 1] = temp;
          renderTimelineStudio(currentPlanShots);
        }
      });
    });

    // 删除镜头
    container.querySelectorAll(".shot-btn-del").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.currentTarget.getAttribute("data-index"), 10);
        syncCurrentShotsFromDOM();
        currentPlanShots.splice(idx, 1);
        renderTimelineStudio(currentPlanShots);
      });
    });
  }

  function syncCurrentShotsFromDOM() {
    const container = pipeStoryFlowTrack || pipeShotsList;
    if (!container) return;
    const durInputs = container.querySelectorAll(".film-dur-input");
    const txtInputs = container.querySelectorAll(".film-prompt-input");
    const motionSelects = container.querySelectorAll(".film-motion-select");

    durInputs.forEach(inp => {
      const i = parseInt(inp.getAttribute("data-index"), 10);
      if (currentPlanShots[i]) {
        currentPlanShots[i].duration = parseFloat(inp.value) || 3.0;
      }
    });
    txtInputs.forEach(inp => {
      const i = parseInt(inp.getAttribute("data-index"), 10);
      if (currentPlanShots[i]) {
        currentPlanShots[i].voice_text = inp.value;
        currentPlanShots[i].subtitle_text = inp.value;
      }
    });
    motionSelects.forEach(sel => {
      const i = parseInt(sel.getAttribute("data-index"), 10);
      if (currentPlanShots[i]) {
        currentPlanShots[i].camera_motion = sel.value;
        currentPlanShots[i].motion = sel.value;
      }
    });
  }

  // 保持向后兼容的别名
  function renderShotsPlan(shots) {
    renderTimelineStudio(shots);
  }

  // 模态框 1：双窗咬合对比抽屉 (Joint Bite Inspection)
  function openBiteDrawerModal(prevIdx, currIdx) {
    currentBitePrevIdx = prevIdx;
    currentBiteCurrIdx = currIdx;
    const prevShot = currentPlanShots[prevIdx];
    const currShot = currentPlanShots[currIdx];
    if (!prevShot || !currShot) return;

    if (bitePrevLabel) bitePrevLabel.textContent = `上一镜 #${prevIdx + 1} 尾帧出点 (${prevShot.name || 'Shot'})`;
    if (biteCurrLabel) biteCurrLabel.textContent = `本镜 #${currIdx + 1} 起点入帧 (${currShot.name || 'Shot'})`;

    const prevThumb = prevShot.preview_url || (prevShot.image_path ? `/api/pipeline/file-preview?path=${encodeURIComponent(prevShot.image_path)}` : '');
    const currThumb = currShot.preview_url || (currShot.image_path ? `/api/pipeline/file-preview?path=${encodeURIComponent(currShot.image_path)}` : '');

    if (bitePrevImg) bitePrevImg.src = prevThumb;
    if (biteCurrImg) biteCurrImg.src = currThumb;

    currentBiteSelectedMode = currShot.continuity || "continue";
    updateBiteDrawerModeUI(currentBiteSelectedMode);

    if (pipeBiteDrawerModal) pipeBiteDrawerModal.style.display = "flex";
  }

  function updateBiteDrawerModeUI(mode) {
    currentBiteSelectedMode = mode;
    const jointInfo = CONTINUITY_JOINTS[mode] || CONTINUITY_JOINTS.continue;
    if (biteJointBadge) {
      biteJointBadge.textContent = jointInfo.badge;
      biteJointBadge.className = `bite-joint-badge ${jointInfo.class}`;
    }
    if (biteJointDesc) {
      biteJointDesc.textContent = jointInfo.desc;
    }
    document.querySelectorAll(".bite-mode-btn").forEach(btn => {
      if (btn.getAttribute("data-mode") === mode) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  // 模态框 2：Animatic 极速动态分镜预演
  async function triggerAnimaticPreview() {
    syncCurrentShotsFromDOM();
    syncContinuityAnchorsFromDOM();

    if (!currentPlanShots || currentPlanShots.length === 0) {
      alert("请先规划或添加分镜头素材后再生成预演！");
      return;
    }

    if (pipeAnimaticModal) pipeAnimaticModal.style.display = "flex";
    if (animaticLoadingSpinner) animaticLoadingSpinner.style.display = "block";
    if (animaticVideoPlayer) {
      animaticVideoPlayer.style.display = "none";
      animaticVideoPlayer.pause();
      animaticVideoPlayer.src = "";
    }
    if (animaticModalFooter) animaticModalFooter.style.display = "none";

    try {
      const payload = {
        material_dir: pipeMatDir ? pipeMatDir.value.trim() : null,
        shots_override: currentPlanShots.map((s, idx) => ({
          id: s.id || `shot_${String(idx + 1).padStart(2, "0")}`,
          name: s.name || `镜头 ${idx + 1}`,
          image_path: s.image_path || "",
          voice_text: s.voice_text || "",
          subtitle_text: s.subtitle_text || s.voice_text || "",
          duration: parseFloat(s.duration) || 3.0,
          motion: s.camera_motion || s.motion || "zoom_in",
          camera_motion: s.camera_motion || s.motion || "zoom_in",
          continuity: s.continuity || "continue",
          re_anchor: !!s.re_anchor
        })),
        continuity_anchors: currentContinuityAnchors,
        aspect_ratio: pipeAspect ? pipeAspect.value : "16:9",
        duration_mode: "auto",
        total_duration: currentPlanShots.reduce((a, s) => a + (parseFloat(s.duration) || 3.0), 0),
        voice_mode: (pipeToggleVoice && pipeToggleVoice.checked) ? "edge_tts" : "mute",
        voice_name: pipeVoiceName ? pipeVoiceName.value : "zh-CN-YunxiNeural",
        bgm_mode: (pipeToggleBgm && pipeToggleBgm.checked) ? (pipeBgmMode ? pipeBgmMode.value : "auto") : "mute",
        bgm_path: (pipeBgmPath && pipeBgmMode && pipeBgmMode.value === "custom") ? pipeBgmPath.value.trim() : null
      };

      const res = await fetch("/api/pipeline/animatic-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "动态预演启动失败");
      }

      const jobId = data.job_id;
      let pollCount = 0;
      const pollTimer = setInterval(async () => {
        pollCount++;
        try {
          const sRes = await fetch(`/api/pipeline/job/${encodeURIComponent(jobId)}`);
          if (!sRes.ok) return;
          const sData = await sRes.json();
          const job = sData.job;
          if (!job) return;

          if (job.status === "success" || job.status === "done" || job.status === "completed") {
            clearInterval(pollTimer);
            if (animaticLoadingSpinner) animaticLoadingSpinner.style.display = "none";
            if (animaticVideoPlayer) {
              animaticVideoPlayer.src = job.video_url || `/api/pipeline/download?job_id=${encodeURIComponent(jobId)}`;
              animaticVideoPlayer.style.display = "block";
              animaticVideoPlayer.play().catch(() => {});
            }
            if (animaticModalFooter) animaticModalFooter.style.display = "flex";
          } else if (job.status === "failed") {
            clearInterval(pollTimer);
            if (animaticLoadingSpinner) {
              animaticLoadingSpinner.innerHTML = `
                <div style="color:#ef4444;font-size:13px;font-weight:700;">❌ 预演生成失败</div>
                <div style="color:#94a3b8;font-size:11px;margin-top:6px;">${escapeHtml(job.error || '未知错误')}</div>
              `;
            }
          } else if (job.status === "running" || job.status === "processing") {
            if (animaticLoadingSpinner) {
              const pct = job.progress || 0;
              const step = job.step || "渲染中...";
              animaticLoadingSpinner.innerHTML = `
                <div class="spinner" style="margin: 0 auto 12px auto;"></div>
                <div style="color:#f8fafc; font-size:13px; font-weight:700;">动态分镜预演合成中 (${pct}%)</div>
                <div style="color:#94a3b8; font-size:11px; margin-top:6px;">${escapeHtml(step)}</div>
              `;
            }
          }
        } catch (e) {
          console.warn("Poll animatic failed", e);
        }
        if (pollCount > 120) {
          clearInterval(pollTimer);
        }
      }, 1000);

    } catch (err) {
      if (animaticLoadingSpinner) {
        animaticLoadingSpinner.innerHTML = `
          <div style="color:#ef4444;font-size:13px;font-weight:700;">❌ 预演启动失败</div>
          <div style="color:#94a3b8;font-size:11px;margin-top:6px;">${escapeHtml(err.message)}</div>
        `;
      }
    }
  }

  // 模态框 3：Job Spec 导出与导入
  async function triggerExportSpec() {
    syncCurrentShotsFromDOM();
    syncContinuityAnchorsFromDOM();

    if (!currentPlanShots || currentPlanShots.length === 0) {
      alert("当前没有可导出的镜头规划！");
      return;
    }

    try {
      const payload = {
        material_dir: pipeMatDir ? pipeMatDir.value.trim() : null,
        shots_override: currentPlanShots.map((s, idx) => ({
          id: s.id || `shot_${String(idx + 1).padStart(2, "0")}`,
          name: s.name || `镜头 ${idx + 1}`,
          image_path: s.image_path || "",
          voice_text: s.voice_text || "",
          subtitle_text: s.subtitle_text || s.voice_text || "",
          duration: parseFloat(s.duration) || 3.0,
          motion: s.camera_motion || s.motion || "zoom_in",
          camera_motion: s.camera_motion || s.motion || "zoom_in",
          continuity: s.continuity || "continue",
          re_anchor: !!s.re_anchor
        })),
        continuity_anchors: currentContinuityAnchors,
        aspect_ratio: pipeAspect ? pipeAspect.value : "16:9"
      };

      const res = await fetch("/api/pipeline/job-spec/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "导出失败");

      if (pipeSpecJsonTextarea) {
        pipeSpecJsonTextarea.value = JSON.stringify(data.job_spec, null, 2);
      }
      if (pipeSpecModal) pipeSpecModal.style.display = "flex";

    } catch (e) {
      alert("导出失败: " + e.message);
    }
  }

  async function triggerApplySpecJson() {
    if (!pipeSpecJsonTextarea) return;
    const raw = pipeSpecJsonTextarea.value.trim();
    if (!raw) {
      alert("请输入有效的 Job Spec JSON！");
      return;
    }

    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      alert("JSON 语法解析错误，请检查格式！");
      return;
    }

    try {
      const res = await fetch("/api/pipeline/job-spec/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_spec: parsed })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "校验失败");

      if (data.missing_assets && data.missing_assets.length > 0) {
        alert("⚠️ 提示: 检测到以下素材在本地不存在:\n" + data.missing_assets.slice(0, 3).join("\n") + (data.missing_assets.length > 3 ? `\n...等共${data.missing_assets.length}个文件` : ''));
      }

      const restoredShots = [];
      const vTrack = (data.spec && data.spec.tracks && data.spec.tracks.video_track) || [];
      vTrack.forEach((s, idx) => {
        restoredShots.push({
          id: s.id || `shot_${String(idx + 1).padStart(2, "0")}`,
          name: s.name || `镜头 ${idx + 1}`,
          image_path: s.in_frame || (s.visual ? s.visual.start_image : ""),
          image_name: s.in_frame ? s.in_frame.split(/[\\/]/).pop() : `镜头 ${idx + 1}`,
          duration: s.duration || 3.0,
          voice_text: s.narration ? s.narration.text : "",
          subtitle_text: s.narration ? s.narration.text : "",
          camera_motion: (s.visual && s.visual.camera_motion) || "zoom_in",
          continuity: s.continuity || "continue",
          re_anchor: !!(s.visual && s.visual.re_anchor),
          preview_url: `/api/pipeline/file-preview?path=${encodeURIComponent(s.in_frame || '')}`
        });
      });

      if (data.continuity_anchors) {
        renderContinuityAnchors(data.continuity_anchors);
      }

      renderTimelineStudio(restoredShots);
      if (pipeSpecModal) pipeSpecModal.style.display = "none";
      alert(`✅ 成功应用 Job Spec！已载入 ${restoredShots.length} 个镜头方案`);

    } catch (e) {
      alert("Job Spec 校验与应用失败: " + e.message);
    }
  }

  // 绑定 Studio 工具栏与模态框事件
  if (btnPipeAnimaticPreview) {
    btnPipeAnimaticPreview.addEventListener("click", triggerAnimaticPreview);
  }
  if (btnPipeExportSpec) {
    btnPipeExportSpec.addEventListener("click", triggerExportSpec);
  }
  if (btnPipeImportSpec) {
    btnPipeImportSpec.addEventListener("click", () => {
      if (pipeSpecJsonTextarea) pipeSpecJsonTextarea.value = "";
      if (pipeSpecModal) pipeSpecModal.style.display = "flex";
    });
  }

  if (btnCloseSpecModal) {
    btnCloseSpecModal.addEventListener("click", () => {
      if (pipeSpecModal) pipeSpecModal.style.display = "none";
    });
  }
  if (btnCopySpecJson) {
    btnCopySpecJson.addEventListener("click", () => {
      if (pipeSpecJsonTextarea && pipeSpecJsonTextarea.value) {
        navigator.clipboard.writeText(pipeSpecJsonTextarea.value).then(() => {
          btnCopySpecJson.textContent = "✅ 已复制到剪贴板";
          setTimeout(() => { btnCopySpecJson.textContent = "📑 复制到剪贴板"; }, 2000);
        });
      }
    });
  }
  if (btnApplySpecJson) {
    btnApplySpecJson.addEventListener("click", triggerApplySpecJson);
  }

  if (btnCloseAnimaticModal) {
    btnCloseAnimaticModal.addEventListener("click", () => {
      if (pipeAnimaticModal) pipeAnimaticModal.style.display = "none";
      if (animaticVideoPlayer) animaticVideoPlayer.pause();
    });
  }
  if (btnDoneAnimaticModal) {
    btnDoneAnimaticModal.addEventListener("click", () => {
      if (pipeAnimaticModal) pipeAnimaticModal.style.display = "none";
      if (animaticVideoPlayer) animaticVideoPlayer.pause();
    });
  }

  if (btnCloseBiteModal) {
    btnCloseBiteModal.addEventListener("click", () => {
      if (pipeBiteDrawerModal) pipeBiteDrawerModal.style.display = "none";
    });
  }
  document.querySelectorAll(".bite-mode-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const mode = e.currentTarget.getAttribute("data-mode");
      if (mode) updateBiteDrawerModeUI(mode);
    });
  });
  if (btnSaveBiteJoint) {
    btnSaveBiteJoint.addEventListener("click", () => {
      if (currentPlanShots[currentBiteCurrIdx]) {
        currentPlanShots[currentBiteCurrIdx].continuity = currentBiteSelectedMode;
        currentPlanShots[currentBiteCurrIdx].re_anchor = (currentBiteSelectedMode === "re_anchor");
        renderTimelineStudio(currentPlanShots);
      }
      if (pipeBiteDrawerModal) pipeBiteDrawerModal.style.display = "none";
    });
  }

  // 加镜头与清空按钮
  if (btnPipeAddShot) {
    btnPipeAddShot.addEventListener("click", () => {
      syncCurrentShotsFromDOM();
      const newIdx = currentPlanShots.length + 1;
      const customPath = prompt("请输入新增镜头的图片/素材绝对路径 (留空将创建空镜头):", "");
      if (customPath === null) return;
      currentPlanShots.push({
        id: `shot_${String(newIdx).padStart(2, "0")}`,
        name: `分镜头 ${newIdx}`,
        image_path: customPath.trim(),
        image_name: customPath.trim() ? customPath.trim().split(/[\\/]/).pop() : `自定义镜头 ${newIdx}`,
        duration: 3.0,
        voice_text: "",
        subtitle_text: "",
        camera_motion: newIdx % 2 === 0 ? "zoom_in" : "pan_left",
        continuity: newIdx === 1 ? "cut" : "continue",
        re_anchor: false
      });
      renderTimelineStudio(currentPlanShots);
    });
  }

  if (btnPipeClearShots) {
    btnPipeClearShots.addEventListener("click", () => {
      if (currentPlanShots.length === 0) return;
      if (confirm("确定要清空所有已规划的分镜头吗？")) {
        currentPlanShots = [];
        renderTimelineStudio([]);
      }
    });
  }

  // ================= 智能一键模式核心逻辑与数据流驱动 =================
  const simpleModeState = {
    aspect: "16:9",
    duration: 30,
    voice: "zh-CN-YunxiNeural",
    style: "commercial"
  };

  const STYLE_PROMPT_MAP = {
    commercial: "商业电影大片质感, 8K超高清, 细腻材质光影, 景深通透, 现代极简布光",
    tech: "微观科技机理, 显微镜特写, 晶莹微距透亮, 粒子游走流光, 4K精微结构",
    natural: "自然治愈纪实风光, 真实通透晨光, 柔和丁达尔光线, 纯净生态质感",
    anime: "奇幻唯美二次元画风, 浪漫细腻色彩, 柔光动漫光晕, 唯美手绘笔触质感"
  };

  const INSPIRATION_TEMPLATES = {
    product: {
      text: "高端商业产品展示大片。从现代展台缓缓推近，微距特写产品精湛质感与光泽，随后光束流转展现核心细节，最后镜头拉远平稳定格，尽显卓越专业品质。",
      style: "commercial",
      shots: [
        { name: "镜头 1 · 宏观远景 (建置环境)", dur: 7.0, motion: "zoom_in", continuity: "cut", text: "光影穿透极简空间，精工锻造的标杆之作缓缓入画。" },
        { name: "镜头 2 · 中景推移 (主体入画)", dur: 8.0, motion: "pan_left", continuity: "continue", text: "镜头顺着光影平滑推移，核心形态在自然流动中清晰显现。" },
        { name: "镜头 3 · 环绕特写 (细节纹理)", dur: 7.5, motion: "orbit_cw", continuity: "continue", text: "环绕微距视角捕捉细微纹理，每一处精雕细琢都凝结着极致工艺。" },
        { name: "镜头 4 · 宏大全景 (升空定格)", dur: 7.5, motion: "zoom_out", continuity: "re_anchor", re_anchor: true, text: "视线缓缓拉远升腾，在辽阔天地中定格震撼瞬间。" }
      ]
    },
    drama: {
      text: "都市微电影连续故事片段。主角神情专注地推开玻璃门走进咖啡馆，镜头平滑跟拍坐下翻看信件，特写信纸上的关键文字，随后主角若有所思地望向窗外雨景。",
      style: "commercial",
      shots: [
        { name: "镜头 1 · 侧面跟拍 (推门入画)", dur: 7.0, motion: "pan_right", continuity: "cut", text: "雨幕朦胧的午后街头，主角若有所思地推开咖啡馆门扉。" },
        { name: "镜头 2 · 缓慢推近 (落座拆信)", dur: 8.0, motion: "zoom_in", continuity: "continue", text: "步入窗边座位坐下，指尖轻轻启封那封保存已久的信函。" },
        { name: "镜头 3 · 俯视特写 (信件文字)", dur: 7.5, motion: "tilt_down", continuity: "continue", text: "墨迹跃然纸上，昔日的字句在这一刻唤醒了封存的记忆。" },
        { name: "镜头 4 · 平缓拉远 (定格凝望)", dur: 7.5, motion: "zoom_out", continuity: "re_anchor", re_anchor: true, text: "视线抬起望向窗外雨丝，神情舒展，心中的困惑悄然解开。" }
      ]
    },
    nature: {
      text: "高山晨曦治愈风光大片。清晨第一缕阳光穿透山谷薄雾，镜头沿着潺潺清澈溪流低空滑翔穿行，穿过静谧森林，随后无人机大俯冲升腾，豁然展现群山日出的壮阔全景。",
      style: "natural",
      shots: [
        { name: "镜头 1 · 穿透薄雾 (晨光初现)", dur: 7.0, motion: "zoom_in", continuity: "cut", text: "清晨第一缕金色阳光穿透薄雾，整片山川在此刻苏醒。" },
        { name: "镜头 2 · 贴水滑翔 (溪流穿越)", dur: 8.0, motion: "pan_left", continuity: "continue", text: "镜头贴着清冽山溪低空疾驰，溅起的水珠映照出斑斓光斑。" },
        { name: "镜头 3 · 穿梭林冠 (斑驳树影)", dur: 7.5, motion: "crane_up", continuity: "continue", text: "顺势穿过古老静谧的林冠，光影交错在枝叶间婆娑起舞。" },
        { name: "镜头 4 · 峰顶升腾 (万丈朝阳)", dur: 7.5, motion: "zoom_out", continuity: "re_anchor", re_anchor: true, text: "镜头豁然冲出云海直上云霄，万丈朝阳普照壮丽群山。" }
      ]
    },
    tech: {
      text: "微观科技分子作用动画。显微镜视角深入微观世界，发光活性粒子如银河般游走汇聚，精准穿透细胞膜完成赋能激活动作，最后能量向外绽放，微光点亮整个空间。",
      style: "tech",
      shots: [
        { name: "镜头 1 · 深入微观 (深邃世界)", dur: 7.0, motion: "zoom_in", continuity: "cut", text: "微观视角极速下潜，璀璨的微观生命场域豁然展现。" },
        { name: "镜头 2 · 粒子汇聚 (动态游走)", dur: 8.0, motion: "orbit_cw", continuity: "continue", text: "高活性科技分子如星芒般汇聚旋转，释放纯净生命动能。" },
        { name: "镜头 3 · 穿透靶向 (精准赋能)", dur: 7.5, motion: "pan_right", continuity: "continue", text: "精准触达靶向核心，澎湃活性成分瞬时深层渗透激活。" },
        { name: "镜头 4 · 能量绽放 (整体升维)", dur: 7.5, motion: "zoom_out", continuity: "re_anchor", re_anchor: true, text: "强劲能量呈同心圆环层层激荡绽放，完成由内而外的生机蜕变。" }
      ]
    }
  };

  function generateShotsFromSimpleInput(text, predefShots = null) {
    const durSec = simpleModeState.duration || 30;
    let count = 4;
    let perShotDur = 7.5;
    if (durSec <= 15) {
      count = 3;
      perShotDur = 5.0;
    } else if (durSec >= 60) {
      count = 6;
      perShotDur = 10.0;
    }

    if (predefShots && predefShots.length > 0) {
      const scale = durSec / (predefShots.reduce((a, b) => a + (b.dur || 7.5), 0) || 30);
      const res = predefShots.map((s, idx) => ({
        id: `shot_${String(idx + 1).padStart(2, "0")}`,
        name: s.name || `镜头 ${idx + 1}`,
        image_path: s.image_path || "",
        image_name: s.image_name || "智能构图画面",
        duration: Math.max(3.0, Math.round(s.dur * scale * 10) / 10),
        voice_text: s.text || text,
        subtitle_text: s.text || text,
        camera_motion: s.motion || (idx === 0 ? "zoom_in" : "orbit_cw"),
        continuity: s.continuity || (idx === 0 ? "cut" : "continue"),
        re_anchor: !!s.re_anchor
      }));
      renderTimelineStudio(res);
      return;
    }

    const rawSentences = text
      .split(/[。！？\n]+/)
      .map(s => s.trim())
      .filter(s => s.length > 0);

    const shots = [];
    const motions = ["zoom_in", "pan_left", "orbit_cw", "crane_up", "pan_right", "zoom_out"];
    const titles = [
      "镜头 1 · 宏观远景 (建置环境)",
      "镜头 2 · 中景推移 (主体入画)",
      "镜头 3 · 环绕特写 (细节纹理)",
      "镜头 4 · 视角转换 (动态交互)",
      "镜头 5 · 空间升维 (光影流转)",
      "镜头 6 · 宏大全景 (定格终章)"
    ];

    for (let i = 0; i < count; i++) {
      let sentence = "";
      if (rawSentences.length === 0) {
        sentence = text;
      } else if (rawSentences.length <= count) {
        sentence = rawSentences[i % rawSentences.length];
      } else {
        const start = Math.floor((i * rawSentences.length) / count);
        const end = Math.floor(((i + 1) * rawSentences.length) / count);
        sentence = rawSentences.slice(start, Math.max(start + 1, end)).join("，");
      }

      const isFirst = (i === 0);
      const isAnchorPoint = (i === count - 1 || (count >= 6 && i === 3));

      shots.push({
        id: `shot_${String(i + 1).padStart(2, "0")}`,
        name: titles[i] || `镜头 ${i + 1}`,
        image_path: "",
        image_name: "智能生成画面",
        duration: perShotDur,
        voice_text: sentence,
        subtitle_text: sentence,
        camera_motion: motions[i % motions.length],
        continuity: isFirst ? "cut" : (isAnchorPoint ? "re_anchor" : "continue"),
        re_anchor: isAnchorPoint
      });
    }

    renderTimelineStudio(shots);
  }

  // 模式切换监听 (智能一键 vs 专业工坊)
  if (btnModeSimple && btnModePro) {
    btnModeSimple.addEventListener("click", () => {
      btnModeSimple.classList.add("active");
      btnModePro.classList.remove("active");
      if (panelModeSimple) panelModeSimple.style.display = "block";
      if (panelModePro) panelModePro.style.display = "none";
      if (creatorModeDescText) {
        creatorModeDescText.textContent = "写下你的创意想法或产品卖点，系统自动拆解分镜与连贯衔接";
      }
    });

    btnModePro.addEventListener("click", () => {
      btnModePro.classList.add("active");
      btnModeSimple.classList.remove("active");
      if (panelModeSimple) panelModeSimple.style.display = "none";
      if (panelModePro) panelModePro.style.display = "block";
      if (creatorModeDescText) {
        creatorModeDescText.textContent = "专业模式：可单独微调 5 大工序参数、全局画面防走样锚点及高级合成配置";
      }
    });
  }

  // 选项卡片点击同步
  document.querySelectorAll(".simple-opt-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const opt = btn.getAttribute("data-opt");
      const val = btn.getAttribute("data-val");
      if (!opt) return;

      const groupRow = btn.closest(".opt-card-row");
      if (groupRow) {
        groupRow.querySelectorAll(".simple-opt-btn").forEach(b => b.classList.remove("active"));
      }
      btn.classList.add("active");

      if (opt === "aspect") {
        simpleModeState.aspect = val;
        if (pipeAspect) pipeAspect.value = val;
        setAspectRatio(val);
      } else if (opt === "duration") {
        simpleModeState.duration = parseInt(val, 10) || 30;
        if (pipeDuration) {
          if (val === "60") {
            pipeDuration.value = "custom";
            if (pipeCustomDurationBox) pipeCustomDurationBox.style.display = "block";
            if (pipeCustomDurationInput) pipeCustomDurationInput.value = "60";
          } else {
            pipeDuration.value = val;
            if (pipeCustomDurationBox) pipeCustomDurationBox.style.display = "none";
          }
        }
      } else if (opt === "voice") {
        simpleModeState.voice = val;
        if (val === "none") {
          if (pipeToggleVoice) pipeToggleVoice.checked = false;
        } else {
          if (pipeToggleVoice) pipeToggleVoice.checked = true;
          if (pipeVoiceName) pipeVoiceName.value = val;
        }
        updateVoiceStageUI();
      } else if (opt === "style") {
        simpleModeState.style = val;
        const styleText = STYLE_PROMPT_MAP[val] || STYLE_PROMPT_MAP.commercial;
        currentContinuityAnchors.style_anchor = styleText;
        if (dnaStyleInput) dnaStyleInput.value = styleText;
      }

      const currentText = simpleIdeaInput ? simpleIdeaInput.value.trim() : "";
      if (currentText) {
        generateShotsFromSimpleInput(currentText);
      }
    });
  });

  // 灵感芯片点击绑定
  document.querySelectorAll(".simple-chip[data-inspiration]").forEach(chip => {
    chip.addEventListener("click", () => {
      const key = chip.getAttribute("data-inspiration");
      const tmpl = INSPIRATION_TEMPLATES[key];
      if (!tmpl) return;

      if (simpleIdeaInput) {
        simpleIdeaInput.value = tmpl.text;
      }

      const targetStyle = tmpl.style || "commercial";
      simpleModeState.style = targetStyle;
      document.querySelectorAll(".simple-opt-btn[data-opt='style']").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-val") === targetStyle);
      });
      const styleText = STYLE_PROMPT_MAP[targetStyle] || STYLE_PROMPT_MAP.commercial;
      currentContinuityAnchors.style_anchor = styleText;
      if (dnaStyleInput) dnaStyleInput.value = styleText;

      generateShotsFromSimpleInput(tmpl.text, tmpl.shots);
    });
  });

  if (btnSimpleClearIdea) {
    btnSimpleClearIdea.addEventListener("click", () => {
      if (simpleIdeaInput) simpleIdeaInput.value = "";
      currentPlanShots = [];
      renderTimelineStudio([]);
    });
  }

  if (simpleIdeaInput) {
    let ideaDebounceTimer = null;
    simpleIdeaInput.addEventListener("input", () => {
      clearTimeout(ideaDebounceTimer);
      ideaDebounceTimer = setTimeout(() => {
        const val = simpleIdeaInput.value.trim();
        if (val) {
          generateShotsFromSimpleInput(val);
        }
      }, 600);
    });
  }

  if (simpleMatDir) {
    simpleMatDir.addEventListener("input", () => {
      if (pipeMatDir) pipeMatDir.value = simpleMatDir.value.trim();
    });
  }

  if (btnSimpleScan) {
    btnSimpleScan.addEventListener("click", () => {
      const dirVal = simpleMatDir ? simpleMatDir.value.trim() : "";
      if (!dirVal) {
        alert("请先输入本地素材文件夹路径，例如 E:\公司素材\产品实景图");
        return;
      }
      if (pipeMatDir) pipeMatDir.value = dirVal;
      doSmartInspect(dirVal);
    });
  }

  if (btnSimpleGenerate) {
    btnSimpleGenerate.addEventListener("click", () => {
      const idea = simpleIdeaInput ? simpleIdeaInput.value.trim() : "";
      if (!idea && (!currentPlanShots || currentPlanShots.length === 0)) {
        alert("请先在上方输入你想制作的视频内容，或点击任一快捷灵感芯片！");
        if (simpleIdeaInput) simpleIdeaInput.focus();
        return;
      }
      if ((!currentPlanShots || currentPlanShots.length === 0) && idea) {
        generateShotsFromSimpleInput(idea);
      }
      if (tabPipeMonitor) tabPipeMonitor.click();
      startProductionPipeline();
    });
  }

  if (btnSimplePreviewAnimatic) {
    btnSimplePreviewAnimatic.addEventListener("click", () => {
      const idea = simpleIdeaInput ? simpleIdeaInput.value.trim() : "";
      if (!idea && (!currentPlanShots || currentPlanShots.length === 0)) {
        alert("请先输入视频创意或点击快捷灵感芯片生成分镜后再进行试看！");
        if (simpleIdeaInput) simpleIdeaInput.focus();
        return;
      }
      if ((!currentPlanShots || currentPlanShots.length === 0) && idea) {
        generateShotsFromSimpleInput(idea);
      }
      triggerAnimaticPreview();
    });
  }

  // 4. 智能素材诊断与分镜预案规划
  async function doSmartInspect(targetPath) {
    const p = (targetPath || (pipeMatDir ? pipeMatDir.value : "")).trim();
    if (!p) {
      alert("请输入或粘贴素材目录或文件路径！");
      return;
    }

    if (pipeDiagSummary) {
      pipeDiagSummary.innerHTML = '<span style="color:#60a5fa;">🔍 正在深度诊断素材结构、提取文本并智能规划双层时间轴全案...</span>';
    }
    if (tabPipePlan) tabPipePlan.click();

    try {
      const res = await fetch("/api/pipeline/inspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_path: p,
          user_instruction: pipeScriptText ? pipeScriptText.value.trim() : null
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "诊断失败");
      }

      const rep = data.report;
      if (!rep) return;

      if (pipeDiagModeTag) {
        pipeDiagModeTag.textContent = rep.mode_title || rep.recommended_mode;
      }
      if (pipeDiagConfidence) {
        pipeDiagConfidence.textContent = `推荐置信度: ${Math.round((rep.confidence || 0.9) * 100)}%`;
      }
      if (pipeDiagSummary) {
        pipeDiagSummary.textContent = rep.summary_text || "素材解析完成";
      }

      if (rep.recommended_mode && PRESET_CONFIGS[rep.recommended_mode]) {
        applyPreset(rep.recommended_mode, false);
      }

      if (rep.script_lines && rep.script_lines.length > 0 && pipeScriptText && !pipeScriptText.value.trim()) {
        pipeScriptText.value = rep.script_lines.join("\n");
      }

      if (rep.continuity_anchors) {
        renderContinuityAnchors(rep.continuity_anchors);
      }

      renderTimelineStudio(rep.suggested_shots || []);

    } catch (err) {
      if (pipeDiagSummary) {
        pipeDiagSummary.innerHTML = `<span style="color:#ef4444;">诊断失败: ${escapeHtml(err.message)}</span>`;
      }
    }
  }

  if (btnPipeInspectAction) {
    btnPipeInspectAction.addEventListener("click", () => doSmartInspect());
  }
  if (btnPipeQuickInspect) {
    btnPipeQuickInspect.addEventListener("click", () => doSmartInspect());
  }
  if (btnPipePlanConfirm) {
    btnPipePlanConfirm.addEventListener("click", () => doSmartInspect());
  }

  // 5. 执行生产流水线
  function updatePipelineStepNodes(step) {
    const nodes = {
      "素材解析": "step-crop",
      "切图解析": "step-crop",
      "视听装配": "step-tts",
      "配音对齐": "step-tts",
      "运镜渲染": "step-motion",
      "混音字幕": "step-mix",
      "母片交付": "step-done",
      "完成": "step-done"
    };
    document.querySelectorAll(".pipe-step-node").forEach(el => {
      el.classList.remove("active", "done");
    });
    const targetId = nodes[step];
    if (targetId) {
      const activeEl = document.getElementById(targetId);
      if (activeEl) {
        activeEl.classList.add("active");
      }
    }
    if (step === "完成" || step === "母片交付") {
      document.querySelectorAll(".pipe-step-node").forEach(el => el.classList.add("done"));
    }
  }

  async function startProductionPipeline() {
    const matDir = pipeMatDir ? pipeMatDir.value.trim() : "";
    if (!matDir && (!currentPlanShots || currentPlanShots.length === 0)) {
      alert("请输入素材文件夹路径或先规划分镜头！");
      return;
    }

    syncCurrentShotsFromDOM();

    // 收集分镜头预案重载
    const shotsOverride = [];
    if (currentPlanShots && currentPlanShots.length > 0) {
      currentPlanShots.forEach((s, idx) => {
        shotsOverride.push({
          id: s.id || `shot_${String(idx + 1).padStart(2, "0")}`,
          name: s.name || `镜头 ${idx + 1}`,
          image_path: s.image_path || "",
          voice_text: s.voice_text || "",
          subtitle_text: s.subtitle_text || s.voice_text || "",
          duration: parseFloat(s.duration) || 3.0,
          motion: s.camera_motion || s.motion || (idx % 2 === 0 ? "zoom_in" : "pan_left"),
          camera_motion: s.camera_motion || s.motion || (idx % 2 === 0 ? "zoom_in" : "pan_left"),
          continuity: s.continuity || (idx === 0 ? "cut" : "continue"),
          re_anchor: !!s.re_anchor,
          end_image: s.end_image || null
        });
      });
    }

    // 计算时长
    let durationMode = "fixed";
    let totalDuration = 30.0;
    if (pipeDuration) {
      if (pipeDuration.value === "natural") {
        durationMode = "auto";
        totalDuration = 0.0;
      } else if (pipeDuration.value === "custom") {
        durationMode = "fixed";
        totalDuration = parseFloat(pipeCustomDurationInput.value) || 30.0;
      } else {
        durationMode = "fixed";
        totalDuration = parseFloat(pipeDuration.value) || 30.0;
      }
    }

    // BGM 路径与模式
    const isBgmOn = pipeToggleBgm ? pipeToggleBgm.checked : true;
    let bgmModeVal = isBgmOn ? (pipeBgmMode ? pipeBgmMode.value : "auto") : "none";
    let bgmPathVal = null;
    if (isBgmOn && bgmModeVal === "custom" && pipeBgmPath) {
      bgmPathVal = pipeBgmPath.value.trim();
    }

    // 配音与字幕模式解耦
    const isVoiceOn = pipeToggleVoice ? pipeToggleVoice.checked : true;
    const isSubOn = pipeToggleSub ? pipeToggleSub.checked : true;
    const isInspectOn = pipeToggleInspect ? pipeToggleInspect.checked : true;
    const isGridCrop = pipeCheckGridCrop ? pipeCheckGridCrop.checked : false;

    // 按钮进入生产中状态
    if (btnPipeExecutePlan) {
      btnPipeExecutePlan.disabled = true;
      btnPipeExecutePlan.innerHTML = "<span>⏳ 工坊正在全速生产中...</span>";
    }
    if (btnStartPipeline) {
      btnStartPipeline.disabled = true;
      btnStartPipeline.innerHTML = "<span>⏳ 全力生产中...</span>";
    }

    // 自动切到监控面板
    if (tabPipeMonitor) tabPipeMonitor.click();
    if (pipeStatusTag) {
      pipeStatusTag.innerText = "启动中";
      pipeStatusTag.style.background = "#2563eb";
      pipeStatusTag.style.color = "#fff";
    }
    if (pipeProgressBar) pipeProgressBar.style.width = "5%";
    if (pipeLogBox) pipeLogBox.innerHTML = "<div>[提交] 正在创建智能多模态生产作业...</div>";
    if (pipeResultBox) pipeResultBox.style.display = "none";

    try {
      const payload = {
        material_dir: matDir,
        mode: currentStudioMode || "custom",
        aspect_ratio: pipeAspect ? pipeAspect.value : "16:9",
        duration_mode: durationMode,
        total_duration: totalDuration,
        voice_mode: isVoiceOn ? "auto" : "none",
        voice_name: pipeVoiceName ? pipeVoiceName.value : "zh-CN-YunxiNeural",
        bgm_mode: bgmModeVal,
        bgm_path: bgmPathVal,
        subtitle_mode: isSubOn ? "auto" : "none",
        engine_choice: pipeEngineChoice ? pipeEngineChoice.value : "local",
        grid_crop: isGridCrop,
        enable_inspect: isInspectOn,
        script_text: pipeScriptText ? pipeScriptText.value.trim() : "",
        shots_override: shotsOverride.length > 0 ? shotsOverride : null,
        continuity_anchors: currentContinuityAnchors
      };

      const res = await fetch("/api/pipeline/smart-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "启动流水线失败");
      }

      activePipelineJobId = data.job_id;
      if (pipeLogBox) {
        pipeLogBox.innerHTML += `<div>[作业就绪] 任务ID: <b style="color:#38bdf8;">${activePipelineJobId}</b>，模式: <b>${data.mode}</b>，镜头数: <b>${data.shots_count}</b></div>`;
      }

      // 启动轮询状态
      if (pipelinePollTimer) clearInterval(pipelinePollTimer);
      pipelinePollTimer = setInterval(async () => {
        try {
          const jRes = await fetch(`/api/pipeline/job/${activePipelineJobId}`);
          if (!jRes.ok) return;
          const jData = await jRes.json();
          const job = jData.job;
          if (!job) return;

          if (pipeProgressBar) pipeProgressBar.style.width = `${job.progress}%`;
          updatePipelineStepNodes(job.step);
          if (pipeStatusTag) pipeStatusTag.innerText = `${job.step} (${job.progress}%)`;

          if (job.logs && job.logs.length > 0 && pipeLogBox) {
            const logHtml = job.logs.map(l => `<div><span style="color:#64748b;">[${l.time}]</span> <b style="color:#38bdf8;">[${l.step}]</b> ${l.message}</div>`).join("");
            pipeLogBox.innerHTML = logHtml;
            pipeLogBox.scrollTop = pipeLogBox.scrollHeight;
          }

          if (job.status === "completed") {
            clearInterval(pipelinePollTimer);
            if (btnPipeExecutePlan) {
              btnPipeExecutePlan.disabled = false;
              btnPipeExecutePlan.innerHTML = "<span>🚀 确认方案并开始生产</span>";
            }
            if (btnStartPipeline) {
              btnStartPipeline.disabled = false;
              btnStartPipeline.innerHTML = "<span>⚡ 极速直通生成</span>";
            }
            if (pipeStatusTag) {
              pipeStatusTag.innerText = "已完成";
              pipeStatusTag.style.background = "#10b981";
              pipeStatusTag.style.color = "#fff";
            }
            updatePipelineStepNodes("完成");

            if (pipeResultBox) pipeResultBox.style.display = "block";
            const vUrl = `/api/pipeline/video/${activePipelineJobId}`;
            if (pipeVideoLink) pipeVideoLink.href = vUrl;
            if (pipePlayVideoBtn) {
              pipePlayVideoBtn.onclick = () => {
                openVideoPlayer(activePipelineJobId, vUrl);
              };
            }
            if (pipeOpenFolderBtn) {
              pipeOpenFolderBtn.onclick = () => {
                fetch("/api/system/open-folder", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ folder_path: matDir + "/output" })
                });
              };
            }
          } else if (job.status === "failed") {
            clearInterval(pipelinePollTimer);
            if (btnPipeExecutePlan) {
              btnPipeExecutePlan.disabled = false;
              btnPipeExecutePlan.innerHTML = "<span>🚀 重新开始生产</span>";
            }
            if (btnStartPipeline) {
              btnStartPipeline.disabled = false;
              btnStartPipeline.innerHTML = "<span>⚡ 极速直通生成</span>";
            }
            if (pipeStatusTag) {
              pipeStatusTag.innerText = "失败";
              pipeStatusTag.style.background = "#ef4444";
              pipeStatusTag.style.color = "#fff";
            }
            if (pipeLogBox) {
              pipeLogBox.innerHTML += `<div style="color:#ef4444; font-weight:bold;">[作业故障] ${job.error || "未知异常"}</div>`;
              pipeLogBox.scrollTop = pipeLogBox.scrollHeight;
            }
          }
        } catch (pollErr) {
          console.error("Pipeline poll error:", pollErr);
        }
      }, 1000);

    } catch (err) {
      alert("启动流水线失败: " + err.message);
      if (btnPipeExecutePlan) {
        btnPipeExecutePlan.disabled = false;
        btnPipeExecutePlan.innerHTML = "<span>🚀 确认方案并开始生产</span>";
      }
      if (btnStartPipeline) {
        btnStartPipeline.disabled = false;
        btnStartPipeline.innerHTML = "<span>⚡ 极速直通生成</span>";
      }
      if (pipeStatusTag) {
        pipeStatusTag.innerText = "失败";
        pipeStatusTag.style.background = "#ef4444";
      }
    }
  }

  if (btnPipeExecutePlan) {
    btnPipeExecutePlan.addEventListener("click", startProductionPipeline);
  }
  if (btnStartPipeline) {
    btnStartPipeline.addEventListener("click", startProductionPipeline);
  }

  // 初始化所有工序的 UI 状态
  updateAllStageUIs();

  // 初始化时间轴为空态，不强加预设模板
  try {
    applyPreset("long_series_30s", false);
    renderTimelineStudio([]);
  } catch (e) {
    console.error("Default initialization error:", e);
  }

// ==================== 初始化与自动轮询 ====================
  setAspectRatio("16:9");
  setDurationSec(8);
  applyEngineMode("flow");
  fetchOverview();
  fetchTasks();
  fetchProfiles();

  state.pollTimer = setInterval(() => {
    fetchOverview();
    const activeTab = document.querySelector(".tab-button.active");
    if (activeTab && activeTab.getAttribute("data-target") === "view-tasks") {
      fetchTasks();
    }
    if (activeTab && activeTab.getAttribute("data-target") === "view-images") {
      fetchTasks().then(() => renderImageGallery());
    }
    if (activeTab && activeTab.getAttribute("data-target") === "view-profiles") {
      fetchProfiles();
    }
  }, 3000);
});
