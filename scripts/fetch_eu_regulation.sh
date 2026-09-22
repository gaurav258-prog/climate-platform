#!/usr/bin/env bash
# Fetch the official EU Official Journal text of a regulation/directive by CELEX number, bypassing
# eur-lex.europa.eu's AWS WAF Bot Control challenge (x-amzn-waf-action: challenge — a JS-computation
# challenge that blocks curl/WebFetch/any non-browser client, regardless of User-Agent spoofing).
#
# Route: publications.europa.eu's Cellar repository — the same official EU Publications Office document
# store EUR-Lex's own frontend is built on, on a different domain with NO bot-challenge. Plain HTTP content
# negotiation, no API key, no auth.
#
# Usage:
#   scripts/fetch_eu_regulation.sh <CELEX_ID> [output_file]
#
# CELEX_ID formats:
#   Original enactment:        3<year><type><number>        e.g. 32022R2453 (Pillar 3 ESG ITS)
#   Consolidated/as-amended:   0<year><type><0number>-<YYYYMMDD>
#                               e.g. 02015R0035-20200101 (Solvency II, as amended by (EU) 2019/981,
#                               in force from 2020-01-01 — the exact point-in-time regulators enforce)
#   Type letters: R=Regulation, L=Directive, D=Decision
#   Find the right consolidated date on the regulation's own EUR-Lex page (viewable in a real browser —
#   only the raw-text FETCH is blocked, not human browsing) under "Consolidated versions".
#
# Output is real Official Journal XHTML — can be large (a few hundred KB to tens of MB for a big
# regulation with all annexes). Don't load the whole file into an LLM context; grep/extract the specific
# article or annex needed, e.g.:
#   scripts/fetch_eu_regulation.sh 32023R1115 /tmp/eudr.html
#   grep -A 40 'Article 9' /tmp/eudr.html | sed 's/<[^>]*>//g'
#
# Examples used in this platform's regulatory-fidelity audits (2026-09):
#   32022R2453              CIR (EU) 2022/2453 — Pillar 3 ESG ITS (Annex XXXIX/XL)
#   32021R2178              Del. Reg. (EU) 2021/2178 — Taxonomy Art. 8 delegated act (GAR, non-financial KPIs)
#   32021R2139              Del. Reg. (EU) 2021/2139 — Climate Delegated Act (technical screening criteria)
#   32022R1288              Del. Reg. (EU) 2022/1288 — SFDR RTS (PAI Annex I, pre-contractual Annex II/III)
#   32023R1115              Reg. (EU) 2023/1115 — EUDR
#   32023R2772              Del. Reg. (EU) 2023/2772 — ESRS Set 1
#   02015R0035-20200101     Del. Reg. (EU) 2015/35 as amended by 2019/981 — Solvency II (consolidated)
#   32006R1893              Reg. (EC) 1893/2006 — NACE Rev. 2

set -euo pipefail

CELEX="${1:?Usage: $0 <CELEX_ID> [output_file]}"
OUT="${2:-/tmp/${CELEX}.html}"

curl -sSL --max-time 60 \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  -H "Accept: application/xhtml+xml" \
  -H "Accept-Language: eng, en" \
  "http://publications.europa.eu/resource/celex/${CELEX}" \
  -o "$OUT"

SIZE=$(wc -c < "$OUT" | tr -d ' ')
if [ "$SIZE" -lt 500 ]; then
  echo "FAILED — response too small ($SIZE bytes), likely a 404 (wrong CELEX / no consolidated version at that date):" >&2
  cat "$OUT" >&2
  exit 1
fi
echo "OK — wrote $SIZE bytes to $OUT"
