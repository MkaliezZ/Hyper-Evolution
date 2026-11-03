"""Pure, version-bound subject labels. A category is neither permission nor domain approval."""
from base.app.companion.assets.references import digest

def binding_id(kind,id):return 'subject-'+digest([kind,id])[:24]

def project_subject(meta,binding):
    ref=binding.get('asset_ref',{}) if binding else {}
    current=bool(binding) and all(ref.get(k)==meta.get(k) for k in ['id','revision','source_hash'])
    subject=binding.get('subject') if current else None
    return {'subject':subject,'revision':binding['revision'] if binding else 0,
        'state':'classified' if subject else 'needs_reclassification' if binding and binding.get('subject') and not current else 'unclassified',
        'previous_subject':binding.get('subject') if binding and not current else None,
        'authority':'user_declared_category_not_domain_review'}
