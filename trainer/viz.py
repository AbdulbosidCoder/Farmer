"""Self-contained HTML reports (no extra dependencies, no internet needed).

    game_report(env, names)      one game: money per turn, market prices, farm map per day, actions
    progress_report(avlod_dir)   training: fitness / win rates / money per generation

Used by scripts/visualize.py and by trainer/evolve.py (writes <out>/progress.html
after every generation).
"""
import collections
import csv
import glob
import html
import json
import os

PRICE_ITEMS = ["EGG", "MILK", "WOOL", "MELON", "STRAWBERRY", "TOMATO", "WHEAT", "CARROT"]

# ----------------------------------------------------------------- page shell
_CSS = """
:root{color-scheme:light;--bg:#f6f6f4;--surface:#fcfcfb;--border:#e4e3df;--grid:#ecebe7;
--text:#0b0b0b;--text2:#52514e;--muted:#8a8984;--s1:#2a78d6;--s2:#eb6834;
--crop:#cfe9da;--crop-ink:#0f5a3c;--animal:#fbd9c9;--animal-ink:#8a3413;--struct:#e8e6f5;
--struct-ink:#3d3290;--weed:#f6d2d2;--weed-ink:#8f1f1f;--locked:#e7e6e2;--shed:#fff1c7}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#121211;
--surface:#1a1a19;--border:#2e2e2b;--grid:#262624;--text:#fff;--text2:#c3c2b7;--muted:#8d8c85;
--s1:#3987e5;--s2:#d95926;--crop:#153d2c;--crop-ink:#8fe0b9;--animal:#4a2414;--animal-ink:#ffb996;
--struct:#27234a;--struct-ink:#b9b1ff;--weed:#4a1b1b;--weed-ink:#ff9f9f;--locked:#232321;--shed:#3d3413}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--border:#2e2e2b;
--grid:#262624;--text:#fff;--text2:#c3c2b7;--muted:#8d8c85;--s1:#3987e5;--s2:#d95926;--crop:#153d2c;
--crop-ink:#8fe0b9;--animal:#4a2414;--animal-ink:#ffb996;--struct:#27234a;--struct-ink:#b9b1ff;
--weed:#4a1b1b;--weed-ink:#ff9f9f;--locked:#232321;--shed:#3d3413}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 10px}
.sub{color:var(--text2);margin:0 0 20px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;margin:0 0 16px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 16px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.tile .k{color:var(--text2);font-size:12px}.tile .v{font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--text2);font-size:12px;margin:0 0 6px}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{fill:var(--muted);font-size:11px;font-family:inherit}
.tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--border);
border-radius:8px;padding:6px 9px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.15);display:none;z-index:9;
font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
th,td{padding:4px 8px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--text2);font-weight:600}
.scroll{overflow-x:auto}
.farm{display:grid;grid-template-columns:repeat(10,1fr);gap:2px;max-width:360px}
.cell{aspect-ratio:1;border-radius:4px;display:flex;align-items:center;justify-content:center;
font-size:11px;font-weight:600;position:relative;border:1px solid var(--border);background:var(--surface)}
.cell.locked{background:var(--locked);border-color:transparent}
.cell.crop{background:var(--crop);color:var(--crop-ink);border-color:transparent}
.cell.animal{background:var(--animal);color:var(--animal-ink);border-color:transparent}
.cell.struct{background:var(--struct);color:var(--struct-ink);border-color:transparent}
.cell.weed{background:var(--weed);color:var(--weed-ink);border-color:transparent}
.cell.shed{outline:2px dashed var(--muted);outline-offset:-3px}
.cell .u{position:absolute;right:1px;bottom:0;font-size:9px;color:var(--text)}
.ctrl{display:flex;align-items:center;gap:12px;margin:0 0 12px;flex-wrap:wrap}
input[type=range]{flex:1;min-width:200px}
.muted{color:var(--muted)}.small{font-size:12px}
.bar{height:8px;border-radius:0 4px 4px 0;display:inline-block;vertical-align:middle}
"""

