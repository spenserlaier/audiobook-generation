<script>
  import { request } from '../api.js';
  import ArchiveControl from './ArchiveControl.svelte';
  import ChapterList from './ChapterList.svelte';

  let { job, onChanged, onRegenerate } = $props();
  const activeStatuses = ['queued', 'crawling', 'synthesizing'];

  async function cancel() {
    if (!confirm('Cancel this job? Any current crawler process will be stopped.')) return;
    try { await request(`/api/jobs/${job.id}/cancel`, {method: 'POST'}); await onChanged(); }
    catch (exc) { alert(exc.message); }
  }

  async function remove() {
    try { await request(`/api/jobs/${job.id}`, {method: 'DELETE'}); await onChanged(true); }
    catch (exc) { alert(exc.message); }
  }
</script>

<article class="job">
  <div class="job-head">
    <div><h3>{job.title || 'Untitled audiobook'}</h3><small>{job.novel_url}</small></div>
    <div class="job-controls">
      <strong>{job.status}</strong>
      {#if job.chapters_total && !activeStatuses.includes(job.status)}<button class="quiet" type="button" onclick={() => onRegenerate(job)}>Regenerate</button>{/if}
      {#if activeStatuses.includes(job.status)}<button class="danger" type="button" onclick={cancel}>Cancel</button>{/if}
      <button class="quiet remove-job" type="button" onclick={remove}>Remove from list</button>
    </div>
  </div>
  <div class="bar"><span style:width={`${Math.round(job.progress * 100)}%`}></span></div>
  <small>{job.stage} · {Math.round(job.progress * 100)}%</small>
  {#if job.status === 'completed' && job.output_dir}<ArchiveControl jobId={job.id} />{/if}
  {#if job.voice_preview_url}<div class="chapter"><span>Designed voice preview</span><audio controls preload="none" src={job.voice_preview_url}></audio></div>{/if}
  {#if job.error}<p class="failed">{job.error}</p>{/if}
  {#if job.chapters_total}<ChapterList jobId={job.id} total={job.chapters_total} />{/if}
</article>
