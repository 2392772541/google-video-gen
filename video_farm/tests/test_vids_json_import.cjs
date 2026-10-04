'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../static/vids.html'), 'utf8');
const source = fs.readFileSync(path.join(__dirname, '../static/vids.js'), 'utf8');
function harness(legacy = false) {
  const nodes = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m => [m[1], {value:'', style:{}, textContent:'original label', innerHTML:'', disabled:false}]));
  if (legacy) { nodes['batch-import-textarea'] = nodes['json-import-textarea']; delete nodes['json-import-textarea']; }
  const alerts = [], requests = [];
  const context = vm.createContext({
    document: {getElementById:id=>nodes[id] || null, querySelector:()=>({value:'new'}), addEventListener:()=>{}},
    alert:msg=>alerts.push(msg), console, setTimeout:()=>0,
    FileReader:class {readAsText(file) {this.onload({target:{result:file.content}});}},
    fetch:async (url, options)=>{requests.push({url, options}); return {ok:true, json:async()=>({success:true, imported_count:6, workflow:{id:'test-only', title:'test', resolution:'1080p'}})};}
  });
  vm.runInContext(source, context);
  context.appendLog=()=>{};
  context.selectWorkflow=async()=>{};
  return {nodes, alerts, requests, context, textarea:nodes[legacy?'batch-import-textarea':'json-import-textarea']};
}
const assetFile = process.env.VIDS_IMPORT_ASSET_JSON;
const sample = [{engine:'flow', prompt:'镜头1：缓慢推入', start_image_path:'E:/assets/start.png', end_image_path:'E:/assets/end.png', duration_sec:10, priority:10}];
test('live HTML button imports pasted six-shot user JSON rather than reporting empty input', async()=>{
  const h=harness();
  assert.match(html, /onclick="executeBatchJsonImport\(\)"/);
  const data=assetFile ? JSON.parse(fs.readFileSync(assetFile,'utf8').replace(/^\uFEFF/,'')) : Array.from({length:6},(_,i)=>({...sample[0],prompt:'镜头'+(i+1)}));
  assert.equal(data.length,6);
  h.textarea.value=JSON.stringify(data);
  await h.context.executeBatchJsonImport();
  assert.deepEqual(h.alerts,[], 'Pasted input must not trigger the user-visible empty-input alert');
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].url,'/api/vids/batch_import');
  assert.deepEqual(JSON.parse(h.requests[0].options.body).data,data);
});
test('legacy textarea remains supported',async()=>{const h=harness(true);h.textarea.value=JSON.stringify(sample);await h.context.executeBatchImport();assert.equal(h.requests.length,1);});
test('empty input alerts without posting',async()=>{const h=harness();h.textarea.value='  ';await h.context.executeBatchJsonImport();assert.deepEqual(h.alerts,['请先输入或粘贴 JSON 数据！']);assert.equal(h.requests.length,0);});
test('invalid JSON displays visible syntax error without posting',async()=>{const h=harness();h.textarea.value='[{broken}]';await h.context.executeBatchJsonImport();assert.equal(h.requests.length,0);assert.deepEqual(h.alerts,[]);assert.ok(h.nodes['import-msg-box']);assert.equal(h.nodes['import-msg-box'].style.display,'block');assert.match(h.nodes['import-msg-box'].innerHTML,/JSON 格式语法解析失败/);});
test('fenced JSON parses through actual import alias',async()=>{const h=harness();h.textarea.value='```json\n'+JSON.stringify(sample)+'\n```';await h.context.executeBatchJsonImport();assert.equal(h.requests.length,1);});
test('pending import disables real submit button and restores its label',async()=>{
  const h=harness();h.textarea.value=JSON.stringify(sample);
  const btn=h.nodes['btn-submit-import'];assert.ok(btn);
  const label=btn.textContent;
  let release;h.context.fetch=()=>new Promise(resolve=>{release=resolve;});
  const pending=h.context.executeBatchJsonImport();assert.equal(btn.disabled,true);
  release({ok:true,json:async()=>({success:true,imported_count:1,workflow:{id:'test',title:'test'}})});
  await pending;assert.equal(btn.disabled,false);assert.equal(btn.textContent,label);
});
test('clear and file load operate on the visible textarea',()=>{const h=harness();h.textarea.value='old';h.context.clearImportTextarea();assert.equal(h.textarea.value,'');h.context.loadJsonFileToTextarea({files:[{name:'test.json',content:'[]'}]});assert.equal(h.textarea.value,'[]');});
test('sample loading writes to the visible textarea',async()=>{const h=harness();await h.context.fillSampleImportJson();assert.notEqual(h.textarea.value,'');});
