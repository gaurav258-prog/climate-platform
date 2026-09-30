#!/usr/bin/env python3
"""Resolve S.27.01.01 natural-catastrophe cells from EIOPA's Solvency II XBRL
taxonomy (table linkbase + XDT definition linkbase), without Arelle.

Usage: python3 scripts/build_eiopa_s2701_map.py <taxonomy_root> <annotated_templates.xlsx> <version> <out.json>

- taxonomy_root: folder holding META-INF/ and eiopa.europa.eu/ (unzipped package)
- Cells are keyed "Rxxxx|Cxxxx" (ITS 2023/894 row/column codes, read from the
  rc-code labels of the table linkbase).
- Aspects for each cell = merge of rule-node aspects along the path root->node
  on x, y and z (child overrides parent), then x+y+z combined.
- Each cell is also checked against the table's XDT hypercubes (def.xml) with
  dimension defaults (dim-def.xml): a cell whose aspect set is not valid in any
  closed hypercube is a greyed/non-existent cell in the taxonomy.
- Each cell is cross-checked against the DPM annotated template sheet.
"""
import glob
import itertools
import json
import os
import re
import sys

import openpyxl
from lxml import etree

NS = {
    'link': 'http://www.xbrl.org/2003/linkbase',
    'xlink': 'http://www.w3.org/1999/xlink',
    'gen': 'http://xbrl.org/2008/generic',
    'table': 'http://xbrl.org/2014/table',
    'formula': 'http://xbrl.org/2008/formula',
    'label': 'http://xbrl.org/2008/label',
    'xbrldt': 'http://xbrl.org/2005/xbrldt',
    'xsd': 'http://www.w3.org/2001/XMLSchema',
    'xbrli': 'http://www.xbrl.org/2003/instance',
    'enum': 'http://xbrl.org/2014/extensible-enumerations',
    'df': 'http://xbrl.org/2008/filter/dimension',
}
XL = '{%s}' % NS['xlink']
ARC_ALL = 'http://xbrl.org/int/dim/arcrole/all'
ARC_NOTALL = 'http://xbrl.org/int/dim/arcrole/notAll'
ARC_HD = 'http://xbrl.org/int/dim/arcrole/hypercube-dimension'
ARC_DD = 'http://xbrl.org/int/dim/arcrole/dimension-domain'
ARC_DM = 'http://xbrl.org/int/dim/arcrole/domain-member'
ARC_DEF = 'http://xbrl.org/int/dim/arcrole/dimension-default'
RC_CODE = 'http://www.eurofiling.info/xbrl/role/rc-code'
FI_CODE = 'http://www.eurofiling.info/xbrl/role/filing-indicator-code'


class Taxonomy:
    def __init__(self, root):
        self.root = root
        self.local_base = os.path.join(root, 'eiopa.europa.eu')
        self.xsd_cache = {}
        self.ns2prefix = {}
        self.defaults = None

    # ---- URL / file resolution (META-INF/catalog.xml: http://eiopa.europa.eu/ -> ../eiopa.europa.eu/)
    def resolve(self, base_file, href):
        path, _, frag = href.partition('#')
        if path.startswith('http://eiopa.europa.eu/'):
            p = os.path.join(self.local_base, path[len('http://eiopa.europa.eu/'):])
        elif path.startswith('http'):
            return None, frag  # external (eurofiling/xbrl.org) not in package
        elif path == '':
            p = base_file
        else:
            p = os.path.normpath(os.path.join(os.path.dirname(base_file), path))
        return p, frag

    def xsd(self, path):
        if path not in self.xsd_cache:
            t = etree.parse(path).getroot()
            tns = t.get('targetNamespace')
            ids = {}
            for el in t.iter('{%s}element' % NS['xsd']):
                if el.get('id'):
                    ids[el.get('id')] = el
            for p, u in t.nsmap.items():
                if p and u not in self.ns2prefix:
                    self.ns2prefix[u] = p
            self.xsd_cache[path] = (tns, ids)
        return self.xsd_cache[path]

    def element(self, base_file, href):
        """-> (namespace, localname, xsd element) or (None, frag, None) if external."""
        p, frag = self.resolve(base_file, href)
        if p is None:
            return None, frag, None
        tns, ids = self.xsd(p)
        el = ids.get(frag)
        if el is None:
            raise KeyError(href)
        return tns, el.get('name'), el

    def q(self, ns, local):
        return '%s:%s' % (self.ns2prefix.get(ns, ns), local)

    def load_defaults(self):
        if self.defaults is not None:
            return self.defaults
        f = os.path.join(self.local_base, 'eu/xbrl/s2c/dict/dim/dim-def.xml')
        t = etree.parse(f).getroot()
        self.defaults = {}
        for dl in t.iter('{%s}definitionLink' % NS['link']):
            locs = {lc.get(XL + 'label'): lc.get(XL + 'href') for lc in dl.iter('{%s}loc' % NS['link'])}
            for a in dl.iter('{%s}definitionArc' % NS['link']):
                if a.get(XL + 'arcrole') == ARC_DEF:
                    dns, dn, _ = self.element(f, locs[a.get(XL + 'from')])
                    mns, mn, _ = self.element(f, locs[a.get(XL + 'to')])
                    self.defaults[(dns, dn)] = (mns, mn)
        return self.defaults


