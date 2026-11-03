const test=require('node:test'),assert=require('node:assert/strict');
const state=require('../src/growth_local/static/assistant-state.js');
test('teacher starts with four recognizable jobs rather than model modes',()=>{
 assert.deepEqual(state.intents.map(i=>i.id),['prepare','analyze','practice','review']);
 assert.equal(new Set(state.intents.map(i=>i.title)).size,4);
});
test('generic subjects use their material workflow, never the English exam generator',()=>{
 for(const subject of ['mathematics','science','subject-1234']){
  assert.equal(state.flow('practice',subject,'materials').route,'materials');
  assert.equal(state.flow('practice',subject,'materials').mode,undefined);
 }
});
test('K12 analysis and generation go to actual route/report/review workflows',()=>{
 for(const intent of ['analyze','practice'])assert.equal(state.flow(intent,'english','k12').route,'k12');
});
test('only explicit study-abroad route exposes exam draft generation',()=>{
 assert.equal(state.flow('practice','english','study_abroad').mode,'draft');
 assert.equal(state.flow('practice','english','materials').route,'materials');
});
test('AI starts only with a paired student, required work and configured key',()=>{
 assert.match(state.ready('coach',true,'',2),/学生/);
 assert.match(state.ready('coach',true,'p',0),/作品/);
 assert.match(state.ready('coach',false,'p',2),/API/);
 assert.equal(state.ready('coach',true,'p',2),'');
 assert.equal(state.ready('draft',true,'p',0),'');
});
test('pre-review remains attached to submitted work and explicit teacher publication',()=>{
 const flow=state.flow('review','mathematics','materials');
 assert.equal(flow.route,'review');assert.match(flow.steps.at(-1),/确认教师反馈/);
});
test('growth goals fill task fields only for the chosen subject and learner',()=>{
 const form={elements:{goal:{value:''},question:{value:''},criteria:{value:''}}},details={open:false};
 const growth={subject:'mathematics',peer:'student-a',goal:'Explain a ratio',action:'Use a new example',criteria:'State its conditions'};
 assert.equal(state.applyGoal(form,details,growth,'science','student-a'),false);
 assert.equal(state.applyGoal(form,details,growth,'mathematics','student-b'),false);
 assert.equal(form.elements.goal.value,'');assert.equal(details.open,false);
 assert.equal(state.applyGoal(form,details,growth,'mathematics','student-a'),true);
 assert.equal(form.elements.goal.value,growth.goal);assert.equal(form.elements.question.value,growth.action);
 assert.equal(form.elements.criteria.value,growth.criteria);assert.equal(details.open,true);
 assert.equal(state.applyGoal(null,details,growth,'mathematics','student-a'),false);
});
