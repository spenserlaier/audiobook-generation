<script>
  import { onMount } from 'svelte';
  import { formatBytes, request } from '../api.js';

  let { jobId } = $props();
  let format = $state('mp3');
  let status = $state(null);
  let error = $state('');
  let starting = $state(false);

  async function refresh() {
    try {
      status = await request(`/api/jobs/${jobId}/download/status?format=${format}`);
      error = '';
    } catch (exc) { error = exc.message; }
  }

  async function prepare() {
    starting = true; error = '';
    try {
      status = await request(`/api/jobs/${jobId}/download/prepare?format=${format}`, {method: 'POST'});
    } catch (exc) { error = exc.message; }
    finally { starting = false; }
  }

  onMount(() => {
    refresh();
    const timer = setInterval(refresh, 2500);
    return () => clearInterval(timer);
  });
</script>

<div class="archive-control">
  <label>Export format<select bind:value={format} onchange={refresh}><option value="mp3">MP3</option><option value="wav">WAV</option></select></label>
  <div class="archive-action">
    {#if status?.state === 'ready'}
      <a class="download" href={status.download_url} download>Download {format.toUpperCase()} ZIP ({formatBytes(status.size_bytes)})</a>
    {:else if status?.state === 'preparing'}
      <button class="quiet" type="button" disabled>Preparing {format.toUpperCase()} ZIP… {status.completed_files}/{status.total_files} chapters</button>
    {:else}
      <button class="quiet" type="button" disabled={starting} onclick={prepare}>{starting ? 'Starting ZIP…' : `${status?.state === 'failed' ? 'Retry' : 'Prepare'} ${format.toUpperCase()} ZIP`}</button>
    {/if}
    {#if error || status?.error}<small class="failed">{error || status.error}</small>{/if}
  </div>
</div>
