const test=require('node:test'),assert=require('node:assert/strict');
const {taskState,matches}=require('../src/growth_local/static/workspace-state.js');
const task=(extra={})=>({id:'t',state:'active',pack:{title:'Garden claim'},attempts:[],...extra});
test('saved queue is not delivered work or teacher feedback',()=>{
 const t=task({origin:'teacher',local_submissions:[{delivery:'queued'}]});
 assert.equal(taskState(t,'student').key,'sending');
 assert.equal(matches(t,'todo','','student'),false);
 assert.equal(matches(t,'waiting','','student'),true);
});
test('acknowledged transport does not become a teaching judgment',()=>{
 const t=task({origin:'teacher',local_submissions:[{delivery:'acknowledged'}],attempts:[{evaluation:{status:'pending'},review_history:[]}]});
 assert.equal(taskState(t,'student').key,'waiting');
 assert.equal(taskState(t,'teacher').key,'review');
});
test('automatic answer check still needs teacher review',()=>{
 const t=task({attempts:[{evaluation:{status:'reviewed'},automatic:{score:5},review_history:[]}]});
 assert.equal(taskState(t,'teacher').key,'review');
 assert.match(taskState(t,'student').label,/自动核对/);
});
test('revision and signed feedback are visible separately from completion',()=>{
 const t=task({attempts:[{evaluation:{judgement:'needs_revision'},review_history:[{}]}]});
 assert.equal(taskState(t,'student').key,'revision');
 assert.equal(matches(t,'todo','','student'),true);
 assert.equal(matches(t,'feedback','','student'),true);
 assert.equal(matches(t,'review','','teacher'),false);
 assert.equal(matches(t,'todo','','teacher'),false);
 t.attempts.push({evaluation:{status:'pending'},review_history:[]});
 assert.equal(taskState(t,'teacher').key,'review');
});
test('paused and archived tasks do not appear as tasks to submit',()=>{
 for(const state of ['paused','archived']){
  const t=task({state});assert.equal(matches(t,'todo','','student'),false);assert.equal(matches(t,'closed','','student'),true);
 }
});
test('search works across student and title without dropping other filters',()=>{
 const t=task({_studentName:'合成小林'});
 assert.equal(matches(t,'todo',' 小林 ','teacher'),true);
 assert.equal(matches(t,'todo','garden','teacher'),true);
 assert.equal(matches(t,'review','garden','teacher'),false);
});
test('coverage lists every v0.2 retain/refactor/new item without fake planned routes',()=>{
 const coverage=require('../src/growth_local/static/feature-coverage.json');
 const ids=['K01','K02','K03','K04','K05','K06','K07','R01','R02','R03','R04','R05','R06',...Array.from({length:10},(_,i)=>'N'+String(i+1).padStart(2,'0'))];
 assert.deepEqual(coverage.items.filter(x=>!x.id.startsWith('K12-')).map(x=>x.id),ids);
 assert.equal(new Set(ids).size,23);
 assert.deepEqual(coverage.items.filter(x=>x.id.startsWith('K12-')).map(x=>x.id),['K12-01','K12-02','K12-03']);
 assert.equal(coverage.items.filter(x=>x.status==='planned').every(x=>x.route===null),true);
 assert.equal(coverage.items.find(x=>x.id==='K06').status,'partial');
});
