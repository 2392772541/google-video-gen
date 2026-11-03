'use strict';

// ============================================================================
// MuseFlow Runtime Adapter 真实源码离线回归测试套件
// 
// 目标：直接加载并执行当前生产环境实际使用的 runtime-adapter.js 真实源码，
//       严禁复制任何业务逻辑至测试文件。
// 
// 运行约束：
// - 全内存沙箱环境，隔离真实网络（所有 fetch 均为虚拟桩函数）
// - 零外部依赖，不产生磁盘写入，不调用付费 API
// - 验证 5 类核心可靠性场景：正常完成、等待核对、查询失败、任务停止、持久化失败
// ============================================================================

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ADAPTER_FILE_PATH = path.resolve(__dirname, '../static/museflow/runtime-adapter.js');
const adapterSource = fs.readFileSync(ADAPTER_FILE_PATH, 'utf8');

/**
 * 构建一个隔离的浏览器宿主沙箱，直接加载并运行真实的 runtime-adapter.js 源码
 */
function createAdapterHarness({
  fetchHandler = async () => ({ ok: true, json: async () => ({}) }),
  quotaExceeded = false,
  initialStorage = {}
} = {}) {
  const store = new Map(Object.entries(initialStorage));
  const calls = [];
  const consoleWarnings = [];
  const consoleErrors = [];

  const localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => {
      if (quotaExceeded) {
        const err = new Error('QuotaExceededError: The quota has been exceeded.');
        err.name = 'QuotaExceededError';
        throw err;
      }
      store.set(k, String(v));
    },
    removeItem: (k) => store.delete(k),
    clear: () => store.clear()
  };

  const domListeners = [];
  const window = {
    location: { origin: 'http://127.0.0.1:8088', href: 'http://127.0.0.1:8088/museflow' },
    addEventListener: (type, fn) => domListeners.push({ type, fn })
  };
  window.window = window;

  const document = {
    getElementById: () => null,
    querySelector: () => null,
    createElement: () => ({
      classList: { add() {}, remove() {}, contains: () => false },
      style: {},
      appendChild() {}
    }),
    body: { appendChild() {} }
  };

  const ctx = {
    window,
    document,
    localStorage,
    console: {
      log: () => {},
      warn: (...args) => consoleWarnings.push(args),
      error: (...args) => consoleErrors.push(args)
    },
    // 快进定时器：将 2000ms 压缩至 2ms，避免测试阻塞或占用高内存
    setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms, 2)),
    clearTimeout,
    AbortController,
    DOMException,
    FormData,
    Blob,
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      return fetchHandler(url, options);
    }
  };

  vm.createContext(ctx);
  vm.runInContext(adapterSource, ctx);

  return {
    ctx,
    calls,
    store,
    consoleWarnings,
    consoleErrors,
    adapter: ctx.window.__museFlowAdapter,
    storage: ctx.window.chrome?.storage?.local
  };
}

// ============================================================================
// 基础环境验证（证明真实源码在测试沙箱中成功装载并具备基础功能）
// ============================================================================

test('环境基线：真实 runtime-adapter.js 成功加载并挂载核心方法', () => {
  const h = createAdapterHarness();
  assert.ok(h.adapter, 'window.__museFlowAdapter 应当已挂载');
  assert.equal(typeof h.adapter.handleMessage, 'function');
  assert.equal(typeof h.adapter.checkVideoFarmHealth, 'function');
  assert.equal(typeof h.adapter.stopActiveGeneration, 'function');
  assert.equal(typeof h.adapter.executeVideoFarmGeneration, 'function');
  assert.ok(h.storage, 'window.chrome.storage.local 垫片应当已挂载');
});

test('基础探活：checkVideoFarmHealth 在服务在线时返回正常状态', async () => {
  const h = createAdapterHarness({
    fetchHandler: async (url) => {
      if (url === '/api/canvas/status') {
        return { ok: true, json: async () => ({ status: 'healthy', version: '1.0' }) };
      }
      throw new Error('Unexpected URL: ' + url);
    }
  });
  const res = await h.adapter.checkVideoFarmHealth();
  assert.equal(res.ok, true);
  assert.equal(res.signedIn, true);
  assert.match(res.title, /8088/);
});

