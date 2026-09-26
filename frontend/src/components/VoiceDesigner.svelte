<script>
  import { jsonPost, request } from '../api.js';

  const adjectives = ['Airy', 'Amber', 'Bright', 'Breezy', 'Calm', 'Clear', 'Crisp', 'Dreamy', 'Gentle', 'Golden', 'Lively', 'Mellow', 'Quiet', 'Silvery', 'Soft', 'Steady', 'Velvet', 'Warm'];
  const nouns = ['Badger', 'Bear', 'Finch', 'Fox', 'Heron', 'Lark', 'Lynx', 'Marten', 'Ostrich', 'Otter', 'Owl', 'Puffin', 'Raven', 'Robin', 'Seal', 'Sparrow', 'Wolf', 'Wren'];

  function randomNarratorName(existing = []) {
    const used = new Set(existing.map((voice) => voice.name));
    let candidate;
    for (let attempt = 0; attempt < 100; attempt++) {
      const first = Math.floor(Math.random() * adjectives.length);
      let second = Math.floor(Math.random() * (adjectives.length - 1));
      if (second >= first) second++;
      candidate = `${adjectives[first]} ${adjectives[second]} ${nouns[Math.floor(Math.random() * nouns.length)]}`;
      if (!used.has(candidate)) return candidate;
    }
    let suffix = 2;
    while (used.has(`${candidate} ${suffix}`)) suffix++;
    return `${candidate} ${suffix}`;
  }

  let { voices, onChanged } = $props();
  let name = $state(randomNarratorName());
  let nameEdited = $state(false);
  let language = $state('Auto');
  let ttsProvider = $state('qwen');
  let description = $state('A compelling, warm audiobook narrator with a clear mid-low register, measured pacing, subtle emotional range, crisp diction, and an intimate storytelling tone.');
  let referenceText = $state('The road disappeared into the evening mist, and with every quiet step, the old world fell farther behind. Ahead waited a story no one had dared to tell.');
  let error = $state('');
  let submitting = $state(false);
  let editingId = $state(null);
  let editingName = $state('');

  $effect(() => {
    if (!nameEdited && voices.some((voice) => voice.name === name)) name = randomNarratorName(voices);
  });

  async function submit() {
    error = ''; submitting = true;
    try {
      const submittedName = name;
      await jsonPost('/api/voices', {name, language, tts_provider: ttsProvider, description, reference_text: referenceText});
      await onChanged();
      name = randomNarratorName([...voices, {name: submittedName}]);
      nameEdited = false;
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

  async function retry(voice) {
    try {
      await request(`/api/voices/${voice.id}/retry`, {method: 'POST'});
      await onChanged();
    } catch (exc) { alert(exc.message); }
  }

  function useDescription(voice) {
    description = voice.description;
    const field = document.getElementById('narrator-description');
    field?.scrollIntoView({behavior: 'smooth', block: 'center'});
    field?.focus({preventScroll: true});
  }

  function useScript(voice) {
    referenceText = voice.reference_text;
    const field = document.getElementById('narrator-script');
    field?.scrollIntoView({behavior: 'smooth', block: 'center'});
    field?.focus({preventScroll: true});
  }
</script>

<section class="panel">
  <h2>Design a narrator</h2>
  <p class="hint">Generate and audition a reusable voice before choosing a novel.</p>
  <form onsubmit={(event) => { event.preventDefault(); submit(); }}>
    <div class="row">
      <label>Voice name<input bind:value={name} oninput={() => nameEdited = true} maxlength="120" required /></label>
      <label>Language<input bind:value={language} /></label>
    </div>
    <label>TTS model<select bind:value={ttsProvider}><option value="qwen">Qwen3-TTS</option><option value="breeze">Breeze TTS 2</option></select></label>
    <label>Voice description<textarea id="narrator-description" bind:value={description} maxlength="1000" rows="4"></textarea></label>
    <label>Preview script<textarea id="narrator-script" bind:value={referenceText} maxlength="1000" rows="3"></textarea></label>
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
            <strong>{voice.name}</strong> <small>· {voice.tts_provider === 'breeze' ? 'Breeze TTS 2' : 'Qwen3-TTS'} · {voice.status}</small>
            <div class="voice-controls">{#if voice.status === 'failed'}<button class="quiet" type="button" onclick={() => retry(voice)}>Retry</button>{/if}<button class="quiet" type="button" onclick={() => beginRename(voice)}>Rename</button><button class="danger" type="button" onclick={() => remove(voice)}>Delete</button></div>
          {/if}
          {#if voice.error}<p class="failed">{voice.error}</p>{/if}
        </div>
        {#if voice.preview_url}<div class="audio-actions"><audio controls preload="none" src={voice.preview_url}></audio><a class="download" href={voice.preview_url} download>Download preview</a></div>{/if}
        <details class="voice-settings">
          <summary>View settings</summary>
          <div class="voice-setting">
            <div class="voice-setting-heading"><strong>Voice description</strong><button class="quiet" type="button" onclick={() => useDescription(voice)}>Use description</button></div>
            <p>{voice.description}</p>
          </div>
          <div class="voice-setting">
            <div class="voice-setting-heading"><strong>Preview script</strong><button class="quiet" type="button" onclick={() => useScript(voice)}>Use script</button></div>
            <p>{voice.reference_text}</p>
          </div>
        </details>
      </div>
    {/each}
  </div>
</section>
