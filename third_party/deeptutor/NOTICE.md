# DeepTutor assessment adaptation

Upstream: HKUDS/DeepTutor, commit `1ea7df155447f4caf0e3abc86b3ff5395479cd4a`, inspected 2026-10-29.

The source-bound semantic-assessment pattern in `deeptutor/learning/semantic_assessment.py` and `assessment.py` informed this adaptation. Apache License 2.0 is reproduced in `LICENSE` in this directory. No upstream runtime or additional dependency is installed.

Modified implementation: `src/base/app/companion/aesthetic/prereview.py` and `functional/review_*`. We retain separate deterministic checks and semantic candidates, explicit unknowns, source/version revalidation and bounded model calls. Unlike upstream's confidence-based final receipts, model confidence never publishes a formal teacher judgment here. We add private versioned drafts, teacher edits, explicit publication, paired-student authorization and signed feedback provenance.

The teacher UI, local worker and v6 capability contract are project-specific implementations, not a claimed upstream teacher-review feature. This notice does not grant rights to textbooks, exam banks or learner submissions.

Source: https://github.com/HKUDS/DeepTutor/blob/1ea7df155447f4caf0e3abc86b3ff5395479cd4a/deeptutor/learning/semantic_assessment.py
