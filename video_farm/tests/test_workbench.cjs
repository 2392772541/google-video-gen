'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const file = path.join(__dirname,'../static/workbench.js');
const {mediaURL,playableTasks} = require(file);
const origin = 'http://127.0.0.1:8088';
const task = (id='one',extra={}) => ({id:'task_'+id,status:'completed',task_type:'video',has_video:true,video_url:'/media/outputs/'+id+'.mp4',prompt:id,...extra});
test('local media accepted',()=>assert.equal(mediaURL('/media/outputs/one.mp4',origin),origin+'/media/outputs/one.mp4'));
test('remote, protocol, and scheme-relative media rejected',()=>{for(const url of ['https://evil.example/a.mp4','//evil.example/a.mp4','javascript:alert(1)','/api/tasks']) assert.equal(mediaURL(url,origin),null)});
test('path traversal, backslashes and control characters rejected',()=>{for(const url of ['/media/../secret','/media/%2e%2e/secret','/media/a\\b','/media/a\nb']) assert.equal(mediaURL(url,origin),null)});
test('malformed media input is safe',()=>{for(const url of [undefined,null,42,{},'']) assert.equal(mediaURL(url,origin),null)});
test('only existing completed video outputs are included',()=>assert.equal(playableTasks([task(),task('2',{status:'running'}),task('3',{has_video:false}),task('4',{task_type:'audio'}),task('5',{task_type:'image'}),task('6',{id:'bad"id'})],origin).length,1));
test('invalid task collections are safe',()=>{for(const v of [null,{},undefined]) assert.deepEqual(playableTasks(v,origin),[]);assert.deepEqual(playableTasks([null,{},task('x',{video_url:'//evil/a'})],origin),[])});
test('latest collection is bounded to five without reordering',()=>assert.deepEqual(playableTasks(Array.from({length:100},(_,i)=>task(String(i))),origin).map(t=>t.id),['task_0','task_1','task_2','task_3','task_4']));
function harness() {
  class El {
    constructor(tag='DIV') {this.tagName=tag;this.children=[];this.dataset={};this.attrs={};this.events={};this.hidden=false;this.textContent='';this.srcWrites=0;this.paused=true;this.active=true;this.duration=8;this.videoWidth=1280;this.videoHeight=720;}
    set src(v){this._src=v;this.srcWrites++;} get src(){return this._src;}
    pause(){this.paused=true;} load(){this.loads=(this.loads||0)+1;}
    setAttribute(k,v){this.attrs[k]=v;} getAttribute(k){return this.attrs[k];}
    removeAttribute(k){delete this.attrs[k];if(k==='src')this._src='';}
    addEventListener(k,f){(this.events[k]??=[]).push(f);} fire(k){(this.events[k]||[]).forEach(f=>f());}
    replaceChildren(){this.children=[];} append(...els){this.children.push(...els);}
    querySelectorAll(sel){return sel==='button'?this.children:[];}
    closest(sel){return sel==='.view-pane.active' && this.active ? {} : null;}
  }
  const ids=['workbench-video','workbench-empty','workbench-state','workbench-output-title','workbench-task-id','workbench-prompt','workbench-requested','workbench-download','workbench-recents','workbench-measured','workbench-go-tasks','btn-mode-batch'];
  const nodes=Object.fromEntries(ids.map(id=>[id,new El(id==='workbench-video'?'VIDEO':'DIV')]));
  const tabs=[new El('BUTTON')],events={};
  const doc={hidden:false,getElementById:id=>nodes[id],createElement:t=>new El(t.toUpperCase()),querySelector:()=>tabs[0],querySelectorAll:sel=>sel==='video,audio'?[nodes['workbench-video']]:tabs,addEventListener:(k,f)=>(events[k]??=[]).push(f)};
  const root={document:doc};
  vm.runInNewContext(fs.readFileSync(file,'utf8'),{window:root,location:{origin},URL,queueMicrotask});
  const fire=k=>(events[k]||[]).forEach(f=>f());
  return {root,nodes,tabs,doc,fire};
}
test('single video source is stable across unchanged polling',()=>{const h=harness();h.fire('DOMContentLoaded');h.root.VideoWorkbench.update([task()]);const v=h.nodes['workbench-video'];v.paused=false;h.root.VideoWorkbench.update([task()]);assert.equal(v.srcWrites,1);assert.equal(v.paused,false);});
test('selecting a recent output changes only the single player',()=>{const h=harness();h.fire('DOMContentLoaded');h.root.VideoWorkbench.update([task(),task('two')]);h.nodes['workbench-recents'].children[1].fire('click');assert.equal(h.nodes['workbench-task-id'].textContent,'task_two');assert.equal(h.nodes['workbench-video'].srcWrites,2);});
test('empty output list clears the previous media and download',()=>{const h=harness();h.fire('DOMContentLoaded');h.root.VideoWorkbench.update([task()]);h.root.VideoWorkbench.update([]);assert.equal(h.nodes['workbench-video'].src,'');assert.equal(h.nodes['workbench-video'].hidden,true);assert.equal(h.nodes['workbench-download'].hidden,true);});
test('actual metadata is independent of requested duration',()=>{const h=harness();h.fire('DOMContentLoaded');h.root.VideoWorkbench.update([task('one',{duration_sec:4})]);h.nodes['workbench-video'].fire('loadedmetadata');assert.match(h.nodes['workbench-measured'].textContent,/1280.*720.*8\.0/);assert.match(h.nodes['workbench-requested'].textContent,/4 秒/);});
test('tab pause is deferred until the original navigation handler changes active state',async()=>{const h=harness();h.fire('DOMContentLoaded');h.root.VideoWorkbench.update([task()]);const v=h.nodes['workbench-video'];v.paused=false;h.tabs[0].fire('click');v.active=false;await new Promise(resolve=>queueMicrotask(resolve));assert.equal(v.paused,true);});
test('hiding page or choosing batch pauses the preview',()=>{const h=harness();h.fire('DOMContentLoaded');const v=h.nodes['workbench-video'];v.paused=false;h.doc.hidden=true;h.fire('visibilitychange');assert.equal(v.paused,true);v.paused=false;h.nodes['btn-mode-batch'].fire('click');assert.equal(v.paused,true);});
test('updates arriving before DOM ready are rendered on initialization',()=>{const h=harness();h.root.VideoWorkbench.update([task()]);h.fire('DOMContentLoaded');assert.equal(h.nodes['workbench-task-id'].textContent,'task_one');});
