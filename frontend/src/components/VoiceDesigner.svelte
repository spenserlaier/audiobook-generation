<script>
  import { jsonPost } from '../api.js';

  let { voices, onChanged } = $props();
  let name = $state('Narrator');
  let language = $state('Auto');
  let description = $state('A compelling, warm audiobook narrator with a clear mid-low register, measured pacing, subtle emotional range, crisp diction, and an intimate storytelling tone.');
  let referenceText = $state('The road disappeared into the evening mist, and with every quiet step, the old world fell farther behind. Ahead waited a story no one had dared to tell.');
  let error = $state('');
  let submitting = $state(false);

  async function submit() {
    error = ''; submitting = true;
    try {
      await jsonPost('/api/voices', {name, language, description, reference_text: referenceText});
      await onChanged();
    } catch (exc) { error = exc.message; }
    finally { submitting = false; }
  }
</script>

<section class="panel">
  <h2>Design a narrator</h2>
  <p class="hint">Generate and audition a reusable voice before choosing a novel.</p>
  <form onsubmit={(event) => { event.preventDefault(); submit(); }}>
    <div class="row">
      <label>Voice name<input bind:value={name} maxlength="120" required /></label>
      <label>Language<input bind:value={language} /></label>
    </div>
    <label>Voice description<textarea bind:value={description} maxlength="1000" rows="4"></textarea></label>
    <label>Preview script<textarea bind:value={referenceText} maxlength="1000" rows="3"></textarea></label>
    <div class="actions"><button disabled={submitting}>{submitting ? 'Queueing…' : 'Generate voice preview'}</button></div>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
  </form>
  <div class="voices">
    {#if voices.length === 0}<p class="empty">No saved voices yet.</p>{/if}
    {#each voices as voice (voice.id)}
      <div class="voice">
        <div><strong>{voice.name}</strong> <small>· {voice.status}</small>{#if voice.error}<p class="failed">{voice.error}</p>{/if}</div>
        {#if voice.preview_url}<div class="audio-actions"><audio controls preload="none" src={voice.preview_url}></audio><a class="download" href={voice.preview_url} download>Download preview</a></div>{/if}
      </div>
    {/each}
  </div>
</section>
