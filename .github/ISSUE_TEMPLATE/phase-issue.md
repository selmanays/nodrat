---
name: Modular Monolith Phase Issue
about: Track a single phase of the Modular Monolith Transition
title: Phase X — <başlık>
labels:
  - modular-monolith
  - architecture
assignees: ''
---

## Master Plan Link
`wiki/plans/modular-monolith-transition-master-plan.md` §Phase X

## Previous Phase / Dependency
<!-- e.g. Blocked by #<previous_phase_issue>; or "-" if Phase 0 -->

## Objective
<!-- 2-3 sentences: why this phase exists, what it must achieve -->

## In Scope
- [ ] <bullet>
- [ ] <bullet>

## Out of Scope
<!-- Especially: model relocation, behavioral changes, new features, unrelated cleanups -->
- ...

## Acceptance Criteria
- [ ] <measurable criterion>
- [ ] CI green (lint + import-linter + tests + alembic check)
- [ ] Staging verification (if applicable)
- [ ] `wiki/plans/modular-monolith-transition-master-plan.md` "Current Status" updated
- [ ] `wiki/log.md` phase-start and phase-end entry added

## Testing Requirements
- [ ] Unit
- [ ] Integration
- [ ] Characterization snapshot (god-file phases only)
- [ ] Eval baseline diff < 0.5 % (retrieval/citation phases only)

## Docs / Wiki Update Requirements
- [ ] `wiki/log.md`
- [ ] `wiki/plans/modular-monolith-transition-master-plan.md`
- [ ] Affected `wiki/decisions/*.md` (if any new/superseded)
- [ ] Affected `docs/engineering/*.md` (if architecture / structure changed)

## Rollback Notes
<!-- Per-PR rollback should be possible; note any phase-specific rollback hazards -->

## Risk Level
- [ ] Low
- [ ] Medium
- [ ] High
- [ ] Very High

## Sub-tasks (PR-level checklist)
- [ ] PR — <scope>
- [ ] PR — <scope>
- [ ] Phase retrospective → `wiki/log.md`

## Related Tracking Issues
<!-- Link cross-cutting trackers: T1 master plan, T2 boundary, T3 docs sync, etc. -->
