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
    checkRequireClean: document.getElementById("check-require-clean"),
    btnSubmitTask: document.getElementById("btn-submit-task"),
    btnResetForm: document.getElementById("btn-reset-form"),
    selectVideoModel: document.getElementById("select-video-model"),

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

  // ==================== 双生成引擎切换 ====================
  function applyEngineMode(engine) {
    state.currentEngine = engine;
    if (engine === "gemini") {
      if (el.btnEngineGemini) el.btnEngineGemini.classList.add("active", "gemini-active");
      if (el.btnEngineFlow) el.btnEngineFlow.classList.remove("active");

      // 调整舞台显示：隐藏尾帧，首帧标为参考图
      if (el.dropEnd) el.dropEnd.style.display = "none";
      if (el.btnSwapFrames) el.btnSwapFrames.style.display = "none";
      if (el.dropStart) {
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
      el.inputPrompt.placeholder = "输入视频描述提示词（例如：一只可爱的柴犬在阳光草坪上奔跑追逐泡泡，9:16竖屏，4K高质量摄影，毛发质感清晰细腻，动作自然流畅）...";
    } else {
      if (el.btnEngineFlow) el.btnEngineFlow.classList.add("active");
      if (el.btnEngineGemini) el.btnEngineGemini.classList.remove("active", "gemini-active");

      // 恢复 Flow 首尾帧模式
      if (el.dropEnd) el.dropEnd.style.display = "";
      if (el.btnSwapFrames) el.btnSwapFrames.style.display = "";
      if (el.dropStart) {
        const roleTag = el.dropStart.querySelector(".frame-role-tag");
        if (roleTag) roleTag.textContent = "首帧 (Start)";
        const dropTxt = el.placeholderStart.querySelector(".drop-text");
        if (dropTxt) dropTxt.textContent = "上传首帧图片";
        const dropSub = el.placeholderStart.querySelector(".drop-subtext");
        if (dropSub) dropSub.textContent = "推荐 9:16 (如 720x1280)";
      }
      if (el.stageHintText) {
        el.stageHintText.textContent = "首帧 + 尾帧刚性约束 · 9:16 物理平滑运镜收束";
      }
      el.btnSubmitTask.textContent = "🚀 提交到 Flow 首尾帧生成队列";
      el.inputPrompt.placeholder = "描述从首帧到尾帧之间的运动轨迹、主体动作变化及镜头推拉摇移逻辑...";
    }
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
    showToast("表单已清空", "info");
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
      formData.append("model", el.selectVideoModel.value);
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

  el.btnSubmitBatch.addEventListener("click", async () => {
    const raw = el.inputBatchJson.value.trim();
    if (!raw) {
      showToast("请输入分镜 JSON 数组", "warn");
      return;
    }
    let list;
    try {
      list = JSON.parse(raw);
      if (!Array.isArray(list)) throw new Error("必须是 JSON 数组结构");
    } catch (e) {
      showToast("JSON 格式错误: " + e.message, "error");
      return;
    }

    try {
      const resp = await fetch("/api/tasks/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tasks: list })
      });
      const data = await resp.json();
      if (resp.ok) {
        showToast("✅ 成功批量创建 " + data.created_count + " 个分镜任务！", "success");
        document.querySelector(".tab-button[data-target=\"view-tasks\"]").click();
      } else {
        showToast("批量提交失败: " + (data.detail || "未知错误"), "error");
      }
    } catch (err) {
      showToast("网络错误: " + err.message, "error");
    }
  });

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
    fetchTasks();
    showToast("任务列表已刷新", "info");
  });

  async function fetchTasks() {
    try {
      const resp = await fetch("/api/tasks?limit=100");
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
        engineBadge = `<span class="badge-engine-gemini" style="margin-right:6px;">🌐 Gemini 网页版</span>`;
      } else {
        const mLabel = t.model ? ` · ${t.model}` : "";
        engineBadge = `<span class="badge-engine-flow" style="margin-right:6px;">🎬 Flow 首尾帧${mLabel}</span>`;
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

      // 智能异常提示展示
      let errorNoticeHtml = "";
      if (t.error_code === "AUTH_EXPIRED") {
        errorNoticeHtml = `
          <div style="margin-top:8px; padding:8px 10px; background:rgba(239,68,68,0.12); border-left:3px solid var(--red-err); border-radius:4px; font-size:12px; color:#fca5a5;">
            <b>⚠️ 授权已失效 (401 UNAUTHORIZED)</b><br>
            Google Flow / Gemini 会话凭据已过期。请前往【账号管理】点击<b>【🔑 登录 Flow】</b>或<b>【🌐 登录 Gemini】</b>完成重新授权。
          </div>
        `;
      } else if (t.error_code === "QUOTA_EXHAUSTED") {
        errorNoticeHtml = `
          <div style="margin-top:8px; padding:8px 10px; background:rgba(245,158,11,0.12); border-left:3px solid var(--orange-warn); border-radius:4px; font-size:12px; color:#fde68a;">
            <b>⚡ 账号额度耗尽</b><br>
            原账号今日已用尽配额，系统已自动熔断冷却并将该任务无缝切换至下一个空闲账号。
          </div>
        `;
      } else if (t.error_code === "RATE_LIMITED") {
        errorNoticeHtml = `
          <div style="margin-top:8px; padding:8px 10px; background:rgba(245,158,11,0.12); border-left:3px solid var(--orange-warn); border-radius:4px; font-size:12px; color:#fde68a;">
            <b>⏳ 触发高频频控保护</b><br>
            账号暂时触发 Google 异常活动限制，已自动切入 20 分钟休眠，任务已无缝移交。
          </div>
        `;
      } else if (t.status === "failed" && t.error_message) {
        errorNoticeHtml = `
          <div style="margin-top:8px; padding:8px 10px; background:rgba(239,68,68,0.12); border-left:3px solid var(--red-err); border-radius:4px; font-size:12px; color:#fca5a5;">
            ${escapeHtml(t.error_message.slice(0, 160))}
          </div>
        `;
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

          ${isImageTask && t.status === "completed" && t.image_urls && t.image_urls.length > 0 ? `
            <div style="margin-top:10px; display:flex; gap:10px; align-items:center; background:rgba(0,0,0,0.25); padding:8px; border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
              <div style="width:65px; height:85px; border-radius:4px; overflow:hidden; background:#000; cursor:pointer; flex-shrink:0;" onclick="openImageViewer('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}', '${escapeJs(t.prompt)}')">
                <img src="${t.image_urls[0]}" style="width:100%; height:100%; object-fit:cover;" title="点击查看大图">
              </div>
              <div style="display:flex; flex-direction:column; gap:6px; flex:1; min-width:0;">
                <span style="font-size:11px; color:var(--text-sub);">✅ 图像已生成就绪，可一键填入视频工作台：</span>
                <div style="display:flex; gap:6px;">
                  <button class="gallery-btn-action" style="flex:1;" onclick="setAsStartFrame('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}')">📌 设为首帧</button>
                  <button class="gallery-btn-action" style="flex:1;" onclick="setAsEndFrame('${escapeJs(t.image_paths[0] || "")}', '${escapeJs(t.image_urls[0])}')">📌 设为尾帧</button>
                </div>
              </div>
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
            ${t.status === "failed" ? `<button class="btn btn-warning btn-sm btn-retry-task" data-id="${t.id}">🔄 重试</button>` : ""}
          </div>
          <button class="btn btn-secondary btn-sm btn-open-folder" data-id="${t.id}" title="在资源管理器中打开">📂</button>
        </div>
      `;

      container.appendChild(card);
    });

    // 绑定卡片动作事件
    container.querySelectorAll(".btn-play-video").forEach(b => {
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
      fetchTasks().then(() => {
        renderImageGallery();
        showToast("成果库已更新", "info");
      });
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
  el.btnRefreshProfiles.addEventListener("click", () => {
    fetchProfiles();
    showToast("账号状态已刷新", "info");
  });

  async function fetchProfiles() {
    try {
      const resp = await fetch("/api/profiles");
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
          <div class="meta-item"><span>上次成功</span><b>${p.last_success_at ? p.last_success_at.substring(0, 19).replace("T", " ") : "暂无"}</b></div>
          <div class="meta-item"><span>冷却截止</span>${cooldownInfo}</div>
        </div>

        <div class="profile-bottom" style="display:flex; flex-direction:column; gap:8px;">
          <div style="display:flex; gap:6px; width:100%;">
            <button class="btn btn-secondary btn-sm btn-login-flow" data-id="${p.id}" data-name="${p.name}" style="flex:1;" title="打开真实 Chrome 登录 Google Flow">
              🔑 登录 Flow
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

    // 绑定账号登录 Flow
    container.querySelectorAll(".btn-login-flow").forEach(b => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const name = b.getAttribute("data-name");
        try {
          const resp = await fetch("/api/profiles/" + id + "/launch-login", { method: "POST" });
          if (resp.ok) {
            showToast("已拉起 Google Flow 登录窗口 [" + name + "]，请在弹出的 Chrome 中登录并确认完成", "success");
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
    const currentVal = sel ? sel.value : "";
    const currentImgVal = imgSel ? imgSel.value : "";

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
      if (d.scheduler.running) {
        el.schedulerDot.className = "status-dot dot-running";
        el.schedulerText.textContent = "调度器运行中";
        el.btnToggleScheduler.textContent = "暂停";
        el.btnToggleScheduler.className = "btn btn-secondary btn-sm";
      } else {
        el.schedulerDot.className = "status-dot dot-idle";
        el.schedulerText.textContent = "调度器已暂停";
        el.btnToggleScheduler.textContent = "恢复";
        el.btnToggleScheduler.className = "btn btn-primary btn-sm";
      }

      // 顶部统计
      el.statIdleProf.textContent = d.profiles.idle_count;
      el.statRunningTask.textContent = d.tasks.running_count;
      el.statQueuedTask.textContent = d.tasks.queued_count;
      el.statCompletedTask.textContent = d.tasks.completed_count;

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

  
  // ==================== 一键成片流水线 (Pipeline) ====================
  const btnStartPipeline = document.getElementById("btn-start-pipeline");
  const pipeMatDir = document.getElementById("pipe-mat-dir");
  const pipeScriptText = document.getElementById("pipe-script-text");
  const pipeDuration = document.getElementById("pipe-duration");
  const pipeBgmPath = document.getElementById("pipe-bgm-path");
  const pipeStatusTag = document.getElementById("pipe-status-tag");
  const pipeProgressBar = document.getElementById("pipe-progress-bar");
  const pipeLogBox = document.getElementById("pipe-log-box");
  const pipeResultBox = document.getElementById("pipe-result-box");
  const pipeVideoLink = document.getElementById("pipe-video-link");
  const pipeOpenFolderBtn = document.getElementById("pipe-open-folder-btn");

  let activePipelineJobId = null;
  let pipelinePollTimer = null;

  function updatePipelineStepNodes(step) {
    const nodes = {
      "切图解析": "step-crop",
      "配音对齐": "step-tts",
      "运镜渲染": "step-motion",
      "混音字幕": "step-mix",
      "完成": "step-done"
    };
    document.querySelectorAll(".pipe-step-node").forEach(el => {
      el.style.background = "#1e293b";
      el.style.color = "#94a3b8";
      el.style.border = "none";
    });
    const targetId = nodes[step];
    if (targetId) {
      const activeEl = document.getElementById(targetId);
      if (activeEl) {
        activeEl.style.background = "rgba(59, 130, 246, 0.25)";
        activeEl.style.color = "#60a5fa";
        activeEl.style.border = "1px solid #3b82f6";
      }
    }
  }

  if (btnStartPipeline) {
    btnStartPipeline.addEventListener("click", async () => {
      const matDir = pipeMatDir.value.trim();
      const scriptText = pipeScriptText.value.trim();
      const duration = parseFloat(pipeDuration.value) || 45.0;
      const bgmPath = pipeBgmPath.value.trim();

      if (!matDir) {
        alert("请输入素材文件夹路径！");
        return;
      }

      btnStartPipeline.disabled = true;
      btnStartPipeline.innerHTML = "<span>⏳ 流水线全力生产中...</span>";
      pipeStatusTag.innerText = "运行中";
      pipeStatusTag.style.background = "#2563eb";
      pipeStatusTag.style.color = "#fff";
      pipeProgressBar.style.width = "5%";
      pipeLogBox.innerHTML = "<div>[提交] 正在创建流水线作业...</div>";
      pipeResultBox.style.display = "none";

      try {
        const res = await fetch("/api/pipeline/storyboard/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            material_dir: matDir,
            script_text: scriptText,
            target_duration: duration,
            bgm_path: bgmPath || null
          })
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "创建流水线作业失败");
        }

        activePipelineJobId = data.job_id;
        pipeLogBox.innerHTML += `<div>[作业ID] ${activePipelineJobId} 已派发至后台流水线</div>`;

        if (pipelinePollTimer) clearInterval(pipelinePollTimer);
        pipelinePollTimer = setInterval(async () => {
          try {
            const jRes = await fetch(`/api/pipeline/job/${activePipelineJobId}`);
            if (!jRes.ok) return;
            const jData = await jRes.json();
            const job = jData.job;
            if (!job) return;

            pipeProgressBar.style.width = `${job.progress}%`;
            updatePipelineStepNodes(job.step);
            pipeStatusTag.innerText = `${job.step} (${job.progress}%)`;

            // 渲染最新日志
            if (job.logs && job.logs.length > 0) {
              const logHtml = job.logs.map(l => `<div><span style="color:#64748b;">[${l.time}]</span> <b style="color:#38bdf8;">[${l.step}]</b> ${l.message}</div>`).join("");
              pipeLogBox.innerHTML = logHtml;
              pipeLogBox.scrollTop = pipeLogBox.scrollHeight;
            }

            if (job.status === "completed") {
              clearInterval(pipelinePollTimer);
              btnStartPipeline.disabled = false;
              btnStartPipeline.innerHTML = "<span>🚀 再次启动全自动流水线</span>";
              pipeStatusTag.innerText = "已完成";
              pipeStatusTag.style.background = "#10b981";
              pipeStatusTag.style.color = "#fff";
              updatePipelineStepNodes("完成");
              pipeResultBox.style.display = "block";
              pipeVideoLink.href = `/api/pipeline/video/${activePipelineJobId}`;
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
              btnStartPipeline.disabled = false;
              btnStartPipeline.innerHTML = "<span>🚀 重试全自动流水线</span>";
              pipeStatusTag.innerText = "失败";
              pipeStatusTag.style.background = "#ef4444";
              pipeStatusTag.style.color = "#fff";
              pipeLogBox.innerHTML += `<div style="color:#ef4444;">[错误] ${job.error || "未知故障"}</div>`;
              pipeLogBox.scrollTop = pipeLogBox.scrollHeight;
            }
          } catch (err) {
            console.error(err);
          }
        }, 1000);

      } catch (err) {
        alert("启动失败: " + err.message);
        btnStartPipeline.disabled = false;
        btnStartPipeline.innerHTML = "<span>🚀 启动全自动流水线生成成片</span>";
        pipeStatusTag.innerText = "失败";
        pipeStatusTag.style.background = "#ef4444";
      }
    });
  }

  // ==================== 初始化与自动轮询 ====================
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
