"use strict";
const $ = (s) => document.querySelector(s),
  h = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const labels = {
  diagnostic: "先做诊断",
  practice: "个性化补练",
  listening: "听力练习",
  retest: "未见题复测",
  writing: "写作与修订",
  speaking: "口语作品",
};
const stageNames = {
  application: "申请准备",
  predeparture: "行前准备",
  enrolled: "海外在读",
};
let access = localStorage.getItem("growth-access") || "",
  owner = sessionStorage.getItem("growth-owner") || "",
  catalog = null,
  dash = null,
  teacher = null,
  current = null,
  view = "home",
  teacherTab = "today",
  selected = "",
  files = [],
  recorder = null,
  recordStream = null,
  busy = false,
  objectURLs = [];
let currentRole = localStorage.getItem("growth-role") || "", pendingPairCode = "";
const uuid = () => crypto.randomUUID();
function chooseRole(role) { currentRole = role; localStorage.setItem("growth-role", role); }
function notify(message, error = false) {
  const t = $("#toast");
  t.textContent = message;
  t.className = "show" + (error ? " error" : "");
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => (t.className = ""), error ? 6500 : 3200);
}
async function api(path, data, admin = false, method) {
  const headers = {};
  if (admin) headers["X-Owner-Token"] = owner;
  else if (access) headers.Authorization = "Bearer " + access;
  let body;
  if (data instanceof FormData) body = data;
  else if (data !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(data);
  }
  let r;
  try {
    r = await fetch(path, {
      method: method || (data === undefined ? "GET" : "POST"),
      headers,
      body,
    });
  } catch (e) {
    throw Error("暂时连接不上，请检查服务是否运行；你的本地草稿仍保留。");
  }
  const value = await r
    .json()
    .catch(() => ({ error: "服务返回了无法读取的内容" }));
  if (!r.ok) {
    let error = Error(value.error || value.detail || "操作未完成，请稍后再试");
    error.status = r.status;
    throw error;
  }
  return value;
}
function revokeMedia() {
  objectURLs.forEach((u) => URL.revokeObjectURL(u));
  objectURLs = [];
  if (recordStream) recordStream.getTracks().forEach((t) => t.stop());
  recordStream = null;
  recorder = null;
}
function header() {
  const isTeacher = currentRole === "teacher";
  $("#header").innerHTML = `<div class="wrap header-inner"><button class="brand" data-action="home" aria-label="超维伴学首页"><span class="brand-mark" aria-hidden="true">✳</span><span><strong>超维伴学</strong><small>${currentRole ? (isTeacher ? "FOR TEACHERS · 教师空间" : "FOR STUDENTS · 学生空间") : "GROW BEYOND · LEARN WITH EVIDENCE"}</small></span></button><nav class="nav" aria-label="主导航">${currentRole ? `<button data-action="${isTeacher ? "teacher" : "student"}" class="active">${isTeacher ? "教师工作台" : "我的学习"}</button>` : ""}<button data-action="guide">使用指南</button>${isTeacher ? '<button data-action="agent">Agent 接入</button>' : ""}<button data-action="home">${currentRole ? "切换身份" : "选择身份"}</button></nav></div>`;
}
function shell(content) {
  $("#app").innerHTML =
    `<div class="wrap">${content}<footer><span>超维伴学 · 基于伴学 BASE</span><span>一次练习，一份证据，一步成长。 <button class="btn text small" data-action="guide">遇到问题？查看指南 ↗</button></span></footer></div>`;
  header();
}
function setView(v) {
  revokeMedia();
  view = v;
  history.replaceState(null, "", "#" + v);
  window.scrollTo(0, 0);
}
function home() {
  chooseRole(""); setView("home");
  shell(`<section class="role-welcome"><span class="eyebrow">WELCOME TO GROW BEYOND</span><h1>先选身份，<br>从适合你的地方开始。</h1><p class="intro">学生专心练习与提交，老师围绕作品给反馈。一个配对码，把下一步接起来。</p><div class="role-choices"><article class="role-card"><span class="num">01 / FOR STUDENTS</span><h2>我是学生</h2><p>输入老师的配对码，查看任务、完成练习、提交作业与录音，并查看反馈和复测。</p><button class="btn accent" data-action="student">进入学生空间 →</button></article><article class="role-card teacher-choice"><span class="num">02 / FOR TEACHERS</span><h2>我是老师</h2><p>验证教师身份，邀请学生配对，管理档案、布置练习、评阅作品和查看成长证据。</p><button class="btn" data-action="teacher">进入教师空间 →</button></article></div><div class="role-how"><b>第一次使用？</b><span>老师生成配对码 → 学生输入连接 → 布置与提交 → 反馈与修订</span><button class="btn text" data-action="demo">先体验学生示例 ↗</button></div><p class="small muted">托福 2026 · 雅思 Academic 机考 · 申请、行前与在读</p></section>`);
}
function studentEntry() {
  chooseRole("student"); setView("student-entry");
  shell(`<section class="page signin"><span class="eyebrow">FOR STUDENTS</span><h1>和老师连接，<br>也从自己的起点开始。</h1><div class="card"><h2>我有老师的配对码</h2><p>老师发来8位配对码后，输入即可连接。若老师已建立档案，会直接打开那份档案。</p><button class="btn accent" data-action="pair-student">输入配对码 →</button></div>${access ? '<div class="card"><h2>继续我的学习</h2><p>这个浏览器已保存你的学习入口，任务和历史作品会继续保留。</p><button class="btn" data-action="continue-student">打开我的学习空间 →</button></div>' : '<button class="btn ghost" data-action="enroll">还没有老师，先建立自己的学习档案</button>'}<p class="small muted">配对码只用一次；配对后本浏览器可继续学习。换设备时，使用自己保存的学习链接或向老师索取新码。</p></section>`);
}
function pairingModal() {
  openModal("输入老师的配对码", `<p>配对后，老师可以查看你的档案、任务与提交并给反馈。原有作品会保留。</p><form id="pair-form"><div class="field"><label for="pair-code">老师配对码</label><input class="input pairing-input" id="pair-code" name="code" placeholder="例如 ABCD-2345" required maxlength="20" autocapitalize="characters" autocomplete="off" spellcheck="false"></div><button class="btn accent" type="submit">连接老师 →</button></form><p class="small muted" style="margin-top:16px">配对码24小时有效，只能使用一次。过期或用过时，请向老师索取新码。</p>`);
}
function showPairCode(result) {
  openModal("把配对码发给对应学生", `<p>${result.student_name ? `专用于 <strong>${h(result.student_name)}</strong> 的档案；使用后旧学习链接失效。` : "邀请学生连接自己的档案，已有练习和作品会保留。"}</p><div class="pair-code-display">${h(result.code)}</div><p class="small muted">${h(result.teacher.name)} · 单次使用 · 有效至 ${new Date(result.expires*1000).toLocaleString()}</p><p>学生打开同一网站，选择“我是学生”→“输入配对码”。</p><input id="pair-share" type="hidden" value="${h('打开 '+location.origin+'，选择「我是学生」并输入配对码 '+result.code+'，连接'+result.teacher.name+'。配对码24小时有效，仅供你使用。')}"><div class="actions"><button class="btn accent" data-action="copy-pair">复制邀请说明</button><button class="btn ghost" data-action="revoke-code" data-id="${h(result.id)}">撤销这个码</button></div>`);
}
function openModal(title, body) {
  $("#modal-root").innerHTML =
    `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-label="${h(title)}"><button class="close" data-action="close" aria-label="关闭">×</button><h2>${h(title)}</h2>${body}</section></div>`;
  setTimeout(() => $(".modal input,.modal select,.modal button")?.focus(), 0);
}
function closeModal() {
  $("#modal-root").innerHTML = "";
}
function selects(exam = "ielts", stage = "application") {
  return `<div class="inline-grid"><div class="field"><label for="exam">考试路线</label><select id="exam" name="exam"><option value="ielts" ${exam === "ielts" ? "selected" : ""}>雅思 Academic · 机考</option><option value="toefl" ${exam === "toefl" ? "selected" : ""}>托福 iBT · 2026</option></select></div><div class="field"><label for="stage">留学阶段</label><select id="stage" name="stage">${Object.entries(
    stageNames,
  )
    .map(
      ([v, n]) =>
        `<option value="${v}" ${stage === v ? "selected" : ""}>${n}</option>`,
    )
    .join("")}</select></div></div>`;
}
function enrollment(demo = false, admin = false) {
  openModal(
    demo ? "用示例走一遍" : admin ? "建立学生档案" : "让我们认识一下你",
    `<p class="muted small">${demo ? "这是可操作的示例空间。你会依次体验诊断、补练、听力、反馈与复测；记录会明确标记为示例。" : "只需要称呼、路线和阶段，不必一次填完所有背景资料。"}</p><form id="enroll-form" data-demo="${demo}" data-admin="${admin}"><div class="field"><label for="name">${admin ? "学生称呼" : "怎么称呼你"}</label><input class="input" id="name" name="name" required maxlength="80" placeholder="例如：小林" value="${demo ? "示例同学" : ""}"></div>${selects()}<div class="field"><label for="goal">现在最想改善什么？<span class="muted">（选填）</span></label><input class="input" id="goal" name="goal" maxlength="1000" placeholder="例如：听清老师要求，写邮件时提出明确请求"></div><button class="btn accent" type="submit">${demo ? "进入示例空间" : admin ? "建立档案并生成配对码" : "建立档案，开始学习"} →</button></form>`,
  );
}
async function student() {
  chooseRole("student");
  if (!access) return studentEntry();
  dash = await api("/api/me");
  setView("student");
  renderStudent();
}
function side() {
  let done = new Set(
    dash.tasks.filter((t) => t.attempts.length).map((t) => t.purpose),
  );
  return `<aside class="side"><div class="side-title">我的学习路径</div>${["diagnostic", "practice", "listening", "retest"].map((p, i) => `<button data-action="start" data-purpose="${p}" class="${done.has(p) ? "done" : ""} ${dash.next === p ? "selected" : ""}"><span class="step-num">${done.has(p) ? "✓" : i + 1}</span>${labels[p]}</button>`).join("")}<hr><button data-action="start" data-purpose="writing">↗ 写作与修订</button><button data-action="start" data-purpose="speaking">◉ 口语作品</button><button data-action="goal">✳ 目标与机会准备</button><button data-action="guide">? 使用教程与实例</button></aside>`;
}
function renderStudent() {
  let p = dash.person,
    counts = dash.evidence;
  const nextCopy = {
    diagnostic: [
      "先花几分钟，认识你的起点。",
      "5个原创微练习题，先找一个可以改善的薄弱点。不把一次小测当成正式考试等级。",
    ],
    practice: [
      "针对上次的薄弱点，再练一小步。",
      "新的材料会保留同类技能要求。留意为什么错，而不只是记住正确选项。",
    ],
    listening: [
      "把练习放进真实声音里。",
      "先听懂关键要求，再看逐题依据。待审素材只能在示例空间体验。",
    ],
    retest: [
      "换一份新材料，看看能否独立完成。",
      "先不看提示，记录真实作答；对照前一次表现，检验这次练习是否帮到你。",
    ],
    writing: [
      "把学到的东西，用在自己的表达里。",
      "保留初稿和修订，让老师看到你的具体变化。",
    ],
  }[dash.next];
  shell(
    `<div class="page"><div class="page-title"><div><span class="eyebrow">YOUR LEARNING SPACE</span><h1>${h(p.name)}，今天从一个小目标开始。</h1><div class="task-meta"><span class="tag">${h(catalog.exams[p.exam].name)}</span><span class="tag">${stageNames[p.stage]}</span>${p.demo ? '<span class="tag orange">示例档案</span>' : ""}</div></div><div class="actions"><button class="btn text" data-action="refresh">↻ 同步进度</button><button class="btn text" data-action="logout-student">退出学习空间</button></div></div><section class="pair-status card"><div><span class="eyebrow">MY TEACHER</span><h3>${p.teacher ? h(p.teacher.name) : "还没有连接老师"}</h3><p class="small muted">${p.teacher ? "已配对 · 老师可以查看你的提交并给反馈。" : "你可以先自主练习，配对后老师才会看到你的档案和作品。"}</p></div><div class="actions">${p.teacher ? '<button class="btn text small" data-action="leave-pair">解除配对</button>' : '<button class="btn accent" data-action="pair-student">输入配对码</button>'}<button class="btn ghost small" data-action="save-my-link">保管学习入口</button></div></section>${p.demo ? '<div class="banner">你正在示例空间。可体验真实操作；待审录音明确作为流程体验，未经试听不算教学发布。<button class="btn text small" data-action="enroll">建立正式档案 →</button></div>' : ""}<div class="workspace">${side()}<div><section class="next-card"><div><span class="eyebrow">NEXT SMALL STEP</span><h2>${nextCopy[0]}</h2><p>${nextCopy[1]}</p></div><button class="btn" data-action="start" data-purpose="${dash.next}">${labels[dash.next]} →</button></section><div class="stats"><div class="stat"><b>${counts.completed}</b><span>已有提交的活动</span></div><div class="stat"><b>${counts.meets_criteria}</b><span>教师确认本次达标</span></div><div class="stat"><b>${counts.independent_transfer}</b><span>独立迁移证据</span></div></div>${dash.weak_skills.length ? `<div class="card"><h3>这次先关注</h3><div class="task-meta">${dash.weak_skills.map((s) => `<span class="tag orange">${h(catalog.skills[s] || s)}</span>`).join("")}</div><p class="small muted" style="margin-top:12px;margin-bottom:0">根据已有作答提出补练方向，不是对你能力的固定标签。</p></div>` : ""}<section class="card"><div class="section-head"><h3>我的任务与反馈</h3><span class="small muted">提交后在这里继续</span></div>${dash.tasks.length ? dash.tasks.slice().reverse().map(taskRow).join("") : '<div class="empty">还没有任务。点击上方“先做诊断”，就会得到第一份练习。</div>'}</section>${p.goal_plan.target ? `<section class="card"><h3>✳ ${h(p.goal_plan.target)}</h3><p class="small muted">机会价值与准备度分开看；计划不是已完成。</p>${p.goal_plan.gaps.map((g) => `<div class="task-row"><div><strong>${h(g.requirement)}</strong><p class="small muted">${h(g.gap)}<br>完成标准：${h(g.completion_standard)}</p><span class="tag">${h(g.evidence_status || "计划待执行，暂无作品证据")} · ${(g.evidence_refs || []).length}份证据</span></div><button class="btn soft small" data-action="start" data-purpose="${h(g.activity)}">去准备 →</button></div>`).join("")}<button class="btn text small" data-action="goal">调整目标与准备计划</button></section>` : ""}<p class="small muted">自动判分依据原文和明确答案；写作与口语由教师按量规评阅。成长看作品和迁移，不只看提交次数。</p></div></div></div>`,
  );
}
function taskRow(t) {
  let a = t.attempts.at(-1);
  let status =
    t.state !== "active"
      ? t.state === "paused"
        ? "已暂停"
        : "已归档"
      : !a
        ? "待完成"
        : a.evaluation.status === "pending"
          ? "等待教师反馈"
          : a.evaluation.judgement === "needs_revision"
            ? "请按反馈修订"
            : "可查看反馈";
  return `<div class="task-row"><div><h3>${h(t.pack.title)}</h3><div class="task-meta"><span class="tag">${labels[t.purpose]}</span><span class="tag ${a ? "green" : ""}">${status}</span>${t.attempts.length > 1 ? `<span class="tag">${t.attempts.length}次提交，初稿保留</span>` : ""}</div></div><button class="btn ghost small" data-action="open-task" data-id="${h(t.id)}">${a ? "查看反馈与作品" : "继续完成"} →</button></div>`;
}
async function start(purpose) {
  let existing = dash?.tasks.find(
    (t) => t.purpose === purpose && !t.attempts.length && t.state === "active",
  );
  if (!existing && ["writing", "speaking"].includes(purpose)) {
    existing = dash?.tasks
      .toReversed()
      .find(
        (t) =>
          t.purpose === purpose &&
          t.state === "active" &&
          t.attempts.length &&
          (t.attempts.at(-1).evaluation.status === "pending" ||
            t.attempts.at(-1).evaluation.judgement === "needs_revision"),
      );
  }
  if (existing) {
    current = await api("/api/activities/" + existing.id);
  } else
    current = await api("/api/activities", { purpose, request_key: uuid() });
  files = [];
  setView("study");
  renderStudy();
}
async function openTask(id) {
  current = await api("/api/activities/" + id);
  files = [];
  setView("study");
  renderStudy();
}
function questionHTML(i, index, answer = "") {
  let opts = i.kind === "tfng" ? ["TRUE", "FALSE", "NOT GIVEN"] : i.options;
  return `<section class="question"><div class="q-title"><span class="q-num">${index + 1} /</span>${h(i.prompt)}</div>${
    i.kind === "gap"
      ? `<input class="input" name="q_${h(i.id)}" aria-label="第${index + 1}题答案" maxlength="200" value="${h(answer)}" placeholder="输入答案，遵守题目字数要求" required>`
      : opts
          .map((o, n) => {
            let value = i.kind === "tfng" ? o : String.fromCharCode(65 + n);
            return `<label class="option"><input type="radio" name="q_${h(i.id)}" value="${value}" ${answer === value ? "checked" : ""} required><span>${i.kind === "tfng" ? "" : String.fromCharCode(65 + n) + ". "}${h(o)}</span></label>`;
          })
          .join("")
  }</section>`;
}
function renderStudy(revise = false) {
  let p = current.pack,
    a = current.attempts.at(-1);
  if (a && !revise) return renderFeedback();
  let cached;
  try {
    cached = JSON.parse(
      localStorage.getItem("growth-draft-" + current.id) || "{}",
    );
  } catch (e) {
    cached = {};
  }
  let previous = revise ? a.answer : {};
  let draft = { ...previous, ...cached };
  let body = p.items.length
    ? `<div>${p.items.map((q, i) => questionHTML(q, i, draft.answers?.[q.id])).join("")}</div>`
    : `<div><div class="field"><label for="work-text">${current.purpose === "speaking" ? "可补充文字说明或自己的转写" : "我的英文作品"}</label><textarea id="work-text" name="text" class="english" maxlength="12000" placeholder="在这里独立完成初稿。你的文字会自动保存在当前浏览器。">${h(draft.text || "")}</textarea><small id="word-count" class="muted">写作字数与格式只是提示，内容仍需按量规评阅。</small></div><div class="actions"><button class="btn ghost" data-action="record" type="button">◉ 开始录音</button><label class="btn soft" for="file-input">上传作品或录音</label><input id="file-input" type="file" class="sr-only" accept="audio/*,.pdf,.png,.jpg,.jpeg,.txt"><span class="small muted">每份不超过12MB</span></div><audio id="record-preview" controls hidden></audio><div id="file-list"></div></div>`;
  shell(
    `<div class="page"><div class="study-head"><button class="btn text" data-action="student">← 返回学习空间</button><span class="tag">${labels[current.purpose]} · ${h(p.task_type)}</span></div><h1 style="font-size:32px;margin-bottom:14px">${h(p.title)}</h1><p class="muted small">${h(p.instructions)}</p>${current.state !== "active" ? '<div class="banner error">活动已暂停或归档。请联系教师安排下一步，已有作品与反馈保留。</div>' : ""}${p.status !== "ready" ? '<div class="banner">示例使用待审材料：可体验流程，尚未经过教师完整试听与逐题放行。</div>' : ""}<form id="answer-form"><div class="study-grid"><div>${p.audio ? `<div class="audio-card"><span class="eyebrow">LISTEN FIRST</span><h3>先听，再作答。</h3><p class="small muted">精听练习模式 · 可以重听 · 提交后查看文字依据</p><audio id="lesson-audio" controls preload="metadata"></audio><div id="audio-status" class="small muted">正在载入录音…</div></div>` : ""}${p.stimulus ? `<article class="reading"><h2>${p.audio ? "任务说明" : "Read & understand"}</h2>${h(p.stimulus)}</article>` : ""}<p class="small muted" style="margin-top:16px">来源：${h(p.source?.title || "原创练习")}<br>${h(p.source?.calibration || p.source?.voice || "练习表现不等于正式考试成绩")}</p>${p.rubric ? `<div class="card"><h3>老师会关注什么</h3>${p.rubric.map((r) => `<p class="small">— ${h(r)}</p>`).join("")}</div>` : ""}</div>${body}</div><div class="submit-bar"><div><span id="answer-progress">${p.items.length ? "完成全部题目后再提交" : "初稿、修订和录音都会保留"}</span>${current.purpose === "retest" ? '<label class="check-label"><input type="checkbox" name="independent" required>我独立完成了这份新材料，没有查看提示或答案</label>' : ""}</div><button type="submit" class="btn accent" ${current.state !== "active" ? "disabled" : ""}>${revise ? "提交这次修订" : "提交，查看反馈"} →</button></div></form></div>`,
  );
  if (p.audio) loadAudio(p.audio, "#lesson-audio");
  files = previous.files ? [...previous.files] : [];
  renderFiles();
}
async function loadAudio(id, target) {
  try {
    const headers = target.startsWith("#teacher")
      ? { "X-Owner-Token": owner }
      : { Authorization: "Bearer " + access };
    let r = await fetch("/api/audio/" + encodeURIComponent(id), { headers });
    if (!r.ok) throw Error((await r.json()).error);
    let blob = await r.blob(),
      url = URL.createObjectURL(blob);
    objectURLs.push(url);
    let node = $(target);
    if (node) {
      node.src = url;
      if ($("#audio-status"))
        $("#audio-status").textContent =
          "录音已载入。请戴上耳机，在安静环境开始。";
    }
  } catch (e) {
    if ($("#audio-status")) $("#audio-status").textContent = e.message;
    notify(e.message, true);
  }
}
function renderFeedback() {
  let a = current.attempts.at(-1),
    ev = a.evaluation,
    auto = a.automatic,
    p = current.pack;
  let next = {
    diagnostic: "practice",
    practice: "listening",
    listening: "retest",
    retest: "writing",
    writing: "speaking",
    speaking: "retest",
  }[current.purpose];
  shell(
    `<div class="page"><div class="study-head"><button class="btn text" data-action="student">← 返回学习空间</button><span class="tag green">第${current.attempts.length}次提交已保存</span></div><div class="result-hero">${auto ? `<div class="score-circle"><b>${auto.score}<span class="small"> / ${auto.total}</span></b><small>本次微练习</small></div>` : '<div class="score-circle"><b>✓</b><small>作品已收到</small></div>'}<div><span class="eyebrow">FEEDBACK, THEN A FRESH START</span><h1 style="font-size:32px;margin:8px 0">${auto ? "先看为什么，再看下一步。" : "让反馈，落在你的作品上。"}</h1><p class="muted small">${h(ev.comment)}</p></div></div>${ev.status === "pending" ? '<div class="banner">老师可以在工作台直接看到这份作品。内容与发音仍待教师评阅，自动结构提示不代表达标。</div>' : ""}${ev.review_state === "confirmed" ? `<div class="card"><h3>教师反馈</h3><p>${h(ev.comment)}</p><p><strong>下一步：</strong>${h(ev.next_step)}</p><div class="task-meta"><span class="tag ${ev.judgement === "meets_criteria" ? "green" : "orange"}">${ev.judgement === "meets_criteria" ? "教师确认本次达标" : ev.judgement === "needs_revision" ? "需要修订" : "仅反馈，尚未认定达标"}</span>${ev.scores ? ev.scores.map((s) => `<span class="tag">${h(s.label)} ${s.score}/${s.max_score}</span>`).join("") : ""}</div></div>` : ""}<div class="study-grid"><section class="card"><h3>${auto ? "逐题反馈与原文依据" : "我的作品"}</h3>${auto ? auto.items.map((r, i) => `<div class="feedback-item"><span class="tag ${r.correct ? "green" : "red"}">${r.correct ? "✓ 正确" : "↗ 需要再看"} · 第${i + 1}题</span><p style="margin-top:10px">我的答案：${h(r.answer)}　参考答案：${h(r.accepted.join(" / "))}</p><blockquote>${h(r.evidence)}</blockquote><p>${h(r.explanation)}</p></div>`).join("") : `<article class="reading" style="border:0;padding:10px 0;font-size:16px">${h(a.answer.text || "已提交录音或附件，请老师结合文件评阅。")}</article>${(a.answer.files || []).map((id) => `<button class="btn soft small" data-action="file" data-id="${h(id)}">打开提交附件</button>`).join("")}`}</section><div><section class="card"><h3>这次先带走一个方法</h3><p>${h(auto?.weak_skills.includes("contradiction") ? "FALSE需要原文明确反对；NOT GIVEN是没有足够信息。不要用常识替原文补答案。" : auto?.weak_skills.length ? "找到原文中真正决定答案的那句话，区分“听起来合理”和“有证据支持”。" : "把有效的方法用到下一份新材料中。原题会了，还需要验证能否独立迁移。")}</p><p class="small muted">${h(ev.next_step || "根据反馈修改，再完成新任务。")}</p><div class="actions"><button class="btn accent" data-action="next" data-purpose="${next}">${labels[next]} →</button><button class="btn ghost" data-action="revise">修改本次作答</button></div></section><section class="card"><h3>修改前后，都保留</h3>${current.attempts.map((x, i) => `<details ${i === current.attempts.length - 1 ? "open" : ""}><summary>第${i + 1}次提交 · ${new Date(x.created).toLocaleString("zh-CN")}</summary><p>${h(x.automatic ? x.automatic.score + "/" + x.automatic.total + "；" + x.evaluation.comment : x.answer.text || "已提交作品附件")}</p>${x.review_history.length ? `<p>${x.review_history.length}条教师评阅历史已保留。</p>` : ""}</details>`).join("")}<p class="small muted" style="margin-top:18px">得分是这份材料上的表现。长期能力和考试成绩，需要更多独立证据。</p></section>${p.transcript ? `<details><summary>查看听力原文</summary><article class="reading">${h(p.transcript)}</article></details>` : ""}</div></div></div>`,
  );
}
async function teacherPage() {
  chooseRole("teacher");
  setView("teacher");
  if (!owner) {
    shell(
      `<div class="page signin"><span class="eyebrow">FOR TEACHERS</span><h1>学生的下一步，<br>从你的反馈开始。</h1><div class="card"><form id="teacher-login"><div class="field"><label for="owner-token">教师访问口令</label><input class="input" id="owner-token" type="password" name="token" required autocomplete="off" placeholder="输入本实例的教师口令"><small>首次启动时，口令保存在服务提示的 owner-token.txt。只交给教师，不要发给学生。</small></div><button class="btn accent" type="submit">进入教师工作台 →</button></form></div><p class="small muted">学生无需教师口令。建好档案后，把专属学习链接发给对应学生即可。</p><button class="btn text" data-action="guide">查看教师首次使用教程 →</button></div>`,
    );
    return;
  }
  try {
    teacher = await api("/api/teacher", undefined, true);
  } catch (error) {
    if (error.status === 403) {
      owner = "";
      sessionStorage.removeItem("growth-owner");
      await teacherPage();
      notify("教师口令已失效，请重新输入", true);
      return;
    }
    throw error;
  }
  renderTeacher();
}

