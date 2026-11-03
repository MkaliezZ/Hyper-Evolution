"""Judgment rules for feedback on a learner's own submitted work; no I/O."""
def policy():
    return {'id':'self-feedback','version':'1.0','purpose':'help the learner revise this work',
        'steps':['read the frozen goal and criteria','compare the actual work with those criteria',
                 'cite observed work','offer one manageable next step','check again with new work'],
        'authority':'model_suggestion','unseen_media':'describe the missing observation; assess only visible text',
        'conclusion_scope':'this_work_only','formal_teacher_review':False}

def validate(output,context):
    observed=context['text']+'\n'+str(context['answers'])+'\n'+context['material']
    if (context['text'].strip() or context['answers']) and not output['evidence_quotes']:
        raise ValueError('Feedback on observed work needs at least one exact evidence quote')
    if not context['text'].strip() and not context['answers']:
        if output['outcome']!='ungraded':raise ValueError('Only ungraded feedback is appropriate without observed answer text')
    if any(not q or q not in observed for q in output['evidence_quotes']):
        raise ValueError('Evidence quotes must be exact excerpts of the observed answer or material')
    if context['unobserved'] and not output['limitations']:
        raise ValueError('State which media have not been inspected')
