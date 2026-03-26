// ── Water Ripple ──────────────────────────────────────────────
const canvas = document.getElementById('ripple-canvas');
const ctx    = canvas.getContext('2d');
let ripples  = [];

function resizeCanvas() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

document.addEventListener('click', e => {
  ripples.push({ x:e.clientX, y:e.clientY, r:0, max:100, alpha:.35 });
});
document.addEventListener('mousemove', e => {
  if (Math.random() < .03)
    ripples.push({ x:e.clientX, y:e.clientY, r:0, max:35, alpha:.12 });
});

(function animateRipples() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ripples = ripples.filter(r => r.alpha > .01);
  ripples.forEach(r => {
    ctx.beginPath(); ctx.arc(r.x, r.y, r.r, 0, Math.PI*2);
    ctx.strokeStyle = `rgba(162,155,254,${r.alpha})`;
    ctx.lineWidth = 1.2; ctx.stroke();
    r.r    += (r.max - r.r) * .06;
    r.alpha *= .92;
  });
  requestAnimationFrame(animateRipples);
})();

// Btn ripple
document.addEventListener('click', e => {
  const btn = e.target.closest('.btn');
  if (!btn || btn.disabled) return;
  const rect = btn.getBoundingClientRect();
  const r    = document.createElement('div');
  r.className = 'btn-ripple';
  r.style.left = (e.clientX - rect.left) + 'px';
  r.style.top  = (e.clientY - rect.top)  + 'px';
  btn.appendChild(r); setTimeout(() => r.remove(), 600);
});

// ── State ─────────────────────────────────────────────────────
let selectedFile  = null;
let historyItems  = [];
let allModels     = [];
let pollTimers    = {};
let currentFilter = 'all';
let scaleTimer    = null;
let scaleElapsed  = 0;

// ── Log Terminal ──────────────────────────────────────────────
function logMsg(msg, type = 'info') {
  const wrap = document.getElementById('log-wrap');
  const body = document.getElementById('log-body');
  wrap.classList.add('visible');
  const t = new Date();
  const ts = [t.getHours(), t.getMinutes(), t.getSeconds()]
    .map(n => String(n).padStart(2,'0')).join(':');
  const typeLabel = { ok:'[OK] ', info:'[--] ', err:'[!!] ', warn:'[^^] ' }[type] || '[--] ';
  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML =
    `<span class="log-time">${ts}</span>` +
    `<span class="log-type log-${type}">${typeLabel}</span>` +
    `<span class="log-msg">${msg}</span>`;
  body.appendChild(line);
  while (body.children.length > 50) body.removeChild(body.firstChild);
  body.scrollTop = body.scrollHeight;
}

function logStatus(active, title) {
  document.getElementById('log-dot').className    = `log-dot ${active?'active':'idle'}`;
  document.getElementById('log-title-text').textContent = title;
}

function logProgress(pct) {
  const bar  = document.getElementById('log-progress');
  const fill = document.getElementById('log-progress-fill');
  if (pct === null) { bar.classList.remove('visible'); return; }
  bar.classList.add('visible'); fill.style.width = pct + '%';
}

// ── Elapsed Timer ─────────────────────────────────────────────
function startElapsed() {
  scaleElapsed = 0;
  const el = document.getElementById('log-elapsed');
  clearInterval(scaleTimer);
  scaleTimer = setInterval(() => {
    scaleElapsed++;
    el.textContent = `${scaleElapsed}s`;
    // Sau 10s cảnh báo đang xử lý
    if (scaleElapsed === 10) logMsg('Đang xử lý... máy ARM có thể mất 30-60s', 'warn');
    if (scaleElapsed === 30) logMsg('Vẫn đang chạy — inference ONNX trên CPU ARM chậm hơn x86', 'warn');
  }, 1000);
}
function stopElapsed() {
  clearInterval(scaleTimer);
  document.getElementById('log-elapsed').textContent = '';
}

