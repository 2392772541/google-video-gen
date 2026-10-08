'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');
function section(start, end) {
  const from = source.indexOf(start), to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from, 'Missing production seam: ' + start);
  return source.slice(from, to);
}
const options = {
  engines: [
    {id:'flow',label:'Google Flow 网页生图',model_label:'图像生成模型'},
    {id:'gemini',label:'Gemini 网页生图',model_label:'Gemini 网页模式'}
  ],
  models: {
    flow:[{id:'nano-pro',label:'Nano Banana Pro'},{id:'nano2-lite',label:'Nano Banana 2 Lite'},{id:'nano2.1',label:'Nano Banana 2.1'}],
    gemini:[{id:'gemini-flash',label:'3.8 Flash'},{id:'gemini-pro',label:'3.1 Pro'},{id:'gemini-thinking',label:'扩展思考'}]
  },
  default_models:{flow:'nano-pro',gemini:'gemini-flash'},
  aspect_ratios:['1:1','9:16','3:4','4:3','16:9'],
  availability_note:'以所选账号网页提供的选项为准；不可用时明确报错，不自动换模型。'
};
class Element {
  constructor(value = '') { this.value=value; this.textContent=''; this.innerHTML=''; this.style={}; this.disabled=false; this.events={}; this.children=[]; this.classList={add(){},remove(){}}; }
  get innerHTML() { return this._innerHTML || ""; }
  set innerHTML(value) { this._innerHTML=value; this.children=[]; }
  addEventListener(name, listener) { (this.events[name] ??= []).push(listener); }
  replaceChildren(...children) { this.children=children; this.value=children[0]?.value || ''; }
  appendChild(child) { this.children.push(child); }
  removeAttribute(name) { delete this[name]; }
  click() { this.clicks=(this.clicks || 0)+1; }
  async fire(name, extra={}) {
    const e={target:this,preventDefault(){},stopPropagation(){},...extra};
    for (const f of this.events[name] || []) await f(e);
  }
}
function deferred() { let resolve; const promise=new Promise(r=>{resolve=r;}); return {promise,resolve}; }
async function settle() { for(let i=0;i<8;i++) await Promise.resolve(); }
function harness({payload=options,holdOptions=null,holdSubmit=null,tasks=[]}={}) {
  const el={};
  for(const key of ['selectImageEngine','selectImageModel','selectImageAspect','btnSubmitImageTask','inputImagePrompt','selectImageProfile','dropImageRef','fileInputImageRef','imgPreviewRef','placeholderImageRef','btnClearImageRef','imageGalleryList','galleryCount']) el[key]=new Element();
  el.selectImageEngine.value='flow'; el.selectImageModel.value='nano-pro'; el.selectImageAspect.value='9:16'; el.inputImagePrompt.value='a test image';
  const hints={'image-availability-hint':new Element(),'image-model-label':new Element()};
  const h={el,hints,posts:[],toasts:[],created:[],revoked:[],refreshes:0};
  const state={currentEngine:'vids',imageRefFile:null,tasks};
  const document={getElementById:id=>hints[id] || null,createElement:()=>new Element()};
  class FormData { constructor(){this.values=new Map();} append(k,v){this.values.set(k,v);} get(k){return this.values.get(k);} }
  class FileReader { readAsDataURL(){h.fileReaderUsed=true;} }
  const ctx=vm.createContext({el,state,document,FormData,FileReader,console,Set,AbortController,setTimeout,clearTimeout,
    URL:{createObjectURL:f=>{const u='blob:'+h.created.length;h.created.push({f,u});return u;},revokeObjectURL:u=>h.revoked.push(u)},
    fetch:async(url,request)=>{
      if(url==='/api/image/options'){ if(holdOptions) await holdOptions.promise; return {ok:true,json:async()=>payload}; }
      if(url==='/api/tasks/create-image'){ h.posts.push(request.body); if(holdSubmit) await holdSubmit.promise; return {ok:true,json:async()=>({id:'task_test',status:'queued'})}; }
      throw Error('Unexpected HTTP request '+url);
    },
    showToast:(...a)=>h.toasts.push(a),fetchTasks:async()=>{h.refreshes++;},renderTasks(){},triggerRefreshButton(){}
  });
  vm.runInContext(section('  function escapeJs(', '  // 统一刷新按钮')+'\n'+section('// ==================== 图像生成工坊事件绑定', '  // ==================== 设为首尾帧')+'\n'+section('  function renderImageGallery()', '  // ==================== 视频播放器弹窗')+'\nthis.imageTest={handleImageRefSelect,loadImageOptions,updateImageModels,renderImageGallery,state};',ctx);
  h.api=ctx.imageTest;
  return h;
}
test('HTML disables image submission until the provider contract is loaded',()=>{
  const button=html.match(/<button\b[^>]*id="btn-submit-image-task"[^>]*>/)[0];
  assert.match(button,/\bdisabled\b/);
  assert.doesNotMatch(html.split('id="select-image-model"')[1].split('</select>')[0],/本地路由|imagen4/);
});
test('a malformed successful options response cannot submit or silently default to Flow',async()=>{
  const h=harness({payload:{models:{flow:[]}}}); await settle();
  assert.equal(h.el.btnSubmitImageTask.disabled,true);
  await h.el.btnSubmitImageTask.fire('click');
  assert.equal(h.posts.length,0);
});
test('the form cannot submit while options are still loading',async()=>{
  const pending=deferred(), h=harness({holdOptions:pending});
  await h.el.btnSubmitImageTask.fire('click');
  assert.equal(h.posts.length,0); pending.resolve(); await settle();
  assert.equal(h.el.btnSubmitImageTask.disabled,false);
});
test('platform switches rebuild only the image models and send the exact engine/mode',async()=>{
  const h=harness(); await settle();
  assert.deepEqual(Array.from(h.el.selectImageModel.children,m=>m.textContent),['Nano Banana Pro','Nano Banana 2 Lite','Nano Banana 2.1']);
  h.el.selectImageEngine.value='gemini'; await h.el.selectImageEngine.fire('change');
  assert.equal(h.el.selectImageModel.value,'gemini-flash');
  assert.match(h.hints['image-model-label'].textContent,/Gemini.*网页模式/);
  assert.match(h.hints['image-availability-hint'].textContent,/不是|不代表|底层/);
  await h.el.btnSubmitImageTask.fire('click');
  assert.equal(h.posts[0].get('engine'),'gemini');
  assert.equal(h.posts[0].get('model'),'gemini-flash');
  assert.equal(h.api.state.currentEngine,'vids');
  assert.equal(h.posts[0].get('assigned_profile_id'),undefined);
});
test('a tampered engine/model pair is blocked before a task is queued',async()=>{
  const h=harness(); await settle(); h.el.selectImageModel.value='gemini-flash';
  await h.el.btnSubmitImageTask.fire('click'); assert.equal(h.posts.length,0);
  assert.equal(h.el.btnSubmitImageTask.disabled,true);
});
test('double clicks queue only one image task and recover the readiness state',async()=>{
  const pending=deferred(), h=harness({holdSubmit:pending}); await settle();
  const first=h.el.btnSubmitImageTask.fire('click'); await settle();
  const second=h.el.btnSubmitImageTask.fire('click'); await settle();
  assert.equal(h.posts.length,1);
  pending.resolve(); await Promise.all([first,second]);
  assert.equal(h.el.btnSubmitImageTask.disabled,false);
});
test('references are bounded, previewed without base64 copies, and revoked on replacement/clear',async()=>{
  const h=harness(); await settle();
  h.api.handleImageRefSelect({type:'image/png',name:'large.png',size:32*1024*1024+1});
  assert.equal(h.api.state.imageRefFile,null); assert.equal(h.created.length,0);
  const file={type:'image/png',name:'test.png',size:1024};
  h.api.handleImageRefSelect(file); assert.equal(h.api.state.imageRefFile,file);
  assert.equal(h.el.imgPreviewRef.src,'blob:0'); assert.equal(h.fileReaderUsed,undefined);
  h.api.handleImageRefSelect({...file,name:'another.png'}); assert.deepEqual(h.revoked,['blob:0']);
  await h.el.btnClearImageRef.fire('click'); assert.equal(h.api.state.imageRefFile,null);
  assert.deepEqual(h.revoked,['blob:0','blob:1']);
});
test('reference input is keyboard accessible',async()=>{
  const h=harness(); await settle(); await h.el.dropImageRef.fire('keydown',{key:'Enter'});
  await h.el.dropImageRef.fire('keydown',{key:' '}); assert.equal(h.el.fileInputImageRef.clicks,2);
});
test('gallery displays source platform, escapes labels and keeps original download/frame actions',async()=>{
  const h=harness({tasks:[{id:'task_img',task_type:'image',engine:'gemini',model:'gemini-flash',prompt:'<test>',status:'completed',image_urls:['/media/outputs/task_img/attempt_test/new.png'],image_paths:['C:/outputs/task_img/attempt_test/new.png'],aspect_ratio:'9:16'}]}); await settle();
  h.api.renderImageGallery(); const content=h.el.imageGalleryList.children[0].innerHTML;
  assert.match(content,/Gemini.*3\.8 Flash/); assert.match(content,/\bdownload\b/);
  assert.match(content,/setAsStartFrame/); assert.match(content,/setAsEndFrame/);
  h.api.state.tasks[0].model='<img src=x onerror=alert(1)>'; h.api.renderImageGallery();
  assert.doesNotMatch(h.el.imageGalleryList.children[0].innerHTML,/<img src=x/);
});
