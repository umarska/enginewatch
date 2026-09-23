/* EngineWatch: dependency-free client. Every displayed result comes from the API. */
"use strict";

const ICONS = {
  grid: '<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="3" width="6" height="6" rx="1"/><rect x="3" y="15" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  bars: '<path d="M4 20V11m6 9V4m6 16V8m6 12H2"/>',
  book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  back: '<path d="M19 12H5m5-5-5 5 5 5"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  engine: '<path d="M6 7h12v10H6Zm0 3H3v4h3m12-3h3v2h-3M9 7V4h6v3M9 17v3m6-3v3"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Zm-4 9 3 3 5-6"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  play: '<path d="m8 5 11 7-11 7Z"/>',
  pause: '<path d="M7 5h3v14H7Zm7 0h3v14h-3Z"/>',
  warning: '<path d="m12 3 10 18H2Zm0 6v5m0 3v.1"/>',
  check: '<path d="m5 12 4 4 10-10"/>',
  refresh: '<path d="M20 7a9 9 0 1 0 1 8M20 3v5h-5"/>'
};
const state = { payload: null, fleetPage: 0, filter: "all", sort: "id", search: "", engine: null, engineId: null, index: 0, sensorId: null, showTruth: false, playback: null, requestToken: 0, route: "fleet" };
const view = document.getElementById("app-view");
const dialog = document.getElementById("upload-dialog");
const PAGE_SIZE = 8;
const escaped = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
const finite = value => typeof value === "number" && Number.isFinite(value);
const number = (value, decimals = 0) => finite(value) ? value.toLocaleString("en-GB", { maximumFractionDigits: decimals, minimumFractionDigits: decimals }) : "—";
const percent = (value, decimals = 0) => finite(value) ? `${number(value * 100, decimals)}%` : "—";
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.info}</svg>`;
const engineName = id => String(id).match(/^\d+$/) ? `Engine ${String(id).padStart(3,"0")}` : `Engine ${escaped(id)}`;
const modelName = model => ({hist_gradient_boosting:"Gradient boosting",gradient_boosting:"Gradient boosting",ridge:"Ridge regression",linear_regression:"Linear regression",linear:"Linear regression",constant:"Constant baseline",baseline:"Constant baseline",last_observation:"Last observation"})[model] || String(model || "Model").replace(/_/g," ").replace(/^./,c=>c.toUpperCase());
const summary = () => state.payload?.summary || {};
const metrics = () => summary().metrics || [];
const selectedMetric = () => metrics().find(item => item.model === summary().selected_model) || metrics()[metrics().length - 1] || {};
const metricValue = (item, key) => item[key] ?? item[key.toUpperCase()];

function fillIcons(root = document) { root.querySelectorAll("[data-icon]").forEach(node => { node.innerHTML = icon(node.dataset.icon); }); }
fillIcons();

async function api(url, options = {}) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { throw new Error("The server did not return a readable response. Restart the app and try again."); }
  if (!response.ok) throw new Error(data.error || `The request failed (${response.status}).`);
  return data;
}

function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message; node.hidden = false;
  clearTimeout(toast.timeout); toast.timeout = setTimeout(() => { node.hidden = true; }, 3500);
}

function setNavigation(route) {
  state.route = route;
  document.querySelectorAll("[data-nav]").forEach(node => {
    const active = node.dataset.nav === route;
    node.classList.toggle("active", active);
    if (active) node.setAttribute("aria-current", "page"); else node.removeAttribute("aria-current");
  });
  document.getElementById("breadcrumb-current").textContent = {fleet:"Fleet overview",engine:"Engine explorer",benchmark:"Model benchmark",methodology:"Methodology"}[route] || "Fleet overview";
}

function stopPlayback() { clearInterval(state.playback); state.playback = null; }

async function boot() {
  try {
    state.payload = await api("/api/summary");
    if (!Array.isArray(state.payload.fleet) || !state.payload.summary) throw new Error("The model summary is incomplete. Run the training pipeline to create the app artifacts.");
    document.getElementById("nav-fleet-count").textContent = number(state.payload.fleet.length);
    route();
  } catch (error) { view.innerHTML = `<div class="error-state"><span class="eyebrow">MODEL ARTIFACTS UNAVAILABLE</span><h2>The fleet could not be loaded</h2><p>${escaped(error.message)}</p><button class="button primary" data-action="retry">${icon("refresh")} Try again</button></div>`; }
}

function route() {
  if (!state.payload) return;
  const [page, id] = location.hash.slice(1).split("/");
  const next = ["fleet","engine","benchmark","methodology"].includes(page) ? page : "fleet";
  stopPlayback(); setNavigation(next);
  if (next === "engine") {
    if (id === "uploaded" && state.engine?.uploaded) { renderEngine(); return; }
    const chosen = id || state.engineId || String(state.payload.fleet[0]?.id ?? "");
    if (!chosen) { view.innerHTML = '<div class="empty-state">There are no engines to explore.</div>'; return; }
    loadEngine(chosen);
  } else if (next === "benchmark") renderBenchmark();
  else if (next === "methodology") renderMethodology();
  else renderFleet();
}
window.addEventListener("hashchange", route);

function statusFor(rul) {
  if (!finite(rul)) return { label:"Unavailable", className:"", key:"unknown" };
  if (rul <= 30) return { label:"Review · ≤30", className:"priority", key:"review" };
  if (rul <= 80) return { label:"Watch · 31–80", className:"watch", key:"watch" };
  return { label:"Horizon · >80", className:"", key:"horizon" };
}
function badge(rul) { const status = statusFor(rul); return `<span class="status-badge ${status.className}"><span class="status-dot"></span>${status.label}</span>`; }

function turbineArt() {
  let blades = "";
  for (let i = 0; i < 18; i++) blades += `<path d="M0-27C14-36 31-65 18-89C37-82 50-63 47-48C34-33 20-23 0-27Z" transform="rotate(${i*20})"/>`;
  return `<div class="engine-art" aria-hidden="true"><span class="art-coordinate top">TURBOFAN / HEALTH MONITOR</span><svg viewBox="0 0 390 220"><defs><linearGradient id="blade-fill" x1="0" x2="1"><stop stop-color="#dae8e1"/><stop offset="1" stop-color="#adc6bc"/></linearGradient><pattern id="art-grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#d5e3dc" stroke-width=".5"/></pattern></defs><rect width="390" height="220" fill="url(#art-grid)"/><g transform="translate(198 111)"><circle r="97" fill="none" stroke="#b0c8bd" stroke-width=".7" stroke-dasharray="3 5"/><circle r="87" fill="none" stroke="#bdd1c8"/><g fill="url(#blade-fill)" stroke="#72988b" stroke-width=".65">${blades}</g><circle r="28" fill="#ccdfd5" stroke="#759c8e"/><circle r="19" fill="#e6efe9" stroke="#82a799"/><circle r="6" fill="#9bbbac" stroke="#658c7e"/><path d="M-114 0h-28m256 0h28M0-102v-13m0 217v13" stroke="#8fad9e" stroke-width=".6"/><circle r="104" fill="none" stroke="#c5d9ce" stroke-width=".7"/></g><path d="M260 40h58v27m-175 98H71v-26" fill="none" stroke="#99b4a7" stroke-width=".7"/><circle cx="260" cy="40" r="2" fill="#608f7e"/><circle cx="143" cy="165" r="2" fill="#608f7e"/></svg><span class="art-coordinate bottom">FD001 · SINGLE OPERATING CONDITION</span></div>`;
}

function metricCard(label, value, unit, note, glyph, tone = "") { return `<div class="metric-card"><div class="metric-label"><span>${label}</span>${icon(glyph)}</div><div class="metric-value">${value}<small>${unit}</small></div><p class="metric-note ${tone}">${note}</p></div>`; }

function renderFleet() {
  const all = state.payload.fleet;
  const rul = all.map(e => e.predicted_rul).filter(finite).sort((a,b)=>a-b);
  const median = rul.length ? rul.length%2 ? rul[(rul.length-1)/2] : (rul[rul.length/2-1]+rul[rul.length/2])/2 : null;
  const reviews = all.filter(e => finite(e.predicted_rul) && e.predicted_rul<=30).length;
  const rmse = metricValue(selectedMetric(), "rmse");
  view.innerHTML = `<div class="page-heading"><div><span class="eyebrow">PREDICTIVE MAINTENANCE</span><h1>Fleet intelligence</h1><p>A working view of engine health, one operating cycle at a time.</p></div><button class="button secondary" data-action="upload">${icon("upload")} Analyze data</button></div>
    <section class="hero" aria-labelledby="hero-title"><div class="hero-copy"><span class="eyebrow">FROM SENSOR READINGS TO REMAINING LIFE</span><h1 id="hero-title">A clearer view of<br><span>what comes next.</span></h1><p>Explore an engine’s journey toward failure. See its predicted remaining life, understand the uncertainty, and trace the sensor signals behind it.</p><div class="hero-meta"><span>${icon("engine")} ${number(all.length)} held-out engines</span><span>${icon("shield")} ${percent(summary().interval?.nominal_coverage || .9)} prediction intervals</span></div></div>${turbineArt()}</section>
    <div class="metric-grid">${metricCard("Engines in benchmark",number(all.length),"engines","Held out from model development","engine")}${metricCard("Median remaining life",number(median),"cycles","Predictions at last observed cycle","clock")}${metricCard("Short predicted horizon",number(reviews),"engines","Estimated remaining life ≤30 cycles","activity",reviews ? "amber":"")}${metricCard("Test prediction error",number(rmse,1),"cycles RMSE",escaped(modelName(summary().selected_model)),"bars","positive")}</div>
    <div class="dashboard-grid"><section class="panel"><div class="panel-header"><div><h2>Engine fleet</h2><p>Latest observation · select an engine to replay its history</p></div><span class="tiny-tag">FD001 / TEST SET</span></div><div class="fleet-tools"><label class="search-field">${icon("search")}<input id="fleet-search" type="search" placeholder="Search engine ID…" value="${escaped(state.search)}" aria-label="Search engines by ID"></label><select id="fleet-filter" class="filter-select" aria-label="Filter predicted horizon"><option value="all">All horizons</option><option value="review">Review · ≤30 cycles</option><option value="watch">Watch · 31–80 cycles</option><option value="horizon">Horizon · >80 cycles</option></select><select id="fleet-sort" class="filter-select" aria-label="Sort engines"><option value="id">Engine ID ↑</option><option value="rul-asc">Remaining life ↑</option><option value="rul-desc">Remaining life ↓</option><option value="cycles-desc">Observed cycles ↓</option></select></div><div id="fleet-rows"></div></section>
    <aside class="side-stack fleet-aside"><section class="panel"><div class="panel-header"><div><h2>Remaining life spread</h2><p>At the final observed cycle</p></div>${icon("bars")}</div>${distribution(all)}</section><section class="panel signal-panel"><span class="eyebrow">A BENCHMARK YOU CAN EXPLORE</span><h2 class="signal-title">Watch a prediction evolve.</h2><p>Replay the full sensor history and reveal benchmark truth when you want to compare the model with the simulated outcome.</p><a class="button text" href="#engine/${escaped(all[0]?.id || "")}">Open engine explorer ${icon("arrow")}</a></section></aside></div>
    <div class="source-strip">${icon("info")}<p><strong>Simulated data. Measured results.</strong> This fleet is NASA’s FD001 test set. Horizon buckets are display aids, not validated maintenance alerts. All estimates come from the trained model; interval coverage is measured separately on unseen engines. <a href="#methodology">How it works →</a></p></div>`;
  document.getElementById("fleet-filter").value = state.filter;
  document.getElementById("fleet-sort").value = state.sort;
  renderFleetRows();
}

function distribution(fleet) {
  const ranges = [[0,25],[25,50],[50,75],[75,100],[100,150],[150,Infinity]];
  const labels = ["0–25","26–50","51–75","76–100","101–150","150+"];
  const counts = ranges.map(([low,high],i) => fleet.filter(e=>finite(e.predicted_rul) && (i===0 ? e.predicted_rul>=0 : e.predicted_rul>low) && e.predicted_rul<=high).length);
  const max = Math.max(1,...counts);
  return `<div class="distribution-body"><div class="distribution-chart" role="img" aria-label="Predicted remaining life distribution: ${counts.map((count,i)=>`${labels[i]} cycles: ${count} engines`).join("; ")}">${counts.map((count,i)=>`<div class="distribution-column"><div class="bar" style="height:${Math.max(count?8:0,count/max*76)}%"><span>${count}</span></div><span>${labels[i]}</span></div>`).join("")}</div><p class="chart-caption">PREDICTED REMAINING LIFE / OPERATING CYCLES</p><div class="distribution-legend"><span class="swatch amber"></span> Shorter horizon <span class="swatch" style="margin-left:10px"></span> Longer horizon</div></div>`;
}

function renderFleetRows() {
  let fleet = state.payload.fleet.filter(e => (!state.search || String(e.id).toLowerCase().includes(state.search.toLowerCase().replace(/^engine\s*0*/,"")) || String(e.id).padStart(3,"0").includes(state.search)) && (state.filter==="all" || statusFor(e.predicted_rul).key===state.filter));
  fleet = [...fleet].sort((a,b)=>state.sort==="rul-asc" ? a.predicted_rul-b.predicted_rul : state.sort==="rul-desc" ? b.predicted_rul-a.predicted_rul : state.sort==="cycles-desc" ? b.cycles-a.cycles : Number(a.id)-Number(b.id));
  const pages = Math.max(1,Math.ceil(fleet.length/PAGE_SIZE));
  state.fleetPage = Math.min(state.fleetPage,pages-1);
  const start = state.fleetPage*PAGE_SIZE;
  const visible = fleet.slice(start,start+PAGE_SIZE);
  const maxRul = Math.max(1,...state.payload.fleet.map(e=>finite(e.predicted_rul)?e.predicted_rul:0));
  document.getElementById("fleet-rows").innerHTML = `<div class="table-scroll"><table class="fleet-table"><thead><tr><th scope="col">ENGINE</th><th scope="col" class="mobile-hidden">OBSERVED CYCLES</th><th scope="col">PREDICTED RUL</th><th scope="col">90% INTERVAL</th><th scope="col">HORIZON</th><th scope="col"><span class="visually-hidden">Explore</span></th></tr></thead><tbody>${visible.map(e=>`<tr><td><span class="fleet-id"><span class="engine-mini">${icon("engine")}</span><button class="engine-link" data-action="engine" data-id="${escaped(e.id)}">${engineName(e.id)}</button></span></td><td class="mobile-hidden">${number(e.cycles)}</td><td><span class="range-cell"><i style="width:${Math.max(0,Math.min(100,e.predicted_rul/maxRul*100))}%"></i></span><span class="rul-table-value">${number(e.predicted_rul)}</span> cycles</td><td>${number(e.lower_rul)}–${number(e.upper_rul)}</td><td>${badge(e.predicted_rul)}</td><td><button class="row-arrow" data-action="engine" data-id="${escaped(e.id)}" aria-label="Explore ${engineName(e.id)}">${icon("chevron")}</button></td></tr>`).join("")}</tbody></table>${visible.length ? "" : '<div class="empty-state">No engines match these filters. Try another engine ID or horizon.</div>'}</div><div class="table-footer"><span>${fleet.length ? `${start+1}–${Math.min(start+PAGE_SIZE,fleet.length)}` : "0"} of ${fleet.length} engines</span><div class="pager"><button data-action="prev-page" ${state.fleetPage===0?"disabled":""} aria-label="Previous fleet page">‹</button><span>${state.fleetPage+1} / ${pages}</span><button data-action="next-page" ${state.fleetPage>=pages-1?"disabled":""} aria-label="Next fleet page">›</button></div></div>`;
}

async function loadEngine(id) {
  const token = ++state.requestToken;
  if (state.engine && !state.engine.uploaded && String(state.engine.id)===String(id)) { renderEngine(); return; }
  view.innerHTML = '<div class="initial-loading"><div class="loading-ring"></div><p>Loading engine history…</p><span>Reading sensor trends and cycle-by-cycle predictions</span></div>';
  try {
    const engine = await api(`/api/engines/${encodeURIComponent(id)}`);
    if (token!==state.requestToken || state.route!=="engine") return;
    if (!Array.isArray(engine.cycles) || !engine.cycles.length) throw new Error("This engine has no operating history to display.");
    state.engine = engine; state.engineId = id; state.index=engine.cycles.length-1; state.sensorId=engine.sensors?.[0]?.id; state.showTruth=false;
    renderEngine();
  } catch(error) { if (token===state.requestToken && state.route==="engine") view.innerHTML=`<div class="error-state"><h2>Engine history unavailable</h2><p>${escaped(error.message)}</p><a class="button secondary" href="#fleet">Return to fleet</a></div>`; }
}

function currentPrediction() { const e=state.engine,i=state.index;return {prediction:e.predictions?.[i],low:e.lower?.[i],high:e.upper?.[i],truth:e.true_rul?.[i],cycle:e.cycles?.[i]}; }

function renderEngine() {
  const e=state.engine;
  if (!e) return;
  state.index=Math.min(state.index,e.cycles.length-1);
  const last=e.cycles[e.cycles.length-1];
  if (!e.sensors?.some(sensor=>sensor.id===state.sensorId)) state.sensorId=e.sensors?.[0]?.id;
  const hasTruth=Array.isArray(e.true_rul) && e.true_rul.some(finite);
  view.innerHTML = `<a class="back-link" href="#fleet">${icon("back")} Fleet overview</a><div class="page-heading engine-heading"><div><span class="eyebrow">${e.uploaded?"UPLOADED ENGINE HISTORY":"HELD-OUT ENGINE / NASA FD001"}</span><h1 class="engine-number">${engineName(e.id)} <span class="tiny-tag ${e.uploaded?"":"teal"}" style="vertical-align:middle;margin-left:8px">${e.uploaded?"USER DATA":"TEST SET"}</span></h1><p>${number(last)} observed cycles · Replay the model’s view of this engine.</p></div><div class="heading-actions"><button class="button secondary" data-action="export-json">${icon("download")} Prediction JSON</button><button class="button secondary" data-action="export-csv">${icon("download")} Prediction CSV</button></div></div>
    ${(e.warnings||[]).length?`<div class="warning-banner">${icon("warning")}<span>${(e.warnings||[]).map(escaped).join(" ")}</span></div>`:""}
    <div class="engine-detail-grid"><div><section class="panel chart-panel"><div class="panel-header"><div><h2>Remaining useful life</h2><p>Predicted operating cycles before failure</p></div><div class="chart-legend"><span><i class="swatch blue"></i>Prediction</span><span><i class="swatch band"></i>90% interval</span><span id="truth-legend" ${state.showTruth?"":"hidden"}><i class="swatch teal"></i>Benchmark truth</span></div></div><div id="rul-chart" class="chart-container"></div><div class="replay-controls"><div class="replay-top"><span class="replay-label">ENGINE HISTORY REPLAY</span><span class="replay-cycle" id="replay-cycle">Cycle ${number(e.cycles[state.index])} <span>/ ${number(last)}</span></span></div><div class="replay-row"><button class="play-button" id="play-button" data-action="play" aria-label="Play engine history">${icon("play")}</button><input class="cycle-slider" id="cycle-slider" type="range" min="0" max="${e.cycles.length-1}" value="${state.index}" aria-label="Operating cycle" aria-valuetext="Cycle ${number(e.cycles[state.index])}"><button class="replay-reset" data-action="terminal">Last observation ↗</button></div><p class="replay-description">Move through the observed history. Each prediction uses only readings available at that cycle.</p></div></section><section class="panel sensor-panel"><div class="panel-header"><div><h2>Sensor history</h2><p>Raw measurements across the observed engine life</p></div><select class="sensor-select" id="sensor-select" aria-label="Choose sensor">${(e.sensors||[]).map(sensor=>`<option value="${escaped(sensor.id)}">${escaped(sensor.label || sensor.id)}</option>`).join("")}</select></div><div id="sensor-chart" class="chart-container"></div><p class="sensor-note" id="sensor-note"></p></section></div>
    <aside class="side-stack engine-aside"><section class="panel rul-summary"><span class="eyebrow">PREDICTED REMAINING LIFE</span><div class="rul-hero" id="rul-value"></div><div class="rul-range"><span>90% prediction interval</span><strong id="rul-range"></strong></div><p class="interval-note">An estimated range, not a guarantee. ${percent(summary().interval?.test_coverage,1)} of terminal test outcomes fell inside the nominal 90% intervals.</p><div id="rul-status"></div><p class="selected-cycle-caption" id="selected-cycle-caption"></p>${hasTruth?`<label class="truth-control"><input id="show-truth" type="checkbox" ${state.showTruth?"checked":""}> Reveal benchmark truth</label><div class="truth-value" id="truth-value" ${state.showTruth?"":"hidden"}></div>`:'<div class="truth-control">Benchmark truth unavailable for uploaded data.</div>'}</section><section class="panel sensitivity-panel"><span class="eyebrow">MODEL RESPONSE / TERMINAL OBSERVATION</span><h2>Sensor substitution sensitivity</h2><p>Replace one sensor’s feature group with training medians, then measure how much the estimated remaining life changes.</p><div class="effect-list">${sensitivity(e.contributions||[])}</div><div class="sensitivity-terminal" id="sensitivity-terminal"></div><p>Positive = the substitution increases predicted life. These are model responses, not causal effects or fault diagnoses.</p></section></aside></div>`;
  if (state.sensorId) document.getElementById("sensor-select").value=state.sensorId;
  updateEngine();
}

function sensitivity(contributions) {
  const items=[...contributions].filter(item=>finite(item.effect)).sort((a,b)=>Math.abs(b.effect)-Math.abs(a.effect)).slice(0,6);
  const max=Math.max(1,...items.map(item=>Math.abs(item.effect)));
  if (!items.length) return '<div class="empty-state" style="padding:8px 0">Sensitivity results are unavailable.</div>';
  return items.map(item=>`<div><div class="effect-top"><span title="${escaped(item.label||item.sensor)}">${escaped(item.label||item.sensor)}</span><strong>${item.effect>=0?"+":""}${number(item.effect,1)} cycles</strong></div><div class="effect-track"><i class="${item.effect<0?"negative":""}" style="width:${Math.abs(item.effect)/max*100}%"></i></div></div>`).join("");
}

function updateEngine() {
  if (state.route!=="engine" || !state.engine) return;
  const p=currentPrediction(),e=state.engine,last=e.cycles[e.cycles.length-1];
  document.getElementById("rul-value").innerHTML=`${number(p.prediction)}<small>operating cycles remaining</small>`;
  document.getElementById("rul-range").textContent=`${number(p.low)}–${number(p.high)} cycles`;
  document.getElementById("rul-status").innerHTML=badge(p.prediction);
  document.getElementById("selected-cycle-caption").textContent=`Prediction at cycle ${number(p.cycle)}${state.index===e.cycles.length-1?" · Last observation":" · Historical replay"}`;
  document.getElementById("replay-cycle").innerHTML=`Cycle ${number(p.cycle)} <span>/ ${number(last)}</span>`;
  const slider=document.getElementById("cycle-slider");slider.value=state.index;slider.setAttribute("aria-valuetext",`Cycle ${number(p.cycle)} of ${number(last)}`);
  const truthValue=document.getElementById("truth-value");
  if(truthValue){truthValue.hidden=!state.showTruth;truthValue.innerHTML=`<span>Actual remaining life</span><strong>${number(p.truth)} cycles</strong>`;}
  document.getElementById("truth-legend").hidden=!state.showTruth;
  document.getElementById("sensitivity-terminal").textContent=state.index===e.cycles.length-1?`Sensitivity calculated at terminal cycle ${number(last)}.`:`Replaying cycle ${number(p.cycle)}. Sensitivity remains for terminal cycle ${number(last)}; it does not change with replay.`;
  const series=[{label:"Prediction",values:e.predictions||[],color:"#335dd5"}];
  if(state.showTruth && e.true_rul)series.push({label:"Benchmark truth",values:e.true_rul,color:"#228c81"});
  drawChart("rul-chart",{cycles:e.cycles,series,lower:e.lower,upper:e.upper,selected:state.index,yLabel:"Remaining life / cycles",unit:"cycles",minZero:true});
  const sensor=e.sensors?.find(s=>s.id===state.sensorId);
  if(sensor){drawChart("sensor-chart",{cycles:e.cycles,series:[{label:sensor.label||sensor.id,values:sensor.values,color:"#228c81"}],selected:state.index,yLabel:sensor.unit?`${sensor.label||sensor.id} / ${sensor.unit}`:"Raw sensor value",unit:sensor.unit||"raw units",height:220});document.getElementById("sensor-note").textContent=`${sensor.label||sensor.id} · ${sensor.id.replace(/_/g," ")} · NASA raw measurements${sensor.unit?` (${sensor.unit})`:"; units depend on the selected sensor"}. Vertical marker indicates the selected replay cycle.`;}
  else document.getElementById("sensor-chart").innerHTML='<div class="empty-state">No sensor readings are available.</div>';
}

function drawChart(containerId, options) {
  const container=document.getElementById(containerId);if(!container)return;
  const {cycles,series,lower,upper,selected,yLabel,unit}=options;
  const width=730,height=options.height||275,left=57,right=22,top=16,bottom=39;
  const pw=width-left-right,ph=height-top-bottom;
  const all=[...series.flatMap(s=>s.values),...(lower||[]),...(upper||[])].filter(finite);
  if(!all.length){container.innerHTML='<div class="empty-state">Predictions become available after the initial feature window.</div>';return;}
  let min=options.minZero?0:Math.min(...all),max=Math.max(...all);if(min===max){min-=1;max+=1;}const pad=(max-min)*.08;if(!options.minZero)min-=pad;max+=pad;
  const minCycle=cycles[0],maxCycle=cycles[cycles.length-1];
  const x=c=>left+((c-minCycle)/Math.max(1,maxCycle-minCycle))*pw;
  const y=v=>top+ph-(v-min)/(max-min)*ph;
  const path=values=>{let active=false;return values.map((v,i)=>{if(!finite(v)){active=false;return "";}const part=`${active?"L":"M"}${x(cycles[i]).toFixed(2)},${y(v).toFixed(2)}`;active=true;return part;}).join(" ");};
  let band="";
  if(lower&&upper){const usable=cycles.map((cycle,i)=>({cycle,low:lower[i],high:upper[i]})).filter(p=>finite(p.low)&&finite(p.high));if(usable.length)band=`<path d="${usable.map((p,i)=>`${i?"L":"M"}${x(p.cycle).toFixed(2)},${y(p.high).toFixed(2)}`).join(" ")} ${[...usable].reverse().map(p=>`L${x(p.cycle).toFixed(2)},${y(p.low).toFixed(2)}`).join(" ")}Z" fill="#e9eeff"/>`;}
  let grid="";
  for(let i=0;i<=4;i++){const value=min+(max-min)*i/4;grid+=`<line class="grid-line" x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis-text" x="${left-10}" y="${y(value)+3}" text-anchor="end">${number(value,max-min<3?1:0)}</text>`;}
  for(let i=0;i<=4;i++){const cycle=Math.round(minCycle+(maxCycle-minCycle)*i/4);grid+=`<text class="axis-text" x="${x(cycle)}" y="${height-20}" text-anchor="middle">${number(cycle)}</text>`;}
  const selectedCycle=cycles[selected];
  const dots=series.filter(s=>finite(s.values[selected])).map(s=>`<circle cx="${x(selectedCycle)}" cy="${y(s.values[selected])}" r="3.2" fill="#fff" stroke="${s.color}" stroke-width="2"/>`).join("");
  container.innerHTML=`<svg class="plot-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escaped(yLabel)} over observed operating cycles. Current cycle ${number(selectedCycle)}."><text class="axis-title" x="${left}" y="9">${escaped(yLabel)}</text>${grid}${band}${series.map(s=>`<path class="line-curve" d="${path(s.values)}" stroke="${s.color}"/>`).join("")}<line class="selection-line" x1="${x(selectedCycle)}" x2="${x(selectedCycle)}" y1="${top}" y2="${height-bottom}"/>${dots}<text class="axis-title" x="${left+pw/2}" y="${height-1}" text-anchor="middle">Observed operating cycle</text><rect class="chart-hit" x="${left}" y="${top}" width="${pw}" height="${ph}"/></svg><div class="chart-tooltip" hidden></div>`;
  const hit=container.querySelector(".chart-hit"),tooltip=container.querySelector(".chart-tooltip"),svg=container.querySelector("svg");
  hit.addEventListener("pointermove",event=>{
    const rect=svg.getBoundingClientRect();const pointerX=(event.clientX-rect.left)*width/rect.width;
    const target=minCycle+(pointerX-left)/pw*(maxCycle-minCycle);
    let idx=0;for(let i=1;i<cycles.length;i++)if(Math.abs(cycles[i]-target)<Math.abs(cycles[idx]-target))idx=i;
    tooltip.innerHTML=`<strong>Observed cycle ${number(cycles[idx])}</strong>${series.map(s=>`<div><span class="swatch" style="background:${s.color}"></span>${escaped(s.label)}<span class="tooltip-value">${number(s.values[idx],1)} ${escaped(unit)}</span></div>`).join("")}${lower&&upper?`<div><span class="swatch band"></span>90% interval<span class="tooltip-value">${number(lower[idx],1)}–${number(upper[idx],1)}</span></div>`:""}`;
    tooltip.hidden=false;const localX=event.clientX-container.getBoundingClientRect().left;tooltip.style.left=`${Math.max(6,Math.min(localX+12,container.clientWidth-tooltip.offsetWidth-6))}px`;tooltip.style.top=`${Math.max(15,(event.clientY-container.getBoundingClientRect().top)-tooltip.offsetHeight-12)}px`;
  });
  hit.addEventListener("pointerleave",()=>{tooltip.hidden=true;});
}

