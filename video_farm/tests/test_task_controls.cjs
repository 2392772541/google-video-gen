'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
function section(start,end,after=0) {const from=source.indexOf(start,after),to=source.indexOf(end,from);assert.ok(from>=0&&to>from,'missing production seam '+start);return source.slice(from,to);}
const updater = section('  function updateBatchActionBar()', '  // 绑定批量操作条控制逻辑');
const binding = section('  if (el.btnBatchCancel) {','  if (el.btnBatchDelete) {',source.indexOf('window.location.href = \x60/api/tasks/batch-download-zip'));
function setup(result) {
 const listeners=[],toasts=[],requests=[];
 const el={batchActionBar:{},btnBatchCancel:{addEventListener:(ev,fn)=>listeners.push(fn)}};
 const state={tasks:[],selectedTaskIds:new Set(['queued','active','done'])};
 const ctx={el,state,confirm:()=>true,getCurrentFilteredTasks:()=>[],showToast:(msg,kind)=>toasts.push({msg,kind}),fetch:async(u,o)=>{requests.push({u,o});return {ok:true,json:async()=>result}},fetchTasks:async()=>{},fetchOverview:async()=>{}};
 vm.createContext(ctx);vm.runInContext(updater+binding,ctx);return {ctx,listeners,toasts,requests,state,el};
}
test('polling/selection refresh never accumulates batch-stop click handlers',async()=>{const x=setup({cancelled_ids:[],stopping_ids:[],errors:[]});for(let i=0;i<20;i++)vm.runInContext('updateBatchActionBar()',x.ctx);assert.equal(x.listeners.length,1);await x.listeners[0]();assert.equal(x.requests.length,1);});
test('partial stop reports cancelled/stopping separately and retains failed selection',async()=>{const x=setup({cancelled_count:1,cancelled_ids:['queued'],stopping_count:1,stopping_ids:['active'],errors:[{task_id:'done',message:'already completed'}]});await x.listeners[0]();assert.deepEqual([...x.state.selectedTaskIds],['done']);assert.match(x.toasts[0].msg,/已取消 1.*正在停止 1.*未处理 1/s);assert.equal(x.toasts[0].kind,'warning');assert.doesNotMatch(x.toasts[0].msg,/已.*释放槽位/);});
