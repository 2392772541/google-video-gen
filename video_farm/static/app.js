// Video Farm Studio - Modern Frontend Engine (Dual Engine: Google Flow & Gemini Web)
document.addEventListener("DOMContentLoaded", () => {
  // ==================== 全局状态 ====================
  const state = {
    currentEngine: "flow", // "flow" 或 "gemini"
    selectedTaskIds: new Set(),
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
        batchActionBar: document.getElementById("batch-action-bar"),
    batchSelectAllChk: document.getElementById("batch-select-all-chk"),
    btnBatchInvert: document.getElementById("btn-batch-invert"),
    btnBatchClear: document.getElementById("btn-batch-clear"),
    batchStatsText: document.getElementById("batch-stats-text"),
    btnBatchDownload: document.getElementById("btn-batch-download"),
    btnBatchCancel: document.getElementById("btn-batch-cancel"),
    btnBatchDelete: document.getElementById("btn-batch-delete"),
    btnBatchSelectCompleted: document.getElementById("btn-batch-select-completed"),
    btnQuickSelectCompleted: document.getElementById("btn-quick-select-completed"),
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
    countAudio: document.getElementById("count-audio"),

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
    if (str == null) return "";
    // JS literal escaping and HTML attribute escaping are different layers.
    return escapeHtml(String(str)
      .replace(/\\/g, "\\\\")
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\"')
      .replace(/\n/g, "\\n")
      .replace(/\r/g, "\\r"));
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

      if (targetId === "view-tasks") { renderTasks(); fetchTasks(); }
      if (targetId === "view-images") { renderImageGallery(); fetchTasks(); }
      if (targetId === "view-generate") { taskPage = 0; fetchTasks(); }
      if (targetId === "view-profiles") fetchProfiles();
      if (targetId === "view-audio") {
        updateAudioCompletedVideos();
        updateAssignedProfSelect();
        if (window.refreshGeminiHubView) window.refreshGeminiHubView();
      }
    });
  });

  // ==================== 模型数据字典与动态联动 ====================
  const VIDEO_ENGINE_MODELS = {
    flow: [
      { value: "veo-lite", label: "Veo 3.1 Lite · 默认配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "veo-quality", label: "Veo 3.1 Quality · 质量请求", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "veo-fast", label: "Veo 3.1 Fast · 速度请求", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "omni-flash", label: "Omni Flash · 本地配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "veo-lite-lp", label: "Veo 3.1 Lite LP · 备用配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "custom", label: "自定义模型代码…", desc: "输入当前账号确实可用的模型代码；系统不保证任意代码都能生成。" }
    ],
    gemini: [
      { value: "auto", label: "Auto · 自动选择", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "gemini-3.8-flash", label: "Gemini 3.8 Flash · 本地配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "gemini-3.8-pro", label: "Gemini 3.8 Pro / Advanced · 本地配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "gemini-3.8-thinking", label: "Gemini 3.8 Flash Thinking · 本地配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "gemini-3.0-flash", label: "Gemini 3.0 Flash · 本地配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "gemini-3.0-pro", label: "Gemini 3.0 Pro · 本地配置", desc: "本地路由配置名称；实际模型可用性、额度与成片规格以上游账号及实际文件为准。" },
      { value: "custom", label: "自定义模型代码…", desc: "输入当前账号确实可用的模型代码；系统不保证任意代码都能生成。" }
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
      el.modelDescHint.textContent = `${found.desc}`;
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
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-aspect") === aspect));
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
      btn.setAttribute("aria-pressed", String(parseInt(btn.getAttribute("data-sec")) === sec));
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
      el.stagePanelTitle.textContent = "参考画面 · 可选";
    } else {
      el.stagePanelTitle.textContent = "参考画面 · 首尾帧";
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
      if (el.labelModelTitle) el.labelModelTitle.innerHTML = `Gemini 对话框模型`;
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
        if (roleTag) roleTag.textContent = "参考图 · 可选";
        const dropTxt = el.placeholderStart.querySelector(".drop-text");
        if (dropTxt) dropTxt.textContent = "上传参考图 (可选)";
        const dropSub = el.placeholderStart.querySelector(".drop-subtext");
        if (dropSub) dropSub.textContent = "留空则执行纯文本生视频";
      }
      if (el.stageHintText) {
        el.stageHintText.textContent = "支持文字或单张参考图；可用性与额度以账号为准。";
      }
      el.btnSubmitTask.textContent = "创建视频任务";
      el.inputPrompt.placeholder = "输入视频描述提示词（例如：现代化农业种植大棚航拍，阳光透射绿叶生机盎然，16:9横屏，镜头平滑推进，4K质感）...";
    } else {
      if (el.btnEngineFlow) el.btnEngineFlow.classList.add("active");
      if (el.btnEngineGemini) el.btnEngineGemini.classList.remove("active", "gemini-active");

      // 模型与标签切换为 Flow
      updateModelOptions("flow", "veo-lite");
      if (el.labelModelTitle) el.labelModelTitle.innerHTML = `Google Flow 视频模型`;
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
        if (roleTag) roleTag.textContent = "首帧";
        const dropTxt = el.placeholderStart.querySelector(".drop-text");
        if (dropTxt) dropTxt.textContent = "上传首帧图片";
        const dropSub = el.placeholderStart.querySelector(".drop-subtext");
        const asp = state.currentAspect || "16:9";
        if (dropSub) dropSub.textContent = ASPECT_CONFIG[asp] ? ASPECT_CONFIG[asp].resHint : "推荐 16:9 (如 1280x720)";
      }
      if (el.stageHintText) {
        el.stageHintText.textContent = "用两张画面定义起点与终点，具体效果以生成结果为准。";
      }
      el.btnSubmitTask.textContent = "创建视频任务";
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
    const selectEngineEl = document.getElementById("select-batch-engine");
    const selectedEngine = selectEngineEl ? selectEngineEl.value : "vids";

    try {
      const resp = await fetch("/api/tasks/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots: list,
          profile_id: selectedProfile,
          engine: selectedEngine
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

  let taskPage = 0;
  const taskPageSize = 100;
  let taskTotal = 0;
  let tasksRequest = null;
  let lastTasksSnapshot = "";

  async function fetchTasks(force = false) {
    if (tasksRequest) {
      await tasksRequest;
      if (force) return fetchTasks(true);
      return;
    }
    const requestedPage = taskPage;
    tasksRequest = (async () => {
      try {
        const resp = await fetch(`/api/tasks?limit=${taskPageSize}&offset=${requestedPage * taskPageSize}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const tasks = await resp.json();
        taskTotal = Number(resp.headers.get("X-Total-Count") || tasks.length);
        if (el.badgeTotalTasks) el.badgeTotalTasks.textContent = taskTotal;
        const maxPage = Math.max(0, Math.ceil(taskTotal / taskPageSize) - 1);
        if (taskPage > maxPage) { taskPage = maxPage; lastTasksSnapshot = ""; }
        const snapshot = JSON.stringify(tasks);
        if (force || snapshot !== lastTasksSnapshot) {
          state.tasks = tasks;
          lastTasksSnapshot = snapshot;
          updateTaskFilterCounts();
          if (document.getElementById("view-tasks")?.classList.contains("active")) renderTasks();
          if (document.getElementById("view-images")?.classList.contains("active")) renderImageGallery();
        }
        if (requestedPage === 0) window.VideoWorkbench?.update(tasks);
        document.querySelectorAll(".task-page-info").forEach(e => {
          e.textContent = `第 ${requestedPage + 1} 页 · 本页 ${tasks.length} 条 / 全库 ${taskTotal} 条（分类计数与勾选仅限本页）`;
        });
        document.querySelectorAll(".btn-task-prev").forEach(e => e.disabled = taskPage === 0);
        document.querySelectorAll(".btn-task-next").forEach(e => e.disabled = (taskPage + 1) * taskPageSize >= taskTotal);
      } catch (e) {
        console.error("任务列表刷新失败", e);
        if (force) showToast("任务列表刷新失败，请检查服务连接", "error");
      }
    })();
    try { await tasksRequest; } finally { tasksRequest = null; }
    if (requestedPage !== taskPage) return fetchTasks(true);
  }
  document.querySelectorAll(".btn-task-prev, .btn-task-next").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (tasksRequest) return;
      taskPage += btn.classList.contains("btn-task-next") ? 1 : -1;
      state.selectedTaskIds.clear();
      updateBatchActionBar();
      await fetchTasks(true);
    });
  });

  function updateTaskFilterCounts() {
    const counts = { all: state.tasks.length, running: 0, queued: 0, completed: 0, failed: 0, video: 0, image: 0, audio: 0 };
    state.tasks.forEach(t => {
      if (t.task_type === "image") counts.image++;
      else if (t.task_type === "audio") counts.audio++;
      else counts.video++;

      if (["dispatching", "running", "verifying"].includes(t.status)) counts.running++;
      else if (["queued", "retry_wait"].includes(t.status)) counts.queued++;
      else if (t.status === "completed") counts.completed++;
      else if (t.status === "failed") counts.failed++;
    });

    if (el.countAll) el.countAll.textContent = counts.all;
    if (el.countVideo) el.countVideo.textContent = counts.video;
    if (el.countImage) el.countImage.textContent = counts.image;
    if (el.countAudio) el.countAudio.textContent = counts.audio;
    if (el.countRunning) el.countRunning.textContent = counts.running;
    if (el.countQueued) el.countQueued.textContent = counts.queued;
    if (el.countCompleted) el.countCompleted.textContent = counts.completed;
    if (el.countFailed) el.countFailed.textContent = counts.failed;
    if (el.badgeTotalTasks) el.badgeTotalTasks.textContent = taskTotal;
  }

  function renderTasks() {
    const container = el.tasksContainer;
    container.innerHTML = "";

    let filtered = state.tasks;
    if (state.currentFilter === "video") {
      filtered = filtered.filter(t => t.task_type !== "image" && t.task_type !== "audio");
    } else if (state.currentFilter === "image") {
      filtered = filtered.filter(t => t.task_type === "image");
    } else if (state.currentFilter === "audio") {
      filtered = filtered.filter(t => t.task_type === "audio");
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
      const isSelected = state.selectedTaskIds.has(t.id);
      const card = document.createElement("div");
      card.className = "task-card" + (isSelected ? " selected" : "");

      let statusBadgeClass = "status-queued";
      if (t.status === "completed") statusBadgeClass = "status-completed";
      if (["dispatching", "running", "verifying"].includes(t.status)) statusBadgeClass = "status-running";
      if (t.status === "failed") statusBadgeClass = "status-failed";

      const isAudioTask = t.task_type === "audio";
      const isImageTask = t.task_type === "image";
      const isVideoTask = !isImageTask && !isAudioTask;
      let engineBadge = "";
      if (isAudioTask) {
        const vName = t.model || "zh-CN-YunxiNeural";
        const vLabel = vName.includes("Xiaoxiao") ? "晓晓 (温柔女声)" : (vName.includes("Yunjian") ? "云健 (影视男声)" : (vName.includes("Yunyang") ? "云扬 (播音男声)" : (vName.includes("Xiaoyi") ? "晓伊 (生动女声)" : (vName.includes("gemini") ? "Gemini 网页原生" : "云希 (阳光男声)"))));
        engineBadge = `<span class="badge-engine-gemini" style="background:rgba(217,70,239,0.2); color:#f0abfc; border:1px solid rgba(217,70,239,0.4); margin-right:6px;">🎙️ 配音 · ${escapeHtml(vLabel)}</span>`;
      } else if (isImageTask) {
        const mLabel = t.model === "nano-pro" ? "Nano Banana Pro" : (t.model === "nano2" ? "Nano Banana 2" : (t.model === "imagen4" ? "Imagen（imagen4 路由）" : (t.model || "Nano Pro")));
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
        watermarkText = "✓ 抽查未检出";
        watermarkClass = "qa-val-ok";
      } else if (t.watermark_check === "forced_visible") {
        watermarkText = "⚠️ 抽查检出";
        watermarkClass = "qa-val-bad";
      }

      // 智能异常提示与对策方案展示（覆盖等待重试与失败任务）
      let errorNoticeHtml = "";
      if (t.status === "retry_wait") {
        let reasonDesc = t.error_message || "上一轮生成网络响应超时或环境链路抖动";
        let solutionDesc = "系统已自动解绑故障通道，达到冷却时间后，按账号绑定与池内空闲情况继续排队";
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
            <div style="margin-top:4px; color:#bfdbfe;"><b>手动干预：</b>您可等待系统自动调度，或点击下方<b>【🔄 重新排队】</b>直接唤醒。</div>
          </div>
        `;
      } else if (t.status === "failed") {
        if (t.error_code === "AUTH_EXPIRED") {
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(239,68,68,0.12); border-left:3px solid var(--red-err); border-radius:4px; font-size:12px; color:#fca5a5; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#f87171;">⚠️ 授权已失效 (401 UNAUTHORIZED)</div>
              <div><b>原因分析：</b>Google Flow / Gemini 会话凭据已过期或未完成首次服务条款同意。</div>
              <div style="margin-top:2px;"><b>解决方案：</b>请前往顶部【账号管理】点击【✨ 自动过协议】或在 Chrome 中点一次同意，然后点击下方【🔄 重新排队】。</div>
            </div>
          `;
        } else if (t.error_code === "QUOTA_EXHAUSTED") {
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(245,158,11,0.12); border-left:3px solid var(--orange-warn); border-radius:4px; font-size:12px; color:#fde68a; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#fbbf24;">⚡ 账号额度耗尽</div>
              <div><b>原因分析：</b>原账号今日已用尽配额。</div>
              <div style="margin-top:2px;"><b>解决方案：</b>系统已将原账号切入冷却，请点击下方【🔄 重新排队】使用池中其他空闲账号。</div>
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
              <div style="margin-top:4px;"><b>操作建议：</b>可等待系统安全削峰自愈，或点击下方【🔄 重新排队】手动指定其他健康账号。</div>
            </div>
          `;
        } else if (t.error_code === "RATE_LIMITED") {
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(245,158,11,0.12); border-left:3px solid var(--orange-warn); border-radius:4px; font-size:12px; color:#fde68a; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#fbbf24;">⏳ 触发高频频控保护</div>
              <div><b>原因分析：</b>账号暂时触发 Google 异常活动限制。</div>
              <div style="margin-top:2px;"><b>解决方案：</b>已自动切入冷却，点击下方【🔄 重新排队】重新排队；冷却仍会生效。</div>
            </div>
          `;
        } else {
          let reasonDesc = t.error_message || "任务遇到异常中断或已达到最大重试次数";
          errorNoticeHtml = `
            <div style="margin-top:8px; padding:10px 12px; background:rgba(239,68,68,0.12); border-left:3px solid var(--red-err); border-radius:4px; font-size:12px; color:#fca5a5; line-height:1.5;">
              <div style="font-weight:600; margin-bottom:4px; color:#f87171;">⚠️ 任务中断或需重试</div>
              <div><b>原因分析：</b>${escapeHtml(reasonDesc.slice(0, 160))}</div>
              <div style="margin-top:2px;"><b>解决方案：</b>点击下方【🔄 重新排队】按钮，系统将重置计数并按现有账号绑定排队。</div>
            </div>
          `;
        }
      }

      if (["WIRE_FORMAT_MISMATCH", "UNSUPPORTED_FEATURE"].includes(t.error_code)) {
        errorNoticeHtml = `<div class="audit-task-warning">模型 / 参数不兼容：请修正后创建新任务，换号或重复提交无法解决。</div>`;
      }
      if (t.status === "completed" && !t.has_video && !t.has_audio && !(t.image_urls || []).length) {
        errorNoticeHtml += `<div class="audit-task-warning">任务已完成，但产物文件缺失；请检查输出目录或日志。</div>`;
      }
      card.innerHTML = `
        <div class="task-card-top">
          <div style="display:flex; align-items:center;">
            <div class="task-card-check-wrap">
              <input type="checkbox" class="task-item-checkbox" data-id="${t.id}" ${isSelected ? "checked" : ""} title="勾选进行批量操作">
            </div>
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
            ${isAudioTask ? `
              <span>类型: 智能语音解说 | 音色: ${escapeHtml(t.model || "标准")}</span>
              <span>账号: ${escapeHtml(t.assigned_profile_id || "自动调度")}</span>
            ` : `
              <span>比例: ${t.aspect_ratio || "9:16"}${isImageTask ? ` | 模型: ${t.model || "nano-pro"}` : ` | 请求时长: ${t.duration_sec || 8}s`}</span>
              <span>账号: ${t.assigned_profile_id || "自动调度"}</span>
            `}
          </div>

          ${errorNoticeHtml}

          ${isAudioTask && t.status === "completed" && (t.has_audio || t.audio_url || t.output_audio_path) ? `
            <div class="task-audio-result" style="margin: 10px 0; padding: 12px; background: rgba(15,23,42,0.6); border-radius: 8px; border: 1px solid rgba(217,70,239,0.3);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:12px; color:#cbd5e1;">
                <span style="display:flex; align-items:center; gap:6px;">
                  <span style="font-size:16px;">🎵</span>
                  <b>成品音频播放</b>
                </span>
                <span style="font-size:11px; color:#c084fc;">音频成片</span>
              </div>
              <audio controls src="${t.audio_url || ('/media/outputs/' + (t.output_audio_path ? t.output_audio_path.split(/[\\/]/).pop() : ''))}" style="width:100%; height:36px; outline:none; border-radius:4px;"></audio>
              ${t.input_video_path ? `<div style="font-size:11px; color:#94a3b8; margin-top:6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">📹 参考视频: ${escapeHtml(t.input_video_path.split(/[\\/]/).pop())}</div>` : ''}
            </div>
          ` : ""}

          ${isVideoTask && t.has_video ? `
            <div class="task-media-box btn-play-video-box" data-id="${t.id}" data-url="${t.video_url}" title="点击直接播放成片视频">
              ${t.first_frame_url || t.start_image_url ? `
                <img src="${t.first_frame_url || t.start_image_url}" class="task-media-thumb" loading="lazy" alt="成片封面">
              ` : `
                <video src="${t.video_url}#t=0.5" preload="none" class="task-media-thumb" muted playsinline></video>
              `}
              <div class="task-media-overlay">
                <div class="play-btn-circle">▶</div>
              </div>
              <div class="task-media-badge-group">
                <span class="task-media-badge">${t.aspect_ratio || "16:9"}</span>
                <span class="task-media-badge" title="请求时长；实际时长以播放信息为准">请求 ${t.duration_sec || 8}s</span>
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

          ${!isImageTask && !isAudioTask && t.status === "completed" ? `
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
                <span class="qa-col-label" title="仅抽查区域，不代表全画面无水印">水印抽查</span>
                <span class="qa-col-val ${watermarkClass}">${watermarkText}</span>
              </div>
            </div>
          ` : ""}

          ${!isImageTask && !isAudioTask && t.has_video && t.output_video_path ? `
            <div style="font-size: 11px; color: var(--text-muted); font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 4px; padding: 2px 6px; background: rgba(0,0,0,0.25); border-radius: 4px;" title="${escapeAttr(t.output_video_path)}">
              📁 本地路径: ${escapeHtml(t.output_video_path)}
            </div>
          ` : ""}
        </div>

        <div class="task-card-bottom">
          <div class="task-btn-group">
            ${isImageTask && t.status === "completed" && t.image_urls && t.image_urls.length > 0 ? `<button class="btn btn-primary btn-sm" onclick="openImageViewer('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}', '${escapeJs(t.prompt)}')">👁️ 查看大图</button>` : ""}
            ${!isImageTask && !isAudioTask && t.has_video ? `<button class="btn btn-primary btn-sm btn-play-video" data-id="${t.id}" data-url="${t.video_url}">🎥 播放</button>` : ""}
            ${!isImageTask && !isAudioTask && t.has_video ? `<button class="btn btn-secondary btn-sm btn-copy-video-path" data-id="${t.id}" data-path="${escapeAttr(t.output_video_path || '')}" title="复制本地绝对路径，可直接在 Google Vids 导入窗口粘贴使用">📋 复制路径</button>` : ""}
            ${(t.has_video || t.has_audio || (isImageTask && t.status === "completed" && t.image_urls && t.image_urls.length > 0)) ? `<a href="/api/tasks/${t.id}/download" download class="btn btn-secondary btn-sm" title="保存下载该成品文件">📥 下载</a>` : ""}
            ${["running", "dispatching", "verifying"].includes(t.status) ? `<button class="btn btn-danger btn-sm btn-cancel-task" data-id="${t.id}" style="background:#dc2626;border-color:#b91c1c;font-weight:700;" title="强行中止当前正在运行的任务并释放资源与槽位">⏹ 强制停止</button>` : ""}
            ${["queued", "retry_wait"].includes(t.status) ? `<button class="btn btn-danger btn-sm btn-cancel-task" data-id="${t.id}" title="取消排队中的任务">⏹ 取消</button>` : ""}
            ${!isImageTask && !isAudioTask && t.status === "completed" && t.engine !== "gemini" ? `<button class="btn btn-secondary btn-sm btn-view-qa" data-id="${t.id}">🔍 质检对比</button>` : ""}
            <button class="btn btn-secondary btn-sm btn-view-log" data-id="${t.id}">📋 日志</button>
            ${(t.status === "failed" || t.status === "retry_wait" || t.status === "cancelled") && !["WIRE_FORMAT_MISMATCH", "UNSUPPORTED_FEATURE"].includes(t.error_code) ? `<button class="btn btn-warning btn-sm btn-retry-task" data-id="${t.id}" title="重新排队；保留原账号绑定，等待调度">🔄 重新排队</button>` : ""}
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm btn-open-folder" data-id="${t.id}" title="在资源管理器中打开">📂</button>
            <button class="btn btn-secondary btn-sm btn-delete-task" data-id="${t.id}" title="删除该任务记录及产物文件" style="color:var(--red-err);">🗑️</button>
          </div>
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

    // 绑定复选框选择事件
    container.querySelectorAll(".task-item-checkbox").forEach(chk => {
      chk.addEventListener("change", (e) => {
        const id = chk.getAttribute("data-id");
        if (chk.checked) {
          state.selectedTaskIds.add(id);
          chk.closest(".task-card")?.classList.add("selected");
        } else {
          state.selectedTaskIds.delete(id);
          chk.closest(".task-card")?.classList.remove("selected");
        }
        updateBatchActionBar();
      });
      chk.addEventListener("click", (e) => e.stopPropagation());
    });

    // 单任务删除事件
    container.querySelectorAll(".btn-delete-task").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        if (!confirm(`确定要删除任务记录 [${id}] 吗？\n未共享的受管理产物会隔离到回收目录；外部原素材与共享产物保留。恢复需要维护工具。`)) {
          return;
        }
        try {
          const resp = await fetch("/api/tasks/" + id, { method: "DELETE" });
          if (resp.ok) {
            state.selectedTaskIds.delete(id);
            showToast("任务 " + id + " 已删除（产物隔离保存）", "success");
            fetchTasks(true);
          } else {
            const err = await resp.json().catch(() => ({}));
            showToast("删除失败: " + (err.detail || resp.statusText), "error");
          }
        } catch (e) {
          showToast("网络错误: " + e.message, "error");
        }
      });
    });

    // 单任务取消与强制停止事件
    container.querySelectorAll(".btn-cancel-task").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const isRunning = b.textContent.includes("停止");
        const msg = isRunning ? `确定要强行中止正在运行的任务 [${id}] 吗？将立即终止底层执行进程并释放账号。` : `确定要取消排队中的任务 [${id}] 吗？`;
        if (!confirm(msg)) {
          return;
        }
        try {
          const endpoint = isRunning ? `/api/tasks/${id}/stop` : `/api/tasks/${id}/cancel`;
          const resp = await fetch(endpoint, { method: "POST" });
          if (resp.ok) {
            showToast("任务 " + id + (isRunning ? " 已强制中止并释放资源" : " 已取消"), "info");
            fetchTasks(true);
            fetchOverview();
          } else {
            const errData = await resp.json().catch(() => ({}));
            showToast("操作失败: " + (errData.detail || resp.statusText), "error");
          }
        } catch (e) {
          showToast("网络错误: " + e.message, "error");
        }
      });
    });

    // 一键复制本地绝对路径（直接在 Google Vids 导入窗口粘贴）
    container.querySelectorAll(".btn-copy-video-path").forEach(b => {
      b.addEventListener("click", () => {
        let p = b.getAttribute("data-path");
        if (!p) {
          const id = b.getAttribute("data-id");
          p = `C:\\Users\\win10\\Documents\\ChatGPT\\视频制作\\video_farm_data\\outputs\\${id}.mp4`;
        }
        navigator.clipboard.writeText(p).then(() => {
          showToast("已复制本地绝对路径: " + p.split(/[\\/]/).pop() + "（可直接在 Google Vids 导入窗口粘贴）", "success");
        }).catch(() => {
          prompt("请复制本地绝对路径（可在 Google Vids 导入窗口粘贴）：", p);
        });
      });
    });

    updateBatchActionBar();
  }

  function getCurrentFilteredTasks() {
    let filtered = state.tasks || [];
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
    return filtered;
  }

  function updateBatchActionBar() {
    if (!el.batchActionBar) return;
    const currentTasks = getCurrentFilteredTasks();
    const currentIds = currentTasks.map(t => t.id);
    const selectedInCurrent = currentIds.filter(id => state.selectedTaskIds.has(id));
    const totalSelected = state.selectedTaskIds.size;
    
    let readyVideoCount = 0;
    (state.tasks || []).forEach(t => {
      if (state.selectedTaskIds.has(t.id)) {
        if (t.has_video || (t.task_type === "image" && t.status === "completed" && t.image_urls && t.image_urls.length > 0)) {
          readyVideoCount++;
        }
      }
    });

    if (el.batchStatsText) {
      el.batchStatsText.innerHTML = `已选中 <b>${totalSelected}</b> 项 (成片 <b>${readyVideoCount}</b> 个)`;
    }

    if (el.btnBatchDownload) {
      el.btnBatchDownload.disabled = (readyVideoCount === 0);
      el.btnBatchDownload.innerHTML = `📥 批量保存下载视频 (${readyVideoCount}) (ZIP)`;
    }

    if (el.btnBatchCancel) {
      el.btnBatchCancel.disabled = (totalSelected === 0);
      el.btnBatchCancel.innerHTML = `⏹ 批量停止/取消 (${totalSelected})`;
    }

    if (el.btnBatchCancel) {
    el.btnBatchCancel.addEventListener("click", async () => {
      const ids = Array.from(state.selectedTaskIds);
      if (ids.length === 0) return;
      if (!confirm(`确定要强行停止/取消选中的 ${ids.length} 个任务吗？\n如果任务正在运行，将立即终止底层执行进程并释放账号与调度槽位。`)) {
        return;
      }
      try {
        const resp = await fetch("/api/tasks/batch/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task_ids: ids })
        });
        const res = await resp.json().catch(() => ({}));
        if (resp.ok) {
          showToast(`已成功停止/取消 ${res.cancelled_count ?? ids.length} 个任务并释放槽位`, "info");
          fetchTasks(true);
          fetchOverview();
        } else {
          showToast("批量停止失败: " + (res.detail || resp.statusText), "error");
        }
      } catch (e) {
        showToast("网络请求失败: " + e.message, "error");
      }
    });
  }

  if (el.btnBatchDelete) {
      el.btnBatchDelete.disabled = (totalSelected === 0);
      el.btnBatchDelete.innerHTML = `🗑️ 批量删除选中 (${totalSelected})`;
    }

    if (el.batchSelectAllChk) {
      if (currentIds.length > 0 && selectedInCurrent.length === currentIds.length) {
        el.batchSelectAllChk.checked = true;
        el.batchSelectAllChk.indeterminate = false;
      } else if (selectedInCurrent.length > 0) {
        el.batchSelectAllChk.checked = false;
        el.batchSelectAllChk.indeterminate = true;
      } else {
        el.batchSelectAllChk.checked = false;
        el.batchSelectAllChk.indeterminate = false;
      }
    }
  }

  // 绑定批量操作条控制逻辑
  if (el.batchSelectAllChk) {
    el.batchSelectAllChk.addEventListener("change", () => {
      const currentTasks = getCurrentFilteredTasks();
      if (el.batchSelectAllChk.checked) {
        currentTasks.forEach(t => state.selectedTaskIds.add(t.id));
      } else {
        currentTasks.forEach(t => state.selectedTaskIds.delete(t.id));
      }
      renderTasks();
    });
  }

  if (el.btnBatchInvert) {
    el.btnBatchInvert.addEventListener("click", () => {
      const currentTasks = getCurrentFilteredTasks();
      currentTasks.forEach(t => {
        if (state.selectedTaskIds.has(t.id)) {
          state.selectedTaskIds.delete(t.id);
        } else {
          state.selectedTaskIds.add(t.id);
        }
      });
      renderTasks();
    });
  }

  if (el.btnBatchClear) {
    el.btnBatchClear.addEventListener("click", () => {
      state.selectedTaskIds.clear();
      renderTasks();
    });
  }

  const selectAllCompletedTasks = () => {
    let addedCount = 0;
    (state.tasks || []).forEach(t => {
      if (t.status === "completed") {
        if (t.has_video || (t.task_type === "image" && t.image_urls && t.image_urls.length > 0)) {
          state.selectedTaskIds.add(t.id);
          addedCount++;
        }
      }
    });
    renderTasks();
    if (addedCount > 0) {
      showToast(`已一键全选 ${addedCount} 个已完成成片，可直接点击右侧下载 ZIP！`, "success");
      el.batchActionBar?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else {
      showToast("当前暂无已生成完成的媒体成片", "warning");
    }
  };

  if (el.btnBatchSelectCompleted) {
    el.btnBatchSelectCompleted.addEventListener("click", selectAllCompletedTasks);
  }

  if (el.btnQuickSelectCompleted) {
    el.btnQuickSelectCompleted.addEventListener("click", selectAllCompletedTasks);
  }

  if (el.btnBatchDownload) {
    el.btnBatchDownload.addEventListener("click", () => {
      const readyIds = [];
      (state.tasks || []).forEach(t => {
        if (state.selectedTaskIds.has(t.id)) {
          if (t.has_video || (t.task_type === "image" && t.status === "completed" && t.image_urls && t.image_urls.length > 0)) {
            readyIds.push(t.id);
          }
        }
      });
      if (readyIds.length === 0) {
        showToast("选中的任务中暂无已生成完成的媒体文件", "warning");
        return;
      }
      showToast(`正在打包下载 ${readyIds.length} 个视频/图片产物，请稍候...`, "info");
      window.location.href = `/api/tasks/batch-download-zip?task_ids=${encodeURIComponent(readyIds.join(","))}`;
    });
  }

  if (el.btnBatchCancel) {
    el.btnBatchCancel.addEventListener("click", async () => {
      const ids = Array.from(state.selectedTaskIds);
      if (ids.length === 0) return;
      if (!confirm(`确定要强行停止/取消选中的 ${ids.length} 个任务吗？\n如果任务正在运行，将立即终止底层执行进程并释放账号与调度槽位。`)) {
        return;
      }
      try {
        const resp = await fetch("/api/tasks/batch/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task_ids: ids })
        });
        const res = await resp.json().catch(() => ({}));
        if (resp.ok) {
          showToast(`已成功停止/取消 ${res.cancelled_count ?? ids.length} 个任务并释放槽位`, "info");
          fetchTasks(true);
          fetchOverview();
        } else {
          showToast("批量停止失败: " + (res.detail || resp.statusText), "error");
        }
      } catch (e) {
        showToast("网络请求失败: " + e.message, "error");
      }
    });
  }

  if (el.btnBatchDelete) {
    el.btnBatchDelete.addEventListener("click", async () => {
      const ids = Array.from(state.selectedTaskIds);
      if (ids.length === 0) return;
      if (!confirm(`确定要删除已选中的 ${ids.length} 个任务吗？\n运行中任务不会删除；受管理产物隔离保存，外部原素材及共享文件保留。`)) {
        return;
      }
      try {
        const resp = await fetch("/api/tasks/batch-delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task_ids: ids })
        });
        const res = await resp.json().catch(() => ({}));
        if (resp.ok) {
          state.selectedTaskIds.clear();
          showToast(`已删除 ${res.deleted_count ?? 0} 个任务，${(res.results || []).filter(r => !r.deleted).length} 个未删除；产物隔离保存`, res.success ? "success" : "warning");
          fetchTasks(true);
        } else {
          showToast("批量删除失败: " + (res.detail || resp.statusText), "error");
        }
      } catch (e) {
        showToast("网络请求失败: " + e.message, "error");
      }
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
          fetchTasks();
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
          在左侧输入画面提示词，选择模型（如 当前账号可用模型），点击【立即生成图片】开始创作！
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    imageItems.forEach(item => {
      const card = document.createElement("div");
      card.className = "gallery-card";
      const modelLabel = item.model === "nano-pro" ? "Nano Banana Pro" : (item.model === "nano2" ? "Nano Banana 2" : (item.model === "imagen4" ? "Imagen（imagen4 路由）" : item.model));
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
      el.playerMeta.textContent = "实际文件: " + w + " × " + h + " · " + dur + " 秒 · 水印状态请查看质检";
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

      el.qaModalSub.textContent = (t.engine === "gemini" ? "Gemini 视频" : "Google Flow") + " · 请求画幅: " + (t.aspect_ratio || "未记录") + " · 请求时长: " + (t.duration_sec || 8) + "s（实际规格以成片为准）";

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
        el.qaWatermarkTitle.textContent = "可见水印检测: ✓ 抽查区域未检出";
        el.qaWatermarkDetail.textContent = "当前右下角抽查区域未检出可见水印特征，不代表全画面无水印。本工具不检测或验证隐形数字水印；商业使用前仍需人工复核及确认授权。";
      } else if (t.watermark_check === "forced_visible") {
        el.qaWatermarkTitle.textContent = "可见水印检测: ⚠️ 存在可见水印 (Watermarked)";
        el.qaWatermarkDetail.textContent = "检测到右下角有高对比度水印特征。建议仅作为初版草稿预览使用。";
      } else {
        el.qaWatermarkTitle.textContent = "可见水印检测: --";
        el.qaWatermarkDetail.textContent = "尚无可确认的水印分析结果，请人工检查成片。";
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
            <div class="prof-title">${escapeHtml(p.name)}</div>
            <div class="prof-desc">${escapeHtml(p.account_label || "独立 Chrome Profile 隔离")}</div>
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
          <button class="btn btn-primary btn-sm btn-auto-onboard" data-id="${p.id}" data-name="${escapeHtml(p.name)}" style="width:100%; background:linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); border:none; font-weight:600; color:#fff;" title="针对新添加账号：全自动模拟跳过一次性服务条款/欢迎弹窗，并自动创建默认工程">
            ✨ 自动过协议与初始化
          </button>
          <div style="display:flex; gap:6px; width:100%;">
            <button class="btn btn-secondary btn-sm btn-login-flow" data-id="${p.id}" data-name="${escapeHtml(p.name)}" style="flex:1;" title="打开真实 Chrome 登录 Google Flow。若有弹窗点一次同意后关闭 Chrome 即可">
              🔑 打开 Flow 点同意
            </button>
            <button class="btn btn-secondary btn-sm btn-login-gemini" data-id="${p.id}" data-name="${escapeHtml(p.name)}" style="flex:1;" title="打开真实 Chrome 登录 Gemini 网页版">
              🌐 登录 Gemini
            </button>
          </div>
          <div style="display:flex; gap:6px; width:100%;">
            <button class="btn btn-secondary btn-sm btn-verify-profile" data-id="${p.id}" data-name="${escapeHtml(p.name)}" style="flex:1; border-color:var(--blue-primary); color:var(--blue-primary);" title="无头检测登录凭据状态，有效则直接恢复空闲就绪">
              🔍 验证登录
            </button>
            <button class="btn btn-secondary btn-sm btn-kill-chrome" data-id="${p.id}" data-name="${escapeHtml(p.name)}" style="flex:1; border-color:var(--orange-warn); color:var(--orange-warn);" title="强制关闭占用该 Profile 的 Chrome 进程并解除锁定">
              ⏹ 关占用 Chrome
            </button>
          </div>
          
          ${(p.status === "cooldown" || p.status === "auth_expired") ? `
            <button class="btn btn-warning btn-sm btn-reset-profile" data-id="${p.id}" data-name="${escapeHtml(p.name)}" style="width:100%; margin-bottom:4px;" title="清除冷却或异常标记，立即恢复为空闲就绪">
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

    const geminiProfSel = document.getElementById("gemini-active-profile");
    if (geminiProfSel) {
      const savedPid = localStorage.getItem("gemini_hub_profile_id");
      const curGVal = geminiProfSel.value || savedPid || "";
      geminiProfSel.innerHTML = "";
      state.profiles.forEach(p => {
        if (p.enabled) {
          const opt = document.createElement("option");
          opt.value = p.id;
          opt.textContent = `${p.name} (${p.account_label || "Google"}) [${p.status}]`;
          geminiProfSel.appendChild(opt);
        }
      });
      if (curGVal && Array.from(geminiProfSel.options).some(o => o.value === curGVal)) {
        geminiProfSel.value = curGVal;
      } else if (geminiProfSel.options.length > 0) {
        geminiProfSel.selectedIndex = 0;
      }
      if (geminiProfSel.value) {
        localStorage.setItem("gemini_hub_profile_id", geminiProfSel.value);
      }
    }

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

    const audioSel = document.getElementById("audio-profile-select");
    const currentAudioVal = audioSel ? audioSel.value : "auto";
    if (audioSel) {
      audioSel.innerHTML = '<option value="auto">⚡ 自动负载均衡 (自动分配最空闲账号)</option>';
      state.profiles.forEach(p => {
        if (p.enabled) {
          const opt = document.createElement("option");
          opt.value = p.id;
          opt.textContent = p.name + " (" + (p.account_label || "无备注") + ") [" + p.status + "]";
          audioSel.appendChild(opt);
        }
      });
      audioSel.value = currentAudioVal || "auto";
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

  
  // ==================== Gemini 智能配音与多模态音频工作台 ====================
  function selectVideoForAudioWorkbench(videoId, videoUrl, videoPath, prompt) {
    const audioTabBtn = document.querySelector('.tab-button[data-target="view-audio"]');
    if (audioTabBtn) {
      audioTabBtn.click();
    }
    const inputPath = document.getElementById("audio-input-video-path");
    if (inputPath) inputPath.value = videoPath || videoUrl;

    const previewBox = document.getElementById("audio-preview-box");
    const previewPlayer = document.getElementById("audio-preview-player");
    const previewTitle = document.getElementById("audio-preview-filename");
    if (previewPlayer && previewBox) {
      previewPlayer.src = videoUrl;
      previewBox.style.display = "block";
      if (previewTitle) previewTitle.textContent = `任务 [${videoId}] 成片画面预览`;
    }

    const selectComp = document.getElementById("audio-select-completed-video");
    if (selectComp) {
      selectComp.value = videoId;
    }

    const promptInput = document.getElementById("audio-prompt-input");
    if (promptInput && !promptInput.value.trim() && prompt) {
      promptInput.value = `请针对画面（${prompt.slice(0, 45)}...）生成匹配节奏的高清解说旁白。`;
    }

    showToast(`已将视频 [${videoId}] 载入智能配音工作台`, "info");
    const audioPane = document.getElementById("view-audio");
    if (audioPane) audioPane.scrollIntoView({ behavior: "smooth" });
  }

  let audioCompletedVideos = [];
  let audioVideosRequest = null;
  async function updateAudioCompletedVideos() {
    if (audioVideosRequest) return audioVideosRequest;
    audioVideosRequest = (async () => {
      const all = [];
      let offset = 0, total = 1;
      while (offset < total) {
        const response = await fetch(`/api/tasks?status=completed&limit=500&offset=${offset}`);
        if (!response.ok) throw new Error("成片列表读取失败");
        const items = await response.json();
        total = Number(response.headers.get("X-Total-Count") || items.length);
        all.push(...items);
        if (!items.length) break;
        offset += items.length;
      }
      audioCompletedVideos = all.filter(t => t.has_video);
      renderAudioCompletedVideos();
    })();
    try { await audioVideosRequest; return true; }
    catch (error) { console.error(error); showToast("成片列表读取失败，请点击刷新重试", "error"); return false; }
    finally { audioVideosRequest = null; }
  }
  function renderAudioCompletedVideos() {
    const sel = document.getElementById("audio-select-completed-video");
    if (!sel) return;
    const currentVal = sel.value;
    const compVideos = audioCompletedVideos;

    sel.innerHTML = '<option value="">-- 点击下拉选择已生成的视频成片 --</option>';
    compVideos.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.id;
      const vUrl = t.video_url || ('/media/outputs/' + (t.output_video_path ? t.output_video_path.split(/[\\/]/).pop() : ''));
      opt.setAttribute("data-url", vUrl);
      opt.setAttribute("data-path", t.output_video_path || "");
      const shortPrompt = t.prompt ? t.prompt.slice(0, 30) : "视频成片";
      opt.textContent = `[${t.id}] ${shortPrompt}... (${t.duration_sec || 8}s)`;
      sel.appendChild(opt);
    });

    if (currentVal) {
      sel.value = currentVal;
    }
  }

  function initAudioWorkbench() { return; // 本地配音功能已下线
    const selCompVideo = document.getElementById("audio-select-completed-video");
    const inputVideoPath = document.getElementById("audio-input-video-path");
    const uploadVideoFile = document.getElementById("audio-upload-video-file");
    const previewBox = document.getElementById("audio-preview-box");
    const previewPlayer = document.getElementById("audio-preview-player");
    const previewTitle = document.getElementById("audio-preview-filename");
    const btnClearPreview = document.getElementById("btn-audio-clear-preview");
    const btnRefreshVideoSel = document.getElementById("btn-refresh-audio-video-select");
    const refImgPath = document.getElementById("audio-ref-image-path");
    const uploadRefImg = document.getElementById("audio-upload-ref-img");
    const promptInput = document.getElementById("audio-prompt-input");
    const voiceSelect = document.getElementById("audio-voice-select");
    const profileSelect = document.getElementById("audio-profile-select");
    const btnSubmitAudio = document.getElementById("btn-submit-audio-task");
    const btnResetAudio = document.getElementById("btn-audio-reset-form");
    const submitStatus = document.getElementById("audio-submit-status");

    // 下拉选择成片联动
    if (selCompVideo) {
      selCompVideo.addEventListener("change", () => {
        const selectedId = selCompVideo.value;
        if (!selectedId) return;
        const task = audioCompletedVideos.find(t => t.id === selectedId);
        if (task) {
          const vUrl = task.video_url || ('/media/outputs/' + (task.output_video_path ? task.output_video_path.split(/[\\/]/).pop() : ''));
          const vPath = task.output_video_path || vUrl;
          if (inputVideoPath) inputVideoPath.value = vPath;
          if (previewPlayer && previewBox) {
            previewPlayer.src = vUrl;
            previewBox.style.display = "block";
            if (previewTitle) previewTitle.textContent = `任务 [${task.id}] 成片画面预览`;
          }
          if (uploadVideoFile) uploadVideoFile.value = "";
        }
      });
    }

    // 上传本地视频文件
    if (uploadVideoFile) {
      uploadVideoFile.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if (file) {
          const blobUrl = URL.createObjectURL(file);
          if (previewPlayer && previewBox) {
            previewPlayer.src = blobUrl;
            previewBox.style.display = "block";
            if (previewTitle) previewTitle.textContent = `已选本地视频: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)`;
          }
          if (inputVideoPath) inputVideoPath.value = "";
          if (selCompVideo) selCompVideo.value = "";
        }
      });
    }

    // 移除画面预览
    if (btnClearPreview) {
      btnClearPreview.addEventListener("click", () => {
        if (previewPlayer) {
          previewPlayer.pause();
          previewPlayer.src = "";
        }
        if (previewBox) previewBox.style.display = "none";
        if (selCompVideo) selCompVideo.value = "";
        if (inputVideoPath) inputVideoPath.value = "";
        if (uploadVideoFile) uploadVideoFile.value = "";
      });
    }

    // 刷新成片下拉列表
    if (btnRefreshVideoSel) {
      btnRefreshVideoSel.addEventListener("click", async () => {
        await fetchTasks(true);
        if (await updateAudioCompletedVideos()) showToast("已刷新成片视频列表", "info");
      });
    }

    // 上传参考图
    if (uploadRefImg) {
      uploadRefImg.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if (file && refImgPath) {
          refImgPath.value = file.name;
          showToast(`已选择参考图: ${file.name}`, "info");
        }
      });
    }

    // 快捷灵感标签点击直接追加或填入
    document.querySelectorAll(".btn-audio-preset").forEach(btn => {
      btn.addEventListener("click", () => {
        const text = btn.getAttribute("data-text");
        if (promptInput && text) {
          if (!promptInput.value.trim()) {
            promptInput.value = text;
          } else {
            promptInput.value += "\n" + text;
          }
          promptInput.focus();
          showToast("已填入灵感文案模板", "info");
        }
      });
    });

    // 表单清空与重置
    if (btnResetAudio) {
      btnResetAudio.addEventListener("click", () => {
        if (promptInput) promptInput.value = "";
        if (refImgPath) refImgPath.value = "";
        if (uploadRefImg) uploadRefImg.value = "";
        if (voiceSelect) voiceSelect.value = "zh-CN-YunxiNeural";
        if (profileSelect) profileSelect.value = "auto";
        if (btnClearPreview) btnClearPreview.click();
        if (submitStatus) submitStatus.innerHTML = "";
        showToast("已重置配音工作台表单", "info");
      });
    }

    // 提交生成任务
    if (btnSubmitAudio) {
      btnSubmitAudio.addEventListener("click", async () => {
        const prompt = promptInput ? promptInput.value.trim() : "";
        if (!prompt) {
          showToast("请输入配音台词或提示词", "warn");
          if (promptInput) promptInput.focus();
          return;
        }

        btnSubmitAudio.disabled = true;
        btnSubmitAudio.innerHTML = "<span>⏳ 正在提交配音任务...</span>";
        if (submitStatus) submitStatus.innerHTML = '<span style="color:#38bdf8;">正在提交配音任务并调度账号...</span>';

        const formData = new FormData();
        formData.append("prompt", prompt);
        const voiceVal = voiceSelect ? voiceSelect.value : "zh-CN-YunxiNeural";
        formData.append("voice", voiceVal);
        formData.append("model", voiceVal);

        if (uploadVideoFile && uploadVideoFile.files && uploadVideoFile.files[0]) {
          formData.append("input_video", uploadVideoFile.files[0]);
        } else if (inputVideoPath && inputVideoPath.value.trim()) {
          formData.append("input_video_path", inputVideoPath.value.trim());
        }

        if (uploadRefImg && uploadRefImg.files && uploadRefImg.files[0]) {
          formData.append("ref_image", uploadRefImg.files[0]);
        } else if (refImgPath && refImgPath.value.trim()) {
          formData.append("ref_image_path", refImgPath.value.trim());
        }

        if (profileSelect && profileSelect.value && profileSelect.value !== "auto") {
          formData.append("assigned_profile_id", profileSelect.value);
        }

        try {
          const resp = await fetch("/api/tasks/create-audio", {
            method: "POST",
            body: formData
          });
          const data = await resp.json();
          if (resp.ok) {
            showToast(`🚀 智能配音任务 ${data.id} 已成功加入队列！`, "success");
            if (submitStatus) submitStatus.innerHTML = `<span style="color:#10b981;">✅ 任务已创建: ${data.id}</span>`;
            
            // 切换到任务与成片 Tab，并激活音频筛选
            const tasksTabBtn = document.querySelector('.tab-button[data-target="view-tasks"]');
            if (tasksTabBtn) {
              tasksTabBtn.click();
              const audioFilterBtn = document.querySelector('.filter-btn[data-filter="audio"]');
              if (audioFilterBtn) {
                audioFilterBtn.click();
              }
            }
            await fetchTasks(true);
          } else {
            showToast("配音任务提交失败: " + (data.detail || "未知错误"), "error");
            if (submitStatus) submitStatus.innerHTML = `<span style="color:#ef4444;">❌ 提交失败: ${escapeHtml(data.detail || "未知错误")}</span>`;
          }
        } catch (err) {
          showToast("网络错误: " + err.message, "error");
          if (submitStatus) submitStatus.innerHTML = `<span style="color:#ef4444;">❌ 网络错误: ${escapeHtml(err.message)}</span>`;
        } finally {
          btnSubmitAudio.disabled = false;
          btnSubmitAudio.innerHTML = "<span>🚀 一键生成智能配音与音频</span>";
        }
      });
    }
  }

  // 初始化智能配音工作台
  initAudioWorkbench();
  // 初始化 Gemini 多模态创作中心
  initGeminiHub();

// Gemini Hub Part 1

function initGeminiHub() {
  let currentMode = "chat";
  let attachedVideoFile = null;
  let attachedVideoPath = "";
  let attachedImageFile = null;
  let attachedImagePath = "";

  const activeProfSel = document.getElementById("gemini-active-profile");
  const profStatusBadge = document.getElementById("gemini-profile-status-badge");
  const btnLaunchChrome = document.getElementById("btn-gemini-launch-chrome");
  const btnTestConn = document.getElementById("btn-gemini-test-conn");
  const btnUnlockChrome = document.getElementById("btn-gemini-unlock-chrome");

  const chatStatus = document.getElementById("gemini-chat-status");
  const btnClearChat = document.getElementById("btn-gemini-clear-chat");
  const feed = document.getElementById("gemini-messages-feed");
  const chatInput = document.getElementById("gemini-chat-input");
  const btnSend = document.getElementById("btn-gemini-chat-send");

  const modeBtns = document.querySelectorAll(".gemini-mode-btn");
  const voiceGroup = document.getElementById("gemini-voice-control-group");
  const aspectGroup = document.getElementById("gemini-aspect-control-group");
  const voiceSelect = document.getElementById("gemini-voice-select");
  const aspectSelect = document.getElementById("gemini-aspect-select");

  const attachmentBar = document.getElementById("gemini-attachment-bar");
  const videoBadge = document.getElementById("gemini-video-badge");
  const videoName = document.getElementById("gemini-video-name");
  const btnRemoveVideo = document.getElementById("btn-remove-gemini-video");
  const imageBadge = document.getElementById("gemini-image-badge");
  const imageName = document.getElementById("gemini-image-name");
  const btnRemoveImage = document.getElementById("btn-remove-gemini-image");

  const fileVideo = document.getElementById("file-gemini-video");
  const fileImage = document.getElementById("file-gemini-image");
  const btnAttachVideo = document.getElementById("btn-gemini-attach-video");
  const btnPickCompleted = document.getElementById("btn-gemini-pick-completed");
  const btnAttachImage = document.getElementById("btn-gemini-attach-image");

  const videoViewer = document.getElementById("gemini-video-viewer");
  const videoPlaceholder = document.getElementById("gemini-video-placeholder");
  const quickSelectVideo = document.getElementById("gemini-quick-select-video");
  const btnRefreshVids = document.getElementById("btn-gemini-refresh-vids");

  const assetTabs = document.querySelectorAll(".gemini-asset-tab");
  const paneGallery = document.getElementById("pane-gemini-gallery");
  const paneAudio = document.getElementById("pane-gemini-audio");
  const paneVideo = document.getElementById("pane-gemini-video");
  const galleryGrid = document.getElementById("gemini-gallery-grid");
  const galleryEmpty = document.getElementById("gemini-gallery-empty");
  const galleryCount = document.getElementById("gemini-gallery-count");
  const audioList = document.getElementById("gemini-audio-list");
  const audioEmpty = document.getElementById("gemini-audio-empty");
  const audioCount = document.getElementById("gemini-audio-count");
  const btnRefreshAssets = document.getElementById("btn-refresh-gemini-assets");

  function updateProfBadge() {
    if (!activeProfSel || !profStatusBadge) return;
    const pid = activeProfSel.value;
    if (pid === "auto") {
      profStatusBadge.textContent = "⚡ 自动轮转";
      profStatusBadge.style.background = "#ecfdf5";
      profStatusBadge.style.color = "#047857";
      return;
    }
    const p = state.profiles.find(x => x.id === pid || x.name === pid);
    if (p) {
      if (p.status === "busy") {
        profStatusBadge.textContent = "⏳ 忙碌中";
        profStatusBadge.style.background = "#fef3c7";
        profStatusBadge.style.color = "#b45309";
      } else if (p.status === "auth_expired") {
        profStatusBadge.textContent = "⚠️ 需登录授权";
        profStatusBadge.style.background = "#fee2e2";
        profStatusBadge.style.color = "#b91c1c";
      } else {
        profStatusBadge.textContent = "🟢 空闲就绪";
        profStatusBadge.style.background = "#ecfdf5";
        profStatusBadge.style.color = "#047857";
      }
    }
  }

  if (activeProfSel) {
    activeProfSel.addEventListener("change", () => {
      if (activeProfSel.value) {
        localStorage.setItem("gemini_hub_profile_id", activeProfSel.value);
      }
      updateProfBadge();
      const p = state.profiles.find(x => x.id === activeProfSel.value);
      if (p) showToast(`已锁定对话账号为: ${p.name}，多轮对话上下文将持续保持`, "info");
    });
  }

  if (btnLaunchChrome) {
    btnLaunchChrome.addEventListener("click", async () => {
      let pid = activeProfSel ? activeProfSel.value : "auto";
      if (pid === "auto") {
        if (state.profiles.length > 0) pid = state.profiles[0].id;
        else { showToast("暂无可用 Profile，请先添加账号", "warn"); return; }
      }
      showToast("正在拉起独立 Chrome 登录窗口...", "info");
      try {
        const resp = await fetch("/api/profiles/" + pid + "/launch-gemini-login", { method: "POST" });
        const data = await resp.json();
        if (resp.ok) {
          showToast(data.message || "已启动 Chrome 登录窗口，登录后请关闭窗口", "success");
        } else {
          showToast(data.detail || "启动登录失败", "error");
        }
      } catch (e) {
        showToast("请求异常: " + e.message, "error");
      }
    });
  }

  if (btnTestConn) {
    btnTestConn.addEventListener("click", async () => {
      let pid = activeProfSel ? activeProfSel.value : "auto";
      if (pid === "auto") {
        if (state.profiles.length > 0) pid = state.profiles[0].id;
        else { showToast("暂无可用 Profile", "warn"); return; }
      }
      showToast("正在检查账号连通性与目录状态...", "info");
      try {
        const resp = await fetch("/api/profiles/" + pid + "/test-gemini", { method: "POST" });
        const data = await resp.json();
        if (data.success) {
          showToast(data.message || "账号状态良好，可正常发起多模态任务！", "success");
        } else {
          showToast(data.message || "检测发现问题", "warn");
        }
        await fetchProfiles(true);
        updateProfBadge();
      } catch (e) {
        showToast("检查失败: " + e.message, "error");
      }
    });
  }

  if (btnUnlockChrome) {
    btnUnlockChrome.addEventListener("click", async () => {
      let pid = activeProfSel ? activeProfSel.value : "auto";
      if (pid === "auto") {
        if (state.profiles.length > 0) pid = state.profiles[0].id;
        else return;
      }
      try {
        const resp = await fetch("/api/profiles/" + pid + "/close-chrome", { method: "POST" });
        const data = await resp.json();
        showToast(data.message || "已释放 Chrome 占用锁并重置为空闲", "success");
        await fetchProfiles(true);
        updateProfBadge();
      } catch (e) {
        showToast("释放锁失败: " + e.message, "error");
      }
    });
  }

  modeBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      modeBtns.forEach(b => b.classList.remove("active", "btn-primary"));
      btn.classList.add("active");
      currentMode = btn.getAttribute("data-mode") || "chat";
      if (currentMode === "chat") {
        if (chatInput) chatInput.placeholder = "像 ChatGPT / Gemini 网页端一样输入对话内容、分镜剧本润色或提问... (Enter 发送, Shift+Enter 换行)";
        if (voiceGroup) voiceGroup.style.display = "flex";
        if (aspectGroup) aspectGroup.style.display = "none";
      } else if (currentMode === "dubbing") {
        if (chatInput) chatInput.placeholder = "输入自定义配音台词，或直接上传视频让 Gemini 深度分析画面自动生成高保真配音... (Enter 发送)";
        if (voiceGroup) voiceGroup.style.display = "flex";
        if (aspectGroup) aspectGroup.style.display = "none";
      } else if (currentMode === "image") {
        if (chatInput) chatInput.placeholder = "输入 AI 绘画提示词，如：高品质4K科技农业现代生态大棚，金黄色晨曦写实插画... (Enter 发送)";
        if (voiceGroup) voiceGroup.style.display = "none";
        if (aspectGroup) aspectGroup.style.display = "flex";
      }
    });
  });

  document.querySelectorAll(".btn-gemini-prompt-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const txt = chip.getAttribute("data-text");
      if (chatInput && txt) {
        chatInput.value = txt;
        chatInput.focus();
        showToast("已填入灵感提示词", "info");
      }
    });
  });

  function updateAttachmentBar() {
    if (!attachmentBar) return;
    const hasV = Boolean(attachedVideoFile || attachedVideoPath);
    const hasI = Boolean(attachedImageFile || attachedImagePath);
    attachmentBar.style.display = (hasV || hasI) ? "flex" : "none";
    if (videoBadge) videoBadge.style.display = hasV ? "flex" : "none";
    if (imageBadge) imageBadge.style.display = hasI ? "flex" : "none";

    if (hasV && videoName) {
      videoName.textContent = attachedVideoFile ? attachedVideoFile.name : (attachedVideoPath.split(/[\\/]/).pop() || "视频附件");
    }
    if (hasI && imageName) {
      imageName.textContent = attachedImageFile ? attachedImageFile.name : (attachedImagePath.split(/[\\/]/).pop() || "参考图片");
    }
  }

  function setAttachedVideo(fileOrUrl, isUrl = false) {
    if (isUrl) {
      attachedVideoPath = fileOrUrl;
      attachedVideoFile = null;
      if (videoViewer) {
        videoViewer.src = fileOrUrl;
        videoViewer.style.display = "block";
      }
      if (videoPlaceholder) videoPlaceholder.style.display = "none";
    } else {
      attachedVideoFile = fileOrUrl;
      attachedVideoPath = "";
      if (fileOrUrl && videoViewer) {
        const blobUrl = URL.createObjectURL(fileOrUrl);
        videoViewer.src = blobUrl;
        videoViewer.style.display = "block";
        if (videoPlaceholder) videoPlaceholder.style.display = "none";
      }
    }
    const dubBtn = document.querySelector(".gemini-mode-btn[data-mode=\"dubbing\"]");
    if (dubBtn) dubBtn.click();
    updateAttachmentBar();
    const vTab = document.querySelector(".gemini-asset-tab[data-tab=\"video\"]");
    if (vTab) vTab.click();
    showToast("已成功挂载参考视频", "info");
  }

  if (btnAttachVideo && fileVideo) {
    btnAttachVideo.addEventListener("click", () => fileVideo.click());
    fileVideo.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        setAttachedVideo(e.target.files[0], false);
      }
    });
  }

  if (btnRemoveVideo) {
    btnRemoveVideo.addEventListener("click", () => {
      attachedVideoFile = null;
      attachedVideoPath = "";
      if (fileVideo) fileVideo.value = "";
      if (videoViewer) { videoViewer.pause(); videoViewer.src = ""; videoViewer.style.display = "none"; }
      if (videoPlaceholder) videoPlaceholder.style.display = "block";
      updateAttachmentBar();
      showToast("已移除参考视频", "info");
    });
  }

  if (btnAttachImage && fileImage) {
    btnAttachImage.addEventListener("click", () => fileImage.click());
    fileImage.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        attachedImageFile = e.target.files[0];
        attachedImagePath = "";
        updateAttachmentBar();
        showToast("已挂载参考图片: " + e.target.files[0].name, "info");
      }
    });
  }

  if (btnRemoveImage) {
    btnRemoveImage.addEventListener("click", () => {
      attachedImageFile = null;
      attachedImagePath = "";
      if (fileImage) fileImage.value = "";
      updateAttachmentBar();
      showToast("已移除参考图片", "info");
    });
  }

  if (btnPickCompleted) {
    btnPickCompleted.addEventListener("click", () => {
      const vTab = document.querySelector(".gemini-asset-tab[data-tab=\"video\"]");
      if (vTab) vTab.click();
      if (quickSelectVideo) quickSelectVideo.focus();
      showToast("请在右侧【视频画面】下拉列表中快速选用成片", "info");
    });
  }

  function populateCompletedVideos() {
    if (!quickSelectVideo) return;
    const cur = quickSelectVideo.value;
    const vids = state.tasks.filter(t => t.has_video && t.video_url);
    quickSelectVideo.innerHTML = "<option value=\"\">-- 点击选择成片库视频 --</option>";
    vids.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.video_url;
      opt.textContent = "[" + t.id + "] " + (t.prompt || "视频").slice(0, 26) + "... (" + (t.duration_sec || 5) + "s)";
      quickSelectVideo.appendChild(opt);
    });
    if (cur) quickSelectVideo.value = cur;
  }

  if (quickSelectVideo) {
    quickSelectVideo.addEventListener("change", () => {
      const vUrl = quickSelectVideo.value;
      if (vUrl) {
        setAttachedVideo(vUrl, true);
      }
    });
  }

  if (btnRefreshVids) {
    btnRefreshVids.addEventListener("click", async () => {
      await fetchTasks(true);
      populateCompletedVideos();
      showToast("已刷新成片视频列表", "info");
    });
  }

  assetTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      assetTabs.forEach(t => t.classList.remove("active", "btn-primary"));
      tab.classList.add("active");
      const target = tab.getAttribute("data-tab");
      if (paneGallery) paneGallery.style.display = (target === "gallery") ? "block" : "none";
      if (paneAudio) paneAudio.style.display = (target === "audio") ? "block" : "none";
      if (paneVideo) paneVideo.style.display = (target === "video") ? "flex" : "none";
    });
  });

  if (btnRefreshAssets) {
    btnRefreshAssets.addEventListener("click", () => {
      fetchGeminiImages();
      fetchGeminiAudios();
      populateCompletedVideos();
      showToast("已刷新资产看板", "info");
    });
  }

  function scrollFeedToBottom() {
    if (feed) feed.scrollTop = feed.scrollHeight;
  }

  function renderMessageBubble(msg) {
    if (!feed) return;
    const isUser = msg.role === "user";
    const item = document.createElement("div");
    item.className = isUser ? "gemini-msg-user" : "gemini-msg-assistant";
    item.style.display = "flex";
    item.style.flexDirection = "column";
    item.style.alignItems = isUser ? "flex-end" : "flex-start";
    item.style.gap = "4px";

    const timeStr = msg.created_at ? msg.created_at.substring(11, 16) : "";
    const roleBadge = isUser ? "<span style=\"font-size:10px;color:#888\">你 · " + timeStr + "</span>" : "<span style=\"font-size:10px;color:#10b981;font-weight:600\">✨ Gemini (" + (msg.profile_name || "AI") + ") · " + timeStr + "</span>";

    const bubble = document.createElement("div");
    bubble.style.maxWidth = "88%";
    bubble.style.borderRadius = isUser ? "10px 10px 2px 10px" : "10px 10px 10px 2px";
    bubble.style.padding = "10px 14px";
    bubble.style.fontSize = "13px";
    bubble.style.lineHeight = "1.6";
    bubble.style.boxShadow = "0 1px 3px rgba(0,0,0,0.05)";

    if (isUser) {
      bubble.style.background = "#e6b64f";
      bubble.style.color = "#252724";
      bubble.style.fontWeight = "500";
    } else {
      bubble.style.background = "#fff";
      bubble.style.color = "var(--text-main)";
      bubble.style.border = "1px solid #e5e7eb";
    }

    if (isUser && msg.attachments_json) {
      try {
        const atts = JSON.parse(msg.attachments_json);
        if (Array.isArray(atts) && atts.length > 0) {
          const attBox = document.createElement("div");
          attBox.style.display = "flex";
          attBox.style.flexWrap = "wrap";
          attBox.style.gap = "6px";
          attBox.style.marginBottom = "8px";
          atts.forEach(a => {
            const chip = document.createElement("span");
            chip.style.fontSize = "11px";
            chip.style.padding = "2px 8px";
            chip.style.background = "rgba(0,0,0,0.08)";
            chip.style.borderRadius = "4px";
            chip.textContent = (a.type === "video" ? "📹 " : "🖼️ ") + (a.name || "附件");
            attBox.appendChild(chip);
          });
          bubble.appendChild(attBox);
        }
      } catch (e) {}
    }

    const textDiv = document.createElement("div");
    textDiv.style.whiteSpace = "pre-wrap";
    textDiv.style.wordBreak = "break-word";
    textDiv.textContent = msg.content || "";
    bubble.appendChild(textDiv);

    if (!isUser && msg.audio_url) {
      const audioBox = document.createElement("div");
      audioBox.style.marginTop = "10px";
      audioBox.style.padding = "10px";
      audioBox.style.background = "#f8fafc";
      audioBox.style.borderRadius = "6px";
      audioBox.style.border = "1px solid #e2e8f0";

      const audioHeader = document.createElement("div");
      audioHeader.style.display = "flex";
      audioHeader.style.justifyContent = "space-between";
      audioHeader.style.alignItems = "center";
      audioHeader.style.marginBottom = "6px";
      audioHeader.innerHTML = "<span style=\"font-size:11px;font-weight:600;color:#0284c7\">🎙️ 神经配音成品</span><a href=\"" + msg.audio_url + "\" download=\"gemini_voiceover.mp3\" class=\"btn btn-secondary btn-sm\" style=\"padding:1px 6px;font-size:10px\">📥 下载 MP3</a>";

      const audioPlayer = document.createElement("audio");
      audioPlayer.controls = true;
      audioPlayer.src = msg.audio_url;
      audioPlayer.style.width = "100%";
      audioPlayer.style.height = "32px";

      audioBox.appendChild(audioHeader);
      audioBox.appendChild(audioPlayer);
      bubble.appendChild(audioBox);
    }

    if (!isUser && msg.image_urls_json) {
      try {
        const imgs = JSON.parse(msg.image_urls_json);
        if (Array.isArray(imgs) && imgs.length > 0) {
          const imgGrid = document.createElement("div");
          imgGrid.style.display = "grid";
          imgGrid.style.gridTemplateColumns = "repeat(auto-fill, minmax(140px, 1fr))";
          imgGrid.style.gap = "8px";
          imgGrid.style.marginTop = "10px";

          imgs.forEach(url => {
            const card = document.createElement("div");
            card.style.borderRadius = "6px";
            card.style.overflow = "hidden";
            card.style.border = "1px solid #e5e7eb";
            card.style.background = "#000";

            const imgEl = document.createElement("img");
            imgEl.src = url;
            imgEl.style.width = "100%";
            imgEl.style.height = "120px";
            imgEl.style.objectFit = "cover";
            imgEl.style.cursor = "pointer";
            imgEl.onclick = () => window.open(url, "_blank");

            const actBar = document.createElement("div");
            actBar.style.padding = "4px";
            actBar.style.background = "#fff";
            actBar.style.display = "flex";
            actBar.style.justifyContent = "space-between";
            actBar.innerHTML = "<a href=\"" + url + "\" download class=\"btn btn-secondary btn-sm\" style=\"padding:1px 5px;font-size:10px\">📥 下载</a><button type=\"button\" class=\"btn btn-secondary btn-sm btn-use-as-ref\" style=\"padding:1px 5px;font-size:10px\">🎬 作参考图</button>";

            actBar.querySelector(".btn-use-as-ref").onclick = () => {
              applyImageAsStartFrame(url);
            };

            card.appendChild(imgEl);
            card.appendChild(actBar);
            imgGrid.appendChild(card);
          });
          bubble.appendChild(imgGrid);
        }
      } catch (e) {}
    }

    if (!isUser) {
      const opBar = document.createElement("div");
      opBar.style.display = "flex";
      opBar.style.gap = "6px";
      opBar.style.marginTop = "6px";

      const btnCopy = document.createElement("button");
      btnCopy.className = "btn btn-secondary btn-sm";
      btnCopy.type = "button";
      btnCopy.style.padding = "1px 6px";
      btnCopy.style.fontSize = "10px";
      btnCopy.textContent = "📋 复制文案";
      btnCopy.onclick = () => {
        navigator.clipboard.writeText(msg.content || "");
        showToast("已复制文案到剪贴板", "success");
      };
      opBar.appendChild(btnCopy);
      bubble.appendChild(opBar);
    }

    item.innerHTML = roleBadge;
    item.appendChild(bubble);
    feed.appendChild(item);
  }

  function applyImageAsStartFrame(imgUrl) {
    const genTab = document.querySelector(".tab-button[data-target=\"view-generate\"]");
    if (genTab) genTab.click();
    const dropStart = document.getElementById("drop-start");
    const hiddenPath = document.getElementById("hidden-start-image-path");
    if (hiddenPath) hiddenPath.value = imgUrl;
    if (dropStart) {
      dropStart.style.backgroundImage = "url(\"" + imgUrl + "\")";
      dropStart.style.backgroundSize = "cover";
      dropStart.classList.add("has-image");
    }
    showToast("✨ 已将图片成功设为视频创作的起始帧参考图！", "success");
  }

  let lastRenderedGeminiMsgCount = 0;
  async function fetchGeminiMessages(force = false) {
    try {
      const resp = await fetch("/api/gemini/messages?session_id=default");
      if (!resp.ok) return;
      const data = await resp.json();
      const msgs = data.messages || [];
      if (feed) {
        if (force || msgs.length !== lastRenderedGeminiMsgCount) {
          lastRenderedGeminiMsgCount = msgs.length;
          const welcome = feed.querySelector(".gemini-welcome-card");
          feed.innerHTML = "";
          if (welcome) feed.appendChild(welcome);
          msgs.forEach(renderMessageBubble);
          scrollFeedToBottom();
        }
      }
    } catch (e) {
      console.error("fetchGeminiMessages error", e);
    }
  }

  async function fetchGeminiImages() {
    try {
      const resp = await fetch("/api/gemini/images?limit=60");
      if (!resp.ok) return;
      const data = await resp.json();
      const imgs = data.images || [];
      if (galleryCount) galleryCount.textContent = imgs.length;
      if (galleryEmpty) galleryEmpty.style.display = imgs.length === 0 ? "block" : "none";
      if (galleryGrid) {
        galleryGrid.innerHTML = "";
        imgs.forEach(im => {
          const card = document.createElement("div");
          card.style.borderRadius = "6px";
          card.style.overflow = "hidden";
          card.style.border = "1px solid #e5e7eb";
          card.style.background = "#fff";
          card.style.display = "flex";
          card.style.flexDirection = "column";

          const promptEsc = escapeHtml(im.prompt || "Gemini 绘画资产");
          const profEsc = escapeHtml(im.profile_name || "Gemini");
          card.innerHTML = `<div style="background:#000;height:110px;overflow:hidden;position:relative"><img src="${im.url}" style="width:100%;height:100%;object-fit:cover;cursor:pointer" onclick="window.open('${im.url}', '_blank')"></div><div style="padding:6px 8px;flex:1;display:flex;flex-direction:column;justify-content:space-between"><div style="font-size:11px;color:var(--text-sub);overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;min-height:28px" title="${promptEsc}">${promptEsc}</div><div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;padding-top:4px;border-top:1px solid #f0f0f0"><span style="font-size:9px;color:var(--text-muted)">${profEsc}</span><div style="display:flex;gap:4px"><a href="${im.url}" download class="btn btn-secondary btn-sm" style="padding:1px 5px;font-size:9px">📥</a><button type="button" class="btn btn-secondary btn-sm btn-set-ref" style="padding:1px 5px;font-size:9px" title="设为视频创作参考图">🎬</button></div></div></div>`;
          card.querySelector(".btn-set-ref").onclick = () => applyImageAsStartFrame(im.url);
          galleryGrid.appendChild(card);
        });
      }
    } catch (e) {
      console.error("fetchGeminiImages error", e);
    }
  }

  function fetchGeminiAudios() {
    if (!audioList) return;
    const audios = state.tasks.filter(t => (t.task_type === "audio" || t.has_audio) && t.audio_url);
    if (audioCount) audioCount.textContent = audios.length;
    if (audioEmpty) audioEmpty.style.display = audios.length === 0 ? "block" : "none";
    audioList.innerHTML = "";

    audios.slice(0, 30).forEach(t => {
      const item = document.createElement("div");
      item.style.padding = "8px 10px";
      item.style.background = "#fff";
      item.style.border = "1px solid #e5e7eb";
      item.style.borderRadius = "6px";
      item.style.display = "flex";
      item.style.flexDirection = "column";
      item.style.gap = "6px";

      const promptEsc = escapeHtml(t.prompt || "配音音频");
      const modelEsc = escapeHtml(t.model || "广播级");
      const timeStr = t.submit_time ? t.submit_time.substring(5, 16) : "";

      item.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:11px;font-weight:600;color:var(--text-main);max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${promptEsc}</span><span style="font-size:10px;color:#0284c7;background:#f0f9ff;padding:1px 5px;border-radius:3px">${modelEsc}</span></div><audio controls src="${t.audio_url}" style="width:100%;height:30px"></audio><div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;color:var(--text-muted)"><span>${timeStr}</span><div style="display:flex;gap:4px"><button type="button" class="btn btn-secondary btn-sm btn-copy-aud-txt" style="padding:1px 6px;font-size:9px">复制文案</button><a href="${t.audio_url}" download="voiceover_${t.id}.mp3" class="btn btn-secondary btn-sm" style="padding:1px 6px;font-size:9px">下载 MP3</a></div></div>`;
      item.querySelector(".btn-copy-aud-txt").onclick = () => {
        navigator.clipboard.writeText(t.prompt || "");
        showToast("已复制配音文案", "success");
      };
      audioList.appendChild(item);
    });
  }

  if (btnClearChat) {
    btnClearChat.addEventListener("click", async () => {
      if (!confirm("确定清空当前 Gemini 多模态会话历史吗？")) return;
      try {
        await fetch("/api/gemini/messages?session_id=default", { method: "DELETE" });
        if (feed) {
          const welcome = feed.querySelector(".gemini-welcome-card");
          feed.innerHTML = "";
          if (welcome) feed.appendChild(welcome);
        }
        showToast("会话已清空", "info");
      } catch (e) {
        showToast("清空失败: " + e.message, "error");
      }
    });
  }

  let isGeminiSending = false;
  async function sendMessage() {
    if (isGeminiSending) {
      showToast("正在处理上一条消息，请稍候...", "warn");
      return;
    }
    const msg = chatInput ? chatInput.value.trim() : "";
    if (!msg && !attachedVideoFile && !attachedVideoPath && !attachedImageFile && !attachedImagePath) {
      showToast("请输入文字对话内容，或上传视频/图片", "warn");
      if (chatInput) chatInput.focus();
      return;
    }

    isGeminiSending = true;
    if (btnSend) {
      btnSend.disabled = true;
      btnSend.innerHTML = `<span>生成中...</span> ⏳`;
    }
    if (chatInput) {
      chatInput.disabled = true;
      chatInput.placeholder = "Gemini 正在思考并生成回复，请稍候...";
    }
    if (chatStatus) chatStatus.textContent = "正在处理与生成中...";

    const formData = new FormData();
    formData.append("message", msg);
    formData.append("session_id", "default");
    formData.append("mode", currentMode);
    if (activeProfSel && activeProfSel.value) {
      formData.append("profile_id", activeProfSel.value);
    }
    if (voiceSelect && voiceSelect.value) {
      formData.append("voice", voiceSelect.value);
    }
    if (aspectSelect && aspectSelect.value) {
      formData.append("aspect_ratio", aspectSelect.value);
    }

    if (attachedVideoFile) formData.append("video", attachedVideoFile);
    else if (attachedVideoPath) formData.append("video_path", attachedVideoPath);

    if (attachedImageFile) formData.append("image", attachedImageFile);
    else if (attachedImagePath) formData.append("image_path", attachedImagePath);

    const attachmentsPreview = [];
    if (attachedVideoFile) attachmentsPreview.push({ type: "video", name: attachedVideoFile.name });
    else if (attachedVideoPath) attachmentsPreview.push({ type: "video", name: attachedVideoPath.split(/[\\/]/).pop() });
    if (attachedImageFile) attachmentsPreview.push({ type: "image", name: attachedImageFile.name });
    else if (attachedImagePath) attachmentsPreview.push({ type: "image", name: attachedImagePath.split(/[\\/]/).pop() });

    renderMessageBubble({
      role: "user",
      content: msg,
      attachments_json: JSON.stringify(attachmentsPreview),
      created_at: new Date().toISOString()
    });
    scrollFeedToBottom();

    if (chatInput) chatInput.value = "";
    if (btnRemoveVideo) btnRemoveVideo.click();
    if (btnRemoveImage) btnRemoveImage.click();

    const loadingBubble = document.createElement("div");
    loadingBubble.className = "gemini-msg-assistant loading-placeholder";
    loadingBubble.style.display = "flex";
    loadingBubble.style.flexDirection = "column";
    loadingBubble.style.alignItems = "flex-start";
    loadingBubble.style.gap = "4px";
    loadingBubble.innerHTML = `<span style="font-size:10px;color:#10b981;font-weight:600">✨ Gemini 多模态引擎调度中...</span><div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px 14px;font-size:12px;color:var(--text-sub)">⏳ 正在调度账号理解多模态输入并生成结果，请稍候...</div>`;
    feed.appendChild(loadingBubble);
    scrollFeedToBottom();

    try {
      const resp = await fetch("/api/gemini/chat", {
        method: "POST",
        body: formData
      });
      const data = await resp.json();
      loadingBubble.remove();

      if (data.assistant_message) {
        renderMessageBubble(data.assistant_message);
        scrollFeedToBottom();
      } else {
        showToast(data.error_message || "执行完成", data.success ? "success" : "warn");
      }

      if (data.warning) {
        showToast(data.warning, "warn");
      }

      fetchGeminiImages();
      await fetchTasks(true);
      fetchGeminiAudios();
    } catch (err) {
      loadingBubble.remove();
      showToast("网络请求异常: " + err.message, "error");
      renderMessageBubble({
        role: "assistant",
        content: "❌ 请求处理失败: " + err.message + "。如果正在使用外部 Chrome，请关闭 Chrome 或点击上方【⏹ 释放占用】后再试。",
        created_at: new Date().toISOString()
      });
      scrollFeedToBottom();
    } finally {
      isGeminiSending = false;
      if (btnSend) {
        btnSend.disabled = false;
        btnSend.innerHTML = `<span>发送</span> 🚀`;
      }
      if (chatInput) {
        chatInput.disabled = false;
        chatInput.placeholder = "像 ChatGPT / Gemini 网页端一样输入对话内容、视频配音诉求或画图提示词... (Enter 发送, Shift+Enter 换行)";
        chatInput.focus();
      }
      if (chatStatus) chatStatus.textContent = "就绪";
    }
  }

  if (btnSend) {
    btnSend.addEventListener("click", sendMessage);
  }

  if (chatInput) {
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!isGeminiSending) {
          sendMessage();
        }
      }
    });
  }

  window.refreshGeminiHubView = () => {
    updateProfBadge();
    fetchGeminiMessages();
    fetchGeminiImages();
    fetchGeminiAudios();
    populateCompletedVideos();
  };

  updateProfBadge();
  fetchGeminiMessages();
  fetchGeminiImages();
  fetchGeminiAudios();
  populateCompletedVideos();
}


// ==================== 初始化与自动轮询 ====================
  setAspectRatio("16:9");
  setDurationSec(8);
  applyEngineMode("flow");
  fetchOverview();
  fetchTasks();
  fetchProfiles();

  state.pollTimer = setInterval(() => {
    if (document.hidden) return;
    fetchOverview();
    const activeTab = document.querySelector(".tab-button.active");
    if (activeTab && ["view-tasks", "view-generate"].includes(activeTab.getAttribute("data-target"))) {
      fetchTasks();
    }
    if (activeTab && activeTab.getAttribute("data-target") === "view-images") {
      fetchTasks();
    }
    if (activeTab && activeTab.getAttribute("data-target") === "view-profiles") {
      fetchProfiles();
    }
    if (activeTab && activeTab.getAttribute("data-target") === "view-audio") {
      updateAudioCompletedVideos();
    }
  }, 5000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { fetchOverview(); fetchTasks(); }
  });
});