function renderTeacher() {
  const students = teacher.learners;
  selected = students.some((d) => d.person.id === selected)
    ? selected
    : students[0]?.person.id || "";
  const student = students.find((d) => d.person.id === selected);
  const pending = students.flatMap((d) =>
    d.tasks
      .filter(
        (t) =>
          t.attempts.length &&
          t.attempts.at(-1).evaluation.status === "pending",
      )
      .map((t) => ({ student: d.person, task: t })),
  );
  const needReview = teacher.resources.filter(
    (p) => p.status !== "ready",
  ).length;
  const meta = {
    today: [
      "教学待办",
      "今天，先处理这些学习进展。",
      "先看学生的提交，再决定反馈和下一步。",
    ],
    students: [
      "学生与作业",
      "围绕一位学生，把下一步接起来。",
      "档案、任务、提交与反馈，留在同一份记录里。",
    ],
    resources: [
      "题库与试听",
      "题目有依据，声音也要过关。",
      "先核对，再放行。未经审核的素材不进入正式学生练习。",
    ],
  }[teacherTab] || [
    "学生与作业",
    "围绕一位学生，把下一步接起来。",
    "档案、任务、提交与反馈，留在同一份记录里。",
  ];
  const rail = `<aside class="teacher-rail"><div class="rail-label">${h(teacher.teacher.name)} · 教师工作区</div><button class="btn text small" data-action="teacher-name">设置老师称呼</button><nav class="rail-links" aria-label="教学工作导航">${[
    ["today", "教学待办", "01"],
    ["students", "学生与作业", "02"],
    ["resources", "题库与试听", "03"],
  ]
    .map(
      ([tab, label, num]) =>
        `<button data-action="teacher-tab" data-tab="${tab}" class="${teacherTab === tab ? "active" : ""}"><span>${label}</span><small>${num}</small></button>`,
    )
    .join(
      "",
    )}<button data-action="guide"><span>使用教程与实例</span><small>↗</small></button></nav><p class="rail-note">把精力放在学生的作品上。<br>每次反馈，都连接下一步。</p><button class="btn text small" data-action="logout-teacher">退出教师空间</button></aside>`;
  let content;
  if (teacherTab === "today") {
    content = `<div class="work-summary"><span><b>${pending.length}</b> 份作品等待反馈</span><span><b>${students.length}</b> 份学生档案</span><span><b>${needReview}</b> 份题包尚待审核</span></div>
    <div class="work-queues"><section class="card"><div class="queue-heading"><h2>先给反馈</h2><span class="tag">${pending.length} 项</span></div>${pending.length ? pending.map(({ student, task }) => `<div class="task-row"><div><h3>${h(student.name)} · ${labels[task.purpose]}</h3><p class="small muted">${h(task.pack.title)}</p></div><button class="btn accent small" data-action="review-work" data-learner="${student.id}" data-id="${task.id}">查看作品 →</button></div>`).join("") : `<div class="quiet-empty"><span class="empty-mark">✓</span><h3>目前没有待评阅的作品。</h3><p>学生提交写作或口语后，会出现在这里。<br>也可以到学生档案里查看已完成的诊断与复测。</p><button class="btn text small" data-action="teacher-tab" data-tab="students">查看学生与作业 →</button></div>`}</section>
    <section class="card"><div class="queue-heading"><h2>接上下一步</h2><span class="small muted">按学习进展继续</span></div>${
      students.length
        ? students
            .slice(0, 5)
            .map(
              (d) =>
                `<div class="task-row"><div><h3>${h(d.person.name)} ${d.person.demo ? '<span class="tag orange">示例</span>' : ""}</h3><p class="small muted">${stageNames[d.person.stage]} · ${h(catalog.exams[d.person.exam].name)}<br>建议继续：${labels[d.next]}</p></div><button class="btn ghost small" data-action="open-student" data-id="${d.person.id}">打开档案 →</button></div>`,
            )
            .join("")
        : '<div class="quiet-empty"><h3>先认识第一位学生。</h3><p>发出配对码，让学生连接自己的档案，<br>或先建立档案，再发专属配对码。</p><button class="btn accent" data-action="new-student">建立学生档案 →</button></div>'
    }</section></div>
    <section class="review-strip"><div><span class="eyebrow">A SMALL QUALITY CHECK, BEFORE THE NEXT TASK</span><h3>首批听力，先把质量关。</h3><p>完整试听并逐题核对题目、原文和答案。已经下载，不代表已经适合布置。</p></div><button class="btn ghost" data-action="teacher-tab" data-tab="resources">去试听与审核 →</button></section>`;
  } else if (teacherTab === "resources" || teacherTab === "import") {
    content =
      resourcesHTML() +
      `<details class="advanced-import"><summary>已有 Agent 生成的题包？在这里导入草稿</summary><p class="small muted">这是进阶入口。日常教学直接在学生档案里安排活动即可；导入草稿仍须逐题审校。</p><form id="pack-import"><div class="field"><label for="pack-json">题包JSON<textarea id="pack-json" name="pack" required placeholder="粘贴Agent按考试蓝图生成的题包JSON"></textarea></label></div><button class="btn ghost">保存待审草稿</button></form><button class="btn text small" data-action="agent">查看Agent接入说明 →</button></details>`;
  } else {
    content = pairingInvitations() + `<div class="teacher-layout"><aside><div class="side-title">已配对学生 · 同名保持独立</div><div class="student-list">${students.map((d) => `<button class="student-entry ${d.person.id === selected ? "selected" : ""}" data-action="select-student" data-id="${d.person.id}"><strong>${h(d.person.name)}</strong>${d.person.demo ? ' <span class="tag orange">示例</span>' : ""}<small>${stageNames[d.person.stage]} · ${d.person.exam.toUpperCase()}</small><small>${d.tasks.filter((t) => t.attempts.length).length}项已提交</small></button>`).join("") || '<div class="empty">还没有学生。先建立一份档案。</div>'}</div></aside><div>${student ? teacherStudentHTML(student) : '<div class="card teacher-empty"><span class="brand-mark">✳</span><h2>先认识一位学生。</h2><p class="muted">邀请学生输入配对码，或先建档再发专属配对码，就能开始布置与评阅。</p><button class="btn accent" data-action="new-student">建立第一份档案 →</button></div>'}</div></div>`;
  }
  shell(
    `<div class="page teacher-shell">${rail}<section class="teacher-content"><div class="work-status"><span class="sync-dot"></span>资料已同步 · ${h(teacher.teacher.name)} · 已配对学生可见</div><div class="page-title"><div><span class="eyebrow">GROW BEYOND / ${meta[0]}</span><h1>${meta[1]}</h1><p class="muted">${meta[2]}</p></div><div class="actions"><button class="btn ghost small" data-action="teacher">↻ 刷新资料</button><button class="btn accent small" data-action="invite-student">＋ 邀请学生配对</button><button class="btn ghost small" data-action="new-student">建立学生档案</button></div></div>${content}</section></div>`,
  );
}
function pairingInvitations() {
  const active=(teacher.pair_codes || []).filter(c=>c.state==="active").slice(0,5);
  return `<section class="card pair-invitations"><div class="section-head"><div><h3>用配对码连接学生</h3><p class="small muted">学生已有档案时，直接发邀请；还没建档，也可以由你先建立档案再发专属配对码。每个码单次使用，24小时有效。</p></div><button class="btn accent small" data-action="invite-student">生成邀请配对码</button></div>${active.map(c=>`<div class="task-row"><span class="small">${c.learner_id ? h(teacher.learners.find(x=>x.person.id===c.learner_id)?.person.name || "指定档案") : "学生邀请"} · 待使用 · ${new Date(c.expires*1000).toLocaleString()}到期</span><button class="btn text small" data-action="revoke-code" data-id="${h(c.id)}">撤销</button></div>`).join("")}</section>`;
}
function teacherStudentHTML(d) {
  let p = d.person;
  return `<section class="card"><div class="section-head"><div><h2 style="margin:0">${h(p.name)}</h2><span class="small muted">${h(catalog.exams[p.exam].name)} · ${stageNames[p.stage]}</span></div><div class="actions"><button class="btn ghost small" data-action="model-draft">按错因生成模型草稿</button><button class="btn ghost small" data-action="edit-profile">编辑档案</button><button class="btn accent small" data-action="personal-pair">学生配对码</button><button class="btn text small" data-action="student-link">备用学习链接</button><button class="btn text small" data-action="unpair-student">解除配对</button></div></div><p><strong>当前目标：</strong>${h(p.profile.goal || "尚未填写，可以和学生一起确定一个小目标。")}</p>${p.notes ? `<p class="small muted">教师备注：${h(p.notes)}</p>` : ""}<div class="task-meta"><span class="tag">已提交 ${d.evidence.completed} 项</span><span class="tag green">本次达标 ${d.evidence.meets_criteria} 项</span><span class="tag">迁移核验 ${d.evidence.independent_transfer} 项</span></div><div class="actions" style="margin-top:20px"><select id="assign-purpose" aria-label="要安排的活动" style="width:auto">${Object.entries(
    labels,
  )
    .map(([v, n]) => `<option value="${v}">${n}</option>`)
    .join(
      "",
    )}</select><select id="assign-resource" aria-label="选择题包" style="width:auto;max-width:260px"><option value="">自动按近期错因出题</option>${teacher.resources
    .filter((r) => r.exam === p.exam && r.status === "ready")
    .map((r) => `<option value="${h(r.id)}">${h(r.title)}</option>`)
    .join(
      "",
    )}</select><button class="btn soft" data-action="assign">安排给这位学生 →</button></div><p class="small muted" style="margin:10px 0 0">把配对码发给对应学生；教师口令只留在教师端。配对码使用一次后失效，学生作品会继续保留。</p></section><section class="card"><h3>任务、提交与反馈</h3>${
    d.tasks
      .slice()
      .reverse()
      .map((t) => {
        let a = t.attempts.at(-1);
        return `<div class="task-row"><div><h3>${h(t.pack.title)}</h3><div class="task-meta"><span class="tag">${labels[t.purpose]}</span><span class="tag ${a?.evaluation.status === "pending" ? "orange" : ""}">${!a ? "尚未提交" : a.evaluation.status === "pending" ? "待教师评阅" : "已有反馈"} · ${t.attempts.length}次提交</span><span class="tag">${t.state === "active" ? "进行中" : t.state === "paused" ? "已暂停" : "已归档"}</span></div></div><div class="actions">${a ? `<button class="btn accent small" data-action="review-work" data-id="${t.id}">查看与评阅</button>` : ""}<button class="btn ghost small" data-action="state" data-id="${t.id}" data-state="${t.state === "active" ? "paused" : "active"}" ${t.state === "archived" ? "disabled" : ""}>${t.state === "active" ? "暂停" : "恢复"}</button></div></div>`;
      })
      .join("") ||
    '<div class="empty">还没有活动。先安排“诊断”，再按作答选择补练。</div>'
  }</section>${p.goal_plan.target ? `<section class="card"><h3>投石问路 · 目标差距</h3><p>${h(p.goal_plan.target)}</p>${p.goal_plan.gaps.map((g) => `<p class="small">${h(g.requirement)} → ${h(g.gap)} → ${h(g.completion_standard)}<br><span class="muted">${h(g.evidence_status || "计划待执行")}</span></p>`).join("")}<p class="small muted">完成活动只是新增证据，准备度须结合新作品回评。</p></section>` : ""}`;
}
function resourcesHTML() {
  return `<div class="banner neutral">下载与解码通过不等于教学通过。逐题检查答案依据，完整试听后再放行；修改题包会撤销原审核。</div>${teacher.resources.length ? teacher.resources.map((p) => `<section class="card"><div class="section-head"><div><h3>${h(p.title)}</h3><div class="task-meta"><span class="tag">${p.exam.toUpperCase()} · ${h(p.task_type)}</span><span class="tag ${p.status === "ready" ? "green" : "orange"}">${p.status === "ready" ? "已审核可安排" : "待审，正式学生不可使用"}</span><span class="tag">${p.items.length}题</span></div></div><button class="btn ghost small" data-action="review-pack" data-id="${h(p.id)}">预览与审核 →</button></div><p class="small muted">${h(p.source.title)} · ${h(p.source.voice || p.source.kind)}${p.review ? " · 审核人：" + h(p.review.reviewer) : ""}</p></section>`).join("") : '<div class="card"><h2>还没有导入素材。</h2><p>本地安装后运行资源导入脚本，即可带入前期下载的配套题目与录音。原始题册与录音不随源码公开分发。</p><pre>python scripts/import_materials.py --source ../materials</pre></div>'}`;
}
function guide() {
  setView("guide");
  shell(
    `<div class="page guide"><span class="eyebrow">A GUIDE FOR YOUR FIRST STEP</span><h1>不用研究系统，<br>照着做一次就会了。</h1><div class="tabs"><button data-action="guide-student" class="active">学生怎么用</button><button data-action="guide-teacher">教师怎么用</button><button data-action="demo">直接体验示例 →</button></div><div id="guide-body">${studentGuide()}</div><section class="section"><h2>三个留学阶段，三个具体例子。</h2><div class="card"><h3>申请 · 小林在准备雅思</h3><p>诊断发现分不清FALSE与NOT GIVEN → 补练“反证/未提及” → 听力定位修正信息 → 新材料独立复测。对比依据，不把背熟原题当作进步。</p><button class="btn text" data-action="demo" data-exam="ielts" data-stage="application">按这个场景体验 →</button></div><div class="card"><h3>行前 · 小夏即将入学</h3><p>托福新版日常信息阅读 → 听懂校园通知 → 给协调员写邮件提出请求 → 教师指出遗漏细节 → 修订后完成另一情境。</p><button class="btn text" data-action="demo" data-exam="toefl" data-stage="predeparture">按这个场景体验 →</button></div><div class="card"><h3>在读 · 想参与导师的小组</h3><p>把目标拆成“听懂要求、提出问题、支持观点”三个差距 → 安排听力、邮件和口语作品 → 用新提交与教师评价回看准备度。计划不算成果。</p><button class="btn text" data-action="demo" data-exam="ielts" data-stage="enrolled">按这个场景体验 →</button></div></section><h2>常见问题</h2><details><summary>配对码和学习链接有什么区别？</summary><p>配对码用于首次连接老师或领取老师建立的档案，24小时内单次有效。学习链接用于保留自己的访问入口，可在学生空间“保管学习入口”复制。换设备时使用自己的链接；遗失后请老师为同一档案生成新码。</p></details><details><summary>解除配对会删除作业吗？</summary><p>不会。作品、提交与反馈保留，老师立即失去继续查看与评阅的权限。重新连接同一老师后可继续原档案；不同档案不会自动合并。</p></details><details><summary>学生怎么把作业交给老师？</summary><p>先选择学生身份并输入老师的配对码，完成任务后点“提交”。不用另外发送截图；老师在同一个实例的工作台就能看到提交。每次修订作为新一次提交保留。</p></details><details><summary>老师评阅后，学生在哪里看？</summary><p>回到学习空间的“我的任务与反馈”，打开对应任务。页面会定期同步，也可点击“同步进度”。教师反馈、下一步、分项评价和修订历史都在任务内。</p></details><details><summary>为什么录音需要先审核？</summary><p>文件能播放并不保证声音自然、原文一致和答案有据。教师在“题库与试听审核”完整听过并逐题核对后再放行。示例空间允许明确标记的待审材料，正式学生不开放。</p></details><details><summary>可以看到其他学生的资料吗？</summary><p>不可以。学习入口只授权一个学生。教师另有口令；链接可重新生成使旧链接失效。首次部署仍需配置HTTPS、备份与正式账号策略。</p></details><details><summary>这里的分数是托福或雅思正式成绩吗？</summary><p>不是。显示本次微练习正确数和教师量规反馈，没有经过官方等值标定，也不把两次练习认定为长期能力提升。</p></details><details><summary>录音按钮不工作，怎么办？</summary><p>请在HTTPS或本机localhost打开，并允许麦克风。也可在手机或录音软件录好，再上传MP3、M4A、WAV或WebM。浏览器支持与系统授权可能影响录音；文字草稿会保留。</p></details><details><summary>个性化出题真的调用了AI吗？</summary><p>默认使用本地语义模板生成新的、答案有依据的微练习，按错因安排任务，不会假装调用模型。Agent可通过MCP读取蓝图与学习证据、生成原创题、保存草稿，由教师审核后安排给学生。</p></details></div>`,
  );
}
function studentGuide() {
  return [
    [
      "进入学习空间",
      "首页选择“我是学生”，输入老师发来的配对码。老师已建档时直接进入；否则先填写称呼、考试路线和阶段再完成配对。没有老师也可先自主练习。",
    ],
    [
      "从“现在做什么”开始",
      "点击首页推荐任务。诊断尽量独立完成，不确定的题也可以先按自己的判断作答。",
    ],
    [
      "提交后，看具体依据",
      "逐题看原文证据与解析；作品等待教师反馈。按反馈修改，系统保留初稿。",
    ],
    [
      "换新材料，独立复测",
      "完成补练与听力后，做一份未见材料。把方法带走，而不只是记住答案。",
    ],
  ]
    .map(
      ([a, b], i) =>
        `<div class="guide-step"><span class="number">0${i + 1}</span><div><h3>${a}</h3><p class="muted">${b}</p></div></div>`,
    )
    .join("");
}
function teacherGuide() {
  return [
    [
      "打开教师工作台",
      "本机首次启动后，从启动信息指向的owner-token.txt取得教师口令登录。学生不需要也不应获得这个口令。",
    ],
    [
      "建档并发送专属链接",
      "先设置学生看到的老师称呼。点击“邀请学生配对”，复制配对码给一位学生；也可先“建立学生档案”，再发该档案的专属配对码。同名档案不自动合并。",
    ],
    [
      "审核内容，再安排任务",
      "在题库中预览题目与答案、完整试听录音，写审核依据并放行。随后在学生档案里安排任务。",
    ],
    [
      "看提交，给反馈，跟进修订",
      "打开“查看与评阅”，指出作品中的具体表现、差距和下一步；评分为可选，明确区分仅反馈、需修订与本次达标。",
    ],
    [
      "验证迁移，保留证据",
      "新情境中独立完成且经教师确认达标后，可记录迁移核验。暂停任务立即限制新提交，已有记录保留。",
    ],
  ]
    .map(
      ([a, b], i) =>
        `<div class="guide-step"><span class="number">0${i + 1}</span><div><h3>${a}</h3><p class="muted">${b}</p></div></div>`,
    )
    .join("");
}
function agentPage() {
  setView("agent");
  shell(`<div class="page guide"><span class="eyebrow">ONE SERVICE, TWO WAYS TO WORK</span><h1>网页给人用，<br>MCP 给 Agent 用。</h1><p class="muted">教师、学生与Agent共享同一套档案、任务与反馈。Agent是教师授权的工作入口，不是学生账号。</p><div class="card"><h3>远程 / HTTP MCP</h3><p class="small">服务已经提供Streamable HTTP接口。部署前使用本机地址；部署后换成服务器的HTTPS域名。</p><pre>${h(location.origin)}/mcp/
Authorization: Bearer &lt;本实例教师口令&gt;</pre><p class="small muted">不要把教师口令写进学生链接、Git仓库或公开文档。</p></div><div class="card"><h3>本机 / stdio MCP</h3><pre>{
  "mcpServers": {
    "hyper-growth": {
      "command": "&lt;项目绝对路径&gt;/.venv/Scripts/python.exe",
      "args": ["-m", "growth.mcp_server"],
      "env": {
        "PYTHONPATH": "&lt;项目绝对路径&gt;/src",
        "BASE_DATA": "&lt;与网页相同的数据目录绝对路径&gt;",
        "PYTHONUTF8": "1"
      }
    }
  }
}</pre></div><h2>给 Agent 一条可以直接执行的任务</h2><div class="card"><p id="agent-example">先调用 get_context 读取托福2026与雅思蓝图，再读取我指定学生的 get_student 和 prepare_generation。根据其真实错因生成一份原创练习，逐题给出答案、原文证据和干扰项解释；validate_pack 后 save_draft_pack，保留为待审。不要编造教师审校或试听结果。审核完成后再安排活动，并读取学生真实提交，给具体反馈与新情境复测建议。</p><button class="btn ghost" data-action="copy-example">复制这条任务</button></div><h2>建议的调用顺序</h2><pre>get_context → get_student → prepare_generation
→ validate_pack → save_draft_pack → 教师在网页审校
→ release_reviewed_pack → start_activity
→ 学生在网页作答 → get_student → record_feedback
→ 学生修订 → start_activity(retest) → 教师核验迁移</pre><p class="small muted">两个入口指向同一个BASE_DATA才会共享记录。本轮协议测试与网页联动可以证明工程连通；实际教学效果仍需目标学生试用。</p></div>`);
}

