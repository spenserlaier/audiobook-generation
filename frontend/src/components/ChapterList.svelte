<script>
  import { request } from '../api.js';

  let { jobId, total } = $props();
  let expanded = $state(false);
  let chapters = $state([]);
  let loading = $state(false);
  let error = $state('');

  async function loadNext() {
    loading = true; error = '';
    try {
      const items = await request(`/api/jobs/${jobId}/chapters?offset=${chapters.length}&limit=50`);
      chapters = [...chapters, ...items];
    } catch (exc) { error = exc.message; }
    finally { loading = false; }
  }

  async function toggle() {
    expanded = !expanded;
    if (expanded && chapters.length === 0) await loadNext();
  }
</script>

<div class="chapter-browser">
  <button class="quiet" type="button" onclick={toggle}>{expanded ? 'Hide chapters' : `Show chapters (${total})`}</button>
  {#if expanded}
    <div class="chapter-panel">
      <div class="chapters">
        {#each chapters as chapter, index (`${chapter.title}-${index}`)}
          <div class="chapter">
            <span>{chapter.title} <small>· {chapter.status}</small></span>
            {#if chapter.audio_url}<div class="audio-actions"><audio controls preload="none" src={chapter.audio_url}></audio><a class="download" href={chapter.audio_url} download>Download WAV</a></div>{/if}
          </div>
        {/each}
      </div>
      {#if error}<p class="failed">{error}</p>{/if}
      {#if chapters.length < total}<button class="quiet load-chapters" type="button" disabled={loading} onclick={loadNext}>{loading ? 'Loading…' : 'Load next 50'}</button>{/if}
    </div>
  {/if}
</div>