// ── Pages ─────────────────────────────────────────────────────
function showPage(name, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  el.classList.add('active');
  if (name === 'settings') loadSettingsModels();
}

function switchTab(name, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('scale-controls').style.display = name==='scale' ? 'flex' : 'none';
  document.getElementById('gen-wrap').classList.toggle('visible', name==='generate');
}

// ── System Stats (realtime) ───────────────────────────────────
async function loadSystem() {
  try {
    const d = await fetch('/api/system').then(r => r.json());

    // CPU gauge
    const cpuPct = Math.max(d.cpu_percent, 1); document.getElementById('gauge-cpu-fill').style.width = cpuPct + '%';
    document.getElementById('gauge-cpu-val').textContent   = d.cpu_percent.toFixed(0) + '%';

    // RAM gauge
    document.getElementById('gauge-ram-fill').style.width  = d.ram_percent + '%';
    document.getElementById('gauge-ram-val').textContent   =
      `${d.ram_used_mb}/${d.ram_total_mb}MB`;

    // Disk gauge
    document.getElementById('gauge-disk-fill').style.width = d.disk_percent + '%';
    document.getElementById('gauge-disk-val').textContent  =
      `${d.disk_used_gb}/${d.disk_total_gb}GB`;

    // Header RAM
    document.getElementById('hdr-ram').textContent = d.ram_free_mb;
  } catch(e) {}
}

async function loadStatus() {
  try {
    const d = await fetch('/api/status').then(r => r.json());
    document.getElementById('hdr-platform').textContent   = d.platform.toUpperCase();
    document.getElementById('hdr-score').textContent      = d.tpixel_score;
    document.getElementById('score-ring-val').textContent = d.tpixel_score;

    const circ = 2 * Math.PI * 22;
    const ring = document.getElementById('score-ring-fill');
    ring.style.strokeDasharray  = circ;
    ring.style.strokeDashoffset = circ - circ * (d.tpixel_score/100);
    ring.style.stroke = d.tpixel_score >= 60 ? 'var(--cyan)'
                      : d.tpixel_score >= 40 ? 'var(--yellow)' : 'var(--red)';

    document.getElementById('sd-cpu').textContent  = d.cpu_count + ' cores';
    document.getElementById('sd-arch').textContent = d.architecture || '--';
    if (d.active_model)
      document.getElementById('active-model-info').textContent = d.active_model;
  } catch(e) {}
}

async function loadBenchDetail() {
  try {
    const d = await fetch('/api/benchmark').then(r => r.json());
    const cpuEl   = document.getElementById('sd-cpu');
    const archEl  = document.getElementById('sd-arch');
    if (cpuEl)  cpuEl.textContent  = (d.cpu_score || '?') + ' MB/s · ' + (d.cpu_count || '?') + ' cores';
    if (archEl) archEl.textContent = d.architecture || '--';
  } catch(e) { console.error('benchmark err:', e); }
}

// ── Downloaded Sidebar ────────────────────────────────────────
async function loadDownloadedSidebar() {
  const models = await fetch('/api/models').then(r => r.json());
  allModels = models;
  const dl   = models.filter(m => m.downloaded);
  const list = document.getElementById('downloaded-list');
  if (!dl.length) {
    list.innerHTML = '<div style="font-size:.7rem;color:var(--muted)">Vào Settings để tải model</div>';
    return;
  }
  list.innerHTML = '';
  dl.forEach(m => {
    const div = document.createElement('div');
    div.className = 'model-card'; div.dataset.id = m.id;
    div.innerHTML = `<div class="mc-name">${m.name}</div>
                     <div class="mc-meta">${m.task} · ${m.size_mb}MB</div>`;
    div.onclick = () => selectModel(m.id, div);
    list.appendChild(div);
  });
}

async function selectModel(id, el) {
  await fetch('/api/models/select', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ model_id: id })
  });
  document.querySelectorAll('.model-card').forEach(c => c.classList.remove('active-model'));
  el.classList.add('active-model');
  document.getElementById('active-model-info').textContent = id;
  logMsg(`Model selected: ${id}`, 'ok'); toast(`◈ ${id}`);
}

