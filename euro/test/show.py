import sys
from pathlib import Path
sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
import euro_rules as er
from export_events import events_from_save
events, clubs = events_from_save(Path(sys.argv[1]))
nm = lambda t: clubs[t].name[:22] if t in clubs else str(t)
rows, _ = er.league_table(events, 3)
order = er.ranked(rows)
for p, r in enumerate(order):
    print(f"{p+1:2} {nm(r['id']):22} P{r['played']} {r['points']:2}đ HS{r['gf']-r['ga']:+3} BT{r['gf']:2} BTsk{r['away_gf']:2} T{r['wins']} Tsk{r['away_wins']} đốiThủ:{r['opp_points']:3}đ/{r['opp_gd']:+3}/{r['opp_gf']:3} kỷLuật{r['discipline']:3}")
year = int(sys.argv[2])
ties = er.build_bracket(er.draw_seed(year, [r['id'] for r in order[:24]]))
pos = lambda p: f"{p+1}.{nm(order[p]['id'])}"
for k, (s, h, a) in enumerate(ties):
    print(('NỬA TRÊN' if k < 4 else 'NỬA DƯỚI') if k % 4 == 0 else '', f"R16-{k+1}: {pos(s)}  vs  thắng[{pos(h)} – {pos(a)}]  -> TK{k//2+1}")
