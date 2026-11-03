"""Exam-aligned original micro-drills. No claim of equated difficulty or official score."""

from copy import deepcopy
import hashlib
import json
from random import Random

BLUEPRINTS = {
    "ielts": {
        "name": "雅思 Academic · 机考",
        "version": "IELTS-Academic-2026-10",
        "reading": [
            "multiple_choice",
            "true_false_not_given",
            "matching_headings",
            "completion",
        ],
        "listening": [
            "conversation",
            "monologue",
            "education_conversation",
            "academic_monologue",
        ],
        "writing": ["academic_task1", "task2"],
        "speaking": ["part1", "part2", "part3"],
        "rules": [
            "FALSE必须有反证，NOT GIVEN须缺少所问信息",
            "补全题遵守字数限制和可接受拼写",
            "机考听力结束后2分钟检查；没有10分钟转抄",
            "写作/口语用量规和作品证据评阅，不冒充正式Band",
        ],
    },
    "toefl": {
        "name": "托福 iBT · 2026新版",
        "version": "TOEFL-iBT-2026-01-21",
        "reading": ["complete_words", "daily_life", "academic_passage"],
        "listening": [
            "choose_response",
            "conversation",
            "announcement",
            "academic_talk",
        ],
        "writing": ["build_sentence", "email", "academic_discussion"],
        "speaking": ["listen_repeat", "interview"],
        "rules": [
            "按2026-01-21新版任务结构",
            "日常文本考查目的、细节和行动要求",
            "拼句、邮件与讨论使用不同评价依据",
            "练习适应难度不等于ETS自适应等值；不输出官方换算分",
        ],
    },
}
STAGES = {"application": "申请准备", "predeparture": "行前准备", "enrolled": "海外在读"}
SKILLS = {
    "contradiction": "区分反证与未提及",
    "detail": "定位关键细节",
    "purpose": "理解目的与下一步",
    "inference": "依据原文推断",
    "listening_detail": "听清关键细节",
    "communication": "清楚表达与回应任务",
}


