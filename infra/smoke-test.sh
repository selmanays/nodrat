#!/usr/bin/env bash
# Nodrat production smoke test
#
# Tüm public/admin sayfaların 200 OK döndüğünü, auth-walled API endpoint'lerin
# 401 döndüğünü ve health endpoint'in OK olduğunu doğrular.
#
# Usage:
#   ./infra/smoke-test.sh                       # default: https://nodrat.com
#   SMOKE_BASE=https://staging.nodrat.com ./infra/smoke-test.sh
#
# Exit codes:
#   0 = tüm test'ler geçti
#   1 = en az 1 test başarısız

set -u

BASE="${SMOKE_BASE:-https://nodrat.com}"
FAIL=0
PASS=0
TOTAL=0

# Renk
if [[ -t 1 ]]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[34m'; D=$'\033[0m'
else
  R=""; G=""; Y=""; B=""; D=""
fi

check() {
  local label="$1"
  local url="$2"
  local expected="$3"

  TOTAL=$((TOTAL + 1))
  local actual
  actual=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "${url}" 2>&1)

  if [[ "${actual}" == "${expected}" ]]; then
    printf "  %s✓%s %-45s %s%s%s\n" "${G}" "${D}" "${label}" "${G}" "${actual}" "${D}"
    PASS=$((PASS + 1))
  else
    printf "  %s✗%s %-45s %sgot %s, expected %s%s\n" "${R}" "${D}" "${label}" "${R}" "${actual}" "${expected}" "${D}"
    FAIL=$((FAIL + 1))
  fi
}

check_health() {
  local label="$1"
  local url="$2"

  TOTAL=$((TOTAL + 1))
  local body
  body=$(curl -s -m 10 "${url}" 2>&1)

  if [[ "${body}" == *'"status":"ok"'* ]]; then
    printf "  %s✓%s %-45s %sok%s\n" "${G}" "${D}" "${label}" "${G}" "${D}"
    PASS=$((PASS + 1))
  else
    printf "  %s✗%s %-45s %sbody=%s%s\n" "${R}" "${D}" "${label}" "${R}" "${body:0:60}" "${D}"
    FAIL=$((FAIL + 1))
  fi
}

echo
echo "${B}Nodrat smoke test${D} — base: ${BASE}"
echo

echo "${Y}Public pages (expect 200)${D}"
check "/"                          "${BASE}/"                            200
check "/login"                     "${BASE}/login"                       200
check "/register"                  "${BASE}/register"                    200
check "/bot"                       "${BASE}/bot"                         200

echo
echo "${Y}Legal pages (expect 200)${D}"
check "/legal"                     "${BASE}/legal"                       200
check "/legal/privacy"             "${BASE}/legal/privacy"               200
check "/legal/tos"                 "${BASE}/legal/tos"                   200
check "/legal/kvkk-aydinlatma"     "${BASE}/legal/kvkk-aydinlatma"       200
check "/legal/cookies"             "${BASE}/legal/cookies"               200
check "/legal/scraping"            "${BASE}/legal/scraping"              200
check "/legal/abuse"               "${BASE}/legal/abuse"                 200
check "/legal/takedown"            "${BASE}/legal/takedown"              200
check "/legal/copyright"           "${BASE}/legal/copyright"             200
check "/legal/privacy-request"     "${BASE}/legal/privacy-request"       200

echo
echo "${Y}Admin pages (expect 200 — auth gate is client-side)${D}"
check "/admin"                     "${BASE}/admin"                       200
check "/admin/login"               "${BASE}/admin/login"                 200
check "/admin/sources"             "${BASE}/admin/sources"               200
check "/admin/articles"            "${BASE}/admin/articles"              200
check "/admin/queue"               "${BASE}/admin/queue"                 200
check "/admin/users"               "${BASE}/admin/users"                 200
check "/admin/legal"               "${BASE}/admin/legal"                 200
check "/admin/audit"               "${BASE}/admin/audit"                 200

echo
echo "${Y}Auth-walled API endpoints (expect 401)${D}"
check "/api/admin/sources"         "${BASE}/api/admin/sources"           401
check "/api/admin/articles"        "${BASE}/api/admin/articles"          401
check "/api/admin/queue/overview"  "${BASE}/api/admin/queue/overview"    401
check "/api/admin/users"           "${BASE}/api/admin/users"             401
check "/api/admin/legal/requests"  "${BASE}/api/admin/legal/requests"    401
check "/api/admin/audit"           "${BASE}/api/admin/audit"             401
check "/api/app/me"                "${BASE}/api/app/me"                  401

echo
echo "${Y}Email auth endpoints (POST 422 for missing body)${D}"
check "/auth/verify (no body)"     "${BASE}/api/auth/verify"             405
check "/auth/verify-resend (no)"   "${BASE}/api/auth/verify-resend"      405
check "/auth/password-reset-request" "${BASE}/api/auth/password-reset-request" 405
check "/auth/password-reset"       "${BASE}/api/auth/password-reset"     405

echo
echo "${Y}Public API endpoints${D}"
check_health "/api/health"         "${BASE}/api/health"

echo
echo "${B}Result${D}"
if [[ ${FAIL} -gt 0 ]]; then
  printf "  %s%d failed%s · %d passed · %d total\n" "${R}" "${FAIL}" "${D}" "${PASS}" "${TOTAL}"
  echo
  exit 1
else
  printf "  %sAll %d tests passed%s\n" "${G}" "${TOTAL}" "${D}"
  echo
  exit 0
fi
