import importlib.util, sys, time, math, random
spec = importlib.util.spec_from_file_location('bc', 'build_calendar.py')
bc = importlib.util.module_from_spec(spec)
sys.argv = ['x']
spec.loader.exec_module(bc)
bad = bc.solve(seed=1)
print('solve bad', len(bad), 'cost', bc.total())
t = time.time()
rnd = random.Random(1)
conf = [bc.conflicts(v.idx, bc.DAY[v.idx]) for v in bc.VARS]
badset = {i for i, c in enumerate(conf) if c}
movable = [v for v in bc.VARS if len(v.domain) > 1]
print('movable', len(movable), 'of', len(bc.VARS), 'init conf sum', sum(conf))
acc = 0
w, t0, t1, steps = 50, 60.0, 0.3, 200000
cur = sum(conf)//2*w + sum(v.domain[v.choice][1] for v in bc.VARS)
mincost = None
for step in range(steps):
    T = t0 * (t1/t0) ** (step/steps)
    v = rnd.choice(movable); k = rnd.randrange(len(v.domain))
    if k == v.choice: continue
    i = v.idx; dn = v.domain[k][0].toordinal()
    delta = (bc.conflicts(i, dn) - conf[i]) * w + v.domain[k][1] - v.domain[v.choice][1]
    if delta <= 0 or rnd.random() < math.exp(-delta/T):
        bc.set_day(i, k, conf, badset); cur += delta; acc += 1
        if not badset and (mincost is None or cur < mincost): mincost = cur
    if step % 50000 == 0: print(step, 'T', round(T,1), 'acc', acc, 'bad', len(badset), 'cur', cur)
print('time', time.time()-t, 'min zero-conflict cost', mincost, 'final', bc.total())