function itemEditor(i) {
  return `<details><summary>${h(i.id)}. ${h(i.prompt)}</summary><div class="item-edit" data-item-id="${h(i.id)}"><div class="field"><label>题干<input class="input" data-field="prompt" value="${h(i.prompt)}" maxlength="2000"></label></div>${i.kind === "mcq" ? `<div class="field"><label>选项（每行一个，保持A/B/C/D顺序）<textarea data-field="options" style="min-height:95px">${h(i.options.join("\n"))}</textarea></label></div>` : ""}<div class="field"><label>可接受答案（多个写法以 | 分开）<input class="input" data-field="key" value="${h(i.key.join(" | "))}" maxlength="1000"></label></div><div class="field"><label>原文证据<textarea data-field="evidence" style="min-height:95px" maxlength="12000">${h(i.evidence)}</textarea></label></div><div class="field"><label>给学生的具体解析<textarea data-field="explanation" style="min-height:95px" maxlength="3000">${h(i.explanation)}</textarea></label></div></div></details>`;
}

function renderFiles() {
  if ($("#file-list"))
    $("#file-list").innerHTML = files
      .map((f, i) => `<span class="file-pill">✓ 附件${i + 1}已准备</span>`)
      .join("");
}
async function uploadFile(file) {
  let data = new FormData();
  data.append("file", file);
  let r = await api("/api/uploads", data);
  files.push(r.id);
  renderFiles();
  notify("附件已保存，提交作品时会一并附上");
}
async function toggleRecord(button) {
  if (recorder && recorder.state === "recording") {
    recorder.stop();
    button.textContent = "◉ 开始录音";
    button.classList.remove("recording");
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia)
    throw Error(
      "当前环境不能直接录音。请在localhost或HTTPS打开，或上传已有录音。",
    );
  recordStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  let chunks = [];
  recorder = new MediaRecorder(recordStream);
  recorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };
  recorder.onstop = async () => {
    recordStream.getTracks().forEach((t) => t.stop());
    let type = recorder.mimeType.split(";")[0],
      blob = new Blob(chunks, { type }),
      url = URL.createObjectURL(blob);
    objectURLs.push(url);
    let preview = $("#record-preview");
    if (preview) {
      preview.hidden = false;
      preview.src = url;
    }
    try {
      await uploadFile(
        new File(
          [blob],
          "我的录音." + (type.includes("mp4") ? "m4a" : "webm"),
          { type },
        ),
      );
    } catch (e) {
      notify(e.message, true);
    }
  };
  recorder.start();
  button.textContent = "■ 停止录音并保存";
  button.classList.add("recording");
  setTimeout(() => {
    if (recorder?.state === "recording") {
      recorder.stop();
      button.textContent = "◉ 开始录音";
      button.classList.remove("recording");
    }
  }, 120000);
}
async function downloadFile(id, admin = false) {
  let r = await fetch("/api/files/" + id, {
    headers: admin
      ? { "X-Owner-Token": owner }
      : { Authorization: "Bearer " + access },
  });
  if (!r.ok) throw Error((await r.json()).error);
  let url = URL.createObjectURL(await r.blob());
  objectURLs.push(url);
  let type = r.headers.get("content-type") || "";
  if (type.startsWith("audio/") || type.startsWith("video/")) {
    let existing = $("#submission-audio");
    if (!existing) {
      existing = document.createElement("audio");
      existing.id = "submission-audio";
      existing.controls = true;
      ($(".modal") || $("#app")).prepend(existing);
    }
    existing.src = url;
  } else {
    let a = document.createElement("a");
    a.href = url;
    a.download = "学生提交作品";
    a.click();
  }
}
async function copy(text) {
  await navigator.clipboard.writeText(text);
  notify("已复制，可以发给对应学生");
}

