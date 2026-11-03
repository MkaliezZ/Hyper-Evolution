"""Shared application service for learner/teacher web and MCP. BASE owns evidence."""

import hashlib, hmac, json, re, secrets, time
from pathlib import Path
from uuid import uuid4
from base.core import Store, now
from base.app.content import (
    BLUEPRINTS,
    STAGES,
    SKILLS,
    make_drill,
    writing_task,
    speaking_task,
    public_pack,
    grade,
)


class GrowthService:
    def __init__(self, folder):
        self.base = Store(folder)
        self.folder = self.base.folder
        (self.folder / "owner-token.txt").write_text(
            self.base.owner_token, encoding="utf-8"
        )
        with self.base.db() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS hd_people(id TEXT PRIMARY KEY REFERENCES learners(id), exam TEXT NOT NULL,stage TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,demo INTEGER NOT NULL DEFAULT 0,notes TEXT NOT NULL DEFAULT '',goal TEXT NOT NULL DEFAULT '{}');
   CREATE TABLE IF NOT EXISTS hd_resources(id TEXT PRIMARY KEY,body TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS hd_files(id TEXT PRIMARY KEY,learner_id TEXT NOT NULL REFERENCES learners(id),name TEXT NOT NULL,mime TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,created TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS hd_audits(id TEXT PRIMARY KEY,kind TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);""")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS hd_teacher(id TEXT PRIMARY KEY,name TEXT NOT NULL);
                INSERT OR IGNORE INTO hd_teacher VALUES ('workspace-teacher','伴学老师');
                CREATE TABLE IF NOT EXISTS hd_pairings(learner_id TEXT PRIMARY KEY REFERENCES hd_people(id),teacher_id TEXT NOT NULL,paired_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hd_pair_codes(id TEXT PRIMARY KEY,digest TEXT UNIQUE NOT NULL,learner_id TEXT,expires INTEGER NOT NULL,state TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hd_pair_limits(client TEXT PRIMARY KEY,start INTEGER NOT NULL,failures INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS hd_migrations(name TEXT PRIMARY KEY);
            """)
            # Existing workspaces keep their teacher/student relationships exactly once.
            if not db.execute("SELECT 1 FROM hd_migrations WHERE name='pairing-v1'").fetchone():
                db.execute("INSERT OR IGNORE INTO hd_pairings SELECT id,'workspace-teacher',? FROM hd_people", (now(),))
                db.execute("INSERT INTO hd_migrations VALUES ('pairing-v1')")

    def catalog(self):
        return {
            "exams": BLUEPRINTS,
            "stages": STAGES,
            "skills": SKILLS,
            "version": "0.2.0",
            "generation": "本地语义模板 + 可由Agent提交原创题；语言模型服务未配置时不会假装调用模型",
        }

    def person(self, learner_id):
        with self.base.db() as db:
            row = db.execute(
                "SELECT * FROM hd_people WHERE id=?", (learner_id,)
            ).fetchone()
        if not row:
            raise KeyError("找不到这个学生档案")
        return {
            **self.base.learner(learner_id),
            **dict(row),
            "goal_plan": json.loads(row["goal"]),
        }

    def capability(self, learner_id):
        p = self.person(learner_id)
        sig = hmac.new(
            self.base.owner_token.encode(),
            f"{learner_id}:{p['revision']}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return learner_id + "." + sig

    def authorize(self, token, learner_id=None):
        if not isinstance(token, str) or len(token) > 160 or "." not in token:
            raise PermissionError("请通过自己的学习链接进入")
        subject = token.split(".")[0]
        try:
            expected = self.capability(subject)
        except KeyError:
            raise PermissionError("学习链接不存在或已更新") from None
        if not hmac.compare_digest(token, expected) or (
            learner_id and subject != learner_id
        ):
            raise PermissionError("这个学习链接不能访问其他学生的内容")
        return subject

    def create_learner(
        self,
        name,
        exam="ielts",
        stage="application",
        goal="",
        demo=False,
        request_key=None,
        paired=True,
    ):
        if exam not in BLUEPRINTS or stage not in STAGES:
            raise ValueError("请先选择考试和留学阶段")
        if not isinstance(goal, str) or len(goal) > 2000:
            raise ValueError("学习目标最长2000字")
        p = self.base.save_learner(
            name, {"goal": goal, "stage": stage}, request_key=request_key
        )
        with self.base.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO hd_people(id,exam,stage,demo) VALUES (?,?,?,?)",
                (p["id"], exam, stage, int(demo)),
            )
            if paired:
                db.execute("INSERT OR IGNORE INTO hd_pairings VALUES (?,'workspace-teacher',?)", (p['id'],now()))
        return {
            "person": self.public_person(p["id"]),
            "access": self.capability(p["id"]),
            "student_path": "/#learn=" + self.capability(p["id"]),
        }

    def public_person(self, id, include_notes=False):
        p = self.person(id)
        out = {
            k: p[k]
            for k in ["id", "name", "exam", "stage", "demo", "profile", "goal_plan"]
        }
        out["notes"] = p["notes"] if include_notes else ""
        out["teacher"] = self.pairing(id)
        return out

    def teacher_profile(self, name=None):
        if name is not None and (not isinstance(name,str) or not 1 <= len(name.strip()) <= 40):
            raise ValueError("老师称呼请填写1—40字")
        with self.base.db() as db:
            if name is not None:
                db.execute("UPDATE hd_teacher SET name=? WHERE id='workspace-teacher'",(name.strip(),))
            return dict(db.execute("SELECT * FROM hd_teacher WHERE id='workspace-teacher'").fetchone())

    def pairing(self, learner_id):
        with self.base.db() as db:
            row=db.execute("SELECT t.id,t.name,p.paired_at FROM hd_pairings p JOIN hd_teacher t ON p.teacher_id=t.id WHERE p.learner_id=?",(learner_id,)).fetchone()
        return dict(row) if row else None

    def require_paired(self, learner_id):
        if not self.pairing(learner_id):
            raise PermissionError("学生尚未与本教师配对，或配对已解除")
        return learner_id

    def require_task_pair(self, task_id):
        return self.require_paired(self._task(task_id)['learner_id'])

    def require_submission_pair(self, submission_id):
        with self.base.db() as db:
            row=db.execute("SELECT t.learner_id FROM submissions s JOIN tasks t ON s.task_id=t.id WHERE s.id=?",(submission_id,)).fetchone()
        if not row: raise KeyError("提交不存在")
        return self.require_paired(row['learner_id'])

    def create_pair_code(self, learner_id=None):
        if learner_id: self.require_paired(learner_id)
        code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
        expires=int(time.time())+86400
        id=uuid4().hex
        with self.base.db() as db:
            if learner_id:
                db.execute("UPDATE hd_pair_codes SET state='revoked' WHERE learner_id=? AND state='active'",(learner_id,))
            db.execute("INSERT INTO hd_pair_codes VALUES (?,?,?,?,?,?)",(id,hashlib.sha256(code.encode()).hexdigest(),learner_id,expires,'active',now()))
        return {'id':id,'code':code[:4]+'-'+code[4:],'expires':expires,'single_use':True,'teacher':self.teacher_profile(),'student_name':self.person(learner_id)['name'] if learner_id else None}

    def pair_codes(self):
        with self.base.db() as db:
            rows=db.execute("SELECT c.id,c.learner_id,c.expires,c.state,c.created,p.id AS person_id FROM hd_pair_codes c LEFT JOIN hd_people p ON p.id=c.learner_id ORDER BY c.created DESC LIMIT 100").fetchall()
        return [{**dict(r),'state':'expired' if r['state']=='active' and r['expires']<=int(time.time()) else r['state']} for r in rows]

    def revoke_pair_code(self, code_id):
        with self.base.db() as db:
            db.execute("UPDATE hd_pair_codes SET state='revoked' WHERE id=? AND state='active'",(code_id,))
        return {'revoked':True}

    def pair_rate_limit(self, client, failure=False):
        client=hashlib.sha256(client.encode()).hexdigest()
        stamp=int(time.time())
        with self.base.db() as db:
            r=db.execute("SELECT * FROM hd_pair_limits WHERE client=?",(client,)).fetchone()
            if r and r['start']>stamp-600 and r['failures']>=10:
                raise ValueError("配对码连续输入错误较多，请10分钟后重试")
            if failure:
                if not r or r['start']<=stamp-600:
                    db.execute("INSERT OR REPLACE INTO hd_pair_limits VALUES (?,?,1)",(client,stamp))
                else:
                    db.execute("UPDATE hd_pair_limits SET failures=failures+1 WHERE client=?",(client,))

    def redeem_pair_code(self, code, learner_id=None):
        if not isinstance(code,str) or len(code)>40: raise ValueError("请填写老师提供的8位配对码")
        normalized=re.sub(r'[\s-]','',code).upper()
        digest=hashlib.sha256(normalized.encode()).hexdigest()
        with self.base.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r=db.execute("SELECT * FROM hd_pair_codes WHERE digest=?",(digest,)).fetchone()
            if not r or r['state']!='active' or r['expires']<=int(time.time()):
                raise ValueError("配对码无效、已使用或已过期，请向老师索取新码")
            if r['learner_id']:
                if learner_id and learner_id!=r['learner_id']:
                    raise ValueError("此码属于另一份学生档案。请使用自己的配对码；系统不会合并或覆盖当前作品。")
                subject=r['learner_id']
                # A teacher-issued personal code also recovers access, revoking older links.
                db.execute("UPDATE hd_people SET revision=revision+1 WHERE id=?",(subject,))
            elif not learner_id:
                return {'needs_profile':True,'teacher':self.teacher_profile()}
            else:
                subject=learner_id
            db.execute("INSERT OR IGNORE INTO hd_pairings VALUES (?,'workspace-teacher',?)",(subject,now()))
            db.execute("UPDATE hd_pair_codes SET state='used' WHERE id=?",(r['id'],))
        return {'person':self.public_person(subject),'access':self.capability(subject),'student_path':'/#learn='+self.capability(subject),'paired':True}

    def unpair(self, learner_id):
        self.person(learner_id)
        with self.base.db() as db:
            db.execute("DELETE FROM hd_pairings WHERE learner_id=?",(learner_id,))
            db.execute("UPDATE hd_pair_codes SET state='revoked' WHERE learner_id=? AND state='active'",(learner_id,))
        return {'unpaired':True,'records_preserved':True}

    def update_person(self, id, name, goal, exam, stage, notes=""):
        self.require_paired(id)
        if (
            exam not in BLUEPRINTS
            or stage not in STAGES
            or not isinstance(notes, str)
            or len(notes) > 3000
        ):
            raise ValueError("档案字段不符合要求")
        self.base.save_learner(name, {"goal": goal, "stage": stage}, learner_id=id)
        with self.base.db() as db:
            db.execute(
                "UPDATE hd_people SET exam=?,stage=?,notes=? WHERE id=?",
                (exam, stage, notes, id),
            )
        return self.public_person(id)

    def issue_link(self, id):
        self.require_paired(id)
        self.person(id)
        with self.base.db() as db:
            db.execute("UPDATE hd_people SET revision=revision+1 WHERE id=?", (id,))
        return {
            "student_path": "/#learn=" + self.capability(id),
            "note": "旧学习入口已失效；任务与提交保留。",
        }

    def tasks(self, learner_id):
        self.person(learner_id)
        with self.base.db() as db:
            rows = db.execute(
                "SELECT * FROM tasks WHERE learner_id=? ORDER BY created,id",
                (learner_id,),
            ).fetchall()
        return [
            {**dict(r), "snapshot": json.loads(r["snapshot"])}
            for r in rows
            if "growth" in json.loads(r["snapshot"])
        ]

    def _task(self, id):
        with self.base.db() as db:
            r = db.execute("SELECT token FROM tasks WHERE id=?", (id,)).fetchone()
        if not r:
            raise KeyError("任务不存在")
        task = self.base.task(r["token"])
        if "growth" not in task["snapshot"]:
            raise ValueError("这不是超维成长任务")
        return task

    def session(self, id):
        task = self._task(id)
        subs = self.base.submissions(id)
        pack = task["snapshot"]["growth"]
        attempts = []
        for s in subs:
            answer = json.loads(s["answer"])
            ev = s["evaluation"]
            auto = grade(pack, answer.get("answers", {})) if pack["items"] else None
            attempts.append(
                {
                    "id": s["id"],
                    "created": s["created"],
                    "answer": answer,
                    "evaluation": ev,
                    "automatic": auto,
                    "review_history": s["review_history"],
                }
            )
        return {
            "id": id,
            "learner_id": task["learner_id"],
            "created": task["created"],
            "state": task["state"],
            "purpose": pack["purpose"],
            "pack": public_pack(pack, bool(subs)),
            "attempts": attempts,
        }

    def dashboard(self, id, teacher=False):
        if teacher: self.require_paired(id)
        p = self.public_person(id, include_notes=teacher)
        tasks = [self.session(t["id"]) for t in self.tasks(id)]
        latest_skills = {}
        for t in tasks:
            if t['pack'].get('academic'):continue
            if t["attempts"]:
                auto = t["attempts"][-1]["automatic"]
                if auto:
                    for skill in {r["skill"] for r in auto["items"]}:
                        latest_skills[skill] = all(
                            r["correct"] for r in auto["items"] if r["skill"] == skill
                        )
        weak = [skill for skill, passed in latest_skills.items() if not passed]
        completed = {t["purpose"] for t in tasks if t["attempts"]}
        next_type = next(
            (
                x
                for x in ["diagnostic", "practice", "listening", "retest"]
                if x not in completed
            ),
            "writing",
        )
        if next_type == "listening" and not self.available_audio(
            p["exam"], bool(p["demo"])
        ):
            next_type = "listening"
        evidence = self.base.growth(id)
        verified_ids = {
            e["detail"].get("submission_id")
            for e in evidence["events"]
            if e["kind"] == "transfer_verified"
        }
        for gap in p["goal_plan"].get("gaps", []):
            related = [
                t for t in tasks if t["purpose"] == gap["activity"] and t["attempts"]
            ]
            gap["evidence_refs"] = [
                {
                    "activity_id": t["id"],
                    "submission_id": t["attempts"][-1]["id"],
                    "judgement": t["attempts"][-1]["evaluation"].get("judgement"),
                    "transfer_verified": t["attempts"][-1]["id"] in verified_ids,
                }
                for t in related
            ]
            valid = any(
                r["judgement"] == "meets_criteria"
                and (gap["activity"] != "retest" or r["transfer_verified"])
                for r in gap["evidence_refs"]
            )
            gap["evidence_status"] = (
                "已有教师核验的相关作品，需对照机会具体要求回评"
                if valid
                else "已有提交，尚待教师按完成标准核验"
                if related
                else "计划待执行，暂无作品证据"
            )
        return {
            "person": p,
            "tasks": tasks,
            "weak_skills": sorted(set(weak)),
            "next": next_type,
            "evidence": evidence,
            "audio_available": bool(self.available_audio(p["exam"], bool(p["demo"]))),
            "limits": [
                "微练习诊断不能认定托福/雅思正式等级",
                "未见材料复测记录本次表现，真实学习效果需试用验证",
            ],
        }

    def start(self, id, purpose, request_key, resource_id=None):
        if purpose not in [
            "diagnostic",
            "practice",
            "listening",
            "retest",
            "writing",
            "speaking",
        ]:
            raise ValueError("未知的活动类型")
        if not isinstance(request_key, str) or not 0 < len(request_key) <= 100:
            raise ValueError("请提供有效的操作标识")
        p = self.person(id)
        with self.base.db() as db:
            saved = db.execute(
                "SELECT task_id FROM task_requests WHERE key=?",
                ("growth:" + id + ":" + request_key,),
            ).fetchone()
        if saved:
            old = self.session(saved["task_id"])
            if old["purpose"] != purpose or (
                resource_id and old["pack"]["id"] != resource_id
            ):
                raise ValueError("操作标识已用于其他内容，请使用新的标识")
            return old
        previous = self.dashboard(id)
        completed = {t["purpose"] for t in previous["tasks"] if t["attempts"]}
        if purpose == "practice" and "diagnostic" not in completed:
            raise ValueError("先完成简短诊断，再生成针对练习")
        if purpose == "retest" and not {"diagnostic", "practice"} <= completed:
            raise ValueError("先完成诊断和针对练习，再做未见材料复测")
        focus = (previous["weak_skills"] or ["detail"])[0]
        seed = id + purpose + request_key
        if resource_id and purpose != "listening":
            choice = next((x for x in self.resources() if x["id"] == resource_id), None)
            if not choice or choice["exam"] != p["exam"]:
                raise ValueError("题包不存在或与学生当前考试路线不符")
            if choice["status"] != "ready" and not p["demo"]:
                raise ValueError("题包还没有完成审核放行")
            if purpose == "retest":
                oldpacks = [t["pack"] for t in previous["tasks"]]
                if any(
                    choice["family_id"] == old["family_id"]
                    or (choice.get("audio") and choice["audio"] == old.get("audio"))
                    or (
                        not choice.get("audio")
                        and " ".join(choice["stimulus"].casefold().split())
                        == " ".join(old["stimulus"].casefold().split())
                    )
                    for old in oldpacks
                ):
                    raise ValueError(
                        "复测须使用未见材料家族，不能重用已做题包或同一录音"
                    )
            pack = json.loads(json.dumps(choice))
            pack["purpose"] = purpose
        elif purpose == "listening":
            available = self.available_audio(p["exam"], bool(p["demo"]))
            if resource_id:
                available = [a for a in available if a["id"] == resource_id]
            if not available:
                raise ValueError(
                    "当前没有经过教师试听放行的配套录音。请教师先到题库审核；示例入口可体验待审素材。"
                )
            seen = {t["pack"]["family_id"] for t in previous["tasks"]}
            heard = {
                t["pack"].get("audio")
                for t in previous["tasks"]
                if t["pack"].get("audio")
            }
            choice = next(
                (
                    x
                    for x in available
                    if x["family_id"] not in seen and x.get("audio") not in heard
                ),
                None,
            )
            if not choice:
                raise ValueError(
                    "已完成现有录音家族；请审核新的听力素材，避免把重复当作未见题"
                )
            pack = json.loads(json.dumps(choice))
            pack["purpose"] = purpose
        elif purpose == "writing":
            pack = writing_task(p["exam"], p["stage"], seed)
            pack["purpose"] = purpose
        elif purpose == "speaking":
            pack = speaking_task(p["exam"], p["stage"], seed)
            pack["purpose"] = purpose
        else:
            pack = make_drill(p["exam"], p["stage"], focus, seed, purpose)
        draft = {
            "name": "超维成长",
            "activity_title": pack["title"],
            "goal": SKILLS.get(focus, "理解并独立迁移"),
            "deliverable": "逐题作答或提交作品；依据反馈修订，并用未见材料复测。",
            "instructions": pack["instructions"],
            "criteria": "答案须有原文依据；主观作品按公开量规评阅。",
            "next_step": "查看逐题反馈，完成补练与复测。",
            "mode": "text",
            "assessment_version": "growth-0.1",
            "material": pack.get("stimulus") or "请先听录音，再独立完成题目。",
            "growth": pack,
        }
        if pack.get("rubric"):
            draft["rubric"] = [
                {"label": label, "max_score": 5} for label in pack["rubric"]
            ]
        task = self.base.create(
            p["name"], draft, "growth:" + id + ":" + request_key, learner_id=id
        )
        return self.session(task["id"])

    def submit(
        self, id, answers=None, text="", files=None, request_key="", independent=False, learning_conditions=None,writing_history_ref=None
    ):
        t = self._task(id)
        pack = t["snapshot"]["growth"]
        if pack.get('academic',{}).get('mode')=='target':
            with self.base.db() as db:
                prior=db.execute('SELECT request_key FROM submissions WHERE task_id=?',(id,)).fetchall()
            if prior and not any(s['request_key']==request_key for s in prior):raise ValueError('目标测验已交卷，原答不能覆盖；需要新材料另行再测')
        files = files or []
        if (
            not isinstance(files, list)
            or len(files) > 5
            or not isinstance(text, str)
            or len(text) > 12000
        ):
            raise ValueError("作品过长或附件过多")
        for file_id in files:
            if self.file(file_id)["learner_id"] != t["learner_id"]:
                raise PermissionError("不能提交其他学生的附件")
        if not pack["items"] and not text.strip() and not files:
            raise ValueError("请先填写作品，或录音/上传附件")
        if pack["items"] and (
            not isinstance(answers, dict)
            or any(not str(answers.get(i["id"], "")).strip() for i in pack["items"])
        ):
            raise ValueError("还有题目没有作答，请完成后再提交")
        payload = {
            "answers": answers or {},
            "text": text,
            "files": files,
            "independent": bool(independent),
            "conditions": "self_report_only",
        }
        if learning_conditions is not None:
            from base.app.companion.functional.study_contracts import LearningConditions
            try:payload['learning_conditions']=LearningConditions.model_validate(learning_conditions).model_dump()
            except ValueError:raise ValueError('学习条件说明格式无效') from None
        if writing_history_ref is not None:
            from base.app.companion.assets.changes import validate_history_ref
            payload['writing_history_ref']=validate_history_ref(writing_history_ref)
        self.base.submit(
            t["token"], json.dumps(payload, ensure_ascii=False), request_key
        )
        return self.session(id)

    def feedback(
        self,
        submission_id,
        comment,
        next_step,
        judgement=None,
        scores=None,
        request_key=None,
    ):
        self.require_submission_pair(submission_id)
        return self.base.feedback(
            submission_id, comment, next_step, scores, judgement, request_key
        )

    def teacher_overview(self):
        with self.base.db() as db:
            ids = [r["learner_id"] for r in db.execute("SELECT learner_id FROM hd_pairings")]
        learners = [self.dashboard(id, teacher=True) for id in ids]
        return {
            "learners": learners,
            "resources": self.resources(),
            "teacher": self.teacher_profile(),
            "pair_codes": self.pair_codes(),
            "stats": {
                "learners": len(learners),
                "submitted": sum(
                    len(t["attempts"]) for p in learners for t in p["tasks"]
                ),
                "pending_reviews": sum(
                    t["attempts"][-1]["evaluation"]["status"] == "pending"
                    for p in learners
                    for t in p["tasks"]
                    if t["attempts"]
                ),
            },
        }

    def resources(self):
        with self.base.db() as db:
            rows = db.execute("SELECT body FROM hd_resources").fetchall()
        return [json.loads(r["body"]) for r in rows]

    def available_audio(self, exam, demo=False):
        return [
            p
            for p in self.resources()
            if p.get("audio") and p["exam"] == exam and (p["status"] == "ready" or demo)
        ]

    def import_pack(self, pack):
        self.validate_pack(pack)
        pack = json.loads(json.dumps(pack))
        pack["status"] = "pending_review"
        pack.pop("review", None)
        with self.base.db() as db:
            db.execute(
                "INSERT INTO hd_resources VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                (pack["id"], json.dumps(pack, ensure_ascii=False)),
            )
        return {
            "id": pack["id"],
            "status": "pending_review",
            "note": "格式通过不是语义审校。内容或音频变更会撤销放行。",
        }

    def validate_pack(self, p):
        if not isinstance(p, dict):
            raise ValueError("题包必须是对象")
        for field in [
            "id",
            "family_id",
            "title",
            "exam",
            "task_type",
            "instructions",
            "stimulus",
            "blueprint",
        ]:
            if (
                not isinstance(p.get(field), str)
                or len(p[field]) > 16000
                or (field != "stimulus" and not p[field].strip())
            ):
                raise ValueError("题包缺少有效字段：" + field)
        if (
            p["exam"] not in BLUEPRINTS
            or p["blueprint"] != BLUEPRINTS[p["exam"]]["version"]
        ):
            raise ValueError("考试版本不匹配，不能把旧版题标作新版")
        allowed = {
            s
            for group in ["reading", "listening", "writing", "speaking"]
            for s in BLUEPRINTS[p["exam"]][group]
        }
        allowed.update(
            {
                "toefl": {
                    "response",
                    "Read in Daily Life",
                    "Read an Academic Passage",
                    "Write an Email",
                    "Write for an Academic Discussion",
                    "Build a Sentence",
                    "Listen and Repeat",
                    "Take an Interview",
                },
                "ielts": {
                    "Listening Part 1",
                    "Listening Part 2",
                    "Listening Part 3",
                    "Listening Part 4",
                    "真实交流补充（非雅思真题）",
                    "true_false_not_given + completion + multiple_choice",
                    "true_false_not_given + completion",
                },
            }[p["exam"]]
        )
        if p["task_type"] not in allowed:
            raise ValueError(
                "此题型未纳入当前考试蓝图；请明确适配，而不是仅修改考试名称"
            )
        if not isinstance(p.get("items"), list) or not 1 <= len(p["items"]) <= 80:
            raise ValueError("题包须含1—80题")
        ids = set()
        for i in p["items"]:
            if (
                not isinstance(i, dict)
                or not isinstance(i.get("id"), str)
                or i["id"] in ids
            ):
                raise ValueError("题号重复或无效")
            ids.add(i["id"])
            if i.get("kind") not in ["mcq", "gap", "tfng"] or not all(
                isinstance(i.get(k), str) and i[k].strip()
                for k in ["prompt", "evidence", "explanation", "skill"]
            ):
                raise ValueError("题目必须含题干、原文依据、解析和技能标签")
            if (
                not isinstance(i.get("key"), list)
                or not i["key"]
                or not all(isinstance(v, str) and 0 < len(v) < 400 for v in i["key"])
            ):
                raise ValueError("答案格式无效")
            if i["kind"] == "mcq":
                opts = i.get("options", [])
                if (
                    not isinstance(opts, list)
                    or not 2 <= len(opts) <= 6
                    or not all(isinstance(v, str) and v.strip() for v in opts)
                    or len(i["key"]) != 1
                    or i["key"][0] not in [chr(65 + j) for j in range(len(opts))]
                ):
                    raise ValueError("选择题选项或唯一答案无效")
            if i["kind"] == "tfng" and (
                len(i["key"]) != 1 or i["key"][0] not in ["TRUE", "FALSE", "NOT GIVEN"]
            ):
                raise ValueError("判断题答案只能为TRUE/FALSE/NOT GIVEN")
        if not isinstance(p.get("source"), dict):
            raise ValueError("必须记录题目来源")
        if p.get("media_path"):
            path = Path(p["media_path"]).resolve()
            if not path.is_relative_to((self.folder / "media").resolve()):
                raise ValueError(
                    "录音必须先导入本实例的media目录，不能引用任意本机文件"
                )
        return {
            "valid": True,
            "semantic_quality_verified": False,
            "audio_listened": False,
        }

    def review_pack(
        self, id, reviewer, note, audio_listened=False, content_checked=False
    ):
        p = next((x for x in self.resources() if x["id"] == id), None)
        if not p:
            raise KeyError("题包不存在")
        if (
            not all(
                isinstance(v, str) and 0 < len(v.strip()) <= 3000
                for v in [reviewer, note]
            )
            or content_checked is not True
        ):
            raise ValueError("请记录审核人、逐题核验意见，并确认内容审核完成")
        if p.get("audio") and audio_listened is not True:
            raise ValueError("听力题包须先完整试听，再确认放行")
        if p.get("audio"):
            path = Path(p.get("media_path", ""))
            if not path.is_file() or hashlib.sha256(
                path.read_bytes()
            ).hexdigest() != p.get("audio_sha256"):
                raise ValueError("录音缺失或内容已变化，请重新导入后审核")
        p["status"] = "ready"
        p["review"] = {
            "reviewer": reviewer,
            "note": note,
            "content_checked": True,
            "audio_listened": bool(audio_listened),
            "at": now(),
            "content_hash": hashlib.sha256(
                json.dumps(
                    {k: v for k, v in p.items() if k not in ["status", "review"]},
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        }
        with self.base.db() as db:
            db.execute(
                "UPDATE hd_resources SET body=? WHERE id=?",
                (json.dumps(p, ensure_ascii=False), id),
            )
            db.execute(
                "INSERT INTO hd_audits VALUES (?,?,?,?)",
                (
                    uuid4().hex,
                    "pack_review",
                    json.dumps(p["review"], ensure_ascii=False),
                    now(),
                ),
            )
        return p

    def file(self, id):
        with self.base.db() as db:
            r = db.execute("SELECT * FROM hd_files WHERE id=?", (id,)).fetchone()
        if not r:
            raise KeyError("附件不存在")
        return dict(r)

    def save_file(self, learner_id, name, mime, data):
        self.person(learner_id)
        if not data or len(data) > 12 * 1024 * 1024:
            raise ValueError("附件须非空且不超过12MB")
        valid = (
            (
                mime in ["audio/webm", "video/webm"]
                and data.startswith(bytes.fromhex("1a45dfa3"))
            )
            or (mime in ["audio/mp4", "audio/x-m4a"] and b"ftyp" in data[:16])
            or (
                mime in ["audio/mpeg", "audio/mp3"]
                and (data.startswith(b"ID3") or data[0] == 255)
            )
            or (mime in ["audio/wav", "audio/x-wav"] and data.startswith(b"RIFF"))
            or (mime == "application/pdf" and data.startswith(b"%PDF"))
            or (mime == "image/png" and data.startswith(b"\x89PNG"))
            or (mime == "image/jpeg" and data.startswith(b"\xff\xd8"))
            or (mime == "text/plain" and b"\x00" not in data[:2000])
        )
        if not valid:
            raise ValueError(
                "文件类型不支持或文件内容与类型不符，请上传MP3/M4A/WebM/WAV、PDF、图片或纯文本"
            )
        id = uuid4().hex
        folder = self.folder / "uploads"
        folder.mkdir(exist_ok=True)
        path = folder / id
        path.write_bytes(data)
        safe = Path(name or "作品").name[:120]
        with self.base.db() as db:
            db.execute(
                "INSERT INTO hd_files VALUES (?,?,?,?,?,?,?)",
                (
                    id,
                    learner_id,
                    safe,
                    mime,
                    str(path),
                    hashlib.sha256(data).hexdigest(),
                    now(),
                ),
            )
        return {"id": id, "name": safe, "mime": mime, "bytes": len(data)}

    def save_goal(self, id, target, url="", gaps=None):
        self.person(id)
        if (
            not isinstance(target, str)
            or not 0 < len(target.strip()) <= 1000
            or not isinstance(url, str)
            or (url and not re.match(r"^https?://", url))
            or len(url) > 2000
        ):
            raise ValueError("请填写目标；来源链接须为http/https地址")
        gaps = gaps or [
            {
                "requirement": "听懂关键要求",
                "gap": "尚缺独立听力证据",
                "activity": "listening",
                "completion_standard": "用新的录音定位关键信息，并解释依据",
            },
            {
                "requirement": "清楚提出请求",
                "gap": "尚缺邮件作品",
                "activity": "writing",
                "completion_standard": "邮件包含背景、证据与明确请求，教师确认",
            },
            {
                "requirement": "独立迁移",
                "gap": "尚缺未见情境复测",
                "activity": "retest",
                "completion_standard": "独立完成新材料，保留作答与反馈",
            },
        ]
        if not isinstance(gaps, list) or not 1 <= len(gaps) <= 5:
            raise ValueError("差距任务须为1—5项")
        clean = []
        for g in gaps:
            if not isinstance(g, dict):
                raise ValueError("每条差距必须是对象")
            row = {
                k: g.get(k, "")
                for k in ["requirement", "gap", "activity", "completion_standard"]
            }
            if any(
                not isinstance(v, str) or not v.strip() or len(v) > 1000
                for v in row.values()
            ) or row["activity"] not in [
                "diagnostic",
                "practice",
                "listening",
                "writing",
                "speaking",
                "retest",
            ]:
                raise ValueError("每条差距须含要求、差距、活动及完成标准")
            clean.append(row)
        plan = {
            "target": target,
            "source_url": url,
            "source_status": "需核对机会有效性与截止日期",
            "gaps": clean,
            "value_assessment": "未评估",
            "readiness": "按作品证据逐项核验；不推断录取概率",
            "updated": now(),
        }
        with self.base.db() as db:
            db.execute(
                "UPDATE hd_people SET goal=? WHERE id=?",
                (json.dumps(plan, ensure_ascii=False), id),
            )
        return plan