def make_drill(exam, stage, focus="detail", seed="0", purpose="practice"):
    """Generate fresh, answerable stimuli from semantic slots; independent families per use."""
    if exam not in BLUEPRINTS or stage not in STAGES:
        raise ValueError("请选择有效的考试和留学阶段")
    rng = Random(hashlib.sha256(str(seed).encode()).hexdigest())
    idpart = hashlib.sha256(str(seed).encode()).hexdigest()[:12]
    place = rng.choice(
        [
            "library",
            "student centre",
            "language centre",
            "research centre",
            "arts centre",
        ]
    )
    day = rng.choice(["Monday", "Tuesday", "Wednesday", "Thursday"])
    hour = rng.choice([9, 10, 11, 14, 15, 16])
    room = rng.choice([104, 207, 312, 406, 508])
    topic = {
        "application": "information session",
        "predeparture": "arrival workshop",
        "enrolled": "research workshop",
    }[stage]
    heading = f"{topic.title()} · {place.title()}"
    source = {
        "kind": "original",
        "title": "超维伴学原创微练习",
        "version": "1",
        "review": "developer_template_checked",
        "calibration": "未标定，不是官方真题",
    }

    def mc(i, q, options, key, evidence, skill, reason):
        order = list(range(len(options)))
        rng.shuffle(order)
        return {
            "id": str(i),
            "kind": "mcq",
            "prompt": q,
            "options": [options[j] for j in order],
            "key": [chr(65 + order.index(key))],
            "evidence": evidence,
            "skill": skill,
            "explanation": reason,
            "distractors": "其余选项与原文明示细节矛盾，或原文没有支持。",
        }

    if exam == "ielts":
        early = hour
        late = hour + 3
        stimulus = f"The {place} is running an {topic} on {day}. It begins at {early}:00 and ends at {late}:00. Participants meet in Room {room}. Current students may attend free of charge; visitors must pay £12. Everyone must register online before arriving. Participants should bring a university card or another form of photo identification. Laptops are optional, and printed materials will be provided. The workshop includes a short introduction followed by guided activities. Staff will collect comments at the end. The notice does not provide any information about parking facilities."
        items = [
            {
                "id": "1",
                "kind": "tfng",
                "prompt": "Visitors can attend the workshop without paying.",
                "key": ["FALSE"],
                "evidence": "visitors must pay £12",
                "skill": "contradiction",
                "explanation": "原文明确访客需付费，与免费相矛盾，应选FALSE。",
            },
            {
                "id": "2",
                "kind": "tfng",
                "prompt": "Free parking is available for all participants.",
                "key": ["NOT GIVEN"],
                "evidence": "The notice does not provide any information about parking facilities.",
                "skill": "contradiction",
                "explanation": "没有停车费用信息；不能由未提及推断为收费或免费。",
            },
            {
                "id": "3",
                "kind": "tfng",
                "prompt": "Participants have to register before the workshop.",
                "key": ["TRUE"],
                "evidence": "Everyone must register online before arriving.",
                "skill": "detail",
                "explanation": "register before arriving直接支持题干。",
            },
            {
                "id": "4",
                "kind": "gap",
                "prompt": "Write ONE NUMBER ONLY. The room number is ___.",
                "key": [str(room)],
                "word_limit": 1,
                "evidence": f"Room {room}",
                "skill": "detail",
                "explanation": "只填数字，不写Room或添加说明。",
            },
            mc(
                5,
                "What should every participant bring?",
                [
                    "Photo identification",
                    "A laptop",
                    "A printed ticket",
                    "A parking permit",
                ],
                0,
                "a university card or another form of photo identification",
                "purpose",
                "laptop是optional；身份证明才是必须携带的。",
            ),
        ]
        task_type = "true_false_not_given + completion + multiple_choice"
    else:
        stimulus = f"To: Participants\nSubject: Updated arrangements for the {topic}\nThe {topic} will take place in Room {room} at the {place} on {day}. The starting time remains {hour}:00. The original room is unavailable because repairs are underway. Please register online before arriving; existing registrations remain valid. Bring a photo ID. A laptop is optional because loan computers can be reserved. If you need a loan computer, email the organizer by noon the day before the workshop. Do not submit another registration. A reminder will be sent on the morning of the event."
        items = [
            mc(
                1,
                "Why was this email sent?",
                [
                    "To explain updated arrangements",
                    "To cancel the event",
                    "To request another registration",
                    "To announce a later starting time",
                ],
                0,
                "Subject: Updated arrangements",
                "purpose",
                "邮件目的在于通知安排；取消、重报、推迟都无据。",
            ),
            mc(
                2,
                "What should someone needing a computer do?",
                [
                    "Email the organizer before the deadline",
                    "Buy a new computer",
                    "Send another registration",
                    "Arrive after the workshop",
                ],
                0,
                "email the organizer by noon the day before the workshop",
                "detail",
                "需要借用设备者须按截止时间发邮件。",
            ),
            mc(
                3,
                "Why is the original room unavailable?",
                [
                    "It is being repaired",
                    "It is too small",
                    "The workshop was cancelled",
                    "The organizer forgot to reserve it",
                ],
                0,
                "repairs are underway",
                "detail",
                "原文明示维修，不能用其他合理猜测替代。",
            ),
            mc(
                4,
                "What can be inferred about existing registrations?",
                [
                    "They still allow participation",
                    "They must all be replaced",
                    "They are valid only after noon",
                    "They cannot be used in the new room",
                ],
                0,
                "existing registrations remain valid",
                "inference",
                "remain valid说明原报名继续有效。",
            ),
            mc(
                5,
                "Which item is required?",
                [
                    "A photo ID",
                    "A personal laptop",
                    "A printed registration",
                    "A repair notice",
                ],
                0,
                "Bring a photo ID",
                "detail",
                "电脑是可选，身份证明是要求。",
            ),
        ]
        task_type = "Read in Daily Life"
    if exam == "ielts":
        stimulus = stimulus.replace(
            " The notice does not provide any information about parking facilities.", ""
        )
        items[1]["evidence"] = "全文没有停车设施或收费的相关信息。"
        if rng.choice([True, False]):
            items[0].update(
                prompt="Visitors are charged a fee to attend the workshop.",
                key=["TRUE"],
                explanation="visitors must pay £12直接支持访客收费。",
            )
        if rng.choice([True, False]):
            items[2].update(
                prompt="People can attend without registering in advance.",
                key=["FALSE"],
                explanation="Everyone must register before arriving与无需预先报名矛盾。",
            )
        if purpose == "practice" and focus == "contradiction":
            items[4] = {
                "id": "5",
                "kind": "tfng",
                "prompt": "A laptop is required for every participant.",
                "key": ["FALSE"],
                "evidence": "Laptops are optional",
                "skill": "contradiction",
                "explanation": "optional是可选，与required必须相矛盾。",
            }
    # Transfer uses a different situation and proposition structure, not a cosmetic room-number swap.
    if purpose == "retest" and exam == "ielts":
        quantity = rng.choice([2, 3, 4])
        days = rng.choice([5, 7, 10])
        fee = rng.choice([2, 3, 4])
        heading = "Borrowing equipment · independent transfer"
        task_type = "true_false_not_given + completion"
        stimulus = f"The university media desk lends cameras to current students. Each student may borrow up to {quantity} cameras at a time for a maximum of {days} days. Staff members can borrow laptops but are not eligible to borrow cameras under this scheme. Camera bookings are made online and must be confirmed by the desk before collection. The student must present a university card when collecting equipment. There is no borrowing fee, but returning a camera after the deadline costs £{fee} per day. Students should report any existing damage before leaving the desk. Equipment that stops working during a loan must be returned for inspection; students must not attempt repairs themselves."
        items = [
            {
                "id": "1",
                "kind": "tfng",
                "prompt": "University staff can borrow cameras through this scheme.",
                "key": ["FALSE"],
                "evidence": "Staff members ... are not eligible to borrow cameras under this scheme",
                "skill": "contradiction",
                "explanation": "不能把可借笔记本电脑扩大为可借摄像机。",
            },
            {
                "id": "2",
                "kind": "tfng",
                "prompt": "The university buys all its cameras from the same supplier.",
                "key": ["NOT GIVEN"],
                "evidence": "全文未提供设备采购供应商信息。",
                "skill": "contradiction",
                "explanation": "设备借用政策没有涉及采购来源，不能判断同一供应商。",
            },
            {
                "id": "3",
                "kind": "tfng",
                "prompt": "Students should tell the desk about damage they notice before taking equipment away.",
                "key": ["TRUE"],
                "evidence": "report any existing damage before leaving the desk",
                "skill": "detail",
                "explanation": "report damage与tell the desk about damage同义。",
            },
            {
                "id": "4",
                "kind": "gap",
                "prompt": "Write ONE NUMBER ONLY. A student can borrow up to ___ cameras.",
                "key": [str(quantity)],
                "word_limit": 1,
                "evidence": f"up to {quantity} cameras",
                "skill": "detail",
                "explanation": "注意借用数量上限，不要填最大借用天数。",
            },
            {
                "id": "5",
                "kind": "gap",
                "prompt": "Write ONE NUMBER ONLY. An overdue camera costs £___ per day.",
                "key": [str(fee)],
                "word_limit": 1,
                "evidence": f"after the deadline costs £{fee} per day",
                "skill": "detail",
                "explanation": "借用免费不代表逾期也免费；区分条件。",
            },
        ]
    if purpose == "retest" and exam == "toefl":
        heading = "Urban gardens · independent transfer"
        task_type = "Read an Academic Passage"
        stimulus = "Urban gardens can affect nearby temperatures, but their influence depends on more than the number of plants. Leaves provide shade, which reduces the amount of sunlight reaching roads and walls. Plants also release water through their leaves, helping to cool the surrounding air. However, a small garden surrounded by tall buildings may receive little sunlight and offer only limited cooling beyond its boundaries. Researchers therefore measure temperatures at several distances rather than assuming that every garden produces the same result. In one study, temperatures fell most clearly beside a garden, while streets farther away showed little change. This finding does not mean that small gardens lack value: they may still provide habitats and places for people to meet. It suggests that cities should consider the location and design of green spaces when planning for heat reduction."
        items = [
            mc(
                1,
                "What is the main point of the passage?",
                [
                    "The cooling effect of urban gardens depends on their conditions",
                    "All gardens cool whole cities equally",
                    "Gardens are useful only for social meetings",
                    "Tall buildings always prevent plant growth",
                ],
                0,
                "their influence depends on more than the number of plants",
                "purpose",
                "文章强调效果取决于条件，并非所有花园产生相同效果。",
            ),
            mc(
                2,
                "How do leaves help cool their surroundings?",
                [
                    "They provide shade and release water",
                    "They absorb all nearby heat",
                    "They remove surrounding buildings",
                    "They cause streets to become wider",
                ],
                0,
                "Leaves provide shade ... Plants also release water",
                "detail",
                "原文列出遮阴与释放水分两个机制。",
            ),
            mc(
                3,
                "Why do researchers measure at different distances?",
                [
                    "Cooling may not extend equally far from a garden",
                    "They want to count all the buildings",
                    "They cannot measure near plants",
                    "Gardens change location every day",
                ],
                0,
                "measure temperatures at several distances rather than assuming ... the same result",
                "inference",
                "从不同距离读数可检验效果范围，不能假设处处相同。",
            ),
            mc(
                4,
                "What did the study find about more distant streets?",
                [
                    "Their temperatures changed little",
                    "They became much colder",
                    "They had more plants",
                    "They received no sunlight",
                ],
                0,
                "streets farther away showed little change",
                "detail",
                "little change与changed little同义。",
            ),
            mc(
                5,
                "What does the author suggest for urban planning?",
                [
                    "Consider where green spaces are and how they are designed",
                    "Replace all small gardens with roads",
                    "Count plants without measuring temperature",
                    "Build every garden beside a tall building",
                ],
                0,
                "consider the location and design of green spaces",
                "purpose",
                "最后一句给出规划建议，并未提出统一选址或取消小花园。",
            ),
        ]
    if purpose == "practice":
        items.sort(key=lambda x: x["skill"] != focus)
    elif purpose == "retest":
        rng.shuffle(items)
    return {
        "id": "original-" + idpart,
        "family_id": f"original-{exam}-{idpart}",
        "title": heading,
        "exam": exam,
        "stage": stage,
        "task_type": task_type,
        "skill": focus,
        "blueprint": BLUEPRINTS[exam]["version"],
        "purpose": purpose,
        "instructions": "独立阅读后作答。判断题按原文，不用常识补充；补全题遵守字数要求。",
        "stimulus": stimulus,
        "items": items,
        "source": source,
        "status": "ready",
        "audio": None,
        "generator": {
            "type": "local_semantic_template",
            "seed_hash": idpart,
            "focus": focus,
            "note": "本地规则生成；没有调用语言模型。",
        },
    }


