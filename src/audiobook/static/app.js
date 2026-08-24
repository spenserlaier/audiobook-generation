const jobsEl = document.querySelector('#jobs');
const voicesEl = document.querySelector('#voices');
const storageEl = document.querySelector('#storage');
let regenerationSourceId = null;
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

const chapterRow = chapter => `<div class="chapter"><span>${escapeHtml(chapter.title)} <small>· ${escapeHtml(chapter.status)}</small></span>${chapter.audio_url ? `<div class="audio-actions"><audio controls preload="none" src="${chapter.audio_url}"></audio><a class="download" href="${chapter.audio_url}" download>Download WAV</a></div>` : ''}</div>`;
const chapterPanel = job => job.chapters_total ? `<div class="chapter-browser"><button class="quiet toggle-chapters" data-job-id="${job.id}" type="button">Show chapters (${job.chapters_total})</button><div class="chapter-panel" data-job-id="${job.id}" data-offset="0" data-total="${job.chapters_total}" hidden><div class="chapters"></div><button class="quiet load-chapters" type="button">Load next 50</button></div></div>` : '';
const archiveControl = job => job.status === 'completed' && job.output_dir ? `<div class="archive-control" data-job-id="${job.id}"><label>Export format<select class="archive-format"><option value="mp3">MP3</option><option value="wav">WAV</option></select></label><div class="archive-action"><button class="quiet prepare-archive" type="button">Prepare MP3 ZIP</button></div></div>` : '';

async function loadChapterBatch(panel) {
  const offset = Number(panel.dataset.offset);
  const response = await fetch(`/api/jobs/${panel.dataset.jobId}/chapters?offset=${offset}&limit=50`);
  const items = await response.json();
  panel.querySelector('.chapters').insertAdjacentHTML('beforeend', items.map(chapterRow).join(''));
  panel.dataset.offset = offset + items.length;
  if (Number(panel.dataset.offset) >= Number(panel.dataset.total) || !items.length) panel.querySelector('.load-chapters').hidden = true;
}

async function refreshVoices() {
  // Keep a voice preview playing while status polling continues in the background.
  if ([...voicesEl.querySelectorAll('audio')].some(player => !player.paused)) return;
  const response = await fetch('/api/voices');
  const voices = await response.json();
  voicesEl.innerHTML = voices.length ? voices.map(voice => `<div class="voice"><div><strong>${escapeHtml(voice.name)}</strong> <small>· ${escapeHtml(voice.status)}</small>${voice.error ? `<p class="failed">${escapeHtml(voice.error)}</p>` : ''}</div>${voice.preview_url ? `<div class="audio-actions"><audio controls preload="none" src="${voice.preview_url}"></audio><a class="download" href="${voice.preview_url}" download>Download preview</a></div>` : ''}</div>`).join('') : '<p class="empty">No saved voices yet.</p>';
  const selected = document.querySelector('#voice-id').value;
  document.querySelector('#voice-id').innerHTML = '<option value="">Create a new voice for this job</option>' + voices.filter(v => v.status === 'ready').map(v => `<option value="${v.id}">${escapeHtml(v.name)}</option>`).join('');
  document.querySelector('#voice-id').value = selected;
}

async function refresh() {
  // Replacing the job cards destroys active audio elements and stops playback.
  if ([...jobsEl.querySelectorAll('audio')].some(player => !player.paused) || jobsEl.querySelector('.chapter-panel:not([hidden])')) return;
  const response = await fetch('/api/jobs');
  const jobs = await response.json();
  if (!jobs.length) { jobsEl.innerHTML = '<p class="empty">No jobs yet.</p>'; return; }
  const cards = jobs.map(job => `<article class="job"><div class="job-head"><div><h3>${escapeHtml(job.title || 'Untitled audiobook')}</h3><small>${escapeHtml(job.novel_url)}</small></div><div class="job-controls"><strong>${escapeHtml(job.status)}</strong>${job.chapters_total && !['queued','crawling','synthesizing'].includes(job.status) ? `<button class="quiet regenerate-job" data-job-id="${job.id}" type="button">Regenerate</button>` : ''}${['queued','crawling','synthesizing'].includes(job.status) ? `<button class="danger cancel-job" data-job-id="${job.id}" type="button">Cancel</button>` : ''}<button class="quiet remove-job" data-job-id="${job.id}" type="button">Remove from list</button></div></div><div class="bar"><span style="width:${Math.round(job.progress*100)}%"></span></div><small>${escapeHtml(job.stage)} · ${Math.round(job.progress*100)}%</small>${archiveControl(job)}${job.voice_preview_url ? `<div class="chapter"><span>Designed voice preview</span><audio controls preload="none" src="${job.voice_preview_url}"></audio></div>` : ''}${job.error ? `<p class="failed">${escapeHtml(job.error)}</p>` : ''}${chapterPanel(job)}</article>`);
  jobsEl.innerHTML = cards.join('');
  await refreshArchiveStatuses();
}

