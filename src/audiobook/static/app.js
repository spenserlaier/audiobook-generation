const jobsEl = document.querySelector('#jobs');
const voicesEl = document.querySelector('#voices');
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function chapters(job) {
  if (!['synthesizing','completed'].includes(job.status)) return '';
  const response = await fetch(`/api/jobs/${job.id}/chapters`);
  const items = await response.json();
  return `<div class="chapters">${items.map(c => `<div class="chapter"><span>${escapeHtml(c.title)} <small>· ${escapeHtml(c.status)}</small></span>${c.audio_url ? `<div class="audio-actions"><audio controls preload="none" src="${c.audio_url}"></audio><a class="download" href="${c.audio_url}" download>Download WAV</a></div>` : ''}</div>`).join('')}</div>`;
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
  if ([...jobsEl.querySelectorAll('audio')].some(player => !player.paused)) return;
  const response = await fetch('/api/jobs');
  const jobs = await response.json();
  if (!jobs.length) { jobsEl.innerHTML = '<p class="empty">No jobs yet.</p>'; return; }
  const cards = await Promise.all(jobs.map(async job => `<article class="job"><div class="job-head"><div><h3>${escapeHtml(job.title || 'Untitled audiobook')}</h3><small>${escapeHtml(job.novel_url)}</small></div><strong>${escapeHtml(job.status)}</strong></div><div class="bar"><span style="width:${Math.round(job.progress*100)}%"></span></div><small>${escapeHtml(job.stage)} · ${Math.round(job.progress*100)}%</small>${job.status === 'completed' ? `<p><a class="download" href="/api/jobs/${job.id}/download" download>Download all chapters (.zip)</a></p>` : ''}${job.voice_preview_url ? `<div class="chapter"><span>Designed voice preview</span><audio controls preload="none" src="${job.voice_preview_url}"></audio></div>` : ''}${job.error ? `<p class="failed">${escapeHtml(job.error)}</p>` : ''}${await chapters(job)}</article>`));
  jobsEl.innerHTML = cards.join('');
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
refresh(); refreshVoices(); setInterval(() => { refresh(); refreshVoices(); }, 2500);
