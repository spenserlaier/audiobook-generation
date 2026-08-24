<script>
  import { onMount } from 'svelte';
  import { formatBytes, request } from '../api.js';

  let { onChanged } = $props();
  let entries = $state([]);
  let error = $state('');

  async function refresh() {
    try { entries = await request('/api/storage'); error = ''; }
    catch (exc) { error = exc.message; }
  }

  async function remove(entry) {
    if (!confirm(`Permanently delete generated files for “${entry.title}”?`)) return;
    try { await request(`/api/storage/jobs/${entry.job_id}`, {method: 'DELETE'}); await refresh(); await onChanged(); }
    catch (exc) { alert(exc.message); }
  }

  async function clear() {
    if (!confirm('Permanently delete generated files for all finished runs? Active runs will be skipped.')) return;
    try {
      const result = await request('/api/storage', {method: 'DELETE'});
      alert(`Deleted artifacts for ${result.deleted} runs.${result.skipped_active ? ` Skipped ${result.skipped_active} active runs.` : ''}`);
      await refresh(); await onChanged();
    } catch (exc) { alert(exc.message); }
  }

  onMount(refresh);
</script>

<div class="section-title"><h2>Generated files</h2><div class="section-actions"><button class="quiet" onclick={refresh}>Refresh</button><button class="danger" onclick={clear}>Clear all artifacts</button></div></div>
{#if error}<p class="error">{error}</p>{/if}
<div class="jobs">
  {#if entries.length === 0}<p class="empty">No runs yet.</p>{/if}
  {#each entries as entry (entry.job_id)}
    <article class="job storage-item">
      <div><h3>{entry.title}</h3><small>{entry.file_count} files · {formatBytes(entry.size_bytes)} · {entry.status}{entry.hidden ? ' · hidden from jobs' : ''}</small></div>
      {#if entry.file_count}<button class="danger" type="button" onclick={() => remove(entry)}>Delete generated files</button>{:else}<small>Files already removed</small>{/if}
    </article>
  {/each}
</div>
