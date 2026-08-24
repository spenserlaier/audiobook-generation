<script>
  import { jsonPost } from '../api.js';

  let { voices, sourceJob = null, onCreated, onCancelRegeneration } = $props();
  let novelUrl = $state('');
  let title = $state('');
  let chapterScope = $state('first');
  let chapterLimit = $state(3);
  let language = $state('Auto');
  let synthesisMode = $state('designed_clone');
  let voiceId = $state('');
  let voiceDescription = $state('A compelling, warm audiobook narrator with a clear mid-low register, measured pacing, subtle emotional range, crisp diction, and an intimate storytelling tone.');
  let referenceText = $state('The road disappeared into the evening mist, and with every quiet step, the old world fell farther behind. Ahead waited a story no one had dared to tell.');
  let speaker = $state('Ryan');
  let instruction = $state('');
  let error = $state('');
  let submitting = $state(false);
  let loadedSourceId = $state(null);

  $effect(() => {
    if (sourceJob && sourceJob.id !== loadedSourceId) {
      loadedSourceId = sourceJob.id;
      novelUrl = sourceJob.novel_url;
      title = sourceJob.title ?? '';
      chapterScope = 'all';
      language = sourceJob.language;
      synthesisMode = sourceJob.synthesis_mode;
      voiceId = sourceJob.voice_id ?? '';
      voiceDescription = sourceJob.voice_description;
      referenceText = sourceJob.reference_text;
      speaker = sourceJob.speaker;
      instruction = sourceJob.voice_instruction;
      document.querySelector('#job-form')?.scrollIntoView({behavior: 'smooth'});
    }
    if (!sourceJob) loadedSourceId = null;
  });

  async function submit() {
    error = ''; submitting = true;
    try {
      await jsonPost('/api/jobs', {
        novel_url: novelUrl, title: title || null,
        chapter_limit: chapterScope === 'all' ? null : Number(chapterLimit),
        language, synthesis_mode: synthesisMode, voice_id: voiceId || null,
        source_job_id: sourceJob?.id ?? null, voice_description: voiceDescription,
        reference_text: referenceText, speaker, voice_instruction: instruction,
      });
      novelUrl = ''; title = ''; chapterScope = 'first'; chapterLimit = 3; language = 'Auto';
      onCancelRegeneration(); await onCreated();
    } catch (exc) { error = exc.message; }
    finally { submitting = false; }
  }
</script>

<section class="panel">
  <form id="job-form" onsubmit={(event) => { event.preventDefault(); submit(); }}>
    {#if sourceJob}<div class="notice"><span>Using saved chapters from <strong>{sourceJob.title || 'Untitled audiobook'}</strong>; the crawler will be skipped.</span><button class="quiet" type="button" onclick={onCancelRegeneration}>Use a new crawl</button></div>{/if}
    <label>Novel URL<input bind:value={novelUrl} type="url" required placeholder="https://supported-site.example/novel" /></label>
    <div class="row">
      <label>Title (optional)<input bind:value={title} maxlength="300" placeholder="Use a friendly library title" /></label>
      <label>Chapter scope<select bind:value={chapterScope}><option value="first">First N chapters</option><option value="all">All chapters</option></select></label>
    </div>
    {#if chapterScope === 'first'}<label>Number of chapters<input bind:value={chapterLimit} type="number" min="1" max="10000" required /></label>{/if}
    <div class="row">
      <label>Language<input bind:value={language} /></label>
      <label>Voice workflow<select bind:value={synthesisMode}><option value="designed_clone">Design + clone (recommended)</option><option value="custom_voice">Built-in Qwen voice</option></select></label>
    </div>
    {#if synthesisMode === 'designed_clone'}
      <div class="voice-fields">
        <label>Saved narrator<select bind:value={voiceId}><option value="">Create a new voice for this job</option>{#each voices.filter((voice) => voice.status === 'ready') as voice}<option value={voice.id}>{voice.name}</option>{/each}</select></label>
        <label>Narrative voice description<textarea bind:value={voiceDescription} maxlength="1000" rows="4"></textarea></label>
        <label>Reference script<textarea bind:value={referenceText} maxlength="1000" rows="3"></textarea></label>
        <p class="hint">VoiceDesign reads this short script, then the Base model clones that result consistently across every chapter.</p>
      </div>
    {:else}
      <div class="row">
        <label>Speaker<select bind:value={speaker}>{#each ['Ryan','Aiden','Vivian','Serena','Uncle_Fu','Dylan','Eric','Ono_Anna','Sohee'] as name}<option>{name}</option>{/each}</select></label>
        <label>Voice direction<input bind:value={instruction} maxlength="500" placeholder="Calm, measured narration" /></label>
      </div>
    {/if}
    <div class="actions"><button disabled={submitting}>{submitting ? 'Queueing…' : sourceJob ? 'Regenerate audiobook' : 'Start audiobook'}</button><a href="https://github.com/lncrawl/lightnovel-crawler#supported-sources" target="_blank" rel="noreferrer">Browse supported sources ↗</a></div>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
  </form>
</section>