def qname_to_clark(el, qn):
    p, _, local = qn.strip().partition(':')
    return (el.nsmap[p], local)


def parse_rend(tax, rend_path, codes):
    t = etree.parse(rend_path).getroot()
    res, arcs = {}, []
    for gl in t.iter('{%s}link' % NS['gen']):
        for ch in gl:
            if not isinstance(ch.tag, str):
                continue
            typ = ch.get(XL + 'type')
            if typ == 'resource':
                res[ch.get(XL + 'label')] = ch
            elif typ == 'arc':
                arcs.append(ch)
    tables = [e for e in res.values() if e.tag == '{%s}table' % NS['table']]
    assert len(tables) == 1
    table = tables[0]
    children = {}
    breakdowns = {'x': [], 'y': [], 'z': []}
    tree_root = {}
    filters = {}
    table_level = []
    for a in arcs:
        tag = etree.QName(a).localname
        f, to = a.get(XL + 'from'), a.get(XL + 'to')
        order = float(a.get('order', '1'))
        if tag == 'tableBreakdownArc':
            breakdowns[a.get('axis')].append((order, to))
        elif tag == 'breakdownTreeArc':
            tree_root.setdefault(f, []).append((order, to))
        elif tag == 'definitionNodeSubtreeArc':
            children.setdefault(f, []).append((order, to))
        elif tag == 'aspectNodeFilterArc':
            filters.setdefault(f, []).append(to)
        elif tag in ('tableFilterArc', 'tableParameterArc'):
            table_level.append((tag, to))

    def node_aspects(n):
        asp = {'concept': None, 'dims': {}, 'typed': {}, 'open': []}
        for c in n.iter('{%s}concept' % NS['formula']):
            qn = c.find('{%s}qname' % NS['formula']).text
            asp['concept'] = qname_to_clark(c, qn)
        for d in n.iter('{%s}explicitDimension' % NS['formula']):
            dim = qname_to_clark(d, d.get('dimension'))
            m = d.find('{%s}member/{%s}qname' % (NS['formula'], NS['formula']))
            asp['dims'][dim] = qname_to_clark(m, m.text) if m is not None else None
        for d in n.iter('{%s}typedDimension' % NS['formula']):
            dim = qname_to_clark(d, d.get('dimension'))
            v = d.find('{%s}value' % NS['formula'])
            asp['typed'][dim] = etree.tostring(v[0]).decode() if v is not None and len(v) else None
        if etree.QName(n).localname == 'aspectNode':
            da = n.find('{%s}dimensionAspect' % NS['table'])
            if da is not None:
                asp['open'].append({'dimension': qname_to_clark(da, da.text.strip()),
                                    'filters': [etree.tostring(res[x]).decode()[:400] for x in filters.get(n.get(XL + 'label'), [])]})
        # guard: unsupported aspect rules
        for ch in n:
            ln = etree.QName(ch).localname if isinstance(ch.tag, str) else None
            if ln and ln not in ('concept', 'explicitDimension', 'typedDimension', 'dimensionAspect', 'label'):
                asp.setdefault('unsupported', []).append(ln)
        return asp

    def merge(parent, child):
        out = {'concept': child['concept'] or parent['concept'],
               'dims': dict(parent['dims']), 'typed': dict(parent['typed']),
               'open': parent['open'] + child['open']}
        out['dims'].update(child['dims'])
        out['typed'].update(child['typed'])
        if parent.get('unsupported') or child.get('unsupported'):
            out['unsupported'] = parent.get('unsupported', []) + child.get('unsupported', [])
        return out

    def walk(lbl, inherited, out):
        n = res[lbl]
        asp = merge(inherited, node_aspects(n))
        is_abstract = n.get('abstract') == 'true'
        if not is_abstract:
            out.append({'node': lbl, 'code': codes.get(n.get('id') or lbl), 'aspects': asp})
        for _, c in sorted(children.get(lbl, [])):
            walk(c, asp, out)

    empty = {'concept': None, 'dims': {}, 'typed': {}, 'open': []}
    axes = {}
    for ax in ('x', 'y', 'z'):
        per_bd = []
        for _, bd in sorted(breakdowns[ax]):
            out = []
            for _, r in sorted(tree_root.get(bd, [])):
                walk(r, empty, out)
            per_bd.append(out)
        # cross product of breakdowns on the same axis
        combos = []
        for tup in itertools.product(*per_bd) if per_bd else [()]:
            a = empty
            for n in tup:
                a = merge(a, n['aspects'])
            combos.append({'nodes': [n['node'] for n in tup], 'codes': [n['code'] for n in tup], 'aspects': a})
        axes[ax] = combos
    return table, axes, table_level