def writing_task(exam, stage, seed="writing"):
    pack = make_drill(exam, stage, "communication", seed)
    pack["id"] = "writing-" + pack["id"]
    pack["family_id"] = pack["id"]
    pack["items"] = []
    pack["skill"] = "communication"
    pack["task_type"] = "Write an Email" if exam == "toefl" else "Writing Task 2"
    pack["title"] = (
        "写一封明确提出请求的邮件" if exam == "toefl" else "有依据地表达观点"
    )
    pack["instructions"] = (
        "先独立完成初稿。系统只给结构提示，教师按量规评阅内容；反馈后可以修订。"
    )
    pack["stimulus"] = (
        "You are joining a university workshop, but the registration system incorrectly shows that you have not completed a prerequisite. Write an email to the coordinator. Explain the problem, describe the relevant course and evidence you can provide, and ask what you should do to confirm your place. You have 7 minutes."
        if exam == "toefl"
        else "Some people believe universities should focus on academic knowledge, while others believe practical skills are equally important. Discuss both views and give your own opinion. Give reasons and relevant examples. Write at least 250 words; suggested time: 40 minutes."
    )
    pack["rubric"] = ["任务回应与必备细节", "组织与连贯", "词汇使用", "语法与表达"]
    return pack


def speaking_task(exam, stage, seed="speaking"):
    pack = writing_task(exam, stage, seed)
    pack["id"] = "speaking-" + pack["id"]
    pack["family_id"] = pack["id"]
    pack["title"] = "录一段清楚的英文表达"
    pack["task_type"] = "Take an Interview" if exam == "toefl" else "Speaking Part 2"
    pack["instructions"] = (
        "可以直接录音或上传录音。教师会根据录音给内容和表达反馈；自动转写尚未配置。"
    )
    pack["stimulus"] = (
        "Answer each question in up to 45 seconds: 1. Where do you prefer to study? 2. Describe a time you studied with others. 3. What makes group work difficult? 4. Should universities provide more shared study spaces?"
        if exam == "toefl"
        else "Describe a place where you enjoy studying. Say where it is, what it is like, what you do there, and explain why you enjoy studying there. Prepare for 1 minute, then speak for 1–2 minutes."
    )
    pack["rubric"] = ["表达与连贯", "内容回应", "词汇与语法", "发音与可理解度"]
    return pack


