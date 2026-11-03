"""Optional real stdio MCP smoke plus in-process learner HTTP, synthetic data only."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'src/base').exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT/'src'))


async def run(folder, log):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from fastapi.testclient import TestClient
    from base.web import create_app
    checks = []
    def check(value, name):
        if not value:
            raise ValueError(name)
        checks.append(name)
    parameters = StdioServerParameters(command=sys.executable, args=['-m','base.mcp'], cwd=str(ROOT), env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'BASE_DATA':folder,'PYTHONUTF8':'1'})
    async with stdio_client(parameters, errlog=log) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            check({'get_context','check_activity','create_activity','list_records','record_feedback','save_learner','get_growth','plan_next','set_activity_state','verify_transfer'} <= tools, 'stdio握手与10项工具发现')
            async def call(name, arguments=None):
                result = await session.call_tool(name, arguments or {})
                if result.isError:
                    raise ValueError('MCP工具失败：'+name)
                value = result.structuredContent
                if value is None:
                    value = json.loads(next(v.text for v in result.content if v.type=='text'))
                return value
            context = await call('get_context')
            check(bool(context['teaching']['principles']), 'MCP可读通用教学约定')
            draft = context['activity'] | {'rubric':[{'label':'证据','max_score':5}]}
            check((await call('check_activity',{'draft':draft}))['valid'], '发布前检查与教学提醒')
            p = await call('save_learner',{'name':'合成MCP学习者','profile':{'goal':'解释一个要点'},'request_key':'profile'})
            task = await call('create_activity',{'learner':p['name'],'learner_id':p['id'],'draft':draft,'request_key':'task'})
            check((await call('create_activity',{'learner':p['name'],'learner_id':p['id'],'draft':draft,'request_key':'task'}))['id']==task['id'], 'MCP发布回执与超时重试')
            client = TestClient(create_app(folder))
            answer = str(draft['expected']) if draft['mode']=='numeric' else '合成作品：一个要点及其证据，下一步执行并观察。'
            row = client.post('/api/learn/'+task['token'],json={'answer':answer,'request_key':'one'}).json()
            saved = await call('record_feedback',{'submission_id':row['id'],'comment':'合成评阅：已有证据，继续换情境验证。','next_step':'换情境复做','scores':[{'label':'证据','score':4}],'judgement':'meets_criteria','request_key':'review'})
            check(saved['total']==4 and client.get('/api/learn/'+task['token']).json()['submissions'][0]['evaluation']['total']==4, 'MCP分项反馈与网页读取共用数据服务')
            check((await call('get_growth',{'learner_id':p['id']}))['meets_criteria']==1 and bool((await call('plan_next',{'learner_id':p['id']}))['suggestion']), 'MCP成长与普通策略函数（允许业务自定义动作名称）')
            await call('verify_transfer',{'submission_id':row['id'],'context':'合成新情境核验；仅测试管线，不宣称真实迁移','independent':True})
            check((await call('get_growth',{'learner_id':p['id']}))['independent_transfer']==1, 'MCP人工迁移证据记录')
            records = await call('list_records')
            check(len(records['learners'])==1 and len(records['submissions'])==1, 'MCP维护者私有记录')
            await call('set_activity_state',{'task_id':task['id'],'state':'paused'})
            check(client.post('/api/learn/'+task['token'],json={'answer':answer,'request_key':'two'}).status_code==400, 'MCP暂停立即约束网页新提交')
            await call('set_activity_state',{'task_id':task['id'],'state':'archived'})
            check(client.get('/api/learn/'+task['token']).json()['state']=='archived', 'MCP归档可从网页读取')
    return {'ok':True,'checks':checks,'mcp_transport':'real-stdio','learner_http':'in-process-TestClient','synthetic_only':True,'teaching_quality_verified':False,'browser_clicks_verified':False}


if __name__ == '__main__':
    try:
        import anyio
        with tempfile.TemporaryDirectory(prefix='base-mcp-check-') as folder:
            with (Path(folder)/'stderr.log').open('w',encoding='utf-8') as log:
                report = anyio.run(run, folder, log)
        print(json.dumps(report,ensure_ascii=False))
    except Exception as error:
        # Avoid logging private MCP tool results or temporary bearer URLs.
        print(json.dumps({'ok':False,'error_type':type(error).__name__,'hint':'先安装requirements-mcp.lock；使用正确工程解释器，检查MCP与业务配置。'},ensure_ascii=False))
        sys.exit(1)