const formatBytes = bytes => {
  if (!bytes) return '0 B';
  const units = ['B','KB','MB','GB']; let unit = 0; let value = bytes;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(unit ? 1 : 0)} ${units[unit]}`;
};

function renderArchiveStatus(control, status) {
  const action = control.querySelector('.archive-action');
  const format = status.format.toUpperCase();
  if (status.state === 'ready') {
    action.innerHTML = `<a class="download" href="${status.download_url}" download>Download ${format} ZIP (${formatBytes(status.size_bytes)})</a>`;
  } else if (status.state === 'preparing') {
    action.innerHTML = `<button class="quiet" type="button" disabled>Preparing ${format} ZIP… ${status.completed_files}/${status.total_files} chapters</button>`;
  } else if (status.state === 'failed') {
    action.innerHTML = `<button class="quiet prepare-archive" type="button">Retry ${format} ZIP</button><small class="failed">${escapeHtml(status.error)}</small>`;
  } else {
    action.innerHTML = `<button class="quiet prepare-archive" type="button">Prepare ${format} ZIP</button>`;
  }
}

async function refreshArchiveStatuses() {
  await Promise.all([...jobsEl.querySelectorAll('.archive-control')].map(async control => {
    const format = control.querySelector('.archive-format').value;
    const response = await fetch(`/api/jobs/${control.dataset.jobId}/download/status?format=${format}`);
    if (response.ok) renderArchiveStatus(control, await response.json());
  }));
}

async function refreshStorage() {
  const response = await fetch('/api/storage');
  const entries = await response.json();
  storageEl.innerHTML = entries.length ? entries.map(entry => `<article class="job storage-item"><div><h3>${escapeHtml(entry.title)}</h3><small>${entry.file_count} files · ${formatBytes(entry.size_bytes)} · ${escapeHtml(entry.status)}${entry.hidden ? ' · hidden from jobs' : ''}</small></div>${entry.file_count ? `<button class="danger delete-files" data-job-id="${entry.job_id}" data-title="${escapeHtml(entry.title)}" type="button">Delete generated files</button>` : '<small>Files already removed</small>'}</article>`).join('') : '<p class="empty">No runs yet.</p>';
}

document.querySelector('#job-form').addEventListener('submit', async event => {
  event.preventDefault(); const error = document.querySelector('#form-error'); error.textContent = '';
  const limit = document.querySelector('#chapter-limit').value;
  const chapterLimit = document.querySelector('#chapter-scope').value === 'all' ? null : Number(limit);
  const body = { novel_url:document.querySelector('#novel-url').value, title:document.querySelector('#title').value || null, chapter_limit:chapterLimit, language:document.querySelector('#language').value, synthesis_mode:document.querySelector('#synthesis-mode').value, voice_id:document.querySelector('#voice-id').value || null, source_job_id:regenerationSourceId, voice_description:document.querySelector('#voice-description').value, reference_text:document.querySelector('#reference-text').value, speaker:document.querySelector('#speaker').value, voice_instruction:document.querySelector('#instruction').value };
  const response = await fetch('/api/jobs', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) { const detail = await response.json(); error.textContent = JSON.stringify(detail.detail); return; }
  event.target.reset(); regenerationSourceId = null; document.querySelector('#regeneration-note').hidden = true; document.querySelector('#chapter-limit').value = 3; document.querySelector('#chapter-limit-field').hidden = false; document.querySelector('#language').value = 'Auto'; await refresh();
});
document.querySelector('#chapter-scope').addEventListener('change', event => {
  const limited = event.target.value === 'first';
  document.querySelector('#chapter-limit-field').hidden = !limited;
  document.querySelector('#chapter-limit').required = limited;
});
document.querySelector('#refresh').addEventListener('click', refresh);
document.querySelector('#refresh-storage').addEventListener('click', refreshStorage);
jobsEl.addEventListener('click', async event => {
  const prepare = event.target.closest('.prepare-archive');
  if (prepare) {
    const control = prepare.closest('.archive-control');
    prepare.disabled = true; prepare.textContent = 'Starting ZIP…';
    const format = control.querySelector('.archive-format').value;
    const response = await fetch(`/api/jobs/${control.dataset.jobId}/download/prepare?format=${format}`, {method:'POST'});
    if (!response.ok) { const detail = await response.json(); alert(detail.detail); return; }
    renderArchiveStatus(control, await response.json()); return;
  }
  const cancel = event.target.closest('.cancel-job');
  if (cancel) {
    if (!confirm('Cancel this job? Any current crawler process will be stopped.')) return;
    const response = await fetch(`/api/jobs/${cancel.dataset.jobId}/cancel`, {method:'POST'});
    if (!response.ok) { const detail = await response.json(); alert(detail.detail); }
    await refresh(); return;
  }
  const regenerate = event.target.closest('.regenerate-job');
  if (regenerate) {
    const response = await fetch(`/api/jobs/${regenerate.dataset.jobId}`);
    const job = await response.json();
    regenerationSourceId = job.id;
    document.querySelector('#regeneration-title').textContent = job.title || 'Untitled audiobook';
    document.querySelector('#regeneration-note').hidden = false;
    document.querySelector('#novel-url').value = job.novel_url;
    document.querySelector('#title').value = job.title || '';
    document.querySelector('#language').value = job.language;
    document.querySelector('#chapter-scope').value = 'all';
    document.querySelector('#chapter-limit-field').hidden = true;
    document.querySelector('#chapter-limit').required = false;
    document.querySelector('#synthesis-mode').value = job.synthesis_mode;
    document.querySelector('#voice-id').value = job.voice_id || '';
    document.querySelector('#voice-description').value = job.voice_description;
    document.querySelector('#reference-text').value = job.reference_text;
    document.querySelector('#speaker').value = job.speaker;
    document.querySelector('#instruction').value = job.voice_instruction;
    document.querySelector('#synthesis-mode').dispatchEvent(new Event('change'));
    document.querySelector('#job-form').scrollIntoView({behavior:'smooth'});
    return;
  }
  const button = event.target.closest('.remove-job');
  if (button) {
    await fetch(`/api/jobs/${button.dataset.jobId}`, {method:'DELETE'});
    await refresh(); await refreshStorage(); return;
  }
  const toggle = event.target.closest('.toggle-chapters');
  if (toggle) {
    const panel = toggle.parentElement.querySelector('.chapter-panel');
    panel.hidden = !panel.hidden;
    toggle.textContent = panel.hidden ? `Show chapters (${panel.dataset.total})` : 'Hide chapters';
    if (!panel.hidden && Number(panel.dataset.offset) === 0) await loadChapterBatch(panel);
    return;
  }
  const load = event.target.closest('.load-chapters');
  if (load) await loadChapterBatch(load.closest('.chapter-panel'));
});
document.querySelector('#cancel-regeneration').addEventListener('click', () => {
  regenerationSourceId = null;
  document.querySelector('#regeneration-note').hidden = true;
});
jobsEl.addEventListener('change', async event => {
  if (!event.target.matches('.archive-format')) return;
  const control = event.target.closest('.archive-control');
  const response = await fetch(`/api/jobs/${control.dataset.jobId}/download/status?format=${event.target.value}`);
  if (response.ok) renderArchiveStatus(control, await response.json());
});
document.querySelector('#clear-jobs').addEventListener('click', async () => {
  if (!confirm('Remove every job from the main list? Generation will continue and files will be kept.')) return;
  await fetch('/api/jobs', {method:'DELETE'}); await refresh(); await refreshStorage();
});
document.querySelector('#clear-queue').addEventListener('click', async () => {
  if (!confirm('Cancel every job still waiting for a worker?')) return;
  const response = await fetch('/api/jobs/cancel-pending', {method:'POST'});
  const result = await response.json(); alert(`Cancelled ${result.cancelled} queued jobs.`);
  await refresh();
});
storageEl.addEventListener('click', async event => {
  const button = event.target.closest('.delete-files');
  if (!button || !confirm(`Permanently delete generated files for “${button.dataset.title}”?`)) return;
  const response = await fetch(`/api/storage/jobs/${button.dataset.jobId}`, {method:'DELETE'});
  if (!response.ok) { const detail = await response.json(); alert(detail.detail); return; }
  await refreshStorage(); await refresh();
});
document.querySelector('#clear-storage').addEventListener('click', async () => {
  if (!confirm('Permanently delete generated files for all finished runs? Active runs will be skipped.')) return;
  const response = await fetch('/api/storage', {method:'DELETE'});
  const result = await response.json();
  alert(`Deleted artifacts for ${result.deleted} runs.${result.skipped_active ? ` Skipped ${result.skipped_active} active runs.` : ''}`);
  await refreshStorage(); await refresh();
});
document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab === button));
  document.querySelectorAll('.generate-view').forEach(view => { view.hidden = button.dataset.view !== 'generate'; });
  document.querySelectorAll('.storage-view').forEach(view => { view.hidden = button.dataset.view !== 'storage'; });
  if (button.dataset.view === 'storage') refreshStorage();
}));
document.querySelector('#voice-form').addEventListener('submit', async event => {
  event.preventDefault(); const error = document.querySelector('#voice-error'); error.textContent = '';
  const body = {name:document.querySelector('#voice-name').value, language:document.querySelector('#voice-language').value, description:document.querySelector('#new-voice-description').value, reference_text:document.querySelector('#new-reference-text').value};
  const response = await fetch('/api/voices', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) { const detail = await response.json(); error.textContent = JSON.stringify(detail.detail); return; }
  await refreshVoices();
});
document.querySelector('#synthesis-mode').addEventListener('change', event => {
  const designed = event.target.value === 'designed_clone';
  document.querySelector('#designed-voice-fields').hidden = !designed;
  document.querySelector('#custom-voice-fields').hidden = designed;
});
refresh(); refreshVoices(); refreshStorage(); setInterval(() => { refresh(); refreshVoices(); refreshArchiveStatuses(); }, 2500);
