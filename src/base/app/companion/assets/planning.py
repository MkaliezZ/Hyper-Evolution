"""Immutable content identity for local growth plans, without storage or execution."""
from base.app.companion.assets.references import digest

FIELDS = ['id','revision','owner_device','subject_device','author_role','content','evidence_refs','created','parent_hash']


def seal(value):
    return {**value,'content_hash':digest({k:value[k] for k in FIELDS})}


def verify(value):
    if value.get('content_hash') != digest({k:value[k] for k in FIELDS}):
        raise ValueError('成长规划内容发生变化，请重新保存后分享')
    return value