def parse_codes(lab_codes_path):
    t = etree.parse(lab_codes_path).getroot()
    codes, fi = {}, None
    for lk in t:
        if not isinstance(lk.tag, str):
            continue
        locs = {lc.get(XL + 'label'): lc.get(XL + 'href').split('#')[1] for lc in lk.iter('{%s}loc' % NS['link'])}
        labs = {}
        for lb in lk.iter('{%s}label' % NS['label']):
            labs[lb.get(XL + 'label')] = (lb.get(XL + 'role'), lb.text)
        for a in lk.iter('{%s}arc' % NS['gen']):
            role, text = labs[a.get(XL + 'to')]
            nid = locs[a.get(XL + 'from')]
            if role == RC_CODE:
                codes[nid] = text
            elif role == FI_CODE:
                fi = text
    return codes, fi


def parse_def(tax, def_path):
    """XDT: list of hypercubes {closed, primaries:set, dims:{dim:{'usable':set,'all':set}}}."""
    t = etree.parse(def_path).getroot()
    by_role = {}
    for dl in t.iter('{%s}definitionLink' % NS['link']):
        role = dl.get(XL + 'role')
        locs = {}
        for lc in dl.iter('{%s}loc' % NS['link']):
            ns_, ln, _ = tax.element(def_path, lc.get(XL + 'href'))
            locs[lc.get(XL + 'label')] = (ns_, ln)
        for a in dl.iter('{%s}definitionArc' % NS['link']):
            by_role.setdefault(role, []).append({
                'arcrole': a.get(XL + 'arcrole'), 'from': locs[a.get(XL + 'from')], 'to': locs[a.get(XL + 'to')],
                'targetRole': a.get('{%s}targetRole' % NS['xbrldt']),
                'closed': a.get('{%s}closed' % NS['xbrldt']),
                'ctx': a.get('{%s}contextElement' % NS['xbrldt']),
                'usable': a.get('{%s}usable' % NS['xbrldt'])})

    def arcs_from(role, node, arcrole):
        return [a for a in by_role.get(role, []) if a['from'] == node and a['arcrole'] == arcrole]

    def dm_desc(role, node, acc, usable_acc, seen):
        for a in arcs_from(role, node, ARC_DM):
            r2 = a['targetRole'] or role
            if (r2, a['to']) in seen:
                continue
            seen.add((r2, a['to']))
            acc.add(a['to'])
            if a['usable'] != 'false':
                usable_acc.add(a['to'])
            dm_desc(r2, a['to'], acc, usable_acc, seen)

    hcs = []
    for role, arcs in by_role.items():
        for a in arcs:
            if a['arcrole'] not in (ARC_ALL, ARC_NOTALL):
                continue
            prim = {a['from']}
            dm_desc(role, a['from'], prim, set(), set())
            hrole = a['targetRole'] or role
            dims = {}
            for hd in arcs_from(hrole, a['to'], ARC_HD):
                drole = hd['targetRole'] or hrole
                allm, usable = set(), set()
                for dd in arcs_from(drole, hd['to'], ARC_DD):
                    mrole = dd['targetRole'] or drole
                    if dd['usable'] != 'false':
                        usable.add(dd['to'])
                    allm.add(dd['to'])
                    dm_desc(mrole, dd['to'], allm, usable, set())
                dims[hd['to']] = {'usable': usable, 'all': allm, 'domains': [dd['to'] for dd in arcs_from(drole, hd['to'], ARC_DD)]}
            hcs.append({'role': role, 'kind': 'all' if a['arcrole'] == ARC_ALL else 'notAll',
                        'closed': a['closed'] == 'true', 'ctx': a['ctx'], 'primaries': prim, 'dims': dims})
    return hcs


