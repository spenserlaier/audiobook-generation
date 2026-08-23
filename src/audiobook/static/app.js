const jobsEl = document.querySelector('#jobs');
const voicesEl = document.querySelector('#voices');
const storageEl = document.querySelector('#storage');
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

const chapterRow = chapter => `<div class="chapter"><span>${escapeHtml(chapter.title)} <small>· ${escapeHtml(chapter.status)}</small></span>${chapter.audio_url ? `<div class="audio-actions"><audio controls preload="none" src="${chapter.audio_url}"></audio><a class="download" href="${chapter.audio_url}" download>Download WAV</a></div>` : ''}</div>`;
const chapterPanel = job => job.chapters_total ? `<div class="chapter-browser"><button class="quiet toggle-chapters" data-job-id="${job.id}" type="button">Show chapters (${job.chapters_total})</button><div class="chapter-panel" data-job-id="${job.id}" data-offset="0" data-total="${job.chapters_total}" hidden><div class="chapters"></div><button class="quiet load-chapters" type="button">Load next 50</button></div></div>` : '';

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
  const cards = jobs.map(job => `<article class="job"><div class="job-head"><div><h3>${escapeHtml(job.title || 'Untitled audiobook')}</h3><small>${escapeHtml(job.novel_url)}</small></div><div class="job-controls"><strong>${escapeHtml(job.status)}</strong><button class="quiet remove-job" data-job-id="${job.id}" type="button">Remove from list</button></div></div><div class="bar"><span style="width:${Math.round(job.progress*100)}%"></span></div><small>${escapeHtml(job.stage)} · ${Math.round(job.progress*100)}%</small>${job.status === 'completed' && job.output_dir ? `<p><a class="download" href="/api/jobs/${job.id}/download" download>Download all chapters (.zip)</a></p>` : ''}${job.voice_preview_url ? `<div class="chapter"><span>Designed voice preview</span><audio controls preload="none" src="${job.voice_preview_url}"></audio></div>` : ''}${job.error ? `<p class="failed">${escapeHtml(job.error)}</p>` : ''}${chapterPanel(job)}</article>`);
  jobsEl.innerHTML = cards.join('');
}

const formatBytes = bytes => {
  if (!bytes) return '0 B';
  const units = ['B','KB','MB','GB']; let unit = 0; let value = bytes;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(unit ? 1 : 0)} ${units[unit]}`;
};

async function refreshStorage() {
  const response = await fetch('/api/storage');
  const entries = await response.json();
  storageEl.innerHTML = entries.length ? entries.map(entry => `<article class="job storage-item"><div><h3>${escapeHtml(entry.title)}</h3><small>${entry.file_count} files · ${formatBytes(entry.size_bytes)} · ${escapeHtml(entry.status)}${entry.hidden ? ' · hidden from jobs' : ''}</small></div>${entry.file_count ? `<button class="danger delete-files" data-job-id="${entry.job_id}" data-title="${escapeHtml(entry.title)}" type="button">Delete generated files</button>` : '<small>Files already removed</small>'}</article>`).join('') : '<p class="empty">No runs yet.</p>';
}

document.querySelector('#job-form').addEventListener('submit', async event => {
  event.preventDefault(); const error = document.querySelector('#form-error'); error.textContent = '';
  const limit = document.querySelector('#chapter-limit').value;
  const body = { novel_url:document.querySelector('#novel-url').value, title:document.querySelector('#title').value || null, chapter_limit:limit ? Number(limit) : null, language:document.querySelector('#language').value, synthesis_mode:document.querySelector('#synthesis-mode').value, voice_id:document.querySelector('#voice-id').value || null, voice_description:document.querySelector('#voice-description').value, reference_text:document.querySelector('#reference-text').value, speaker:document.querySelector('#speaker').value, voice_instruction:document.querySelector('#instruction').value };
  const response = await fetch('/api/jobs', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) { const detail = await response.json(); error.textContent = JSON.stringify(detail.detail); return; }
  event.target.reset(); document.querySelector('#chapter-limit').value = 3; document.querySelector('#language').value = 'Auto'; await refresh();
});
document.querySelector('#refresh').addEventListener('click', refresh);
document.querySelector('#refresh-storage').addEventListener('click', refreshStorage);
jobsEl.addEventListener('click', async event => {
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
document.querySelector('#clear-jobs').addEventListener('click', async () => {
  if (!confirm('Remove every job from the main list? Generation will continue and files will be kept.')) return;
  await fetch('/api/jobs', {method:'DELETE'}); await refresh(); await refreshStorage();
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
refresh(); refreshVoices(); refreshStorage(); setInterval(() => { refresh(); refreshVoices(); }, 2500);