_JS = r"""
const tip=document.querySelector('.tip');
function fmt(v,f){if(v==null||isNaN(v))return'–';if(f==='pct')return(100*v).toFixed(0)+'%';
 if(f==='money')return'$'+Math.round(v).toLocaleString();if(f==='int')return Math.round(v).toLocaleString();
 return(+v).toFixed(3)}
function css(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()}
const CHARTS=[];let rt;addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(()=>CHARTS.forEach(([e,o])=>draw(e,o)),150)});
function lineChart(el,o){CHARTS.push([el,o]);draw(el,o)}
function draw(el,o){
 const W=Math.max(240,el.clientWidth||560),H=o.h||220,m={l:54,r:o.endLabels?74:12,t:10,b:28};
 const xs=o.x, n=xs.length; let lo=o.ymin, hi=o.ymax;
 const all=o.series.flatMap(s=>s.values.filter(v=>v!=null));
 if(lo==null)lo=Math.min(0,...all); if(hi==null)hi=Math.max(...all,lo+1);
 const X=i=>m.l+(n<2?0:i/(n-1))*(W-m.l-m.r), Y=v=>H-m.b-(v-lo)/(hi-lo||1)*(H-m.t-m.b);
 let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${o.title||''}">`;
 for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4,y=Y(v);
  s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/>`+
     `<text x="${m.l-6}" y="${y+4}" text-anchor="end">${fmt(v,o.yfmt)}</text>`}
 const nt=Math.max(2,Math.min(n,Math.floor(W/70)));
 const st=Math.max(1,Math.ceil((n-1)/(nt-1)));let ticks=o.xticks;
 if(!ticks){ticks=[];for(let i=0;i<n;i+=st)ticks.push(i);if(n-1-ticks[ticks.length-1]>=st/2)ticks.push(n-1)}
 for(const i of ticks){s+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle">${o.xfmt?o.xfmt(xs[i]):xs[i]}</text>`}
 o.series.forEach(se=>{let d='',pen=false;se.values.forEach((v,i)=>{if(v==null){pen=false;return}
  d+=(pen?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1);pen=true});
  s+=`<path d="${d}" fill="none" stroke="${se.color}" stroke-width="2" stroke-linejoin="round"/>`;
  (se.markers||[]).forEach(i=>{if(se.values[i]!=null)s+=`<circle cx="${X(i)}" cy="${Y(se.values[i])}" r="4" fill="${se.color}" stroke="var(--surface)" stroke-width="2"/>`});
  if(o.endLabels){let i=se.values.length-1;while(i>0&&se.values[i]==null)i--;
   s+=`<text x="${X(i)+6}" y="${Y(se.values[i])+4}" style="fill:var(--text2)">${se.name}</text>`}});
 s+=`<line class="xh" x1="0" x2="0" y1="${m.t}" y2="${H-m.b}" stroke="var(--muted)" stroke-dasharray="3 3" visibility="hidden"/>`;
 s+=`<rect x="${m.l}" y="0" width="${W-m.l-m.r}" height="${H}" fill="transparent"/></svg>`;
 el.innerHTML=(o.series.length>1?'<div class="legend">'+o.series.map(se=>`<span><span class="sw" style="background:${se.color}"></span>${se.name}</span>`).join('')+'</div>':'')+s;
 const svg=el.querySelector('svg'),xh=svg.querySelector('.xh');
 svg.addEventListener('mousemove',e=>{const r=svg.getBoundingClientRect(),px=(e.clientX-r.left)*W/r.width;
  const i=Math.max(0,Math.min(n-1,Math.round((px-m.l)/(W-m.l-m.r)*(n-1))));
  xh.setAttribute('x1',X(i));xh.setAttribute('x2',X(i));xh.setAttribute('visibility','visible');
  tip.innerHTML=`<b>${o.xname||''} ${o.xfmt?o.xfmt(xs[i]):xs[i]}</b><br>`+o.series.map(se=>
   `<span class="sw" style="background:${se.color}"></span>${se.name}: <b>${fmt(se.values[i],o.yfmt)}</b>`).join('<br>');
  tip.style.display='block';tip.style.left=Math.min(e.clientX+14,innerWidth-200)+'px';tip.style.top=(e.clientY+14)+'px'});
 svg.addEventListener('mouseleave',()=>{tip.style.display='none';xh.setAttribute('visibility','hidden')});
}
"""