document.addEventListener("click", async (event) => {
  let b = event.target.closest("[data-action]");
  if (!b) return;
  let a = b.dataset.action;
  try {
    if (a === "home") home();
    else if (a === "continue-student") await student();
    else if (a === "pair-student") pairingModal();
    else if (a === "invite-student") showPairCode(await api("/api/teacher/pair-codes", {}, true));
    else if (a === "personal-pair") showPairCode(await api("/api/teacher/pair-codes", {learner_id:selected}, true));
    else if (a === "copy-pair") await copy($("#pair-share").value);
    else if (a === "revoke-code") { await api("/api/teacher/pair-codes/"+b.dataset.id+"/revoke", {}, true); closeModal(); await teacherPage(); notify("配对码已撤销"); }
    else if (a === "save-my-link") { openModal("保管自己的学习入口", `<p>这是你的个人学习入口，请自己保管，换设备时可继续原有记录。</p><input class="input" id="student-link" readonly value="${h(location.origin+"/#learn="+access)}"><button class="btn accent" data-action="copy-link" style="margin-top:16px">复制我的学习链接</button>`); }
    else if (a === "leave-pair") openModal("解除与老师的配对", `<p>解除后，老师不能再查看你的档案、提交或继续评阅。你的作品和学习入口保留；重新连接需要新的配对码。</p><button class="btn accent" data-action="confirm-leave-pair">确认解除配对</button>`);
    else if (a === "confirm-leave-pair") { await api("/api/pairing/leave", {}); closeModal(); await student(); notify("已解除配对，作品已保留"); }
    else if (a === "unpair-student") openModal("解除学生配对", `<p>这位学生将从当前教师工作区移出，学生的作品与个人学习入口保留。</p><button class="btn accent" data-action="confirm-unpair">确认解除</button>`);
    else if (a === "confirm-unpair") { await api("/api/teacher/students/"+selected+"/unpair",{},true); closeModal(); selected=""; await teacherPage(); }
    else if (a === "teacher-name") openModal("学生看到的老师称呼", `<form id="teacher-name-form"><div class="field"><label for="teacher-name">老师称呼</label><input id="teacher-name" name="name" class="input" required maxlength="40" value="${h(teacher.teacher.name)}"></div><button class="btn accent" type="submit">保存称呼</button></form>`);
    else if (a === "close") { pendingPairCode=""; closeModal(); }
    else if (a === "student") studentEntry();
    else if (a === "enroll") enrollment();
    else if (a === "demo") {
      enrollment(true);
      if (b.dataset.exam) $("#exam").value = b.dataset.exam;
      if (b.dataset.stage) $("#stage").value = b.dataset.stage;
    } else if (a === "guide") guide();
    else if (a === "guide-student") $("#guide-body").innerHTML = studentGuide();
    else if (a === "guide-teacher") $("#guide-body").innerHTML = teacherGuide();
    else if (a === "agent") agentPage();
    else if (a === "teacher") await teacherPage();
    else if (a === "new-student") enrollment(false, true);
    else if (a === "refresh") await student();
    else if (a === "logout-student") {
      access = "";
      localStorage.removeItem("growth-access");
      dash = null;
      home();
    } else if (a === "logout-teacher") {
      owner = "";
      sessionStorage.removeItem("growth-owner");
      await teacherPage();
    } else if (a === "start" || a === "next") {
      b.disabled = true;
      if (a === "next") dash = await api("/api/me");
      await start(b.dataset.purpose);
    } else if (a === "open-task") await openTask(b.dataset.id);
    else if (a === "revise") renderStudy(true);
    else if (a === "teacher-tab") {
      teacherTab = b.dataset.tab;
      renderTeacher();
    } else if (a === "open-student") {
      selected = b.dataset.id;
      teacherTab = "students";
      renderTeacher();
    } else if (a === "select-student") {
      selected = b.dataset.id;
      renderTeacher();
    } else if (a === "model-draft") {
      b.disabled = true;
      b.textContent = "正在生成草稿…";
      notify("正在按考试蓝图准备草稿，请稍候…");
      let r = await api(
        "/api/teacher/generate",
        { learner_id: selected },
        true,
      );
      notify(r.note);
      teacherTab = "resources";
      await teacherPage();
    } else if (a === "assign") {
      b.disabled = true;
      await api(
        "/api/teacher/assign",
        {
          learner_id: selected,
          purpose: $("#assign-purpose").value,
          resource_id: $("#assign-resource").value || null,
          request_key: uuid(),
        },
        true,
      );
      notify("任务已安排，学生同步后即可看到");
      await teacherPage();
    } else if (a === "student-link") {
      openModal(
        "重新生成学习入口",
        `<p>新的入口会替换旧入口，但不会删除任何学习记录。只把链接发给 <strong>${h(teacher.learners.find((d) => d.person.id === selected).person.name)}</strong>。</p><button class="btn accent" data-action="confirm-link">生成新入口并复制</button>`,
      );
    } else if (a === "confirm-link") {
      let r = await api(
        "/api/teacher/students/" + selected + "/link",
        {},
        true,
      );
      let link = location.origin + r.student_path;
      openModal(
        "学习入口已生成",
        `<p class="small muted">旧入口已失效。请把下面的完整链接发给对应学生。</p><input class="input" id="student-link" readonly value="${h(link)}"><button class="btn accent" style="margin-top:18px" data-action="copy-link">复制学习链接</button>`,
      );
    } else if (a === "copy-link") await copy($("#student-link").value);
    else if (a === "state") {
      await api(
        "/api/teacher/state/" + b.dataset.id,
        { state: b.dataset.state },
        true,
      );
      notify("任务状态已更新，学生端立即生效");
      await teacherPage();
    } else if (a === "edit-profile") {
      let p = teacher.learners.find((d) => d.person.id === selected).person;
      openModal(
        "编辑学生档案",
        `<form id="profile-form"><div class="field"><label>学生称呼<input class="input" name="name" value="${h(p.name)}" required maxlength="80"></label></div>${selects(p.exam, p.stage)}<div class="field"><label>当前目标<input class="input" name="goal" value="${h(p.profile.goal)}" maxlength="1000"></label></div><div class="field"><label>教师备注<textarea name="notes" maxlength="3000">${h(p.notes)}</textarea></label></div><button class="btn accent">保存档案</button></form>`,
      );
    } else if (a === "goal") {
      let p = dash.person.goal_plan;
      openModal(
        "把目标，变成准备任务",
        `<p class="muted small">借用投石问路的差距分析：先明确要求，再用学习作品补齐证据。未知信息保持待核实。</p><form id="goal-form"><div class="field"><label>我的目标<input class="input" name="target" value="${h(p.target || "")}" required maxlength="1000" placeholder="例如：参与导师小组的讨论"></label></div><div class="field"><label>机会或要求的官方链接（选填）<input class="input" name="url" type="url" value="${h(p.source_url || "")}" placeholder="https://..."></label></div><p class="small muted">先生成听懂要求、清楚提出请求、独立迁移三条准备任务。完成后结合新作品回评，不自动推断录取概率。</p><button class="btn accent">保存目标与准备计划</button></form>`,
      );
    } else if (a === "record") await toggleRecord(b);
    else if (a === "file")
      await downloadFile(b.dataset.id, Boolean(b.dataset.admin));
    else if (a === "review-work") {
      if (b.dataset.learner) selected = b.dataset.learner;
      let t = teacher.learners
          .find((d) => d.person.id === selected)
          .tasks.find((t) => t.id === b.dataset.id),
        s = t.attempts.at(-1);
      openModal(
        "查看提交与评阅",
        `<p><strong>${h(t.pack.title)}</strong> · 第${t.attempts.length}次提交</p><details><summary>查看本次题目与任务要求</summary><p>${h(t.pack.stimulus)}</p>${t.pack.items.map((q) => `<p>${h(q.id)}. ${h(q.prompt)}<br>${(q.options || []).map((v, i) => h(String.fromCharCode(65 + i) + ". " + v)).join(" / ")}</p>`).join("")}</details>${s.automatic ? `<p class="small">规则判分 ${s.automatic.score}/${s.automatic.total}，不代表正式考试分数。</p>${s.automatic.items.map((x, index) => `<details><summary>第${index + 1}题：${h(x.answer)} ${x.correct ? "✓" : "↗"}</summary><p>参考答案：${h(x.accepted.join("/"))}<br>依据：${h(x.evidence)}<br>${h(x.explanation)}</p></details>`).join("")}` : `<article class="reading" style="font-size:15px;padding:15px">${h(s.answer.text || "提交了附件或录音")}</article>`}${(s.answer.files || []).map((id) => `<button class="btn ghost small" data-action="file" data-admin="1" data-id="${h(id)}">听取录音 / 打开附件</button>`).join("")}<form id="feedback-form" data-submission="${s.id}"><div class="field" style="margin-top:20px"><label>具体反馈<textarea name="comment" required maxlength="5000" placeholder="指出作品中的一个具体表现和一个可改进点">${s.evaluation.review_state === "confirmed" ? h(s.evaluation.comment) : ""}</textarea></label></div><div class="field"><label>下一步怎么改<input class="input" name="next_step" required maxlength="1000" placeholder="例如：在第2句补充明确请求，并说明所需证明"></label></div><div class="field"><label>本次判定<select name="judgement"><option value="">仅记录反馈，尚不判断达标</option><option value="needs_revision">需要修订</option><option value="meets_criteria">教师确认本次作品达标</option></select></label></div>${t.pack.rubric ? `<p class="small muted">分项评分选填；填写时须所有项完整填写（0—5）。</p>${t.pack.rubric.map((r, i) => `<div class="field"><label>${h(r)}<input class="input" type="number" min="0" max="5" step="0.5" name="score_${i}" data-label="${h(r)}"></label></div>`).join("")}` : ""}<button class="btn accent">保存反馈，学生端同步可见</button></form>${t.purpose === "retest" && s.evaluation.judgement === "meets_criteria" ? `<hr><button class="btn ghost" data-action="transfer" data-id="${s.id}">确认新情境独立迁移</button>` : ""}<details><summary>历次提交与评阅</summary>${t.attempts.map((x, i) => `<p>第${i + 1}次：${h(x.evaluation.comment)}（${x.review_history.length}条教师评阅历史）</p>`).join("")}</details>`,
      );
    } else if (a === "transfer") {
      openModal(
        "核验独立迁移",
        `<p class="small muted">仅在已核实新情境、无提示独立完成且本次作品达标后记录。自述独立完成不等于教师已核验。</p><form id="transfer-form" data-submission="${h(b.dataset.id)}"><div class="field"><label>新情境与独立完成条件<textarea name="context" required maxlength="2000"></textarea></label></div><label class="check-label"><input type="checkbox" name="independent" required>我已实际核验这次独立完成条件</label><button class="btn accent">记录本次迁移证据</button></form>`,
      );
    } else if (a === "review-pack") {
      let p = teacher.resources.find((x) => x.id === b.dataset.id);
      openModal(
        "题包预览与质量审核",
        `<p><strong>${h(p.title)}</strong></p><p class="small muted">${h(p.source.title)} · ${h(p.source.voice || p.source.kind)}</p>${p.audio ? '<audio id="teacher-audio" controls></audio>' : ""}<details><summary>查看原文 / 刺激材料</summary><article class="reading" style="font-size:15px">${h(p.transcript || p.stimulus)}</article></details>${p.items.map(itemEditor).join("")}<form id="pack-review" data-id="${h(p.id)}"><div class="field"><label>实际审核人<input class="input" name="reviewer" required maxlength="100"></label></div><div class="field"><label>逐题核验与试听意见<textarea name="note" required maxlength="3000" placeholder="记录具体题号、时间点、原文/答案对应及声音质量；不能只写‘能播放’"></textarea></label></div><label class="check-label"><input type="checkbox" name="content_checked" required>我已逐题检查原文依据、答案有效性与干扰项</label>${p.audio ? '<label class="check-label"><input type="checkbox" name="audio_listened" required>我已完整试听，确认自然连贯、无截断且音文一致</label>' : ""}<button class="btn accent">记录审核并放行</button></form>`,
      );
      if (p.audio) await loadAudio(p.audio, "#teacher-audio");
    } else if (a === "copy-example")
      await copy($("#agent-example").textContent);
  } catch (e) {
    notify(e.message, true);
  } finally {
    if (b.isConnected) {
      b.disabled = false;
      if (a === "model-draft") b.textContent = "按错因生成模型草稿";
    }
  }
});

