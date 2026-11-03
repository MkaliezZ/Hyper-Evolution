"use strict";
// Human guides only: no model calls, business writes or role changes.
function usageGuideBlock(block){
 const [kind,value,rows]=block;
 if(kind==='p')return `<p>${h(value)}</p>`;
 if(kind==='h')return `<h3>${h(value)}</h3>`;
 if(kind==='steps')return `<ol>${value.map(text=>`<li>${h(text)}</li>`).join('')}</ol>`;
 return `<div class="usage-guide-table"><table><thead><tr>${value.map(text=>`<th scope="col">${h(text)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(text=>`<td>${h(text)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function usageGuideBody(manual){
 return `<section class="card usage-guide-index"><p class="small muted">使用说明 v${h(UsageGuides.version)} · ${h(UsageGuides.date)} · ${h(UsageGuides.edition)}</p><h2>第一次从第一节开始 用到哪里再查哪里</h2><nav aria-label="使用说明目录">${manual.chapters.map((chapter,i)=>`<button class="btn ghost small" data-action="usage-jump" data-section="usage-chapter-${i}">${String(i+1).padStart(2,'0')} ${h(chapter.title)}</button>`).join('')}</nav></section>`+
 manual.chapters.map((chapter,i)=>`<section class="card usage-guide-chapter" id="usage-chapter-${i}"><h2>${String(i+1).padStart(2,'0')} ${h(chapter.title)}</h2>${chapter.blocks.map(usageGuideBlock).join('')}</section>`).join('');
}
document.addEventListener('click',event=>{const button=event.target.closest('[data-action="usage-jump"]');if(!button)return;const target=document.getElementById(button.dataset.section);if(target){target.scrollIntoView({behavior:'smooth',block:'start'});target.setAttribute('tabindex','-1');target.focus({preventScroll:true});}});
