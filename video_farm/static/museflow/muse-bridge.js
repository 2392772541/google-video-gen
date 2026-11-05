(() => {
  window.__museFlowBridgeVersion = '2026-10-30-v3';

  function t05Probe(stage, fields = {}) {
    try {
      const record = {
        testId: "T05",
        source: "bridge",
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

  window.__museFlowBridgeHandler = (message, _sender, sendResponse) => {
    if (message?.type === 'MUSEFLOW_CHECK_SESSION' || message?.type === 'MUSEFLOW_CHECK_SESSION_V3') {
      checkSession().then(sendResponse);
      return true;
    }
    if (message?.type === 'MUSEFLOW_GENERATE' || message?.type === 'MUSEFLOW_GENERATE_V3') {
      const controller=new AbortController();activeGenerations.set(message.requestId,controller);
      generate(message,controller.signal).then(sendResponse, error => sendResponse({ ok: false, code:error.code||'MUSE_ERROR', error: error.message || String(error) })).finally(()=>activeGenerations.delete(message.requestId));
      return true;
    }
    if (message?.type === 'MUSEFLOW_RECOVER_LATEST' || message?.type === 'MUSEFLOW_RECOVER_LATEST_V3') {
      recoverLatestMedia(message).then(
        sendResponse,
        error => sendResponse({ ok: false, error: error.message || String(error) })
      );
      return true;
    }
    if(message?.type==='MUSEFLOW_STOP_GENERATION' || message?.type==='MUSEFLOW_STOP_GENERATION_V3'){
      const stopped=message.requestId?abortGeneration(message.requestId):[...activeGenerations.keys()].some(id=>abortGeneration(id));
      sendResponse({ok:true,stopped});return false;
    }
    return false;
  };

  if (window.__museFlowBridgeListener && chrome.runtime?.onMessage?.removeListener) {
    try { chrome.runtime.onMessage.removeListener(window.__museFlowBridgeListener); } catch {}
  }
  window.__museFlowBridgeListener = (message, sender, sendResponse) => {
    if (typeof window.__museFlowBridgeHandler === 'function') {
      return window.__museFlowBridgeHandler(message, sender, sendResponse);
    }
    return false;
  };
  window.__museFlowBridgeInstalled = true;
  chrome.runtime.onMessage.addListener(window.__museFlowBridgeListener);

  function findPrecedingUserMsg(el) {
    if (!el) return null;
    const allUserMsgs = userMessageElements();
    let preceding = null;
    for (const um of allUserMsgs) {
      if (isFollowing(um, el)) preceding = um;
    }
    return preceding;
  }

  function rankMediaCandidates(items, { mediaType = 'video', size = '16:9', duration = 0 } = {}) {
    const [ratioW, ratioH] = String(size || '1:1').split(':').map(Number);
    const expectedRatio = ratioW > 0 && ratioH > 0 ? ratioW / ratioH : 1;
    const trimRe = /trim|cut|clip|first\d+s|mid\d+|[-_]\d+(?:\.\d+)?s(?:\b|\.mp4)/i;
    return [...items].sort((a, b) => {
      if (mediaType === 'video') {
        const labelA = `${a.label || ''} ${a.videoUrl || ''}`;
        const labelB = `${b.label || ''} ${b.videoUrl || ''}`;
        // 最高优先级：优先保存 10 秒完整原片（media-generation-），绝不让已加载宽高的 3 秒裁剪版排到前面
        const isRawA = /media-generation-/i.test(labelA) && !trimRe.test(labelA);
        const isRawB = /media-generation-/i.test(labelB) && !trimRe.test(labelB);
        if (isRawA !== isRawB) return isRawA ? -1 : 1;

        const isTrimA = trimRe.test(labelA);
        const isTrimB = trimRe.test(labelB);
        if (isTrimA !== isTrimB) return isTrimA ? 1 : -1;

        const durA = Number(a.videoDuration) || 0;
        const durB = Number(b.videoDuration) || 0;
        if (durA > 0 && durB > 0 && Math.abs(durA - durB) > 0.4) {
          return durB - durA; // 优先完整长原片（10s 优先于 3s）
        }
      }
      const wA = mediaType === 'video' ? a.videoWidth : a.width;
      const hA = mediaType === 'video' ? a.videoHeight : a.height;
      const wB = mediaType === 'video' ? b.videoWidth : b.width;
      const hB = mediaType === 'video' ? b.videoHeight : b.height;
      const hasDimA = Boolean(wA && hA);
      const hasDimB = Boolean(wB && hB);
      if (hasDimA && hasDimB) {
        const scoreA = Math.abs(Math.log((wA / hA) / expectedRatio));
        const scoreB = Math.abs(Math.log((wB / hB) / expectedRatio));
        if (Math.abs(scoreA - scoreB) > 0.03) return scoreA - scoreB;
      } else if (hasDimA !== hasDimB) {
        return hasDimA ? -1 : 1;
      }
      if (mediaType === 'video') {
        // 同一轮中 10s 原片总是先于裁剪版出现
        return isFollowing(a.el, b.el) ? -1 : 1;
      }
      return isFollowing(a.el, b.el) ? 1 : -1;
    });
  }

  async function resolveTransferableMediaUrl(src, mediaType = 'video') {
    if (!src) return { url: '', error: '媒体地址为空' };
    if (src.startsWith('data:')) return { url: src };
    if (mediaType === 'video' && !src.startsWith('blob:')) return { url: src };
    try {
      const fetchOpts = src.startsWith('blob:') ? {} : { credentials: 'include' };
      const response = await fetch(src, fetchOpts);
      if (!response.ok) throw new Error(`${mediaType === 'video' ? '视频' : '图片'}下载返回 HTTP ${response.status}.`);
      const blob = await response.blob();
      return { url: await blobToDataUrl(blob) };
    } catch (error) {
      return { url: src, error: `新${mediaType === 'video' ? '视频' : '图片'}已检测到，但无法复制到本地：${error.message}` };
    }
  }

  async function recoverLatestMedia(message = {}) {
    const mediaType = typeof message === 'string' ? message : (message.mediaType || 'video');
    const wantVideo = mediaType !== 'image';
    const items = attachments().filter(item => wantVideo ? Boolean(item.videoUrl) : (Boolean(item.src) && !item.isVideo));
    if (!items.length) {
      return { ok: false, error: '当前 Muse 聊天中还没有可收回的视频附件。请确认聊天里的视频已经生成并能播放。' };
    }
    const rawPrompt = String(message?.prompt || '').trim();
    const rawSceneLabel = String(message?.sceneLabel || '').trim();
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
        const um = findPrecedingUserMsg(item.el);
        const userText = (um?.innerText || um?.textContent || '').replace(/\s+/g, ' ');
        const labelText = String(item.label || '');
        if (shotRegex && (shotRegex.test(userText) || shotRegex.test(labelText))) return true;
        if (promptSnippet && userText.toLowerCase().includes(promptSnippet)) return true;
        return false;
      });
    }

    const anchorItem = matchedItems.length ? matchedItems[matchedItems.length - 1] : items[items.length - 1];
    const targetUserMsg = findPrecedingUserMsg(anchorItem.el);
    const turnPool = targetUserMsg
      ? items.filter(item => findPrecedingUserMsg(item.el) === targetUserMsg)
      : (matchedItems.length ? matchedItems : items.slice(-2));
    const ranked = rankMediaCandidates(turnPool.length ? turnPool : items, {
      mediaType,
      size: message?.size || '16:9',
      duration: message?.duration || 0
    });
    const best = ranked[0] || anchorItem;
    const rawUrl = wantVideo ? best.videoUrl : best.src;
    if (!rawUrl) {
      return { ok: false, error: '页面上还没有可收回的视频。请确认聊天里的视频已经能播放。' };
    }
    let reviewNotes = '';
    try {
      const bubbles = assistantMessageElements().filter(b => !targetUserMsg || isFollowing(targetUserMsg, b));
      reviewNotes = bubbles.map(b => (b.innerText || b.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean).join('\n').slice(-2000);
    } catch {}
    const transferred = await resolveTransferableMediaUrl(rawUrl, mediaType);
    return {
      ok: true,
      url: transferred.url,
      posterUrl: best.posterUrl || '',
      width: best.videoWidth || best.width || 0,
      height: best.videoHeight || best.height || 0,
      duration: best.videoDuration || 0,
      label: best.label || '',
      reviewNotes,
      error: transferred.error
    };
  }

  function findComposer() {
    const candidates=[...document.querySelectorAll('textarea')].filter(el=>visible(el)&&!el.disabled);
    return candidates.find(el=>/message|消息/i.test(el.getAttribute('placeholder')||''))||candidates[0]||null;
  }

  function isChineseGenerationFailure(context) {
    const text = String(context || "").replace(/\s+/g, " ").trim();
    const failure = /(?:没能|未能|无法|不能|没(?:有)?)\s*(?:成功)?\s*(?:生成|制作|创建|渲染|完成)(?:出来)?|(?:生成|制作|渲染)\s*(?:失败|未成功)/u;
    const acknowledgement = /(?:抱歉|对不起|很遗憾|换个做法|换种方式|换一种方式|改成|改为)/u;
    const hypothetical = /(?:如果|假如|若).{0,25}(?:没能|未能|无法|不能|没(?:有)?).{0,20}(?:生成|制作|创建|渲染|完成)/u;
    return failure.test(text) && acknowledgement.test(text) && !hypothetical.test(text);
  }

  function visible(el) { return Boolean(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'); }
  function isFollowing(elA, elB) {
    try {
      if (!elA || !elB || !elA.compareDocumentPosition) return false;
      var mask = (typeof Node !== 'undefined' && Node.DOCUMENT_POSITION_FOLLOWING) || 4;
      return Boolean(elA.compareDocumentPosition(elB) & mask);
    } catch (e) { return false; }
  }
  const delay = (ms,signal) => new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(new DOMException("用户已停止生成。",'AbortError'));return;}
    const timer=setTimeout(()=>{signal?.removeEventListener('abort',cancel);resolve();},ms);
    const cancel=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);reject(new DOMException("用户已停止生成。",'AbortError'));};
    signal?.addEventListener('abort',cancel,{once:true});
  });
  const attachmentSelector='[data-testid^="hatch-chat-attachment-presentation-"]';
  const activeGenerations=new Map();
  const consumedAttachmentSrcs=new Set();
  const staleOrCancelledPrompts=new Set();
  const quarantinedAttachments=new Set();

  function isNonChatOrAvatarElement(el) {
    if (!el || typeof el.closest !== 'function') return true;
    if (el.hasAttribute?.('data-hatch-avatar-layer') || el.querySelector?.('[data-hatch-avatar-layer]')) return true;
    if (el.closest('[data-hatch-avatar-layer],[data-testid*="status-panel" i],[data-testid*="avatar" i],[class*="status-panel" i],[class*="avatar-layer" i],aside,header,nav,form,[class*="chat-user-bubble"],[data-message-author-role="user"],[data-testid="hatch-composer-placeholder-overlay"]')) return true;
    if (el.getAttribute?.('aria-label') === 'Muse' || el.closest('[role="button"][aria-label="Muse"]')) return true;
    const inPresentation = Boolean(el.closest('[data-testid^="hatch-chat-attachment-presentation-"]'));
    const inAssistantBubble = Boolean(el.closest('div[class*="hatch-chat-groupable-bubble"],[data-message-author-role="assistant"]'));
    return !inPresentation && !inAssistantBubble;
  }

  function clickMuseStop(){
    const button=[...document.querySelectorAll('[data-testid="hatch-composer-stop-button"],button[aria-label*="Stop" i],button[aria-label*="停止"]')].find(visible);
    if(button){button.click();return true;}return false;
  }

  function abortGeneration(requestId){
    const controller=activeGenerations.get(requestId);
    if(!controller)return false;
    controller.abort();clickMuseStop();
    attachments().forEach(a=>{if(a?.src)consumedAttachmentSrcs.add(a.src);});
    return true;
  }

  async function checkSession() {
    await waitHydrated(5000);
    const composer=findComposer();
    const ready=Boolean(composer&&visible(composer)&&!composer.disabled&&!composer.readOnly);
    const loginRequired=Boolean(document.querySelector('input[type="password"],button[type="submit"]'))&&/sign in|log in|登录/i.test(document.body?.innerText||'');
    return {ok:true,signedIn:ready&&!loginRequired,title:document.title,composer:ready,loginRequired,url:location.href};
  }

  async function waitHydrated(timeout,signal) {
    const end=Date.now()+timeout;
    while(Date.now()<end){
      const hydration=document.querySelector('[data-hatch-shell-hydration-state]');
      if(document.readyState==='complete'&&findComposer()&&(!hydration||hydration.getAttribute('data-hatch-shell-hydration-state')==='hydrated'))return;
      if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');
      await delay(120,signal);
    }
    if(!findComposer())throw new Error("Muse 聊天尚未就绪。请打开 Muse 聊天页面，等待输入框加载。");
  }

  function attachments() {
    const rawList = [];
    const presentations = [...document.querySelectorAll(attachmentSelector)].filter(el => !isNonChatOrAvatarElement(el));
    for (const pres of presentations) {
      const innerVideos = [...pres.querySelectorAll('video')].filter(v => !isNonChatOrAvatarElement(v));
      if (innerVideos.length > 1) {
        for (const v of innerVideos) {
          const card = v.closest('div[class*="hatch-chat-groupable-bubble"],[role="button"][aria-label]') || v;
          rawList.push(card);
        }
      } else {
        rawList.push(pres);
      }
    }
    const uniqueElements = [...new Set(rawList)].filter(el => !isNonChatOrAvatarElement(el));
    return uniqueElements.map(el=>{
      const isVidTag=el.tagName==='VIDEO'||(typeof HTMLVideoElement!=='undefined'&&el instanceof HTMLVideoElement);
      const isImgTag=el.tagName==='IMG'||(typeof HTMLImageElement!=='undefined'&&el instanceof HTMLImageElement);
      const presAncestor=el.closest?.('[data-testid^="hatch-chat-attachment-presentation-"]');
      const tid=el.getAttribute('data-testid')||presAncestor?.getAttribute('data-testid')||'';
      const video=isVidTag?el:el.querySelector('video');
      const image=isImgTag?el:el.querySelector('img');
      if (video && isNonChatOrAvatarElement(video)) return null;
      const label=el.getAttribute?.('aria-label')||el.querySelector?.('[role="button"][aria-label]')?.getAttribute('aria-label')||video?.closest?.('[role="button"][aria-label]')?.getAttribute('aria-label')||'';
      const urls=[...el.querySelectorAll('a[href],video source[src],source[src],[data-video-src],[data-download-url],video[src],img[src]')].map(item=>({url:item.href||item.src||item.getAttribute('data-video-src')||item.getAttribute('data-download-url')||'',download:item.getAttribute('download')||'',type:item.getAttribute('type')||''})).filter(item=>item.url);
      if(el.tagName==='A'&&el.href) urls.push({url:el.href,download:el.getAttribute('download')||'',type:el.getAttribute('type')||''});
      if(video?.currentSrc) urls.push({url:video.currentSrc,download:'',type:'video/mp4'});
      else if(video?.src) urls.push({url:video.src,download:'',type:'video/mp4'});
      const videoLink=urls.find(item=>/video\//i.test(item.type)||/\.(?:mp4|webm|mov|m4v)(?:$|[?#])/i.test(item.url)||/\.(?:mp4|webm|mov|m4v)$/i.test(item.download))?.url||'';
      const videoUrl=video?.currentSrc||video?.src||videoLink||'';
      const posterUrl=image?.currentSrc||image?.src||urls.find(u=>/\.(?:png|jpe?g|webp)(?:$|[?#])/i.test(u.url))?.url||'';
      const isCard=Boolean(tid);
      const isVideoCard=Boolean(videoUrl) || isVidTag || Boolean(video) || /video/i.test(tid) || Boolean(el.querySelector('video'));
      const videoWidth=video?.videoWidth||0;
      const videoHeight=video?.videoHeight||0;
      const videoDuration=Number.isFinite(video?.duration)&&video.duration>0?Number(video.duration):0;
      const imageWidth=image?.naturalWidth||0;
      const imageHeight=image?.naturalHeight||0;
      return {
        el,
        tid,
        label,
        isCard,
        isVideo: isVideoCard,
        hasVideoUrl: Boolean(videoUrl),
        videoUrl,
        posterUrl,
        src: videoUrl || posterUrl || urls[0]?.url || '',
        videoWidth,
        videoHeight,
        videoDuration,
        imageWidth,
        imageHeight,
        width: isVideoCard ? videoWidth : imageWidth,
        height: isVideoCard ? videoHeight : imageHeight
      };
    }).filter(a=>a&&(a.src || a.isCard));
  }

  function waitForAttachmentChange(timeoutMs,signal){
    return new Promise(resolve=>{
      let timer;
      const observer=new MutationObserver(()=>finish());
      const finish=()=>{observer.disconnect();clearTimeout(timer);signal?.removeEventListener('abort',finish);resolve();};
      observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['src','poster','href','download','type','data-testid','data-video-src','data-download-url']});
      timer=setTimeout(finish,timeoutMs);
      signal?.addEventListener('abort',finish,{once:true});
    });
  }

  function assistantMessageElements(){
    return [...document.querySelectorAll('div[class*="hatch-chat-groupable-bubble"],[data-message-author-role="assistant"],[data-testid*="assistant" i],[data-testid*="message-content" i],[class*="assistant-message" i],[class*="assistant-bubble" i]')].filter(el=>visible(el)&&!el.closest('[class*="chat-user-bubble"],[data-message-author-role="user"],[data-testid*="user-message" i]'));
  }
  function userMessageElements(){
    return [...document.querySelectorAll('[class*="chat-user-bubble"],[data-message-author-role="user"],[data-testid*="user-message" i]')].filter(visible);
  }

  function readNewAssistantContext(previousBubbleTexts){
    const bubbles=assistantMessageElements();
    // Muse wraps assistant replies in group containers too; excluding every group/msg
    // ancestor accidentally filtered out the refusal text that should trigger retry.
    const messages=bubbles.map(el=>({el,text:(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim()})).filter(item=>item.text&&item.text!==previousBubbleTexts.get(item.el));
    return messages.map(item=>item.text).join('\n').slice(-6000);
  }

  function isRefusalContext(context){
    const text=String(context||'');
    const explicit=/(?:i|we)\s+(?:am\s+)?sorry[\s\S]{0,180}(?:cannot|can't|unable|won't)|(?:cannot|can't|couldn't|unable to|not able to)\s+(?:help|assist|create|generate|make|produce|fulfill|complete|comply)|(?:request|prompt).{0,100}(?:violat|disallowed|restricted|not allowed)|(?:policy|safety).{0,100}(?:prevent|restrict|unable)|generation (?:was )?(?:declined|blocked)|content (?:is )?not allowed|i can't comply/i;
    const inability=/(?:không tạo được|không thể tạo|chưa thể tạo|không thực hiện được|vẫn không tạo được|không làm được)/i;
    const sceneContext=/(?:cảnh|bản|đoạn|video|ảnh|nội dung|yêu cầu|này)/i;
    const offerAlternative=/(?:bản|phiên bản|phương án)\s+tương\s+đương|tương\s+đương.{0,100}(?:bám|theo|kịch bản)|muốn.{0,100}(?:tạo mới|thử lại|làm lại)|(?:would you like|do you want|want me to).{0,100}(?:create|make|generate|try)|equivalent alternative/i;
    return explicit.test(text)||(inability.test(text)&&(sceneContext.test(text)||offerAlternative.test(text)))||isChineseGenerationFailure(text);
  }

  function isFailureOrErrorContext(text){
    if(!text)return false;
    const pattern=/(?:generation|generating|video generation|image generation)\s+(?:failed|error|stopped|interrupted|aborted)|(?:failed\s+to\s+(?:generate|create|render|process|load))|(?:error\s+(?:occurred|generating|processing))|(?:something\s+went\s+wrong)|(?:service\s+unavailable)|(?:timed?\s*out)|(?:internal\s+server\s+error)|(?:rate\s+limit)|(?:unsupported\s+prompt)|(?:content\s+filter)|(?:violat(?:es?|ion)\s+of\s+terms)|(?:quota\s+exceeded)|(?:out of credits|insufficient credits)|(?:生成失败|视频生成失败|图片生成失败|生成错误|渲染失败|服务异常|网络错误|请求超时|发生错误|出错了|无法处理|生成中断|内容受限|违规内容|违规提示词|额度不足|积分不足)/i;
    return pattern.test(text);
  }

  function findPageErrorText(){
    const alerts=[...document.querySelectorAll('[role="alert"],[class*="toast" i],[class*="banner" i],[class*="notification" i],[class*="error-message" i],[class*="error_message" i]')].filter(visible);
    for(const alert of alerts){
      const text=(alert.innerText||alert.textContent||'').trim();
      if(isFailureOrErrorContext(text))return text;
    }
    return '';
  }

  async function generate({prompt,timeoutSec=600,mediaType='image',referenceImage='',referenceImages=[],size='1:1',duration=0,model='muse-image',requestId},signal) {
    const throwIfAborted=()=>{if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');};
    throwIfAborted();
    if(!String(prompt||'').trim())throw new Error("提示词为空。");
    const promptSummary=String(prompt||'').slice(0,30).trim();
    if(promptSummary)staleOrCancelledPrompts.delete(promptSummary);
    const markPromptStale=()=>{if(promptSummary)staleOrCancelledPrompts.add(promptSummary);};
    await waitHydrated(15000,signal);
    throwIfAborted();

    // 若页面尚有残留的生成任务，先安全停止并清理，防止旧任务迟到结果与新任务混淆串号
    const existingStop=document.querySelector('[data-testid="hatch-composer-stop-button"],button[aria-label*="Stop" i],button[aria-label*="停止"]');
    if(existingStop&&visible(existingStop)){clickMuseStop();await delay(400,signal);}

    const composer=findComposer();
    if(!visible(composer))throw new Error("Muse 输入框不可见。请打开聊天输入框后重试。");
    const referenceList=Array.isArray(referenceImages)&&referenceImages.length?referenceImages:referenceImage?[referenceImage]:[];
    if(referenceList.length)await attachReferences(referenceList,signal);
    throwIfAborted();
    const baseline=new Set(attachments().map(a=>a.src));
    const priorBubbles=new Set(assistantMessageElements());
    const priorBubbleTexts=new Map([...priorBubbles].map(el=>[el,(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim()]));
    composer.scrollIntoView({block:'center'});composer.focus();
    const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set;
    if(!setter)throw new Error("不支持此 Muse 输入框。");
    setter.call(composer,String(prompt));
    composer.dispatchEvent(new Event('input',{bubbles:true}));
    composer.dispatchEvent(new Event('change',{bubbles:true}));
    let sendButton=null;
    for(let i=0;i<30;i++){
      throwIfAborted();
      sendButton=[...document.querySelectorAll('button,[role="button"]')].filter(visible).find(b=>/send|发送/i.test(`${b.getAttribute('aria-label')||''} ${b.getAttribute('data-testid')||''} ${b.innerText||''}`));
      if(sendButton&&!sendButton.disabled)break;
      await delay(100,signal);
    }
    if(!composer.value.trim())throw new Error("提示词未成功填入 Muse 输入框，未提交任何内容。");
    const bubbleCount=()=>document.querySelectorAll('div[class*="hatch-chat-groupable-bubble"]').length;
    const beforeSendCount=bubbleCount();
    let submitted=false;
    throwIfAborted();
    if(sendButton&&!sendButton.disabled){sendButton.click();submitted=true;}
    else {
      // Match M2A's keyboard fallback: submit once only when Muse exposes no active Send button.
      const form=composer.closest('form');
      if(form&&typeof form.requestSubmit==='function'){form.requestSubmit();submitted=true;}
      else {
        composer.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));
        composer.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',bubbles:true}));
        submitted=true;
      }
    }
    let accepted=false;
    for(let i=0;i<30;i++){
      throwIfAborted();
      if(!composer.isConnected||!composer.value.trim()||bubbleCount()>beforeSendCount||document.querySelector('[data-testid="hatch-composer-stop-button"],button[aria-label*="Stop" i],button[aria-label*="停止"]')){accepted=true;break;}
      await delay(100,signal);
    }
    if(!submitted||!accepted)throw new Error("Muse 未确认提示词已提交。请检查聊天输入框后重试；MuseFlow 不会自动重复提交。");
    const userMsgAnchor=userMessageElements().pop();
    const deadline=Date.now()+Math.min(900,Math.max(30,Number(timeoutSec)||600))*1000;
    const submitTime=Date.now();
    let lastProgress=Date.now(),firstWrongRatioAt=0,firstZeroDimAt=0;
    let refusalContext='',refusalContextSince=0;
    let currentContext='';
    let generationEverActive=false,stopDisappearedAt=0;
    let cardEverDetected=false;
    let videoEverResolved=false;
    let firstVideoResolvedAt=0;
    try{
    while(Date.now()<deadline){
      throwIfAborted();
      currentContext=String(readNewAssistantContext(priorBubbleTexts)||'');
      const stop=Boolean(document.querySelector('[data-testid="hatch-composer-stop-button"],button[aria-label*="Stop" i],button[aria-label*="停止"]'));
      if(stop){
        generationEverActive=true;
        stopDisappearedAt=0;
        lastProgress=Date.now();
      }else if(generationEverActive&&!stopDisappearedAt){
        stopDisappearedAt=Date.now();
      }
      const fresh=attachments().filter(a=>{
        if(baseline.has(a.src))return false;
        if(consumedAttachmentSrcs.has(a.src))return false;
        if(quarantinedAttachments.has(a.src))return false;
        // 严格气泡归属检测：如果该媒体位于提交前已存在的老气泡中，判定为迟到的旧结果，坚决剔除（防串号）
        const bubble=a.el?.closest('div[class*="hatch-chat-groupable-bubble"],[data-message-author-role="assistant"]');
        if(bubble&&priorBubbles.has(bubble))return false;
        // 直接前置用户消息与回合指纹校验（防跨任务迟到回包）
        const allUserMsgs=userMessageElements();
        let directPrecedingUserMsg=null;
        for(const um of allUserMsgs){
          if(isFollowing(um, a.el)){
            directPrecedingUserMsg=um;
          }
        }
        if(directPrecedingUserMsg){
          const precedingText=(directPrecedingUserMsg.innerText||directPrecedingUserMsg.textContent||'').trim();
          if(userMsgAnchor&&userMsgAnchor.isConnected&&directPrecedingUserMsg!==userMsgAnchor){
            const isStale=[...staleOrCancelledPrompts].some(p=>p&&precedingText.includes(p));
            if(isStale){
              consumedAttachmentSrcs.add(a.src);
              quarantinedAttachments.add(a.src);
              return false;
            }
            const promptKeyword=promptSummary.slice(0,20);
            const matchesCurrentPrompt=promptKeyword?precedingText.includes(promptKeyword):true;
            if(!matchesCurrentPrompt){
              return false;
            }
          }
        }else if(userMsgAnchor&&a.el){
          if(!isFollowing(userMsgAnchor, a.el)){
            consumedAttachmentSrcs.add(a.src);
            return false;
          }
        }
        if(!directPrecedingUserMsg&&!userMsgAnchor&&!generationEverActive){
          quarantinedAttachments.add(a.src);
          return false;
        }
        return true;
      });
      const matching=fresh.filter(a=>mediaType==='video'?(a.isVideo||a.isCard):!a.isVideo);
      if(mediaType==='video'){
        const cardCandidate=matching.find(a=>a.isCard||a.isVideo);
        if(cardCandidate&&!cardEverDetected){
          cardEverDetected=true;
          t05Probe('VIDEO_CARD_DETECTED', { requestId, hasMedia: false });
        }
      }

      const readyItems=matching.filter(a=>mediaType==='video'?Boolean(a.videoUrl):Boolean(a.src));
      const [ratioW,ratioH]=String(size||'1:1').split(':').map(Number),expectedRatio=ratioW>0&&ratioH>0?ratioW/ratioH:1;
      
      let result=null;
      if(readyItems.length>0){
        if(mediaType==='video'&&!videoEverResolved){
          videoEverResolved=true;
          firstVideoResolvedAt=Date.now();
          t05Probe('VIDEO_URL_RESOLVED', { requestId, hasMedia: true, width: readyItems[0].videoWidth, height: readyItems[0].videoHeight });
        }
        const measured=rankMediaCandidates(readyItems,{mediaType,size,duration});
        const best=measured[0];
        if(mediaType==='video'){
          const videoEl = best.el?.tagName === 'VIDEO' ? best.el : best.el?.querySelector?.('video');
          if (videoEl && (!best.videoWidth || !best.videoHeight)) {
            try { if (videoEl.preload === 'none') videoEl.preload = 'metadata'; } catch {}
          }
          if(best.videoWidth>0&&best.videoHeight>0){
            firstZeroDimAt=0;
            const ratioError=Math.abs(Math.log((best.videoWidth/best.videoHeight)/expectedRatio));
            if(ratioError<=0.09||!stop||Date.now()-firstWrongRatioAt>=4000) result=best;
            else if(!firstWrongRatioAt) firstWrongRatioAt=Date.now();
          }else{
            if(!firstZeroDimAt) firstZeroDimAt=Date.now();
            else if(Date.now()-firstZeroDimAt>=3500) result=best;
          }
        }else{
          result=best;
        }
      }
      if(result){
        const src=mediaType==='video'?result.videoUrl:(result.src||result.posterUrl);
        if(!src){firstWrongRatioAt=firstWrongRatioAt||Date.now();await waitForAttachmentChange(Math.min(500,deadline-Date.now()),signal);continue;}
        consumedAttachmentSrcs.add(src);
        if(result.videoUrl)consumedAttachmentSrcs.add(result.videoUrl);
        if(result.posterUrl)consumedAttachmentSrcs.add(result.posterUrl);
        const reviewNotes=currentContext.trim();
        const transferred=await resolveTransferableMediaUrl(src,mediaType);
        return {ok:true,url:transferred.url,posterUrl:result.posterUrl,reviewNotes,width:result.videoWidth,height:result.videoHeight,duration:result.videoDuration||0,error:transferred.error};
      }
      const refusal=isRefusalContext(currentContext);
      if(refusal){
        if(currentContext!==refusalContext){refusalContext=currentContext;refusalContextSince=Date.now();}
        if(Date.now()-refusalContextSince>=1200){
          if(stop)clickMuseStop();
          const error=new Error(`Muse 生成失败：${currentContext.slice(-700)}`);error.code='MUSE_GENERATION_FAILED';throw error;
        }
      }
      else{refusalContext='';refusalContextSince=0;}

      const pageError=findPageErrorText();
      const assistantError=isFailureOrErrorContext(currentContext)?currentContext.slice(-700):'';
      if(assistantError||pageError){
        if(stop)clickMuseStop();
        const errDetail=assistantError||pageError;
        const error=new Error(`Muse 提示生成失败：${errDetail}`);error.code='GENERATION_FAILED';throw error;
      }

      const elapsedSinceSubmit=Date.now()-submitTime;
      const composerNow=findComposer();
      const composerReady=Boolean(composerNow&&!composerNow.disabled&&visible(composerNow));
      const stopGraceMs=matching.length>0?8000:3500;
      const stoppedAfterActive=generationEverActive&&stopDisappearedAt&&Date.now()-stopDisappearedAt>=stopGraceMs&&composerReady;
      const idleWithoutActivity=!generationEverActive&&elapsedSinceSubmit>=12000&&!stop&&composerReady;
      if(stoppedAfterActive||idleWithoutActivity){
        const tail=(document.body?.innerText||'').slice(-800);
        if(/out of credits|insufficient credits|额度不足|积分不足/i.test(tail)){
          const err=new Error("Muse 账号的生成额度已耗尽。");err.code='OUT_OF_CREDITS';throw err;
        }
        const lastMsg=currentContext.trim()||tail.slice(-300).trim();
        if(readyItems.length>0){
          const fallbackItem=rankMediaCandidates(readyItems,{mediaType,size,duration})[0];
          const fallbackSrc=mediaType==='video'?fallbackItem.videoUrl:(fallbackItem.src||fallbackItem.posterUrl);
          if(fallbackSrc){
            consumedAttachmentSrcs.add(fallbackSrc);
            const transferred=await resolveTransferableMediaUrl(fallbackSrc,mediaType);
            return {ok:true,url:transferred.url,posterUrl:fallbackItem.posterUrl,reviewNotes:lastMsg,width:fallbackItem.videoWidth,height:fallbackItem.videoHeight,duration:fallbackItem.videoDuration||0,error:transferred.error};
          }
        }
        const failReason=lastMsg?`（页面反馈：${lastMsg}）`:'（Muse 已停止响应且未生成新的媒体附件，可能生成出错或服务异常）';
        const error=new Error(`Muse ${mediaType==='video'?'视频':'图片'}生成失败${failReason}。`);
        error.code='GENERATION_FAILED';
        error.reviewNotes=lastMsg;
        throw error;
      }

      if(!stop&&Date.now()-lastProgress>5000){
        const tail=(document.body?.innerText||'').slice(-800);
        if(/out of credits|insufficient credits|额度不足|积分不足/i.test(tail)){
          const err=new Error("Muse 账号的生成额度已耗尽。");err.code='OUT_OF_CREDITS';throw err;
        }
        if(document.querySelector('input[type="password"]')&&/sign in|log in|登录/i.test(tail)){
          const err=new Error("Muse 登录已失效或需要重新登录。");err.code='LOGIN_REQUIRED';throw err;
        }
      }
      await waitForAttachmentChange(Math.min(500,deadline-Date.now()),signal);
    }
    throwIfAborted();
    markPromptStale();
    if (mediaType === 'video' && !cardEverDetected) {
      const err = new Error('等待 Muse 生成视频超时：未在页面检测到任何新生成卡片（NO_CARD_DETECTED）。提示词仅提交了一次，没有重复提交。');
      err.code = 'NO_CARD_DETECTED';
      throw err;
    }
    if (mediaType === 'video' && !videoEverResolved) {
      const err = new Error('等待 Muse 视频就绪超时：已检测到生成卡片，但未解析到有效视频流地址（VIDEO_URL_UNRESOLVED）。提示词仅提交了一次，没有重复提交。');
      err.code = 'VIDEO_URL_UNRESOLVED';
      throw err;
    }
    throw new Error(`等待 Muse 返回新的${mediaType==='video'?'视频':'图片'}附件超时。提示词仅提交了一次，没有重复提交。`);
    }catch(err){
      if(err.name==='AbortError'||/超时|timeout/i.test(err.message)||err.code==='GENERATION_FAILED'||err.code==='SCENE_REFUSED'){
        markPromptStale();
      }
      throw err;
    }
  }

  async function attachReferences(references,signal){
    const cappedRefs = Array.isArray(references) ? references.slice(0, 9) : [];
    const files=await Promise.all(cappedRefs.map(async(reference,index)=>{
      const url=typeof reference==='string'?reference:reference?.url;
      if(!url)throw new Error(`参考图片 ${index+1}没有 URL。`);
      if(url.startsWith('data:')){
        const arr=url.split(',');
        const mime=arr[0].match(/:(.*?);/)?.[1]||'image/png';
        const bstr=atob(arr[1]||'');
        let n=bstr.length;
        const u8arr=new Uint8Array(n);
        while(n--)u8arr[n]=bstr.charCodeAt(n);
        const extension=(mime.split('/')[1]||'png').replace('jpeg','jpg').replace(/[^a-z0-9]/gi,'')||'png';
        return new File([u8arr],`museflow-reference-${String(index+1).padStart(2,'0')}.${extension}`,{type:mime});
      }
      const response=await fetch(url,{credentials:'include'});
      if(!response.ok)throw new Error(`无法加载参考图片 ${index+1} (${response.status}).`);
      const blob=await response.blob();
      if(!blob.type.startsWith('image/')||!blob.size)throw new Error(`参考图 ${index+1}不是可读取的图片。`);
      const extension=(blob.type.split('/')[1]||'png').replace('jpeg','jpg').replace(/[^a-z0-9]/gi,'')||'png';
      return new File([blob],`museflow-reference-${String(index+1).padStart(2,'0')}.${extension}`,{type:blob.type});
    }));
    const composer=findComposer();
    let composerRoot=composer.closest('form')||composer.parentElement;
    for(let i=0;i<8&&composerRoot?.parentElement;i++){
      if(composerRoot.querySelector('input[type="file"]'))break;
      composerRoot=composerRoot.parentElement;
    }
    const acceptsImage=input=>{
      const accept=(input.accept||'').toLowerCase();
      return !accept||accept.includes('image')||accept.includes('*/*')||/\.(png|jpe?g|webp|gif|bmp|avif)/.test(accept);
    };
    const findInput=()=>{
      const all=[...document.querySelectorAll('input[type="file"]')].filter(input=>!input.disabled&&acceptsImage(input));
      const isImageInput=input=>/image|\.png|\.jpe?g|\.webp|\.gif|\.avif/i.test(input.accept||'');
      return all.find(input=>composerRoot?.contains(input)&&isImageInput(input))||
        all.find(input=>composerRoot?.contains(input))||
        all.find(isImageInput)||null;
    };
    let input=findInput();
    if(!input){
      const roots=[composerRoot,composer.closest('form'),composer.parentElement].filter(Boolean);
      const uploadButton=roots.flatMap(root=>[...root.querySelectorAll('button,[role="button"],label')]).filter(visible).find(el=>/attach|upload|image|photo|file|đính kèm|tải lên/i.test(`${el.getAttribute('aria-label')||''} ${el.getAttribute('title')||''} ${el.innerText||''}`));
      if(uploadButton){uploadButton.click();await delay(250,signal);input=findInput();}
    }
    if(!input)throw new Error("聊天输入框附近未找到 Muse 图片上传控件，未提交提示词。");
    const previewSelector='img,[role="img"],[data-testid*="attachment" i],[data-testid*="upload" i],[class*="attachment" i],[class*="upload" i]';
    const previewElements=()=>[...document.querySelectorAll(previewSelector)].filter(visible);
    const previewKey=el=>{
      const src=el.matches('img')?(el.currentSrc||el.src||''):/url\(["']?(blob:|data:image\/|https?:)[^)]*\)/i.exec(getComputedStyle(el).backgroundImage)?.[0]||'';
      return `${src}|${el.getAttribute('data-testid')||''}|${el.getAttribute('class')||''}|${el.getAttribute('aria-label')||''}|${el.getAttribute('title')||''}`;
    };
    const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'files')?.set;
    if(!setter)throw new Error("浏览器不允许设置 Muse 附件输入框。");
    const uploadBatch=async(batch)=>{
      const previousPreviews=new Set(previewElements().map(previewKey));
      const transfer=new DataTransfer();batch.forEach(file=>transfer.items.add(file));
      if(batch.length>1)input.multiple=true;
      setter.call(input,transfer.files);
      input.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
      input.dispatchEvent(new Event('change',{bubbles:true,composed:true}));
      const started=Date.now(),deadline=started+8000;
      const accepted=()=>batch.every(file=>[...(input.files||[])].some(item=>item.name===file.name&&item.size===file.size&&item.type===file.type));
      const previewSeen=()=>previewElements().some(el=>{
        const key=previewKey(el),src=el.matches('img')?(el.currentSrc||el.src||''):key.split('|',1)[0];
        return !previousPreviews.has(key)&&Boolean(src);
      });
      while(Date.now()<deadline){if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');if(previewSeen()||accepted()&&Date.now()-started>1000)return;await delay(160,signal);}
      throw new Error(`Muse 未确认 ${batch.length} 张参考图片已在聊天输入框中上传（上传控件接受：${input.accept||"任意文件"}）；未提交提示词。`);
    };
    if(files.length>1&&!input.multiple){
      for(const file of files)await uploadBatch([file]);
    }else await uploadBatch(files);
  }

  function blobToDataUrl(blob){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(reader.error||new Error("媒体转换失败。"));reader.readAsDataURL(blob);});}
})();
