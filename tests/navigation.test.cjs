const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const state=require('../src/growth_local/static/workspace-state.js');
const read=name=>fs.readFileSync(path.join(__dirname,'../src/growth_local/static',name),'utf8');
test('cold boot waits until all deferred modules have loaded',async()=>{
 const events={};let requests=0,booted=0;
 const ctx=vm.createContext({document:{body:{dataset:{}},addEventListener(){}},window:{addEventListener(name,fn){events[name]=fn;}},
  location:{hash:''},setInterval(){},setTimeout,clearTimeout,FormData,fetch:async()=>{requests++;return {ok:true,json:async()=>({profile:{role:'student'}})};},workspaceBoot:async()=>{booted++;}});
 vm.runInContext(read('local.js'),ctx);
 assert.equal(requests,0);assert.equal(booted,0);
 await events.DOMContentLoaded();assert.equal(booted,1);
});
test('first home after setup resolves the selected workspace before reading the dashboard',async()=>{
 let ready=false,rendered=false;
 const ctx=vm.createContext({document:{body:{dataset:{}},addEventListener(){}},window:{addEventListener(){}},setInterval(){},setTimeout,clearTimeout,FormData,
  academicContext:{selection:{subject:'mathematics'}},academicLoad:async()=>{ready=true;},
  workspaceTeacherHome:async()=>{assert.equal(ready,true);rendered=true;},
  fetch:async()=>({ok:true,json:async()=>({profile:{role:'teacher'}})})});
 vm.runInContext(read('local.js'),ctx);await vm.runInContext('home()',ctx);assert.equal(rendered,true);
});
function context(role='teacher'){
 const ctx=vm.createContext({WorkspaceState:state,URLSearchParams,console,
  document:{addEventListener(){}},window:{addEventListener(){}},
  status:{profile:{role},model:{}},view:'materials',currentTask:null,
  h:s=>String(s??''),api:async()=>({}),header(){},setup(){},shell(){},results(){},guide(){}});
 vm.runInContext(read('workspace.js'),ctx);vm.runInContext(read('academic.js'),ctx);vm.runInContext("academicContext={selection:{subject:'english',track:'k12'}}",ctx);return ctx;
}
test('old category URLs cannot select a workspace or change the current data scope',()=>{
 assert.equal(state.routeTarget('#materials?subject=science').route,'materials');
 assert.equal(state.routeHash('materials',{materialSubject:'science'}),'#materials');
 assert.equal(state.routeHash('agent'),'#agent');
});
test('each role has one active menu and specialized English remains a secondary menu',()=>{
 for(const role of ['teacher','student']){
  const ctx=context(role);
  const routes=vm.runInContext('workspaceRoutes.filter(workspaceAllowed)',ctx);
  for(const route of routes){
   ctx.view=route;const html=vm.runInContext('workspaceNavigation()',ctx);
   assert.equal((html.match(/aria-current="page"/g)||[]).length,1,role+': '+route);
   assert.match(html,/aria-label="学科与路线的二级菜单"/);
   assert.match(html,/我的资料库/);assert.match(html,/data-track="k12"/);assert.match(html,/data-track="study_abroad"/);
   assert.equal(html.includes('data-route="'+(role==='teacher'?'tasks':'students')+'"'),false);
  }
  ctx.view='task';ctx.currentTask={pack:{academic:true}};
  vm.runInContext("workspaceReturn='"+(role==='teacher'?'review':'tasks')+"'",ctx);
  assert.equal((vm.runInContext('workspaceNavigation()',ctx).match(/aria-current="page"/g)||[]).length,1);
 }
});
test('K12 selection does not silently redirect assign, resources, practice or agent menus',async()=>{
 const ctx=context();ctx.called=[];
 vm.runInContext("academicContext={selection:{subject:'english',track:'k12'}}; workspaceAssign=async()=>called.push('assign'); resources=async()=>called.push('resources'); workspacePractice=async()=>called.push('practice'); workspaceLoad=async()=>{}; agentPage=()=>called.push('agent'); jobHistory=async()=>{}; academicHome=async()=>called.push('k12');",ctx);
 for(const route of ['assign','resources','agent','k12'])await vm.runInContext("workspaceRender('"+route+"')",ctx);
 ctx.status.profile.role='student';await vm.runInContext("workspaceRender('practice')",ctx);
 assert.deepEqual(ctx.called,['assign','resources','agent','k12','practice']);
});
test('a stale category form cannot silently switch the current workspace',async()=>{
 const ctx=context();ctx.writes=[];ctx.history={replaceState(...args){ctx.writes.push(args);}};
 vm.runInContext('studyCall=async()=>({}); studyAdd=()=>{}; studyRead=async()=>{}; c3AddPage=()=>{}; agentPage=()=>{};',ctx);
 vm.runInContext(read('subject-materials.js'),ctx);
 await assert.rejects(vm.runInContext("subjectAfterSave('science')",ctx));
 await vm.runInContext("subjectAfterSave('english')",ctx);
 assert.equal(vm.runInContext('academicContext.selection.subject',ctx),'english');
 assert.equal(ctx.writes[0][2],'/#materials');
});
test('non-English workspace hides English submenus and legacy only exposes reading routes',()=>{
 const ctx=context('student');
 vm.runInContext("academicContext={selection:{subject:'mathematics',track:'materials'}}",ctx);
 assert.equal(vm.runInContext('workspaceNavigation()',ctx).includes('data-track="k12"'),false);
 assert.equal(vm.runInContext("workspaceAllowed('practice')",ctx),false);
 vm.runInContext("academicContext={selection:{subject:'legacy',track:'materials'}}",ctx);
 assert.equal(vm.runInContext("workspaceAllowed('agent')",ctx),false);
 assert.equal(vm.runInContext("workspaceAllowed('materials')",ctx),true);
});
