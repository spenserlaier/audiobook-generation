const jobsEl = document.querySelector('#jobs');
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function chapters(job) {
  if (!['synthesizing','completed'].includes(job.status)) return '';
  const response = await fetch(`/api/jobs/${job.id}/chapters`);
  const items = await response.json();
  return `<div class="chapters">${items.map(c => `<div class="chapter"><span>${escapeHtml(c.title)} <small>· ${escapeHtml(c.status)}</small></span>${c.audio_url ? `<audio controls preload="none" src="${c.audio_url}"></audio>` : ''}</div>`).join('')}</div>`;
}

async function refresh() {
  const response = await fetch('/api/jobs');
  const jobs = await response.json();
  if (!jobs.length) { jobsEl.innerHTML = '<p class="empty">No jobs yet.</p>'; return; }
  const cards = await Promise.all(jobs.map(async job => `<article class="job"><div class="job-head"><div><h3>${escapeHtml(job.title || 'Untitled audiobook')}</h3><small>${escapeHtml(job.novel_url)}</small></div><strong>${escapeHtml(job.status)}</strong></div><div class="bar"><span style="width:${Math.round(job.progress*100)}%"></span></div><small>${escapeHtml(job.stage)} · ${Math.round(job.progress*100)}%</small>${job.voice_preview_url ? `<div class="chapter"><span>Designed voice preview</span><audio controls preload="none" src="${job.voice_preview_url}"></audio></div>` : ''}${job.error ? `<p class="failed">${escapeHtml(job.error)}</p>` : ''}${await chapters(job)}</article>`));
  jobsEl.innerHTML = cards.join('');
}

document.querySelector('#job-form').addEventListener('submit', async event => {
  event.preventDefault(); const error = document.querySelector('#form-error'); error.textContent = '';
  const limit = document.querySelector('#chapter-limit').value;
  const body = { novel_url:document.querySelector('#novel-url').value, title:document.querySelector('#title').value || null, chapter_limit:limit ? Number(limit) : null, language:document.querySelector('#language').value, synthesis_mode:document.querySelector('#synthesis-mode').value, voice_description:document.querySelector('#voice-description').value, reference_text:document.querySelector('#reference-text').value, speaker:document.querySelector('#speaker').value, voice_instruction:document.querySelector('#instruction').value };
  const response = await fetch('/api/jobs', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) { const detail = await response.json(); error.textContent = JSON.stringify(detail.detail); return; }
  event.target.reset(); document.querySelector('#chapter-limit').value = 3; document.querySelector('#language').value = 'Auto'; await refresh();
});
document.querySelector('#refresh').addEventListener('click', refresh);
document.querySelector('#synthesis-mode').addEventListener('change', event => {
  const designed = event.target.value === 'designed_clone';
  document.querySelector('#designed-voice-fields').hidden = !designed;
  document.querySelector('#custom-voice-fields').hidden = designed;
});
refresh(); setInterval(refresh, 2500);