def xdt_valid(tax, hcs, concept, dims, typed, open_dims):
    """True if the cell's dimension set is valid in some closed 'all' hypercube of its concept."""
    defaults = tax.load_defaults()
    reasons = []
    for hc in hcs:
        if hc['kind'] != 'all' or concept not in hc['primaries']:
            continue
        ok, why = True, []
        for d, m in dims.items():
            if d not in hc['dims']:
                ok = False; why.append('dim %s not in hypercube' % tax.q(*d)); continue
            if defaults.get(d) == m:
                ok = False; why.append('member %s is the default of %s (must be omitted)' % (tax.q(*m), tax.q(*d)))
            elif m not in hc['dims'][d]['usable']:
                ok = False; why.append('member %s not usable for %s' % (tax.q(*m), tax.q(*d)))
        for d in list(typed) + list(open_dims):
            if d not in hc['dims']:
                ok = False; why.append('typed/open dim %s not in hypercube' % tax.q(*d))
        for d in hc['dims']:
            if d not in dims and d not in typed and d not in open_dims and d not in defaults:
                ok = False; why.append('hypercube dim %s has no default and is not given' % tax.q(*d))
        if hc['closed'] is False:
            why.append('(open hypercube)')
        if ok:
            return True, hc['role']
        reasons.append((hc['role'], why))
    return False, reasons


# ---------------- annotated templates -----------------
QN_RE = re.compile(r'^\s*([A-Za-z0-9_]+:[A-Za-z0-9_]+)')