// ── Drop Zone ─────────────────────────────────────────────────
const dz = document.getElementById('drop-zone');
const fi = document.getElementById('file-input');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('drag-over'); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });
fi.addEventListener('change', () => { if (fi.files[0]) setFile(fi.files[0]); });

function setFile(file) {
  selectedFile = file;
  const url = URL.createObjectURL(file);
  dz.style.display = 'none';
  document.getElementById('compare-row').classList.add('visible');
  const before = document.getElementById('img-before');
  before.onload = () => {
    before.classList.add('loaded');
    document.getElementById('size-before').textContent =
      `${before.naturalWidth}×${before.naturalHeight}`;
  };
  before.src = url;
  const after = document.getElementById('img-after');
  after.src = ''; after.classList.remove('loaded');
  document.getElementById('size-after').textContent = '--';
  document.getElementById('btn-scale').disabled = false;
  logMsg(`Loaded: ${file.name} · ${(file.size/1024).toFixed(0)}KB`, 'info');
  toast(`◈ ${file.name}`);
}

// ── Scale ─────────────────────────────────────────────────────
async function doScale() {
  if (!selectedFile) return;
  const factor = document.getElementById('factor-select').value;
  const method = document.getElementById('method-select').value;
  const btn    = document.getElementById('btn-scale');
  const fa     = document.getElementById('frame-after');
  const skel   = document.getElementById('skeleton-after');
  const after  = document.getElementById('img-after');
  const timer  = document.getElementById('frame-timer');

  btn.disabled = true;
  fa.classList.add('processing');
  skel.style.display = 'block';
  after.classList.remove('loaded'); after.src = '';
  document.getElementById('size-after').textContent = 'Processing...';
  timer.classList.add('visible');

  logStatus(true, 'SCALE / PROCESSING');
  logMsg(`Scale ${factor}x · method: ${method}`, 'info');
  logProgress(10);
  startElapsed();

  const form = new FormData(); form.append('file', selectedFile);
  try {
    logProgress(30);
    const resp = await fetch(`/api/scale?factor=${factor}&method=${method}`, { method:'POST', body:form });
    logProgress(80);
    if (!resp.ok) throw new Error((await resp.json()).detail);

    const blob = await resp.blob();
    const info = resp.headers.get('X-Scale-Info') || '';
    const url  = URL.createObjectURL(blob);
    const bmp  = await createImageBitmap(blob);
    const ow = bmp.width, oh = bmp.height; bmp.close();
    const iw = document.getElementById('img-before').naturalWidth;
    const ih = document.getElementById('img-before').naturalHeight;

    skel.style.display = 'none';
    after.onload = () => after.classList.add('loaded');
    after.src = url;
    document.getElementById('size-after').textContent = `${ow}×${oh}`;

    logProgress(100);
    logMsg(`Done in ${scaleElapsed}s: ${iw}×${ih} → ${ow}×${oh} | ${info}`, 'ok');
    setTimeout(() => logProgress(null), 1200);
    addHistory(url, `${method}_${factor}x`);
    toast(`✓ ${iw}×${ih} → ${ow}×${oh} · ${scaleElapsed}s`);
  } catch(err) {
    skel.style.display = 'none';
    logMsg(`Error: ${err.message}`, 'err');
    document.getElementById('size-after').textContent = 'ERROR';
    toast('✗ ' + err.message, true);
  } finally {
    btn.disabled = false;
    fa.classList.remove('processing');
    timer.classList.remove('visible');
    logStatus(false, 'READY');
    stopElapsed();
  }
}

// ── Generate với fake progress ────────────────────────────────
let genProgressInterval = null;

