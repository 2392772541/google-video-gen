/**
 * MuseFlow 镜头级精细化生产管理模块 (M9 核心体系)
 * 职责：
 * 1. 稳定镜头身份 (shotId, sceneId, version)
 * 2. 单镜头独立执行与重新生成 (不波及其他镜头)
 * 3. 候选结果管理与无损版本回退 (V1, V2, V3 候选并存)
 * 4. 跨镜头依赖管理 (尾帧失效检测 STALE_REFERENCE)
 * 5. 工程全局视觉规范 (Project Visual Bible) 编译与镜头级覆写
 * 6. 时间线精确剪裁 (trim_start_s / trim_end_s)
 */
(() => {
  'use strict';

  class ShotManager {
    constructor() {
      this.projectId = 'default';
      this.visualBible = this.createDefaultVisualBible();
      this.shots = [];
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
        status: raw.status || 'DRAFT',
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

    initFromParsedScenes(scenes, replace = true) {
      const newShots = scenes.map((sc, idx) => {
        const shotId = `shot_${idx + 1}`;
        return this.normalizeShot({
          shotId: shotId,
          sceneId: `scene_${idx + 1}`,
          sceneNumber: sc.number || (idx + 1),
          title: sc.title || `场景 ${idx + 1}`,
          imagePrompt: sc.imagePrompt || '',
          videoPrompt: sc.videoPrompt || '',
          targetDuration: sc.seconds || this.visualBible.targetDurationPerShot || 6.0,
          trimStart: 0.0,
          trimEnd: sc.seconds || this.visualBible.targetDurationPerShot || 6.0,
          status: 'READY',
          dependencies: idx > 0 ? {
            upstreamShotId: `shot_${idx}`,
            tailFrameAssetUrl: null,
            stale: false
          } : {}
        });
      });

      if (replace) {
        this.shots = newShots;
      } else {
        this.shots = this.shots.concat(newShots);
      }
      this.notify();
      return this.shots;
    }

    addCandidateResult(shotId, resultPayload) {
      const shot = this.getShot(shotId);
      if (!shot) throw new Error(`未找到镜头 ${shotId}`);

      const resultId = resultPayload.resultId || `res_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      const existing = shot.candidateResults.find(r => 
        r.resultId === resultId || (resultPayload.originTaskId && r.originTaskId === resultPayload.originTaskId)
      );
      if (existing) {
        console.warn(`[ShotManager] Candidate result already exists for taskId: ${resultPayload.originTaskId}`);
        return existing;
      }

      const versionNum = shot.candidateResults.length + 1;
      const candidate = {
        resultId: resultId,
        version: versionNum,
        label: `V${versionNum}`,
        originTaskId: resultPayload.originTaskId || null,
        assetUrl: resultPayload.assetUrl || resultPayload.url,
        fileHash: resultPayload.fileHash || resultPayload.sha256 || null,
        duration: typeof resultPayload.duration === 'number' ? resultPayload.duration : shot.targetDuration,
        promptSnapshot: resultPayload.promptSnapshot || this.compilePrompt(shotId),
        modelSnapshot: resultPayload.modelSnapshot || shot.modelId,
        createdAt: new Date().toISOString(),
        status: 'ready'
      };

      shot.candidateResults.push(candidate);
      shot.selectedResultId = candidate.resultId;
      shot.status = 'COMPLETED';
      shot.shotVersion = versionNum;
      shot.updatedAt = new Date().toISOString();

      this.checkDownstreamDependencies(shotId);
      this.notify();
      return candidate;
    }

    selectCandidate(shotId, resultId) {
      const shot = this.getShot(shotId);
      if (!shot) return false;
      const cand = shot.candidateResults.find(r => r.resultId === resultId);
      if (!cand) return false;

      shot.selectedResultId = resultId;
      shot.status = 'COMPLETED';
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
  }

  window.ShotManager = ShotManager;
  window.__shotManager = new ShotManager();
})();
