'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/vids.js'),'utf8');
function harness(){
 const badge={innerHTML:''},preview={innerHTML:'',dataset:{},querySelector:()=>null};
 const actions={children:[],querySelector(sel){return this.children.find(n=>n.className.includes(sel.slice(1)))||null;},insertBefore(n){n.remove=()=>{this.children=this.children.filter(v=>v!==n);};this.children.push(n);}};
 const card={className:'',querySelector(sel){if(sel==='.shot-header-actions')return actions;if(sel==='.shot-status-badge-wrap')return badge;if(sel==='#shot-media-preview-shot1')return preview;return null;}};
 const container={querySelectorAll:()=>[card]};
 const ctx=vm.createContext({console,setTimeout:()=>0,document:{addEventListener(){},getElementById(id){return id==='shots-cards-container'?container:id==='shot-card-shot1'?card:null;},createElement:()=>({style:{}})}});
 vm.runInContext(source,ctx);ctx.renderShotIndex=()=>{};ctx.bindShotMedia=()=>{};ctx.appendLog=()=>{};
 return {ctx,actions,badge,preview};
}
for(const [status,label,canStop] of [['queued','排队',true],['retry_wait','等待重试',true],['running','生成中',true],['stopping','停止中',false],['cancelled','已停止',false],['failed','失败',false]]){
 test(`poll ${status} preserves honest badge and stop control`,()=>{
  const h=harness();assert.doesNotThrow(()=>h.ctx.syncShotsDOM([{id:'shot1',status,progress:15,engine:'flow'}]));
  assert.match(h.badge.innerHTML,new RegExp(label));assert.equal(Boolean(h.actions.querySelector('.btn-dynamic-stop')),canStop);
  if(status==='queued'||status==='retry_wait'||status==='stopping')assert.doesNotMatch(h.preview.innerHTML,/单独渲染|重新生成/);
  assert.doesNotMatch(h.preview.innerHTML,/Google Vids 原生成片|Google Vids 渲染中/);
 });
}
test('Flow output is not labelled as native Google Vids',()=>{const h=harness();const html=h.ctx.getShotMediaPreviewHtml({id:'shot1',engine:'flow',video_url:'/media/one.mp4'},0,true,false,false,'1080p');assert.doesNotMatch(html,/Google Vids 原生成片/);assert.match(html,/Google Flow/);});
test('preview does not invent a first-last frame interpolation capability',()=>{const h=harness();const html=h.ctx.getShotMediaPreviewHtml({id:'shot1',engine:'vids',mode:'first_last_frame'},0,false,false,false,'1080p');assert.doesNotMatch(html,/原生插值/);});
