"""Avalanche SLF validator — the pure parsing / cell-set logic (no network, no DB)."""
import h3

from services.validation.validators import avalanche_slf as A

_RAW = "\n".join([
    "WSL Institute for Snow and Avalanche Research SLF",
    "Avalanche accidents in Switzerland since 1970-1971",
    "Update: 2025-02-10 08:56 (UTC)",
    '"avalanche.id,date,date.quality,hydrological.year,canton,municipality,""start.zone.coordinates.latitude"",'
    '""start.zone.coordinates.longitude"",coordinates.quality,start.zone.elevation,start.zone.slope.aspect,'
    'start.zone.inclination,number.dead,number.caught,number.fully.buried,activity"',
    '"a1,2024-06-27,0,2023/24,VS,""St. Niklaus"",46.12193704,7.84862752,,3736,NE,,0,2,0,"',
    "a2,2024-09-07,0,2023/24,VS,Randa,46.0954963,7.85616041,,4389,NW,,1,2,0,tour",
    "a3,2000-01-01,0,1999/00,GR,Nowhere,,,,1000,N,,0,1,0,tour",          # no coordinates → dropped
    "a4,2001-02-02,0,2000/01,BE,Bern,47.40,7.45,,540,N,,0,1,0,road",      # north of the Alps box
])


def test_unwrap_line_undoes_whole_row_quoting():
    assert A.unwrap_line('"a,""b c"",d"\n') == 'a,"b c",d'
    assert A.unwrap_line("a,b,c\r\n") == "a,b,c"
    assert A.unwrap_line('"plain quoted"') == '"plain quoted"'   # no doubled quotes → untouched


def test_parse_slf_csv_keeps_only_located_rows():
    rows = A.parse_slf_csv(_RAW)
    assert [r["avalanche_id"] for r in rows] == ["a1", "a2", "a4"]
    assert rows[0]["lat"] == 46.12193704 and rows[0]["lon"] == 7.84862752
    assert rows[1]["n_dead"] == 1 and rows[1]["n_caught"] == 2
    assert rows[0]["canton"] == "VS"


def test_parse_slf_csv_without_header_is_empty():
    assert A.parse_slf_csv("no header here\n1,2,3\n") == []


def test_event_counts_restricts_to_alps_box_and_counts_per_cell():
    rows = A.parse_slf_csv(_RAW)
    counts = A.event_counts(rows)
    assert sum(counts.values()) == 2                       # Bern row is outside the box
    assert all(h3.get_resolution(c) == A.H3_RES for c in counts)
    same = [dict(rows[0]), dict(rows[0])]
    assert list(A.event_counts(same).values()) == [2]


def test_sample_background_is_fixed_disjoint_and_in_box():
    ex = {h3.latlng_to_cell(46.1, 7.85, A.H3_RES)}
    a = A.sample_background(ex, 50, seed=7)
    b = A.sample_background(ex, 50, seed=7)
    assert a == b and len(set(a)) == 50 and not set(a) & ex
    for c in a:
        lat, lon = h3.cell_to_latlng(c)
        assert A.in_bbox(lat, lon)
    assert A.sample_background(ex, 50, seed=8) != a


def test_choose_event_cells_caps_deterministically():
    counts = {h3.latlng_to_cell(46.0 + i * 0.01, 8.0, A.H3_RES): 1 for i in range(30)}
    assert A.choose_event_cells(counts, max_n=100) == sorted(counts)
    s1 = A.choose_event_cells(counts, max_n=10, seed=7)
    assert len(s1) == 10 and s1 == A.choose_event_cells(counts, max_n=10, seed=7) and set(s1) <= set(counts)
