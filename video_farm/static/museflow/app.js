(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const escapeHtml = (str) => String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const canvas = $('#canvas');
  const edgesSvg = $('#edges');
  const runStatus = $('#runStatus');
  const backendStatus = $('#backendStatus');
  const museStatus = $('#museStatus');

  const state = {
    nodes: [],
    edges: [],
    selectedNodeId: null,
    selectedNodeIds: [],
    selectedEdgeIds: [],
    selectionMarquee: null,
    connectingFrom: null,
    settings: {},
    isRunning: false,
    activeGenerationId: null,
    generationAbortController: null,
    generationRequestId: null,
    timelinePreviewToken: 0,
    timelinePreviewTimer: 0,
    timelineExporting: false,
    timelineExportUrl: '',
    edgeFrame: 0,
    draggingWire: null,
    wireMoved: false,
    wireOrigin: null,
    pendingConnection: null,
    pointerId: null,
    zoom: 1,
    panX: 0,
    panY: 0,
    handMode: false,
    spaceDown: false,
    panning: null,
    suppressPortClick: false,
    contextPoint: {x:120,y:100}
  };

  const nodeDefs = {
    prompt: { title: "提示词", outputs: [{ id: 'text', label: "文本", type: 'text' }] },
    negativePrompt: { title: "反向提示词", outputs: [{ id: 'text', label: "反向提示词", type: 'negative' }] },
    textAppend: { title: "追加文本", inputs: [{ id: 'text', label: "文本", type: 'text' }], outputs: [{ id: 'text', label: "文本", type: 'text' }] },
    textConcat: { title: "合并文本", inputs: [{ id: 'a', label: "文本 A", type: 'text' }, { id: 'b', label: "文本 B", type: 'text' }], outputs: [{ id: 'text', label: "文本", type: 'text' }] },
    imageInput: { title: "输入图片", outputs: [{ id: 'image', label: "图片", type: 'image' }] },
    references: { title: "参考图片", inputs: Array.from({length:8},(_,i)=>({id:`reference${i+1}`,label:`图片 ${i+1}`,type:'image'})), outputs: [{id:'image',label:'图片集',type:'image'}] },
    generateImage: {
      title: "生成图片",
      inputs: [{ id: 'prompt', label: "提示词", type: 'text' }, { id: 'negative', label: "反向提示词", type: 'negative' }, { id: 'reference', label: "参考图片", type: 'image' }],
      outputs: [{ id: 'image', label: "图片", type: 'image' }]
    },
    generateVideo: {
      title: "生成视频",
      inputs: [{ id: 'prompt', label: "提示词", type: 'text' }, { id: 'negative', label: "反向提示词", type: 'negative' }, { id: 'reference', label: "参考图片", type: 'image' }],
      outputs: [{ id: 'video', label: "视频", type: 'video' }, { id: 'endFrame', label: "尾帧", type: 'image' }]
    },
    timeline: { title: "时间线", inputs: Array.from({length:6},(_,i)=>({id:`clip${i+1}`,label:`片段 ${i+1}`,type:'video'})), outputs: [] },
    imageResize: { title: "调整图片尺寸", inputs: [{ id: 'image', label: "图片", type: 'image' }], outputs: [{ id: 'image', label: "图片", type: 'image' }] },
    preview: { title: "预览", inputs: [{ id: 'media', label: "媒体", type: 'media' }] }
  };

  const statusLabels={idle:'待运行',running:'生成中',success:'已完成',error:'失败',stopped:'已停止',pending:'等待中',waiting:'等待中'};
  const mediaLabels={image:'图片',video:'视频',text:'文本',negative:'反向提示词',media:'媒体'};
  function statusText(value){return statusLabels[value]||value||statusLabels.idle;}
  function mediaText(value){return mediaLabels[value]||value;}

  const BUILTIN_IMAGE_MODELS = [
    { id: 'muse-image', name: 'Muse.ai (默认)' },
    { id: 'flux-1-schnell', name: 'FLUX.1 Schnell' },
    { id: 'flux-1-dev', name: 'FLUX.1 Dev' },
    { id: 'dall-e-3', name: 'DALL·E 3' },
    { id: 'sd-xl', name: 'Stable Diffusion XL' },
    { id: 'midjourney', name: 'Midjourney' }
  ];

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
      scheduleAutoSave();
    }
  }

  function removeCustomImageModel(name) {
    if (!name || !state.settings?.customImageModels) return;
    state.settings.customImageModels = state.settings.customImageModels.filter(m => m !== name);
    if (state.settings.defaultImageModel === name) {
      state.settings.defaultImageModel = 'muse-image';
    }
    scheduleAutoSave();
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
    scheduleAutoSave();
  }

  function uid(prefix='id') { return `${prefix}-${crypto.randomUUID()}`; }

  function starter() {
    return {
      nodes: [
        { id: 'prompt-1', type: 'prompt', x: 90, y: 110, data: { text: "电影质感的未来风格越南女性肖像，霓虹雨景，面部细节清晰" } },
        { id: 'gen-1', type: 'generateImage', x: 450, y: 105, data: { model: state.settings?.defaultImageModel || 'muse-image', size: '1:1', status: 'idle' } },
        { id: 'preview-1', type: 'preview', x: 820, y: 110, data: {} }
      ],
      edges: [
        { id: 'e1', source: 'prompt-1', sourcePort: 'text', target: 'gen-1', targetPort: 'prompt' },
        { id: 'e2', source: 'gen-1', sourcePort: 'image', target: 'preview-1', targetPort: 'media' }
      ]
    };
  }

  function addNode(type, x=250 + Math.random()*220, y=160 + Math.random()*180) {
    const dockTimeline=type==='timeline'&&state.nodes.find(node=>node.type==='timeline'&&node.data?.dockOnly);
    if(dockTimeline){dockTimeline.data.dockOnly=false;dockTimeline.x=x;dockTimeline.y=y;render();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();return;}
    const data = type === 'prompt' ? { text: "描述你希望 Muse 生成的内容…" } :
      type === 'negativePrompt' ? { text: "模糊、低画质、人体结构畸形、多余手指、文字、水印" } :
      type === 'textAppend' ? { text: "电影感光线，精细构图" } :
      type === 'textConcat' ? { separator: ', ' } :
      type === 'imageResize' ? { width: 1024, height: 1024, fit: 'cover' } :
      type === 'generateImage' ? { model: state.settings?.defaultImageModel || 'muse-image', size: '1:1', status: 'idle' } :
      type === 'generateVideo' ? { model: 'muse-video', size: '16:9', duration: 5, continuity: false, status: 'idle' } :
      type === 'timeline' ? { clipOrder: [], durations: {} } : {};
    const node={ id: uid(type), type, x, y, data };state.nodes.push(node);
    if(type==='references')syncReferenceFanOut(node);else if(['generateImage','generateVideo'].includes(type)){const references=state.nodes.find(item=>item.type==='references');if(references)connectReferenceNode(references,node);}
    render();if(type==='timeline'){syncTimelineDock();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();}
  }

  function nodeById(id) { return state.nodes.find(n => n.id === id); }

  function removeNode(id) {
    const outgoingTargets = state.edges.filter(e => e.source === id).map(e => e.target);
    state.nodes = state.nodes.filter(n => n.id !== id);
    state.edges = state.edges.filter(e => e.source !== id && e.target !== id);
    state.selectedNodeIds=state.selectedNodeIds.filter(nodeId=>nodeId!==id);if(state.selectedNodeId===id)state.selectedNodeId=state.selectedNodeIds.at(-1)||null;
    outgoingTargets.forEach(tid => markNodeDirty(tid));
    render();syncTimelineDock();
  }

  function selectNode(id,{toggle=false,add=false}={}){let ids=[...state.selectedNodeIds];if(toggle){ids=ids.includes(id)?ids.filter(item=>item!==id):[...ids,id];}else if(add){if(!ids.includes(id))ids.push(id);}else ids=[id];state.selectedNodeIds=ids;state.selectedNodeId=ids.at(-1)||null;document.querySelectorAll('.node').forEach(el=>el.classList.toggle('selected',ids.includes(el.dataset.id)));}
  function removeSelectedNodes(){const ids=new Set(state.selectedNodeIds);if(!ids.size&&state.selectedNodeId)ids.add(state.selectedNodeId);if(!ids.size)return;state.nodes=state.nodes.filter(node=>!ids.has(node.id));state.edges=state.edges.filter(edge=>!ids.has(edge.source)&&!ids.has(edge.target));state.selectedNodeIds=[];state.selectedNodeId=null;render();saveState();}

  function portCompatible(from, targetNodeId, targetPortId) {
    const sourceNode = nodeById(from.nodeId), targetNode = nodeById(targetNodeId);
    if (!sourceNode || !targetNode || sourceNode.id === targetNode.id) return false;
    const out = (nodeDefs[sourceNode.type].outputs || []).find(p => p.id === from.portId);
    const input = (nodeDefs[targetNode.type].inputs || []).find(p => p.id === targetPortId);
    return Boolean(out && input && canConnectTypes(out.type,input.type));
  }

  function connectionChoices(from){
    const source=nodeById(from.nodeId),output=nodeDefs[source?.type]?.outputs?.find(port=>port.id===from.portId);if(!source||!output)return{existing:[],create:[]};
    const existing=[];for(const target of state.nodes){if(target.id===source.id)continue;for(const input of nodeDefs[target.type]?.inputs||[]){if(!portCompatible(from,target.id,input.id))continue;if(target.type==='timeline'&&getIncoming(target.id,input.id).length)continue;if(wouldCreateCycle(source.id,target.id,isMultiInput(target.type,input.id)?null:input.id))continue;existing.push({kind:'existing',targetId:target.id,targetPort:input.id,label:`${nodeDefs[target.type].title} · ${input.label}${target.data?.dockOnly?"（底部时间线）":''}`});}}
    const candidates=output.type==='image'?[['references','reference1',"参考图片 · 图片 1"],['preview','media',"预览 · 图片"],['imageResize','image',"调整图片尺寸"],['generateImage','reference',"生成图片 · 参考图片"],['generateVideo','reference',"生成视频 · 参考图片"]]:output.type==='video'?[['preview','media',"预览 · 视频"],['timeline','clip1',"时间线 · 添加片段"]]:output.type==='text'?[['generateImage','prompt',"生成图片 · 提示词"],['generateVideo','prompt',"生成视频 · 提示词"],['textAppend','text',"追加文本"],['textConcat','a',"合并文本 · 文本 A"],['textConcat','b',"合并文本 · 文本 B"]]:output.type==='negative'?[['generateImage','negative',"生成图片 · 反向提示词"],['generateVideo','negative',"生成视频 · 反向提示词"]]:[];
    const create=candidates.map(([type,port,label])=>({kind:'create',type,targetPort:port,label}));return{existing,create};
  }

  function openConnectionPicker(from,x,y){
    const output=nodeDefs[nodeById(from.nodeId)?.type]?.outputs?.find(port=>port.id===from.portId),choices=connectionChoices(from),menu=$('#canvasMenu'),viewport=$('#viewport').getBoundingClientRect();
    if(!output)return;state.pendingConnection={from:{...from},x:(x-viewport.left-state.panX)/state.zoom,y:(y-viewport.top-state.panY)/state.zoom,choices:[...choices.existing,...choices.create]};menu.innerHTML='';delete menu.dataset.nodeId;delete menu.dataset.edgeId;
    const title=document.createElement('div');title.className='menu-caption';title.textContent=`发送 ${output.label} · ${mediaText(output.type)}`;menu.appendChild(title);
    const addSection=label=>{const section=document.createElement('div');section.className='menu-caption';section.textContent=label;menu.appendChild(section);};
    const addChoice=(choice,index)=>{const button=document.createElement('button');button.type='button';button.textContent=choice.label;button.dataset.contextAction='connect-choice';button.dataset.choice=String(index);menu.appendChild(button);};
    if(choices.existing.length){addSection("连接已有节点");choices.existing.forEach((choice,index)=>addChoice(choice,index));}
    if(choices.create.length){addSection("创建兼容节点");choices.create.forEach((choice,index)=>addChoice(choice,choices.existing.length+index));}
    if(!state.pendingConnection.choices.length){const empty=document.createElement('div');empty.className='menu-caption';empty.textContent="此输出没有可兼容的节点操作。";menu.appendChild(empty);}
    menu.classList.remove('hidden');menu.style.left=`${Math.max(8,Math.min(x,innerWidth-260))}px`;menu.style.top=`${Math.max(8,Math.min(y,innerHeight-420))}px`;
  }

  function runConnectionChoice(index){
    const pending=state.pendingConnection,choice=pending?.choices?.[index];state.pendingConnection=null;closeCanvasMenu();
    if(!pending||!choice)return;
    if(choice.kind==='existing'){
      state.connectingFrom=pending.from;connect(choice.targetId,choice.targetPort);selectNode(choice.targetId,{add:true});setRunStatus(`已连接到 ${choice.label}.`,'ok');return;
    }
    const before=new Set(state.nodes.map(node=>node.id));addNode(choice.type,pending.x-135,pending.y-80);
    const target=state.nodes.find(node=>!before.has(node.id))||state.nodes.find(node=>node.type===choice.type&&node.data?.dockOnly===false&&choice.type==='timeline');if(!target||target.type!==choice.type){setRunStatus("无法创建所选节点。",'error');return;}
    state.connectingFrom=pending.from;connect(target.id,choice.targetPort);selectNode(target.id);setRunStatus(`${nodeDefs[target.type].title}已创建，并连接到 ${choice.label.split(' · ').at(-1)}.`,'ok');
  }

  function connect(targetNodeId, targetPortId) {
    const from = state.connectingFrom;
    if (!from) return;
    if (!portCompatible(from, targetNodeId, targetPortId)) {
      setRunStatus("端口类型不兼容。", 'error');
      state.connectingFrom = null;
      return;
    }
    const target=nodeById(targetNodeId),source=nodeById(from.nodeId),multi=isMultiInput(target?.type,targetPortId);
    if(wouldCreateCycle(from.nodeId,targetNodeId,multi?null:targetPortId)){setRunStatus("此连接会使工作流形成循环。请按单一方向连接节点。", 'error');state.connectingFrom=null;return;}
    const duplicate=state.edges.some(edge=>edge.source===from.nodeId&&edge.sourcePort===from.portId&&edge.target===targetNodeId&&edge.targetPort===targetPortId);
    if(!multi)state.edges=state.edges.filter(edge=>!(edge.target===targetNodeId&&edge.targetPort===targetPortId));
    if(!duplicate){
      state.edges.push({id:uid('edge'),source:from.nodeId,sourcePort:from.portId,target:targetNodeId,targetPort:targetPortId});
      markNodeDirty(targetNodeId);
    }
    if(target?.type==='timeline'&&targetPortId.startsWith('clip')&&source?.type==='generateVideo'){
      target.data.clipOrder=target.data.clipOrder||[];if(!target.data.clipOrder.includes(source.id))target.data.clipOrder.push(source.id);
    }
    state.connectingFrom=null;
    render();
  }

  function wouldCreateCycle(sourceId,targetId,replacedPort){const pending=[targetId],seen=new Set();while(pending.length){const id=pending.pop();if(id===sourceId)return true;if(seen.has(id))continue;seen.add(id);for(const edge of state.edges){if(edge.source===id&&!(edge.target===targetId&&edge.targetPort===replacedPort))pending.push(edge.target);}}return false;}

  function nearestCompatibleInput(x,y,from){
    let best=null,bestDistance=44;
    for(const port of document.querySelectorAll('.port.in')){
      if(!portCompatible(from,port.dataset.node,port.dataset.port))continue;
      const rect=port.getBoundingClientRect(),distance=Math.hypot(x-(rect.left+rect.width/2),y-(rect.top+rect.height/2));
      if(distance<bestDistance){best=port;bestDistance=distance;}
    }
    return best;
  }
  function canConnectTypes(outputType,inputType){return outputType===inputType||inputType==='media'&&['image','video'].includes(outputType);}
  function isMultiInput(nodeType,portId){return ['generateImage','generateVideo'].includes(nodeType)&&['prompt','reference'].includes(portId)||nodeType==='references'&&portId.startsWith('reference');}
  function connectReferenceNode(references,generator){if(!references||!generator||!['generateImage','generateVideo'].includes(generator.type))return;const duplicate=state.edges.some(edge=>edge.source===references.id&&edge.sourcePort==='image'&&edge.target===generator.id&&edge.targetPort==='reference');if(!duplicate)state.edges.push({id:uid('edge'),source:references.id,sourcePort:'image',target:generator.id,targetPort:'reference'});}
  function syncReferenceFanOut(references){for(const generator of state.nodes.filter(node=>['generateImage','generateVideo'].includes(node.type)))connectReferenceNode(references,generator);}

  function makeNode(type,x,y){
    const data=type==='prompt'?{text:"描述你希望 Muse 生成的内容…"}:type==='negativePrompt'?{text:"模糊、低画质、人体结构畸形、多余手指、文字、水印"}:type==='imageInput'?{}:type==='generateImage'?{model:state.settings?.defaultImageModel||'muse-image',size:'1:1',status:'idle'}:type==='generateVideo'?{model:'muse-video',size:'16:9',duration:5,continuity:false,status:'idle'}:{};
    return{id:uid(type),type,x,y,data};
  }

  function scriptField(section,label,nextLabels){
    const startPattern=new RegExp(`^[\\t ]*(?:${label})[\\t ]*[:：][\\t ]*`,'im'),match=startPattern.exec(section);if(!match)return'';
    const start=match.index+match[0].length,tail=section.slice(start),stop=nextLabels.length?new RegExp(`^[\\t ]*(?:${nextLabels.join('|')})[\\t ]*[:：]`,'im').exec(tail):null;
    return tail.slice(0,stop?stop.index:tail.length).trim();
  }
  function parseSceneScript(text){
    const heading=/^[\t ]*(?:CẢNH|场景|分镜|Scene)[\t ]*(\d+)[\t ]*[(（]([^\r\n)）]*)[)）][\t ]*[:：][\t ]*(.*?)\r?$/gim,matches=[...text.matchAll(heading)];
    const imageLabel='Prompt\\s+ảnh|图片提示词|图像提示词|图片提示|Image\\s+prompt',videoLabel='Prompt\\s+video|视频提示词|视频提示|Video\\s+prompt',audioLabel='Audio|音频|音效|声音';
    return matches.map((match,index)=>{
      const body=text.slice(match.index+match[0].length,matches[index+1]?.index??text.length),imagePrompt=scriptField(body,imageLabel,[videoLabel,audioLabel]),videoPrompt=scriptField(body,videoLabel,[audioLabel]),audio=scriptField(body,audioLabel,[]),range=match[2].match(/(\d+)[:：](\d{2})\s*[–—\-~～至]\s*(\d+)[:：](\d{2})/);
      const seconds=range?(Number(range[3])*60+Number(range[4]))-(Number(range[1])*60+Number(range[2])):0;
      const ratio=(imagePrompt+' '+videoPrompt).match(/\b(9:16|16:9|1:1|4:3|3:4)\b/);
      return{number:Number(match[1]),title:match[3].trim(),imagePrompt,videoPrompt:[videoPrompt,audio?`Audio direction: ${audio}`:''].filter(Boolean).join('\n\n'),seconds:seconds>0?seconds:6,size:ratio?.[1]||'9:16'};
    }).filter(scene=>scene.imagePrompt||scene.videoPrompt);
  }
  function buildSceneNodesFromScript(){
    const status=$('#scriptImportStatus'),scenes=parseSceneScript($('#scriptInput').value);
    if(!scenes.length){status.className='error';status.textContent="未识别到场景。请使用“场景 1（0:00–0:07）：标题”，并填写“图片提示词”或“视频提示词”；也兼容原版 CẢNH 格式。";return;}
    const clearCanvas = $('#scriptClearCanvas')?.checked ?? true;
    if (clearCanvas) {
      state.nodes = state.nodes.filter(n => n.data?.dockOnly);
      state.edges = [];
    }
    if (window.__shotManager) {
      window.__shotManager.initFromParsedScenes(scenes, clearCanvas);
    }
    const baseY=Math.max(40,...state.nodes.filter(node=>!node.data?.dockOnly).map(node=>node.y+360)),createdVideos=[];let made=0;
    scenes.forEach((scene,index)=>{
      const column=index%4,row=Math.floor(index/4),x=80+column*650,y=baseY+row*1100,label=`场景 ${scene.number}${scene.title?`: ${scene.title}`:''}`;
      let imageNode=null,videoNode=null;
      if(scene.imagePrompt){const prompt=makeNode('prompt',x,y);prompt.data={text:scene.imagePrompt,sceneLabel:label};const image=makeNode('generateImage',x+330,y);image.data={model:state.settings?.defaultImageModel||'muse-image',size:scene.size,status:'idle',sceneLabel:label};state.nodes.push(prompt,image);state.edges.push({id:uid('edge'),source:prompt.id,sourcePort:'text',target:image.id,targetPort:'prompt'});imageNode=image;made+=2;}
      if(scene.videoPrompt){const prompt=makeNode('prompt',x,y+540);prompt.data={text:scene.videoPrompt,sceneLabel:label};const requestedDuration=[5,6,8,10].reduce((best,value)=>Math.abs(value-scene.seconds)<Math.abs(best-scene.seconds)?value:best,5);videoNode=makeNode('generateVideo',x+330,y+540);videoNode.data={model:'muse-video',size:scene.size,duration:requestedDuration,continuity:createdVideos.length>0,status:'idle',sceneLabel:label};state.nodes.push(prompt,videoNode);state.edges.push({id:uid('edge'),source:prompt.id,sourcePort:'text',target:videoNode.id,targetPort:'prompt'});if(imageNode)state.edges.push({id:uid('edge'),source:imageNode.id,sourcePort:'image',target:videoNode.id,targetPort:'reference'});made+=2;createdVideos.push({node:videoNode,seconds:scene.seconds});}
    });
    let references=state.nodes.find(node=>node.type==='references');if(!references){const minX=Math.min(80,...state.nodes.filter(node=>!node.data?.dockOnly).map(node=>node.x));references=makeNode('references',minX-360,baseY);references.data={};state.nodes.push(references);made++;}syncReferenceFanOut(references);
    const timeline=ensureDockTimeline();timeline.data.clipOrder=createdVideos.map(item=>item.node.id);timeline.data.durations=timeline.data.durations||{};createdVideos.forEach(({node,seconds})=>{timeline.data.durations[node.id]=seconds;});
    $('#scriptModal').classList.add('hidden');render();saveState();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();
    setRunStatus(`已创建 ${scenes.length} 个场景 · ${made} 个节点 · ${createdVideos.length} 个视频片段已按顺序加入时间线。`,'ok');
  }

  function screenToCanvas(x,y){const rect=$('#viewport').getBoundingClientRect();return{x:x-rect.left,y:y-rect.top};}

  function startWire(e,nodeId,portId){
    if(e.button!==undefined&&e.button!==0)return;
    e.preventDefault();e.stopPropagation();
    state.draggingWire={nodeId,portId};state.connectingFrom={nodeId,portId};state.wireMoved=false;
    const sourceForCapture=nodeById(nodeId);
    if(!(sourceForCapture?.type==='generateVideo'&&portId==='video'))try{e.currentTarget.setPointerCapture(e.pointerId);}catch{}
    state.wirePointer={x:e.clientX,y:e.clientY};state.wireOrigin={x:e.clientX,y:e.clientY};
    document.querySelectorAll('.port.in').forEach(port=>{if(portCompatible({nodeId,portId},port.dataset.node,port.dataset.port))port.classList.add('wire-compatible');});
  }

  function startWireFromInput(e,nodeId,portId,portType){
    if(e.button!==undefined&&e.button!==0)return;e.preventDefault();e.stopPropagation();state.draggingWire={nodeId,portId,direction:'in',portType};state.wireMoved=false;state.wirePointer={x:e.clientX,y:e.clientY};state.wireOrigin={x:e.clientX,y:e.clientY};
    try{e.currentTarget.setPointerCapture(e.pointerId);}catch{}
    document.querySelectorAll('.port.out').forEach(port=>{if(portCompatible({nodeId:port.dataset.node,portId:port.dataset.port},nodeId,portId))port.classList.add('wire-compatible');});
  }

  function onWireMove(e){
    if(!state.draggingWire)return;
    if(state.wireOrigin&&Math.hypot(e.clientX-state.wireOrigin.x,e.clientY-state.wireOrigin.y)>5)state.wireMoved=true;
      const source=nodeById(state.draggingWire.nodeId),dock=$('#timelineDock'),overDock=source?.type==='generateVideo'&&state.draggingWire.portId==='video'&&(()=>{const r=dock.getBoundingClientRect();return e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;})();
    dock.classList.toggle('wire-drop-target',Boolean(overDock));
    if(overDock&&dock.classList.contains('collapsed'))toggleTimeline();
    state.wirePointer={x:e.clientX,y:e.clientY};scheduleDrawEdges();
  }

  function onWireUp(e){
    if(!state.draggingWire)return;
    const from=state.draggingWire,moved=state.wireMoved,source=nodeById(from.nodeId),dock=$('#timelineDock'),r=dock.getBoundingClientRect(),droppedOnTimeline=source?.type==='generateVideo'&&from.portId==='video'&&e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;
    state.draggingWire=null;state.wirePointer=null;state.wireOrigin=null;
    dock.classList.remove('wire-drop-target');
    document.querySelectorAll('.wire-compatible').forEach(port=>port.classList.remove('wire-compatible'));
    if(moved&&from.direction==='in'){
      const output=nearestCompatibleOutput(e.clientX,e.clientY,from);
      if(output){state.connectingFrom={nodeId:output.dataset.node,portId:output.dataset.port};connect(from.nodeId,from.portId);}
      else{const rect=$('#viewport').getBoundingClientRect(),emptyCanvas=!document.elementFromPoint(e.clientX,e.clientY)?.closest('.node'),inside=e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom,type=from.portType==='negative'?'negativePrompt':'prompt';if(inside&&emptyCanvas){addNode(type,(e.clientX-rect.left-state.panX)/state.zoom-135,(e.clientY-rect.top-state.panY)/state.zoom-80);const created=state.nodes.at(-1);state.connectingFrom={nodeId:created.id,portId:'text'};connect(from.nodeId,from.portId);setRunStatus(`${nodeDefs[type].title}已创建并连接。`,'ok');}else setRunStatus("拖到输出端口，或拖到画布空白处创建提示词节点。",'warn');}
      state.suppressPortClick=true;setTimeout(()=>state.suppressPortClick=false,80);scheduleDrawEdges();return;
    }
    if(moved){
      if(droppedOnTimeline){addTimelineClip(ensureDockTimeline(),source.id);state.connectingFrom=null;state.suppressPortClick=true;setTimeout(()=>state.suppressPortClick=false,80);scheduleDrawEdges();return;}
      const hit=nearestCompatibleInput(e.clientX,e.clientY,from);
      if(hit){state.connectingFrom=from;connect(hit.dataset.node,hit.dataset.port);}
      else {const rect=$('#viewport').getBoundingClientRect(),inside=e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom;if(inside)openConnectionPicker(from,e.clientX,e.clientY);else{state.connectingFrom=null;setRunStatus("将输出拖到画布上，选择兼容节点。",'warn');}}
      state.suppressPortClick=true;setTimeout(()=>state.suppressPortClick=false,80);
    }
    scheduleDrawEdges();
  }

  function nearestInputPort(x,y){
    const direct=document.elementsFromPoint(x,y).map(el=>el.closest?.('.port.in')).filter(Boolean);
    const candidates=[...new Set([...direct,...document.querySelectorAll('.port.in.wire-compatible')])];
    let best=null,distance=Infinity;
    for(const port of candidates){if(!port.classList.contains('wire-compatible'))continue;const r=port.getBoundingClientRect(),d=Math.hypot(x-(r.left+r.width/2),y-(r.top+r.height/2));if(d<distance){best=port;distance=d;}}
    return best&&distance<=38?best:null;
  }
  function nearestCompatibleOutput(x,y,target){let best=null,distance=44;for(const port of document.querySelectorAll('.port.out')){if(!portCompatible({nodeId:port.dataset.node,portId:port.dataset.port},target.nodeId,target.portId))continue;const rect=port.getBoundingClientRect(),d=Math.hypot(x-(rect.left+rect.width/2),y-(rect.top+rect.height/2));if(d<distance){best=port;distance=d;}}return best;}
  function normalizeSavedGraph(){
    const knownNodes=new Set(Object.keys(nodeDefs));
    const seenNodeIds=new Set();
    state.nodes=state.nodes.filter(node=>{if(!node||!knownNodes.has(node.type)||typeof node.id!=='string'||seenNodeIds.has(node.id))return false;seenNodeIds.add(node.id);return true;});
    for(const node of state.nodes)if(!node.data||typeof node.data!=='object'||Array.isArray(node.data))node.data={};
    for(const node of state.nodes)if(node.type==='timeline'){
      node.data.clipOrder=Array.isArray(node.data.clipOrder)?[...new Set(node.data.clipOrder.filter(id=>state.nodes.some(item=>item.id===id&&item.type==='generateVideo')))]:[];
      if(!node.data.durations||typeof node.data.durations!=='object'||Array.isArray(node.data.durations))node.data.durations={};
    }
    const normalized=[];
    for(const raw of state.edges){
      if(!raw||typeof raw.source!=='string'||typeof raw.target!=='string')continue;
      const source=nodeById(raw.source),target=nodeById(raw.target);
      if(!source||!target||source.id===target.id)continue;
      const outputs=nodeDefs[source.type].outputs||[],inputs=nodeDefs[target.type].inputs||[];
      // Only infer port names for old single-port edges; never guess between semantic ports.
      const sourcePort=raw.sourcePort|| (outputs.length===1?outputs[0].id:null);
      const sourceDef=outputs.find(port=>port.id===sourcePort);
      const compatibleInputs=inputs.filter(port=>sourceDef&&canConnectTypes(sourceDef.type,port.type));
      const targetPort=raw.targetPort|| (compatibleInputs.length===1?compatibleInputs[0].id:null);
      const inputDef=inputs.find(port=>port.id===targetPort);
      if(!sourceDef||!inputDef||!canConnectTypes(sourceDef.type,inputDef.type))continue;
      normalized.push({...raw,id:raw.id||uid('edge'),sourcePort,targetPort});
    }
    // Normal inputs are single-source; prompt and reference inputs retain distinct sources.
    const occupied=new Set(),unique=[];
    for(let index=normalized.length-1;index>=0;index--){const edge=normalized[index],key=isMultiInput(nodeById(edge.target)?.type,edge.targetPort)?`${edge.target}:${edge.targetPort}:${edge.source}:${edge.sourcePort}`:`${edge.target}:${edge.targetPort}`;if(occupied.has(key))continue;occupied.add(key);unique.push(edge);}
    state.edges=unique.reverse();
  }
  function renderNode(n) {
    const el = document.createElement('section');
    el.className = `node ${['generateImage','generateVideo'].includes(n.type) ? 'generate' : ''} ${n.type==='timeline'?'timeline-node':''} ${state.selectedNodeIds.includes(n.id)||state.selectedNodeId===n.id ? 'selected' : ''}`;
    el.dataset.id = n.id;
    el.dataset.type = n.type;
    el.style.left = `${n.x}px`;
    el.style.top = `${n.y}px`;
    const head = document.createElement('div');
    head.className = 'node-header';
    const title=document.createElement('span');title.textContent=`${nodeDefs[n.type].title}${n.data.sceneLabel?` · ${n.data.sceneLabel}`:''}`;title.title=title.textContent;const close=document.createElement('span');close.className='node-close';close.title="删除";close.textContent='×';head.append(title,close);
    head.querySelector('.node-close').onclick = (e) => { e.stopPropagation(); removeNode(n.id); };
    setupDrag(head, n, el);
    el.appendChild(head);

    const body = document.createElement('div');
    body.className = 'node-body';

    if (['prompt','negativePrompt','textAppend'].includes(n.type)) {
      const ta = document.createElement('textarea');
      ta.value = n.data.text || '';
      ta.oninput = () => { n.data.text = ta.value; markNodeDirty(n.id); };
      body.appendChild(ta);
      if(n.type==='negativePrompt'){const hint=document.createElement('div');hint.className='hint';hint.textContent="连接到图片或视频节点的“反向提示词”输入端口。";body.appendChild(hint);}
      if(n.type==='textAppend'){const hint=document.createElement('div');hint.className='hint';hint.textContent="将此文本追加到传入的提示词后。";body.appendChild(hint);}
    }

    if(n.type==='textConcat'){
      const separator=document.createElement('input');separator.value=n.data.separator??', ';separator.placeholder="分隔符";separator.oninput=()=>n.data.separator=separator.value;body.append("合并文本时使用以下分隔符：",separator);
      separator.oninput = () => { n.data.separator = separator.value; markNodeDirty(n.id); };
    }

    if (n.type === 'imageInput') {
      if (n.data.localDataUrl) {
        const img = document.createElement('img'); img.src = n.data.localDataUrl; body.appendChild(img);
      } else {
        const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = "尚未选择图片"; body.appendChild(empty);
      }
      const label = document.createElement('label');
      label.className = 'small-btn'; label.textContent = "选择图片";
      const input = document.createElement('input'); input.type = 'file'; input.accept = 'image/*';
      input.onchange = () => {
        const f = input.files && input.files[0]; if (!f) return;
        const r = new FileReader(); r.onload = () => { n.data.localDataUrl = String(r.result || ''); markNodeDirty(n.id); render(); }; r.readAsDataURL(f);
      };
      label.appendChild(input); body.appendChild(label);
      const hint = document.createElement('div'); hint.className = 'hint'; hint.textContent = "将此图片连接到“生成图片”的“参考图片”端口。"; body.appendChild(hint);
    }

    if(n.type==='references'){
      const incoming=(nodeDefs.references.inputs||[]).reduce((count,input)=>count+getIncoming(n.id,input.id).length,0),badge=document.createElement('span');badge.className='ref-badge';badge.textContent=`${incoming} 个图片来源 已连接`;body.appendChild(badge);
      const list=document.createElement('div');list.className='references-input-list';(nodeDefs.references.inputs||[]).forEach(input=>{const row=document.createElement('div');row.textContent=`${input.label} · 连接图片来源`;list.appendChild(row);});body.appendChild(list);
      const hint=document.createElement('div');hint.className='hint';hint.textContent="所有接入的图片都会发送给与此节点相连的“生成图片”和“生成视频”节点。";body.appendChild(hint);
    }

    if (n.type === 'generateImage') {
      const controls = document.createElement('div'); controls.className = 'gen-controls';
      const size = document.createElement('select');
      [['1:1',"正方形"],['16:9',"横向 16:9"],['9:16',"纵向 9:16"],['4:3',"横向 4:3"],['3:4',"纵向 3:4"]].forEach(([v,label]) => { const o=document.createElement('option'); o.value=v; o.textContent=label; size.appendChild(o); });
      size.value = ['1:1','16:9','9:16','4:3','3:4'].includes(n.data.size)?n.data.size:'1:1';
      size.onchange = () => { n.data.size = size.value; markNodeDirty(n.id); };

      const modelSelect = document.createElement('select');
      modelSelect.className = 'model-select';
      modelSelect.title = "选择或自定义生图模型";
      const availableModels = getAvailableImageModels();
      const currentModel = n.data.model || state.settings?.defaultImageModel || 'muse-image';
      if (!availableModels.some(m => m.id === currentModel)) {
        const customOpt = document.createElement('option');
        customOpt.value = currentModel;
        customOpt.textContent = `${currentModel} (自定义)`;
        modelSelect.appendChild(customOpt);
      }
      availableModels.forEach(m => {
        const o = document.createElement('option');
        o.value = m.id;
        o.textContent = m.name;
        modelSelect.appendChild(o);
      });
      const addOpt = document.createElement('option');
      addOpt.value = '__add_custom__';
      addOpt.textContent = '＋ 自定义模型...';
      modelSelect.appendChild(addOpt);
      modelSelect.value = currentModel;

      modelSelect.onchange = () => {
        if (modelSelect.value === '__add_custom__') {
          const customName = window.prompt("请输入你自己的生图模型名称（例如 flux-1-dev, kolors, custom-sdxl 等）：", "");
          if (customName && customName.trim()) {
            const clean = customName.trim();
            addCustomImageModel(clean);
            n.data.model = clean;
            markNodeDirty(n.id);
            render();
          } else {
            modelSelect.value = n.data.model || 'muse-image';
          }
          return;
        }
        n.data.model = modelSelect.value;
        markNodeDirty(n.id);
        scheduleAutoSave();
      };

      controls.append(size, modelSelect); body.appendChild(controls);
      const isDirtySuccess = n.data.status === 'success' && n.data.dirty;
      const st = document.createElement('div');
      st.className = `status ${isDirtySuccess ? 'dirty' : (n.data.status || 'idle')}`;
      st.textContent = isDirtySuccess ? `已就绪 · 已修改（待重新生成）${n.data.error ? ' · ' + n.data.error : ''}` : `${statusText(n.data.status)}${n.data.error ? ' · ' + n.data.error : ''}`;
      body.appendChild(st);
      if(n.data.asset?.width&&n.data.asset?.height){const dimensions=document.createElement('div');dimensions.className=`hint ${n.data.asset.sizeMismatch?'error':''}`;dimensions.textContent=`请求比例：${n.data.asset.requestedSize||n.data.size} · 实际：${n.data.asset.width} × ${n.data.asset.height}${n.data.asset.sizeMismatch?"（Muse 返回的比例不同）":''}`;body.appendChild(dimensions);}
      if (n.data.asset?.url) { const a=document.createElement('a'); a.href=n.data.asset.url; a.target='_blank'; a.className='image-link'; const img=document.createElement('img'); img.src=n.data.asset.url; a.appendChild(img); body.appendChild(a); }
      const promptCount=getIncoming(n.id,'prompt').length;if(promptCount>1){const b=document.createElement('span');b.className='ref-badge';b.textContent=`${promptCount} 个提示词来源已合并`;body.appendChild(b);}
      const referenceCount=getIncoming(n.id,'reference').length;if(referenceCount){const b=document.createElement('span');b.className='ref-badge';b.textContent=`${referenceCount} 张参考图片 已连接`;body.appendChild(b);}
      body.appendChild(createNodeRunButton(n));
    }

    if(n.type==='generateVideo'){
      const controls=document.createElement('div');controls.className='gen-controls video-controls';
      const ratio=document.createElement('select');[['16:9',"横向 16:9"],['9:16',"纵向 9:16"],['1:1',"正方形"]].forEach(([v,label])=>{const o=document.createElement('option');o.value=v;o.textContent=label;ratio.appendChild(o);});ratio.value=['16:9','9:16','1:1'].includes(n.data.size)?n.data.size:'16:9';ratio.onchange=()=>n.data.size=ratio.value;
      ratio.onchange = () => { n.data.size = ratio.value; markNodeDirty(n.id); };
      const duration=document.createElement('select');[5,6,8,10].forEach(v=>{const o=document.createElement('option');o.value=String(v);o.textContent=`${v} 秒`;duration.appendChild(o);});duration.value=String(n.data.duration||5);
      duration.onchange = () => { n.data.duration = Number(duration.value); markNodeDirty(n.id); };
      controls.append(ratio,duration);body.appendChild(controls);
      const continuityLabel=document.createElement('label');continuityLabel.className='continuity-toggle';continuityLabel.htmlFor=`continuity-${n.id}`;continuityLabel.onpointerdown=event=>event.stopPropagation();const continuity=document.createElement('input');continuity.id=`continuity-${n.id}`;continuity.type='checkbox';continuity.checked=Boolean(n.data.continuity);continuity.onchange=()=>{n.data.continuity=continuity.checked;scheduleAutoSave();};continuityLabel.append(continuity,document.createTextNode("使用上一片段的尾帧作为起始参考图"));body.appendChild(continuityLabel);
      continuity.onchange = () => { n.data.continuity = continuity.checked; markNodeDirty(n.id); scheduleAutoSave(); };
      if(n.data.endFrame?.url){const frame=document.createElement('img');frame.className='end-frame-thumb';frame.src=n.data.endFrame.url;frame.alt="已提取用于连续生成的尾帧";frame.title="视频尾帧 · 将“尾帧”连接到下一个视频的“参考图片”端口";body.appendChild(frame);}
      const isVideoDirtySuccess = n.data.status === 'success' && n.data.dirty;
      const status=document.createElement('div');status.className=`status ${isVideoDirtySuccess ? 'dirty' : (n.data.status||'idle')}`;status.textContent=isVideoDirtySuccess ? `已就绪 · 已修改（待重新生成）${n.data.error?' · '+n.data.error:''}` : `${statusText(n.data.status)}${n.data.error?' · '+n.data.error:''}`;body.appendChild(status);
      if(n.data.asset?.width&&n.data.asset?.height){const dimensions=document.createElement('div');dimensions.className=`hint ${n.data.asset.sizeMismatch?'error':''}`;dimensions.textContent=`请求比例：${n.data.asset.requestedSize||n.data.size} · 实际：${n.data.asset.width} × ${n.data.asset.height}${n.data.asset.sizeMismatch?"（Muse 返回的比例不同）":''}`;body.appendChild(dimensions);}
      if(n.data.asset?.url){const video=document.createElement('video');video.controls=true;video.preload='metadata';video.src=n.data.asset.url;body.appendChild(video);}
      const timelineDrag=document.createElement('button');timelineDrag.type='button';timelineDrag.className='video-timeline-drag';timelineDrag.draggable=true;timelineDrag.innerHTML="<span aria-hidden=\"true\">⠿</span> 将输出拖到时间线";timelineDrag.title="将此输出拖到时间线";timelineDrag.ondragstart=event=>{event.dataTransfer.setData('application/x-museflow-video-node',n.id);event.dataTransfer.setData('text/plain',n.id);event.dataTransfer.effectAllowed='copy';};timelineDrag.onclick=event=>{event.stopPropagation();addTimelineClip(ensureDockTimeline(),n.id);};body.appendChild(timelineDrag);
      body.appendChild(createNodeRunButton(n));
    }
    if(n.type==='timeline')renderTimelineBody(n,body);

    if(n.type==='imageResize'){
      const incoming=sourceFor(getIncoming(n.id,'image')[0]);
      const imageUrl=incoming?.data?.localDataUrl||incoming?.data?.asset?.url||'';
      const width=document.createElement('input');width.type='number';width.min='1';width.max='4096';width.value=n.data.width||1024;width.title="宽度";width.oninput=()=>n.data.width=clampDimension(width.value);
      const height=document.createElement('input');height.type='number';height.min='1';height.max='4096';height.value=n.data.height||1024;height.title="高度";height.oninput=()=>n.data.height=clampDimension(height.value);
      const fit=document.createElement('select');[['cover',"裁剪填满"],['contain',"完整适应"],['stretch',"拉伸"]].forEach(([v,label])=>{const o=document.createElement('option');o.value=v;o.textContent=label;fit.appendChild(o);});fit.value=n.data.fit||'cover';fit.onchange=()=>n.data.fit=fit.value;
      body.append(width,height,fit);
      const out=document.createElement('canvas');out.className='resize-preview';
      if(imageUrl){const image=new Image();image.onload=()=>drawResized(image,out,n.data);image.src=imageUrl;}
      body.appendChild(out);
      const download=document.createElement('button');download.type='button';download.className='small-btn';download.textContent="下载调整后的图片";download.disabled=!imageUrl;download.onclick=()=>{out.toBlob(blob=>{if(!blob)return;const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`museflow-${n.data.width}x${n.data.height}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);});};body.appendChild(download);
    }

    if (n.type === 'preview') {
      if (n.data.asset?.url) { if(n.data.asset.kind==='video'){const video=document.createElement('video');video.controls=true;video.src=n.data.asset.url;body.appendChild(video);}else{const a=document.createElement('a');a.href=n.data.asset.url;a.target='_blank';const img=document.createElement('img');img.src=n.data.asset.url;a.appendChild(img);body.appendChild(a);} }
      else { const empty=document.createElement('div'); empty.className='empty preview-empty'; empty.textContent="运行工作流"; body.appendChild(empty); }
    }

    el.appendChild(body);
    addPorts(el, n);
    el.onmousedown = event => {if(event.target.closest('button,input,textarea,select,.port,.node-header'))return;selectNode(n.id,{toggle:event.shiftKey||event.ctrlKey||event.metaKey});};
    return el;
  }

  function createNodeRunButton(node){
    const button=document.createElement('button');button.type='button';button.className='node-run-button primary';
    if(node.data.status==='running'){
      button.classList.add('stop');button.textContent="■ 停止";button.disabled=false;button.title="停止本次生成";button.dataset.stopGeneration=node.id;
    }else{
      button.textContent=`▶ 生成${node.type==='generateVideo'?"视频":"图片"}`;button.disabled=state.isRunning;
      button.onclick=event=>{event.stopPropagation();runSingleNode(node.id);};
    }
    return button;
  }

  function addPorts(el, n) {
    const def = nodeDefs[n.type];
    (def.inputs || []).forEach((p, i) => {
      const y = ['generateImage','generateVideo'].includes(n.type) ? 52+i*26 : n.type==='timeline'?58+i*42:68+i*42;
      const port = document.createElement('div'); port.className='port in'; port.dataset.node=n.id; port.dataset.port=p.id;port.dataset.type=p.type; port.style.top=`${y}px`; port.title=`输入：${p.label} (${p.type})`;
      if(p.type==='text'||p.type==='negative')port.onpointerdown=e=>startWireFromInput(e,n.id,p.id,p.type);
      port.ondragover=e=>{if(state.connectingFrom&&portCompatible(state.connectingFrom,n.id,p.id)){e.preventDefault();port.classList.add('wire-compatible');}};
      port.onclick = (e) => { e.stopPropagation(); if(state.suppressPortClick)return; if(state.connectingFrom)connect(n.id,p.id); else setRunStatus("先选择兼容的输出端口，再点击此输入端口。",'warn'); };
      const label=document.createElement('span'); label.className='port-label left'; label.style.top=`${y-1}px`; const count=isMultiInput(n.type,p.id)?getIncoming(n.id,p.id).length:0;label.textContent=count?`${p.label} · ${count}`:p.label;if(count)port.title=p.id==='prompt'?`提示词来源（${count} 已连接）`:`参考图片（${count} 已连接）`;el.append(label,port);
    });
    (def.outputs || []).forEach((p, i) => {
      const y = ['prompt','negativePrompt','textAppend'].includes(n.type) ? 80 : n.type==='generateVideo'?82+i*30:['imageInput','generateImage'].includes(n.type)?82:66+i*42;
      const port=document.createElement('div'); port.className='port out'; port.dataset.node=n.id; port.dataset.port=p.id;port.dataset.type=p.type; port.style.top=`${y}px`; port.title=`输出：${p.label} (${p.type})`;
      port.onpointerdown=e=>startWire(e,n.id,p.id);
      if(n.type==='generateVideo'){port.classList.add('video-output-port');port.title=p.id==='endFrame'?"将此尾帧连接到下一个视频的参考图片输入端口":"将视频输出连接到时间线或其他兼容输入端口";}
      port.onmousedown=e=>{if(e.button===0){e.stopPropagation();state.connectingFrom={nodeId:n.id,portId:p.id};setRunStatus(`正在连接 ${p.type}：请点击兼容的输入端口。`,'warn');}};
      port.onclick=(e)=>{e.stopPropagation();if(state.suppressPortClick)return;if(!state.draggingWire){state.connectingFrom={nodeId:n.id,portId:p.id};setRunStatus(`正在连接 ${p.type}：请点击兼容的输入端口，或拖动连接。`,'warn');}};
      const label=document.createElement('span'); label.className='port-label right'; label.style.top=`${y-1}px`; label.textContent=p.label; el.append(label,port);
    });
  }

  function setupDrag(handle, n, el) {
    handle.onmousedown = (e) => {
      if(state.handMode||state.spaceDown)return;
      if (e.target.classList.contains('node-close')) return;
      e.preventDefault();
      const modified=e.shiftKey||e.ctrlKey||e.metaKey,wasSelected=state.selectedNodeIds.includes(n.id);if(modified){selectNode(n.id,{toggle:true});if(wasSelected)return;}else if(!wasSelected)selectNode(n.id);
      const sx=e.clientX, sy=e.clientY,zoom=state.zoom,group=state.selectedNodeIds.includes(n.id)?state.selectedNodeIds:[n.id],origins=group.map(id=>{const node=nodeById(id);return node&&{node,x:node.x,y:node.y};}).filter(Boolean);
      const move=(ev)=>{const dx=(ev.clientX-sx)/zoom,dy=(ev.clientY-sy)/zoom;for(const origin of origins){origin.node.x=origin.x+dx;origin.node.y=origin.y+dy;const nodeEl=document.querySelector(`.node[data-id="${CSS.escape(origin.node.id)}"]`);if(nodeEl){nodeEl.style.left=`${origin.node.x}px`;nodeEl.style.top=`${origin.node.y}px`;}}scheduleDrawEdges();};
      const up=()=>{window.removeEventListener('mousemove',move);window.removeEventListener('mouseup',up);};
      window.addEventListener('mousemove',move); window.addEventListener('mouseup',up);
    };
  }

  function renderTimelineBody(node,body){
    const edges=getIncoming(node.id).filter(e=>e.targetPort.startsWith('clip'));
    const sources=new Map(edges.map(e=>[e.source,nodeById(e.source)]));
    const ordered=(node.data.clipOrder||[]).filter(id=>state.nodes.some(n=>n.id===id&&n.type==='generateVideo'));
    for(const edge of edges)if(!ordered.includes(edge.source))ordered.push(edge.source);
    for(const id of node.data.clipOrder||[])if(state.nodes.some(n=>n.id===id&&n.type==='generateVideo')&&!ordered.includes(id))ordered.push(id);
    node.data.clipOrder=ordered;syncTimelineDock();
    node._timelineEdges=edges;
    const bar=document.createElement('div');bar.className='timeline-toolbar';
    const count=document.createElement('span');count.textContent=`${ordered.length} 个片段`;
    const play=document.createElement('button');play.type='button';play.className='small-btn';play.textContent="▶ 预览序列";play.disabled=!ordered.some(id=>nodeById(id)?.data?.asset?.url);play.onclick=()=>playTimeline(node);
    bar.append(count,play);body.appendChild(bar);
    const track=document.createElement('div');track.className='timeline-track';
    if(!ordered.length){const empty=document.createElement('div');empty.className='timeline-empty';empty.textContent="将视频节点拖到这里，或连接到片段输入端口";track.appendChild(empty);}
    ordered.forEach((id,index)=>{
      const source=nodeById(id);if(!source)return;
      const clip=document.createElement('div');clip.className='timeline-clip';clip.draggable=true;clip.dataset.clip=id;
      clip.ondragstart=e=>{e.dataTransfer.setData('text/plain',id);e.dataTransfer.effectAllowed='move';};
      clip.ondragover=e=>{e.preventDefault();};
      clip.ondrop=e=>{e.preventDefault();const moving=e.dataTransfer.getData('application/x-museflow-video-node')||e.dataTransfer.getData('text/plain'),arr=[...node.data.clipOrder],from=arr.indexOf(moving),to=arr.indexOf(id);if(from>=0&&to>=0){arr.splice(from,1);arr.splice(to,0,moving);node.data.clipOrder=arr;syncTimelineDock();render();saveState();}};
      const label=document.createElement('div');label.className='timeline-clip-head';label.textContent=`${String(index+1).padStart(2,'0')} · ${source.data.asset?.name||"视频片段"}`;
      const length=document.createElement('label');length.className='clip-duration';length.textContent="播放时长（秒）";
      const input=document.createElement('input');input.type='number';input.min='1';input.max='60';input.value=String(node.data.durations?.[id]||source.data.duration||5);input.onchange=()=>{node.data.durations=node.data.durations||{};node.data.durations[id]=Math.max(1,Math.min(60,Number(input.value)||5));};length.appendChild(input);
      const status=document.createElement('span');status.className=`timeline-clip-state ${source.data.status||'idle'}`;status.textContent=statusText(source.data.status||'waiting');
      clip.append(label,length,status);track.appendChild(clip);
    });
    body.appendChild(track);
    body.appendChild(createTimelineDropZone(node));
  }

  function createTimelineDropZone(node){
    const zone=document.createElement('div');zone.className='timeline-inline-drop';zone.textContent="将视频节点拖到这里以加入时间线";
    zone.ondragover=event=>{event.preventDefault();zone.classList.add('drag-over');};zone.ondragleave=()=>zone.classList.remove('drag-over');
    zone.ondrop=event=>{event.preventDefault();zone.classList.remove('drag-over');addTimelineClip(node,event.dataTransfer.getData('application/x-museflow-video-node')||event.dataTransfer.getData('text/plain'));};return zone;
  }

  function ensureDockTimeline(){let timeline=state.nodes.find(item=>item.type==='timeline');if(!timeline){timeline={id:uid('timeline'),type:'timeline',x:0,y:0,data:{clipOrder:[],durations:{},dockOnly:true}};state.nodes.push(timeline);}timeline.data=timeline.data||{};timeline.data.clipOrder=timeline.data.clipOrder||[];timeline.data.durations=timeline.data.durations||{};return timeline;}

  function addTimelineClip(timeline,nodeId){timeline=timeline||ensureDockTimeline();if(!nodeId||nodeById(nodeId)?.type!=='generateVideo'){setRunStatus("只有“生成视频”的输出可以加入时间线。",'warn');return;}timeline.data.clipOrder=timeline.data.clipOrder||[];if(!timeline.data.clipOrder.includes(nodeId))timeline.data.clipOrder.push(nodeId);syncTimelineDock();render();saveState();setRunStatus("视频已加入时间线。",'ok');}

  function importAllVideosToTimeline(){
    const timeline=ensureDockTimeline(),order=timeline.data.clipOrder,existing=new Set(order),all=state.nodes.filter(item=>item.type==='generateVideo');
    const additions=all.filter(video=>!existing.has(video.id));
    if(!additions.length){setRunStatus(all.length?"全部“生成视频”节点已在时间线上。":"没有可导入的“生成视频”节点。",'warn');return;}
    const addIds=new Set(additions.map(video=>video.id));
    order.push(...topoOrder().filter(id=>addIds.has(id)));
    syncTimelineDock();render();saveState();if($('#timelineDock').classList.contains('collapsed'))toggleTimeline();
    setRunStatus(`已导入 ${additions.length} 个视频节点到时间线。运行时将按时间线顺序生成视频。`,'ok');
  }

  function syncTimelineDock(){
    const dock=$('#timelineDock'),track=$('#timelineTrack'),count=$('#timelineClipCount'),addButton=$('#timelineAddVideoBtn'),importAllButton=$('#timelineImportAllBtn'),outputMenu=$('#timelineOutputMenu'),node=ensureDockTimeline();dock.classList.remove('no-timeline');const allVideos=state.nodes.filter(item=>item.type==='generateVideo'),candidates=allVideos.filter(item=>!(node.data.clipOrder||[]).includes(item.id));addButton.disabled=!candidates.length;addButton.title=addButton.disabled?"全部视频输出已在时间线上":"添加视频输出";importAllButton.disabled=!candidates.length;importAllButton.title=!allVideos.length?"没有可导入的“生成视频”节点":!candidates.length?"全部“生成视频”节点已在时间线上":"导入全部“生成视频”节点";outputMenu.innerHTML='';if(!candidates.length){const empty=document.createElement('span');empty.textContent="暂无视频输出";outputMenu.appendChild(empty);}candidates.forEach((video,index)=>{const option=document.createElement('button');option.type='button';option.textContent=video.data.asset?.name||`生成视频 ${index+1}`;option.onclick=()=>{outputMenu.classList.add('hidden');addTimelineClip(node,video.id);};outputMenu.appendChild(option);});
    const clips=(node.data.clipOrder||[]).map(id=>nodeById(id)).filter(item=>item?.type==='generateVideo');node.data.clipOrder=clips.map(item=>item.id);count.textContent=`${clips.length} 个片段`;track.innerHTML='';
    const ruler=document.createElement('div');ruler.className='timeline-ruler';const total=clips.reduce((sum,clip)=>sum+Number(node.data.durations?.[clip.id]||clip.data.duration||5),0);for(let sec=0;sec<=Math.ceil(total);sec+=5){const tick=document.createElement('span');tick.textContent=`${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')}`;ruler.appendChild(tick);}track.appendChild(ruler);
    const lane=document.createElement('div');lane.className='timeline-lane';if(!clips.length){const empty=document.createElement('div');empty.className='dock-empty';empty.textContent="将“生成视频”节点拖到这里以编排场景序列";lane.appendChild(empty);}
    clips.forEach((clip,index)=>{const duration=Number(node.data.durations?.[clip.id]||clip.data.duration||5),item=document.createElement('div');item.className='dock-clip';item.style.width=`${Math.max(210,Math.min(520,duration*42))}px`;item.draggable=true;item.dataset.clip=clip.id;item.ondragstart=event=>{event.dataTransfer.setData('application/x-museflow-video-node',clip.id);event.dataTransfer.effectAllowed='move';};item.ondragover=event=>event.preventDefault();item.ondrop=event=>{event.preventDefault();const moving=event.dataTransfer.getData('application/x-museflow-video-node'),from=node.data.clipOrder.indexOf(moving),to=node.data.clipOrder.indexOf(clip.id);if(from>=0&&to>=0){node.data.clipOrder.splice(from,1);node.data.clipOrder.splice(to,0,moving);syncTimelineDock();render();saveState();}else if(moving&&nodeById(moving)?.type==='generateVideo')addTimelineClip(node,moving);};
      const thumb=document.createElement('div');thumb.className='dock-clip-thumb';if(clip.data.asset?.url){if(clip.data.asset.kind==='image'){const image=document.createElement('img');image.src=clip.data.asset.url;thumb.appendChild(image);}else{const video=document.createElement('video');video.src=clip.data.asset.url;video.muted=true;video.preload='metadata';thumb.appendChild(video);}}else thumb.textContent='▶';
      const details=document.createElement('div');details.className='dock-clip-details';const title=document.createElement('span');title.textContent=`${String(index+1).padStart(2,'0')} · ${clip.data.asset?.name||"视频 "+(index+1)}`;title.title=title.textContent;const length=document.createElement('label');length.textContent='时长';const input=document.createElement('input');input.type='number';input.min='1';input.max='60';input.value=String(duration);input.onchange=()=>{node.data.durations=node.data.durations||{};node.data.durations[clip.id]=Math.max(1,Math.min(60,Number(input.value)||5));syncTimelineDock();render();};length.appendChild(input);details.append(title,length);const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.title="移除片段";remove.onclick=()=>{node.data.clipOrder=node.data.clipOrder.filter(id=>id!==clip.id);syncTimelineDock();render();};item.append(thumb,details,remove);lane.appendChild(item);});track.appendChild(lane);
    dock.ondragover=event=>{if(event.dataTransfer.types.includes('application/x-museflow-video-node')){event.preventDefault();dock.classList.add('drag-over');if(dock.classList.contains('collapsed'))toggleTimeline();}};dock.ondragleave=event=>{if(!dock.contains(event.relatedTarget))dock.classList.remove('drag-over');};dock.ondrop=event=>{event.preventDefault();dock.classList.remove('drag-over');const id=event.dataTransfer.getData('application/x-museflow-video-node');if(id)addTimelineClip(node,id);};
  }

  function toggleTimelineOutputMenu(){if($('#timelineAddVideoBtn').disabled)return;$('#timelineOutputMenu').classList.toggle('hidden');}

  function toggleTimeline(){const dock=$('#timelineDock'),collapsed=dock.classList.toggle('collapsed'),button=$('#timelineToggleBtn');button.textContent=collapsed?'▲':'▼';button.title=collapsed?"展开时间线":"收起时间线";button.setAttribute('aria-expanded',String(!collapsed));}

  function closeTimelinePreview(){state.timelinePreviewToken++;clearTimeout(state.timelinePreviewTimer);for(const player of [$('#timelinePlayer'),$('#timelinePlayerNext')]){player.pause();player.onended=null;}$('#timelinePreviewPanel').classList.add('hidden');}
  function visibleTimelineClipOrder(node){const nodeTrack=document.querySelector(`.node[data-id="${CSS.escape(node.id)}"] .timeline-track`),dockTrack=$('#timelineTrack'),visualTrack=nodeTrack||dockTrack,selector=nodeTrack?'.timeline-clip':'.dock-clip',visibleOrder=[...visualTrack.querySelectorAll(selector)].map(item=>item.dataset.clip).filter(Boolean);return visibleOrder.length?visibleOrder:[...(node.data.clipOrder||[])];}
  function playTimeline(node){
    const players=[$('#timelinePlayer'),$('#timelinePlayerNext')],panel=$('#timelinePreviewPanel'),clips=visibleTimelineClipOrder(node).map(id=>nodeById(id)).filter(n=>n?.type==='generateVideo'&&n.data?.asset?.url);
    if(!clips.length){setRunStatus("请先将已生成的视频片段连接到时间线。",'warn');return;}
    clearTimeout(state.timelinePreviewTimer);const token=++state.timelinePreviewToken;panel.classList.remove('hidden');let index=0,active=players.findIndex(player=>player.classList.contains('is-active'));if(active<0)active=0;
    players.forEach(player=>{player.pause();player.onended=null;player.muted=false;player.controls=player===players[active];});
    const waitForFrame=video=>new Promise(resolve=>{let finished=false;const done=()=>{if(finished)return;finished=true;clearTimeout(fallback);resolve();};const fallback=setTimeout(done,1200);if(video.requestVideoFrameCallback)video.requestVideoFrameCallback(done);else requestAnimationFrame(()=>requestAnimationFrame(done));});
    const waitForData=video=>new Promise((resolve,reject)=>{if(video.readyState>=2){resolve();return;}let timer=setTimeout(()=>{cleanup();reject(new Error("下一个时间线片段加载超时。"));},15000);const ready=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(new Error("无法加载下一个时间线片段。"));},cleanup=()=>{clearTimeout(timer);video.removeEventListener('loadeddata',ready);video.removeEventListener('error',failed);};video.addEventListener('loadeddata',ready,{once:true});video.addEventListener('error',failed,{once:true});});
    const prepareClip=(clipIndex,video)=>{const clip=clips[clipIndex];if(!clip)return Promise.resolve();if(video.dataset.preloadClip===clip.id&&video.readyState>=2)return Promise.resolve(video);video.pause();video.onended=null;video.preload='auto';video.dataset.preloadClip=clip.id;video.src=clip.data.asset.url;video.load();return waitForData(video).then(()=>{if(video.dataset.preloadClip===clip.id)video.currentTime=0;return video;});};
    const playNext=async()=>{
      clearTimeout(state.timelinePreviewTimer);if(token!==state.timelinePreviewToken)return;
      if(index>=clips.length){players[active].onended=null;players[active].pause();setRunStatus("时间线预览完成。",'ok');return;}
      const clipIndex=index,clip=clips[index++],nextIndex=1-active,next=players[nextIndex],previous=players[active];next.pause();next.onended=null;next.muted=false;next.controls=false;next.classList.remove('is-active','is-fading');
      try{await prepareClip(clipIndex,next);if(token!==state.timelinePreviewToken)return;next.currentTime=0;await next.play();await waitForFrame(next);}catch(error){if(token===state.timelinePreviewToken&&next.readyState>=2){next.controls=true;next.classList.add('is-active');previous.controls=false;previous.classList.remove('is-active','is-fading');active=nextIndex;next.onended=()=>{if(token===state.timelinePreviewToken)playNext();};setRunStatus(`时间线片段已就绪；请点击播放继续（${error.message})`,'warn');}else if(token===state.timelinePreviewToken)setRunStatus(`时间线预览已暂停：${error.message}`,'error');return;}
      if(token!==state.timelinePreviewToken){next.pause();return;}
      next.controls=true;next.classList.add('is-active');previous.controls=false;previous.onended=null;previous.classList.remove('is-active');previous.classList.add('is-fading');active=nextIndex;setTimeout(()=>{previous.classList.remove('is-fading');if(token===state.timelinePreviewToken)previous.pause();},180);
      if(index<clips.length)prepareClip(index,previous).catch(()=>{});
      const advance=()=>{if(token!==state.timelinePreviewToken)return;clearTimeout(state.timelinePreviewTimer);next.onended=null;playNext();};next.onended=advance;
      state.timelinePreviewTimer=setTimeout(advance,Math.max(1,Number(node.data.durations?.[clip.id]||clip.data.duration||5))*1000);setRunStatus(`时间线镜头 ${index}/${clips.length}`,'warn');
    };
    playNext();
  }

  async function exportTimelineVideo(){
    if(state.timelineExporting)return;const node=ensureDockTimeline(),clips=visibleTimelineClipOrder(node).map(id=>nodeById(id)).filter(clip=>clip?.type==='generateVideo'&&clip.data?.asset?.url),button=$('#timelineExportBtn');
    if(!clips.length){setRunStatus("导出前，请先将已生成的视频片段加入时间线。",'warn');return;}
    if(!window.MediaRecorder||!HTMLCanvasElement.prototype.captureStream){setRunStatus("此浏览器不支持导出时间线拼接视频。",'error');return;}
    state.timelineExporting=true;button.disabled=true;const sourceUrls=[];let recorder=null,canvasStream=null,audioContext=null,audioSource=null,audioDestination=null,audioResumePromise=Promise.resolve(),video=null,frameRequest=0,recordingPromise=null;
    try{const AudioContextType=window.AudioContext||window.webkitAudioContext;if(AudioContextType){audioContext=new AudioContextType();audioDestination=audioContext.createMediaStreamDestination();audioResumePromise=audioContext.resume().catch(()=>{});}}catch{audioContext=null;audioDestination=null;}
    try{
      for(let index=0;index<clips.length;index++){
        button.textContent=`正在准备 ${index+1}/${clips.length}…`;setRunStatus(`正在准备时间线片段 ${index+1}/${clips.length}以导出…`,'warn');
        const response=await fetch(clips[index].data.asset.url,{credentials:'include'});if(!response.ok)throw new Error(`无法下载时间线片段 ${index+1} (HTTP ${response.status}).`);
        const blob=await response.blob();if(!blob.size)throw new Error(`时间线片段 ${index+1}内容为空。`);sourceUrls.push(URL.createObjectURL(blob));
      }
      video=document.createElement('video');video.preload='auto';video.playsInline=true;video.muted=false;video.style.cssText='position:fixed;width:2px;height:2px;left:-4px;bottom:0;opacity:.01;pointer-events:none';document.body.appendChild(video);
      const waitForData=()=>new Promise((resolve,reject)=>{if(video.readyState>=2){resolve();return;}let timer=setTimeout(()=>{cleanup();reject(new Error("视频解码超时。"));},20000);const ready=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(new Error("无法解码此视频文件。"));},cleanup=()=>{clearTimeout(timer);video.removeEventListener('loadeddata',ready);video.removeEventListener('error',failed);};video.addEventListener('loadeddata',ready,{once:true});video.addEventListener('error',failed,{once:true});});
      video.src=sourceUrls[0];video.load();await waitForData();
      const originalWidth=video.videoWidth||1280,originalHeight=video.videoHeight||720,scale=Math.min(1,1920/Math.max(originalWidth,originalHeight)),canvas=document.createElement('canvas');canvas.width=Math.max(2,Math.floor(originalWidth*scale/2)*2);canvas.height=Math.max(2,Math.floor(originalHeight*scale/2)*2);
      const context=canvas.getContext('2d',{alpha:false});if(!context)throw new Error("无法创建视频导出画布。");
      const drawFrame=()=>{if(!video||!context)return;if(video.readyState>=2&&video.videoWidth>0){const fit=Math.min(canvas.width/video.videoWidth,canvas.height/video.videoHeight),width=video.videoWidth*fit,height=video.videoHeight*fit;context.fillStyle='#000';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(video,(canvas.width-width)/2,(canvas.height-height)/2,width,height);}frameRequest=requestAnimationFrame(drawFrame);};drawFrame();
      canvasStream=canvas.captureStream(30);
      if(audioContext&&audioDestination){try{audioSource=audioContext.createMediaElementSource(video);audioSource.connect(audioDestination);const audioTrack=audioDestination.stream.getAudioTracks()[0];if(audioTrack)canvasStream.addTrack(audioTrack);await audioResumePromise;if(audioContext.state!=='running')await audioContext.resume();}catch{audioContext.close().catch(()=>{});audioContext=null;audioDestination=null;audioSource=null;}}
      if(!audioDestination&&typeof video.captureStream==='function'){const captured=video.captureStream();for(const track of captured.getAudioTracks())canvasStream.addTrack(track);}
      const mimeType=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'].find(type=>MediaRecorder.isTypeSupported?.(type));recorder=mimeType?new MediaRecorder(canvasStream,{mimeType}):new MediaRecorder(canvasStream);
      const chunks=[];recordingPromise=new Promise((resolve,reject)=>{recorder.ondataavailable=event=>{if(event.data?.size)chunks.push(event.data);};recorder.onerror=event=>reject(event.error||new Error("视频编码失败。"));recorder.onstop=()=>resolve(new Blob(chunks,{type:recorder.mimeType||'video/webm'}));});recordingPromise.catch(()=>{});recorder.start(1000);
      for(let index=0;index<clips.length;index++){
        if(index){video.pause();video.src=sourceUrls[index];video.load();await waitForData();}
        video.currentTime=0;await video.play();button.textContent=`正在导出 ${index+1}/${clips.length}…`;setRunStatus(`正在导出时间线片段 ${index+1}/${clips.length}（按轨道顺序）…`,'warn');
        const duration=Math.max(1,Math.min(60,Number(node.data.durations?.[clips[index].id]||clips[index].data.duration||5)));await new Promise(resolve=>setTimeout(resolve,duration*1000));video.pause();
      }
      const completed=new Promise(resolve=>{recorder.addEventListener('stop',resolve,{once:true});});recorder.stop();await completed;const output=await recordingPromise;if(!output.size)throw new Error("导出的视频为空。");
      if(state.timelineExportUrl)URL.revokeObjectURL(state.timelineExportUrl);state.timelineExportUrl=URL.createObjectURL(output);
      const player=$('#timelinePlayer'),nextPlayer=$('#timelinePlayerNext');closeTimelinePreview();$('#timelinePreviewPanel').classList.remove('hidden');nextPlayer.pause();nextPlayer.classList.remove('is-active','is-fading');nextPlayer.controls=false;player.src=state.timelineExportUrl;player.controls=true;player.classList.remove('is-fading');player.classList.add('is-active');
      const link=document.createElement('a');link.href=state.timelineExportUrl;link.download=`MuseFlow-Timeline-${new Date().toISOString().replace(/[:.]/g,'-')}.webm`;link.click();setRunStatus("时间线拼接视频已导出为 WebM。",'ok');
    }catch(error){setRunStatus(`时间线导出失败：${error?.message||String(error)}`,'error');}
    finally{if(frameRequest)cancelAnimationFrame(frameRequest);if(recorder?.state==='recording'){recorder.stop();try{await recordingPromise;}catch{}}video?.pause();video?.remove();canvasStream?.getTracks().forEach(track=>track.stop());await audioContext?.close().catch(()=>{});sourceUrls.forEach(url=>URL.revokeObjectURL(url));state.timelineExporting=false;button.disabled=false;button.textContent="⇩ 导出视频";}
  }

  function getPortCenter(nodeId, portId, kind) {
    const q = `.port.${kind}[data-node="${CSS.escape(nodeId)}"][data-port="${CSS.escape(portId)}"]`;
    const p = document.querySelector(q); if (!p) return null;
    const r=p.getBoundingClientRect(), vr=$('#viewport').getBoundingClientRect();
    return { x:(r.left-vr.left-state.panX)/state.zoom+r.width/(2*state.zoom), y:(r.top-vr.top-state.panY)/state.zoom+r.height/(2*state.zoom) };
  }

  function drawEdges() {
    edgesSvg.innerHTML='';
    state.edges.forEach(e => {
      const a=getPortCenter(e.source,e.sourcePort,'out'), b=getPortCenter(e.target,e.targetPort,'in'); if(!a||!b)return;
      const incoming=getIncoming(e.target,e.targetPort),index=incoming.findIndex(edge=>edge.id===e.id),fan=isMultiInput(nodeById(e.target)?.type,e.targetPort)&&incoming.length>1?(index-(incoming.length-1)/2)*12:0;
      const dx=b.x-a.x,direction=dx<0?-1:1,bend=Math.max(62,Math.abs(dx)*.42),output=nodeDefs[nodeById(e.source)?.type]?.outputs?.find(port=>port.id===e.sourcePort),d=`M ${a.x} ${a.y} C ${a.x+direction*bend} ${a.y}, ${b.x-direction*bend} ${b.y+fan}, ${b.x} ${b.y}`,selected=state.selectedEdgeIds.includes(e.id);const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('class',`edge edge-${output?.type||'media'}${selected?' edge-selected':''}`);path.setAttribute('d',d);path.setAttribute('data-edge-id',e.id);edgesSvg.appendChild(path);const hit=document.createElementNS('http://www.w3.org/2000/svg','path');hit.setAttribute('class','edge-hit');hit.setAttribute('data-edge-id',e.id);hit.setAttribute('d',d);edgesSvg.appendChild(hit);
    });
    if(state.draggingWire&&state.wirePointer){
      const reverse=state.draggingWire.direction==='in',a=getPortCenter(state.draggingWire.nodeId,state.draggingWire.portId,reverse?'in':'out');
      const vr=$('#viewport').getBoundingClientRect();
      if(a){const x=(state.wirePointer.x-vr.left-state.panX)/state.zoom,y=(state.wirePointer.y-vr.top-state.panY)/state.zoom,dx=reverse?a.x-x:x-a.x,direction=dx<0?-1:1,bend=Math.max(55,Math.abs(dx)*.4),d=reverse?`M ${x} ${y} C ${x+direction*bend} ${y}, ${a.x-direction*bend} ${a.y}, ${a.x} ${a.y}`:`M ${a.x} ${a.y} C ${a.x+direction*bend} ${a.y}, ${x-direction*bend} ${y}, ${x} ${y}`;const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('class','edge edge-draft');p.setAttribute('d',d);edgesSvg.appendChild(p);}
    }
  }

  function scheduleDrawEdges() {
    if (state.edgeFrame) return;
    state.edgeFrame = requestAnimationFrame(() => { state.edgeFrame = 0; drawEdges(); });
  }

  function render() {
    syncPreviewOutputs();canvas.innerHTML=''; state.nodes.filter(n=>!n.data?.dockOnly).forEach(n => canvas.appendChild(renderNode(n)));applyCanvasTransform();requestAnimationFrame(drawEdges);syncTimelineDock();scheduleAutoSave();
  }

  function syncPreviewOutputs(){for(const preview of state.nodes.filter(node=>node.type==='preview')){const edge=getIncoming(preview.id,'media')[0],source=edge&&nodeById(edge.source);let asset=null;if(source){asset=edge.sourcePort==='endFrame'?source.data?.endFrame:source.data?.asset;if(!asset&&source.type==='imageInput'&&source.data?.localDataUrl)asset={id:source.id,kind:'image',url:source.data.localDataUrl,name:"输入图片"};}preview.data.asset=asset||null;}}

  function applyCanvasTransform(){const transform=`translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;canvas.style.transform=transform;edgesSvg.style.transform=transform;$('#zoomLevel').textContent=`${Math.round(state.zoom*100)}%`;$('#viewport').classList.toggle('hand-mode',state.handMode||state.spaceDown);}
  function zoomAt(clientX,clientY,factor){const rect=$('#viewport').getBoundingClientRect(),x=clientX-rect.left,y=clientY-rect.top,old=state.zoom,next=Math.max(.25,Math.min(2.5,old*factor));if(next===old)return;const contentX=(x-state.panX)/old,contentY=(y-state.panY)/old;state.zoom=next;state.panX=x-contentX*next;state.panY=y-contentY*next;applyCanvasTransform();scheduleDrawEdges();}
  function setZoom(value){const rect=$('#viewport').getBoundingClientRect();zoomAt(rect.left+rect.width/2,rect.top+rect.height/2,value/state.zoom);}
  function fitCanvas(){const nodes=state.nodes.filter(node=>!node.data?.dockOnly);if(!nodes.length){state.zoom=1;state.panX=0;state.panY=0;applyCanvasTransform();return;}const rect=$('#viewport').getBoundingClientRect(),xs=nodes.map(n=>n.x),ys=nodes.map(n=>n.y),maxX=Math.max(...nodes.map(n=>n.x+(document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.offsetWidth||270))),maxY=Math.max(...nodes.map(n=>n.y+(document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.offsetHeight||220)));const minX=Math.min(...xs),minY=Math.min(...ys),scale=Math.max(.25,Math.min(1.5,(rect.width-100)/(maxX-minX+80),(rect.height-80)/(maxY-minY+80)));state.zoom=scale;state.panX=(rect.width-(maxX-minX)*scale)/2-minX*scale;state.panY=(rect.height-(maxY-minY)*scale)/2-minY*scale;applyCanvasTransform();scheduleDrawEdges();}
  function startPan(event){state.panning={x:event.clientX,y:event.clientY,panX:state.panX,panY:state.panY};$('#viewport').classList.add('panning');try{event.currentTarget.setPointerCapture(event.pointerId);}catch{}event.preventDefault();}
  function movePan(event){if(!state.panning)return;state.panX=state.panning.panX+event.clientX-state.panning.x;state.panY=state.panning.panY+event.clientY-state.panning.y;applyCanvasTransform();scheduleDrawEdges();}
  function endPan(){state.panning=null;$('#viewport').classList.remove('panning');}

  function startSelectionMarquee(event){
    if(event.button!==0||state.handMode||state.spaceDown||event.target.closest('.node,.canvas-tools,button'))return;
    const viewport=$('#viewport'),bounds=viewport.getBoundingClientRect(),keep=event.shiftKey||event.ctrlKey||event.metaKey;
    if(!keep){state.selectedNodeIds=[];state.selectedNodeId=null;state.selectedEdgeIds=[];document.querySelectorAll('.node.selected').forEach(node=>node.classList.remove('selected'));scheduleDrawEdges();}
    const box=document.createElement('div');box.className='selection-marquee';viewport.appendChild(box);
    state.selectionMarquee={startX:event.clientX,startY:event.clientY,bounds,box,keep,initial:[...state.selectedNodeIds],initialEdges:keep?[...state.selectedEdgeIds]:[]};
    try{viewport.setPointerCapture(event.pointerId);}catch{}event.preventDefault();
  }
  function moveSelectionMarquee(event){const drag=state.selectionMarquee;if(!drag)return;const left=Math.min(event.clientX,drag.startX),top=Math.min(event.clientY,drag.startY),right=Math.max(event.clientX,drag.startX),bottom=Math.max(event.clientY,drag.startY);Object.assign(drag.box.style,{left:`${left-drag.bounds.left}px`,top:`${top-drag.bounds.top}px`,width:`${right-left}px`,height:`${bottom-top}px`});const selected=new Set(drag.initial);for(const node of document.querySelectorAll('.node')){const r=node.getBoundingClientRect();if(r.right>=left&&r.left<=right&&r.bottom>=top&&r.top<=bottom)selected.add(node.dataset.id);}state.selectedNodeIds=[...selected];state.selectedNodeId=state.selectedNodeIds.at(-1)||null;document.querySelectorAll('.node').forEach(node=>node.classList.toggle('selected',selected.has(node.dataset.id)));const selectedEdges=new Set(drag.initialEdges);for(const path of edgesSvg.querySelectorAll('.edge[data-edge-id]')){const matrix=path.getScreenCTM();if(!matrix)continue;const length=path.getTotalLength();for(let point=0;point<=length;point+=Math.max(8,length/60)){const p=new DOMPoint(path.getPointAtLength(point).x,path.getPointAtLength(point).y).matrixTransform(matrix);if(p.x>=left&&p.x<=right&&p.y>=top&&p.y<=bottom){selectedEdges.add(path.dataset.edgeId);break;}}}state.selectedEdgeIds=[...selectedEdges];scheduleDrawEdges();}
  function endSelectionMarquee(){const drag=state.selectionMarquee;if(!drag)return;drag.box.remove();state.selectionMarquee=null;}

  function openCanvasMenu(e){
    const nodeEl=e.target.closest('.node');e.preventDefault();e.stopPropagation();
    if(!nodeEl){const rect=$('#viewport').getBoundingClientRect(),menu=$('#canvasMenu');state.contextPoint={x:(e.clientX-rect.left-state.panX)/state.zoom,y:(e.clientY-rect.top-state.panY)/state.zoom};menu.innerHTML='';delete menu.dataset.nodeId;const title=document.createElement('div');title.className='menu-caption';title.textContent="画布";menu.appendChild(title);[['＋ 提示词','add:prompt'],['＋ 反向提示词','add:negativePrompt'],['＋ 图片输入','add:imageInput'],['＋ 参考素材','add:references'],['＋ 生成图片','add:generateImage'],['＋ 生成视频','add:generateVideo'],['＋ 时间线','add:timeline'],['＋ 预览','add:preview'],["导出工作流",'save'],['▶ 运行选中节点','run-selected'],['▶ 智能运行工作流','run'],['↺ 全量重新运行','run-all'],["整理节点",'arrange'],["删除选中节点",'delete-selected'],["移除全部连接",'disconnect-all']].forEach(([label,action])=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.contextAction=action;menu.appendChild(button);});menu.classList.remove('hidden');menu.style.left=`${Math.min(e.clientX,innerWidth-230)}px`;menu.style.top=`${Math.min(e.clientY,innerHeight-460)}px`;return;}
    e.stopPropagation();const node=nodeById(nodeEl.dataset.id);if(!node)return;state.selectedNodeId=node.id;
    const menu=$('#canvasMenu');menu.innerHTML='';menu.dataset.nodeId=node.id;
    const title=document.createElement('div');title.className='menu-caption';title.textContent=nodeDefs[node.type].title;menu.appendChild(title);
    const addAction=(label,action)=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.contextAction=action;menu.appendChild(button);};
    if(['generateImage','generateVideo'].includes(node.type))addAction(node.data.status==='running'?`■ 停止${node.type==='generateVideo'?"视频":"图片"}`:`▶ 生成${node.type==='generateVideo'?"视频":"图片"}`,'node-run');
    if(state.selectedNodeIds.length>1)addAction(`▶ 运行选中的 ${state.selectedNodeIds.filter(id=>['generateImage','generateVideo'].includes(nodeById(id)?.type)).length} 个生成节点`,'run-selected');
    if(node.type==='timeline')addAction("▶ 预览序列",'node-preview');
    if((nodeDefs[node.type]?.outputs||[]).some(port=>['image','video'].includes(port.type)))addAction("创建预览节点",'node-create-preview');
    if(node.type==='imageInput')addAction("选择／替换图片",'node-choose-image');
    if(node.type==='imageResize')addAction("下载调整后的图片",'node-download-image');
    if(node.type==='preview')addAction("下载预览内容",'node-download-preview');
    if(node.type==='prompt'||node.type==='negativePrompt'||node.type==='textAppend')addAction("编辑文本",'node-focus-text');
    addAction("复制节点",'node-duplicate');addAction("断开节点连接",'node-disconnect');addAction("删除节点",'node-delete');
    menu.classList.remove('hidden');menu.style.left=`${Math.min(e.clientX,innerWidth-230)}px`;menu.style.top=`${Math.min(e.clientY,innerHeight-380)}px`;
  }
  function openEdgeMenu(e){
    const hit=e.target.closest('.edge-hit[data-edge-id]');if(!hit)return;
    e.preventDefault();e.stopPropagation();const menu=$('#canvasMenu');menu.innerHTML='';menu.dataset.edgeId=hit.dataset.edgeId;delete menu.dataset.nodeId;
    const title=document.createElement('div');title.className='menu-caption';title.textContent="连接";menu.appendChild(title);
    const button=document.createElement('button');button.type='button';button.textContent="删除连接";button.dataset.contextAction='edge-delete';menu.appendChild(button);
    menu.classList.remove('hidden');menu.style.left=`${Math.min(e.clientX,innerWidth-230)}px`;menu.style.top=`${Math.min(e.clientY,innerHeight-120)}px`;
  }
  function selectEdgePointer(e){if(e.button!==0)return;const hit=e.target.closest('.edge-hit[data-edge-id]');if(!hit)return;e.preventDefault();e.stopPropagation();const id=hit.dataset.edgeId;state.selectedEdgeIds=e.shiftKey?[...new Set([...state.selectedEdgeIds,id])]:[id];scheduleDrawEdges();}
  function closeCanvasMenu(){ $('#canvasMenu').classList.add('hidden'); }
  function runNodeContextAction(action){const menu=$('#canvasMenu'),node=nodeById(menu.dataset.nodeId);if(!node)return;closeCanvasMenu();
    if(action==='node-run'){runSingleNode(node.id);return;}if(action==='node-preview'){playTimeline(node);return;}if(action==='node-delete'){removeNode(node.id);return;}
    if(action==='node-create-preview'){const output=(nodeDefs[node.type].outputs||[]).find(port=>['image','video'].includes(port.type));if(output){const target=makeNode('preview',node.x+350,node.y);state.nodes.push(target);state.connectingFrom={nodeId:node.id,portId:output.id};connect(target.id,'media');}return;}
    if(action==='node-disconnect'){state.edges=state.edges.filter(edge=>edge.source!==node.id&&edge.target!==node.id);render();setRunStatus("已移除此节点的连接。",'ok');return;}
    const el=document.querySelector(`.node[data-id="${CSS.escape(node.id)}"]`);
    if(action==='node-focus-text'){el?.querySelector('textarea')?.focus();return;}
    if(action==='node-choose-image'){el?.querySelector('input[type="file"]')?.click();return;}
    if(action==='node-download-image'||action==='node-download-preview'){const url=node.data.asset?.url;if(url){const link=document.createElement('a');link.href=url;link.download=node.data.asset.name||'museflow-output';link.click();}else setRunStatus("此节点暂无可下载的输出。",'warn');return;}
    if(action==='node-duplicate'){const copy=structuredClone(node);copy.id=uid(node.type);copy.x+=36;copy.y+=36;copy.data={...copy.data};state.nodes.push(copy);if(['generateImage','generateVideo'].includes(copy.type)){const references=state.nodes.find(item=>item.type==='references');if(references)connectReferenceNode(references,copy);}render();setRunStatus("节点已复制。",'ok');}
  }
  function arrangeNodes(){
    try{
      const order=topoOrder().filter(id=>!nodeById(id)?.data?.dockOnly),level=new Map(order.map(id=>[id,0]));
      for(const id of order)for(const edge of state.edges.filter(e=>e.source===id&&level.has(e.target)))level.set(edge.target,Math.max(level.get(edge.target)||0,(level.get(id)||0)+1));
      const groups=new Map();for(const id of order){const l=level.get(id)||0;if(!groups.has(l))groups.set(l,[]);groups.get(l).push(id);}
      for(const [l,ids] of groups.entries())ids.forEach((id,row)=>{const node=nodeById(id);node.x=70+l*350;node.y=60+row*260;});
      render();setRunStatus("已按工作流顺序整理节点。",'ok');
    }catch(error){setRunStatus(error.message,'error');}
  }
  function runCanvasAction(action){
    if(action==='edge-delete'){const menu=$('#canvasMenu'),edgeId=menu.dataset.edgeId;closeCanvasMenu();if(!edgeId)return;const before=state.edges.length;state.edges=state.edges.filter(edge=>edge.id!==edgeId);delete menu.dataset.edgeId;if(state.edges.length!==before){render();saveState();setRunStatus("连接已删除。",'ok');}return;}
    if(action.startsWith('node-')){runNodeContextAction(action);return;}
    closeCanvasMenu();const pos=state.contextPoint;
    if(action.startsWith('add:')){addNode(action.slice(4),pos.x,pos.y);return;}
    if(action==='save'){saveState();return;}
    if(action==='run'){execute(null,{forceAll:false});return;}
    if(action==='run-all'){execute(null,{forceAll:true});return;}
    if(action==='run-selected'){runSelectedNodes();return;}
    if(action==='arrange'){arrangeNodes();return;}
    if(action==='delete-selected'){if(state.selectedNodeIds.length)removeSelectedNodes();else if(state.selectedNodeId)removeNode(state.selectedNodeId);else setRunStatus("请先选择一个或多个节点。",'warn');return;}
    if(action==='disconnect-all'){state.edges=[];state.connectingFrom=null;render();setRunStatus("已移除全部连接。",'ok');}
  }

  function runSelectedNodes(){
    const selected=state.selectedNodeIds.filter(id=>['generateImage','generateVideo'].includes(nodeById(id)?.type));
    if(selected.length)execute(selected);
    else if(state.selectedNodeId&&['generateImage','generateVideo'].includes(nodeById(state.selectedNodeId)?.type))execute(state.selectedNodeId);
    else setRunStatus("请先在画布中选择一个或多个生成节点。",'warn');
  }

  function runNodeContextAction(action){const menu=$('#canvasMenu'),node=nodeById(menu.dataset.nodeId);if(!node)return;closeCanvasMenu();
    if(action==='node-run'){runSingleNode(node.id);return;}if(action==='node-preview'){playTimeline(node);return;}if(action==='node-delete'){removeNode(node.id);return;}
    if(action==='node-disconnect'){state.edges=state.edges.filter(edge=>edge.source!==node.id&&edge.target!==node.id);render();setRunStatus("已移除此节点的连接。",'ok');return;}
    const el=document.querySelector(`.node[data-id="${CSS.escape(node.id)}"]`);
    if(action==='node-focus-text'){el?.querySelector('textarea')?.focus();return;}if(action==='node-choose-image'){el?.querySelector('input[type="file"]')?.click();return;}
    if(action==='node-download-image'||action==='node-download-preview'){const url=node.data.asset?.url;if(url){const link=document.createElement('a');link.href=url;link.download=node.data.asset.name||'museflow-output';link.click();}else setRunStatus("此节点暂无可下载的输出。",'warn');return;}
    if(action==='node-duplicate'){const copy=structuredClone(node);copy.id=uid(node.type);copy.x+=36;copy.y+=36;copy.data={...copy.data};state.nodes.push(copy);render();setRunStatus("节点已复制。",'ok');}
  }

  function getIncoming(nodeId, targetPort) { return state.edges.filter(e => e.target===nodeId && (!targetPort || e.targetPort===targetPort)); }
  function sourceFor(edge) { return edge ? nodeById(edge.source) : null; }

  function resolveText(nodeId,seen=new Set()){
    if(seen.has(nodeId))return '';seen.add(nodeId);
    const node=nodeById(nodeId);if(!node)return '';
    if(['prompt','negativePrompt'].includes(node.type))return String(node.data?.text??node.data?.prompt??node.data?.value??'');
    if(node.type==='textAppend'){
      const parent=sourceFor(getIncoming(nodeId,'text')[0]);
      return [parent?resolveText(parent.id,new Set(seen)):'' ,String(node.data?.text??'')].filter(value=>value.trim()).join(' ');
    }
    if(node.type==='textConcat'){
      const inputs=['a','b'].map(port=>sourceFor(getIncoming(nodeId,port)[0])).filter(Boolean).map(source=>resolveText(source.id,new Set(seen))).filter(Boolean);
      return inputs.join(node.data.separator??', ');
    }
    const source=sourceFor(getIncoming(nodeId,'text')[0]);return source?resolveText(source.id,seen):'';
  }
  function resolvePrompt(nodeId){
    return getIncoming(nodeId,'prompt').map(edge=>nodeById(edge.source)).filter(Boolean).map(source=>resolveText(source.id).trim()).filter(Boolean).join('\n\n');
  }
  function resolveNegativePrompt(nodeId){const source=sourceFor(getIncoming(nodeId,'negative')[0]);return source?resolveText(source.id):'';}
  function timelinePredecessor(nodeId){const timeline=state.nodes.find(item=>item.type==='timeline'),order=timeline?.data?.clipOrder||[],index=order.indexOf(nodeId);return index>0?nodeById(order[index-1]):null;}
  function resolveReferences(nodeId){
    const references=[],seen=new Set();
    const add=(url,name)=>{if(url&&!seen.has(url)){seen.add(url);references.push({url,name:name||`参考图 ${references.length+1}`});}};
    const visit=(source,sourcePort,visited=new Set())=>{if(!source||visited.has(source.id))return;visited.add(source.id);if(source.type==='references'){for(const edge of getIncoming(source.id))visit(nodeById(edge.source),edge.sourcePort,visited);return;}if(sourcePort==='endFrame'){add(source.data?.endFrame?.url,source.data?.endFrame?.name);return;}if(source.type==='imageInput'&&source.data?.localDataUrl){add(source.data.localDataUrl,"输入图片");return;}if(source.data?.asset?.kind==='image')add(source.data.asset.url,source.data.asset.name);};
    const node=nodeById(nodeId),previous=node?.type==='generateVideo'&&node.data?.continuity?timelinePredecessor(nodeId):null;if(previous)add(previous.data?.endFrame?.url,`CONTINUITY START FRAME · ${previous.data?.endFrame?.name||'previous clip end'}`);
    for(const edge of getIncoming(nodeId,'reference'))visit(nodeById(edge.source),edge.sourcePort);
    return references;
  }

  function topoOrder() {
    const indeg=new Map(state.nodes.map(n=>[n.id,0])), outgoing=new Map(state.nodes.map(n=>[n.id,[]]));
    state.edges.forEach(e=>{if(!indeg.has(e.source)||!indeg.has(e.target))return;indeg.set(e.target,indeg.get(e.target)+1);outgoing.get(e.source).push(e.target);});
    for(const node of state.nodes.filter(item=>item.type==='generateVideo'&&item.data?.continuity)){const previous=timelinePredecessor(node.id);if(previous&&previous.id!==node.id&&!outgoing.get(previous.id).includes(node.id)){outgoing.get(previous.id).push(node.id);indeg.set(node.id,indeg.get(node.id)+1);}}
    const timeline=state.nodes.find(item=>item.type==='timeline'),orderedVideos=(timeline?.data?.clipOrder||[]).filter(id=>nodeById(id)?.type==='generateVideo');
    for(const node of state.nodes)if(node.type==='generateVideo'&&!orderedVideos.includes(node.id))orderedVideos.push(node.id);
    const videoRank=new Map(orderedVideos.map((id,index)=>[id,index])),nodeRank=new Map(state.nodes.map((node,index)=>[node.id,index]));
    const priority=id=>{const item=nodeById(id);return item?.type==='generateVideo'?state.nodes.length+1+(videoRank.get(id)??nodeRank.get(id)):nodeRank.get(id)??0;};
    const q=state.nodes.filter(n=>indeg.get(n.id)===0).map(n=>n.id), out=[];
    while(q.length){q.sort((a,b)=>priority(a)-priority(b));const id=q.shift();out.push(id);for(const target of outgoing.get(id)){indeg.set(target,indeg.get(target)-1);if(indeg.get(target)===0)q.push(target);}}
    if(out.length!==state.nodes.length) throw new Error("工作流存在循环，请先移除循环连接。"); return out;
  }

  function requiredNodeOrder(targetId){
    return requiredNodesFor(targetId);
  }

  function requiredNodesFor(targets){
    const targetSet=targets instanceof Set?targets:new Set(Array.isArray(targets)?targets:[targets]);
    const required=new Set();
    const visit=id=>{if(required.has(id))return;required.add(id);for(const edge of state.edges.filter(item=>item.target===id))visit(edge.source);const node=nodeById(id),previous=node?.type==='generateVideo'&&node.data?.continuity?timelinePredecessor(id):null;if(previous)visit(previous.id);};
    targetSet.forEach(id=>visit(id));return topoOrder().filter(id=>required.has(id));
  }

  function validateTargetPrompt(targetId){
    const target=nodeById(targetId);if(!target||!['generateImage','generateVideo'].includes(target.type))throw new Error("所选生成节点已不存在。");
    const prompt=resolvePrompt(targetId);if(prompt.trim())return prompt;
    const edge=getIncoming(targetId,'prompt')[0],source=edge&&nodeById(edge.source);
    const detail=!edge?"请将提示词或文本节点连接到此节点的提示词输入端口。":!source?"相连的提示词节点已不存在。":`相连的 ${nodeDefs[source.type]?.title||'text'}节点没有文本内容。`;
    target.data.status='error';target.data.error=detail;
    render();throw new Error(`${nodeDefs[target.type]?.title||"生成节点"} ${target.id}: ${detail}`);
  }

  let preferredMuseTabId=null;
  async function museTabMessage(message, preferredTabId, signal) {
    if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');
    const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
    if(!tabs.length)throw new Error("请打开 Muse.ai 并登录，然后重试。");
    const preferred=preferredTabId??preferredMuseTabId;
    if(preferred){const index=tabs.findIndex(tab=>tab.id===preferred);if(index>0)tabs.unshift(tabs.splice(index,1)[0]);}
    let lastError='';
    for(const tab of tabs){
      if(signal?.aborted)throw new DOMException("用户已停止生成。",'AbortError');
      if(!tab.id)continue;
      try{const response=await sendMuseTabMessage(tab.id,message,signal);preferredMuseTabId=tab.id;return response;}catch(error){if(error?.name==='AbortError')throw error;lastError=error?.message||String(error);}
      try{
        await chrome.scripting.executeScript({target:{tabId:tab.id},files:['muse-bridge.js']});
        const response=await sendMuseTabMessage(tab.id,message,signal);preferredMuseTabId=tab.id;return response;
      }catch(error){if(error?.name==='AbortError')throw error;lastError=error?.message||String(error);}
    }
    throw new Error(`已找到 Muse 标签页，但 MuseFlow 无法连接页面桥接脚本：${lastError||"未知浏览器错误"}。请在浏览器扩展设置中检查 Muse 网站访问权限，然后重试。`);
  }

  function sendMuseTabMessage(tabId,message,signal){
    if(!signal)return chrome.tabs.sendMessage(tabId,message);
    if(signal.aborted)return Promise.reject(new DOMException("用户已停止生成。",'AbortError'));
    return new Promise((resolve,reject)=>{
      let settled=false;
      const finish=(fn,value)=>{if(settled)return;settled=true;signal.removeEventListener('abort',onAbort);fn(value);};
      const onAbort=()=>finish(reject,new DOMException("用户已停止生成。",'AbortError'));
      signal.addEventListener('abort',onAbort,{once:true});
      chrome.tabs.sendMessage(tabId,message).then(value=>finish(resolve,value),error=>finish(reject,error));
    });
  }

  function stopGeneration(nodeId=state.activeGenerationId){
    if(!nodeId)return;
    const node=nodeById(nodeId);
    if(!node||node.data.status!=='running')return;
    const requestId=state.activeGenerationId===nodeId?state.generationRequestId:null;
    if(state.activeGenerationId===nodeId)state.generationAbortController?.abort();
    if(node){node.data.status='stopped';node.data.error="用户已停止生成。";}
    setRunStatus(`已停止 ${node?.type==='generateVideo'?'视频':'图片'}生成：${nodeId}`,'warn');
    render();
    // Cancellation is best-effort for Muse, but never wait for its response to unlock the UI.
    void sendMuseStop(requestId);
    try{clearTimeout(autoSaveTimer);void queueWorkflowSave();}catch{}
  }

  async function sendMuseStop(requestId){
    try{
      const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
      const ordered=preferredMuseTabId?tabs.sort((a,b)=>(b.id===preferredMuseTabId)-(a.id===preferredMuseTabId)):tabs;
      await Promise.allSettled(ordered.filter(tab=>tab.id).map(tab=>chrome.tabs.sendMessage(tab.id,{type:'MUSEFLOW_STOP_GENERATION',requestId})));
    }catch{}
  }

  async function testMuseSession(preferredTabId) {
    const button=$('#testMuseBtn'),status=$('#connectionStatus');
    if(button)button.disabled=true;
    status.className='warn';status.textContent="正在检查 Muse 会话…";
    try{
      const result=await museTabMessage({type:'MUSEFLOW_CHECK_SESSION'},preferredTabId);
      const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
      const checked=tabs.find(tab=>tab.id===preferredTabId)||tabs.find(tab=>tab.active)||tabs[0];
      if(checked?.id)preferredMuseTabId=checked.id;
      const ready=Boolean(result.composer&&result.signedIn);
      status.className=ready?'ok':'warn';
      status.textContent=ready?"Muse 会话已连接。":result.loginRequired?"Muse 要求登录。请在 Muse 标签页登录后重新检查。":result.composer?"Muse 聊天已就绪，暂时无法确认会话状态；可以尝试生成。":"已找到 Muse 标签页，但聊天输入框尚未就绪。请打开 Muse 聊天后重试。";
      museStatus.textContent=ready?"● Muse 会话已就绪":"● 请检查 Muse 会话";
      museStatus.className=ready?'ok':result.loginRequired?'warn':'ok';
      if(!ready&&!result.loginRequired){museStatus.textContent="● Muse 聊天已就绪 · 会话未确认";}
      return ready||Boolean(result.composer&&!result.loginRequired);
    }catch(error){
      status.className='error';status.textContent=error.message;
      museStatus.textContent="● Muse 会话检查失败";museStatus.className='error';
      return false;
    }finally{if(button)button.disabled=false;}
  }

  async function execute(targetId=null,{forceAll=false}={}) {
    if(state.isRunning)return;
    // Keep runtime graph references valid even if an older saved workflow or
    // an interrupted UI action left stale node IDs behind.
    normalizeSavedGraph();
    // A persisted "running" flag can survive a tab reload even though the old
    // request no longer exists. Normalize it before starting a fresh run.
    for(const node of state.nodes)if(['generateImage','generateVideo'].includes(node.type)&&node.data.status==='running'){
      node.data.status=node.data.asset?.url?'success':'idle';
      if(node.data.status==='idle')node.data.error="上次运行被中断，可以重试。";
    }
    const targetSet=targetId?(Array.isArray(targetId)||targetId instanceof Set?new Set(targetId):new Set([targetId])):null;
    const abortController=new AbortController();state.generationAbortController=abortController;state.activeGenerationId=targetSet?[...targetSet][0]:null;state.isRunning=true;$('#runBtn').disabled=false;$('#runBtn').textContent="■ 停止";
    setRunStatus(targetSet?(targetSet.size===1?`正在运行所选节点：${[...targetSet][0]}…`:`正在运行 ${targetSet.size} 个所选节点…`):forceAll?"正在全量重新运行工作流…":"正在智能运行工作流（跳过未变更节点）…",'warn');
    try{
      if(targetSet){for(const tid of targetSet)validateTargetPrompt(tid);}
      const order=targetSet?requiredNodesFor(targetSet):topoOrder();
      for(const n of state.nodes){
        if(n.type==='imageInput'&&n.data.localDataUrl)n.data.asset={id:n.data.asset?.id||uid('asset'),kind:'image',url:n.data.localDataUrl,sourceNodeId:n.id};
      }
      const nodesToGenerate=[];
      let skippedCount=0;
      for(const id of order){
        const n=nodeById(id);
        if(!n||!['generateImage','generateVideo'].includes(n.type))continue;
        const isTarget=targetSet?targetSet.has(n.id):false;
        const hasAsset=Boolean(n.data.asset?.url);
        const isSuccess=n.data.status==='success';
        const isDirty=Boolean(n.data.dirty);
        let shouldRun=false;
        if(isTarget)shouldRun=true;
        else if(targetSet)shouldRun=!hasAsset;
        else if(forceAll)shouldRun=true;
        else shouldRun=!hasAsset||!isSuccess||isDirty;
        if(shouldRun)nodesToGenerate.push(n.id);
        else{
          skippedCount++;
          if(n.type==='generateVideo'&&n.data.asset?.url&&!n.data.endFrame){
            try{n.data.endFrame=await extractVideoEndFrame(n.data.asset.url);}catch{}
          }
        }
      }
      if(nodesToGenerate.length===0){
        setRunStatus(skippedCount>0?`所有 ${skippedCount} 个生成节点均已完成且未变更，已跳过。`:"没有需要生成的节点。",'ok');
        return;
      }
      let generationStep=0;
      const totalGenerations=nodesToGenerate.length;
      const succeededNodes=[];
      const failedNodes=[];
      const skippedDependencyNodes=[];
      for(const id of order){
        if(abortController.signal.aborted)throw new DOMException("用户已停止生成。",'AbortError');
        const n=nodeById(id); if(!n)continue;
        if(n.type==='imageResize'){
          const source=sourceFor(getIncoming(n.id,'image')[0]);const url=source?.data?.localDataUrl||source?.data?.asset?.url;
          if(!url){setRunStatus("“调整图片尺寸”节点正在等待输入图片。",'warn');continue;}
          const image=await loadImage(url),canvas=document.createElement('canvas');drawResized(image,canvas,n.data);
          const resized=canvas.toDataURL('image/png');n.data.asset={id:uid('asset'),kind:'image',url:resized,name:`已调整尺寸：${n.data.width}×${n.data.height}`,width:canvas.width,height:canvas.height,sourceNodeId:n.id};
          state.edges.filter(e=>e.source===n.id).forEach(e=>{const target=nodeById(e.target);if(target?.type==='preview')target.data.asset=n.data.asset;});render();continue;
        }
        if(['generateImage','generateVideo'].includes(n.type)){
          if(!nodesToGenerate.includes(n.id))continue;
          const isVideo=n.type==='generateVideo';
          generationStep++;
          const prompt=resolvePrompt(n.id);
          if(!String(prompt).trim()){
            n.data.status='error';
            n.data.error=`${nodeDefs[n.type].title} ${n.id}：请先连接提示词或文本节点。`;
            failedNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
            render();
            if(targetSet&&targetSet.size===1)throw new Error(n.data.error);
            setRunStatus(`节点 ${n.id} 未配置提示词，已跳过；正在继续推进后续节点…`,'warn');
            continue;
          }
          const negativePrompt=resolveNegativePrompt(n.id);
          const continuityPrevious=isVideo&&n.data.continuity?timelinePredecessor(n.id):null;
          let continuityStartFrame=continuityPrevious?.data?.endFrame?.url?continuityPrevious.data.endFrame:null;
          if(isVideo&&n.data.continuity&&!continuityStartFrame&&continuityPrevious?.data?.asset?.url){
            try{continuityPrevious.data.endFrame=await extractVideoEndFrame(continuityPrevious.data.asset.url);continuityStartFrame=continuityPrevious.data.endFrame;}catch{}
          }
          if(isVideo&&n.data.continuity&&!continuityStartFrame){
            n.data.status='error';
            n.data.error=`尾帧连续生成依赖前置片段 (${continuityPrevious?.id||'上个视频'}) 成功生成尾帧。请先成功生成前置片段。`;
            skippedDependencyNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
            render();
            if(targetSet&&targetSet.size===1)throw new Error(n.data.error);
            setRunStatus(`节点 ${n.id} 跳过：等待前置片段生成完成。正在推进后续独立节点…`,'warn');
            continue;
          }
          const referenceImages=resolveReferences(n.id);
          state.activeGenerationId=n.id;n.data.status='running';n.data.error='';n.data.asset=null;n.data.endFrame=null;state.edges.filter(edge=>edge.source===n.id).forEach(edge=>{const target=nodeById(edge.target);if(target?.type==='preview')target.data.asset=null;});render();
          const skipHint=skippedCount>0?` (跳过 ${skippedCount} 项)`:'';
          setRunStatus(`${targetSet?"所选节点":`生成 ${generationStep}/${totalGenerations}${skipHint}`} · 正在生成 ${isVideo?'video':'image'}: ${n.id}`,'warn');
          try{
            const sizeInstruction=`Output aspect ratio: ${n.data.size}. Match this frame shape exactly. ${n.data.size==='16:9'?'Use a wide landscape composition.':n.data.size==='9:16'?'Use a tall portrait composition.':n.data.size==='1:1'?'Use a square composition.':n.data.size==='4:3'?'Use a standard landscape composition.':'Use a standard portrait composition.'}`;
            const continuityInstruction=continuityStartFrame?'CONTINUITY LOCK: Attached image 1 is the exact final frame of the previous Timeline clip. Use image 1 as the exact first frame of this video: preserve its subject identity, pose, position, camera angle, crop, lighting, and background. Continue motion naturally from that precise moment. No reset, jump, flash, dissolve, or scene change at the start.':'';
            const audioRequirement=isVideo?'AUDIO IS REQUIRED: Return a video with audible, synchronized sound; do not make a silent clip. Follow the requested audio direction and make its music and sound effects clearly audible. Do not add spoken dialogue unless the prompt asks for it.':'';
            const modelDirective=(!isVideo&&n.data.model&&n.data.model!=='muse-image')?`\n\n[Model: ${n.data.model}] Use ${n.data.model} model.`:'';
            const musePrompt=isVideo?`Create a ${n.data.size} aspect ratio video clip, ${n.data.duration} seconds long. ${sizeInstruction}\n\n${audioRequirement}${continuityInstruction?`\n\n${continuityInstruction}`:''}${referenceImages.length?`\n\nUse the attached reference image${referenceImages.length===1?'':'s'} as visual guidance${continuityStartFrame?' while keeping image 1 as the exact opening frame.':'.'}`:''}\n\nPrompt: ${prompt}${negativePrompt?`\n\nAvoid: ${negativePrompt}`:''}`:`${prompt}${referenceImages.length?'\n\nUse the attached reference image'+(referenceImages.length===1?'':'s')+' as visual guidance; follow the prompt while preserving relevant subject details.':''}\n\n${sizeInstruction}${negativePrompt?`\n\nAvoid the following (negative prompt): ${negativePrompt}`:''}${modelDirective}`;
            const generationRequest={type:'MUSEFLOW_GENERATE',requestId:uid('generation'),prompt:musePrompt,negativePrompt,size:n.data.size,model:n.data.model||'muse-image',duration:n.data.duration,mediaType:isVideo?'video':'image',referenceImages:referenceImages.map(item=>item.url),timeoutSec:300};state.generationRequestId=generationRequest.requestId;
            let reply=await museTabMessage(generationRequest,preferredMuseTabId,abortController.signal);
            if(abortController.signal.aborted)throw new DOMException("用户已停止生成。",'AbortError');
            if(!reply?.ok&&reply?.code==='SCENE_REFUSED'){
              setRunStatus(`Muse 无法生成 ${n.data.sceneLabel||"此场景"}；正在使用接近原意且符合要求的方案重试一次…`,'warn');
              const retryRequest={...generationRequest,prompt:`${musePrompt}\n\nSAFE EQUIVALENT RETRY: The previous version could not be generated. Create a close, allowed alternative for the same scene now. Stay faithful to the script's story purpose, characters, relationship, setting, action, mood, visual style, framing, continuity, and requested duration/aspect ratio. Change only the specific detail that prevents generation, replacing it with the nearest safe equivalent. Keep this scene in the story; do not skip it or change what it needs to accomplish. Do not ask a follow-up question or ask permission; generate the alternative in this attempt. Follow all content and safety rules.`};
              reply=await museTabMessage(retryRequest,preferredMuseTabId,abortController.signal);
            }
            if(abortController.signal.aborted)throw new DOMException("用户已停止生成。",'AbortError');
            if(!reply?.ok)throw new Error(reply?.error||`Muse.ai 未返回生成的${isVideo?'video':'image'}.`);
            const kind=isVideo?'video':'image';
            const url=isVideo?reply.url:await persistImage(reply.url);
            if(!url)throw new Error(`Muse.ai 返回了空的${mediaText(kind)}附件。`);
            const intrinsic=await mediaDimensions(url,isVideo?'video':'image');
            const actualRatio=intrinsic.width&&intrinsic.height?intrinsic.width/intrinsic.height:0;
            const expectedRatio=ratioValue(n.data.size);
            const sizeMismatch=actualRatio&&Math.abs(Math.log(actualRatio/expectedRatio))>0.09;
            if(sizeMismatch)throw new Error(`Muse 返回的尺寸为 ${intrinsic.width} × ${intrinsic.height}，与请求的 ${n.data.size}宽高比不符。旧结果已清除；请检查 Muse 输出后重新生成。`);
            n.data.asset={id:uid('asset'),kind,url,name:`${isVideo?"视频":"图片"} ${n.id}`,sourceNodeId:n.id,width:intrinsic.width,height:intrinsic.height,requestedSize:n.data.size,sizeMismatch}; n.data.status='success';
            n.data.dirty=false;
            succeededNodes.push(n.id);
            if(isVideo)n.data.endFrame=await extractVideoEndFrame(url);
            if(sizeMismatch)n.data.error=`请求比例：${n.data.size}，收到：${intrinsic.width}×${intrinsic.height}. Muse returned a different aspect ratio.`;
            state.edges.filter(e=>e.source===n.id).forEach(e=>{const target=nodeById(e.target);if(target?.type==='preview')target.data.asset=e.sourcePort==='endFrame'?n.data.endFrame:n.data.asset;});render();
          }catch(err){
            if(err?.name==='AbortError'||abortController.signal.aborted){
              n.data.status='stopped';n.data.error="用户已停止生成。";render();
              throw new DOMException("用户已停止生成。",'AbortError');
            }
            n.data.status='error';
            n.data.error=err?.message||String(err);
            failedNodes.push({ id: n.id, title: nodeDefs[n.type].title, error: n.data.error });
            render();
            if(targetSet&&targetSet.size===1)throw err;
            setRunStatus(`节点 ${n.id} 生成失败：${n.data.error}。正在继续推进后续独立节点…`,'warn');
          }
        }
      }
      try{
        clearTimeout(autoSaveTimer);
        await queueWorkflowSave();
        if(failedNodes.length>0||skippedDependencyNodes.length>0){
          const parts=[];
          if(succeededNodes.length>0)parts.push(`成功 ${succeededNodes.length} 项`);
          if(failedNodes.length>0)parts.push(`失败 ${failedNodes.length} 项`);
          if(skippedDependencyNodes.length>0)parts.push(`因依赖跳过 ${skippedDependencyNodes.length} 项`);
          if(skippedCount>0)parts.push(`跳过未变更 ${skippedCount} 项`);
          setRunStatus(`工作流运行完成（${parts.join('，')}）。可点击或右键标红节点单独重试。`,'warn');
        }else{
          const finishMsg=targetSet?(targetSet.size===1?`节点 ${[...targetSet][0]} 生成完成。`:`${totalGenerations} 个所选节点生成完成。`):(skippedCount>0?`工作流运行完成（已生成 ${totalGenerations} 项，跳过 ${skippedCount} 个未变更项）。`:"工作流运行完成。");
          setRunStatus(finishMsg,'ok');
        }
      }catch(saveError){setRunStatus(`生成已完成，但工作流保存失败：${saveError?.message||String(saveError)}`,'warn');}
    }catch(err){
      if(err?.name==='AbortError'||abortController.signal.aborted){
        const active=state.nodes.find(n=>n.id===state.activeGenerationId);
        if(active&&active.data.status==='running'){active.data.status='stopped';active.data.error="用户已停止生成。";render();}
        try{clearTimeout(autoSaveTimer);await queueWorkflowSave();}catch{}
        return;
      }
      const failed=state.nodes.find(n=>['generateImage','generateVideo'].includes(n.type)&&n.data.status==='running');
      if(failed){failed.data.status='error';failed.data.error=err?.message||String(err);render();}
      const message=err?.message||String(err);
      setRunStatus(/failed to fetch/i.test(message)?"Muse 连接失败。请重新加载 MuseFlow 0.5.0，然后检查 Muse 会话。":'MuseFlow 0.5.0 · '+message,'error');
      try{clearTimeout(autoSaveTimer);await queueWorkflowSave();}catch(saveError){setRunStatus(`${runStatus.textContent} · 自动保存失败：${saveError?.message||String(saveError)}`,'error');}
    }
    finally{state.isRunning=false;state.activeGenerationId=null;state.generationAbortController=null;state.generationRequestId=null;$('#runBtn').disabled=false;$('#runBtn').textContent="▶ 运行";render();}
  }

  function runSingleNode(nodeId){const node=nodeById(nodeId);if(!node||!['generateImage','generateVideo'].includes(node.type))return;if(node.data.status==='running'){stopGeneration(nodeId);return;}execute(nodeId);}
  function onWorkflowRunButtonClick(event){if(event.detail>1)return;if(state.isRunning)stopGeneration(state.activeGenerationId);else execute(null,{forceAll:false});}
  function onWorkflowRunAllButtonClick(event){if(event.detail>1)return;if(state.isRunning)stopGeneration(state.activeGenerationId);else execute(null,{forceAll:true});}

  function setRunStatus(text, cls=''){runStatus.className=cls;runStatus.textContent=text;}

  function ratioValue(size){const [w,h]=String(size||'1:1').split(':').map(Number);return w>0&&h>0?w/h:1;}

  function clampDimension(value){return Math.max(1,Math.min(4096,Math.round(Number(value)||1)));}

  function loadImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error("无法加载相连的图片以调整尺寸。"));image.src=url;});}

  function drawResized(image,canvas,data={}){
    const width=clampDimension(data.width||1024),height=clampDimension(data.height||1024);canvas.width=width;canvas.height=height;
    const context=canvas.getContext('2d');if(!context)return;context.fillStyle='#101116';context.fillRect(0,0,width,height);
    const fit=data.fit||'cover';let scale=fit==='stretch'?null:fit==='contain'?Math.min(width/image.naturalWidth,height/image.naturalHeight):Math.max(width/image.naturalWidth,height/image.naturalHeight);
    const drawWidth=scale===null?width:image.naturalWidth*scale,drawHeight=scale===null?height:image.naturalHeight*scale;
    context.drawImage(image,(width-drawWidth)/2,(height-drawHeight)/2,drawWidth,drawHeight);
  }

  async function mediaDimensions(url,kind){
    if(kind==='image')return new Promise(resolve=>{const image=new Image();image.onload=()=>resolve({width:image.naturalWidth,height:image.naturalHeight});image.onerror=()=>resolve({width:0,height:0});image.src=url;});
    return new Promise(resolve=>{const video=document.createElement('video');video.preload='metadata';video.onloadedmetadata=()=>resolve({width:video.videoWidth,height:video.videoHeight});video.onerror=()=>resolve({width:0,height:0});video.src=url;});
  }

  function extractVideoEndFrame(url){return new Promise(resolve=>{const video=document.createElement('video');if(/^https?:/i.test(url))video.crossOrigin='anonymous';video.preload='auto';video.muted=true;video.playsInline=true;let finished=false;const done=value=>{if(finished)return;finished=true;video.removeAttribute('src');video.load();resolve(value);};const timer=setTimeout(()=>done(null),12000);video.onloadedmetadata=()=>{if(!Number.isFinite(video.duration)){clearTimeout(timer);done(null);return;}video.currentTime=Math.max(0,video.duration-Math.min(.04,video.duration/100));};video.onseeked=()=>{try{const width=video.videoWidth,height=video.videoHeight;if(!width||!height){clearTimeout(timer);done(null);return;}const frame=document.createElement('canvas');frame.width=width;frame.height=height;frame.getContext('2d').drawImage(video,0,0,width,height);const dataUrl=frame.toDataURL('image/png');clearTimeout(timer);done({id:uid('endframe'),kind:'image',url:dataUrl,name:"视频尾帧",width,height});}catch{clearTimeout(timer);done(null);}};video.onerror=()=>{clearTimeout(timer);done(null);};video.src=url;video.load();});}

  async function persistImage(url) {
    if(!url)return '';
    if(url.startsWith('data:'))return url;
    try{
      const response=await fetch(url,{credentials:'include'});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const blob=await response.blob();
      if(blob.size>8*1024*1024)return url;
      return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(reader.error);reader.readAsDataURL(blob);});
    }catch{return url;}
  }

  let mediaDbPromise;
  function mediaDb(){if(!mediaDbPromise)mediaDbPromise=new Promise((resolve,reject)=>{const request=indexedDB.open('museflow-media',1);request.onupgradeneeded=()=>request.result.createObjectStore('assets');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error||new Error("无法打开本地媒体存储。"));});return mediaDbPromise;}
  async function putMedia(key,blob){const db=await mediaDb();return new Promise((resolve,reject)=>{const tx=db.transaction('assets','readwrite');tx.objectStore('assets').put(blob,key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error||new Error("无法在本地保存媒体文件。"));tx.onabort=()=>reject(tx.error||new Error("媒体存储事务已取消。"));});}
  async function getMedia(key){const db=await mediaDb();return new Promise((resolve,reject)=>{const request=db.transaction('assets','readonly').objectStore('assets').get(key);request.onsuccess=()=>resolve(request.result||null);request.onerror=()=>reject(request.error||new Error("无法读取已保存的媒体文件。"));});}
  const idbMediaPrefix='museflow-idb:';
  async function dehydrateMediaUrl(url,key){if(!url||url.startsWith(idbMediaPrefix)||!(/^(?:data:|blob:)/i).test(url))return url;const response=await fetch(url);const blob=await response.blob();if(!blob.size)throw new Error("已保存的图片或视频为空。");await putMedia(key,blob);return idbMediaPrefix+encodeURIComponent(key);}
  let autoSaveTimer=0,workflowSaveQueue=Promise.resolve();
  async function saveWorkflowSnapshot(){const snapshot=structuredClone({nodes:state.nodes,edges:state.edges,settings:state.settings});for(const node of snapshot.nodes){const data=node.data||{};if(data.localDataUrl)data.localDataUrl=await dehydrateMediaUrl(data.localDataUrl,`input:${node.id}`);for(const field of ['asset','endFrame']){const media=data[field];if(media?.url)media.url=await dehydrateMediaUrl(media.url,`${field}:${media.id||node.id}`);}}await chrome.storage.local.set({museflow:snapshot});}
  function queueWorkflowSave(){workflowSaveQueue=workflowSaveQueue.catch(()=>{}).then(saveWorkflowSnapshot);return workflowSaveQueue;}
  function scheduleAutoSave(){clearTimeout(autoSaveTimer);autoSaveTimer=setTimeout(()=>{queueWorkflowSave().catch(error=>{if(runStatus.className!=='error')setRunStatus(`自动保存失败：${error?.message||String(error)}`,'error');});},650);}
  async function hydrateMediaUrl(url,cache){if(!url?.startsWith(idbMediaPrefix))return url;const key=decodeURIComponent(url.slice(idbMediaPrefix.length));if(!cache.has(key)){const blob=await getMedia(key);cache.set(key,blob?URL.createObjectURL(blob):'');}return cache.get(key);}
  async function hydrateWorkflowMedia(){const cache=new Map();for(const node of state.nodes){const data=node.data||{};if(data.localDataUrl)data.localDataUrl=await hydrateMediaUrl(data.localDataUrl,cache);for(const field of ['asset','endFrame'])if(data[field]?.url)data[field].url=await hydrateMediaUrl(data[field].url,cache);}}
  async function saveState(){clearTimeout(autoSaveTimer);try{await queueWorkflowSave();setRunStatus('已保存。','ok');}catch(error){setRunStatus(`无法保存工作流：${error?.message||String(error)}`,'error');}}
  function blobAsDataUrl(blob){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(reader.error||new Error("无法打包工作流媒体。"));reader.readAsDataURL(blob);});}
  async function exportWorkflowFile(){
    const button=$('#workflowExportBtn');button.disabled=true;
    try{
      const workflow=structuredClone({nodes:state.nodes,edges:state.edges,settings:state.settings});let externalMedia=0;
      const packageUrl=async url=>{
        if(!url||url.startsWith('data:'))return url;
        try{
          let blob;
          if(url.startsWith(idbMediaPrefix))blob=await getMedia(decodeURIComponent(url.slice(idbMediaPrefix.length)));
          else if(/^(?:blob:|https?:)/i.test(url)){const response=await fetch(url,{credentials:'include'});if(!response.ok)throw new Error(`HTTP ${response.status}`);blob=await response.blob();}
          else return url;
          if(!blob?.size)throw new Error("媒体缺失或内容为空");
          return await blobAsDataUrl(blob);
        }catch{externalMedia++;return url;}
      };
      for(const node of workflow.nodes){const data=node.data||{};if(data.localDataUrl)data.localDataUrl=await packageUrl(data.localDataUrl);for(const field of ['asset','endFrame'])if(data[field]?.url)data[field].url=await packageUrl(data[field].url);}
      const file={format:'26flow-workflow',version:1,appVersion:'0.5.0',exportedAt:new Date().toISOString(),workflow};
      const blob=new Blob([JSON.stringify(file)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`26MuseFlow-Workflow-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
      setRunStatus(externalMedia?`工作流已保存；${externalMedia}个媒体链接未能嵌入文件，可能需要原 Muse 会话才能访问。`:"工作流已保存，包含媒体文件。",'ok');
    }catch(error){setRunStatus(`无法保存工作流文件：${error?.message||String(error)}`,'error');}
    finally{button.disabled=false;}
  }
  async function importWorkflowFile(file){
    if(!file)return;if(state.isRunning){setRunStatus("导入其他工作流前，请先停止当前工作流。",'warn');return;}
    let parsed,workflow;
    try{parsed=JSON.parse(await file.text());workflow=parsed?.format==='26flow-workflow'?parsed.workflow:parsed;if(!workflow||!Array.isArray(workflow.nodes)||!Array.isArray(workflow.edges))throw new Error("此文件不是有效的 MuseFlow 工作流。");}
    catch(error){setRunStatus(`无法导入工作流：${error?.message||String(error)}`,'error');return;}
    if(!window.confirm("导入此工作流会替换当前画布，是否继续？"))return;
    const previous={nodes:state.nodes,edges:state.edges,settings:state.settings};
    try{
      state.nodes=workflow.nodes;state.edges=workflow.edges;state.settings=workflow.settings&&typeof workflow.settings==='object'?workflow.settings:{};
      await hydrateWorkflowMedia();normalizeSavedGraph();state.selectedNodeIds=[];state.selectedNodeId=null;state.selectedEdgeIds=[];syncSettingsUI();render();await queueWorkflowSave();
      setRunStatus(`工作流已导入：${file.name}`,'ok');
    }catch(error){state.nodes=previous.nodes;state.edges=previous.edges;state.settings=previous.settings;render();setRunStatus(`无法导入工作流：${error?.message||String(error)}`,'error');}
  }
  async function loadState(){try{const got=await chrome.storage.local.get('museflow');if(got.museflow){state.nodes=Array.isArray(got.museflow.nodes)?got.museflow.nodes:[];state.edges=Array.isArray(got.museflow.edges)?got.museflow.edges:[];state.settings=got.museflow.settings||{};if(!state.nodes.length){const s=starter();state.nodes=s.nodes;state.edges=s.edges;}}else{const s=starter();state.nodes=s.nodes;state.edges=s.edges;}await hydrateWorkflowMedia();}catch(error){const s=starter();state.nodes=s.nodes;state.edges=s.edges;setRunStatus(`无法加载已保存的工作流：${error.message}`,'error');}normalizeSavedGraph();syncSettingsUI();
    render();syncTimelineDock();try{clearTimeout(autoSaveTimer);await queueWorkflowSave();}catch(error){setRunStatus(`工作流已打开，但媒体迁移失败：${error?.message||String(error)}`,'warn');}}
  async function resetState(){if(state.isRunning)return;const s=starter();state.nodes=s.nodes;state.edges=s.edges;state.selectedNodeIds=[];state.selectedNodeId=null;render();await saveState();}
  function syncSettingsUI(){
    backendStatus.textContent="Muse 会话 · v0.5.0 中文版";
    const defaultSelect=$('#defaultImageModelSelect');
    if(defaultSelect){
      defaultSelect.innerHTML='';
      const models=getAvailableImageModels();
      models.forEach(m=>{
        const opt=document.createElement('option');
        opt.value=m.id;
        opt.textContent=m.name;
        defaultSelect.appendChild(opt);
      });
      defaultSelect.value=state.settings?.defaultImageModel||'muse-image';
    }
    const chipsContainer=$('#customModelsList');
    if(chipsContainer){
      chipsContainer.innerHTML='';
      const custom=Array.isArray(state.settings?.customImageModels)?state.settings.customImageModels:[];
      if(custom.length===0){
        const empty=document.createElement('span');empty.className='empty-chips-hint';empty.textContent="暂无自定义模型（可通过上方输入框添加，或在生成节点中输入）";chipsContainer.appendChild(empty);
      }else{
        custom.forEach(name=>{
          const chip=document.createElement('span');chip.className='model-chip';chip.textContent=name;
          const delBtn=document.createElement('button');delBtn.type='button';delBtn.textContent='×';delBtn.title=`删除模型 ${name}`;
          delBtn.onclick=e=>{e.stopPropagation();removeCustomImageModel(name);syncSettingsUI();render();};
          chip.appendChild(delBtn);chipsContainer.appendChild(chip);
        });
      }
    }
  }

  async function detectMuse(){
    try{
      const tabs=await chrome.tabs.query({url:['https://muse.ai/*','https://*.muse.ai/*']});
      if(tabs.length){const active=tabs.find(t=>t.active)||tabs[0];await testMuseSession(active.id);}
      else{museStatus.textContent="● 请打开 muse.ai 并登录";museStatus.className='warn';}
    }catch{museStatus.textContent="● 暂时无法检查 Muse 会话";museStatus.className='warn';}
  }

  document.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>addNode(b.dataset.add));
  $('#scriptImportBtn').onclick=()=>{$('#scriptModal').classList.remove('hidden');$('#scriptImportStatus').textContent='';$('#scriptInput').focus();};
  $('#cancelScriptImport').onclick=()=>$('#scriptModal').classList.add('hidden');
  $('#buildScriptNodes').onclick=buildSceneNodesFromScript;
  $('#scriptModal').onclick=event=>{if(event.target.id==='scriptModal')$('#scriptModal').classList.add('hidden');};
  $('#scriptInput').addEventListener('input',()=>{
    const scenes=parseSceneScript($('#scriptInput').value);
    const count=scenes.length;
    $('#scriptImportStatus').className='';
    $('#scriptImportStatus').textContent=count?`${count} 个场景已识别。`:'';
    const previewContainer = $('#scriptPreviewContainer');
    if (previewContainer) {
      if (count > 0) {
        previewContainer.classList.remove('hidden');
        previewContainer.innerHTML = `
          <table style="width:100%; border-collapse:collapse; font-size:11px; background:#0f172a; border:1px solid #334155; border-radius:4px;">
            <thead>
              <tr style="border-bottom:1px solid #334155; color:#94a3b8; text-align:left; background:#1e293b;">
                <th style="padding:4px 6px;">#</th>
                <th style="padding:4px 6px;">场景标题</th>
                <th style="padding:4px 6px;">目标时长</th>
                <th style="padding:4px 6px;">分镜提示词概览</th>
              </tr>
            </thead>
            <tbody>
              ${scenes.map(s => `
                <tr style="border-bottom:1px solid #1e293b;">
                  <td style="padding:4px 6px; color:#38bdf8; font-weight:600;">${s.number}</td>
                  <td style="padding:4px 6px; font-weight:600;">${escapeHtml(s.title)}</td>
                  <td style="padding:4px 6px; color:#a3e635;">${s.seconds}s</td>
                  <td style="padding:4px 6px; color:#cbd5e1; max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(s.videoPrompt || s.imagePrompt)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      } else {
        previewContainer.classList.add('hidden');
        previewContainer.innerHTML = '';
      }
    }
  });
  $('#timelineToggleBtn').onclick=toggleTimeline;
  $('#timelineExportBtn').onclick=exportTimelineVideo;
  $('#timelineImportAllBtn').onclick=importAllVideosToTimeline;
  $('#closeTimelinePreview').onclick=closeTimelinePreview;
  $('#timelineAddVideoBtn').onclick=toggleTimelineOutputMenu;
  $('#timelinePlayBtn').onclick=()=>playTimeline(ensureDockTimeline());
  // A DOM click handler receives the MouseEvent as its first argument. Keep
  // the workflow Run button separate from execute(targetNodeId), which accepts
  // an optional node ID when invoked from a node's own Run button.
  $('#runBtn').onclick=onWorkflowRunButtonClick;
  const runAllBtn=$('#runAllBtn');if(runAllBtn)runAllBtn.onclick=onWorkflowRunAllButtonClick;
  $('#saveBtn').onclick=saveState; $('#resetBtn').onclick=resetState;
  $('#workflowExportBtn').onclick=exportWorkflowFile;
  $('#workflowImportBtn').onclick=()=>$('#workflowFileInput').click();
  $('#workflowFileInput').onchange=event=>{const file=event.target.files?.[0];event.target.value='';if(file)void importWorkflowFile(file);};
  $('#settingsBtn').onclick=()=>{syncSettingsUI();$('#settingsModal').classList.remove('hidden');};
  $('#testMuseBtn').onclick=()=>testMuseSession();
  $('#closeSettingsBtn').onclick=()=>$('#settingsModal').classList.add('hidden');
  $('#saveSettingsBtn').onclick=async()=>{
    state.settings=state.settings||{};
    const defaultSelect=$('#defaultImageModelSelect');
    if(defaultSelect)state.settings.defaultImageModel=defaultSelect.value;
    $('#settingsModal').classList.add('hidden');
    await saveState();
    render();
  };
  const addCustomBtn=$('#addCustomModelBtn');
  if(addCustomBtn){
    addCustomBtn.onclick=()=>{
      const inp=$('#customModelInput');
      const val=inp?.value?.trim();
      if(val){
        addCustomImageModel(val);
        inp.value='';
        syncSettingsUI();
        render();
      }
    };
  }
  $('#settingsModal').onclick=(e)=>{if(e.target.id==='settingsModal')$('#settingsModal').classList.add('hidden');};
  window.addEventListener('resize',drawEdges);
  window.addEventListener('pointermove',onWireMove);
  window.addEventListener('pointermove',moveSelectionMarquee);
  window.addEventListener('pointerup',onWireUp);
  window.addEventListener('pointerup',endSelectionMarquee);
  window.addEventListener('pointercancel',endSelectionMarquee);
  $('#viewport').addEventListener('wheel',event=>{event.preventDefault();const factor=Math.exp(-event.deltaY*.0015);zoomAt(event.clientX,event.clientY,factor);},{passive:false});
  $('#viewport').addEventListener('pointerdown',event=>{const panGesture=event.button===1||state.spaceDown||state.handMode;if(panGesture&&!event.target.closest('button,input,label,textarea,select,video,a,.canvas-tools'))startPan(event);});
  $('#viewport').addEventListener('pointerdown',startSelectionMarquee);
  document.addEventListener('pointerdown',event=>{const stop=event.target.closest('[data-stop-generation]');if(!stop)return;if(event.pointerType==='mouse'&&event.detail>1)return;event.preventDefault();event.stopImmediatePropagation();stopGeneration(stop.dataset.stopGeneration);},true);
  window.addEventListener('pointermove',movePan);window.addEventListener('pointerup',endPan);window.addEventListener('pointercancel',endPan);
  $('#handTool').onclick=()=>{state.handMode=!state.handMode;applyCanvasTransform();$('#handTool').classList.toggle('active',state.handMode);};
  $('#zoomIn').onclick=()=>setZoom(Math.min(2.5,state.zoom*1.15));$('#zoomOut').onclick=()=>setZoom(Math.max(.25,state.zoom/1.15));$('#fitCanvas').onclick=fitCanvas;
  $('#viewport').addEventListener('contextmenu',openCanvasMenu);
  document.addEventListener('input',event=>{if(event.target.closest('.node,.timeline-dock,#settingsModal'))scheduleAutoSave();},true);
  document.addEventListener('change',event=>{if(event.target.closest('.node,.timeline-dock,#settingsModal'))scheduleAutoSave();},true);
  $('#canvasMenu').addEventListener('click',e=>{const item=e.target.closest('[data-context-action]');if(!item)return;if(item.dataset.contextAction==='connect-choice')runConnectionChoice(Number(item.dataset.choice));else runCanvasAction(item.dataset.contextAction);});
  edgesSvg.addEventListener('contextmenu',openEdgeMenu);
  edgesSvg.addEventListener('pointerdown',selectEdgePointer);
  canvas.addEventListener('contextmenu',openCanvasMenu);
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('#canvasMenu')){closeCanvasMenu();state.pendingConnection=null;}});
  const isTextEntry=target=>Boolean(target?.closest?.('textarea,input,select,[contenteditable="true"]'));
  document.addEventListener('keydown',e=>{
    if(e.code==='Space'&&!isTextEntry(e.target)){
      // Space is a temporary canvas hand key. Prevent native activation of a
      // focused toolbar button (Run/Stop) on both press and release.
      e.preventDefault();
      if(!e.repeat){state.spaceDown=true;applyCanvasTransform();if(document.activeElement?.matches?.('button'))document.activeElement.blur();}
      return;
    }
    if(e.key==='Escape'){closeCanvasMenu();endSelectionMarquee();}
    if((e.key==="删除"||e.key==='Backspace')&&!isTextEntry(e.target)){e.preventDefault();if(state.selectedEdgeIds.length){const ids=new Set(state.selectedEdgeIds);state.edges=state.edges.filter(edge=>!ids.has(edge.id));state.selectedEdgeIds=[];render();saveState();setRunStatus("已删除选中的连接。",'ok');}else removeSelectedNodes();}
    if(e.key.toLowerCase()==='h'&&!isTextEntry(e.target)){state.handMode=!state.handMode;$('#handTool').classList.toggle('active',state.handMode);applyCanvasTransform();}
  },true);
  document.addEventListener('keyup',e=>{if(e.code==='Space'&&!isTextEntry(e.target)){e.preventDefault();state.spaceDown=false;applyCanvasTransform();}},true);
  window.addEventListener('blur',()=>{state.spaceDown=false;endPan();endSelectionMarquee();applyCanvasTransform();});

  // Keep the session indicator fresh when Muse is opened/reloaded after the canvas.
  chrome.tabs.onUpdated.addListener((tabId,changeInfo,tab)=>{
    if(changeInfo.status==='complete'&&/^https:\/\/(?:[^/]+\.)?muse\.ai\//i.test(tab.url||''))testMuseSession(tabId);
  });
  chrome.tabs.onCreated.addListener(tab=>{
    if(/^https:\/\/(?:[^/]+\.)?muse\.ai\//i.test(tab.url||''))setTimeout(()=>testMuseSession(tab.id),1200);
  });

  loadState(); detectMuse();applyCanvasTransform();
})();