document.addEventListener("submit", async (event) => {
  let form = event.target;
  if (!form.id) return;
  event.preventDefault();
  if (busy) return;
  busy = true;
  let b = form.querySelector("button[type=submit],button:not([type])");
  if (b) b.disabled = true;
  const f = new FormData(form),
    obj = Object.fromEntries(f);
  try {
    if (form.id === "enroll-form") {
      let admin = form.dataset.admin === "true",
        demo = form.dataset.demo === "true";
      let r = await api(
        admin ? "/api/teacher/students" : "/api/enroll",
        { ...obj, demo, request_key: uuid() },
        admin,
      );
      closeModal();
      if (admin) {
        selected = r.person.id;
        await teacherPage();
        showPairCode(await api("/api/teacher/pair-codes", {learner_id:r.person.id}, true));
      } else {
        access = r.access;
        localStorage.setItem("growth-access", access);
        await student();
        if (pendingPairCode) {
          const code=pendingPairCode; pendingPairCode="";
          await api("/api/pairing/redeem", {code});
          await student();
          notify("已连接"+dash.person.teacher.name);
        }
      }
    } else if (form.id === "pair-form") {
      const result=await api("/api/pairing/redeem", {code:obj.code});
      if (result.needs_profile) {
        pendingPairCode=obj.code;
        closeModal(); enrollment();
        notify("先建立自己的学习档案，随后连接"+result.teacher.name);
      } else {
        access=result.access; localStorage.setItem("growth-access",access);
        closeModal(); await student(); notify("已连接"+result.person.teacher.name);
      }
    } else if (form.id === "teacher-name-form") {
      await api("/api/teacher/profile", obj, true); closeModal(); await teacherPage();
    } else if (form.id === "teacher-login") {
      owner = obj.token.trim();
      await api("/api/teacher", undefined, true);
      sessionStorage.setItem("growth-owner", owner);
      await teacherPage();
    } else if (form.id === "answer-form") {
      if (recorder?.state === "recording")
        throw Error("请先停止录音并等待保存完成，再提交作品");
      let answers = {};
      for (let i of current.pack.items) answers[i.id] = obj["q_" + i.id] || "";
      current = await api("/api/activities/" + current.id + "/submit", {
        answers,
        text: obj.text || "",
        files,
        request_key: uuid(),
        independent: f.has("independent"),
      });
      localStorage.removeItem("growth-draft-" + current.id);
      renderFeedback();
      notify("提交已保存，老师也能看到这份记录");
    } else if (form.id === "profile-form") {
      await api("/api/teacher/students/" + selected, obj, true);
      closeModal();
      await teacherPage();
      notify("档案已保存，已发布任务仍保留原版本");
    } else if (form.id === "goal-form") {
      await api("/api/goals", obj);
      closeModal();
      await student();
      notify("目标已拆成可准备的任务，完成后再依据作品回评");
    } else if (form.id === "feedback-form") {
      let entries = [...form.querySelectorAll('[name^="score_"]')],
        scores = null;
      if (entries.some((n) => n.value !== "")) {
        if (entries.some((n) => n.value === ""))
          throw Error("分项评分请全部填写，或全部留空");
        scores = entries.map((n) => ({
          label: n.dataset.label,
          score: Number(n.value),
        }));
      }
      await api(
        "/api/teacher/feedback/" + form.dataset.submission,
        {
          comment: obj.comment,
          next_step: obj.next_step,
          judgement: obj.judgement || null,
          scores,
          request_key: uuid(),
        },
        true,
      );
      closeModal();
      await teacherPage();
      notify("反馈已保存，学生同步后即可查看并修订");
    } else if (form.id === "pack-import") {
      let pack;
      try {
        pack = JSON.parse(obj.pack);
      } catch (e) {
        throw Error("题包JSON格式不正确，请检查括号和引号");
      }
      await api("/api/teacher/packs", pack, true);
      teacherTab = "resources";
      await teacherPage();
      notify("已保存待审草稿，尚未发布给学生");
    } else if (form.id === "pack-review") {
      let pack = structuredClone(
          teacher.resources.find((p) => p.id === form.dataset.id),
        ),
        before = JSON.stringify(pack.items);
      document.querySelectorAll(".item-edit").forEach((row) => {
        let item = pack.items.find((i) => i.id === row.dataset.itemId);
        row.querySelectorAll("[data-field]").forEach((field) => {
          let k = field.dataset.field;
          item[k] =
            k === "key"
              ? field.value
                  .split("|")
                  .map((v) => v.trim())
                  .filter(Boolean)
              : k === "options"
                ? field.value
                    .split("\n")
                    .map((v) => v.trim())
                    .filter(Boolean)
                : field.value;
        });
      });
      if (JSON.stringify(pack.items) !== before)
        await api("/api/teacher/packs", pack, true);
      await api(
        "/api/teacher/packs/" + encodeURIComponent(form.dataset.id) + "/review",
        {
          reviewer: obj.reviewer,
          note: obj.note,
          content_checked: f.has("content_checked"),
          audio_listened: f.has("audio_listened"),
        },
        true,
      );
      closeModal();
      await teacherPage();
      notify("审核已记录，现在可以安排给正式学生");
    } else if (form.id === "transfer-form") {
      await api(
        "/api/teacher/transfer/" + form.dataset.submission,
        { context: obj.context, independent: f.has("independent") },
        true,
      );
      closeModal();
      await teacherPage();
      notify("本次独立迁移证据已保存");
    }
  } catch (e) {
    notify(e.message, true);
  } finally {
    busy = false;
    if (b?.isConnected) b.disabled = false;
  }
});
document.addEventListener("input", (event) => {
  if (!event.target.closest("#answer-form")) return;
  let f = new FormData($("#answer-form")),
    answers = {};
  for (let i of current.pack.items) answers[i.id] = f.get("q_" + i.id) || "";
  let text = f.get("text") || "";
  try {
    localStorage.setItem(
      "growth-draft-" + current.id,
      JSON.stringify({ answers, text }),
    );
  } catch (e) {}
  if ($("#answer-progress") && current.pack.items.length)
    $("#answer-progress").textContent =
      `已作答 ${Object.values(answers).filter(Boolean).length} / ${current.pack.items.length} 题 · 草稿已保留`;
  if ($("#word-count"))
    $("#word-count").textContent =
      `${text.trim() ? text.trim().split(/\s+/).length : 0} 个英文词 · 已保存本机草稿；字数不代表质量`;
});
document.addEventListener("change", async (e) => {
  if (e.target.id === "file-input" && e.target.files[0])
    try {
      await uploadFile(e.target.files[0]);
    } catch (x) {
      notify(x.message, true);
    }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { pendingPairCode=""; closeModal(); }
});
async function init() {
  try {
    catalog = await api("/api/catalog");
    if (location.hash.startsWith("#learn=")) {
      let token = location.hash.slice(7);
      if (!/^[a-f0-9]{32}\.[a-f0-9]{64}$/.test(token))
        throw Error("学习链接格式不正确，请向老师索取完整链接");
      access = token;
      localStorage.setItem("growth-access", access);
      await student();
    } else if (location.hash === "#teacher") await teacherPage();
    else if (location.hash === "#student-entry") studentEntry();
    else if (location.hash === "#guide") guide();
    else if (location.hash === "#agent") agentPage();
    else if (location.hash === "#student" && access) await student();
    else home();
  } catch (e) {
    home();
    notify(e.message, true);
  }
}
setInterval(async () => {
  if (
    view === "student" &&
    access &&
    !document.hidden &&
    !$("#modal-root").children.length
  )
    try {
      let fresh = await api("/api/me");
      if (JSON.stringify(fresh) !== JSON.stringify(dash)) {
        dash = fresh;
        renderStudent();
      }
    } catch (e) {}
}, 15000);
init();
