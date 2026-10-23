"""An asset manager's funds and their holdings — one implementation behind every door that changes them: the API
(api/routers/funds.py) and the sector's standard file (services/ingest/fund_books.py through the intake pipeline).

  registry     a fund as the manager states it: name, type, SFDR article, base currency, parent, LEI
  holding      a holding by ISIN and the issuer data a manager may state with it
  onboarding   holdings into a fund: each ISIN resolved, the issuer located, the position value-weighted
"""
