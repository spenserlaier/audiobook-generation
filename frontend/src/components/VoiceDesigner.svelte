<script>
  import { jsonPost, request } from '../api.js';

  let { voices, onChanged } = $props();
  let name = $state('Narrator');
  let language = $state('Auto');
  let description = $state('A compelling, warm audiobook narrator with a clear mid-low register, measured pacing, subtle emotional range, crisp diction, and an intimate storytelling tone.');
  let referenceText = $state('The road disappeared into the evening mist, and with every quiet step, the old world fell farther behind. Ahead waited a story no one had dared to tell.');
  let error = $state('');
  let submitting = $state(false);
  let editingId = $state(null);
  let editingName = $state('');

  async function submit() {
    error = ''; submitting = true;
    try {
      await jsonPost('/api/voices', {name, language, description, reference_text: referenceText});
      await onChanged();
    } catch (exc) { error = exc.message; }
    finally { submitting = false; }
  }

  function beginRename(voice) {
    editingId = voice.id;
    editingName = voice.name;
  }

  async function rename(voice) {
    try {
      await request(`/api/voices/${voice.id}`, {
        method: 'PATCH', headers: {'content-type': 'application/json'},
        body: JSON.stringify({name: editingName}),
      });
      editingId = null;
      await onChanged();
    } catch (exc) { alert(exc.message); }
  }

  async function remove(voice) {
    if (!confirm(`Delete saved voice “${voice.name}” and its preview file?`)) return;
    try { await request(`/api/voices/${voice.id}`, {method: 'DELETE'}); await onChanged(); }
    catch (exc) { alert(exc.message); }
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
        <div>
          {#if editingId === voice.id}
            <form class="rename-voice" onsubmit={(event) => { event.preventDefault(); rename(voice); }}>
              <input bind:value={editingName} required maxlength="120" aria-label="Voice name" />
              <button class="quiet" type="submit">Save</button>
              <button class="quiet" type="button" onclick={() => editingId = null}>Cancel</button>
            </form>
          {:else}
            <strong>{voice.name}</strong> <small>· {voice.status}</small>
            <div class="voice-controls"><button class="quiet" type="button" onclick={() => beginRename(voice)}>Rename</button><button class="danger" type="button" onclick={() => remove(voice)}>Delete</button></div>
          {/if}
          {#if voice.error}<p class="failed">{voice.error}</p>{/if}
        </div>
        {#if voice.preview_url}<div class="audio-actions"><audio controls preload="none" src={voice.preview_url}></audio><a class="download" href={voice.preview_url} download>Download preview</a></div>{/if}
      </div>
    {/each}
  </div>
</section>
