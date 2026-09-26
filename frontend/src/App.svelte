<script>
  import { onMount } from 'svelte';
  import { request } from './api.js';
  import AudiobookForm from './components/AudiobookForm.svelte';
  import JobCard from './components/JobCard.svelte';
  import StorageView from './components/StorageView.svelte';
  import VoiceDesigner from './components/VoiceDesigner.svelte';

  let view = $state('narrators');
  let jobs = $state([]);
  let voices = $state([]);
  let sourceJob = $state(null);
  let error = $state('');

  async function refreshJobs() {
    try { jobs = await request('/api/jobs'); error = ''; }
    catch (exc) { error = exc.message; }
  }
  async function refreshVoices() {
    try { voices = await request('/api/voices'); }
    catch (exc) { error = exc.message; }
  }
  async function changed() {
    await refreshJobs();
  }
  async function created() {
    await refreshJobs();
    view = 'jobs';
  }
  function regenerate(job) {
    sourceJob = job;
    view = 'audiobooks';
  }
  async function clearJobs() {
    if (!confirm('Remove every job from the main list? Generation will continue and files will be kept.')) return;
    try { await request('/api/jobs', {method: 'DELETE'}); await refreshJobs(); }
    catch (exc) { alert(exc.message); }
  }
  async function clearQueue() {
    if (!confirm('Cancel every job still waiting for a worker?')) return;
    try { const result = await request('/api/jobs/cancel-pending', {method: 'POST'}); alert(`Cancelled ${result.cancelled} queued jobs.`); await refreshJobs(); }
    catch (exc) { alert(exc.message); }
  }

  onMount(() => {
    refreshJobs(); refreshVoices();
    const timer = setInterval(() => { refreshJobs(); refreshVoices(); }, 2500);
    return () => clearInterval(timer);
  });
</script>

<main>
  <header><p class="eyebrow">LOCAL AUDIOBOOK STUDIO</p><h1>Audiobook Foundry</h1><p>Crawl a novel, design its narrator, and generate an audiobook locally.</p></header>
  <nav class="tabs" aria-label="Main sections">
    <button class:active={view === 'narrators'} class="tab" aria-current={view === 'narrators' ? 'page' : undefined} onclick={() => view = 'narrators'}>Narrators</button>
    <button class:active={view === 'audiobooks'} class="tab" aria-current={view === 'audiobooks' ? 'page' : undefined} onclick={() => view = 'audiobooks'}>Audiobooks</button>
    <button class:active={view === 'jobs'} class="tab" aria-current={view === 'jobs' ? 'page' : undefined} onclick={() => view = 'jobs'}>Jobs</button>
    <button class:active={view === 'storage'} class="tab" aria-current={view === 'storage' ? 'page' : undefined} onclick={() => view = 'storage'}>Storage</button>
  </nav>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  <div hidden={view !== 'narrators'}>
    <VoiceDesigner {voices} onChanged={refreshVoices} />
  </div>
  <div hidden={view !== 'audiobooks'}>
    <AudiobookForm {voices} {sourceJob} onCreated={created} onCancelRegeneration={() => sourceJob = null} />
  </div>
  {#if view === 'jobs'}
    <div class="section-title"><h2>Jobs</h2><div class="section-actions"><button class="quiet" onclick={refreshJobs}>Refresh</button><button class="danger" onclick={clearQueue}>Clear queue</button><button class="quiet" onclick={clearJobs}>Clear list</button></div></div>
    <div class="jobs">
      {#if jobs.length === 0}<p class="empty">No jobs yet.</p>{/if}
      {#each jobs as job (job.id)}<JobCard {job} onChanged={changed} onRegenerate={regenerate} />{/each}
    </div>
  {:else if view === 'storage'}
    <StorageView onChanged={refreshJobs} />
  {/if}
</main>
