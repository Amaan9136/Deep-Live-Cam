const source = document.querySelector('#source');
const target = document.querySelector('#target');
const imageType = document.querySelector('#imageType');
const videoType = document.querySelector('#videoType');
const start = document.querySelector('#start');
const status = document.querySelector('#status');
const resultCard = document.querySelector('#resultCard');
const imageResult = document.querySelector('#imageResult');
const videoResult = document.querySelector('#videoResult');
const download = document.querySelector('#download');
const gpuBadge = document.querySelector('#gpuBadge');
let targetType = 'image';

function setType(type){
  targetType = type;
  imageType.classList.toggle('active', type === 'image');
  videoType.classList.toggle('active', type === 'video');
  target.value = '';
  target.accept = type === 'image'
    ? 'image/jpeg,image/png,image/webp,image/bmp'
    : 'video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm';
}
imageType.onclick = () => setType('image');
videoType.onclick = () => setType('video');

fetch('/api/providers').then(r=>r.json()).then(data=>{
  gpuBadge.textContent = data.cuda ? 'NVIDIA CUDA READY' : 'CUDA UNAVAILABLE';
  gpuBadge.style.borderColor = data.cuda ? '#2c694e' : '#6b3434';
}).catch(()=> gpuBadge.textContent = 'LOCAL MODE');

async function waitForJob(id){
  while(true){
    const res = await fetch(`/api/jobs/${id}`);
    const job = await res.json();
    status.textContent = job.status || 'Processing…';
    if(job.state === 'completed') return job;
    if(job.state === 'error') throw new Error(job.status || 'Processing failed.');
    await new Promise(r=>setTimeout(r,700));
  }
}

start.onclick = async () => {
  if(!source.files[0] || !target.files[0]){
    status.textContent = 'Choose a source face and target first.';
    return;
  }
  start.disabled = true;
  resultCard.classList.add('hidden');
  imageResult.classList.add('hidden');
  videoResult.classList.add('hidden');
  status.textContent = 'Uploading…';
  try{
    const form = new FormData();
    form.append('source', source.files[0]);
    form.append('target', target.files[0]);
    form.append('target_type', targetType);
    const response = await fetch('/api/swap', {method:'POST', body:form});
    const data = await response.json();
    if(!response.ok) throw new Error(data.detail || 'Could not start processing.');
    const job = await waitForJob(data.job_id);
    const url = `${job.url}?t=${Date.now()}`;
    download.href = url;
    resultCard.classList.remove('hidden');
    if(targetType === 'image'){
      imageResult.src = url;
      imageResult.classList.remove('hidden');
    }else{
      videoResult.src = url;
      videoResult.classList.remove('hidden');
      videoResult.load();
    }
    status.textContent = 'Face swap completed.';
  }catch(err){
    status.textContent = err.message || 'Processing failed.';
  }finally{
    start.disabled = false;
  }
};
