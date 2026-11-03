"""Growth orientation adapted from Toushi-Wenlu; no exam or admissions scores."""
POLICY_ID = 'learning.growth_orientation'
VERSION = '1.0.0'
STAGES = {'exploring':'探索方向','preparing':'积累准备','acting':'行动实践','reviewing':'复盘调整'}


def guide(content, evidence_count=0):
    missing = []
    if not content.get('goal'): missing.append('选一个接下来想达到的目标')
    requirements = content.get('requirements', [])
    if not requirements: missing.append('写清这个目标需要什么')
    for i, item in enumerate(requirements, 1):
        if not item.get('current_evidence'): missing.append(f'第{i}项：补上已有准备或作品')
        if not item.get('next_action'): missing.append(f'第{i}项：选一个下一步行动')
        if not item.get('completion_standard'): missing.append(f'第{i}项：说清做到什么程度')
    return {'id':POLICY_ID,'version':VERSION,'phases':['收资','投石','问路','展示'],
            'stage_label':STAGES[content['stage']], 'stage_source':'填写者声明',
            'missing':missing,'task_evidence_count':evidence_count,
            'principles':['已有成果与准备行动分开','目标要求逐项对应准备和完成标准','成长阶段由填写者声明，作品记录单独呈现'],
            'opportunity_search':'not_connected','score':'not_generated'}