// ============================================================================
// 五大可靠性核心场景测试（针对当前代码中已被基线审计证实的缺陷）
// ============================================================================

test('场景 1【正常完成】：成片成功后应持久保留 taskId 与 requestId 强关联凭据供追踪对账', async () => {
  // 对应源码：runtime-adapter.js:254-298
  // 预期行为：服务端创建并生成成功后，结果必须包含 taskId 与 requestId，
  //           并能与前端任务/分镜关联，防止在成功后直接清空所有凭据导致无法对账。
  const targetTaskId = 'task_success_999';
  const clientRequestId = 'req_client_shot_101';

  const h = createAdapterHarness({
    fetchHandler: async (url) => {
      if (url === '/api/canvas/v1/videos') {
        return { ok: true, json: async () => ({ id: targetTaskId, status: 'queued' }) };
      }
      if (url.includes(`/api/canvas/v1/videos/${targetTaskId}`)) {
        return {
          ok: true,
          json: async () => ({
            status: 'completed',
            url: '/outputs/render_result.mp4',
            progress: 100
          })
        };
      }
      if (url === '/api/canvas/import-to-farm') {
        return { ok: true, json: async () => ({ success: true }) };
      }
      throw new Error('Unexpected URL: ' + url);
    }
  });

  const result = await h.adapter.executeVideoFarmGeneration({
    mediaType: 'video',
    prompt: '镜头测试',
    requestId: clientRequestId,
    timeoutSec: 1
  });

  assert.equal(result.ok, true);
  assert.equal(result.isVideo, true);
  assert.equal(result.url, '/outputs/render_result.mp4');

  // 核心可靠性断言：返回结果或持久化上下文必须保留 taskId 与 requestId 映射
  // 当前代码第 295 行仅返回 { ok: true, url, isVideo: true }，丢失了所有任务 ID，
  // 且在 finally 块中直接将 activeTaskId 清空为 null。
  assert.equal(
    result.taskId,
    targetTaskId,
    '生成成功结果必须显式返回服务端任务标识 taskId，以供状态持久化与后续对账'
  );
  assert.equal(
    result.requestId,
    clientRequestId,
    '生成成功结果必须显式返回关联的客户端 requestId'
  );
});

test('场景 2【等待核对】：遇 needs_reconciliation 状态必须识别并受控保留凭据，禁止退化为普通超时死等并丢弃任务', async () => {
  // 对应源码：runtime-adapter.js:280-309
  // 预期行为：当后端接口返回 needs_reconciliation（如 upstream 已受理但超时未出成片，需防止重复扣费），
  //           适配器必须识别该状态，立即受控中断死循环，并在报错/返回中明确标记 needs_reconciliation，
  //           绝不能当作未知状态继续轮询直到超时，更不能在超时后丢弃 taskId 诱导用户重复发起生成。
  const targetTaskId = 'task_reconcile_888';
  const clientRequestId = 'req_recon_202';

  const h = createAdapterHarness({
    fetchHandler: async (url) => {
      if (url === '/api/canvas/v1/videos') {
        return { ok: true, json: async () => ({ id: targetTaskId, status: 'queued' }) };
      }
      if (url.includes(`/api/canvas/v1/videos/${targetTaskId}`)) {
        return {
          ok: true,
          json: async () => ({
            status: 'needs_reconciliation',
            message: '上游生成中或状态未同步，等待核对，切勿重复提交'
          })
        };
      }
      throw new Error('Unexpected URL: ' + url);
    }
  });

  let capturedError = null;
  try {
    await h.adapter.executeVideoFarmGeneration({
      mediaType: 'video',
      prompt: '对账测试',
      requestId: clientRequestId,
      timeoutSec: 0.05
    });
  } catch (err) {
    capturedError = err;
  }

  assert.ok(capturedError, '应当产生受控错误或对账状态提示');
  // 核心可靠性断言：错误信息必须反映 needs_reconciliation 或对账语义，
  // 而不是被掩盖为“视频生成超时，请稍后在任务列表查看进度”
  assert.match(
    capturedError.message,
    /needs_reconciliation|核对|对账/i,
    '遇到 needs_reconciliation 时应明确提示对账状态，不能退化为普通超时'
  );
});