def _page(title, subtitle, body, data, script):
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>"
        f"<h1>{html.escape(title)}</h1><p class='sub'>{subtitle}</p>{body}</main>"
        "<div class='tip'></div>"
        f"<script>const DATA={json.dumps(data, separators=(',', ':'))};{_JS}{script}</script>"
        "</body></html>"
    )


# ----------------------------------------------------------------- game report
def _cell(t):
    """Compact tile code for the farm map."""
    if t is None:
        return ""
    if t == "LOCKED":
        return "#"
    if isinstance(t, dict):
        if "animal" in t:
            return "a:" + str(t["animal"])
        kind = t.get("kind")
        if kind == "PLANT":
            return "p:" + str(t.get("crop", "?"))
        return "k:" + str(kind)
    return "?"


def game_report(env, names, seed=None):
    """HTML report for a finished kaggle_environments kaggriculture episode."""
    steps = env.steps
    n = len(steps)
    # farms live in observation[0]; every player sees the same public farms
    money = [[s[0].observation["farms"][p]["money"] if s[0].observation.get("farms") else None
              for s in steps] for p in (0, 1)]
    prices = {it: [] for it in PRICE_ITEMS}
    for s in steps:
        mk = (s[0].observation.get("market") or {}).get("prices", {})
        for it in PRICE_ITEMS:
            prices[it].append(mk.get(it))

    ops = [collections.Counter(), collections.Counter()]
    market_ops = [collections.Counter(), collections.Counter()]
    for s in steps[1:]:
        for p in (0, 1):
            a = s[p].action
            if not isinstance(a, dict):
                continue
            for u in [a.get("farmer")] + list(a.get("hands") or []):
                if isinstance(u, list) and u:
                    ops[p][str(u[0])] += 1
            for o in a.get("market") or []:
                if isinstance(o, list) and o:
                    market_ops[p][" ".join(str(x) for x in o[:2])] += 1

    # one snapshot per day: the last turn of the day (hour 23) plus the final state
    days = []
    for k, s in enumerate(steps):
        o0 = s[0].observation
        if not o0.get("farms"):
            continue
        if o0.get("hour") == 23 or k == n - 1:
            snap = {"day": o0.get("day"), "hour": o0.get("hour"), "step": k, "farms": []}
            for p in (0, 1):
                f = o0["farms"][p]
                priv = s[p].observation.get("private") or {}
                shed = {kk: v for kk, v in (priv.get("shed") or {}).items() if v}
                animals = sum(1 for row in f["tiles"] for t in row if isinstance(t, dict) and "animal" in t)
                snap["farms"].append({
                    "money": f["money"],
                    "tiles": [[_cell(t) for t in row] for row in f["tiles"]],
                    "units": [list(f["farmer"])] + [list(h) for h in f.get("hands") or []],
                    "shed": shed,
                    "seeds": {kk: v for kk, v in (priv.get("seeds") or {}).items() if v},
                    "animals": animals,
                    "quadrants": list(f.get("unlocked_quadrants") or []),
                })
            snap["shops"] = list((o0.get("town") or {}).get("unlocked_shops") or [])
            days.append(snap)

    last = steps[-1]
    final = [last[p].reward for p in (0, 1)]
    status = [last[p].status for p in (0, 1)]
    winner = 0 if (final[0] or 0) > (final[1] or 0) else 1 if (final[1] or 0) > (final[0] or 0) else None

    data = {
        "names": names, "money": money, "prices": prices, "days": days,
        "ops": [dict(c.most_common()) for c in ops],
        "market": [dict(c.most_common(14)) for c in market_ops],
        "n": n,
    }
    tiles = "".join(
        f"<div class='tile'><div class='k'><span class='sw' style='background:var(--s{p + 1})'></span>"
        f"{html.escape(names[p])}{' — winner' if winner == p else ''}</div>"
        f"<div class='v'>${(final[p] or 0):,.0f}</div><div class='k'>status {html.escape(str(status[p]))}</div></div>"
        for p in (0, 1)
    )
    body = f"""
<div class='tiles'>{tiles}
<div class='tile'><div class='k'>Difference</div><div class='v'>${abs((final[0] or 0) - (final[1] or 0)):,.0f}</div>
<div class='k'>{n} turns{'' if seed is None else f', seed {seed}'}</div></div></div>
<div class='card'><h2>Money per turn</h2><div id='money'></div></div>
<div class='card'><h2>Farm by day</h2>
<div class='ctrl'><button id='play'>▶</button><input type='range' id='day' min='0' value='0'>
<b id='dayl'></b></div><div class='grid2' id='farms'></div>
<p class='small muted'>Letters: W wheat, C carrot, T tomato, S strawberry, M melon; g goose, c cow, s sheep;
□ empty coop/pasture, x weed. Dashed cells are the shed. ★ farmer, • hand (position at the end of the day).</p></div>
<div class='card'><h2>Market prices (shared by both players)</h2><div class='grid4' id='prices'></div></div>
<div class='card'><h2>What the units did</h2><div class='grid2' id='ops'></div></div>
"""
    script = r"""
const C1=css('--s1'),C2=css('--s2'),N=DATA.names,D=DATA.days;
const turn=i=>`day ${Math.floor(i/24)} h${i%24}`;
const dticks=[...Array(7).keys()].map(k=>Math.min(DATA.n-1,k*120));
lineChart(document.getElementById('money'),{x:[...Array(DATA.n).keys()],xfmt:i=>i%24?turn(i):'d'+i/24,
 xticks:dticks,xname:'',yfmt:'money',h:260,endLabels:true,series:[{name:N[0],color:C1,values:DATA.money[0]},
 {name:N[1],color:C2,values:DATA.money[1]}]});
const pr=document.getElementById('prices');
const PW=Object.keys(DATA.prices).map(it=>{const w=document.createElement('div');pr.appendChild(w);
 w.innerHTML=`<div class="small" style="color:var(--text2);margin-bottom:4px"><b>${it}</b></div><div></div>`;return[it,w]});
for(const[it,w]of PW){lineChart(w.lastChild,{title:it,x:[...Array(DATA.n).keys()],xfmt:i=>'d'+Math.floor(i/24),xticks:[0,240,480,DATA.n-1],
  yfmt:'money',h:150,series:[{name:it,color:C1,values:DATA.prices[it]}]})}
const CROP={WHEAT:'W',CARROT:'C',TOMATO:'T',STRAWBERRY:'S',MELON:'M'},AN={GOOSE:'g',COW:'c',SHEEP:'s'};
const SHED=new Set(['4,4','5,4','4,5','5,5']);
function cellHTML(code,x,y,units){let cls='cell',t='';
 if(code==='#')cls+=' locked';else if(code.startsWith('p:')){cls+=' crop';t=CROP[code.slice(2)]||'?'}
 else if(code.startsWith('a:')){cls+=' animal';t=AN[code.slice(2)]||'?'}
 else if(code==='k:WEED'){cls+=' weed';t='x'}else if(code.startsWith('k:')){cls+=' struct';t='□'}
 if(SHED.has(x+','+y))cls+=' shed';
 const u=units.findIndex(p=>p[0]===x&&p[1]===y);const cnt=units.filter(p=>p[0]===x&&p[1]===y).length;
 const um=cnt?`<span class="u">${u===0?'★':'•'}${cnt>1?cnt:''}</span>`:'';
 return `<div class="${cls}" title="(${x},${y}) ${code||'empty'}">${t}${um}</div>`}
function kv(o){const e=Object.entries(o);return e.length?e.map(([k,v])=>`${k} ${v}`).join(', '):'<span class="muted">empty</span>'}
function show(i){const s=D[i];document.getElementById('dayl').textContent=`day ${s.day}${s.hour===23?'':' h'+s.hour}`+
 (s.shops.length?` · shops: ${s.shops.join(', ')}`:'');
 document.getElementById('farms').innerHTML=s.farms.map((f,p)=>{
  let g='';f.tiles.forEach((row,y)=>row.forEach((c,x)=>g+=cellHTML(c,x,y,f.units)));
  return `<div><div class="legend"><span><span class="sw" style="background:${p?C2:C1}"></span><b style="color:var(--text)">${N[p]}</b></span>
   <span>$${Math.round(f.money).toLocaleString()}</span><span>${f.animals} animals</span><span>${f.units.length-1} hands</span></div>
   <div class="farm">${g}</div><p class="small" style="color:var(--text2)"><b>Shed</b> (${Object.values(f.shed).reduce((a,b)=>a+b,0)}/100): ${kv(f.shed)}<br>
   <b>Seeds</b>: ${kv(f.seeds)}</p></div>`}).join('')}
const rng=document.getElementById('day');rng.max=D.length-1;rng.oninput=()=>show(+rng.value);show(0);
let timer=null;document.getElementById('play').onclick=e=>{if(timer){clearInterval(timer);timer=null;e.target.textContent='▶';return}
 e.target.textContent='❚❚';timer=setInterval(()=>{if(+rng.value>=D.length-1){clearInterval(timer);timer=null;e.target.textContent='▶';return}
 rng.value=+rng.value+1;show(+rng.value)},450)};
document.getElementById('ops').innerHTML=[0,1].map(p=>{const o=DATA.ops[p],tot=Object.values(o).reduce((a,b)=>a+b,0)||1;
 const mx=Math.max(...Object.values(o),1);
 const rows=Object.entries(o).map(([k,v])=>`<tr><td>${k}</td><td>${v.toLocaleString()}</td><td>${(100*v/tot).toFixed(1)}%</td>
  <td style="width:45%;text-align:left"><span class="bar" style="width:${100*v/mx}%;background:${p?C2:C1}"></span></td></tr>`).join('');
 const mrows=Object.entries(DATA.market[p]).map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
 return `<div><h2><span class="sw" style="background:${p?C2:C1}"></span>${N[p]}</h2><div class="scroll"><table>
  <tr><th>unit op</th><th>count</th><th>share</th><th></th></tr>${rows}</table></div>
  <div class="scroll" style="margin-top:10px"><table><tr><th>market order (turns)</th><th>count</th></tr>${mrows}</table></div></div>`}).join('');
"""
    title = f"{names[0]} vs {names[1]}"
    sub = "Kaggriculture game report" + ("" if seed is None else f" · seed {seed}")
    return _page(title, html.escape(sub), body, data, script)


