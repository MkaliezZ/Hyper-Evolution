/* Navigation is a projection, never an identity or authorization mechanism. */
(function(root){'use strict';
 const teacher=[['home','教学首页',[['home','今日教学']]],
 ['students','学生与目标',[['students','学生档案'],['planning','成长与目标'],['paths','学习安排'],['memory','学习札记']]],
 ['assign','备课与任务',[['assign','设计与布置'],['materials','资料阅读'],['resources','练习与题库'],['agent','教学助手'],['retrieval','检索对照']]],
 ['review','作业与反馈',[['review','作业评阅'],['writing','写作与修订']]],
 ['policy','教学方法',[['policy','学习设计与规则'],['policy-lab','案例与验收'],['methods','方法资产']]]];
 const self=[['home','自学首页',[['home','学习概览']]],
 ['materials','读资料与提问',[['materials','我的资料'],['agent','学习助手'],['retrieval','检索对照'],['policy','学习方法']]],
 ['tasks','练习与作品',[['tasks','我的练习'],['practice','英语练习'],['writing','写作与修订']]],
 ['feedback','反馈与复习',[['feedback','作品与反馈'],['reviews','复习安排'],['memory','学习札记']]],
 ['planning','目标与安排',[['planning','成长与目标'],['paths','学习安排']]]];
 const student=[['home','学习首页',[['home','学习概览']]],
 ['tasks','我的任务',[['tasks','老师布置的任务']]],
 ['feedback','反馈与修订',[['feedback','任务反馈']]],
 ['planning','目标与安排',[['planning','老师的规划'],['paths','学习安排']]]];
 const utility=[['connections','配对与MCP'],['settings','模型与本机设置'],['guide','使用指南'],['features','功能清单']];
 const studentUtility=[['connections','我的老师'],['settings','模型与本机设置'],['guide','使用指南']];
 const utilities=mode=>mode==='student'?studentUtility:utility;
 function section(view,back,mode){
  if(mode==='student'&&['writing','materials','task','k12','practice','agent-job'].includes(view))return back==='feedback'?'feedback':'tasks';
  return view==='task'?back:view==='agent-job'?'agent':view;
 }
 function group(mode,view,back){const route=section(view,back,mode);return (mode==='teacher'?teacher:mode==='student'?student:self).find(g=>g[2].some(([r])=>r===route))||
  (['academic','k12'].includes(route)?['academic','学科与路线',[['academic','切换学科'],['k12','K12英语路线']]]:['settings','连接与设置',utilities(mode)]);}
 const api={teacher,self,student,utility,utilities,section,group,ownTasks:tasks=>tasks.filter(t=>t.origin!=='teacher')};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ExperienceState=api;
})(typeof window==='undefined'?this:window);