def grade(pack, answers):
    if pack.get('academic'):
        from base.app.companion.aesthetic.academic import grade as academic_grade
        return academic_grade(pack,answers)
    if not isinstance(answers, dict):
        raise ValueError("答案须为题号到作答的对象")
    expected_ids = {i["id"] for i in pack["items"]}
    if set(answers) - expected_ids:
        raise ValueError("答案包含本次活动中不存在的题号")
    results = []
    for item in pack["items"]:
        raw = answers.get(item["id"], "")
        if not isinstance(raw, str) or len(raw) > 400:
            raise ValueError("单题答案须为400字内文字")
        answer = " ".join(raw.strip().casefold().split())
        keys = [" ".join(x.strip().casefold().split()) for x in item["key"]]
        correct = answer in keys
        if item.get("word_limit") and len(answer.split()) > item["word_limit"]:
            correct = False
        results.append(
            {
                "id": item["id"],
                "correct": correct,
                "answer": raw,
                "accepted": item["key"],
                "evidence": item["evidence"],
                "skill": item["skill"],
                "explanation": item["explanation"],
            }
        )
    score = sum(i["correct"] for i in results)
    weak = {i["skill"] for i in results if not i["correct"]}
    return {
        "status": "reviewed",
        "correct": score == len(results),
        "score": score,
        "total": len(results),
        "items": results,
        "weak_skills": sorted(weak),
        "comment": f"本次答对{score}/{len(results)}题。"
        + (
            "请先区分原文反证与未提供信息。"
            if "contradiction" in weak
            else "按逐题证据修正，再换新材料检验。"
            if weak
            else "本次表现良好；再用未见材料验证，不能只记住答案。"
        ),
        "next_step": "按错因补练后完成未见材料复测。",
        "meaning": "本次微练习原始表现，不是考试等级或长期掌握度。",
    }


def evaluate_base(activity, answer):
    pack = activity["growth"]
    try:
        value = json.loads(answer)
    except ValueError:
        raise ValueError("结构化作答格式无效") from None
    if pack["items"]:
        return grade(pack, value.get("answers", {}))
    text = value.get("text", "")
    words = len(text.split())
    return {
        "status": "pending",
        "correct": None,
        "comment": f"已收到作品，共{words}个英文词。内容、逻辑与发音需按量规评阅；字数不代表质量。",
        "next_step": "等待教师具体反馈，随后提交修订。",
        "words": words,
    }


def public_pack(pack, feedback=False):
    result = deepcopy(pack)
    for i in result["items"]:
        if result.get('academic') and not feedback:
            i.pop('traps',None)
            if i.get('k12_type')=='listening':i.pop('material',None)
        for field in ["key", "evidence", "explanation", "distractors"]:
            if not feedback:
                i.pop(field, None)
    if not feedback:
        result.pop("transcript", None)
    result.pop("media_path", None)
    return result