function startGenProgress() {
  const wrap = document.getElementById('gen-progress-wrap');
  const fill = document.getElementById('gen-progress-fill');
  const pct  = document.getElementById('gen-progress-pct');
  const lbl  = document.getElementById('gen-progress-label');
  wrap.classList.add('visible');
  let current = 0;
  const steps = [
    [5, 'Initializing model...'],
    [20, 'Encoding prompt...'],
    [40, 'Generating latents...'],
    [65, 'Diffusion steps...'],
    [80, 'Decoding image...'],
    [92, 'Post-processing...'],
  ];
  let si = 0;
  genProgressInterval = setInterval(() => {
    if (si < steps.length && current >= steps[si][0]) {
      lbl.textContent = steps[si][1];
      logMsg(steps[si][1], 'info');
      si++;
    }
    current = Math.min(current + .5, 92);
    fill.style.width = current + '%';
    pct.textContent  = current.toFixed(0) + '%';
  }, 200);
}

function stopGenProgress(success) {
  clearInterval(genProgressInterval);
  const fill = document.getElementById('gen-progress-fill');
  const pct  = document.getElementById('gen-progress-pct');
  const wrap = document.getElementById('gen-progress-wrap');
  if (success) {
    fill.style.width = '100%'; pct.textContent = '100%';
    setTimeout(() => wrap.classList.remove('visible'), 1500);
  } else {
    wrap.classList.remove('visible');
  }
}

async function doGenerate() {
  const prompt = document.getElementById('prompt-input').value.trim();
  if (!prompt) { toast('Nhập prompt trước', true); return; }

  logStatus(true, 'GENERATE / RUNNING');
  startGenProgress(); startElapsed();

  const resp = await fetch('/api/generate', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ prompt })
  });

  stopElapsed();
  if (!resp.ok) {
    const err = await resp.json();
    stopGenProgress(false);
    logMsg('Error: ' + err.detail, 'err');
    logStatus(false, 'READY'); toast('✗ ' + err.detail, true); return;
  }

  const blob = await resp.blob();
  const url  = URL.createObjectURL(blob);
  const img  = document.getElementById('gen-img');
  img.onload = () => img.classList.add('loaded');
  img.src = url;
  document.getElementById('gen-result').classList.add('visible');
  stopGenProgress(true);
  logMsg(`Generate done · ${scaleElapsed}s`, 'ok');
  logStatus(false, 'READY');
  addHistory(url, 'gen'); toast(`✓ Generate xong · ${scaleElapsed}s`);
}

// ── History ───────────────────────────────────────────────────
function addHistory(url, label) {
  historyItems.push({ url, label });
  const grid = document.getElementById('history-grid');
  if (historyItems.length === 1) grid.innerHTML = '';
  const item = document.createElement('div');
  item.className = 'history-item';
  item.innerHTML = `<img src="${url}">
    <div class="history-dl" onclick="dlImg('${url}','${label}')">↓ TẢI VỀ</div>`;
  grid.prepend(item);
  document.getElementById('btn-dl-all').style.display = 'block';
}
function dlImg(url, label) {
  const a = document.createElement('a'); a.href=url; a.download=`tpixel_${label}_${Date.now()}.png`; a.click();
}
function downloadAll() {
  historyItems.forEach((h,i) => setTimeout(() => dlImg(h.url,h.label), i*300));
  toast(`↓ Tải ${historyItems.length} ảnh`);
}