def parse_annotated(ws):
    grid = {}
    for row in ws.iter_rows():
        for c in row:
            v = getattr(c, 'value', None)
            if v is not None and str(v).strip() != '':
                grid[(c.row, c.column)] = str(v).strip()
    ccols = {k: v for k, v in grid.items() if re.fullmatch(r'C\d{4}', v)}
    rrows = {k: v for k, v in grid.items() if re.fullmatch(r'R\d{4}', v)}
    if not ccols or not rrows:
        return None
    code_row = max(set(r for r, _ in ccols), key=lambda r: sum(1 for (rr, _) in ccols if rr == r))
    colcode = {c: v for (r, c), v in ccols.items() if r == code_row}
    rowcode = {r: v for (r, c), v in rrows.items()}
    rcode_col = min(c for (r, c) in rrows)
    last_c = max(colcode)
    last_r = max(rowcode)
    # row-annotation headers (right of the last code column, on/above code row)
    rowhdr = {}
    for (r, c), v in grid.items():
        if c > last_c and r in (code_row - 1, code_row) and (v == 'Metrics' or v.startswith('s2c_dim:')):
            rowhdr[c] = 'metric' if v == 'Metrics' else QN_RE.match(v).group(1)
    # column-annotation block (below the last row code, label in columns <= rcode_col)
    colhdr = {}
    for (r, c), v in grid.items():
        if r > last_r and c <= rcode_col and (v == 'Metrics' or v.startswith('s2c_dim:')):
            colhdr[r] = 'metric' if v == 'Metrics' else QN_RE.match(v).group(1)
    z = [v for (r, c), v in grid.items() if r < code_row - 1 and ('s2c_' in v)]
    rowann = {rc: {} for rc in rowcode.values()}
    for r, rc in rowcode.items():
        for c, h in rowhdr.items():
            if (r, c) in grid:
                rowann[rc][h] = grid[(r, c)]
    colann = {cc: {} for cc in colcode.values()}
    for c, cc in colcode.items():
        for r, h in colhdr.items():
            if (r, c) in grid:
                colann[cc][h] = grid[(r, c)]
    # shading: EIOPA greys non-reportable cells with a solid fill in the annotated templates
    shaded = {}
    for r, rc in rowcode.items():
        for c, cc in colcode.items():
            try:
                cell = ws.cell(r, c)
                shaded[rc + '|' + cc] = bool(cell.fill is not None and cell.fill.fill_type == 'solid')
            except Exception:
                pass
    return {'rows': rowann, 'cols': colann, 'z': z, 'shaded': shaded}


def ann_cell(ann, rc, cc):
    m = None
    dims = {}
    raw = {}
    for src in (ann['rows'].get(rc, {}), ann['cols'].get(cc, {})):
        for h, v in src.items():
            qn = QN_RE.match(v).group(1)
            raw[h] = v
            if h == 'metric':
                if m and m != qn:
                    dims['__metric_conflict__'] = qn
                m = qn
            else:
                dims[h] = qn
    return m, dims, raw


# ---------------- main -----------------