function renderBenchmark() {
  const s=summary(),selected=s.selected_model,items=metrics(),interval=s.interval||{},split=s.split||{};
  const maxRmse=Math.max(1,...items.map(item=>metricValue(item,"rmse")).filter(finite));
  const nasaWinner=[...items].filter(item=>finite(metricValue(item,"nasa_score"))).sort((a,b)=>metricValue(a,"nasa_score")-metricValue(b,"nasa_score"))[0];
  const covered=Math.max(0,Math.min(1,interval.test_coverage||0));
  const circumference=2*Math.PI*59;
  view.innerHTML=`<div class="page-heading"><div><span class="eyebrow">MEASURED ON UNSEEN ENGINES</span><h1>Model benchmark</h1><p>Actual terminal-cycle test results. Lower prediction errors are better.</p></div><a class="button secondary" href="#methodology">${icon("book")} Evaluation method</a></div><div class="metric-grid">${metricCard("Selected model RMSE",number(metricValue(selectedMetric(),"rmse"),2),"cycles","Penalizes larger prediction errors","bars")}${metricCard("Selected model MAE",number(metricValue(selectedMetric(),"mae"),2),"cycles","Mean absolute prediction error","activity")}${metricCard("NASA score",number(metricValue(selectedMetric(),"nasa_score"),1),"score","Late predictions receive a larger penalty","shield")}${metricCard("Observed interval coverage",percent(interval.test_coverage,1),"of engines",`Nominal target: ${percent(interval.nominal_coverage||.9)}`,"check")}</div><div class="benchmark-grid"><div class="section-stack"><section class="panel"><div class="panel-header"><div><h2>Model comparison</h2><p>${number(s.test_engines)} test engines · last available observation per engine</p></div><span class="tiny-tag">HELD-OUT TEST</span></div><div class="table-scroll"><table class="benchmark-table"><thead><tr><th scope="col">MODEL</th><th scope="col">MAE / CYCLES</th><th scope="col">RMSE / CYCLES</th><th scope="col">NASA SCORE</th></tr></thead><tbody>${items.map(item=>`<tr class="${item.model===selected?"selected-model":""}"><td>${escaped(modelName(item.model))}${item.model===selected?'<span class="model-tag">SELECTED</span>':""}</td><td>${number(metricValue(item,"mae"),2)}</td><td>${number(metricValue(item,"rmse"),2)}</td><td>${number(metricValue(item,"nasa_score"),1)}</td></tr>`).join("")}</tbody></table></div><p class="benchmark-note">The selected model was chosen using validation MAE. ${escaped(modelName(nasaWinner?.model))} has the lowest NASA score on this test set; selection does not optimize that metric. Test engines do not determine training, calibration, or model selection.</p></section><section class="panel"><div class="panel-header"><div><h2>Prediction error, in perspective</h2><p>Root mean squared error · operating cycles</p></div><span class="tiny-tag">LOWER IS BETTER</span></div><div class="comparison-chart" role="img" aria-label="Model RMSE comparison: ${items.map(item=>`${modelName(item.model)} ${number(metricValue(item,"rmse"),2)} cycles`).join("; ")}">${items.map(item=>`<div class="comparison-row"><span title="${escaped(modelName(item.model))}">${escaped(modelName(item.model))}</span><div class="comparison-track"><i class="${item.model===selected?"selected":""}" style="width:${(metricValue(item,"rmse")||0)/maxRmse*100}%"></i></div><strong>${number(metricValue(item,"rmse"),1)}</strong></div>`).join("")}</div></section></div><aside class="side-stack benchmark-aside"><section class="panel coverage-panel"><h2>Uncertainty, checked</h2><div class="coverage-ring" role="img" aria-label="${percent(interval.test_coverage,1)} observed interval coverage"><svg viewBox="0 0 143 143" aria-hidden="true"><circle class="ring-base" cx="71.5" cy="71.5" r="59"/><circle class="ring-value" cx="71.5" cy="71.5" r="59" stroke-dasharray="${circumference}" stroke-dashoffset="${circumference*(1-covered)}"/></svg><div class="ring-text"><strong>${percent(interval.test_coverage,1)}</strong><span>ACTUAL TEST COVERAGE</span></div></div><div class="coverage-stats"><div><span>Nominal coverage</span><strong>${percent(interval.nominal_coverage||.9)}</strong></div><div><span>Mean interval width</span><strong>${number(interval.mean_width,1)} cycles</strong></div><div><span>Calibration engines</span><strong>${number(interval.calibration_engines)}</strong></div></div><p>Intervals are calibrated on separate engines. Terminal test coverage is an observed result; the nominal 90% level is not a promise of coverage at every historical cycle or on other operating regimes.</p><p>${escaped(interval.distribution_shift_note || "Calibration and test endpoints can follow different truncation patterns.")}</p></section><section class="panel split-panel"><h2>Independent engine splits</h2><div class="split-track" aria-hidden="true"><i style="flex:${split.fit||0}"></i><i style="flex:${split.validation||0}"></i><i style="flex:${split.calibration||0}"></i></div><div class="split-legend"><div><strong>${number(split.fit)}</strong>Fit</div><div><strong>${number(split.validation)}</strong>Validation</div><div><strong>${number(split.calibration)}</strong>Calibration</div></div><p>Each engine belongs to one development split. The ${number(s.test_engines)} official test engines remain separate throughout development.</p></section></aside></div><div class="source-strip">${icon("info")}<p><strong>How to read the NASA score.</strong> Errors are summed across engines with an asymmetric exponential penalty. Overestimating remaining life is penalized more strongly than underestimating it. Scores depend on the test set size and should be compared on the same benchmark.</p></div>`;
}

