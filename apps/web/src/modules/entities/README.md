# `src/modules/entities/`

**Layer:** middle — frontend mirror of `apps/api/app/modules/entities/`.

**Status:** Phase 1 scaffold (empty). Implementation arrives in Phase 7a or 7b depending on backend readiness.

This directory will hold:
- Page components (eski `src/app/<route>/page.tsx` taşıma sonrası)
- Domain-specific UI components
- API client (`api/entities-api.ts` — `src/lib/api.ts` base infra'sını kullanır)
- Custom hooks
- Types

## References

- Backend mirror: [`apps/api/app/modules/entities/README.md`](../../../../api/app/modules/entities/README.md)
- Frontend modularization plan: [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../../wiki/plans/modular-monolith-transition-master-plan.md) §9 Phase 7a/7b
- Architecture spec: [`docs/engineering/modular-monolith-architecture.md`](../../../../../docs/engineering/modular-monolith-architecture.md) §2.3
