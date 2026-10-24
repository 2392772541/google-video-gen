(() => {
  if (window.__museFlowBridgeInstalled) return;
  window.__museFlowBridgeInstalled = true;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === 'MUSEFLOW_CHECK_SESSION') {
      checkSession().then(sendResponse);
      return true;
    }
    if (message?.type === 'MUSEFLOW_GENERATE') {
      const controller=new AbortController();activeGenerations.set(message.requestId,controller);
      generate(message,controller.signal).then(sendResponse, error => sendResponse({ ok: false, code:error.code||'MUSE_ERROR', error: error.message || String(error) })).finally(()=>activeGenerations.delete(message.requestId));
      return true;
    }
    if(message?.type==='MUSEFLOW_STOP_GENERATION'){
      const stopped=message.requestId?abortGeneration(message.requestId):[...activeGenerations.keys()].some(id=>abortGeneration(id));
      sendResponse({ok:true,stopped});return false;
    }
  });

  function findComposer() {
    const candidates=[...document.querySelectorAll('textarea')].filter(el=>visible(el)&&!el.disabled);
    return candidates.find(el=>/message|消息/i.test(el.getAttribute('placeholder')||''))||candidates[0]||null;
  }

  function visible(el) { return Boolean(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'); }
  const delay = (ms,signal) => new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(new DOMException("用户已停止生成。",'AbortError'));return;}
    const timer=setTimeout(()=>{signal?.removeEventListener('abort',cancel);resolve();},ms);
    const cancel=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);reject(new DOMException("用户已停止生成。",'AbortError'));};
    signal?.addEventListener('abort',cancel,{once:true});
  });
  const attachmentSelector='[data-testid^="hatch-chat-attachment-presentation-"]';
  const activeGenerations=new Map();

  function clickMuseStop(){
    const button=[...document.querySelectorAll('[data-testid="hatch-composer-stop-button"],button[aria-label*="Stop" i],button[aria-label*="停止"]')].find(visible);
    if(button){button.click();return true;}return false;
  }

  function abortGeneration(requestId){
    const controller=activeGenerations.get(requestId);
    if(!controller)return false;
    controller.abort();clickMuseStop();return true;
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
    return [...document.querySelectorAll(attachmentSelector)].filter(el=>!el.closest('form,[class*="chat-user-bubble"],[class*="group/msg"]')&&!el.closest('[data-testid="hatch-composer-placeholder-overlay"]')).map(el=>{
      const tid=el.getAttribute('data-testid')||'',video=el.querySelector('video'),image=el.querySelector('img');
      const urls=[...el.querySelectorAll('a[href],video source[src],source[src],[data-video-src],[data-download-url]')].map(item=>({url:item.href||item.src||item.getAttribute('data-video-src')||item.getAttribute('data-download-url')||'',download:item.getAttribute('download')||'',type:item.getAttribute('type')||''})).filter(item=>item.url);
      const videoLink=urls.find(item=>/video\//i.test(item.type)||/\.(?:mp4|webm|mov|m4v)(?:$|[?#])/i.test(item.url)||/\.(?:mp4|webm|mov|m4v)$/i.test(item.download))?.url||'';
      const videoUrl=video?.currentSrc||video?.src||videoLink||'';
      const media=video||image;
      return {el,tid,src:videoUrl||media?.currentSrc||media?.src||'',videoUrl,isVideo:Boolean(videoUrl)||video instanceof HTMLVideoElement||/video/i.test(tid),width:video?.videoWidth||image?.naturalWidth||0,height:video?.videoHeight||image?.naturalHeight||0};
    }).filter(a=>a.src);
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
    return explicit.test(text)||inability.test(text)&&(sceneContext.test(text)||offerAlternative.test(text));
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

  async function generate({prompt,timeoutSec=600,mediaType='image',referenceImage='',referenceImages=[],size='1:1',model='muse-image',requestId},signal) {
    const throwIfAborted=()=>{if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');};
    throwIfAborted();
    if(!String(prompt||'').trim())throw new Error("提示词为空。");
    await waitHydrated(15000,signal);
    throwIfAborted();
    const composer=findComposer();
    if(!visible(composer))throw new Error("Muse 输入框不可见。请打开聊天输入框后重试。");
    const referenceList=Array.isArray(referenceImages)&&referenceImages.length?referenceImages:referenceImage?[referenceImage]:[];
    if(referenceList.length)await attachReferences(referenceList,signal);
    throwIfAborted();
    const baseline=new Set(attachments().map(a=>a.src));
    const priorBubbleTexts=new Map(assistantMessageElements().map(el=>[el,(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim()]));
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
    const deadline=Date.now()+Math.min(900,Math.max(30,Number(timeoutSec)||600))*1000;
    const submitTime=Date.now();
    let lastProgress=Date.now(),firstWrongRatioAt=0;
    let refusalContext='',refusalContextSince=0;
    let generationEverActive=false,stopDisappearedAt=0;
    while(Date.now()<deadline){
      throwIfAborted();
      const fresh=attachments().filter(a=>!baseline.has(a.src));
      const matching=fresh.filter(a=>mediaType==='video'?a.isVideo:!a.isVideo);
      const [ratioW,ratioH]=String(size||'1:1').split(':').map(Number),expectedRatio=ratioW>0&&ratioH>0?ratioW/ratioH:1;
      const measured=matching.filter(a=>a.width>0&&a.height>0).sort((a,b)=>{
        const scoreA=Math.abs(Math.log((a.width/a.height)/expectedRatio)),scoreB=Math.abs(Math.log((b.width/b.height)/expectedRatio));
        if(Math.abs(scoreA-scoreB)>.015)return scoreA-scoreB;
        return a.el.compareDocumentPosition(b.el)&Node.DOCUMENT_POSITION_FOLLOWING?1:-1;
      });
      const best=measured[0],bestRatioError=best?Math.abs(Math.log((best.width/best.height)/expectedRatio)):Infinity;
      if(best&&bestRatioError<=.09)firstWrongRatioAt=0;
      else if(best&&!firstWrongRatioAt)firstWrongRatioAt=Date.now();
      const result=best&&(bestRatioError<=.09||Date.now()-firstWrongRatioAt>=3500)?best:null;
      if(result){
        const media=mediaType==='video'?(result.el.querySelector('video')||null):(result.el.querySelector('img')||null);
        const src=mediaType==='video'?(result.videoUrl||media?.currentSrc||media?.src||''):(media?.currentSrc||media?.src||'');
        // Muse may first render a poster and attach the playable/download URL after
        // hydration. Keep waiting for that URL instead of rejecting a completed clip.
        if(!src){firstWrongRatioAt=firstWrongRatioAt||Date.now();await waitForAttachmentChange(Math.min(500,deadline-Date.now()),signal);continue;}
        if(mediaType==='video'&&!src.startsWith('blob:')&&!src.startsWith('data:'))return {ok:true,url:src};
        if(src.startsWith('data:'))return {ok:true,url:src};
        try{
          const response=await fetch(src,{credentials:'include'});
          if(!response.ok)throw new Error(`${mediaType==='video'?'视频':'图片'}下载返回 HTTP ${response.status}.`);
          const blob=await response.blob();
          return {ok:true,url:await blobToDataUrl(blob)};
        }catch(error){return {ok:true,url:src,error:`新${mediaType==='video'?'视频':'图片'}已检测到，但无法复制到本地：${error.message}`};}
      }
      const stop=Boolean(document.querySelector('[data-testid="hatch-composer-stop-button"],button[aria-label*="Stop" i],button[aria-label*="停止"]'));
      if(stop){
        generationEverActive=true;
        stopDisappearedAt=0;
        lastProgress=Date.now();
      }else if(generationEverActive&&!stopDisappearedAt){
        stopDisappearedAt=Date.now();
      }
      const currentContext=readNewAssistantContext(priorBubbleTexts),refusal=isRefusalContext(currentContext);
      if(refusal){
        if(currentContext!==refusalContext){refusalContext=currentContext;refusalContextSince=Date.now();}
        const clearRefusal=inability.test(currentContext)&&sceneContext.test(currentContext)&&offerAlternative.test(currentContext);
        if(clearRefusal||Date.now()-refusalContextSince>=1200){
          if(stop)clickMuseStop();
          const error=new Error(`Muse 无法生成此场景：${currentContext.slice(-700)}`);error.code='SCENE_REFUSED';throw error;
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
      const stoppedAfterActive=generationEverActive&&stopDisappearedAt&&Date.now()-stopDisappearedAt>=2500&&composerReady;
      const idleWithoutActivity=!generationEverActive&&elapsedSinceSubmit>=12000&&!stop&&composerReady;
      if(stoppedAfterActive||idleWithoutActivity){
        const tail=(document.body?.innerText||'').slice(-800);
        if(/out of credits|insufficient credits|额度不足|积分不足/i.test(tail))throw new Error("Muse 账号的生成额度不足。");
        const lastMsg=currentContext.trim()||tail.slice(-300).trim();
        const failReason=lastMsg?`（页面反馈：${lastMsg}）`:'（Muse 已停止响应且未生成新的媒体附件，可能生成出错或服务异常）';
        const error=new Error(`Muse ${mediaType==='video'?'视频':'图片'}生成失败${failReason}。`);
        error.code='GENERATION_FAILED';
        throw error;
      }

      if(!stop&&Date.now()-lastProgress>5000){
        const tail=(document.body?.innerText||'').slice(-800);
        if(/out of credits|insufficient credits|额度不足|积分不足/i.test(tail))throw new Error("Muse 账号的图片生成额度不足。");
      }
      await waitForAttachmentChange(Math.min(500,deadline-Date.now()),signal);
    }
    throwIfAborted();
    throw new Error(`等待 Muse 返回新的${mediaType==='video'?'视频':'图片'}附件超时。提示词仅提交了一次，没有重复提交。`);
  }

  async function attachReferences(references,signal){
    const files=await Promise.all(references.map(async(reference,index)=>{
      const url=typeof reference==='string'?reference:reference?.url;
      if(!url)throw new Error(`参考图片 ${index+1}没有 URL。`);
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
