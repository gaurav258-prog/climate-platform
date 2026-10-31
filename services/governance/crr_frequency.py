"""How often an institution discloses its ESG risks under Pillar 3 (bank_p3esg), as Regulation (EU) No 575/2013 (CRR)
says — from the institution's stated size class and listing (services.governance.crr_filers holds the statements), E354.

  a large institution          Art. 433a(1): Article 449a 'on a semi-annual basis' (point (b)(xv))
  a large non-listed, not G-SII Art. 433a(2): 'all the information required under this Part on an annual basis'
  a small and non-complex one  Art. 433b(1)(e), (2): Article 449a on an annual basis, listed or not
  any other institution        Art. 433c(1)(a), (2)(ea): annual, listed or not

So an institution discloses semi-annually when it is a G-SII (listed or not: the derogation of Art. 433a(2) is for
'large institutions other than G-SIIs'), or a large institution that is listed; every other institution annually. A
G-SII and an institution that is not large need no listing statement; a large institution other than a G-SII does.

The semi-annual disclosure is made at the reference date of the half-yearly financial report (services.governance.periods:
the end of the first six months of the financial year), and EBA publishes it 'on the same day as the institutions publish
their financial reports for the corresponding period' (Art. 433); an institution submits it 'no later than' that date
(Art. 434(2)). The calendar dates it by the latest date the Transparency Directive allows a half-yearly financial report —
three months after the half-year (Directive 2004/109/EC Art. 5(1) as replaced by Directive 2013/50/EU) — as it dates the
annual disclosure by the annual report's four months (data/reference/regulatory_mandates.json): a planning date, not the
competent authority's timeframe (Art. 433, Directive 2013/36/EU Art. 106), which a supervisor's published date replaces.
Every table and template of the ESG section is disclosed at each date: Implementing Regulation (EU) 2024/3172 Art. 22(1)
names qualitative and quantitative information alike, and its Art. 26 populates the templates 'in accordance with the
frequency of the disclosure laid down in Articles 433a, 433b and 433c' (quarterly periods; a semi-annual discloser gives
T, T-2 and T-4 — the ESG templates have no period columns); Art. 24d, inserted by Implementing Regulation (EU) 2026/722,
names the disclosures 'with reference dates 30 June 2025, 30 September 2025 and 31 December 2025'.

EBA Single Rulebook Q&A (checked 2026-10-31; keywords 449a — 102 Q&As —, 433a, 433b, 433c, semi-annual, frequency,
non-listed): 2022_6444 (final, submitted 10 May 2022, published 30 Jun 2023) — 'the reference date of the financial
statement/ financial reports and the reference date of the information published in accordance with Part Eight CRR should
be aligned'; 2024_7126 (rejected 7 Jan 2025) — CRR3 is 'clearly specifying the frequency of disclosures for the different
types of institutions'; 2025_7567 (rejected 26 Sep 2025) — the periods are 'already explained in Article 26' of ITS
2024/3172; none on the semi-annual reference date of the ESG disclosures.
"""
from __future__ import annotations

CRR = "02013R0575-20250101"
ITS = "32024R3172"
SEMIANNUAL, ANNUAL = "semiannual", "annual"
GSII, LARGE, NOT_LARGE = "gsii", "large", "not_large"
LISTED, NON_LISTED = "listed", "non_listed"

