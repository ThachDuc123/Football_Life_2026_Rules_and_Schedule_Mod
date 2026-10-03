"""Why can a round not take a given day? python why.py <comp> <key...> <yyyy-mm-dd>"""
import importlib.util, json, sys, datetime as dt, collections
spec = importlib.util.spec_from_file_location('bc', 'build_calendar.py')
bc = importlib.util.module_from_spec(spec)
argv = sys.argv[:]
sys.argv = ['x']
spec.loader.exec_module(bc)
cal = json.load(open('calendar.json'))
for v in bc.VARS:          # load the saved solution
    for r in cal['rows'][str(v.comp)]:
        if tuple(r['key']) == tuple(v.key):
            d = dt.date.fromisoformat(r['date'])
            v.domain.append((d, 99)) if d not in [x for x, _ in v.domain] else None
            v.choice = [x for x, _ in v.domain].index(d)
            bc.DAY[v.idx] = d.toordinal()
cat_of = collections.defaultdict(list)
for k, members in bc.CATS.items():
    for v in members:
        cat_of[v.idx].append(k)
comp, day = int(argv[1]), dt.date.fromisoformat(argv[-1])
key = tuple(int(x) if x.isdigit() else x for x in argv[2:-1])
v = [x for x in bc.VARS if x.comp == comp and x.key == key][0]
print(v, '-> try', day)
for j in bc.NEIGH_L[v.idx]:
    if abs(bc.DAY[j] - day.toordinal()) < bc.MIN_GAP:
        w = bc.VARS[j]
        print('  clashes with', w, 'via', sorted(set(cat_of[v.idx]) & set(cat_of[j]))[:4])