function renderMethodology() {
  const s=summary();
  view.innerHTML=`<div class="page-heading"><div><span class="eyebrow">TRANSPARENT BY DESIGN</span><h1>Inside EngineWatch</h1><p>The data, the model, and the limits of this demonstration.</p></div><button class="button secondary" data-action="upload">${icon("upload")} Try your data</button></div><div class="methodology-layout"><div class="section-stack"><section class="panel method-card"><span class="eyebrow">01 / THE BENCHMARK</span><h2>A simulated journey to engine failure</h2><p>NASA C-MAPSS generates turbofan engine sensor readings under simulated degradation. FD001 contains one operating condition and one fault mode. Its training engines run to failure; its test histories stop earlier, with the true remaining life supplied separately for evaluation.</p><p>EngineWatch estimates the number of operating cycles from the current observation to the simulated failure point. A cycle is one recorded operating step, not an hour or a flight.</p><div class="pipeline"><div class="pipeline-step"><span>01 / INGEST</span><h3>Validate each engine</h3><p>Check all operating settings and sensors, finite values, unique rows, and consecutive cycles.</p></div><div class="pipeline-step"><span>02 / WINDOW</span><h3>Describe the recent past</h3><p>Use sensor levels and trends over up to ${number(s.window)} recent cycles. Early readings use shorter windows; future readings never enter a prediction.</p></div><div class="pipeline-step"><span>03 / PREDICT</span><h3>Compare candidate models</h3><p>Fit on separate engines and select the model using validation results.</p></div><div class="pipeline-step"><span>04 / CALIBRATE</span><h3>Add an uncertainty range</h3><p>Use a separate calibration split before evaluating the official test engines.</p></div></div></section><section class="panel method-card"><span class="eyebrow">02 / A CREDIBLE EVALUATION</span><h2>Separate engines. Separate decisions.</h2><ul class="method-list"><li><strong>Split by engine, not by row.</strong> Related cycles from the same engine cannot appear on both sides of a development split.</li><li><strong>Use only the past.</strong> Rolling features use the current and previous readings. The demonstration does not give the model future observations.</li><li><strong>Evaluate terminal predictions.</strong> The headline errors and interval coverage use one prediction per official test engine at its final observed cycle.</li><li><strong>Report actual uncertainty coverage.</strong> A nominal 90% prediction band is calibrated independently. Historical replay and uploaded data can differ from the terminal calibration regime.</li><li><strong>Keep the target uncapped.</strong> Results describe estimated operating cycles to failure; the display does not replace longer lifetimes with an artificial ceiling.</li></ul></section><section class="panel method-card"><span class="eyebrow">03 / USING THE EXPLORER</span><h2>Read the evidence, with its limits</h2><ul class="method-list"><li><strong>Replay:</strong> the slider selects an observed cycle. The blue line shows predicted remaining life; the shaded band is its nominal 90% interval.</li><li><strong>Benchmark truth:</strong> hidden by default, and available only when a known simulated outcome exists. Revealing it helps inspect prediction errors.</li><li><strong>Sensor substitution:</strong> the sensitivity panel replaces one terminal sensor’s feature group with training medians and measures the change in model output. Positive values mean the replacement increases predicted life. It is not a causal attribution or a diagnosis.</li><li><strong>Horizon buckets:</strong> “Review” (≤30 cycles), “Watch” (31–80), and “Horizon” (>80) organize the demo. They are illustrative display thresholds, not validated maintenance decisions.</li><li><strong>Scope:</strong> this model learns from simulated FD001 engines. Its measured results do not establish accuracy on real engines, other fault modes, or other operating conditions.</li></ul></section><section class="panel method-card"><span class="eyebrow">04 / TRY YOUR OWN HISTORY</span><h2>A strict, reproducible input format</h2><p>Upload one engine as NASA whitespace-separated text, or a CSV using the canonical columns shown below. Supply all 21 sensors and all three operating settings, with finite numbers. Cycles must be chronological and consecutive, starting at 1. ${number(s.window)} or more cycles are recommended. Shorter histories are accepted with a warning; files are limited to 1.9 MB and 5,000 rows.</p><div class="api-box">engine_id,cycle,setting_1,setting_2,setting_3,<br>sensor_1,sensor_2,…,sensor_21</div><p><a href="/api/sample" download="enginewatch-sample.csv">Download the sample CSV →</a> The result opens in the same explorer and can be exported as prediction JSON or CSV. Uploaded histories have no known remaining-life ground truth.</p></section></div><aside class="side-stack methodology-aside"><section class="panel technical-specs"><h2>Project at a glance</h2><div><span>Dataset</span><strong>NASA FD001</strong></div><div><span>Training engines</span><strong>${number(s.train_engines)}</strong></div><div><span>Test engines</span><strong>${number(s.test_engines)}</strong></div><div><span>Feature window</span><strong>${number(s.window)} cycles</strong></div><div><span>Engineered features</span><strong>${number(s.feature_count)}</strong></div><div><span>Selected model</span><strong>${escaped(modelName(s.selected_model))}</strong></div><div><span>Interval target</span><strong>${percent(s.interval?.nominal_coverage||.9)}</strong></div></section><section class="panel reference-panel"><h2>Go to the source</h2><a href="https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data" target="_blank" rel="noopener">NASA benchmark description <span>↗</span></a><a href="https://zenodo.org/records/15346912" target="_blank" rel="noopener">C-MAPSS dataset archive <span>↗</span></a><a href="#benchmark">Measured model results <span>→</span></a><a href="/api/sample" download="enginewatch-sample.csv">Sample input CSV <span>↓</span></a><p>Source code, reproducible training, evaluation artifacts, and the project write-up accompany this application in the EngineWatch repository.</p></section></aside></div>`;
}

