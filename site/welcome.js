(function(){
'use strict';
const tag='v0.6.0-rc.2';
const roles={
 teacher:{
  title:'Enlighter 教师版：连接学生，带着完成一次学习。',
  intro:'先了解一位学生的现状与目标，再布置一个清楚的小任务，收到作品后发回具体反馈。',
  launch:'启动-Enlighter.cmd',
  setup:'向导会预选 Enlighter 教师版，确认教师身份、填写称呼，再选择学科与路线。',
  api:'配置教师自己的 API，供资料解释、候选备题和 AI 预审使用。先测试连接，通过后保存。',
  'pair-title':'生成学生配对码。',
  pair:'在“连接与设置 → 师生配对”点击“生成学生配对码”，把十二位码发给对应学生。双方保持程序在线。',
  'pair-check':'连接成功后，在“学生与目标”确认学生，再选择对应学科。配对码十分钟有效，过期重新生成。',
  'task-title':'布置一次任务，收到一份作品。',
  task:'从“备课与任务”准备资料、目标和评价标准，审校后布置。学生提交后，到“作业与反馈”打开实际作品，运行 AI 预审，修改并确认发布。',
  check:'学生按反馈修订后，查看变化，安排下一次练习或复测。成长规划从“学生与目标 → 成长与目标”梳理并明确分享。',
  mcp:'在教师本机“模型与本机设置”复制 MCP 配置，粘贴到教师自己的 Agent。先读取教师身份和当前学科，再处理所选学生。',
  'agent-prompt':'先读取超维伴学本机教师身份和已配对学生。让我选择一位学生，再整理其近期已提交作品，准备一份可编辑的反馈草稿。',
  manual:'enlighter',brand:'Enlighter'
 },
 student:{
  title:'Evolver 学生版：跟着老师完成一次学习。',
  intro:'先连接老师，再领取任务。完成后查看反馈，按下一步继续。',
  launch:'启动-Evolver.cmd',
  setup:'向导会预选 Evolver 学生版，确认身份、填写称呼，再选择学科与路线。',
  api:'任务中的资料解释或写作 AI 帮助使用你自己的 API。完成任务、提交作品和查看教师反馈，可以先从本机功能开始。',
  'pair-title':'输入老师的配对码。',
  pair:'在“连接与设置 → 我的老师”点击“输入老师配对码”，输入老师生成的十二位配对码。双方保持程序在线。',
  'pair-check':'连接成功后，选中对应学科，在“我的任务”领取老师布置的任务。配对码十分钟有效，过期请老师重新生成。',
  'task-title':'交一份作品，接着改一次。',
  task:'读清任务要求和评价标准，完成后点击提交。到“反馈与修订”查看建议，再修改并提交。',
  check:'在“目标与安排”查看老师分享的规划和学习安排。保存草稿后，记得在任务中明确点击提交。',
  mcp:'在学生本机“模型与本机设置”复制 MCP 配置，粘贴到自己的 Agent。先读取本机身份、学科和老师布置的任务。',
  'agent-prompt':'先读取超维伴学本机学生身份和我的任务，帮我理解一份待完成任务的要求，再引导我完成自己的回答。',
  manual:'evolver',brand:'Evolver'
 },
 self:{
  title:'Self-Evolver 自学版：从自己的问题和资料开始。',
  intro:'导入一份短资料，提出一个具体问题，做一次练习，再把反馈变成修订与复习。',
  launch:'启动-Self-Evolver.cmd',
  setup:'向导会预选 Self-Evolver 自学版，确认自主学习身份、填写称呼，再选择学科与路线。',
  api:'配置自己的模型 API。资料问答、练习草稿和自学作品反馈都使用这里的额度；先测试连接，再保存。',
  'pair-title':'直接开始，也能稍后连接老师。',
  pair:'自学可以直接从“读资料与提问”开始。加入一段自己的文字或图片资料，写清来源，提出这次想弄明白的问题。',
  'pair-check':'需要老师带学时，明确切换到 Evolver 学生版，在“我的老师”输入老师的配对码。老师的任务从学生版完成。',
  'task-title':'读、练、改，再安排一次复习。',
  task:'先读一段短资料，到“练习与作品”写下目标，选择练习方法和评价标准，预览后开始。提交实际作品，再到“反馈与复习”查看 AI 建议并修订。',
  check:'记录这次最需要改进的一点，安排下一次复习，再换一份材料练习。自己的目标放在“目标与安排”。',
  mcp:'在自学版本机“模型与本机设置”复制 MCP 配置，粘贴到自己的 Agent。它会使用这份本机资料、任务和学习记录。',
  'agent-prompt':'先读取超维伴学本机自学身份、当前学科和我选的资料，围绕一个小目标设计一次短练习，先让我看设计，再引导我完成。',
  manual:'self-evolver',brand:'Self-Evolver'
 }
};
function roleFromSearch(search){const v=new URLSearchParams(search).get('role');return Object.hasOwn(roles,v)?v:'student';}
function packageName(role){return 'Hyper-Evolution-'+roles[Object.hasOwn(roles,role)?role:'student'].brand+'-Windows-x64-'+tag+'.zip';}
if(typeof module!=='undefined'&&module.exports)module.exports={roles,roleFromSearch,packageName,tag};
if(typeof document==='undefined')return;
if(/^#(learn=|teacher$|student-entry$)/.test(location.hash)){location.replace('/cloud/'+location.hash);return;}
let selected=roleFromSearch(location.search);
const buttons=document.querySelectorAll('[data-role]');
function showRole(role,navigate){
 selected=Object.hasOwn(roles,role)?role:'student';
 buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.role===selected)));
 Object.entries(roles[selected]).forEach(([key,value])=>{const node=document.getElementById('role-'+key);if(node&&key!=='manual')node.textContent=value;});
 document.getElementById('role-download').href='/downloads/'+packageName(selected);
 document.getElementById('role-download').textContent='下载 '+roles[selected].brand+' ↓';
 document.getElementById('role-manual').href='https://github.com/MkaliezZ/Hyper-Evolution/blob/main/docs/'+roles[selected].manual+'.md';
 document.getElementById('copy-status').textContent='';
 if(navigate){const url=new URL(location.href);url.searchParams.set('role',selected);url.hash='how';history.pushState(null,'',url);document.getElementById('how').scrollIntoView({behavior:'smooth',block:'start'});}
}
buttons.forEach(b=>b.addEventListener('click',()=>showRole(b.dataset.role,true)));
window.addEventListener('popstate',()=>showRole(roleFromSearch(location.search),false));
document.getElementById('copy-guide').addEventListener('click',async()=>{const u=new URL('/',location.origin);u.searchParams.set('role',selected);u.hash='how';const node=document.getElementById('copy-status');try{await navigator.clipboard.writeText(u.href);node.textContent='已复制 '+roles[selected].brand+' 教程链接';}catch(_){node.textContent='可复制浏览器地址，或使用旁边的三个教程链接。';}});
showRole(selected,false);
})();
