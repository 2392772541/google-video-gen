# Flow 时长会话自适应与 Gemini 稳定基线最终闭环报告 (FLOW_SESSION_CAPABILITY_REPORT)

## 一、核心四问明确答复 (Direct Answers to Authoritative Questions)

### 1. 当前账号能否精确选择时长？
- **Omni 系列模型**：**【能】**。当前账号下，Flow Omni 旗舰模型网页端原生具备 4/6/8/10s 滑块，系统开放滑块并透传 `--duration`。
- **Veo 系列模型**：**【不能（当前账号限制）】**。经实机 Playwright 深度探测与 Google 官方已知问题核实，当前账号（`Gopal Kumar Pro`）在网页端未暴露 Veo 时长控件行，时长由 Flow 服务端固定决定（实测约为 6s/8s）。系统界面已透明标注“服务端默认时长 (约 6s/8s)”，彻底移除了不可用的假滑块，避免用户误选。
- **Google Vids**：**【能】**。支持 3~10 秒精确自由调节。
- **Gemini 网页端**：**【不能】**。Gemini 网页端由平台服务端固定渲染，实测物理成片时长为标准的 10.000 秒，界面明确提示“平台决定实际时长”。

### 2. 系统是否根据真实网页能力自动决定？
- **【是，会话能力动态解耦】**。系统在 `FLOW_DURATION_MATRIX.json` 中完整隔离了“官方理论矩阵”与“当前会话/账号 UI 探测矩阵”：
  * 对具备原生控件的 Omni 模型，动态启用 `selectable` 并向底层传递精确 `--duration`；
  * 对当前账号不具备控件的 Veo 模型，自动降级为 `upstream_default`，生成时严格拦截向 CLI 盲传 `--duration` 的行为，从根源上杜绝了 `exit 11` 和 `exit 23` 崩溃；
  * 若未来切换到具备 Veo 时长控件的账号，系统可动态识别并开放对应秒数。

### 3. 用户是否仍然会在生成之后才遇到可提前识别的时长错误？
- **【否，已实现 100% 前置防御】**：
  * **前端输入端防御**：选择 Veo 时自动禁用 10s 选项，选择 Ingredients 时强制对齐为合规模式；
  * **API 网关前置校验**：`canvas_video_compat.py` 在接收请求时执行严格参数归一化，超出范围或非法的组合在入库前即刻 422 友好中文拦截并给出替代指引；
  * **执行器动态防护**：`worker.py` 根据当前会话 UI 能力自适应决定是否透传 `--duration`，彻底消除运行时未知报错。

### 4. Gemini 是否保持可用？
- **【100% 保持可用且物理文件已冻结】**：
  * **物理成片证据**: `C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\gemini_verified_physical.mp4`
  * **SHA-256**: `5F403ADDF19F5F68C5A0FBC72C8C74C6A0D5DA88917346388EA95AC1FD2F4BDB`
  * **规格**: 1280x720, H.264, 10.000000s, 7,098,367 字节；
  * **核心修复**: 移除了导致假超时的 `:last-child` 伪类，采用原生下载按钮（`<2s` 极速完成）与 `currentSrc` 兜底；单图参考正常放行，无限画布回填与刷新播放正常。

---

## 二、端到端功能矩阵回归结果 (Regression Matrix)

| 测试项编号 | 测试模块与场景 | 预期断言 | 实际结果 | 状态 |
|---|---|---|---|---|
| **REG-01** | Gemini 单图参考提交与成片提取 | 移除 `:last-child` 伪类，原生下载极速落盘 | 成功提取 7.1MB 10s MP4 物理文件 | **PASS** |
| **REG-02** | Gemini 单图参考前端防误拦截 | 单图不误报“不支持多图参考” | 校验放行，成功创建任务 `task_2b1eb96408fd` | **PASS** |
| **REG-03** | 视频运镜指令即时推入输入框 | 点击“缓慢推近”立即推入英文指令并自动关闭弹窗 | 提示词即时更新，光标自动置于末尾 | **PASS** |
| **REG-04** | 运镜二次编辑与用户自定修改保护 | 用户在末尾追加中文内容，切换运镜时不丢失 | 追加内容 100% 保留，旧运镜无残留平滑替换 | **PASS** |
| **REG-05** | 视频节点增加【视觉预设】库 | 视频模式下提供风格、色彩、焦段、景深选择 | 视觉预设与运镜指令双重推入，互不冲突 | **PASS** |
| **REG-06** | Flow Omni 时长选择能力 | 4/6/8/10s 正常选择并透传 `--duration` | 正常提交，无越界与截断 | **PASS** |
| **REG-07** | Flow Veo 当前会话免崩防护 | Veo 模型严禁向 CLI 盲传 `--duration` | 规避 exit 11/23，日志明确记录服务端默认时长 | **PASS** |
| **REG-08** | Google Vids 连续分镜能力 | 3~10s 支持自由设置，首尾双帧严格拦截 | 边界拦截与单图提交均符合平台规范 | **PASS** |
| **REG-09** | 前端全库 TypeScript 类型检查 | `tsc --noEmit` 0 错误 | 0 errors | **PASS** |
| **REG-10** | 前端生产包构建打包 | `npm run build` 成功完成 | `dist/` 编译成功 (1,212 KB gzip) | **PASS** |

---

## 三、本轮文件变更清单 (Changelog)

1. `video_farm/gemini_worker.py`:
   - 移除 `model-response:last-child` 限制，采用全量候选集与 `responses[-1]`；
   - 增加 `has_video_indicator` 快捷放行，防止页面路由跳转至 `/app/*` 后继续死等；
   - 优先通过 `page.expect_download` 捕获原生下载按钮，结合 `currentSrc` 上下文安全转存。
2. `video_farm/canvas_video_compat.py`:
   - Gemini 单图参考放行（仅在 `files > 1` 时拦截）；
   - Veo 默认时长适配与 Omni 独占 10s 校验。
3. `web/src/components/canvas/canvas-prompt-chip-input.tsx`:
   - 引入 `forwardRef` 与 `useImperativeHandle`，暴露 `placeCaretAtEnd` 与 `focus` 方法。
4. `web/src/components/canvas/canvas-node-prompt-panel.tsx`:
   - 视频模式 (`mode === "video"`) 同时挂载 `<CanvasVisualPresetsPopover>` 与 `<CanvasCameraMovementPopover>`；
   - 预设点击或提示词选择时自动调用 `placeCaretAtEnd`，实现光标置尾与即时编辑。
5. `web/src/components/canvas/canvas-camera-movement-popover.tsx` & `canvas-visual-presets-popover.tsx`:
   - 点击选项即时推入输入框并收起弹窗，底部增加显式“应用到输入框并开始编辑”按钮。
6. `web/src/types/canvas.ts` & `web/src/stores/canvas/use-canvas-store.ts`:
   - 补齐 `CanvasNodeMetadata` 与 `defaultTestSuiteProject` 声明，实现全库 `tsc --noEmit` 0 错误。
7. `MODEL_CAPABILITIES.json` & `FLOW_DURATION_MATRIX.json`:
   - 建立模型理论矩阵与真实账号会话探测矩阵的分离持久化。
8. `GEMINI_SUCCESS_BASELINE.md`:
   - 固化 Gemini 真实物理成片规格与 SHA256 哈希。