def main(tax_root, xlsx, version, out_path, reportable_json):
    tax = Taxonomy(tax_root)
    tabdirs = sorted(glob.glob(os.path.join(tax.local_base, 'eu/xbrl/s2md/fws/solvency/solvency2/*/tab/s.27.01.01.*')))
    fws_dir = os.path.dirname(os.path.dirname(tabdirs[0]))
    met_xsd = os.path.join(tax.local_base, 'eu/xbrl/s2md/dict/met/met.xsd')
    met_ns, met_ids = tax.xsd(met_xsd)
    # prime prefixes from dim.xsd and domains
    tax.xsd(os.path.join(tax.local_base, 'eu/xbrl/s2c/dict/dim/dim.xsd'))
    wb = openpyxl.load_workbook(xlsx)  # full mode: fills needed for greyed-cell check
    reportable = json.load(open(reportable_json))['reportable_cells']
    our = {(r, c) for r, cs in reportable.items() for c in cs}

    cells, tables, fi_codes, open_z, disagreements, collisions, unsupported = {}, {}, set(), {}, [], [], []
    all_cells_by_table = {}
    for td in tabdirs:
        tid = os.path.basename(td)
        codes, fi = parse_codes(os.path.join(td, tid + '-lab-codes.xml'))
        fi_codes.add(fi)
        rend = os.path.join(td, tid + '-rend.xml')
        tree = etree.parse(rend).getroot()
        for p, u in tree.nsmap.items():
            if p:
                tax.ns2prefix.setdefault(u, p)
        table, axes, table_level = parse_rend(tax, rend, codes)
        hcs = parse_def(tax, os.path.join(td, tid + '-def.xml'))
        xsd_t = etree.parse(os.path.join(td, tid + '.xsd')).getroot()
        ann = None
        sheet = tid.upper()
        if sheet in wb.sheetnames:
            ann = parse_annotated(wb[sheet])
        zinfo = []
        for z in axes['z']:
            zinfo.append({'codes': z['codes'],
                          'dims': {tax.q(*d): tax.q(*m) for d, m in z['aspects']['dims'].items()},
                          'open': [tax.q(*o['dimension']) for o in z['aspects']['open']]})
        open_z[tid.upper()] = sorted({o for z in zinfo for o in z['open']})
        tables[tid.upper()] = {'role': 'http://eiopa.europa.eu/xbrl/s2md/role/fws/solvency/solvency2/%s/tab/%s' % (
            os.path.basename(fws_dir), tid.upper()),
            'namespace': xsd_t.get('targetNamespace'), 'filing_indicator_code': fi,
            'z': zinfo, 'table_level_aspects': table_level}
        tcells = {}
        for x in axes['x']:
            for y in axes['y']:
                for z in axes['z']:
                    codes_all = [c for c in x['codes'] + y['codes'] + z['codes'] if c]
                    r = [c for c in codes_all if c.startswith('R')]
                    col = [c for c in codes_all if c.startswith('C')]
                    if len(r) != 1 or len(col) != 1:
                        continue
                    key = '%s|%s' % (r[0], col[0])
                    concept = None
                    dims, typed, opn = {}, {}, []
                    conflict = []
                    for part in (x, y, z):
                        a = part['aspects']
                        if a.get('unsupported'):
                            unsupported.append((tid, key, a['unsupported']))
                        if a['concept']:
                            if concept and concept != a['concept']:
                                conflict.append(('concept', concept, a['concept']))
                            concept = a['concept']
                        for d, m in a['dims'].items():
                            if d in dims and dims[d] != m:
                                conflict.append(('dim', d, dims[d], m))
                            dims[d] = m
                        typed.update(a['typed'])
                        opn += [o['dimension'] for o in a['open']]
                    valid, why = xdt_valid(tax, hcs, concept, dims, typed, opn)
                    tcells[key] = (concept, dims, typed, opn, valid, why, conflict)
        all_cells_by_table[tid.upper()] = tcells
        for key, (concept, dims, typed, opn, valid, why, conflict) in tcells.items():
            rc, cc = key.split('|')
            mel = met_ids.get('s2md_' + concept[1]) if concept and concept[0] == met_ns else None
            entry = {
                'table': tid.upper(),
                'concept': tax.q(*concept) if concept else None,
                'concept_ns': concept[0] if concept else None,
                'datatype': mel.get('type') if mel is not None else None,
                'period_type': mel.get('{%s}periodType' % NS['xbrli']) if mel is not None else None,
                'dims': {tax.q(*d): tax.q(*m) for d, m in sorted(dims.items())},
                'typed': {},
                'open_dims': [tax.q(*o) for o in opn],
                'xdt_valid': valid,
                'in_our_710': (rc, cc) in our,
            }
            if mel is not None and mel.get('{%s}domain' % NS['enum']):
                entry['enum_domain'] = mel.get('{%s}domain' % NS['enum'])
                entry['enum_linkrole'] = mel.get('{%s}linkrole' % NS['enum'])
            for d, v in typed.items():
                dns_, dn = d
                _, dids = tax.xsd(os.path.join(tax.local_base, 'eu/xbrl/s2c/dict/dim/dim.xsd'))
                entry['typed'][tax.q(*d)] = {'value': v, 'typedDomainRef': dids['s2c_' + dn].get('{%s}typedDomainRef' % NS['xbrldt'])}
            for o in opn:
                _, dids = tax.xsd(os.path.join(tax.local_base, 'eu/xbrl/s2c/dict/dim/dim.xsd'))
                tdr = dids['s2c_' + o[1]].get('{%s}typedDomainRef' % NS['xbrldt'])
                if tdr:
                    entry['typed'][tax.q(*o)] = {'value': None, 'typedDomainRef': tdr, 'open': True}
            if not valid:
                entry['xdt_invalid_reasons'] = [[r, w] for r, w in why] if isinstance(why, list) else why
            if conflict:
                entry['aspect_conflicts'] = [[str(x) for x in c] for c in conflict]
            # annotated-template cross-check
            if ann is not None:
                am, adims, raw = ann_cell(ann, rc, cc)
                mine_dims = {k: v for k, v in entry['dims'].items()}
                # z-axis dims are not printed in the annotated sheets; compare x/y only
                zdims = set()
                for z in axes['z']:
                    zdims |= {tax.q(*d) for d in z['aspects']['dims']}
                cmp_dims = {k: v for k, v in mine_dims.items() if k not in zdims}
                diffs = []
                if am != entry['concept']:
                    diffs.append({'what': 'metric', 'taxonomy': entry['concept'], 'annotated': am})
                for k in sorted(set(cmp_dims) | set(adims)):
                    if cmp_dims.get(k) != adims.get(k):
                        diffs.append({'what': k, 'taxonomy': cmp_dims.get(k), 'annotated': adims.get(k)})
                entry['annotated_check'] = 'match' if not diffs else 'DIFF'
                entry['annotated_greyed'] = ann['shaded'].get(key)
                if diffs:
                    disagreements.append({'cell': key, 'table': tid.upper(), 'diffs': diffs,
                                          'in_our_710': (rc, cc) in our, 'xdt_valid': valid})
            else:
                entry['annotated_check'] = 'sheet missing'
            if key in cells:
                collisions.append((key, cells[key]['table'], tid.upper()))
            cells[key] = entry

    # restrict map to our cells, keep others for reference counts
    ours_found = {k: v for k, v in cells.items() if tuple(k.split('|')) in our}
    missing = sorted('%s|%s' % rc for rc in our if '%s|%s' % rc not in cells)
    used_ns = set()
    for v in ours_found.values():
        for s in [v['concept']] + list(v['dims'].keys()) + list(v['dims'].values()):
            if s:
                used_ns.add(s.split(':')[0])
    prefix2ns = {p: u for u, p in tax.ns2prefix.items()}
    namespaces = {p: prefix2ns[p] for p in sorted(used_ns)}
    namespaces.update({
        'xbrli': 'http://www.xbrl.org/2003/instance', 'xbrldi': 'http://xbrl.org/2006/xbrldi',
        'link': 'http://www.xbrl.org/2003/linkbase', 'xlink': 'http://www.w3.org/1999/xlink',
        'iso4217': 'http://www.xbrl.org/2003/iso4217',
        'find': 'http://www.eurofiling.info/xbrl/ext/filing-indicators'})

    fws_date = os.path.basename(fws_dir)
    ep_file = os.path.join(fws_dir, 'mod', 'ars.xsd')
    ep_txt = open(ep_file, encoding='utf-8-sig').read()
    ep_tables = sorted(set(re.findall(r'tab/(s\.27\.01\.01\.\d\d)/', ep_txt)))
    fchk = open(os.path.join(fws_dir, 'mod', 'ars-find-check.xml'), encoding='utf-8-sig').read()
    m = re.search(r"test=\"\$filingIndicator = \(([^)]*)\)", fchk)
    allowed = re.findall(r"'([^']+)'", m.group(1)) if m else []
    mandatory = re.findall(r"test=\"\. = '([^']+)'\"", fchk)
    ep_label = re.search(r'role/label" xml:lang="en">([^<]+)<', open(os.path.join(fws_dir, 'mod', 'ars-lab-en.xml'), encoding='utf-8-sig').read())

    grey_cmp = {}
    for tid, tc in all_cells_by_table.items():
        if tid not in {v['table'] for v in ours_found.values()}:
            continue
        sh = tid in wb.sheetnames and parse_annotated(wb[tid])
        if not sh:
            continue
        g = {'annotated_white': 0, 'white_and_ours': 0, 'white_not_ours': [], 'ours_but_greyed': [],
             'xdt_valid_but_greyed': []}
        for k, t in tc.items():
            white = sh['shaded'].get(k) is False
            is_ours = tuple(k.split('|')) in our
            g['annotated_white'] += white
            g['white_and_ours'] += white and is_ours
            if white and not is_ours:
                g['white_not_ours'].append(k)
            if is_ours and not white:
                g['ours_but_greyed'].append(k)
            if t[4] and not white:
                g['xdt_valid_but_greyed'].append(k)
        grey_cmp[tid] = g
    greyed_in_taxonomy_but_ours = sorted(k for k, v in ours_found.items() if not v['xdt_valid'])
    valid_not_ours = sorted(k for tid, tc in all_cells_by_table.items() if tid in {v['table'] for v in ours_found.values()}
                            for k, t in tc.items() if t[4] and tuple(k.split('|')) not in our)
    out = {
        'taxonomy_version': version,
        'framework_date': fws_date,
        'entry_point': {
            'schemaRef': 'http://eiopa.europa.eu/eu/xbrl/s2md/fws/solvency/solvency2/%s/mod/ars.xsd' % fws_date,
            'label': ep_label.group(1) if ep_label else None,
            'includes_tables': [t.upper() for t in ep_tables],
            'allowed_filing_indicators_include_S.27.01': 'S.27.01' in allowed,
            'mandatory_filing_indicators': mandatory,
        },
        'filing_indicator': {
            'code': sorted(fi_codes),
            'elements': {'container': 'find:fIndicators', 'indicator': 'find:filingIndicator',
                         'filed_attribute': 'find:filed (boolean, default true)',
                         'namespace': 'http://www.eurofiling.info/xbrl/ext/filing-indicators'},
            'note': 'filing-indicator-code label on every S.27.01.01.xx table is the template-level code; one indicator covers all 28 tables.',
        },
        'namespaces': namespaces,
        'tables': {k: v for k, v in tables.items()},
        'open_z_dims': {k: v for k, v in open_z.items()},
        'counts': {
            'our_reportable_cells': len(our),
            'resolved': len(ours_found),
            'missing_from_taxonomy': missing,
            'ours_xdt_invalid(greyed in taxonomy)': greyed_in_taxonomy_but_ours,
            'taxonomy_valid_cells_not_in_our_710(same tables)': valid_not_ours,
            'all_rendered_cells_in_s2701': len(cells),
            'annotated_disagreements_on_our_cells': sum(1 for d in disagreements if d['in_our_710']),
            'annotated_disagreements_total': len(disagreements),
            'code_collisions_across_tables': collisions,
            'unsupported_aspect_rules': unsupported,
        },
        'annotated_disagreements': disagreements,
        'greyed_cell_check_vs_annotated_shading': grey_cmp,
        'cells': dict(sorted(ours_found.items(), key=lambda kv: (kv[0].split('|')[0], kv[0].split('|')[1]))),
        'other_s2701_cells': {k: {kk: vv for kk, vv in v.items() if kk in ('table', 'concept', 'dims', 'xdt_valid')}
                              for k, v in sorted(cells.items()) if tuple(k.split('|')) not in our},
    }
    # S.01.01 content-of-submission row for S.27.01.01
    s0101 = os.path.join(fws_dir, 'tab', 's.01.01.01.01')
    if os.path.isdir(s0101):
        codes, _ = parse_codes(os.path.join(s0101, 's.01.01.01.01-lab-codes.xml'))
        _, axes, _ = parse_rend(tax, os.path.join(s0101, 's.01.01.01.01-rend.xml'), codes)
        lab = open(os.path.join(s0101, 's.01.01.01.01-lab-en.xml'), encoding='utf-8').read()
        for y in axes['y']:
            nid = y['nodes'][0]
            if re.search(r'#%s"[^>]*/>\s*<label:label[^>]*>S\.27\.01\.01 ' % re.escape(nid), lab):
                for x in axes['x']:
                    c = y['aspects']['concept'] or x['aspects']['concept']
                    mel = met_ids.get('s2md_' + c[1])
                    out['s01_01_content_row'] = {'table': 'S.01.01.01.01', 'cell': '%s|%s' % (y['codes'][0], x['codes'][0]),
                                                 'concept': tax.q(*c), 'datatype': mel.get('type'),
                                                 'enum_domain': mel.get('{%s}domain' % NS['enum']),
                                                 'enum_linkrole': mel.get('{%s}linkrole' % NS['enum']),
                                                 'dims': {tax.q(*d): tax.q(*m) for d, m in {**x['aspects']['dims'], **y['aspects']['dims']}.items()}}
    json.dump(out, open(out_path, 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(out['counts'], indent=1)[:3000])
    print('filing indicator', out['filing_indicator']['code'], 'entry', out['entry_point'])


if __name__ == '__main__':
    main(*sys.argv[1:6])