# ----------------------------------------------------------------- progress
def _num(v):
    if v in (None, "", "None"):
        return None
    if v in ("True", "False"):
        return 1.0 if v == "True" else 0.0
    try:
        return float(v)
    except ValueError:
        return None


def progress_report(avlod_dir):
    """HTML report of a training run folder (history.csv + avlod_NNN/stats.json)."""
    hist = os.path.join(avlod_dir, "history.csv")
    rows = []
    if os.path.exists(hist):
        with open(hist, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    # history.csv is append-only; a --fresh restart repeats generation numbers - keep the last
    by_gen = {}
    for r in rows:
        g = _num(r.get("generation"))
        if g is not None:
            by_gen[int(g)] = r
    gens = sorted(by_gen)
    get = lambda key: [_num(by_gen[g].get(key)) for g in gens]
    templates = {}
    for d in glob.glob(os.path.join(avlod_dir, "avlod_[0-9]*", "stats.json")):
        try:
            with open(d, encoding="utf-8") as f:
                st = json.load(f)
            templates[st.get("generation")] = st.get("agent_template")
        except (OSError, ValueError):
            pass
    promoted = [i for i, g in enumerate(gens) if by_gen[g].get("promoted") == "True"]
    best_info = {}
    bi = os.path.join(avlod_dir, "best", "info.json")
    if os.path.exists(bi):
        with open(bi, encoding="utf-8") as f:
            best_info = json.load(f)
    data = {
        "gens": gens, "fitness": get("fitness"), "winrate": get("winrate"), "money": get("avg_money"),
        "v8": get("v8_winrate"), "hof": get("pop_vs_hof"), "gate": get("gate_vs_best"),
        "starter": get("pop_vs_starter"), "seconds": get("seconds"), "promoted": promoted,
        "templates": [templates.get(g) for g in gens],
    }
    last = by_gen[gens[-1]] if gens else {}
    tpl = sorted({t for t in templates.values() if t})

    def tile(k, v, note=""):
        return f"<div class='tile'><div class='k'>{k}</div><div class='v'>{v}</div><div class='k'>{note}</div></div>"

    tiles = "".join([
        tile("Generations", len(gens), ", ".join(tpl)),
        tile("Best agent", f"avlod {best_info.get('from_generation', '–')}",
             f"avg ${best_info.get('avg_money', 0):,.0f}" if best_info else "not trained yet"),
        tile("Last champion money", f"${_num(last.get('avg_money')) or 0:,.0f}", f"generation {gens[-1]}" if gens else ""),
        tile("Promotions to best", len(promoted), "gate win rate > 50%"),
    ])
    body = f"""<div class='tiles'>{tiles}</div>
<div class='grid2'><div class='card'><h2>Champion fitness</h2><div id='fit'></div>
<p class='small muted'>Dots: champion promoted to best.</p></div>
<div class='card'><h2>Champion average money</h2><div id='money'></div></div></div>
<div class='card'><h2>Win rates</h2><div id='wr'></div>
<p class='small muted'>champion = all games of the champion; vs v8 = champion vs agents/v8; vs hall of fame =
whole population vs earlier champions; gate = champion vs current best (promoted if &gt; 50%).</p></div>
<div class='card'><h2>Generations</h2><div class='scroll' id='tbl'></div></div>"""
    script = r"""
const G=DATA.gens,C1=css('--s1'),C2=css('--s2'),x=G.map(g=>g);
if(!G.length){document.querySelector('main').insertAdjacentHTML('beforeend','<p>No history.csv yet - train first.</p>')}
else{
lineChart(document.getElementById('fit'),{x,xname:'generation',series:[{name:'fitness',color:C1,values:DATA.fitness,markers:DATA.promoted}]});
lineChart(document.getElementById('money'),{x,xname:'generation',yfmt:'money',series:[{name:'avg money',color:C1,values:DATA.money,markers:DATA.promoted}]});
const S=[{name:'champion',color:C1,values:DATA.winrate},{name:'vs v8',color:C2,values:DATA.v8},
 {name:'vs hall of fame',color:css('--crop-ink'),values:DATA.hof},{name:'gate vs best',color:css('--struct-ink'),values:DATA.gate}]
 .filter(s=>s.values.some(v=>v!=null));
lineChart(document.getElementById('wr'),{x,xname:'generation',yfmt:'pct',ymin:0,ymax:1,h:240,endLabels:true,series:S});
const f=(v,t)=>v==null?'–':fmt(v,t);
document.getElementById('tbl').innerHTML='<table><tr><th>gen</th><th>template</th><th>fitness</th><th>winrate</th><th>avg money</th><th>vs v8</th><th>vs HoF</th><th>gate</th><th>best</th><th>sec</th></tr>'+
 G.map((g,i)=>`<tr><td>${g}</td><td>${DATA.templates[i]||''}</td><td>${f(DATA.fitness[i])}</td><td>${f(DATA.winrate[i],'pct')}</td><td>${f(DATA.money[i],'money')}</td>
 <td>${f(DATA.v8[i],'pct')}</td><td>${f(DATA.hof[i],'pct')}</td><td>${f(DATA.gate[i],'pct')}</td><td>${DATA.promoted.includes(i)?'★':''}</td><td>${f(DATA.seconds[i],'int')}</td></tr>`).join('')+'</table>'}
"""
    name = os.path.basename(os.path.normpath(avlod_dir))
    return _page(f"Training progress · {name}", "Self-play evolution, one row per generation", body, data, script)


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
