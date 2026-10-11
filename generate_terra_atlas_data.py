"""Generate aggregated real Earth Engine dataset and update TerraAtlas dashboard."""

import csv
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path


def safe_float(v: str | None, default: float = 0.0) -> float:
    if not v:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def build_terra_atlas_grid(
    scored_csv_path: Path,
    width: int = 24,
    height: int = 16,
    lon_min: float = 79.00,
    lon_max: float = 79.20,
    lat_min: float = 21.05,
    lat_max: float = 21.25,
) -> list[list]:
    grid = defaultdict(list)
    with scored_csv_path.open(mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = safe_float(row.get("latitude"))
            lon = safe_float(row.get("longitude"))
            x = int((lon - lon_min) / (lon_max - lon_min) * width)
            y = int((lat_max - lat) / (lat_max - lat_min) * height)
            x = max(0, min(width - 1, x))
            y = max(0, min(height - 1, y))
            grid[(x, y)].append(row)

    cells = []
    for y in range(height):
        for x in range(width):
            raw = grid.get((x, y), [])
            if not raw:
                clat = round(lat_max - (y + 0.5) * (lat_max - lat_min) / height, 4)
                clon = round(lon_min + (x + 0.5) * (lon_max - lon_min) / width, 4)
                cells.append([
                    x, y, 0.5, 0.5, 0.0, 0.3, 45.0, 0, 0.1, 0.1, 0.0, clat, clon, 0, 0, "Plant trees"
                ])
                continue

            n = len(raw)
            avg_g = round(sum(safe_float(r.get("normalized_ndvi"), 0.5) for r in raw) / n, 4)
            avg_heat = round(sum(safe_float(r.get("normalized_lst"), 0.5) for r in raw) / n, 4)
            avg_pop = round(sum(safe_float(r.get("normalized_population"), 0.0) for r in raw) / n, 4)
            avg_ndvi = round(sum(safe_float(r.get("ndvi"), 0.0) for r in raw) / n, 4)
            avg_lst_c = round(sum(safe_float(r.get("lst_c"), 0.0) for r in raw) / n, 1)
            tot_pop = round(sum(safe_float(r.get("population_estimate"), 0.0) for r in raw))
            avg_built = round(sum(safe_float(r.get("built_probability"), 0.0) for r in raw) / n, 4)
            avg_tree = round(sum(safe_float(r.get("tree_probability"), 0.0) for r in raw) / n, 4)
            avg_bare = round(sum(safe_float(r.get("bare_probability"), 0.0) for r in raw) / n, 4)
            avg_lat = round(sum(safe_float(r.get("latitude")) for r in raw) / n, 4)
            avg_lon = round(sum(safe_float(r.get("longitude")) for r in raw) / n, 4)
            actions = Counter(r.get("recommended_action") for r in raw)
            maj_act = actions.most_common(1)[0][0]
            water_count = actions.get("Water body", 0)
            is_water = 1 if ((water_count / n) > 0.4 or avg_ndvi < 0) else 0
            is_bare = 1 if ((avg_bare > 0.25) or (actions.get("Check site: bare land", 0) / n > 0.3)) else 0

            cells.append([
                x, y, avg_g, avg_heat, avg_pop, avg_ndvi, avg_lst_c, tot_pop,
                avg_built, avg_tree, avg_bare, avg_lat, avg_lon, is_water, is_bare, maj_act
            ])

    return cells


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>TerraAtlas — Heat Risk & Green Cover Analytics</title>
<style>
:root{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px);
--pane:#faf6ef;--bg:#f4e9db;--card:#fffaf2;--ink:#5a4632;--mut:#a08a73;--line:#eadfce;--sage:#7a9a6b;--sagel:#e6ebdd;--brown:#8a6a4a;--tan:#d3a77d;--or:#d9824a}
@media(prefers-color-scheme:dark){:root{--pane:#1f1c17;--bg:#2a2620;--card:#332e26;--ink:#efe3d2;--mut:#b5a28b;--line:#463f34;--sagel:#3a4434}}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",system-ui,Calibri,sans-serif;display:grid;grid-template-columns:220px minmax(0,1fr);min-height:100vh}
h1,h2,h3{font-family:Georgia,Cambria,serif;margin:0}
aside{background:var(--pane);padding:18px 14px;display:flex;flex-direction:column;gap:6px;position:sticky;top:0;height:100vh;border-right:1px solid var(--line)}
.logo{display:flex;align-items:center;gap:10px;margin-bottom:18px}.logo i{width:38px;height:38px;border-radius:50%;background:var(--sagel);color:var(--sage);display:grid;place-items:center;font-style:normal;font-size:18px}.logo h1{font-size:20px}
.nv{border:0;background:transparent;color:var(--brown);text-align:left;padding:11px 14px;border-radius:14px;font:inherit;cursor:pointer;display:flex;gap:10px;align-items:center;white-space:nowrap}
.nv.on{background:var(--sagel);color:var(--sage);font-weight:600}
.stat-card{margin-top:auto;background:var(--card);border-radius:14px;padding:10px 12px;font-size:12px;color:var(--mut);box-shadow:0 2px 8px #0000000d}.stat-card b{display:block;letter-spacing:.08em;font-size:10px}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--sage);margin-right:6px}
.mc{padding:16px;min-width:0}
.pills{display:inline-flex;background:var(--pane);border-radius:30px;padding:5px;gap:4px;margin-bottom:14px;box-shadow:0 2px 10px #0000000a;align-items:center;flex-wrap:wrap}
.pill{border:0;background:transparent;color:var(--brown);padding:8px 16px;border-radius:24px;font:inherit;font-weight:600;cursor:pointer}.pill.on{background:var(--sage);color:#fff}
.row{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:16px}
@media(max-width:1000px){.row{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px;margin-bottom:14px}
.card h3{font-size:16px;margin-bottom:8px}.lbl{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin:14px 0 8px}
button{font:inherit;cursor:pointer;touch-action:manipulation}
.btn{background:var(--sage);color:#fff;border:0;border-radius:24px;padding:12px 16px;font-weight:600;width:100%}.btn.out{background:var(--card);color:var(--brown);border:1px solid var(--line)}.btn.in{width:auto}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:16px;padding:5px 14px;cursor:pointer}.chip.on{background:var(--sage);color:#fff;border-color:var(--sage)}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center}
.mapc{background:linear-gradient(160deg,#f7dcc0,#efe6d3 60%,#dfe8d4);border-radius:28px;padding:12px;box-shadow:0 6px 24px #8a6a4a22}
.gw{position:relative}.grid{display:grid;gap:2px;width:100%}
.c{aspect-ratio:1;border:0;padding:0;border-radius:4px;position:relative;color:#fff;font-weight:700;font-size:clamp(7px,1.8vw,11px);min-width:0;cursor:pointer}
.c.top{outline:2px solid #6b2f1a;outline-offset:-2px;z-index:1}.c.sel{outline:3px solid #fff;outline-offset:-3px;z-index:2;box-shadow:0 0 0 2px var(--brown)}
.zl{position:absolute;inset:0;display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:repeat(4,1fr);pointer-events:none}
.zl span{display:grid;place-items:center;text-align:center;font:700 12px Georgia,serif;color:#fff;text-shadow:0 1px 3px #000c,0 0 6px #0008;border:1px dashed #ffffff66;padding:2px}
.tele{margin-top:10px;background:#fffaf2e6;border-radius:16px;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 20px;font:12px ui-monospace,monospace;color:var(--brown)}.tele b{color:var(--ink)}
.leg{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;margin-top:10px;color:var(--brown)}.leg i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.panel{background:var(--pane);border-radius:22px;padding:16px;border:1px solid var(--line);align-self:start}
.gauge{display:grid;place-items:center}.quote{font:italic 13px/1.5 Georgia,serif;color:var(--brown);text-align:center;margin:6px 0 0}
.an{background:var(--card);border-radius:16px;padding:10px 12px;margin-bottom:10px;border:1px solid var(--line)}.an>div:first-child{display:flex;justify-content:space-between;font-size:13px;font-weight:600}
.mb{display:flex;gap:5px;align-items:flex-end;height:38px;margin-top:8px}.mb i{flex:1;border-radius:3px 3px 0 0}
label.s{display:grid;grid-template-columns:1fr 36px;gap:2px 8px;font-size:12px;margin:8px 0}label.s input{grid-column:1/3}label.s b{text-align:right}
input[type=range]{width:100%;accent-color:var(--brown)}
.wrap{overflow:auto;max-height:560px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:8px;text-align:left;border-bottom:1px solid var(--line)}
th{cursor:pointer;background:var(--sage);color:#fff;position:sticky;top:0}tr.r{cursor:pointer}tr.r:hover{background:var(--sagel)}
.tag{display:inline-block;color:#fff;border-radius:10px;padding:1px 9px;font-size:12px;font-weight:700}
.alert{border-radius:16px;padding:10px 16px;color:#fff;font-weight:700;margin-bottom:12px}
.stat{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:12px}.stat div{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px 12px;font-size:13px}.stat b{font:700 22px Georgia,serif;display:block}
textarea{width:100%;min-height:200px;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:10px;font:13px/1.5 ui-monospace,monospace}
ul.log{margin:6px 0 0;padding-left:18px;font-size:13px}ul.chk{list-style:none;padding:0;margin:0}ul.chk li{margin:6px 0}
#modal{position:fixed;inset:0;background:#000a;display:none;align-items:center;justify-content:center;padding:16px;z-index:9}#modal .card{max-width:640px;width:100%;margin:0}
.note{font-size:12px;color:var(--mut)}
#toast{position:fixed;bottom:calc(16px + env(safe-area-inset-bottom,0px));left:50%;transform:translateX(-50%);background:var(--brown);color:#fff;padding:8px 16px;border-radius:20px;display:none;z-index:10}
@media(max-width:820px){body{grid-template-columns:1fr}aside{position:static;height:auto;flex-direction:row;overflow-x:auto;padding:10px 12px;border-right:0;border-bottom:1px solid var(--line);scrollbar-width:none}.logo{margin:0 8px 0 0}.logo h1{display:none}.nv{padding:9px 12px}.stat-card{display:none}.wrap{max-height:none}}
@media(max-width:640px){.mc{padding:10px}.card,.panel{padding:10px}.grid{gap:1px}.c{border-radius:2px}.zl span{font-size:8.5px}.pills{display:flex;overflow-x:auto}.pill{flex:1;padding:8px 10px}th,td{padding:7px 5px;font-size:13px}.btn.in{width:100%}.mapc{border-radius:20px;padding:8px}.tele{font-size:11px}}
@media(max-width:520px){th:nth-child(n+5),td:nth-child(n+5){display:none}}
</style></head><body>
<aside><div class="logo"><i>❦</i><h1>TerraAtlas</h1></div><div id="nav" style="display:contents"></div>
<div class="stat-card" id="sideStatus"><b>DATA STATUS</b><span class="dot"></span>Loading...</div></aside>
<div class="mc"><div class="pills" id="pills"></div><div id="app"></div></div>
<div id="modal"><div class="card"><h3 id="mt">Export data</h3><p class="note">Direct download or copy data below:</p><textarea id="mx" readonly></textarea><div class="bar" style="margin-top:8px"><button class="btn in" id="mcopy">Copy</button><button class="btn in out" id="mclose">Close</button></div></div></div>
<div id="toast"></div>
<script>
const NAGPUR_REAL_DATA = __DATA__;
const W=24,H=16,CITIES={Nagpur:{s:7,r:.62,la:21.1458,lo:79.0882,hasReal:true},Pune:{s:21,r:.35,la:18.5204,lo:73.8567},Mumbai:{s:42,r:.82,la:19.076,lo:72.8777}};
const ZN={Nagpur:'Wadi (North),Koradi Road,Kamptee Road,Kalamna,Dharampeth,Civil Lines,Sadar,Itwari,Ambazari,Bajaj Nagar,Sitabuldi,Gandhibagh,Hingna,Wardha Road,Manish Nagar,Sakkardara',
Pune:'Wakad,Aundh,Kalyani Nagar,Viman Nagar,Hinjewadi,Baner,Shivajinagar,Camp,Kothrud,Deccan,Swargate,Hadapsar,Katraj,Kondhwa,Bibwewadi,Wanowrie',
Mumbai:'Borivali,Malad,Goregaon,Mulund,Andheri,Juhu,Powai,Ghatkopar,Bandra,Dadar,Kurla,Chembur,Colaba,Fort,Worli,Byculla'};
Object.keys(ZN).forEach(k=>ZN[k]=ZN[k].split(','));
const ACT={plant:{n:'Plant trees',m:'झाडे लावा',c:'#6f9a5b'},roof:{n:'Cool roof / shade',m:'थंड छत / सावली',c:'#d9824a'},protect:{n:'Protect existing green',m:'हरित क्षेत्र जपा',c:'#4f7a95'},check:{n:'Check site: bare land',m:'जागेची पाहणी करा',c:'#a8957d'},water:{n:'Water body',m:'जलस्रोत',c:'#9cc3d9'}};
const DZ={n:'Heatwave',m:'उष्णतेची लाट',r:'Cooling shelter',ic:'☀'};
const S={city:'Nagpur',mode:'real',w:{h:50,g:30,p:20},top:12,sel:null,lang:'en',tab:'map',sort:{k:'rank',d:1},dz:{sev:60,units:6,dep:false,chk:{}}};
const cl=v=>Math.max(0,Math.min(1,v)),$=s=>document.querySelector(s),lvl=v=>v<.33?'low':v<.55?'moderate':v<.75?'high':'very high';
function sm(x,y,s){return(Math.sin(x*.9+s)+Math.sin(y*1.1+s*2)+Math.sin((x+y)*.6+s*3)+Math.hypot(x-W/2,y-H/2)*.2)/4}
function rng(i,s){const v=Math.sin(i*127.1+s*311.7)*43758.5453;return v-Math.floor(v)}
let cells=[];

function gen(){
  if(S.city==='Nagpur'&&S.mode==='real'&&Array.isArray(NAGPUR_REAL_DATA)&&NAGPUR_REAL_DATA.length===384){
    cells=NAGPUR_REAL_DATA.map((d,i)=>{
      const [x,y,g,heat,pop,ndvi,lst_c,pop_est,built,tree,bare_p,lat,lon,water,bare,official_act]=d;
      const z=Math.floor(y/4)*4+Math.floor(x/6);
      return {
        i,x,y,z,zn:ZN[S.city][z],id:'R'+(y+1)+'-C'+(x+1),
        g,heat,pop,ndvi,lst_c,pop_est,built,tree,bare_p,lat,lon,
        water:Boolean(water),bare:Boolean(bare),official_act,
        score:0,act:'',top:false,rank:0
      };
    });
    score();
    return;
  }
  const {s,r}=CITIES[S.city];cells=[];
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    const i=y*W+x,u=cl(1-Math.hypot((x-W/2)/(W/2),(y-H/2)/(H/2))*.95),j=rng(i,s)-.5,n1=sm(x*.5,y*.5,s),n2=sm(x*.8+3,y*.8,s+1);
    const ry=(r+.14*Math.sin(x*.45+s))*H,dr=Math.abs(y-ry),water=dr<.8;
    let g=cl(.78-.7*u+.28*n2+.2*j),heat=cl(.28+.5*u-.35*g+.22*n1+.15*j),pop=cl(.85*u+.25*n1+.2*j);
    if(water){g=.05;heat=.15;pop=0}
    const z=Math.floor(y/4)*4+Math.floor(x/6);
    cells.push({i,x,y,z,zn:ZN[S.city][z],id:'R'+(y+1)+'-C'+(x+1),g,heat,pop,water,bare:!water&&g<.3&&u<.6&&rng(i,s+9)>.55,score:0,act:'',top:false,rank:0});
  }
  score();
}

function score(){
  const {h,g,p}=S.w,t=(h+g+p)||1;
  cells.forEach(c=>{
    if(c.water){c.score=0;c.act='water';return}
    c.score=(h*c.heat+g*(1-c.g)+p*c.pop)/t;
    if(c.bare){c.act='check'}
    else if(c.g>.62){c.act='protect'}
    else if(c.built!==undefined?(c.built>.4||c.heat>.55):(c.heat>.4)){c.act='roof'}
    else{c.act='plant'}
  });
  cells.filter(c=>!c.water).sort((a,b)=>b.score-a.score).forEach((c,k)=>{c.rank=k+1;c.top=k<S.top});
  cells.forEach(c=>c.water&&(c.top=false));
}

const ramp=(v,a,b)=>`rgb(${[0,1,2].map(i=>Math.round(a[i]+(b[i]-a[i])*v))})`;
function hz(c){return c.water?0:cl(S.dz.sev/100*(.6*c.heat+.2*(1-c.g)+.2*c.pop)*1.25)}
function col(c,l){
  if(c.water)return'#9cc3d9';
  if(l==='hazard')return ramp(hz(c),[250,236,205],[165,25,25]);
  return ACT[c.act].c+Math.round((.4+.6*c.score)*255).toString(16).padStart(2,'0');
}
const zlabels=()=>'<div class="zl">'+ZN[S.city].map(n=>`<span>${n}</span>`).join('')+'</div>';
function grid(l,mark){return`<div class="gw"><div class="grid" style="grid-template-columns:repeat(${W},1fr)">`+cells.map(c=>`<button class="c${c.top&&l==='action'?' top':''}${S.sel===c.i?' sel':''}" data-i="${c.i}" aria-label="${c.zn} ${c.id}" style="background:${col(c,l)}">${mark&&mark[c.i]||''}</button>`).join('')+'</div>'+zlabels()+'</div>'}
const T=(en,mr)=>S.lang==='mr'?mr:en;
function legend(l){const m=l==='hazard'?[['rgb(250,236,205)','Low exposure'],['rgb(165,25,25)','Severe exposure']]:Object.entries(ACT).filter(e=>e[0]!=='water').map(e=>[e[1].c,e[1].n]).concat([['#6b2f1a','Top priority (outlined)']]);
return'<div class="leg">'+m.map(a=>`<span><i style="background:${a[0]}"></i>${a[1]}</span>`).join('')+'<span><i style="background:#9cc3d9"></i>Water</span></div>'}
const sl=(k,l,v,mn,mx)=>`<label class="s">${l}<b>${v}</b><input type="range" data-k="${k}" min="${mn}" max="${mx}" value="${v}"></label>`;
const cur=()=>cells[S.sel!==null?S.sel:(cells.find(c=>c.rank===1)||cells[0]).i];
function prof(c,key){const x0=(c.z%4)*6,y0=Math.floor(c.z/4)*4,o=[];for(let dx=0;dx<6;dx++){let s=0;for(let dy=0;dy<4;dy++)s+=cells[(y0+dy)*W+x0+dx][key];o.push(s/4)}return o}
const bars=(a,cc)=>'<div class="mb">'+a.map(v=>`<i style="height:${Math.max(12,v*100)}%;background:${cc};opacity:${.45+v*.55}"></i>`).join('')+'</div>';
function why(c){
  const w=[];
  if(c.heat>.55)w.push('surface heat is '+lvl(c.heat)+(c.lst_c?` (${c.lst_c.toFixed(1)}°C)`:''));
  if(c.g<.35)w.push('green cover is depleted'+(c.ndvi?` (${c.ndvi.toFixed(2)} NDVI)`:''));
  if(c.pop>.55)w.push('dense population is exposed'+(c.pop_est?` (${c.pop_est.toLocaleString('en-IN')} pop)`:''));
  return w.length?w.join(', '):'conditions are comparatively moderate';
}

function panel(){
  const c=cur(),v=Math.round(c.score*100);
  const ring=`<svg viewBox="0 0 100 100" width="150" height="150"><circle cx="50" cy="50" r="46" fill="none" style="stroke:var(--line)" stroke-width="2.5"/><circle cx="50" cy="50" r="46" fill="none" style="stroke:var(--brown)" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="${c.score*289} 289" transform="rotate(-90 50 50)"/><text x="50" y="54" text-anchor="middle" font-size="30" font-family="Georgia" style="fill:var(--ink)">${v}</text><text x="50" y="68" text-anchor="middle" font-size="7" style="fill:var(--mut)">% NEED</text></svg>`;
  const gText=c.ndvi!==undefined?`${c.ndvi.toFixed(2)} NDVI (${Math.round(c.g*100)}%)`:`${Math.round(c.g*100)}%`;
  const hText=c.lst_c!==undefined?`${c.lst_c.toFixed(1)} °C (${Math.round(c.heat*100)} norm)`:`${Math.round(c.heat*100)}`;
  const actQuote=c.water?'Water body — not scored.':`Rank #${c.rank}: ${why(c)}. Recommended: ${ACT[c.act].n}${c.official_act?` · Pipeline: ${c.official_act}`:''}.`;
  return`<div class="panel" id="det"><div class="gauge">${ring}</div><h3 style="text-align:center">${c.water?'Water body':c.zn}</h3><p class="quote">“${actQuote}”</p>
<div class="lbl">Environmental anomalies</div>
<div class="an"><div><span>Green cover</span><span>${gText}</span></div>${bars(prof(c,'g'),'#7a9a6b')}</div>
<div class="an"><div><span>Surface heat</span><span>${hText}</span></div>${bars(prof(c,'heat'),'#c9824a')}</div>
${c.built!==undefined?`<div class="note" style="margin-bottom:8px">Built-up: ${Math.round(c.built*100)}% · Tree canopy: ${Math.round(c.tree*100)}%</div>`:''}
<div class="lbl">Priority formula weights</div>${sl('h','Urban heat',S.w.h,0,100)}${sl('g','Low green cover',S.w.g,0,100)}${sl('p','Population proximity',S.w.p,0,100)}${sl('top','Top-priority areas',S.top,3,40)}
<div style="display:grid;gap:8px;margin-top:14px"><button class="btn" data-tab="report">Generate Field Briefing</button><button class="btn out" id="csv">Export Spatial Data (CSV)</button></div></div>`;
}

function tele(){
  const c=cur(),{la,lo}=CITIES[S.city];
  const lat=c.lat!==undefined?c.lat:(la+(H/2-c.y)*.0045);
  const lon=c.lon!==undefined?c.lon:(lo+(c.x-W/2)*.0048);
  const popStr=c.pop_est!==undefined?`<span>POP <b>${c.pop_est.toLocaleString('en-IN')}</b></span>`:'';
  return`<div class="tele"><span>ZONE <b>${c.zn}</b></span><span>LAT <b>${lat.toFixed(4)}° N</b></span><span>LON <b>${lon.toFixed(4)}° E</b></span><span>CELL <b>${c.id}</b></span>${popStr}</div>`;
}

function vMap(){
  const isReal = S.city==='Nagpur'&&S.mode==='real';
  const desc = isReal
    ? 'Nagpur data aggregated from Google Earth Engine Landsat 8/9 Level 2 & Dynamic World observations (March–May 2026). Interactive 24×16 grid across 21.05°N–21.25°N, 79.00°E–79.20°E.'
    : 'Illustrative simulated model (each cell ≈ 500 m). Switch to live Earth Engine mode for verified satellite data.';
  return`<div class="row"><div><div class="mapc">${grid('action')}</div>${tele()}${legend('action')}<p class="note">${desc}</p></div>${panel()}</div>`;
}

const srt=()=>cells.filter(c=>!c.water).sort((a,b)=>(a[S.sort.k]>b[S.sort.k]?1:-1)*S.sort.d);
function vPri(){
  const isReal = S.city==='Nagpur'&&S.mode==='real';
  const H2=[['rank','Rank'],['zn','Zone'],['act','Action'],['score','Score'],['heat',isReal?'LST (°C)':'Heat'],['g',isReal?'NDVI':'Green'],['pop',isReal?'Pop (Est)':'Pop.']];
  return`<div class="card"><div class="bar"><span style="flex:1"><b>Priority zones</b> <span class="note">· ${S.city} (${isReal?'Real Satellite':'Simulated'})</span></span><button class="btn in" id="csv">Export CSV</button></div>
<div class="wrap"><table><thead><tr>${H2.map(h=>`<th data-s="${h[0]}">${h[1]}${S.sort.k===h[0]?(S.sort.d>0?' ▲':' ▼'):''}</th>`).join('')}</tr></thead><tbody>${srt().slice(0,60).map(c=>`<tr class="r" data-row="${c.i}"><td>#${c.rank}</td><td>${c.zn} <span class="note">${c.id}</span></td><td><span class="tag" style="background:${ACT[c.act].c}">${ACT[c.act].n}</span></td><td>${Math.round(c.score*100)}</td><td>${c.lst_c?c.lst_c.toFixed(1)+'°C':lvl(c.heat)}</td><td>${c.ndvi?c.ndvi.toFixed(2):lvl(c.g)}</td><td>${c.pop_est?c.pop_est.toLocaleString('en-IN'):lvl(c.pop)}</td></tr>`).join('')}</tbody></table></div><p class="note">Top 60 shown. Click a row to open it on the map.</p></div>`;
}

function dzData(){
  const o=cells.filter(c=>!c.water).sort((a,b)=>hz(b)-hz(a)),t=o.slice(0,S.dz.units),avg=t.reduce((s,c)=>s+hz(c),0)/(t.length||1);
  const lv=avg>.7?['EMERGENCY','#a31515']:avg>.5?['WARNING','#d9824a']:avg>.3?['WATCH','#c58a00']:['ADVISORY','#6f9a5b'];
  const popTot=o.slice(0,S.dz.units*3).reduce((s,c)=>s+(c.pop_est!==undefined?c.pop_est:c.pop*1200),0);
  return{t,avg,lv,pop:Math.round(popTot)};
}

const CHK=['Open cooling shelters in top-risk zones','Distribute ORS and drinking water','Issue outdoor-work restriction 12–4 pm','Alert hospitals and ambulances'];
function vDz(){
  const d=S.dz,D=dzData(),mark={};if(d.dep)D.t.forEach(c=>mark[c.i]=DZ.ic);
  return`<div class="alert" style="background:${D.lv[1]}">${D.lv[0]} — Heatwave · average exposure of response zones ${Math.round(D.avg*100)}%</div>
<div class="row"><div><div class="mapc">${grid('hazard',mark)}</div>${legend('hazard')}${d.dep?`<p class="note">${DZ.ic} = ${DZ.r} deployed.</p>`:''}</div>
<div><div class="card"><h3>Scenario</h3>${sl('sev','Severity',d.sev,10,100)}${sl('units','Response units',d.units,2,15)}<button class="btn" id="deploy">${d.dep?'↺ Recall units':'Deploy cooling shelters'}</button>
<div class="stat" style="margin-top:12px"><div><b>${D.t.length}</b>response zones</div><div><b>~${D.pop.toLocaleString('en-IN')}</b>residents covered</div></div></div>
<div class="card"><h3>Response checklist</h3><ul class="chk">${CHK.map((t,k)=>`<li><label><input type="checkbox" data-chk="${k}" ${d.chk[k]?'checked':''}> ${t}</label></li>`).join('')}</ul></div>
<div class="card"><h3>Top response zones</h3><ul class="log">${D.t.slice(0,6).map(c=>`<li><a href="#" data-pick="${c.i}">${c.zn}</a> (${c.id}) — exposure ${Math.round(hz(c)*100)}%</li>`).join('')}</ul><button class="btn" style="margin-top:10px" id="alertBtn">Generate public alert</button></div></div></div>`;
}

function alertText(){
  const D=dzData(),z=D.t.slice(0,5).map(c=>c.zn).join(', ');
  return S.lang==='mr'?`⚠ ${DZ.m} — ${D.lv[0]}\nशहर: ${S.city}\nअतिजोखमीची क्षेत्रे: ${z}\nकृपया सुरक्षित रहा, भरपूर पाणी प्या, दुपारी बाहेर पडणे टाळा आणि अधिकृत सूचनांचे पालन करा. मदतीसाठी १०८ / ११२.`:`⚠ HEATWAVE — ${D.lv[0]}\nCity: ${S.city}\nHighest-risk zones: ${z}\nStay hydrated, avoid going out 12–4 pm, and check on neighbours. Emergency: 112 / 108.`;
}

function reportText(){
  const t=cells.filter(c=>c.top),n=a=>t.filter(c=>c.act===a).length,D=dzData(),A=['plant','roof','protect','check'];
  const isReal=S.city==='Nagpur'&&S.mode==='real';
  if(S.lang==='mr')return`उष्णता जोखीम आणि हरित आच्छादन अहवाल — ${S.city} (${isReal?'भू-उपग्रह डेटा':'मॉडेल'})\n\nएकूण प्राधान्य क्षेत्रे: ${t.length}\n${A.map(a=>`• ${ACT[a].m}: ${n(a)}`).join('\n')}\n\nसर्वोच्च प्राधान्य:\n${t.slice(0,5).map(c=>`${c.rank}. ${c.zn} (${c.id}) — ${ACT[c.act].m} (गुण ${Math.round(c.score*100)})`).join('\n')}\n\nआपत्ती व्यवस्थापन (${DZ.m}): इशारा पातळी ${D.lv[0]}.\nटीप: हा अहवाल नियोजन हेतूने आहे, प्रत्यक्ष पाहणी आवश्यक आहे.`;
  return`HEAT RISK & GREEN COVER REPORT — ${S.city} (${isReal?'Google Earth Engine Landsat 8/9 & Dynamic World':'Simulated Model'})\n\nPriority areas identified: ${t.length}\n${A.map(a=>`• ${ACT[a].n}: ${n(a)}`).join('\n')}\n\nTop areas to prioritize first:\n${t.slice(0,5).map(c=>`${c.rank}. ${c.zn} (${c.id}) — ${ACT[c.act].n} (score ${Math.round(c.score*100)}; heat ${c.lst_c?c.lst_c.toFixed(1)+'°C':lvl(c.heat)}, green ${c.ndvi?c.ndvi.toFixed(2)+' NDVI':lvl(c.g)})`).join('\n')}\n\nDisaster readiness (${DZ.n}, severity ${S.dz.sev}%): alert level ${D.lv[0]}; top response zones: ${D.t.slice(0,5).map(c=>c.zn).join(', ')}.\n\nNote: Planning aid based on satellite observations (Nagpur 2026-03 to 2026-05). Field verification is recommended before planting or cool-roof interventions.`;
}

function vRep(){
  const t=cells.filter(c=>c.top);
  return`<div class="row"><div class="card"><div class="bar"><button class="chip${S.lang==='en'?' on':''}" data-lang="en">English</button><button class="chip${S.lang==='mr'?' on':''}" data-lang="mr">मराठी</button></div><textarea readonly style="min-height:340px">${reportText()}</textarea><button class="btn in" style="margin-top:8px" id="dlRep">⬇ Download report</button></div>
<div class="card" style="align-self:start"><h3>At a glance</h3><div class="stat"><div><b>${t.length}</b>priority areas</div><div><b>${t.filter(c=>c.act==='plant').length}</b>to plant</div><div><b>${t.filter(c=>c.act==='roof').length}</b>cool roofs</div><div><b>${t.filter(c=>c.act==='protect').length}</b>protect</div></div><p class="note">Computed deterministically from satellite & population indices.</p></div></div>`;
}

const TABS={map:['◎','Map View',vMap],priorities:['▤','Priority Zones',vPri],disaster:['⚠','Disaster Response',vDz],report:['▥','Field Report',vRep]};
function render(){
  $('#nav').innerHTML=Object.entries(TABS).map(e=>`<button class="nv${S.tab===e[0]?' on':''}" data-tab="${e[0]}"><span>${e[1][0]}</span>${e[1][1]}</button>`).join('');
  const cityPills = Object.keys(CITIES).map(c=>`<button class="pill${S.city===c?' on':''}" data-city="${c}">${c}</button>`).join('');
  const modePills = S.city==='Nagpur' ? `<span style="border-left:1px solid var(--line);margin:0 4px;height:20px"></span><button class="pill${S.mode==='real'?' on':''}" data-mode="real" style="font-size:12px;padding:6px 12px">🟢 Earth Engine Real</button><button class="pill${S.mode==='sim'?' on':''}" data-mode="sim" style="font-size:12px;padding:6px 12px">⚙ Simulated</button>` : '';
  $('#pills').innerHTML = cityPills + modePills;
  $('#app').innerHTML = TABS[S.tab][2]();
  const sideEl = $('#sideStatus');
  if(sideEl){
    if(S.city==='Nagpur'&&S.mode==='real'){
      sideEl.innerHTML='<b>DATA STATUS</b><span class="dot" style="background:#2e7d32"></span>Earth Engine Live · Nagpur 2026<div style="font-size:10px;margin-top:2px;color:var(--mut)">Landsat 8/9 & Dynamic World</div>';
    }else{
      sideEl.innerHTML='<b>DATA STATUS</b><span class="dot"></span>Simulated demo · 500 m cells';
    }
  }
}

function toast(m){const t=$('#toast');t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',2200)}
function modal(title,txt){$('#mt').textContent=title;$('#mx').value=txt;$('#modal').style.display='flex'}
function save(name,data){
  try{
    const blob=new Blob([data],{type:name.endsWith('.csv')?'text/csv':'text/plain'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download=name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast('Saved '+name);
    return;
  }catch(e){}
  modal(name,data);
}
async function copy(t){try{await navigator.clipboard.writeText(t);toast('Copied')}catch(e){modal('Copy text',t)}}
function csv(){
  const isReal = S.city==='Nagpur'&&S.mode==='real';
  const header = isReal
    ? 'rank,zone,cell_id,action,score,latitude,longitude,lst_c,ndvi,population_estimate,built_prob\n'
    : 'rank,zone,cell,action,score,heat,green_cover,population\n';
  const rows = cells.filter(c=>!c.water).sort((a,b)=>a.rank-b.rank).map(c=>{
    if(isReal){
      return [c.rank,`"${c.zn}"`,c.id,`"${ACT[c.act].n}"`,c.score.toFixed(3),c.lat,c.lon,c.lst_c,c.ndvi,c.pop_est,c.built].join(',');
    }
    return [c.rank,`"${c.zn}"`,c.id,`"${ACT[c.act].n}"`,c.score.toFixed(3),c.heat.toFixed(3),c.g.toFixed(3),c.pop.toFixed(3)].join(',');
  }).join('\n');
  return header+rows;
}

document.addEventListener('click',e=>{
  const t=e.target,q=s=>t.closest(s);let b,cell=false;
  if(b=q('[data-tab]'))S.tab=b.dataset.tab;
  else if(b=q('[data-city]')){S.city=b.dataset.city;S.mode=S.city==='Nagpur'?'real':'sim';S.sel=null;S.dz.dep=false;gen()}
  else if(b=q('[data-mode]')){S.mode=b.dataset.mode;S.sel=null;gen()}
  else if(b=q('.c')){S.sel=+b.dataset.i;cell=true;const c=cells[S.sel];if(S.tab==='disaster')toast(c.zn+': heatwave exposure '+Math.round(hz(c)*100)+'%')}
  else if(b=q('[data-s]')){const k=b.dataset.s;S.sort=S.sort.k===k?{k,d:-S.sort.d}:{k,d:['rank','zn','act'].includes(k)?1:-1}}
  else if(b=q('[data-row]')){S.sel=+b.dataset.row;S.tab='map'}
  else if(b=q('[data-pick]')){e.preventDefault();S.sel=+b.dataset.pick;S.tab='map'}
  else if(b=q('[data-lang]'))S.lang=b.dataset.lang;
  else if(q('#deploy')){S.dz.dep=!S.dz.dep;toast(S.dz.dep?S.dz.units+' units deployed':'Units recalled')}
  else if(q('#alertBtn')){modal('Public alert ('+(S.lang==='mr'?'मराठी':'English')+')',alertText());return}
  else if(q('#csv')){save('terraatlas-'+S.city.toLowerCase()+'-priorities.csv',csv());return}
  else if(q('#dlRep')){save('terraatlas-'+S.city.toLowerCase()+'-report-'+S.lang+'.txt',reportText());return}
  else if(q('#mcopy')){copy($('#mx').value);return}
  else if(q('#mclose')||t.id==='modal'){$('#modal').style.display='none';return}
  else return;
  render();
  if(cell&&S.tab==='map'&&innerWidth<=1000)$('#det').scrollIntoView({behavior:'smooth',block:'nearest'});
});

document.addEventListener('input',e=>{
  const t=e.target,k=t.dataset.k;if(!k)return;const v=+t.value;
  if(k==='top')S.top=v;else if(k==='sev'||k==='units')S.dz[k]=v;else S.w[k]=v;
  score();
  if(t.previousElementSibling)t.previousElementSibling.textContent=v;
});

document.addEventListener('change',e=>{
  if(e.target.dataset.k){const y=scrollY;render();scrollTo(0,y)}
  else if(e.target.dataset.chk)S.dz.chk[e.target.dataset.chk]=e.target.checked;
});

gen();render();
</script></body></html>
"""


def update_terra_atlas_html(root: Path, compact_cells: list[list]) -> None:
    html_path = root / "TerraAtlas.html"
    json_str = json.dumps(compact_cells, separators=(",", ":"))
    content = HTML_TEMPLATE.replace("__DATA__", json_str)
    html_path.write_text(content, encoding="utf-8")
    print(f"Updated {html_path} with real Earth Engine data ({html_path.stat().st_size} bytes)")

    site_copy = root / "site" / "terra_atlas.html"
    if (root / "site").is_dir():
        shutil.copy2(html_path, site_copy)
        print(f"Copied updated dashboard to {site_copy}")


def main() -> None:
    root = Path(__file__).parent
    scored_csv = root / "outputs" / "scored" / "cell_priority_scores.csv"
    if not scored_csv.is_file():
        raise SystemExit(f"Scored file not found: {scored_csv}")

    compact_cells = build_terra_atlas_grid(scored_csv)
    out_json = root / "outputs" / "terra_atlas_nagpur.json"
    out_json.write_text(json.dumps(compact_cells, separators=(",", ":")), encoding="utf-8")
    print(f"Generated {len(compact_cells)} aggregated cells -> {out_json} ({out_json.stat().st_size} bytes)")

    update_terra_atlas_html(root, compact_cells)


if __name__ == "__main__":
    main()
