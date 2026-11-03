(function(root){
 'use strict';
 const intents=[
  {id:'prepare',title:'根据资料备课',detail:'选一份资料，梳理讲解重点与学习任务。'},
  {id:'analyze',title:'看学生情况',detail:'结合已提交作品和反馈，想清下一步。'},
  {id:'practice',title:'准备练习',detail:'按当前路线准备，再审校和布置。'},
  {id:'review',title:'预审学生作业',detail:'选一份作品，AI先提建议，老师修改发送。'}
 ];
 function flow(id,subject,track){
  if(id==='analyze'&&subject==='english'&&track==='k12')return {route:'k12',label:'打开K12路线与学习报告',steps:['选择学生','打开学习路线','查看路线报告和下一步']};
  if(id==='analyze')return {mode:'coach',label:'整理这位学生的下一步',steps:['选择学生','核对本学科已提交作品','补充关注点并开始分析','查看建议，决定下一次任务']};
  if(id==='practice'&&subject==='english'&&track==='study_abroad')return {mode:'draft',label:'生成5题原创草稿',steps:['选择学生','写清本次练习重点','生成并逐题审校','确认后布置给学生']};
  if(id==='practice'&&subject==='english'&&track==='k12')return {route:'k12',label:'进入K12备题',steps:['选择学生和学习路线','填写本次范围','AI备题并独立审题','教师核对后组题布置']};
  if(id==='review')return {route:'review',label:'选择待评阅作品',steps:['打开待评阅作品','进入AI预审 / 人工评阅','生成建议并修改草稿','确认教师反馈并发送']};
  return {route:'materials',label:id==='practice'?'从本学科资料设计练习':'去资料库选一份资料',steps:['打开本学科资料','问一问所选原文，梳理重点','点击“用这段资料学习”','填写目标、方法和完成标准']};
 }
 function ready(mode,configured,peer,submitted){
  if(!peer)return '请先选择一位已配对学生。';
  if(mode==='coach'&&!submitted)return '这位学生在本学科还没有已提交作品，先布置一次任务，收到作品后再来分析。';
  if(!configured)return '先配置并测试自己的API，再开始这项AI任务。';
  return '';
 }
 function applyGoal(form,details,growth,subject,peer){
  if(!form||!growth||growth.subject!==subject||growth.peer!==peer)return false;
  for(const [name,key] of [['goal','goal'],['question','action'],['criteria','criteria']]){
   if(form.elements[name])form.elements[name].value=growth[key]||'';
  }
  if(details)details.open=true;
  return true;
 }
 const api={intents,flow,ready,applyGoal};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.AssistantState=api;
})(typeof window==='undefined'?this:window);