test('场景 3【查询失败】：轮询连续 404/500 时应区分“查询端点不可用”与“生成超时”，禁止静默吞错', async () => {
  // 对应源码：runtime-adapter.js:280-281 (if (!pollResp.ok) continue;)
  // 预期行为：当轮询端点持续返回 404 时，适配器应当识别出查询接口异常或任务在服务端不存在，
  //           向用户明确报出网络/端点查询错误，不能一路 continue 到超时，伪装成普通的“视频生成超时”。
  const targetTaskId = 'task_not_found_404';

  const h = createAdapterHarness({
    fetchHandler: async (url) => {
      if (url === '/api/canvas/v1/videos') {
        return { ok: true, json: async () => ({ id: targetTaskId, status: 'queued' }) };
      }
      if (url.includes(`/api/canvas/v1/videos/${targetTaskId}`)) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ detail: 'Task not found' })
        };
      }
      throw new Error('Unexpected URL: ' + url);
    }
  });

  let capturedError = null;
  try {
    await h.adapter.executeVideoFarmGeneration({
      mediaType: 'video',
      prompt: '404轮询测试',
      timeoutSec: 0.05
    });
  } catch (err) {
    capturedError = err;
  }

  assert.ok(capturedError, '轮询连续失败应抛出错误');
  // 核心可靠性断言：错误信息应当指明查询接口或 HTTP 状态异常，而非被通用超时掩盖
  assert.match(
    capturedError.message,
    /404|查询失败|网络异常|服务接口错误/i,
    '查询接口持续 404 时应当如实汇报查询端点故障，不能谎称为生成超时'
  );
});

test('场景 4【停止任务】：前端停止时若声称 stopped:true，必须向后端通知取消或区分本地中止与云端停止', async () => {
  // 对应源码：runtime-adapter.js:127-130 及 159-165
  // 预期行为：当调用 stopActiveGeneration 或收到 MUSEFLOW_STOP_GENERATION 且存在活动任务时，
  //           如果返回 { ok: true, stopped: true }，必须同时向后端发送了取消/停止请求，
  //           或者必须在返回中明确表示仅“本地中止监听，后端任务未取消”，不能在完全未通知后端的情况下假装云端已停止。
  const activeTaskId = 'task_running_to_stop';
  const h = createAdapterHarness({
    fetchHandler: async (url) => {
      return { ok: true, json: async () => ({ ok: true }) };
    }
  });

  // 模拟当前适配器正在监控一个活动任务
  h.adapter.activeTaskId = activeTaskId;
  const mockAbortController = new AbortController();
  h.adapter.activeAbortController = mockAbortController;

  const stopResponse = await h.adapter.handleMessage({ type: 'MUSEFLOW_STOP_GENERATION' });

  // 核心可靠性断言：若宣称 stopped 为 true，必须触发了针对后端的取消/停止请求
  const stopApiCall = h.calls.find(
    (c) => c.url.includes('/stop') || c.url.includes('/cancel')
  );
  assert.ok(
    stopApiCall,
    '声称停止成功 (stopped: true) 时，必须向后端发送取消或停止请求，避免后台继续空转扣费'
  );
});

test('场景 5【保存失败】：存储配额超限或持久化失败时必须 reject 抛错，严禁静默吞掉假装成功', async () => {
  // 对应源码：runtime-adapter.js:55-71 (chrome.storage.local.set 中的 catch 仅 console.warn)
  // 预期行为：当浏览器 localStorage 配额满（QuotaExceededError）时，
  //           chrome.storage.local.set 必须返回被 reject 的 Promise 或抛出异常，
  //           通知调用方数据保存失败，绝不能吞掉异常静默 resolve，让用户误以为已安全持久化。
  const h = createAdapterHarness({
    quotaExceeded: true // 模拟磁盘/配额已满
  });

  // 核心可靠性断言：保存失败必须 reject，调用方能通过 catch 捕获
  await assert.rejects(
    async () => {
      await h.storage.set({ museflow: { nodes: [{ id: 'node_1' }], test: true } });
    },
    (err) => {
      return (
        err &&
        (err.name === 'QuotaExceededError' ||
          String(err.message).includes('quota') ||
          String(err.message).includes('Storage'))
      );
    },
    '存储空间耗尽时，storage.set 必须 reject 抛出异常，绝不允许静默 resolve 导致数据无感知丢失'
  );
});
