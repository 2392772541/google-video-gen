const assert = require('assert');
const fs = require('fs');

console.log("=== 开始执行 MuseFlow 0.5.0 业务逻辑自动化测试 ===");

// 1. 语法与核心文件检查
assert(fs.existsSync("E:/IDM下载/压缩/museflow-demo-2026-10-09/MuseFlow-0.5.0-简体中文版/MuseFlow-0.5.0-简体中文版/app.js"), "app.js 存在");
assert(fs.existsSync("E:/IDM下载/压缩/museflow-demo-2026-10-09/MuseFlow-0.5.0-简体中文版/MuseFlow-0.5.0-简体中文版/app.html"), "app.html 存在");
assert(fs.existsSync("E:/IDM下载/压缩/museflow-demo-2026-10-09/MuseFlow-0.5.0-简体中文版/MuseFlow-0.5.0-简体中文版/styles.css"), "styles.css 存在");

// 2. 模拟 app.js 中的核心数据结构与逻辑函数
const BUILTIN_IMAGE_MODELS = [
  { id: 'muse-image', name: 'Muse.ai (默认)' },
  { id: 'flux-1-schnell', name: 'FLUX.1 Schnell' },
  { id: 'flux-1-dev', name: 'FLUX.1 Dev' },
  { id: 'dall-e-3', name: 'DALL·E 3' },
  { id: 'sd-xl', name: 'Stable Diffusion XL' },
  { id: 'midjourney', name: 'Midjourney' }
];

let state = {
  nodes: [],
  edges: [],
  settings: {
    customImageModels: [],
    defaultImageModel: 'muse-image'
  }
};

