<script>
  import { onMount } from 'svelte';
  import { request } from './api.js';
  import AudiobookForm from './components/AudiobookForm.svelte';
  import JobCard from './components/JobCard.svelte';
  import StorageView from './components/StorageView.svelte';
  import VoiceDesigner from './components/VoiceDesigner.svelte';

  let view = $state('generate');
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
  <nav class="tabs"><button class:active={view === 'generate'} class="tab" onclick={() => view = 'generate'}>Generate</button><button class:active={view === 'storage'} class="tab" onclick={() => view = 'storage'}>Storage</button></nav>
  {#if view === 'generate'}
    <VoiceDesigner {voices} onChanged={refreshVoices} />
    <AudiobookForm {voices} {sourceJob} onCreated={refreshJobs} onCancelRegeneration={() => sourceJob = null} />
    <div class="section-title"><h2>Jobs</h2><div class="section-actions"><button class="quiet" onclick={refreshJobs}>Refresh</button><button class="danger" onclick={clearQueue}>Clear queue</button><button class="quiet" onclick={clearJobs}>Clear list</button></div></div>
    {#if error}<p class="error">{error}</p>{/if}
    <div class="jobs">
      {#if jobs.length === 0}<p class="empty">No jobs yet.</p>{/if}
      {#each jobs as job (job.id)}<JobCard {job} onChanged={changed} onRegenerate={(selected) => sourceJob = selected} />{/each}
    </div>
  {:else}
    <StorageView onChanged={refreshJobs} />
  {/if}
</main>
