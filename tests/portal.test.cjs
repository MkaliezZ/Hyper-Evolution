const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {roles,roleFromSearch,packageName,tag}=require('../site/welcome.js');
const html=fs.readFileSync(path.join(__dirname,'../site/index.html'),'utf8');

test('share links distinguish the three editions and unknown roles use student guide',()=>{
 for(const role of ['teacher','student','self']){
  assert.equal(roleFromSearch('?role='+role),role);
  assert.ok(html.includes('/?role='+role+'#how'));
 }
 for(const value of ['','?role=__proto__','?role=constructor','?role=%3Cscript%3E'])assert.equal(roleFromSearch(value),'student');
});
test('each edition has a distinct downloadable package and matching startup tutorial',()=>{
 const names=new Set();
 for(const role of ['teacher','student','self']){
  const file=packageName(role);names.add(file);
  assert.ok(html.includes('/downloads/'+file));
  assert.equal(roles[role].launch,'启动-'+roles[role].brand+'.cmd');
  for(const key of Object.keys(roles[role]).filter(x=>!['manual','brand'].includes(x)))assert.ok(html.includes('id="role-'+key+'"'),key);
 }
 assert.equal(names.size,3);assert.equal(tag,'v0.6.0-rc.3');
 assert.match(roles.teacher.pair,/生成学生配对码/);
 assert.match(roles.student.pair,/输入老师配对码/);
 assert.match(roles.self.pair,/自学可以直接/);
});
test('portal exposes product name, engineering status and first-run network instructions without legacy offline steps',()=>{
 assert.ok(html.includes('超维伴学 Hyper Evolution'));
 assert.ok(html.includes('工程测试版')&&html.includes('首次启动需要联网'));
 assert.ok(!html.includes('超维成长')&&!html.includes('HyperGrowth.exe')&&!html.includes('_internal'));
 assert.ok(html.includes('模型与本机设置')&&html.includes('查看本地 MCP 连接配置'));
});