function togglePlayback() {
  const button=document.getElementById("play-button");
  if(state.playback){stopPlayback();button.innerHTML=icon("play");button.setAttribute("aria-label","Play engine history");return;}
  if(state.index>=state.engine.cycles.length-1)state.index=0;
  button.innerHTML=icon("pause");button.setAttribute("aria-label","Pause engine history");updateEngine();
  state.playback=setInterval(()=>{if(state.index>=state.engine.cycles.length-1){stopPlayback();button.innerHTML=icon("play");button.setAttribute("aria-label","Play engine history");return;}state.index++;updateEngine();},220);
}

function openUpload() {
  stopPlayback();
  const playButton=document.getElementById("play-button");if(playButton){playButton.innerHTML=icon("play");playButton.setAttribute("aria-label","Play engine history");}
  document.getElementById("upload-error").hidden=true;
  dialog.showModal();
}
document.querySelectorAll("[data-upload]").forEach(button=>button.addEventListener("click",openUpload));
document.getElementById("help-button").addEventListener("click",()=>{location.hash="methodology";});
document.getElementById("close-upload").addEventListener("click",()=>dialog.close());
document.getElementById("cancel-upload").addEventListener("click",()=>dialog.close());
dialog.addEventListener("click",event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
document.getElementById("upload-file").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file)return;
  const error=document.getElementById("upload-error");
  if(file.size>1900000){error.textContent="Choose a file smaller than 1.9 MB.";error.hidden=false;return;}
  try{document.getElementById("upload-text").value=await file.text();document.getElementById("file-label").textContent=file.name;error.hidden=true;}
  catch{error.textContent="The file could not be read. Try pasting the readings instead.";error.hidden=false;}
});
document.getElementById("upload-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const error=document.getElementById("upload-error"),button=document.getElementById("predict-button"),text=document.getElementById("upload-text").value.trim();
  if(!text){error.textContent="Choose a file or paste an engine history first.";error.hidden=false;document.getElementById("upload-text").focus();return;}
  if(new Blob([text]).size>1900000){error.textContent="The engine history exceeds the 1.9 MB upload limit.";error.hidden=false;return;}
  button.disabled=true;button.innerHTML='Generating prediction…';error.hidden=true;
  try{
    const result=await api("/api/predict",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    if(!Array.isArray(result.cycles)||!result.cycles.length)throw new Error("The engine history was accepted but no predictions were returned.");
    ++state.requestToken;stopPlayback();state.engine={...result,uploaded:true};state.index=result.cycles.length-1;state.sensorId=result.sensors?.[0]?.id;state.showTruth=false;dialog.close();
    if(location.hash==="#engine/uploaded"){setNavigation("engine");renderEngine();}else location.hash="engine/uploaded";
    toast("Your engine history is ready to explore.");
  }catch(err){error.textContent=err.message;error.hidden=false;}
  finally{button.disabled=false;button.innerHTML=`${icon("activity")} Generate prediction`;}
});

