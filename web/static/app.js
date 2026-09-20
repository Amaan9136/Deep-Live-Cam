const $ = s => document.querySelector(s);
const source = $('#source');
const target = $('#target');
const imageType = $('#imageType');
const videoType = $('#videoType');
const start = $('#start');
const status = $('#status');
const resultCard = $('#resultCard');
const imageResult = $('#imageResult');
const videoResult = $('#videoResult');
const download = $('#download');
const gpuBadge = $('#gpuBadge');
const modelsBadge = $('#modelsBadge');
const modelsCard = $('#modelsCard');
const sourcePreview = $('#sourcePreview');
const targetImage = $('#targetImage');
const targetVideo = $('#targetVideo');
const sourceMeta = $('#sourceMeta');
const targetMeta = $('#targetMeta');
const sourceClear = $('#sourceClear');
const targetClear = $('#targetClear');
const progress = $('#progress');
const bar = $('#bar');
const compare = $('#compare');
const IMAGE_RE = /\.(jpe?g|png|bmp|webp)$/i;
const VIDEO_RE = /\.(mp4|mov|avi|mkv|webm)$/i;
const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/bmp';
const VIDEO_ACCEPT = 'video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm';
const ENHANCER_MODELS = {gpen256: 'GPEN-BFR-256.onnx', gpen512: 'GPEN-BFR-512.onnx', gfpgan: 'gfpgan-1024.onnx'};
const AUTO_THREADS = Math.max(1, Math.min(navigator.hardwareConcurrency || 4, 32));
const DEFAULTS = {many: false, poisson: false, enhancer: 'none', opacity: 100, sharpness: 0, mouth: 0, keepFps: true, keepAudio: true, smooth: false, smoothWeight: 0.5, quality: 18, threads: AUTO_THREADS};
const PRESETS = {fast: {...DEFAULTS, quality: 23}, balanced: DEFAULTS, quality: {...DEFAULTS, enhancer: 'gpen256', poisson: true, quality: 14}};
const fields = {many: $('#optMany'), poisson: $('#optPoisson'), enhancer: $('#optEnhancer'), opacity: $('#optOpacity'), sharpness: $('#optSharpness'), mouth: $('#optMouth'), keepFps: $('#optKeepFps'), keepAudio: $('#optKeepAudio'), smooth: $('#optSmooth'), smoothWeight: $('#optSmoothWeight'), quality: $('#optQuality'), threads: $('#optThreads')};
const formats = {opacity: v => `${v}%`, sharpness: v => Number(v).toFixed(1), mouth: v => Number(v) > 0 ? v : 'Off', smoothWeight: v => Number(v).toFixed(2), quality: v => v, threads: v => v};
let targetType = 'image';
let sourceFile = null;
let targetFile = null;
let sourceUrl = null;
let targetUrl = null;
let snap = {source: null, target: null};
let system = {ffmpeg: true};
let modelState = null;
let modelTimer = null;
let view = null;
let rate = null;
const el = (tag, cls = '', text = '') => {
  const node = document.createElement(tag);
  if(cls) node.className = cls;
  if(text) node.textContent = text;
  return node;
};
const fmtBytes = n => !n ? '0 KB' : n >= 1073741824 ? `${(n / 1073741824).toFixed(2)} GB` : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
const fmtTime = s => {
  s = Math.max(0, Math.round(s));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
};
const kindOf = f => VIDEO_RE.test(f.name) ? 'video' : IMAGE_RE.test(f.name) ? 'image' : null;
const revoke = url => url && URL.revokeObjectURL(url);
function setType(type, keep){
  targetType = type;
  imageType.classList.toggle('active', type === 'image');
  videoType.classList.toggle('active', type === 'video');
  target.accept = type === 'image' ? IMAGE_ACCEPT : VIDEO_ACCEPT;
  $('#targetHint').textContent = type === 'image' ? 'Click or drop a target image' : 'Click or drop a target video';
  $('#targetFormats').textContent = type === 'image' ? 'JPG, PNG, WEBP, BMP' : 'MP4, MOV, AVI, MKV, WEBM';
  document.querySelectorAll('.video-only').forEach(node => node.classList.toggle('hidden', type !== 'video'));
  if(!keep) clearTarget();
  if(type === 'video' && !system.ffmpeg) status.textContent = 'FFmpeg was not found on PATH. Install FFmpeg to process videos.';
}
imageType.onclick = () => setType('image');
videoType.onclick = () => setType('video');
function clearSource(){
  revoke(sourceUrl);
  sourceUrl = sourceFile = null;
  source.value = '';
  sourcePreview.removeAttribute('src');
  sourcePreview.classList.add('hidden');
  sourceClear.classList.add('hidden');
  sourceMeta.textContent = '';
  $('#sourceDrop').classList.remove('filled');
}
function clearTarget(){
  revoke(targetUrl);
  targetUrl = targetFile = null;
  target.value = '';
  targetImage.removeAttribute('src');
  targetVideo.removeAttribute('src');
  targetVideo.load();
  targetImage.classList.add('hidden');
  targetVideo.classList.add('hidden');
  targetClear.classList.add('hidden');
  targetMeta.textContent = '';
  $('#targetDrop').classList.remove('filled');
}
function setSource(file){
  if(!file) return clearSource();
  if(kindOf(file) !== 'image'){
    status.textContent = 'Source must be a JPG, PNG, BMP, or WEBP image.';
    source.value = '';
    return;
  }
  revoke(sourceUrl);
  sourceFile = file;
  sourceUrl = URL.createObjectURL(file);
  sourcePreview.onload = () => sourceMeta.textContent = `${file.name} · ${sourcePreview.naturalWidth}×${sourcePreview.naturalHeight} · ${fmtBytes(file.size)}`;
  sourcePreview.src = sourceUrl;
  sourcePreview.classList.remove('hidden');
  sourceClear.classList.remove('hidden');
  sourceMeta.textContent = `${file.name} · ${fmtBytes(file.size)}`;
  $('#sourceDrop').classList.add('filled');
  status.textContent = 'Ready.';
}
function setTarget(file){
  if(!file) return clearTarget();
  const kind = kindOf(file);
  if(!kind){
    status.textContent = 'Target must be an image (JPG, PNG, BMP, WEBP) or a video (MP4, MOV, AVI, MKV, WEBM).';
    target.value = '';
    return;
  }
  if(kind !== targetType) setType(kind, true);
  revoke(targetUrl);
  targetFile = file;
  targetUrl = URL.createObjectURL(file);
  targetMeta.textContent = `${file.name} · ${fmtBytes(file.size)}`;
  targetImage.classList.toggle('hidden', kind !== 'image');
  targetVideo.classList.toggle('hidden', kind !== 'video');
  if(kind === 'image'){
    targetImage.onload = () => targetMeta.textContent = `${file.name} · ${targetImage.naturalWidth}×${targetImage.naturalHeight} · ${fmtBytes(file.size)}`;
    targetImage.src = targetUrl;
  }else{
    targetVideo.onloadedmetadata = () => targetMeta.textContent = `${file.name} · ${targetVideo.videoWidth}×${targetVideo.videoHeight} · ${fmtTime(targetVideo.duration)} · ${fmtBytes(file.size)}`;
    targetVideo.src = targetUrl;
  }
  targetClear.classList.remove('hidden');
  $('#targetDrop').classList.add('filled');
  status.textContent = 'Ready.';
}
source.onchange = () => setSource(source.files[0]);
target.onchange = () => setTarget(target.files[0]);
sourceClear.onclick = e => {
  e.preventDefault();
  clearSource();
};
targetClear.onclick = e => {
  e.preventDefault();
  clearTarget();
};
[['#sourceDrop', setSource], ['#targetDrop', setTarget]].forEach(([id, handler]) => {
  const zone = $(id);
  zone.ondragover = e => {
    e.preventDefault();
    zone.classList.add('over');
  };
  zone.ondragleave = () => zone.classList.remove('over');
  zone.ondrop = e => {
    e.preventDefault();
    zone.classList.remove('over');
    if(e.dataTransfer.files[0]) handler(e.dataTransfer.files[0]);
  };
});
function readOptions(){
  const out = {};
  for(const [key, node] of Object.entries(fields)) out[key] = node.type === 'checkbox' ? node.checked : node.type === 'range' ? Number(node.value) : node.value;
  return out;
}
function refreshOutputs(){
  for(const [key, format] of Object.entries(formats)) $(`#opt${key[0].toUpperCase()}${key.slice(1)}Out`).textContent = format(fields[key].value);
}
function writeOptions(options){
  for(const [key, node] of Object.entries(fields)){
    const value = options[key] ?? DEFAULTS[key];
    if(node.type === 'checkbox') node.checked = !!value;
    else node.value = value;
  }
  refreshOutputs();
}
function saveOptions(){
  try{ localStorage.setItem('lfs.options', JSON.stringify(readOptions())); }catch(err){}
}
Object.values(fields).forEach(node => node.addEventListener('input', () => {
  refreshOutputs();
  saveOptions();
}));
fields.enhancer.addEventListener('change', () => {
  const model = modelState && modelState.models.find(m => m.name === ENHANCER_MODELS[fields.enhancer.value]);
  if(model && !model.present) status.textContent = `${model.label} will be downloaded on first use (${fmtBytes(model.size)}).`;
});
document.querySelectorAll('[data-preset]').forEach(button => button.onclick = () => {
  writeOptions(PRESETS[button.dataset.preset]);
  saveOptions();
});
$('#resetOptions').onclick = () => {
  writeOptions(DEFAULTS);
  saveOptions();
};
try{ writeOptions(JSON.parse(localStorage.getItem('lfs.options')) || DEFAULTS); }catch(err){ writeOptions(DEFAULTS); }
setType('image');
fetch('/api/system').then(r=>r.json()).then(data=>{
  system = data;
  gpuBadge.textContent = data.cuda ? 'NVIDIA CUDA READY' : 'CUDA UNAVAILABLE';
  gpuBadge.title = data.gpu || '';
  gpuBadge.style.borderColor = data.cuda ? '#2c694e' : '#6b3434';
}).catch(()=> gpuBadge.textContent = 'LOCAL MODE');
const summarize = items => ({
  size: items.reduce((a, m) => a + (m.size || 0), 0),
  done: items.reduce((a, m) => a + (m.present ? (m.size || 0) : m.done), 0),
  state: items.every(m => m.present) ? 'ready' : items.some(m => m.state === 'downloading') ? 'downloading' : items.some(m => m.state === 'queued') ? 'queued' : items.some(m => m.state === 'error') ? 'error' : 'missing',
  error: (items.find(m => m.error) || {}).error,
  names: items.filter(m => !m.present).map(m => m.name),
  presentNames: items.filter(m => m.present).map(m => m.name)
});
async function requestDelete(label, names){
  if(!names.length) return;
  if(!confirm(`Delete ${label}? This removes the model file(s) from disk.`)) return;
  for(const name of names){
    await fetch(`/api/models/${name}`, {method: 'DELETE'});
  }
  loadModels();
}
function modelRow(label, note, items){
  const s = summarize(items);
  const row = el('div', 'model');
  const info = el('div', 'model-info');
  info.append(el('strong', '', label), el('small', '', s.size ? `${note} · ${fmtBytes(s.size)}` : note));
  const side = el('div', 'model-side');
  side.append(el('span', `pill ${s.state}`, {ready: 'Ready', missing: 'Missing', queued: 'Queued', downloading: 'Downloading', error: 'Failed'}[s.state]));
  if(s.state === 'missing' || s.state === 'error'){
    const button = el('button', 'ghost', 'Download');
    button.type = 'button';
    button.onclick = () => requestDownload(s.names);
    side.append(button);
  }
  if(s.state === 'ready'){
    const button = el('button', 'link', 'Delete');
    button.type = 'button';
    button.onclick = () => requestDelete(label, s.presentNames);
    side.append(button);
  }
  row.append(info, side);
  if(s.state === 'downloading'){
    const track = el('div', 'bar mini');
    const fill = el('i');
    fill.style.width = `${s.size ? Math.min(100, s.done * 100 / s.size) : 0}%`;
    track.append(fill);
    row.append(track, el('small', 'meta', `${fmtBytes(s.done)} / ${fmtBytes(s.size)}`));
  }
  if(s.state === 'error' && s.error) row.append(el('div', 'model-error', s.error));
  return row;
}
function manualCommands(data){
  const missing = data.models.filter(m => !m.present && m.name !== 'inswapper_128.onnx');
  const lines = [`New-Item -ItemType Directory -Force "${data.directory}" | Out-Null`];
  if(missing.some(m => m.group === 'analyser')) lines.push(`New-Item -ItemType Directory -Force "${data.analyser_directory}" | Out-Null`);
  missing.forEach(m => lines.push(`curl.exe -L -C - -o "${m.path}" "${m.url}"`));
  return missing.length ? lines.join('\n') : 'All models are already downloaded.';
}
function renderModels(data){
  $('#modelsDir').textContent = `Swapper and enhancer models are saved in ${data.directory}. The detection pack is saved in ${data.analyser_directory}.`;
  const list = $('#modelsList');
  list.replaceChildren();
  [['Face swapper (one is enough)', 'swapper'], ['Face enhancers (optional)', 'enhancer']].forEach(([title, group]) => {
    list.append(el('h3', '', title));
    data.models.filter(m => m.group === group).forEach(m => list.append(modelRow(m.label, m.note, [m])));
  });
  const pack = data.models.filter(m => m.group === 'analyser');
  list.append(el('h3', '', 'Face detection (required)'), modelRow('Detection pack (buffalo_l)', pack[0].note, pack));
  $('#manualCmd').textContent = manualCommands(data);
  modelsBadge.textContent = data.ready ? 'Models ready (Click to view)' : data.swapper_ready ? 'Detection pack missing' : 'Models missing';
  modelsBadge.classList.toggle('ok', data.ready);
  modelsBadge.classList.toggle('warn', !data.ready);
}
async function loadModels(){
  const data = await (await fetch('/api/models')).json();
  modelState = data;
  renderModels(data);
  return data;
}
function pollModels(){
  clearTimeout(modelTimer);
  loadModels().then(data => {
    if(data.models.some(m => m.state === 'downloading' || m.state === 'queued')) modelTimer = setTimeout(pollModels, 1000);
  }).catch(() => {});
}
async function requestDownload(names){
  if(!names.length){
    status.textContent = 'All required models are already downloaded.';
    return;
  }
  await fetch('/api/models/download', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({names})});
  pollModels();
}
$('#downloadNeeded').onclick = () => {
  const swapper = modelState.swapper_ready ? [] : ['inswapper_128_fp16.onnx'];
  requestDownload([...swapper, ...modelState.models.filter(m => m.group === 'analyser' && !m.present).map(m => m.name)]);
};
$('#closeModels').onclick = () => modelsCard.classList.add('hidden');
modelsBadge.onclick = () => {
  modelsCard.classList.toggle('hidden');
  if(!modelsCard.classList.contains('hidden')) pollModels();
};
$('#copyCmd').onclick = () => navigator.clipboard.writeText($('#manualCmd').textContent).then(() => $('#copyCmd').textContent = 'Copied');
loadModels().then(data => {
  if(!data.ready) modelsCard.classList.remove('hidden');
}).catch(() => modelsBadge.textContent = 'Models unknown');
function renderJob(job){
  status.textContent = job.status || 'Processing…';
  const elapsed = (job.finished || job.now) - (job.started || job.created);
  const p = job.progress;
  let text = '';
  let eta = '';
  if(p && p.total){
    const pct = Math.min(100, Math.round(p.done * 100 / p.total));
    bar.parentElement.classList.remove('indeterminate');
    bar.style.width = `${pct}%`;
    if(!rate || rate.unit !== p.unit || p.done < rate.done) rate = {unit: p.unit, done: p.done, time: Date.now()};
    const speed = (p.done - rate.done) / Math.max(1, (Date.now() - rate.time) / 1000);
    if(speed > 0) eta = ` · about ${fmtTime((p.total - p.done) / speed)} left`;
    text = p.unit === 'bytes' ? `${fmtBytes(p.done)} / ${fmtBytes(p.total)} (${pct}%)` : `Frame ${p.done} / ${p.total} (${pct}%)`;
  }else{
    bar.parentElement.classList.add('indeterminate');
    bar.style.width = '';
    rate = null;
  }
  $('#progressText').textContent = text;
  $('#timer').textContent = `Elapsed ${fmtTime(elapsed)}${eta}`;
  const list = $('#logList');
  list.replaceChildren();
  (job.log || []).slice(-8).forEach(entry => list.append(el('li', '', `${new Date(entry.time * 1000).toLocaleTimeString()}  ${entry.message}`)));
  $('#logBox').classList.toggle('hidden', !(job.log && job.log.length));
}
async function waitForJob(id){
  while(true){
    const res = await fetch(`/api/jobs/${id}`);
    const job = await res.json();
    if(!res.ok) throw new Error(job.detail || 'Lost connection to the job.');
    renderJob(job);
    if(job.state === 'completed') return job;
    if(job.state === 'error') throw new Error(job.status || 'Processing failed.');
    await new Promise(r=>setTimeout(r,700));
  }
}
function showTab(tab){
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  imageResult.classList.add('hidden');
  videoResult.classList.add('hidden');
  compare.classList.add('hidden');
  videoResult.pause();
  if(tab === 'compare'){
    $('#compareBase').src = snap.target;
    $('#compareTop').src = view.url;
    compare.classList.remove('hidden');
    return;
  }
  const src = tab === 'result' ? view.url : tab === 'original' ? snap.target : snap.source;
  const video = view.kind === 'video' && tab !== 'source';
  const node = video ? videoResult : imageResult;
  node.src = src;
  node.classList.remove('hidden');
  if(video) videoResult.load();
}
function openResult(item){
  view = item;
  resultCard.classList.remove('hidden');
  download.href = `${item.url}${item.url.includes('?') ? '&' : '?'}download=1`;
  $('#openTab').href = item.url;
  $('#resultInfo').textContent = item.info || '';
  $('#tabs').classList.toggle('hidden', !item.local);
  $('#compareTab').classList.toggle('hidden', item.kind !== 'image');
  showTab('result');
  resultCard.scrollIntoView({behavior: 'smooth', block: 'start'});
}
videoResult.onerror = () => $('#resultInfo').textContent = 'Your browser cannot play this video. Use Save Output to download it.';
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => showTab(b.dataset.tab));
$('#compareRange').oninput = e => $('#compareTop').style.clipPath = `inset(0 ${100 - e.target.value}% 0 0)`;
$('#compareRange').value = 50;
$('#compareTop').style.clipPath = 'inset(0 50% 0 0)';
$('#reuse').onclick = async () => {
  const blob = await (await fetch(view.url)).blob();
  setTarget(new File([blob], view.name, {type: blob.type}));
  window.scrollTo({top: 0, behavior: 'smooth'});
  status.textContent = 'Result set as the new target. Pick different options and run again.';
};
async function track(id, local){
  start.disabled = true;
  resultCard.classList.add('hidden');
  progress.classList.remove('hidden');
  rate = null;
  try{ localStorage.setItem('lfs.job', id); }catch(err){}
  try{
    const job = await waitForJob(id);
    const seconds = fmtTime(job.finished - job.started);
    openResult({url: `${job.url}?t=${Date.now()}`, name: job.output, kind: job.target_type, local, info: `Completed in ${seconds} · ${fmtBytes(job.size)}`});
    status.textContent = 'Face swap completed.';
    loadGallery();
  }catch(err){
    status.textContent = err.message || 'Processing failed.';
    loadModels().then(data => {
      if(!data.ready) modelsCard.classList.remove('hidden');
    }).catch(() => {});
  }finally{
    start.disabled = false;
    progress.classList.add('hidden');
    try{ localStorage.removeItem('lfs.job'); }catch(err){}
  }
}
start.onclick = async () => {
  if(!sourceFile || !targetFile){
    status.textContent = 'Choose a source face and target first.';
    return;
  }
  start.disabled = true;
  resultCard.classList.add('hidden');
  imageResult.classList.add('hidden');
  videoResult.classList.add('hidden');
  status.textContent = 'Uploading…';
  try{
    const o = readOptions();
    const form = new FormData();
    form.append('source', sourceFile);
    form.append('target', targetFile);
    form.append('target_type', targetType);
    form.append('many_faces', o.many);
    form.append('enhancer', o.enhancer);
    form.append('opacity', o.opacity);
    form.append('sharpness', o.sharpness);
    form.append('mouth_mask_size', o.mouth);
    form.append('poisson_blend', o.poisson);
    form.append('interpolation', o.smooth);
    form.append('interpolation_weight', o.smoothWeight);
    form.append('keep_fps', o.keepFps);
    form.append('keep_audio', o.keepAudio);
    form.append('video_quality', o.quality);
    form.append('threads', o.threads);
    const response = await fetch('/api/swap', {method:'POST', body:form});
    const data = await response.json();
    if(!response.ok) throw new Error(data.detail || 'Could not start processing.');
    revoke(snap.source);
    revoke(snap.target);
    snap = {source: URL.createObjectURL(sourceFile), target: URL.createObjectURL(targetFile)};
    await track(data.job_id, true);
  }catch(err){
    status.textContent = err.message || 'Processing failed.';
    start.disabled = false;
  }
};
async function loadGallery(){
  const data = await (await fetch('/api/outputs')).json();
  const gallery = $('#gallery');
  gallery.replaceChildren();
  $('#galleryEmpty').classList.toggle('hidden', data.items.length > 0);
  data.items.forEach(item => {
    const card = el('div', 'thumb');
    const media = item.kind === 'video' ? el('video') : el('img');
    if(item.kind === 'video'){
      media.preload = 'metadata';
      media.muted = true;
      media.src = `${item.url}#t=0.1`;
    }else{
      media.loading = 'lazy';
      media.alt = item.name;
      media.src = item.url;
    }
    media.onclick = () => openResult({url: item.url, name: item.name, kind: item.kind, local: false, info: `${item.name} · ${fmtBytes(item.size)} · ${new Date(item.modified * 1000).toLocaleString()}`});
    const row = el('div', 'thumb-row');
    row.append(el('small', '', `${fmtBytes(item.size)} · ${new Date(item.modified * 1000).toLocaleDateString()}`));
    const remove = el('button', 'link', 'Delete');
    remove.type = 'button';
    remove.onclick = async () => {
      if(!confirm(`Delete ${item.name}?`)) return;
      await fetch(item.url, {method: 'DELETE'});
      if(view && view.name === item.name) resultCard.classList.add('hidden');
      loadGallery();
    };
    row.append(remove);
    card.append(media, row);
    gallery.append(card);
  });
}
$('#refreshGallery').onclick = loadGallery;
loadGallery().catch(() => {});
(async () => {
  let id = null;
  try{ id = localStorage.getItem('lfs.job'); }catch(err){}
  if(!id) return;
  const res = await fetch(`/api/jobs/${id}`);
  if(res.ok && (await res.json()).state === 'processing') track(id, false);
})().catch(() => {});
const mainTabs = document.querySelectorAll('[data-maintab]');
const classicPanel = $('#classicPanel');
const realtimePanel = $('#realtimePanel');
const rtSource = $('#rtSource');
const rtSourceDrop = $('#rtSourceDrop');
const rtSourcePreview = $('#rtSourcePreview');
const rtSourceMeta = $('#rtSourceMeta');
const rtSourceClear = $('#rtSourceClear');
const rtCamera = $('#rtCamera');
const rtStart = $('#rtStart');
const rtStop = $('#rtStop');
const rtStatus = $('#rtStatus');
const rtStats = $('#rtStats');
const rtStream = $('#rtStream');
const rtPlaceholder = $('#rtPlaceholder');
let rtSourceUrl = null;
let rtSourceReady = false;
let rtPollTimer = null;
mainTabs.forEach(b => b.onclick = () => {
  mainTabs.forEach(x => x.classList.toggle('active', x === b));
  const tab = b.dataset.maintab;
  classicPanel.classList.toggle('hidden', tab !== 'classic');
  realtimePanel.classList.toggle('hidden', tab !== 'realtime');
  if(tab === 'realtime') loadCameras();
});
async function uploadRtSource(file){
  if(!file) return;
  if(!IMAGE_RE.test(file.name)){
    rtStatus.textContent = 'Source must be a JPG, PNG, BMP, or WEBP image.';
    return;
  }
  revoke(rtSourceUrl);
  rtSourceUrl = URL.createObjectURL(file);
  rtSourcePreview.src = rtSourceUrl;
  rtSourcePreview.classList.remove('hidden');
  rtSourceClear.classList.remove('hidden');
  rtSourceDrop.classList.add('filled');
  rtSourceMeta.textContent = `${file.name} · ${fmtBytes(file.size)}`;
  rtSourceReady = false;
  rtStatus.textContent = 'Analysing source face…';
  try{
    const form = new FormData();
    form.append('source', file);
    const res = await fetch('/api/realtime/source', {method: 'POST', body: form});
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'Could not analyse the source image.');
    rtSourceReady = true;
    rtStatus.textContent = 'Source face ready. Pick a camera and start.';
  }catch(err){
    rtStatus.textContent = err.message || 'Could not analyse the source image.';
  }
}
rtSource.onchange = () => uploadRtSource(rtSource.files[0]);
rtSourceClear.onclick = e => {
  e.preventDefault();
  revoke(rtSourceUrl);
  rtSourceUrl = null;
  rtSourceReady = false;
  rtSource.value = '';
  rtSourcePreview.removeAttribute('src');
  rtSourcePreview.classList.add('hidden');
  rtSourceClear.classList.add('hidden');
  rtSourceDrop.classList.remove('filled');
  rtSourceMeta.textContent = '';
};
rtSourceDrop.ondragover = e => { e.preventDefault(); rtSourceDrop.classList.add('over'); };
rtSourceDrop.ondragleave = () => rtSourceDrop.classList.remove('over');
rtSourceDrop.ondrop = e => {
  e.preventDefault();
  rtSourceDrop.classList.remove('over');
  if(e.dataTransfer.files[0]) uploadRtSource(e.dataTransfer.files[0]);
};
async function loadCameras(){
  try{
    const data = await (await fetch('/api/realtime/cameras')).json();
    rtCamera.replaceChildren();
    if(!data.cameras.length){
      rtCamera.append(el('option', '', 'No cameras found'));
      rtCamera.disabled = true;
      return;
    }
    rtCamera.disabled = false;
    data.cameras.forEach(cam => {
      const opt = el('option', '', cam.name);
      opt.value = cam.index;
      rtCamera.append(opt);
    });
  }catch(err){
    rtStatus.textContent = 'Could not list cameras.';
  }
}
$('#rtRefreshCameras').onclick = loadCameras;
function stopRtView(){
  clearTimeout(rtPollTimer);
  rtStream.removeAttribute('src');
  rtStream.classList.add('hidden');
  rtPlaceholder.classList.remove('hidden');
  rtStart.classList.remove('hidden');
  rtStop.classList.add('hidden');
  rtStats.textContent = '';
}
async function pollRtStatus(){
  try{
    const data = await (await fetch('/api/realtime/status')).json();
    if(!data.running){
      stopRtView();
      rtStatus.textContent = data.error || 'Stopped.';
      return;
    }
    rtStatus.textContent = data.error || 'Streaming…';
    rtStats.textContent = data.camera ? `${data.camera.width}×${data.camera.height} · ~${data.fps.toFixed(1)} FPS` : '';
    rtPollTimer = setTimeout(pollRtStatus, 1000);
  }catch(err){
    rtPollTimer = setTimeout(pollRtStatus, 2000);
  }
}
rtStart.onclick = async () => {
  if(!rtSourceReady){
    rtStatus.textContent = 'Choose a source face first.';
    return;
  }
  if(rtCamera.disabled){
    rtStatus.textContent = 'No camera available.';
    return;
  }
  rtStart.disabled = true;
  rtStatus.textContent = 'Starting camera…';
  try{
    const form = new FormData();
    form.append('camera_index', rtCamera.value);
    const res = await fetch('/api/realtime/start', {method: 'POST', body: form});
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'Could not start the camera.');
    rtStream.src = `/api/realtime/stream?t=${Date.now()}`;
    rtStream.classList.remove('hidden');
    rtPlaceholder.classList.add('hidden');
    rtStart.classList.add('hidden');
    rtStop.classList.remove('hidden');
    pollRtStatus();
  }catch(err){
    rtStatus.textContent = err.message || 'Could not start the camera.';
  }finally{
    rtStart.disabled = false;
  }
};
rtStop.onclick = async () => {
  rtStop.disabled = true;
  try{ await fetch('/api/realtime/stop', {method: 'POST'}); }catch(err){}
  stopRtView();
  rtStatus.textContent = 'Stopped.';
  rtStop.disabled = false;
};
window.addEventListener('beforeunload', () => {
  if(!rtStop.classList.contains('hidden')) navigator.sendBeacon('/api/realtime/stop');
});