# each reading above, in the act's own words (data/sources/legal; checked word for word by tests/unit/test_crr_frequency.py)
QUOTES = {
    "CRR Art. 433a(1)": (CRR, "Large institutions shall disclose the information outlined below with the following "
                              "frequency: (a) all the information required under this Part on an annual basis; (b) on a "
                              "semi-annual basis the information referred to in:"),
    "CRR Art. 433a(1)(b)(xv)": (CRR, "(xv) Article 449a;"),
    "CRR Art. 433a(2)": (CRR, "By way of derogation from paragraph 1, large institutions other than G-SIIs that are "
                              "non-listed institutions shall disclose the information outlined below with the following "
                              "frequency: (a) all the information required under this Part on an annual basis; (b) the key "
                              "metrics referred to in Article 447 on a semi-annual basis."),
    "CRR Art. 433b(1)": (CRR, "Small and non-complex institutions shall disclose the information referred to in the "
                              "following provisions on an annual basis:"),
    "CRR Art. 433b(1)(e)": (CRR, "(d) the key metrics referred to in Article 447; (e) Article 449a;"),
    "CRR Art. 433b(2)": (CRR, "By way of derogation from paragraph 1 of this Article, small and non-complex institutions "
                              "that are non-listed institutions shall disclose the key metrics referred to in Article 447 "
                              "and ESG risks referred to in Article 449a on an annual basis."),
    "CRR Art. 433c(1)": (CRR, "Institutions that are not subject to Article 433a or 433b shall disclose the information "
                              "outlined below with the following frequency: (a) all the information required under this "
                              "Part on an annual basis; (b) the key metrics referred to in Article 447 on a semi-annual "
                              "basis."),
    "CRR Art. 433c(2)": (CRR, "By way of derogation from paragraph 1 of this Article, other institutions that are "
                              "non-listed institutions shall disclose the following information on an annual basis:"),
    "CRR Art. 433c(2)(ea)": (CRR, "(ea) the information referred to in Article 449a;"),
    "CRR Art. 4(1)(133)": (CRR, "‘G-SII’ means a G-SII that has been identified in accordance with Article 131(1) and (2) "
                                "of Directive 2013/36/EU;"),
    "CRR Art. 4(1)(146)": (CRR, "‘large institution’ means an institution that meets any of the following conditions: "
                                "(a) it is a G-SII; (b) it has been identified as an other systemically important "
                                "institution (O-SII) in accordance with Article 131(1) and (3) of Directive 2013/36/EU; (c) "
                                "it is, in the Member State in which it is established, one of the three largest "
                                "institutions in terms of total value of assets; (d) the total value of its assets on an "
                                "individual basis or, where applicable, on the basis of its consolidated situation in "
                                "accordance with this Regulation and Directive 2013/36/EU is equal to or greater than EUR "
                                "30 billion;"),
    "CRR Art. 4(1)(148)": (CRR, "‘non-listed institution’ means an institution that has not issued securities that are "
                                "admitted to trading on a regulated market of any Member State, within the meaning of point "
                                "(21) of Article 4(1) of Directive 2014/65/EU;"),
    "CRR Art. 4(1)(149)": (CRR, "‘financial report’ means, for the purposes of Part Eight, a financial report within the "
                                "meaning of Articles 4 and 5 of Directive 2004/109/EC"),
    "CRR Art. 433": (CRR, "EBA shall publish semi-annual and quarterly disclosures on its website on the same day as the "
                          "institutions publish their financial reports for the corresponding period, where applicable, "
                          "or as soon as possible thereafter."),
    "CRR Art. 434(2)": (CRR, "Institutions other than small and non-complex institutions shall submit the disclosures "
                             "required under Articles 433a and 433c in electronic format to EBA no later than the date on "
                             "which they publish their financial statements or financial reports for the corresponding "
                             "period or as soon as possible thereafter."),
    "CRR Art. 434(2), third subparagraph": (CRR, "If disclosure is required to be made for a period when an institution "
                                                 "does not prepare any financial report, the institution shall submit to "
                                                 "EBA the information on disclosures as soon as possible following the end "
                                                 "of that period."),
    # Implementing Regulation (EU) 2024/3172 (stored 2026-10-31 with the product owner's approval): every table and template
    # of the ESG section at each date, populated by the CRR's frequency; its Arts 22 and 26 are untouched by Implementing
    # Regulation (EU) 2026/722 (stored too: it replaces Arts 16(2) and 27(1)-(2) and inserts Arts 24a-24d)
    "ITS 2024/3172 Art. 22(1)": (ITS, "Institutions shall disclose the information referred to in Article 449a of "
                                      "Regulation (EU) No 575/2013 as specified in Section 21 – ‘Disclosure of prudential "
                                      "disclosures on ESG risks’ in Annex I. That information shall cover all of the "
                                      "following: (a) qualitative information on environmental, social and governance "
                                      "risks; (b) quantitative information on climate change transition risk; (c) "
                                      "quantitative information on climate change physical risks;"),
    "ITS 2024/3172 Art. 25(5)(a)": (ITS, "Institutions shall also provide the following information: (a) disclosure "
                                         "reference date and reference period;"),
    "ITS 2024/3172 Art. 26(1)": (ITS, "Disclosure periods shall be defined as quarterly periods T, T-1, T-2, T-3 and T-4."),
    "ITS 2024/3172 Art. 26(2)": (ITS, "The rows or columns in the uniform disclosure formats referred to in the Annex Ind "
                                      "included in the IT solutions developed by the EBA shall be populated in accordance "
                                      "with the frequency of the disclosure laid down in Articles 433a, 433b and 433c of "
                                      "Regulation (EU) No 575/2013."),
    "ITS 2024/3172 Art. 26(3)(b)": (ITS, "(b) institutions disclosing the information contained in the Annex I on a "
                                         "semi-annual basis shall provide data for periods T, T-2 and T-4;"),
    "ITS 2024/3172 Art. 26(4)": (ITS, "Institutions shall disclose the dates corresponding to the disclosure periods."),
    "Implementing Regulation (EU) 2026/722, Art. 24d inserted in ITS 2024/3172": (
        "32026R0722", "For the disclosures with reference dates 30 June 2025, 30 September 2025 and 31 December 2025"),
    "Directive 2004/109/EC Art. 5(1), as replaced by Directive 2013/50/EU": (
        "32013L0050", "The issuer of shares or debt securities shall make public a half-yearly financial report covering "
                      "the first six months of the financial year as soon as possible after the end of the relevant "
                      "period, but at the latest three months thereafter."),
}

_LEGAL = {SEMIANNUAL: "Regulation (EU) No 575/2013 Art. 433a(1), point (b)(xv)",
          "large_non_listed": "Regulation (EU) No 575/2013 Art. 433a(2)",
          NOT_LARGE: "Regulation (EU) No 575/2013 Arts 433b(1)(e), (2) and 433c(1)(a), (2)(ea)"}
WORDS = {SEMIANNUAL: "Twice a year — at the half-year and the year end", ANNUAL: "Once a year — at the year end"}


def frequency(size: str | None, listing: str | None) -> dict:
    """{frequency: 'semiannual' | 'annual' | None, basis, needs: [the statements still to make]} for one institution's
    stated size class and listing at a reference date."""
    if size is None:
        return {"frequency": None, "basis": None, "needs": ["size"] + ([] if listing else ["listing"])}
    if size == GSII:
        return {"frequency": SEMIANNUAL, "basis": _LEGAL[SEMIANNUAL] + " (a G-SII, listed or not)", "needs": []}
    if size == NOT_LARGE:
        return {"frequency": ANNUAL, "basis": _LEGAL[NOT_LARGE], "needs": []}
    if size != LARGE:
        raise ValueError(f"unknown size class {size!r}")
    if listing == LISTED:
        return {"frequency": SEMIANNUAL, "basis": _LEGAL[SEMIANNUAL], "needs": []}
    if listing == NON_LISTED:
        return {"frequency": ANNUAL, "basis": _LEGAL["large_non_listed"], "needs": []}
    return {"frequency": None, "basis": None, "needs": ["listing"]}
