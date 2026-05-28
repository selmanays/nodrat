# `modules/billing/`

**Layer:** parallel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** Phase 1 scaffold → **T7-1/T7-2 (2026-05-28) services/ aktive** (plan_features + quota service taşındı).

## Layout

```
modules/billing/
├── __init__.py       Module facade (lazy; parallel layer docstring)
├── services/
│   ├── __init__.py   Service layer (lazy)
│   ├── plan_features.py   resolve_user_plan_features (T7-1: core/'dan taşındı)
│   └── quota.py           enforce_quota + record_usage + QuotaExceeded (T7-2: core/'dan taşındı)
└── README.md         Bu dosya
```

`plan_features.py` `Plan` + `Subscription` + `User` modellerini import eder. `quota.py` `UsageEvent` modelini import eder (Redis sliding window + usage_events ledger #29). İkisi birlikte billing domain'in core/ consumer'larını temizler → T8-16 (billing 5 model) + T8-17 (UsageEvent) relocation ön-hazırlık.

## Migration history

- 2026-05-28: **T7-2** — `core/quota.py` → `services/quota.py` (100% rename,
  254 satır). Core-consumer cleanup: `core/quota` `UsageEvent` import ediyordu;
  T8-17 (UsageEvent → billing) relocation'ı blocklardı. 3 caller flip:
  `api/app_research_stream.py:51` (QuotaExceeded, enforce_quota) +
  `api/app_research_stream.py:1259` (record_usage lazy) +
  `tests/unit/test_research_telemetry_wired.py:40` (source-text assertion yeni
  path'e güncellendi — file-path string dersi). Behavior-preserving; no DB/migration;
  Redis sliding window + usage_events ledger AYNEN. T8-17 + T8-16 full billing
  unblock. Bkz. [[t7-cost-tracker-core-consumer-cleanup-mini-plan]].
- 2026-05-28: **T7-1** — `core/plan_features.py` → `services/plan_features.py`
  (100% rename, 85 satır). Core-consumer cleanup (T7 initiative): `core/*`'ın
  model import etmesi (`Plan`, `Subscription`, `User`) `core/* must not import
  modules/*` contract'ını T8-16 billing relocation sonrası patlatacaktı; service
  billing domain'e taşındı. 2 caller flip: `modules/style_profiles/routes.py:33`
  (resolve_user_plan_features) + `tests/unit/test_plan_features.py`. Behavior-preserving;
  no DB/migration; pure function module move. T8-16 billing model relocation unblock
  yolunu açar. Bkz. [[t7-cost-tracker-core-consumer-cleanup-mini-plan]].

## References

- Responsibility + allowed/forbidden imports: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3
- Boundary decision: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction rules (CI-enforced): [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../docs/engineering/refactor-playbook.md)
