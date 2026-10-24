/**
 * MuseFlow 镜头级精细化生产、批量调度与审片归档模块 (M9 + M10 核心体系)
 * 职责：
 * 1. 稳定镜头身份 (shotId, sceneId, version) 与来源完整性 (taskId, sha256)
 * 2. 脚本导入防误删三模式 (更新已有/追加/替换) 与可恢复快照
 * 3. 依赖感知 DAG 批量生成调度器 (串行执行、暂停/恢复、WAITING_DEPENDENCY)
 * 4. 自动技术质检 (Technical QC) 与人工审片 (Review Status)
 * 5. 单镜头独立执行与候选版本回退 (V1, V2, V3 并存无覆盖)
 * 6. 跨镜头尾帧依赖失效检测 (STALE_REFERENCE) 与人工决策
 * 7. 精准时间线入出点裁切与工程归档包导出
 */
(() => {
  'use strict';

  class ShotManager {
    constructor() {
      this.projectId = 'default';
      this.visualBible = this.createDefaultVisualBible();
      this.shots = [];
      this.snapshots = []; // 操作历史快照 (防误删与撤销)
      this.batchState = {
        isRunning: false,
        isPaused: false,
        queue: [],
        activeShotId: null,
        plan: null
      };
      this.listeners = new Set();
      this.activeExecutingShotId = null;
    }

    createDefaultVisualBible() {
      return {
        styleName: '电影级写实摄影',
        stylePrompt: '8k cinematic realism, Hasselblad medium format photography, natural morning lighting, shallow depth of field, natural photorealistic textures',
        colorScheme: '自然晨光微冷青调',
        lighting: '侧逆晨光，柔和丁达尔散射',
        lensCamera: '85mm f/1.4 写实人像与特写镜头',
        aspectRatio: '16:9',
        targetDurationPerShot: 6.0,
        subjectSetting: {
          type: 'plant',
          name: '番茄幼苗 (Solanum lycopersicum)',
          features: '真实番茄双子叶舒展，茎秆微细绒毛，叶脉清晰，湿润黑褐色培养土',
          referenceAssetUrl: '/media/outputs/m8_shot1_tail_frame.png'
        },
        negativePrompt: 'cartoon, 3d render, anime, fantasy glow, oversaturated, blurry, bad anatomy'
      };
    }

    addListener(cb) {
      this.listeners.add(cb);
      return () => this.listeners.delete(cb);
    }

    notify() {
      this.listeners.forEach(cb => {
        try { cb(this); } catch (e) { console.error('[ShotManager] listener error:', e); }
      });
      if (typeof window !== 'undefined' && window.chrome?.storage?.local) {
        window.chrome.storage.local.set({
          museflow_shot_manager: this.toJSON()
        });
      }
    }

    toJSON() {
      return {
        projectId: this.projectId,
        visualBible: this.visualBible,
        shots: this.shots,
        snapshotsCount: this.snapshots.length,
        updatedAt: new Date().toISOString()
      };
    }

    fromJSON(data) {
      if (!data) return;
      if (data.projectId) this.projectId = data.projectId;
      if (data.visualBible) this.visualBible = Object.assign(this.createDefaultVisualBible(), data.visualBible);
      if (Array.isArray(data.shots)) {
        this.shots = data.shots.map(s => this.normalizeShot(s));
      }
      this.notify();
    }

    /**
     * 操作快照备份 (支持撤销，防止误删创作内容)
     */
    takeSnapshot(reason = '用户操作前自动备份') {
      const snap = {
        shots: JSON.parse(JSON.stringify(this.shots)),
        visualBible: JSON.parse(JSON.stringify(this.visualBible)),
        reason: reason,
        createdAt: new Date().toISOString()
      };
      this.snapshots.push(snap);
      if (this.snapshots.length > 10) this.snapshots.shift();
      return snap;
    }

    undoLastSnapshot() {
      if (this.snapshots.length === 0) return false;
      const snap = this.snapshots.pop();
      this.shots = snap.shots.map(s => this.normalizeShot(s));
      this.visualBible = Object.assign(this.createDefaultVisualBible(), snap.visualBible);
      this.notify();
      return true;
    }

    normalizeShot(raw) {
      const shotId = raw.shotId || `shot_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const candidates = Array.isArray(raw.candidateResults) ? raw.candidateResults : [];
      let selectedResultId = raw.selectedResultId || (candidates[0]?.resultId || null);

      return {
        shotId: shotId,
        sceneId: raw.sceneId || shotId,
        sceneNumber: raw.sceneNumber || 1,
        title: raw.title || `分镜 ${raw.sceneNumber || 1}`,
        shotVersion: raw.shotVersion || 1,
        status: raw.status || 'DRAFT', // DRAFT, READY, QUEUED, RUNNING, WAITING_DEPENDENCY, WAITING_REVIEW, COMPLETED, FAILED, CANCELED, STALE_REFERENCE
        imagePrompt: raw.imagePrompt || '',
        videoPrompt: raw.videoPrompt || '',
        localCameraOverride: raw.localCameraOverride || '',
        modelId: raw.modelId || 'flow',
        generationMode: raw.generationMode || 'text',
        targetDuration: raw.targetDuration || this.visualBible.targetDurationPerShot || 6.0,
        trimStart: typeof raw.trimStart === 'number' ? raw.trimStart : 0.0,
        trimEnd: typeof raw.trimEnd === 'number' ? raw.trimEnd : (raw.targetDuration || 6.0),
        candidateResults: candidates,
        selectedResultId: selectedResultId,
        dependencies: Object.assign({
          upstreamShotId: null,
          tailFrameAssetUrl: null,
          upstreamSelectedResultId: null,
          stale: false,
          staleReason: ''
        }, raw.dependencies || {}),
        // 审核与质检状态
        qcResult: raw.qcResult || { passed: true, issues: [], checkedAt: null },
        reviewStatus: raw.reviewStatus || 'PENDING_REVIEW', // PENDING_REVIEW, APPROVED, NEEDS_REVISION, SKIPPED
        reviewNotes: raw.reviewNotes || '',
        reviewedAt: raw.reviewedAt || null,
        reviewedVersionId: raw.reviewedVersionId || null,
        createdAt: raw.createdAt || new Date().toISOString(),
        updatedAt: raw.updatedAt || new Date().toISOString()
      };
    }

    compilePrompt(shotId, type = 'video') {
      const shot = this.getShot(shotId);
      if (!shot) return '';
      const vb = this.visualBible;
      const basePrompt = (type === 'image' ? shot.imagePrompt : shot.videoPrompt) || shot.title;

      const segments = [
        `[风格: ${vb.styleName}] ${vb.stylePrompt}`,
        `[主体设定: ${vb.subjectSetting.name}] ${vb.subjectSetting.features}`,
        `[光照色彩] ${vb.lighting}, ${vb.colorScheme}`,
        `[镜头摄影] ${shot.localCameraOverride || vb.lensCamera}`,
        `[分镜动态] ${basePrompt}`
      ];

      return segments.filter(Boolean).join(' | ');
    }

    getShot(shotId) {
      return this.shots.find(s => s.shotId === shotId);
    }

    getSelectedResult(shotId) {
      const shot = this.getShot(shotId);
      if (!shot || !shot.candidateResults.length) return null;
      return shot.candidateResults.find(r => r.resultId === shot.selectedResultId) || shot.candidateResults[0];
    }

    /**
     * 脚本导入三模式 (更新已有 / 追加新分镜 / 替换草稿) + 快照防御
     */
    importScenesWithMode(scenes, mode = 'update') {
      this.takeSnapshot(`导入分镜脚本 (模式: ${mode})`);

      if (mode === 'replace') {
        // 替换模式：全量重新创建
        this.shots = scenes.map((sc, idx) => {
          const shotId = `shot_${idx + 1}`;
          return this.normalizeShot({
            shotId: shotId,
            sceneId: `scene_${idx + 1}`,
            sceneNumber: sc.number || (idx + 1),
            title: sc.title || `场景 ${idx + 1}`,
            imagePrompt: sc.imagePrompt || '',
            videoPrompt: sc.videoPrompt || '',
            targetDuration: sc.seconds || 6.0,
            trimStart: 0.0,
            trimEnd: sc.seconds || 6.0,
            status: 'READY',
            dependencies: idx > 0 ? {
              upstreamShotId: `shot_${idx}`,
              tailFrameAssetUrl: null,
              stale: false
            } : {}
          });
        });
      } else if (mode === 'update') {
        // 更新模式：按场景号匹配，保留现有候选视频与已审状态
        scenes.forEach((sc, idx) => {
          const existing = this.shots.find(s => s.sceneNumber === sc.number);
          if (existing) {
            existing.title = sc.title || existing.title;
            existing.imagePrompt = sc.imagePrompt || existing.imagePrompt;
            existing.videoPrompt = sc.videoPrompt || existing.videoPrompt;
            existing.targetDuration = sc.seconds || existing.targetDuration;
            existing.updatedAt = new Date().toISOString();
          } else {
            const shotId = `shot_${this.shots.length + 1}`;
            this.shots.push(this.normalizeShot({
              shotId: shotId,
              sceneId: `scene_${this.shots.length + 1}`,
              sceneNumber: sc.number || (this.shots.length + 1),
              title: sc.title || `场景 ${sc.number}`,
              imagePrompt: sc.imagePrompt || '',
              videoPrompt: sc.videoPrompt || '',
              targetDuration: sc.seconds || 6.0,
              trimStart: 0.0,
              trimEnd: sc.seconds || 6.0,
              status: 'READY',
              dependencies: idx > 0 ? {
                upstreamShotId: this.shots[idx - 1]?.shotId || null,
                tailFrameAssetUrl: null,
                stale: false
              } : {}
            }));
          }
        });
      } else if (mode === 'append') {
        // 追加模式：新增到列表末尾
        const startNum = this.shots.reduce((max, s) => Math.max(max, s.sceneNumber || 0), 0);
        scenes.forEach((sc, idx) => {
          const shotId = `shot_${this.shots.length + 1}`;
          this.shots.push(this.normalizeShot({
            shotId: shotId,
            sceneId: `scene_${this.shots.length + 1}`,
            sceneNumber: startNum + idx + 1,
            title: sc.title || `场景 ${startNum + idx + 1}`,
            imagePrompt: sc.imagePrompt || '',
            videoPrompt: sc.videoPrompt || '',
            targetDuration: sc.seconds || 6.0,
            trimStart: 0.0,
            trimEnd: sc.seconds || 6.0,
            status: 'READY',
            dependencies: {
              upstreamShotId: this.shots[this.shots.length - 1]?.shotId || null,
              tailFrameAssetUrl: null,
              stale: false
            }
          }));
        });
      }

      this.notify();
      return this.shots;
    }

    initFromParsedScenes(scenes, replace = true) {
      return this.importScenesWithMode(scenes, replace ? 'replace' : 'update');
    }

    addCandidateResult(shotId, resultPayload) {
      const shot = this.getShot(shotId);
      if (!shot) throw new Error(`未找到镜头 ${shotId}`);

      const resultId = resultPayload.resultId || `res_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      const existing = shot.candidateResults.find(r => 
        r.resultId === resultId || (resultPayload.originTaskId && (r.originTaskId === resultPayload.originTaskId || r.taskId === resultPayload.originTaskId))
      );
      if (existing) {
        console.warn(`[ShotManager] Candidate result already exists for taskId: ${resultPayload.originTaskId}`);
        return existing;
      }

      const versionNum = shot.candidateResults.length + 1;
      const assetUrl = resultPayload.assetUrl || resultPayload.url;
      const sha = resultPayload.fileHash || resultPayload.sha256 || null;
      const taskId = resultPayload.originTaskId || resultPayload.taskId || null;

      const candidate = {
        resultId: resultId,
        version: versionNum,
        versionId: `v_${versionNum}`,
        label: `V${versionNum}`,
        originTaskId: taskId,
        taskId: taskId,
        assetId: resultPayload.assetId || resultId,
        assetUrl: assetUrl,
        fileHash: sha,
        sha256: sha,
        duration: typeof resultPayload.duration === 'number' ? resultPayload.duration : shot.targetDuration,
        promptSnapshot: resultPayload.promptSnapshot || this.compilePrompt(shotId),
        modelSnapshot: resultPayload.modelSnapshot || shot.modelId,
        referenceSnapshot: resultPayload.referenceSnapshot || [],
        createdAt: new Date().toISOString(),
        status: 'ready'
      };

      // 自动执行技术质检
      candidate.qc = this.performTechnicalQC(shotId, candidate);

      shot.candidateResults.push(candidate);
      shot.selectedResultId = candidate.resultId;
      shot.status = 'COMPLETED';
      shot.shotVersion = versionNum;
      // 重置审核状态为待复审 (新版本不可静默沿用旧审核通过)
      shot.reviewStatus = 'PENDING_REVIEW';
      shot.updatedAt = new Date().toISOString();

      this.checkDownstreamDependencies(shotId);
      this.notify();
      return candidate;
    }

    /**
     * 自动技术质检 (Technical QC)
     */
    performTechnicalQC(shotId, candidate) {
      const issues = [];
      const shot = this.getShot(shotId);
      if (!candidate.assetUrl) {
        issues.push('缺失媒体文件访问地址');
      }
      if (candidate.duration <= 0) {
        issues.push('视频时长为 0 或非法');
      }
      const qc = {
        passed: issues.length === 0,
        issues: issues,
        checkedAt: new Date().toISOString()
      };
      if (shot) {
        shot.qcResult = qc;
      }
      return qc;
    }

    /**
     * 人工审片状态流转
     */
    setReviewStatus(shotId, status, notes = '') {
      const shot = this.getShot(shotId);
      if (!shot) return false;
      shot.reviewStatus = status; // APPROVED, NEEDS_REVISION, SKIPPED, PENDING_REVIEW
      shot.reviewNotes = notes;
      shot.reviewedAt = new Date().toISOString();
      shot.reviewedVersionId = shot.selectedResultId;
      this.notify();
      return true;
    }

    selectCandidate(shotId, resultId) {
      const shot = this.getShot(shotId);
      if (!shot) return false;
      const cand = shot.candidateResults.find(r => r.resultId === resultId);
      if (!cand) return false;

      shot.selectedResultId = resultId;
      shot.status = 'COMPLETED';
      // 切换候选后重新判定审核有效性
      if (shot.reviewedVersionId !== resultId) {
        shot.reviewStatus = 'PENDING_REVIEW';
      }
      shot.updatedAt = new Date().toISOString();
      this.checkDownstreamDependencies(shotId);
      this.notify();
      return true;
    }

    checkDownstreamDependencies(upstreamShotId) {
      const upstreamShot = this.getShot(upstreamShotId);
      if (!upstreamShot) return;
      const upstreamSelected = this.getSelectedResult(upstreamShotId);

      this.shots.forEach(s => {
        if (s.dependencies && s.dependencies.upstreamShotId === upstreamShotId) {
          if (s.dependencies.upstreamSelectedResultId && s.dependencies.upstreamSelectedResultId !== upstreamSelected?.resultId) {
            s.dependencies.stale = true;
            s.dependencies.staleReason = `上游镜头 (${upstreamShot.title}) 已切换候选至 ${upstreamSelected?.label || '最新版'}，当前镜头仍使用旧尾帧`;
            if (s.status === 'COMPLETED' || s.status === 'READY') {
              s.status = 'STALE_REFERENCE';
            }
          }
        }
      });
    }

    updateTailFrameReference(shotId, newTailFrameUrl) {
      const shot = this.getShot(shotId);
      if (!shot || !shot.dependencies) return;
      const upstream = this.getShot(shot.dependencies.upstreamShotId);
      const upstreamSelected = upstream ? this.getSelectedResult(upstream.shotId) : null;

      shot.dependencies.tailFrameAssetUrl = newTailFrameUrl;
      shot.dependencies.upstreamSelectedResultId = upstreamSelected?.resultId || null;
      shot.dependencies.stale = false;
      shot.dependencies.staleReason = '';
      if (shot.status === 'STALE_REFERENCE') {
        shot.status = 'READY';
      }
      this.notify();
    }

    ackStaleReference(shotId) {
      const shot = this.getShot(shotId);
      if (!shot || !shot.dependencies) return;
      shot.dependencies.stale = false;
      if (shot.status === 'STALE_REFERENCE') {
        shot.status = shot.candidateResults.length > 0 ? 'COMPLETED' : 'READY';
      }
      this.notify();
    }

    async executeSingleShot(shotId, adapter, options = {}) {
      const shot = this.getShot(shotId);
      if (!shot) throw new Error(`未找到镜头 ${shotId}`);

      this.activeExecutingShotId = shotId;
      shot.status = 'RUNNING';
      this.notify();

      try {
        const compiledPrompt = options.prompt || this.compilePrompt(shotId, 'video');
        const referenceImages = [];

        if (shot.dependencies?.tailFrameAssetUrl) {
          referenceImages.push(shot.dependencies.tailFrameAssetUrl);
        } else if (this.visualBible.subjectSetting?.referenceAssetUrl) {
          referenceImages.push(this.visualBible.subjectSetting.referenceAssetUrl);
        }

        const genPayload = {
          type: 'MUSEFLOW_GENERATE',
          mediaType: 'video',
          prompt: compiledPrompt,
          model: shot.modelId || 'flow',
          duration: shot.targetDuration || 6,
          size: this.visualBible.aspectRatio || '16:9',
          referenceImages: referenceImages
        };

        const res = await adapter.handleMessage(genPayload);
        if (!res || !res.ok || !res.url) {
          throw new Error(res?.error || '生成接口未返回有效视频地址');
        }

        const cand = this.addCandidateResult(shotId, {
          assetUrl: res.url,
          duration: shot.targetDuration,
          promptSnapshot: compiledPrompt,
          modelSnapshot: shot.modelId
        });

        return { ok: true, candidate: cand, shot: shot };
      } catch (err) {
        shot.status = shot.candidateResults.length > 0 ? 'COMPLETED' : 'FAILED';
        this.notify();
        throw err;
      } finally {
        this.activeExecutingShotId = null;
      }
    }

    buildTimelineSpecs() {
      const specs = [];
      this.shots.forEach((s, idx) => {
        const sel = this.getSelectedResult(s.shotId);
        if (sel && sel.assetUrl) {
          specs.push({
            shot_id: s.shotId,
            source_url: sel.assetUrl,
            trim_start_s: s.trimStart || 0.0,
            trim_end_s: s.trimEnd || s.targetDuration,
            target_duration: (s.trimEnd || s.targetDuration) - (s.trimStart || 0.0),
            order: idx,
            title: s.title
          });
        }
      });
      return specs;
    }
    /**
     * 生成依赖感知批量任务计划 (P1)
     */
    generateBatchPlan(scope = 'unready') {
      let targets = [];
      if (scope === 'all') {
        targets = [...this.shots];
      } else if (scope === 'failed') {
        targets = this.shots.filter(s => s.status === 'FAILED');
      } else if (scope === 'unready') {
        targets = this.shots.filter(s => s.status !== 'COMPLETED' || !s.candidateResults.length);
      } else if (Array.isArray(scope)) {
        targets = this.shots.filter(s => scope.includes(s.shotId));
      } else {
        targets = [...this.shots];
      }

      // 依赖拓扑排序 (无前置依赖先执行，有依赖按序排列)
      const sorted = [];
      const visited = new Set();
      targets.forEach(t => {
        if (!t.dependencies?.upstreamShotId) {
          sorted.push(t);
          visited.add(t.shotId);
        }
      });
      targets.forEach(t => {
        if (!visited.has(t.shotId)) {
          sorted.push(t);
          visited.add(t.shotId);
        }
      });

      const plan = {
        totalShots: this.shots.length,
        targetShotsCount: sorted.length,
        shots: sorted.map(s => ({
          shotId: s.shotId,
          title: s.title,
          upstreamDependency: s.dependencies?.upstreamShotId || null,
          currentStatus: s.status,
          modelId: s.modelId
        })),
        concurrency: 1, // 严格单任务串行调度
        createdAt: new Date().toISOString()
      };
      this.batchState.plan = plan;
      return plan;
    }

    /**
     * 启动依赖感知批量执行
     */
    async startBatchExecution(adapter, scope = 'unready') {
      const plan = this.generateBatchPlan(scope);
      this.batchState.isRunning = true;
      this.batchState.isPaused = false;
      this.batchState.queue = [...plan.shots];
      this.notify();

      while (this.batchState.queue.length > 0) {
        if (this.batchState.isPaused) {
          console.log('[BatchExecutor] 批量执行已暂停');
          break;
        }
        if (!this.batchState.isRunning) {
          console.log('[BatchExecutor] 批量执行已终止');
          break;
        }

        const item = this.batchState.queue[0];
        const shot = this.getShot(item.shotId);
        if (!shot) {
          this.batchState.queue.shift();
          continue;
        }

        // 依赖检查：若上游镜头未完成，标记为 WAITING_DEPENDENCY
        if (shot.dependencies?.upstreamShotId) {
          const upstream = this.getShot(shot.dependencies.upstreamShotId);
          if (!upstream || upstream.status !== 'COMPLETED' || !upstream.candidateResults.length) {
            shot.status = 'WAITING_DEPENDENCY';
            this.notify();
            // 延缓当前镜头，等待上游
            break;
          }
        }

        this.batchState.activeShotId = shot.shotId;
        try {
          await this.executeSingleShot(shot.shotId, adapter);
        } catch (e) {
          console.error(`[BatchExecutor] 镜头 ${shot.shotId} 失败:`, e);
          shot.status = 'FAILED';
        } finally {
          this.batchState.queue.shift();
          this.notify();
        }
      }

      this.batchState.isRunning = false;
      this.batchState.activeShotId = null;
      this.notify();
      return { ok: true, completed: true };
    }

    pauseBatchExecution() {
      this.batchState.isPaused = true;
      this.notify();
    }

    resumeBatchExecution(adapter) {
      if (!this.batchState.isPaused) return;
      this.batchState.isPaused = false;
      this.batchState.isRunning = true;
      return this.startBatchExecution(adapter);
    }

    cancelBatchExecution() {
      this.batchState.isRunning = false;
      this.batchState.isPaused = false;
      this.batchState.queue = [];
      this.notify();
    }

    /**
     * 导出完整工程交付归档包 (P3)
     */
    exportArchivePackage() {
      const specs = this.buildTimelineSpecs();
      return {
        format: 'museflow-m10-archive',
        version: 2,
        appVersion: '0.5.0-m10',
        exportedAt: new Date().toISOString(),
        projectId: this.projectId,
        visualBible: this.visualBible,
        shots: this.shots.map(s => ({
          shotId: s.shotId,
          sceneNumber: s.sceneNumber,
          title: s.title,
          selectedCandidate: this.getSelectedResult(s.shotId),
          reviewStatus: s.reviewStatus,
          reviewNotes: s.reviewNotes,
          qcResult: s.qcResult,
          trimStart: s.trimStart,
          trimEnd: s.trimEnd,
          dependencies: s.dependencies
        })),
        timelineSpecs: specs,
        assetsManifest: this.shots.flatMap(s => s.candidateResults.map(c => ({
          shotId: s.shotId,
          resultId: c.resultId,
          assetUrl: c.assetUrl,
          sha256: c.fileHash || c.sha256,
          duration: c.duration,
          taskId: c.originTaskId || c.taskId
        })))
      };
    }
  }

  window.ShotManager = ShotManager;
  window.__shotManager = new ShotManager();
})();
