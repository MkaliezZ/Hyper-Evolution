const test=require('node:test'),assert=require('node:assert/strict');
const state=require('../src/growth_local/static/experience-state.js');
const vm=require('node:vm'),fs=require('node:fs');
test('teacher leaves resolve to one work group; old bookmarks stay meaningful',()=>{
 const expected={materials:'assign',agent:'assign',retrieval:'assign',planning:'students',paths:'students',memory:'students',writing:'review','policy-lab':'policy',methods:'policy',k12:'academic'};
 for(const [leaf,group] of Object.entries(expected))assert.equal(state.group('teacher',leaf,'review')[0],group);
 assert.equal(state.group('teacher','task','review')[0],'review');
 for(const group of state.teacher)for(const [leaf] of group[2])assert.equal(state.teacher.filter(g=>g[0]===state.group('teacher',leaf)[0]).length,1);
});
test('self flow reuses existing routes and keeps teacher assignments outside own task list',()=>{
 assert.deepEqual(state.self.map(g=>g[0]),['home','materials','tasks','feedback','planning']);
 assert.equal(state.group('self','reviews')[0],'feedback');
 assert.deepEqual(state.ownTasks([{id:'own'},{id:'teacher',origin:'teacher'}]).map(t=>t.id),['own']);
});
test('all three final sidebars keep one selected group and guided students stay focused on teacher tasks',()=>{
 for(const mode of ['teacher','self','student']){
  const ctx=vm.createContext({ExperienceState:state,status:{profile:{role:mode==='teacher'?'teacher':'student'},experience:{id:mode},model:{}},
   workspaceTeacher:()=>mode==='teacher',workspaceReturn:'tasks',view:'home',workspaceNavigation:()=>'guided-menu',workspaceAllowed:()=>true,studentPreviousAllowed:()=>true,
   header(){},setup(){},shell(){},workspaceStudentHome(){},workspaceRenderTasks(){},workspaceTasks(){},workspaceBoot(){},continuityEnhance(){},guide(){},results(){},workspaceTaskRow(){},
   document:{addEventListener(){}},h:s=>String(s??'')});
  vm.runInContext(fs.readFileSync(require.resolve('../src/growth_local/static/experience.js'),'utf8'),ctx);
  const routes=mode==='student'?['home','tasks','feedback','planning','paths','writing','connections','settings','guide','academic']:['home','materials','agent','planning','writing','settings','academic',...(mode==='teacher'?['policy-lab','review']:['feedback','reviews'])];
  for(const route of routes){
   ctx.view=route;const html=vm.runInContext('workspaceNavigation()',ctx);
   assert.equal((html.match(/aria-current="page"/g)||[]).length,1,mode+':'+route);
   assert.equal(html.includes('data-route="'+(mode==='teacher'?'tasks':'students')+'"'),false);
   if(mode==='student'){
    assert.match(html,/EVOLVER \/ 学生版/);assert.match(html,/连接与设置/);
    for(const hidden of ['materials','agent','practice','writing','methods','policy'])assert.equal(html.includes('data-route="'+hidden+'"'),false);
   }
   if(mode==='self')assert.match(html,/SELF-EVOLVER \/ 自学版/);
  }
 }
});
test('student plans and task-linked writing retain the correct primary group',()=>{
 assert.deepEqual(state.student.map(g=>g[0]),['home','tasks','feedback','planning']);
 assert.deepEqual(state.utilities('student').map(([r])=>r),['connections','settings','guide']);
 assert.equal(state.group('student','paths','tasks')[0],'planning');
 assert.equal(state.group('student','writing','feedback')[0],'feedback');
 assert.equal(state.group('student','writing','tasks')[0],'tasks');
});
