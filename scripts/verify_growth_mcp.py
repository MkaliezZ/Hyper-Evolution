"""Real stdio + real network HTTP MCP; cross-check teacher/student HTTP shared records."""

import asyncio, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.growth import GrowthService

ROOT = Path(__file__).resolve().parents[1]
checks = []


def check(value, name):
    if not value:
        raise AssertionError(name)
    checks.append(name)


async def call(session, name, args=None):
    r = await session.call_tool(name, args or {})
    if r.isError:
        raise AssertionError(f"MCP tool failed: {name}")
    return r.structuredContent or json.loads(
        next(c.text for c in r.content if c.type == "text")
    )


async def main():
    with tempfile.TemporaryDirectory(prefix="growth-protocol-") as temp:
        service = GrowthService(temp)
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "BASE_DATA": temp,
            "PYTHONUTF8": "1",
        }
        server = StdioServerParameters(
            command=sys.executable, args=["-m", "growth.mcp_server"], env=env
        )
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                check(
                    {
                        "get_context",
                        "create_student",
                        "start_activity",
                        "record_feedback",
                        "prepare_generation",
                        "save_draft_pack",
                        "verify_transfer",
                    }
                    <= names,
                    "real stdio initialize and tool discovery",
                )
                p = await call(
                    session,
                    "create_student",
                    {
                        "name": "合成协议联动学生",
                        "exam": "toefl",
                        "stage": "predeparture",
                        "goal": "写清楚请求",
                        "request_key": "student",
                    },
                )
                activity = await call(
                    session,
                    "start_activity",
                    {
                        "learner_id": p["person"]["id"],
                        "purpose": "diagnostic",
                        "request_key": "diag",
                    },
                )
                check(
                    "key" not in activity["pack"]["items"][0],
                    "MCP hides answer keys before learner submission",
                )
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                proc = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "growth",
                        "--port",
                        str(port),
                        "--data",
                        temp,
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                base = f"http://127.0.0.1:{port}"
                try:
                    async with httpx.AsyncClient(base_url=base, timeout=20) as web:
                        for _ in range(80):
                            try:
                                if (await web.get("/api/health")).status_code == 200:
                                    break
                            except httpx.ConnectError:
                                pass
                            await asyncio.sleep(0.1)
                        else:
                            raise AssertionError("Owned local server not ready")
                        auth = {"Authorization": "Bearer " + p["access"]}
                        admin = {"X-Owner-Token": service.base.owner_token}
                        pack = service._task(activity["id"])["snapshot"]["growth"]
                        answers = {i["id"]: i["key"][0] for i in pack["items"]}
                        result = (
                            await web.post(
                                "/api/activities/" + activity["id"] + "/submit",
                                headers=auth,
                                json={"answers": answers, "request_key": "first"},
                            )
                        ).json()
                        sid = result["attempts"][0]["id"]
                        check(
                            result["attempts"][0]["automatic"]["score"] == 5,
                            "real student HTTP answers scored against original snapshot",
                        )
                        await call(
                            session,
                            "record_feedback",
                            {
                                "submission_id": sid,
                                "comment": "合成协议测试：关键细节定位清楚",
                                "next_step": "换新情境独立验证",
                                "judgement": "meets_criteria",
                                "request_key": "feedback",
                            },
                        )
                        visible = (
                            await web.get(
                                "/api/activities/" + activity["id"], headers=auth
                            )
                        ).json()
                        check(
                            visible["attempts"][0]["evaluation"]["comment"].startswith(
                                "合成协议测试"
                            ),
                            "stdio teacher feedback visible through real student HTTP",
                        )
                        await web.post(
                            "/api/activities/" + activity["id"] + "/submit",
                            headers=auth,
                            json={"answers": answers, "request_key": "revision"},
                        )
                        snapshot = await call(
                            session, "get_student", {"learner_id": p["person"]["id"]}
                        )
                        check(
                            len(snapshot["tasks"][0]["attempts"]) == 2,
                            "student HTTP revision visible through stdio MCP, original retained",
                        )
                        check(
                            (await web.post("/mcp/", json={})).status_code == 401,
                            "HTTP MCP rejects missing teacher credential",
                        )
                    async with streamablehttp_client(
                        base + "/mcp/",
                        headers={"Authorization": "Bearer " + service.base.owner_token},
                    ) as (read, write, _):
                        async with ClientSession(read, write) as http_session:
                            await http_session.initialize()
                            ctx = await call(http_session, "get_context")
                            check(
                                "toefl" in ctx["exams"],
                                "real Streamable HTTP MCP handshake and tool invocation",
                            )
                            both = await call(
                                http_session,
                                "get_student",
                                {"learner_id": p["person"]["id"]},
                            )
                            check(
                                len(both["tasks"][0]["attempts"]) == 2,
                                "HTTP MCP and stdio MCP share browser records",
                            )
                            async with httpx.AsyncClient(base_url=base,timeout=20) as student_web:
                                unpaired=(await student_web.post('/api/enroll',json={'name':'合成MCP配对验证','exam':'ielts','stage':'application'})).json()
                                uid=unpaired['person']['id']
                                denied=await http_session.call_tool('get_student',{'learner_id':uid})
                                check(denied.isError,'MCP rejects unpaired student data')
                                invite=await call(http_session,'create_pair_code')
                                paired=await student_web.post('/api/pairing/redeem',headers={'Authorization':'Bearer '+unpaired['access']},json={'code':invite['code']})
                                check(paired.status_code==200,'student HTTP redeems MCP pairing invitation')
                                check((await call(http_session,'get_student',{'learner_id':uid}))['person']['id']==uid,'MCP reads newly paired student')
                                await call(http_session,'remove_student_pairing',{'learner_id':uid})
                                denied=await http_session.call_tool('get_student',{'learner_id':uid})
                                check(denied.isError and (await student_web.get('/api/me',headers={'Authorization':'Bearer '+unpaired['access']})).status_code==200,'unpair revokes MCP while student retains access')
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
        result = {
            "ok": True,
            "checks": checks,
            "synthetic_only": True,
            "external_agent_app_configured": False,
            "teaching_effect_verified": False,
        }
        folder = ROOT / "artifacts"
        folder.mkdir(exist_ok=True)
        (folder / "mcp-verification.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