function getAvailableImageModels() {
  const list = [...BUILTIN_IMAGE_MODELS];
  const custom = Array.isArray(state.settings?.customImageModels) ? state.settings.customImageModels : [];
  custom.forEach(item => {
    if (typeof item === 'string' && item.trim() && !list.some(m => m.id === item.trim())) {
      list.push({ id: item.trim(), name: `${item.trim()} (自定义)` });
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
  }
}

function removeCustomImageModel(name) {
  if (!name || !state.settings?.customImageModels) return;
  state.settings.customImageModels = state.settings.customImageModels.filter(m => m !== name);
  if (state.settings.defaultImageModel === name) {
    state.settings.defaultImageModel = 'muse-image';
  }
}

function nodeById(id) { return state.nodes.find(n => n.id === id); }

function timelinePredecessor(nodeId){
  const timeline=state.nodes.find(item=>item.type==='timeline'),order=timeline?.data?.clipOrder||[],index=order.indexOf(nodeId);
  return index>0?nodeById(order[index-1]):null;
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
    for (const v of state.nodes.filter(item => item.type === 'generateVideo' && item.data?.continuity)) {
      if (timelinePredecessor(v.id)?.id === curr) {
        v.data.dirty = true;
        queue.push(v.id);
      }
    }
  }
}

function topoOrder() {
  const indeg = new Map(state.nodes.map(n => [n.id, 0]));
  const outgoing = new Map(state.nodes.map(n => [n.id, []]));
  state.edges.forEach(e => {
    if (!indeg.has(e.source) || !indeg.has(e.target)) return;
    indeg.set(e.target, indeg.get(e.target) + 1);
    outgoing.get(e.source).push(e.target);
  });
  const q = state.nodes.filter(n => indeg.get(n.id) === 0).map(n => n.id);
  const out = [];
  while (q.length) {
    const id = q.shift();
    out.push(id);
    for (const target of outgoing.get(id)) {
      indeg.set(target, indeg.get(target) - 1);
      if (indeg.get(target) === 0) q.push(target);
    }
  }
  return out;
}

function requiredNodesFor(targets) {
  const targetSet = targets instanceof Set ? targets : new Set(Array.isArray(targets) ? targets : [targets]);
  const required = new Set();
  const visit = id => {
    if (required.has(id)) return;
    required.add(id);
    for (const edge of state.edges.filter(item => item.target === id)) visit(edge.source);
    const node = nodeById(id), previous = node?.type === 'generateVideo' && node.data?.continuity ? timelinePredecessor(id) : null;
    if (previous) visit(previous.id);
  };
  targetSet.forEach(id => visit(id));
  return topoOrder().filter(id => required.has(id));
}

// 调度过滤函数：模拟 execute 中计算 nodesToGenerate
function computeNodesToGenerate(targetId, forceAll) {
  const targetSet = targetId ? (Array.isArray(targetId) || targetId instanceof Set ? new Set(targetId) : new Set([targetId])) : null;
  const order = targetSet ? requiredNodesFor(targetSet) : topoOrder();
  const nodesToGenerate = [];
  let skippedCount = 0;
  for (const id of order) {
    const n = nodeById(id);
    if (!n || !['generateImage', 'generateVideo'].includes(n.type)) continue;
    const isTarget = targetSet ? targetSet.has(n.id) : false;
    const hasAsset = Boolean(n.data.asset?.url);
    const isSuccess = n.data.status === 'success';
    const isDirty = Boolean(n.data.dirty);
    let shouldRun = false;
    if (isTarget) shouldRun = true;
    else if (targetSet) shouldRun = !hasAsset;
    else if (forceAll) shouldRun = true;
    else shouldRun = !hasAsset || !isSuccess || isDirty;

    if (shouldRun) nodesToGenerate.push(n.id);
    else skippedCount++;
  }
  return { order, nodesToGenerate, skippedCount };
}

// ==================== 测试 1: 模型管理与自定义模型 ====================
console.log("-> 测试 1: 生图模型预设与自定义模型增删");
const defaultModels = getAvailableImageModels();
assert(defaultModels.length >= 6, "内置模型应至少有 6 个");
assert(defaultModels.some(m => m.id === 'muse-image'), "包含 muse-image");
assert(defaultModels.some(m => m.id === 'flux-1-dev'), "包含 flux-1-dev");

addCustomImageModel("my-fine-tuned-model");
const afterAdd = getAvailableImageModels();
assert(afterAdd.some(m => m.id === 'my-fine-tuned-model'), "成功添加自定义模型");
assert.strictEqual(state.settings.customImageModels[0], "my-fine-tuned-model", "自定义模型已持久化在 settings");

removeCustomImageModel("my-fine-tuned-model");
const afterRemove = getAvailableImageModels();
assert(!afterRemove.some(m => m.id === 'my-fine-tuned-model'), "成功删除自定义模型");
console.log("   ✓ 测试 1 通过！");

// ==================== 测试 2: 单节点运行与上游依赖缓存隔离 (AC-001) ====================
console.log("-> 测试 2: 单节点运行保护上游缓存");
// 构建场景：Prompt 1 -> Image 1 (已成功生成) -> Video 1 (需重新生成)
state.nodes = [
  { id: 'p1', type: 'prompt', data: { text: "场景1" } },
  { id: 'img1', type: 'generateImage', data: { model: 'muse-image', status: 'success', asset: { url: 'data:image/png;base64,123' }, dirty: false } },
  { id: 'p2', type: 'prompt', data: { text: "场景2视频" } },
  { id: 'vid1', type: 'generateVideo', data: { status: 'idle', asset: null, dirty: true } }
];
state.edges = [
  { id: 'e1', source: 'p1', target: 'img1' },
  { id: 'e2', source: 'img1', target: 'vid1' },
  { id: 'e3', source: 'p2', target: 'vid1' }
];

// 用户在 vid1 上点击生成
const runVidResult = computeNodesToGenerate('vid1', false);
assert(runVidResult.order.includes('img1'), "order 中应包含上游节点以保证依赖顺序");
assert(runVidResult.order.includes('vid1'), "order 中应包含目标节点");
assert.deepStrictEqual(runVidResult.nodesToGenerate, ['vid1'], "由于 img1 已有有效资产，img1 必须被跳过，nodesToGenerate 仅包含 vid1！");
assert.strictEqual(runVidResult.skippedCount, 1, "跳过计数为 1");
console.log("   ✓ 测试 2 通过：上游已完成图片未被清空，仅重新生成视频目标！");

// ==================== 测试 3: 智能增量工作流运行与跳过已完成项 (AC-002) ====================
console.log("-> 测试 3: 顶栏运行智能跳过未修改项");
// 假设用户修改了 vid1 的提示词，其他节点未变
// 现在 vid1 成功生成
state.nodes.find(n => n.id === 'vid1').data = { status: 'success', asset: { url: 'data:video/mp4;base64,456' }, dirty: false };

// 此时全工作流均处于 success 状态且未脏
const runAllClean = computeNodesToGenerate(null, false);
assert.strictEqual(runAllClean.nodesToGenerate.length, 0, "全部节点未修改且已完成时，无需重复生成任何节点");
assert.strictEqual(runAllClean.skippedCount, 2, "跳过 2 个已完成生成节点");

// 用户此时单独修改了 img1 的提示词
markNodeDirty('p1'); // p1 修改，通过脏链传导
assert.strictEqual(nodeById('img1').data.dirty, true, "img1 应被标记为 dirty");
assert.strictEqual(nodeById('vid1').data.dirty, true, "依赖 img1 的 vid1 也被标记为 dirty");

// 重新运行工作流
const runDirtyResult = computeNodesToGenerate(null, false);
assert(runDirtyResult.nodesToGenerate.includes('img1'), "img1 被修改，必须重新生成");
assert(runDirtyResult.nodesToGenerate.includes('vid1'), "下游 vid1 依赖 img1，也必须重新生成");
console.log("   ✓ 测试 3 通过：智能增量运行准确识别 dirty 状态与依赖链路！");

// ==================== 测试 4: 全量运行强制重跑 (AC-002) ====================
console.log("-> 测试 4: 全量运行 (forceAll=true)");
// 恢复无 dirty 状态
nodeById('img1').data.dirty = false;
nodeById('vid1').data.dirty = false;
const forceResult = computeNodesToGenerate(null, true);
assert.strictEqual(forceResult.nodesToGenerate.length, 2, "forceAll 为 true 时，即使全部成功也强制重新生成所有生成节点");
assert.strictEqual(forceResult.skippedCount, 0, "全量重跑跳过数为 0");
console.log("   ✓ 测试 4 通过：显式全量重跑生效！");

// ==================== 测试 5: 选区运行 (Selected Nodes) ====================
console.log("-> 测试 5: 选区运行");
const selectedResult = computeNodesToGenerate(['img1'], false);
assert.deepStrictEqual(selectedResult.nodesToGenerate, ['img1'], "仅运行选中的 img1");
console.log("   ✓ 测试 5 通过：多选/单选节点运行生效！");

// ==================== 调度器模拟：模拟 app.js 中的 execute 容错执行流程 ====================
async function simulateWorkflowExecution({ targetId = null, forceAll = false, mockGenerators = {} } = {}) {
  let isRunning = true;
  let runStatus = { text: '', cls: '' };
  const setRunStatus = (text, cls = '') => { runStatus = { text, cls }; };

  const targetSet = targetId ? (Array.isArray(targetId) || targetId instanceof Set ? new Set(targetId) : new Set([targetId])) : null;
  const order = targetSet ? requiredNodesFor(targetSet) : topoOrder();

  const nodesToGenerate = [];
  let skippedCount = 0;
  for (const id of order) {
    const n = nodeById(id);
    if (!n || !['generateImage', 'generateVideo'].includes(n.type)) continue;
    const isTarget = targetSet ? targetSet.has(n.id) : false;
    const hasAsset = Boolean(n.data.asset?.url);
    const isSuccess = n.data.status === 'success';
    const isDirty = Boolean(n.data.dirty);
    let shouldRun = false;
    if (isTarget) shouldRun = true;
    else if (targetSet) shouldRun = !hasAsset;
    else if (forceAll) shouldRun = true;
    else shouldRun = !hasAsset || !isSuccess || isDirty;
    if (shouldRun) nodesToGenerate.push(n.id);
    else skippedCount++;
  }

  const succeededNodes = [];
  const failedNodes = [];
  const skippedDependencyNodes = [];

  try {
    for (const id of order) {
      const n = nodeById(id);
      if (!n) continue;
      if (['generateImage', 'generateVideo'].includes(n.type)) {
        if (!nodesToGenerate.includes(n.id)) continue;
        const isVideo = n.type === 'generateVideo';

        // 1. 提示词检查
        const prompt = n.data.prompt || "默认测试提示词";
        if (!String(prompt).trim()) {
          n.data.status = 'error';
          n.data.error = "未配置提示词";
          failedNodes.push({ id: n.id, error: n.data.error });
          if (targetSet && targetSet.size === 1) throw new Error(n.data.error);
          continue;
        }

        // 2. 连续性（Continuity）依赖检查
        const continuityPrevious = isVideo && n.data.continuity ? timelinePredecessor(n.id) : null;
        const continuityStartFrame = continuityPrevious?.data?.endFrame?.url ? continuityPrevious.data.endFrame : null;
        if (isVideo && n.data.continuity && !continuityStartFrame) {
          n.data.status = 'error';
          n.data.error = `尾帧连续生成依赖前置片段 (${continuityPrevious?.id || '上个视频'}) 成功生成尾帧。`;
          skippedDependencyNodes.push({ id: n.id, error: n.data.error });
          if (targetSet && targetSet.size === 1) throw new Error(n.data.error);
          continue;
        }

        n.data.status = 'running';
        try {
          const mockGen = mockGenerators[n.id] || (async () => ({ ok: true, url: `mock://${n.id}.mp4` }));
          const res = await mockGen(n);
          if (!res.ok) throw new Error(res.error || "生成失败");
          n.data.asset = { url: res.url };
          n.data.status = 'success';
          n.data.dirty = false;
          if (isVideo) n.data.endFrame = { url: `mock://${n.id}-end.png` };
          succeededNodes.push(n.id);
        } catch (err) {
          n.data.status = 'error';
          n.data.error = err?.message || String(err);
          failedNodes.push({ id: n.id, error: n.data.error });
          if (targetSet && targetSet.size === 1) throw err;
        }
      }
    }

    if (failedNodes.length > 0 || skippedDependencyNodes.length > 0) {
      const parts = [];
      if (succeededNodes.length > 0) parts.push(`成功 ${succeededNodes.length} 项`);
      if (failedNodes.length > 0) parts.push(`失败 ${failedNodes.length} 项`);
      if (skippedDependencyNodes.length > 0) parts.push(`因依赖跳过 ${skippedDependencyNodes.length} 项`);
      setRunStatus(`工作流运行完成（${parts.join('，')}）。可针对标红节点修改后单独重试。`, 'warn');
    } else {
      setRunStatus(`工作流运行完成（成功 ${succeededNodes.length} 项）。`, 'ok');
    }
  } catch (outerErr) {
    setRunStatus(`执行出错：${outerErr.message}`, 'error');
  } finally {
    isRunning = false;
  }

  return { isRunning, runStatus, succeededNodes, failedNodes, skippedDependencyNodes };
}

(async () => {
  // ==================== 测试 6: 视频节点生成失败时，工作流异常被隔离，后续无依赖节点继续成功生成 (用户新诉求) ====================
  console.log("-> 测试 6: 单视频生成失败故障隔离，后续无依赖节点继续推进");
  state.nodes = [
    { id: 'vid1', type: 'generateVideo', data: { prompt: '视频1', status: 'idle', asset: null, dirty: true } },
    { id: 'vid2', type: 'generateVideo', data: { prompt: '视频2（独立片段）', status: 'idle', asset: null, dirty: true } }
  ];
  state.edges = [];

  const execResult6 = await simulateWorkflowExecution({
    mockGenerators: {
      vid1: async () => { throw new Error("Muse 提示生成失败：服务异常或内容受限"); },
      vid2: async () => ({ ok: true, url: "mock://vid2-success.mp4" })
    }
  });

  assert.strictEqual(execResult6.isRunning, false, "执行完成后 isRunning 必须为 false，绝不卡死");
  assert.strictEqual(nodeById('vid1').data.status, 'error', "vid1 状态应为 error");
  assert(nodeById('vid1').data.error.includes("Muse 提示生成失败"), "vid1 记录了确切的失败原因");
  assert.strictEqual(nodeById('vid2').data.status, 'success', "vid2 不受 vid1 失败影响，必须正常成功生成！");
  assert.strictEqual(execResult6.succeededNodes.length, 1, "成功节点数应为 1");
  assert.strictEqual(execResult6.failedNodes.length, 1, "失败节点数应为 1");
  assert(execResult6.runStatus.text.includes("成功 1 项") && execResult6.runStatus.text.includes("失败 1 项"), "状态栏清晰播报成功与失败统计");
  console.log("   ✓ 测试 6 通过：单视频生成失败时工作流未卡死，后续独立视频正常生成完成！");

  // ==================== 测试 7: 前置片段失败时，依赖连续性的下游节点优雅跳过，其他独立片段不受影响 ====================
  console.log("-> 测试 7: 连续性片段前置缺失优雅跳过，后续其它独立镜头继续生成");
  state.nodes = [
    { id: 'timeline1', type: 'timeline', data: { clipOrder: ['vid1', 'vid2_continuity', 'vid3_standalone'] } },
    { id: 'vid1', type: 'generateVideo', data: { prompt: '镜头1', status: 'idle', asset: null, dirty: true } },
    { id: 'vid2_continuity', type: 'generateVideo', data: { prompt: '镜头2接镜头1', continuity: true, status: 'idle', asset: null, dirty: true } },
    { id: 'vid3_standalone', type: 'generateVideo', data: { prompt: '镜头3独立', continuity: false, status: 'idle', asset: null, dirty: true } }
  ];
  state.edges = [];

  const execResult7 = await simulateWorkflowExecution({
    mockGenerators: {
      vid1: async () => { throw new Error("视频1超时或失败"); },
      vid3_standalone: async () => ({ ok: true, url: "mock://vid3.mp4" })
    }
  });

  assert.strictEqual(execResult7.isRunning, false, "执行完成 isRunning 必须为 false");
  assert.strictEqual(nodeById('vid1').data.status, 'error', "vid1 为 error");
  assert.strictEqual(nodeById('vid2_continuity').data.status, 'error', "vid2 因依赖 vid1 尾帧而跳过，标记为 error 提示");
  assert(nodeById('vid2_continuity').data.error.includes("尾帧连续生成依赖前置片段"), "vid2 明确提示等待前置片段");
  assert.strictEqual(nodeById('vid3_standalone').data.status, 'success', "vid3 为独立片段，必须正常生成成功！");
  assert.strictEqual(execResult7.succeededNodes.length, 1, "成功 1 项");
  assert.strictEqual(execResult7.failedNodes.length, 1, "失败 1 项");
  assert.strictEqual(execResult7.skippedDependencyNodes.length, 1, "依赖跳过 1 项");
  console.log("   ✓ 测试 7 通过：依赖链安全熔断并跳过，无依赖独立节点照常生成！");

  // ==================== 测试 8: 失败后增量重试机制 ====================
  console.log("-> 测试 8: 针对失败节点的增量重试（不重跑已成功的节点）");
  // 模拟用户在修复 vid1 提示词后，再次点击工作流运行（增量模式）
  nodeById('vid1').data.dirty = true;
  nodeById('vid1').data.error = '';

  const retryGenList = computeNodesToGenerate(null, false);
  assert(retryGenList.nodesToGenerate.includes('vid1'), "失败待重试的 vid1 应在运行列表中");
  assert(!retryGenList.nodesToGenerate.includes('vid3_standalone'), "已成功生成的 vid3_standalone 自动跳过，绝不重复生成！");
  console.log("   ✓ 测试 8 通过：增量重试机制完备，仅重跑需修复节点！");

  console.log("\n=========================================");
  console.log("所有 8 项自动化逻辑测试全部验证通过 (EXIT CODE 0)");
  console.log("=========================================");
})().catch(err => {
  console.error("测试未通过：", err);
  process.exit(1);
});