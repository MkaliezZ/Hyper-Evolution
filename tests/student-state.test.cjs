const test=require('node:test'),assert=require('node:assert/strict');
const s=require('../src/growth_local/static/student-state.js');
test('student menu follows assigned work and teacher plans without authoring tools',()=>{
 const routes=s.groups.flatMap(([,items])=>items.map(([route])=>route));
 assert.deepEqual(routes,['home','tasks','feedback','planning','paths','connections','settings','guide']);
 for(const route of ['agent','materials','k12','practice','policy','retrieval','methods','resources'])assert.equal(s.routes.includes(route),false);
 assert.ok(s.routes.includes('writing'));
});
test('old self practice is preserved in storage but absent from assigned task projection',()=>{
 const rows=[{id:'t',origin:'teacher'},{id:'s',origin:'self'}];assert.deepEqual(s.tasks(rows).map(x=>x.id),['t']);assert.equal(rows.length,2);
});
test('student sees verified teacher growth cards and received schedules only',()=>{
 const rows=[{id:'teacher',author_role:'teacher',owner_device:'t',signature_verified:true},{id:'own',author_role:'student',owner_device:'s',signature_verified:false},{id:'fake',author_role:'teacher',owner_device:'x',signature_verified:false}];
 assert.deepEqual(s.plans(rows,'s').map(x=>x.id),['teacher']);
 assert.deepEqual(s.schedules([{owner_device:'t'},{owner_device:'s'}],'s'),[{owner_device:'t'}]);
});
test('task-linked reading and writing keep the task menu selected',()=>{
 for(const route of ['materials','writing','task'])assert.equal(s.section(route,'tasks'),'tasks');
 assert.equal(s.section('writing','feedback'),'feedback');
});
