<!--
Refactor PR template — Modular Monolith Transition
Default feature template is at .github/pull_request_template.md
Activate this template by appending ?template=refactor.md to the PR URL.
-->

## Linked Issue
<!-- Closes #<issue>  or  Part of #<issue> -->

## Scope Type
- [ ] Refactor (behavior-preserving)
- [ ] Documentation
- [ ] Infrastructure / CI
- [ ] Feature  ← if checked, **use the default template instead**
- [ ] Fix      ← if checked, **use the default template instead**

> A single PR carries one scope. Refactor + feature mixing is forbidden.

## What Changed
<!-- 2-5 lines — file / module level -->

## What Did NOT Change (behavior-preserving guarantee)
- [ ] Application behavior (no functional change)
- [ ] URL contracts
- [ ] Celery task names
- [ ] DB schema (no Alembic migration in a refactor PR)
- [ ] LLM prompt content (including RC3-B v2 marker-detect)
- [ ] Runtime config keys / Redis pub/sub channels

## Tests Run
- [ ] Unit (`pytest tests/unit`)
- [ ] Integration (`pytest tests/integration`)
- [ ] Characterization snapshot (retrieval / SSE / extraction — if applicable)
- [ ] Eval baseline diff (recall@5/10 — if applicable; required for RAG-touching PRs)
- [ ] Frontend tsc + Playwright smoke (if frontend touched)

## Boundary Impact (Import-Linter)
- [ ] New `modules/<mod>` or `shared/<sub>` added — under strict contract from day one
- [ ] Legacy `app.core.*` or `app.api.*` moved — promoted into strict contract
- [ ] No violation (CI green)

## Docs / Wiki Updates (in this PR)
- [ ] `wiki/log.md` entry
- [ ] `wiki/plans/modular-monolith-transition-master-plan.md` "Current Status" updated
- [ ] New decision page `wiki/decisions/<slug>.md` (if any)
- [ ] `docs/engineering/*` updated (if architecture / structure shifted)
- [ ] Bidirectional backlink check

## Rollback Plan
<!-- What happens if this PR is reverted; any special steps (worker restart, cache invalidate) -->

## Module(s) Affected
<!-- e.g. modules/sources, shared/runtime_config, frontend/modules/billing -->

## Risk Level
- [ ] Low
- [ ] Medium
- [ ] High

## Notes for Reviewer
<!-- Especially: staging verification evidence (screenshot/link), characterization diff summary -->