// ── Settings ──────────────────────────────────────────────────
async function loadSettingsModels() {
  const models = await fetch('/api/models').then(r => r.json());
  allModels = models; renderSettingsModels();
}
function filterModels(task, el) {
  currentFilter = task;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active'); renderSettingsModels();
}
function renderSettingsModels() {
  const list = currentFilter==='all' ? allModels : allModels.filter(m => m.task===currentFilter);
  const con  = document.getElementById('settings-model-list');
  con.innerHTML = '';
  list.forEach((m,i) => {
    const isDl  = m.downloaded;
    const isRun = m.progress?.status === 'downloading';
    const lblMap = { optimal:'badge-opt', ok:'badge-ok', slow:'badge-slow' };
    const row = document.createElement('div');
    row.className = 'model-row'; row.id = `row-${m.id}`;
    row.style.animationDelay = (i*40)+'ms';
    row.innerHTML = `
      <div>
        <div class="mr-name">
          ${m.name}
          <span class="badge ${isDl?'badge-dl':'badge-nodl'}">${isDl?'✓ READY':'NOT DOWNLOADED'}</span>
          ${m.label?`<span class="badge ${lblMap[m.label]||''}">${m.reason||m.label}</span>`:''}
        </div>
        <div class="mr-desc">${m.description||''}</div>
        <div class="mr-meta">${m.task.toUpperCase()} · ${m.size_mb}MB</div>
      </div>
      <div class="mr-actions">
        <div class="prog-wrap ${isRun?'visible':''}" id="prog-${m.id}">
          <div class="prog-bar"><div class="prog-fill" id="prog-fill-${m.id}" style="width:0%"></div></div>
          <div class="prog-label" id="prog-label-${m.id}">0%</div>
        </div>
        ${isDl
          ? `<button class="btn btn-danger btn-sm" onclick="doDelete('${m.id}')">XÓA</button>`
          : `<button class="btn btn-primary btn-sm" id="btn-dl-${m.id}" onclick="doDownload('${m.id}')">↓ TẢI</button>`
        }
      </div>`;
    con.appendChild(row);
    if (isRun) startPoll(m.id);
  });
}

async function doDownload(id) {
  const btn = document.getElementById(`btn-dl-${id}`);
  if (btn) { btn.disabled=true; btn.textContent='...'; }
  const resp = await fetch(`/api/models/${id}/download`,{method:'POST'});
  const data = await resp.json();
  if (!resp.ok) { toast('✗ '+data.detail,true); return; }
  logMsg(`Downloading: ${id}`,'info');
  document.getElementById(`prog-${id}`)?.classList.add('visible');
  startPoll(id);
}
function startPoll(id) {
  if (pollTimers[id]) return;
  pollTimers[id] = setInterval(() => pollProgress(id), 1000);
}
async function pollProgress(id) {
  const d = await fetch(`/api/models/${id}/progress`).then(r=>r.json());
  const fill  = document.getElementById(`prog-fill-${id}`);
  const label = document.getElementById(`prog-label-${id}`);
  if (fill)  fill.style.width  = d.percent+'%';
  if (label) label.textContent = d.status==='downloading'
    ? `${d.percent}% · ${fmt(d.size_done)}/${fmt(d.size_total)}` : d.message;
  if (d.status==='done'||d.status==='error') {
    clearInterval(pollTimers[id]); delete pollTimers[id];
    if (d.status==='done') {
      logMsg(`Downloaded: ${id}`,'ok'); toast(`✓ ${id} ready`);
      await loadSettingsModels(); await loadDownloadedSidebar();
    } else {
      logMsg(`Error: ${d.message}`,'err'); toast('✗ '+d.message,true);
    }
  }
}
async function doDelete(id) {
  if (!confirm(`Xóa ${id}?`)) return;
  await fetch(`/api/models/${id}`,{method:'DELETE'});
  logMsg(`Deleted: ${id}`,'warn');
  await loadSettingsModels(); await loadDownloadedSidebar();
}
function fmt(b) {
  if (!b) return '?';
  return b>1048576?(b/1048576).toFixed(1)+'MB':(b/1024).toFixed(0)+'KB';
}

// ── Toast ─────────────────────────────────────────────────────
function toast(msg, isErr=false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderColor = isErr ? 'rgba(255,107,129,.4)' : 'rgba(108,92,231,.4)';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2800);
}

// ── Init ──────────────────────────────────────────────────────
async function init() {
  await loadStatus();
  await loadBenchDetail();
  await loadDownloadedSidebar();
  logMsg('TPixel v0.2 initialized', 'ok');
  logMsg('System ready — waiting for input', 'info');
}

init();
setInterval(loadStatus, 15000);
setInterval(loadSystem, 2000);  // Realtime system stats
