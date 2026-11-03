const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const state=require('../src/growth_local/static/student-state.js'),workspace=require('../src/growth_local/static/workspace-state.js');
function context(role='student'){
 const ctx=vm.createContext({StudentState:state,WorkspaceState:workspace,status:{profile:{role,name:'合成学生'},device_id:'s',peers:[]},view:'home',workspaceReturn:'tasks',location:{hash:'#k12'},
 workspaceTeacher:()=>role==='teacher',workspaceAllowed:()=>true,workspaceNavigation:()=>'teacher navigation',workspaceRender:async()=>{},subjectReadOnly:()=>false,workspaceStudentHome(){},workspaceRenderTasks(){},workspaceTasks:async()=>{},
 workspacePlanning:async()=>{ctx.called='teacher planning';},evolutionPaths:async()=>{},academicSubjects:async()=>{},continuityEnhance:async()=>{},studyRead:async()=>{},c3OpenPage:async()=>{},guide(){},workspaceBoot:async()=>{},
 academicLoad:async()=>{ctx.loaded=true;},workspaceLoad:async()=>{},workspaceRows:[],g9:async()=>({data:{plans:ctx.plans||[]}}),c5:async()=>({data:{paths:[]}}),e5Load:async()=>{},
 shell:html=>{ctx.html=html;},workspaceHeading:(a,b,c)=>a+b+c,growthFacts:()=>'',subjectCurrent:()=> 'mathematics',h:x=>String(x??''),
 workspaceNavigate:async route=>{ctx.route=route;},document:{addEventListener(){}},workspaceRouteCard:(a,b,r)=>a+b+r,workspaceEmpty:(a,b)=>a+b,workspaceTaskRow:t=>t.id});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/growth_local/static/student.js'),'utf8'),ctx);return ctx;
}
test('final student navigation has one active item and no authoring entry',()=>{
 const ctx=context();ctx.view='planning';const html=vm.runInContext('workspaceNavigation()',ctx);
 assert.equal((html.match(/aria-current="page"/g)||[]).length,1);assert.match(html,/老师的规划/);
 for(const text of ['投石问路','题库','资料检索','学习助手','学习设计'])assert.equal(html.includes(text),false);
 assert.equal(vm.runInContext("workspaceAllowed('k12')",ctx),false);
});
test('student growth view only displays the teachers shared card without editing or sharing controls',async()=>{
 const ctx=context();ctx.plans=[{id:'t',revision:2,owner_device:'t',author_role:'teacher',signature_verified:true,content:{goal:'Teacher goal',requirements:[]}},
 {id:'s',revision:1,owner_device:'s',author_role:'student',signature_verified:false,content:{goal:'Old private goal',requirements:[]}}];
 await vm.runInContext('workspacePlanning()',ctx);assert.match(ctx.html,/Teacher goal/);assert.equal(ctx.html.includes('Old private goal'),false);
 assert.equal(/<form|growth-edit|growth-share|growth-learn|growth-new/.test(ctx.html),false);
});
test('old K12 bookmark opens assigned tasks and teacher view stays intact',async()=>{
 const ctx=context();await vm.runInContext('workspaceBoot()',ctx);assert.equal(ctx.loaded,true);assert.equal(ctx.route,'tasks');
 const teacher=context('teacher');assert.equal(vm.runInContext('workspaceNavigation()',teacher),'teacher navigation');
 await vm.runInContext('workspacePlanning()',teacher);assert.equal(teacher.called,'teacher planning');
});