function exportPrediction(format) {
  const e=state.engine;if(!e)return;
  const rows=e.cycles.map((cycle,i)=>({id:e.id,cycle,predicted_rul:e.predictions?.[i]??null,lower_rul:e.lower?.[i]??null,upper_rul:e.upper?.[i]??null,...(state.showTruth&&e.true_rul?{true_rul:e.true_rul[i]??null}:{})}));
  let content,type;
  if(format==="json"){content=JSON.stringify({engine_id:e.id,dataset:e.uploaded?"Uploaded history":"NASA C-MAPSS FD001",model:summary().selected_model,nominal_interval_coverage:summary().interval?.nominal_coverage||.9,units:"operating cycles",predictions:rows},null,2);type="application/json";}
  else{const keys=Object.keys(rows[0]);const csvValue=value=>{const text=String(value??"");return /[,"\r\n]/.test(text)?`"${text.replace(/"/g,'""')}"`:text;};content=keys.join(",")+"\n"+rows.map(row=>keys.map(key=>csvValue(row[key])).join(",")).join("\n")+"\n";type="text/csv";}
  const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement("a");a.href=url;a.download=`engine-${String(e.id).replace(/[^\w-]/g,"_")}-predictions.${format}`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(`Prediction ${format.toUpperCase()} downloaded.`);
}

view.addEventListener("click",event=>{
  const target=event.target.closest("[data-action]");if(!target)return;
  const action=target.dataset.action;
  if(action==="retry"){view.innerHTML='<div class="initial-loading"><div class="loading-ring"></div><p>Loading the engine fleet…</p></div>';boot();}
  else if(action==="upload")openUpload();
  else if(action==="engine")location.hash=`engine/${encodeURIComponent(target.dataset.id)}`;
  else if(action==="prev-page"){state.fleetPage=Math.max(0,state.fleetPage-1);renderFleetRows();}
  else if(action==="next-page"){state.fleetPage++;renderFleetRows();}
  else if(action==="play")togglePlayback();
  else if(action==="terminal"){stopPlayback();state.index=state.engine.cycles.length-1;document.getElementById("play-button").innerHTML=icon("play");document.getElementById("play-button").setAttribute("aria-label","Play engine history");updateEngine();}
  else if(action==="export-json")exportPrediction("json");
  else if(action==="export-csv")exportPrediction("csv");
});
view.addEventListener("input",event=>{
  if(event.target.id==="fleet-search"){state.search=event.target.value;state.fleetPage=0;renderFleetRows();}
  else if(event.target.id==="cycle-slider"){stopPlayback();state.index=Number(event.target.value);document.getElementById("play-button").innerHTML=icon("play");document.getElementById("play-button").setAttribute("aria-label","Play engine history");updateEngine();}
});
view.addEventListener("change",event=>{
  if(event.target.id==="fleet-filter"){state.filter=event.target.value;state.fleetPage=0;renderFleetRows();}
  else if(event.target.id==="fleet-sort"){state.sort=event.target.value;state.fleetPage=0;renderFleetRows();}
  else if(event.target.id==="sensor-select"){state.sensorId=event.target.value;updateEngine();}
  else if(event.target.id==="show-truth"){state.showTruth=event.target.checked;updateEngine();}
});
document.addEventListener("visibilitychange",()=>{if(document.hidden){stopPlayback();const button=document.getElementById("play-button");if(button){button.innerHTML=icon("play");button.setAttribute("aria-label","Play engine history");}}});
boot();
