const state = {
  presets: [],
  availableGenres: [],
  availableProductionStyles: [],
  availableArrangementStyles: [],
  selectedPresetId: "",
  selectedMoods: new Set(),
  selectedInstruments: new Set(),
  latestPreview: null,
  latestJob: null,
  latestImprovedLyrics: null,
  latestSuggestion: null,
  latestStems: null,
  latestSectionEdit: null,
  latestProjects: [],
  latestProject: null,
  latestExport: null,
  latestVocalUpload: null,
  latestReferenceUpload: null,
  latestVocalAnalysis: null,
  latestOnlineResponse: null,
  generationMode: "mock",
};

const commonMoods = [
  "heartbreak",
  "longing",
  "emotional",
  "romantic",
  "intimate",
  "nostalgic",
  "soft",
  "late-night",
  "dreamy",
  "devotional",
  "spiritual",
  "powerful",
  "dark",
  "modern",
  "peaceful",
  "warm",
  "anthemic",
];

const commonInstruments = [
  "piano",
  "strings",
  "pads",
  "clean guitar",
  "soft drums",
  "bass",
  "acoustic guitar",
  "electric piano",
  "vinyl texture",
  "sub bass",
  "harmonium",
  "tabla",
  "dholak",
  "claps",
  "chorus vocals",
  "808 bass",
  "trap drums",
  "Indian flute texture",
  "tanpura",
  "flute",
  "electric guitar",
  "backing vocals",
];

const byId = (id) => document.getElementById(id);

const refs = {
  backendPill: byId("backend-pill"),
  phasePill: byId("phase-pill"),
  jobStatusPill: byId("job-status-pill"),
  lyricsInput: byId("lyrics-input"),
  languageSelect: byId("language-select"),
  presetSelect: byId("preset-select"),
  presetName: byId("preset-name"),
  presetDescription: byId("preset-description"),
  projectNameInput: byId("project-name-input"),
  projectStatus: byId("project-status"),
  saveProjectButton: byId("save-project-button"),
  saveJobProjectButton: byId("save-job-project-button"),
  projectListSelect: byId("project-list-select"),
  loadProjectButton: byId("load-project-button"),
  refreshProjectsButton: byId("refresh-projects-button"),
  genreSelect: byId("genre-select"),
  productionStyleSelect: byId("production-style-select"),
  arrangementStyleSelect: byId("arrangement-style-select"),
  moodChips: byId("mood-chips"),
  instrumentChips: byId("instrument-chips"),
  moodCount: byId("mood-count"),
  instrumentCount: byId("instrument-count"),
  bpmInput: byId("bpm-input"),
  keyInput: byId("key-input"),
  durationInput: byId("duration-input"),
  energySelect: byId("energy-select"),
  vocalPathInput: byId("vocal-path-input"),
  vocalUploadInput: byId("vocal-upload-input"),
  referenceUploadInput: byId("reference-upload-input"),
  uploadVocalButton: byId("upload-vocal-button"),
  uploadReferenceButton: byId("upload-reference-button"),
  analyzeVocalButton: byId("analyze-vocal-button"),
  vocalToMusicButton: byId("vocal-to-music-button"),
  musicToMusicButton: byId("music-to-music-button"),
  regenerateOnlineButton: byId("regenerate-online-button"),
  onlineStatus: byId("online-status"),
  onlineProviderSelect: byId("online-provider-select"),
  candidateCountInput: byId("candidate-count-input"),
  referenceStrengthInput: byId("reference-strength-input"),
  musicSourceModeSelect: byId("music-source-mode-select"),
  preserveOriginalVocalToggle: byId("preserve-original-vocal-toggle"),
  rightsConfirmedToggle: byId("rights-confirmed-toggle"),
  onlineInstructionInput: byId("online-instruction-input"),
  onlineOutput: byId("online-output"),
  sourcePreparationGrid: byId("source-preparation-grid"),
  candidateGrid: byId("candidate-grid"),
  vocalGainInput: byId("vocal-gain-input"),
  backingGainInput: byId("backing-gain-input"),
  vocalForwardToggle: byId("vocal-forward-toggle"),
  duckingEnabledToggle: byId("ducking-enabled-toggle"),
  duckingAmountInput: byId("ducking-amount-input"),
  previewButton: byId("preview-button"),
  generateButton: byId("generate-button"),
  manualMixButton: byId("manual-mix-button"),
  improveLyricsButton: byId("improve-lyrics-button"),
  suggestStyleButton: byId("suggest-style-button"),
  explainQualityButton: byId("explain-quality-button"),
  applyLyricsButton: byId("apply-lyrics-button"),
  applyStyleButton: byId("apply-style-button"),
  assistantStatus: byId("assistant-status"),
  assistantOutput: byId("assistant-output"),
  assistantWarningList: byId("assistant-warning-list"),
  stemsStatus: byId("stems-status"),
  stemsSourceInput: byId("stems-source-input"),
  separateStemsButton: byId("separate-stems-button"),
  stemsOutput: byId("stems-output"),
  stemPlayerGrid: byId("stem-player-grid"),
  sectionStatus: byId("section-status"),
  sectionNameSelect: byId("section-name-select"),
  sectionStartInput: byId("section-start-input"),
  sectionEndInput: byId("section-end-input"),
  sectionInstructionInput: byId("section-instruction-input"),
  buildSectionPromptButton: byId("build-section-prompt-button"),
  editSectionButton: byId("edit-section-button"),
  sectionOutput: byId("section-output"),
  sectionAudio: byId("section-audio"),
  positivePrompt: byId("positive-prompt"),
  negativePrompt: byId("negative-prompt"),
  summaryList: byId("summary-list"),
  settingsList: byId("settings-list"),
  warningList: byId("warning-list"),
  jobProgress: byId("job-progress"),
  jobMessage: byId("job-message"),
  diagnosticsGrid: byId("diagnostics-grid"),
  diagnosticLogs: byId("diagnostic-logs"),
  mixDiagnosticsGrid: byId("mix-diagnostics-grid"),
  qualityGrid: byId("quality-grid"),
  exportManifestButton: byId("export-manifest-button"),
  exportOutput: byId("export-output"),
  manifestLink: byId("manifest-link"),
  healthButton: byId("health-button"),
  healthOutput: byId("health-output"),
  cleanupButton: byId("cleanup-button"),
  cleanupOutput: byId("cleanup-output"),
  audioPlaceholder: byId("audio-placeholder"),
  audioPlaceholderText: byId("audio-placeholder-text"),
  generatedAudio: byId("generated-audio"),
  mixedPlaceholder: byId("mixed-placeholder"),
  mixedPlaceholderText: byId("mixed-placeholder-text"),
  mixedAudio: byId("mixed-audio"),
};

async function loadPresets() {
  try {
    await loadGenerationMode();
    const data = await jsonFetch("/presets");
    state.presets = data.presets || [];
    state.availableGenres = data.available_genres || [];
    state.availableProductionStyles = data.available_production_styles || [];
    state.availableArrangementStyles = data.available_arrangement_styles || [];
    state.selectedPresetId = data.default_preset_id || state.presets[0]?.id || "";

    replaceOptions(refs.genreSelect, state.availableGenres);
    replaceOptions(refs.productionStyleSelect, state.availableProductionStyles);
    replaceOptions(refs.arrangementStyleSelect, state.availableArrangementStyles);
    replaceOptions(
      refs.presetSelect,
      state.presets,
      (preset) => preset.id,
      (preset) => preset.name
    );
    refs.presetSelect.value = state.selectedPresetId;
    applyPreset(currentPreset());
    setPill(refs.backendPill, "Backend ready");
    await previewPrompt();
    await loadProjects(true);
    await loadOnlineJobFromUrl();
  } catch (error) {
    setPill(refs.backendPill, "Backend offline", "bad");
    refs.positivePrompt.textContent = error.message;
  }
}

async function loadOnlineJobFromUrl() {
  const jobId = new URLSearchParams(window.location.search).get("online_job_id");
  if (!jobId) return;
  try {
    const job = await jsonFetch(`/jobs/${encodeURIComponent(jobId)}`);
    if (!job.online_response) {
      throw new Error("The requested job does not contain music transformation candidates.");
    }
    renderOnlineResponse(job.online_response);
  } catch (error) {
    refs.onlineStatus.textContent = "Could not load job";
    refs.onlineOutput.textContent = error.message;
  }
}

async function loadGenerationMode() {
  try {
    const health = await jsonFetch("/ace-step/health");
    state.generationMode = health.enabled ? "ace_step" : "mock";
    if (health.enabled) {
      const label = health.procedural_fallback_enabled
        ? "ACE-Step enabled + fallback"
        : "ACE-Step enabled";
      setPill(refs.phasePill, health.available ? label : "ACE-Step needs setup", health.available ? "" : "bad");
    } else {
      setPill(refs.phasePill, "Mock mode", "muted");
    }
  } catch (_error) {
    state.generationMode = "mock";
    setPill(refs.phasePill, "Mock mode", "muted");
  }
}

function replaceOptions(select, values, valueFor = (item) => item, labelFor = (item) => item) {
  select.replaceChildren();
  for (const item of values) {
    const option = document.createElement("option");
    option.value = valueFor(item);
    option.textContent = labelFor(item);
    select.appendChild(option);
  }
}

function currentPreset() {
  return state.presets.find((preset) => preset.id === state.selectedPresetId) || state.presets[0] || null;
}

function applyPreset(preset) {
  if (!preset) return;
  state.selectedPresetId = preset.id;
  refs.presetName.textContent = preset.name;
  refs.presetDescription.textContent = preset.description;
  refs.genreSelect.value = preset.genre;
  refs.productionStyleSelect.value = preset.production_style;
  refs.arrangementStyleSelect.value = preset.arrangement_style;
  refs.bpmInput.value = preset.default_bpm || 88;
  refs.durationInput.value = defaultDuration(preset.duration_range);
  refs.keyInput.value = defaultKey(preset.key_suggestions) || "";
  state.selectedMoods = new Set(preset.mood_tags || []);
  state.selectedInstruments = new Set(preset.instruments || []);
  renderChips();
}

function defaultDuration(range) {
  if (!Array.isArray(range) || range.length !== 2) return 90;
  return Math.min(Math.max(90, Number(range[0])), Number(range[1]));
}

function defaultKey(suggestions) {
  if (!Array.isArray(suggestions)) return "";
  return suggestions.find((item) => /major|minor/i.test(item) && !/keys|\//i.test(item)) || "";
}

function renderChips() {
  const preset = currentPreset();
  const moods = unique([...(preset?.mood_tags || []), ...commonMoods]);
  const instruments = unique([...(preset?.instruments || []), ...commonInstruments]);
  renderChipGroup(refs.moodChips, moods, state.selectedMoods, () => {
    refs.moodCount.textContent = `${state.selectedMoods.size} selected`;
  });
  renderChipGroup(refs.instrumentChips, instruments, state.selectedInstruments, () => {
    refs.instrumentCount.textContent = `${state.selectedInstruments.size} selected`;
  });
  refs.moodCount.textContent = `${state.selectedMoods.size} selected`;
  refs.instrumentCount.textContent = `${state.selectedInstruments.size} selected`;
}

function renderChipGroup(container, values, selectedSet, afterToggle) {
  container.replaceChildren();
  for (const value of values) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = selectedSet.has(value) ? "chip selected" : "chip";
    button.textContent = value;
    button.addEventListener("click", () => {
      if (selectedSet.has(value)) {
        selectedSet.delete(value);
      } else {
        selectedSet.add(value);
      }
      button.classList.toggle("selected", selectedSet.has(value));
      afterToggle();
    });
    container.appendChild(button);
  }
}

function selectedOverrides() {
  return {
    bpm: parseNullableNumber(refs.bpmInput.value),
    key: refs.keyInput.value.trim() || null,
    duration_seconds: parseNullableNumber(refs.durationInput.value),
    energy: refs.energySelect.value || null,
    vocal_gain_db: parseNullableNumber(refs.vocalGainInput.value),
    backing_gain_db: parseNullableNumber(refs.backingGainInput.value),
    ducking_enabled: refs.duckingEnabledToggle.checked,
    ducking_amount: parseNullableNumber(refs.duckingAmountInput.value),
    vocal_forward_mix: refs.vocalForwardToggle.checked,
  };
}

function buildRequest() {
  const overrides = selectedOverrides();
  return removeNullish({
    preset_id: state.selectedPresetId || null,
    lyrics: refs.lyricsInput.value,
    language: refs.languageSelect.value,
    genre: refs.genreSelect.value,
    production_style: refs.productionStyleSelect.value,
    arrangement_style: refs.arrangementStyleSelect.value,
    mood_tags: Array.from(state.selectedMoods),
    instruments: Array.from(state.selectedInstruments),
    output_format: "mp3",
    vocal_audio_path: refs.vocalPathInput.value.trim() || null,
    ...overrides,
  });
}

async function previewPrompt() {
  refs.previewButton.disabled = true;
  try {
    const data = await jsonFetch("/prompt/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRequest()),
    });
    state.latestPreview = data;
    renderPromptData(data);
    setPill(refs.jobStatusPill, "Prompt ready");
  } catch (error) {
    setPill(refs.jobStatusPill, "Preview failed", "bad");
    refs.positivePrompt.textContent = error.message;
  } finally {
    refs.previewButton.disabled = false;
  }
}

async function generateMock() {
  refs.generateButton.disabled = true;
  try {
    const data = await jsonFetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRequest()),
    });
    state.latestJob = data;
    renderJob(data);
    renderPromptData(data);
    setPill(refs.jobStatusPill, data.status, statusVariant(data.status));
    const loaded = await jsonFetch(`/jobs/${data.job_id}`);
    state.latestJob = loaded;
    renderJob(loaded);
    await explainQuality(loaded, true);
  } catch (error) {
    setPill(refs.jobStatusPill, "Generate failed", "bad");
    refs.jobMessage.textContent = error.message;
  } finally {
    refs.generateButton.disabled = false;
  }
}

async function uploadAudio(kind) {
  const input = kind === "vocal" ? refs.vocalUploadInput : refs.referenceUploadInput;
  const file = input?.files?.[0];
  if (!file) {
    refs.onlineOutput.textContent = `Choose a ${kind} audio file first.`;
    return;
  }
  const button = kind === "vocal" ? refs.uploadVocalButton : refs.uploadReferenceButton;
  button.disabled = true;
  try {
    const form = new FormData();
    form.append("file", file);
    const data = await jsonFetch("/uploads/audio", { method: "POST", body: form });
    if (kind === "vocal") {
      state.latestVocalUpload = data;
      refs.vocalPathInput.value = data.original_path || "";
    } else {
      state.latestReferenceUpload = data;
    }
    refs.onlineStatus.textContent = `${kind} uploaded`;
    refs.onlineOutput.textContent = [
      `${kind} upload_id: ${data.upload_id}`,
      `duration: ${formatMaybe(data.duration_seconds, "s")}`,
      `path: ${data.original_path || ""}`,
      ...(data.warnings || []).map((warning) => `warning: ${warning}`),
    ].join("\n");
  } catch (error) {
    refs.onlineStatus.textContent = "Upload failed";
    refs.onlineOutput.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function analyzeUploadedVocal() {
  const uploadId = state.latestVocalUpload?.upload_id;
  if (!uploadId) {
    refs.onlineOutput.textContent = "Upload a vocal first.";
    return;
  }
  refs.analyzeVocalButton.disabled = true;
  try {
    const data = await jsonFetch(`/uploads/${encodeURIComponent(uploadId)}/analyze`, { method: "POST" });
    state.latestVocalAnalysis = data;
    refs.onlineStatus.textContent = "Vocal analyzed";
    refs.onlineOutput.textContent = [
      `duration: ${formatMaybe(data.duration_seconds, "s")}`,
      `estimated BPM: ${formatMaybe(data.estimated_bpm, "")}`,
      `estimated key: ${data.estimated_key || "unknown"}`,
      `phrases: ${(data.phrase_boundaries || []).length}`,
      `sections: ${(data.section_candidates || []).map((item) => item.name).join(", ") || "approximate"}`,
      ...(data.warnings || []).map((warning) => `warning: ${warning}`),
    ].join("\n");
  } catch (error) {
    refs.onlineStatus.textContent = "Analysis failed";
    refs.onlineOutput.textContent = error.message;
  } finally {
    refs.analyzeVocalButton.disabled = false;
  }
}

async function generateVocalToMusic() {
  const uploadId = state.latestVocalUpload?.upload_id;
  if (!uploadId) {
    refs.onlineOutput.textContent = "Upload a vocal first.";
    return;
  }
  refs.vocalToMusicButton.disabled = true;
  try {
    const data = await jsonFetch("/v2/vocal-to-music", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId, ...buildOnlinePayload(false) }),
    });
    renderOnlineResponse(data);
  } catch (error) {
    refs.onlineStatus.textContent = "Generation failed";
    refs.onlineOutput.textContent = error.message;
  } finally {
    refs.vocalToMusicButton.disabled = false;
  }
}

async function generateMusicToMusic() {
  const referenceId = state.latestReferenceUpload?.upload_id;
  if (!referenceId) {
    refs.onlineOutput.textContent = "Upload a reference song first.";
    return;
  }
  refs.musicToMusicButton.disabled = true;
  try {
    const data = await jsonFetch("/v2/music-to-music", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_upload_id: referenceId,
        vocal_upload_id: refs.preserveOriginalVocalToggle.checked ? state.latestVocalUpload?.upload_id || null : null,
        style_instruction:
          refs.onlineInstructionInput.value.trim() ||
          "Create a fresh original Bollywood-style transformation without copying the reference.",
        ...buildOnlinePayload(true),
      }),
    });
    renderOnlineResponse(data);
  } catch (error) {
    refs.onlineStatus.textContent = "Music-to-music failed";
    refs.onlineOutput.textContent = error.message;
  } finally {
    refs.musicToMusicButton.disabled = false;
  }
}

async function regenerateOnlineCandidate() {
  const jobId = state.latestOnlineResponse?.job_id;
  if (!jobId) {
    refs.onlineOutput.textContent = "Generate online candidates first.";
    return;
  }
  const instruction = refs.onlineInstructionInput.value.trim();
  if (!instruction) {
    refs.onlineOutput.textContent = "Add a regenerate direction such as stronger rock or sadder piano.";
    return;
  }
  refs.regenerateOnlineButton.disabled = true;
  try {
    const data = await jsonFetch(`/v2/jobs/${encodeURIComponent(jobId)}/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        edit_instruction: instruction,
        candidate_count: parseNullableNumber(refs.candidateCountInput.value) || 2,
        provider_preference: refs.onlineProviderSelect.value || null,
        reference_strength: parseNullableNumber(refs.referenceStrengthInput.value) || 0.35,
        rights_confirmed: refs.rightsConfirmedToggle.checked,
      }),
    });
    renderOnlineResponse(data);
  } catch (error) {
    refs.onlineStatus.textContent = "Regenerate failed";
    refs.onlineOutput.textContent = error.message;
  } finally {
    refs.regenerateOnlineButton.disabled = false;
  }
}

function buildOnlinePayload(includeReferenceStrength = false) {
  const payload = {
    lyrics: refs.lyricsInput.value,
    language: refs.languageSelect.value,
    genre: refs.genreSelect.value,
    production_style: refs.productionStyleSelect.value,
    arrangement_style: refs.arrangementStyleSelect.value,
    mood_tags: Array.from(state.selectedMoods),
    instruments: Array.from(state.selectedInstruments),
    bpm: parseNullableNumber(refs.bpmInput.value),
    key: refs.keyInput.value.trim() || null,
    duration_seconds: parseNullableNumber(refs.durationInput.value),
    provider_preference: refs.onlineProviderSelect.value || null,
    candidate_count: parseNullableNumber(refs.candidateCountInput.value),
    rights_confirmed: refs.rightsConfirmedToggle.checked,
    output_format: "mp3",
  };
  if (includeReferenceStrength) {
    payload.reference_strength = parseNullableNumber(refs.referenceStrengthInput.value) || 0.35;
    payload.source_mode = refs.musicSourceModeSelect.value || "auto";
    payload.preserve_original_vocal = refs.preserveOriginalVocalToggle.checked;
  }
  return removeNullish(payload);
}

function renderOnlineResponse(data) {
  state.latestOnlineResponse = data;
  const best = data.best_candidate || {};
  const pseudoJob = {
    job_id: data.job_id,
    status: data.status,
    message: data.message,
    generation_mode: data.mode === "music_to_music" ? "online_music_to_music" : "online_vocal_to_music",
    positive_prompt: data.composition_plan?.provider_prompt,
    negative_prompt: data.composition_plan?.negative_prompt,
    structured_summary: data.composition_plan,
    recommended_settings: {
      provider_order: data.composition_plan?.provider_preferences,
      best_provider: best.provider_name,
      bpm: data.composition_plan?.bpm,
      key: data.composition_plan?.key,
      duration_seconds: data.composition_plan?.duration_seconds,
    },
    diagnostics: data.diagnostics,
    quality_report: best.mix_quality_report || best.quality_report,
    backing_audio_path: best.backing_audio_path,
    backing_audio_url: best.backing_audio_url,
    mixed_preview_path: best.mixed_preview_path,
    mixed_preview_url: best.mixed_preview_url,
    final_mix_wav_path: best.final_mix_wav_path,
    final_mix_mp3_path: best.final_mix_mp3_path,
    final_mix_mp3_url: best.final_mix_mp3_url,
    audio_export: {
      backing_audio_path: best.backing_audio_path,
      backing_audio_url: best.backing_audio_url,
      mixed_preview_path: best.mixed_preview_path,
      mixed_preview_url: best.mixed_preview_url,
      final_mix_wav_path: best.final_mix_wav_path,
      final_mix_mp3_path: best.final_mix_mp3_path,
      final_mix_mp3_url: best.final_mix_mp3_url,
    },
  };
  state.latestJob = pseudoJob;
  refs.onlineStatus.textContent = data.status || "online result";
  refs.onlineOutput.textContent = [
    `job: ${data.job_id}`,
    `status: ${data.status}`,
    `mode: ${data.mode}`,
    `best provider: ${best.provider_name || "none"}`,
    `reference conditioned: ${best.reference_conditioned ? `yes (${formatMaybe(best.reference_strength, "")})` : "no"}`,
    `source: ${data.source_preparation?.detected_mode || "not classified"}`,
    `vocal detected/preserved: ${data.source_preparation?.vocal_detected ? "yes" : "no"} / ${data.source_preparation?.vocal_preserved ? "yes" : "no"}`,
    `originality/vocal gate: ${best.transformation_quality?.original_enough === true ? "new audio" : best.transformation_quality ? "needs review" : "not run"} / ${best.transformation_quality?.vocal_check_status || "not run"}`,
    `BPM/key: ${data.composition_plan?.bpm || "?"} / ${data.composition_plan?.key || "?"}`,
    `diagnostics: ${data.diagnostics?.suggested_fix || data.diagnostics?.error_message || ""}`,
  ].join("\n");
  renderSourcePreparation(data.source_preparation);
  renderCandidateGrid(data.candidates || []);
  renderJob(pseudoJob);
  renderPromptData(pseudoJob);
  setPill(refs.jobStatusPill, data.status, statusVariant(data.status));
}

function renderCandidateGrid(candidates) {
  refs.candidateGrid.replaceChildren();
  for (const candidate of candidates) {
    const card = document.createElement("article");
    card.className = "candidate-card";
    const header = document.createElement("header");
    const title = document.createElement("strong");
    title.textContent = `${candidate.candidate_id} · ${candidate.provider_name}`;
    const status = document.createElement("span");
    status.className = `pill ${statusVariant(candidate.status)}`;
    status.textContent = candidate.status || "candidate";
    header.append(title, status);
    card.appendChild(header);

    const meta = document.createElement("div");
    meta.className = "candidate-meta";
    const conditioning = candidate.reference_conditioned
      ? `reference-aware ${formatMaybe(candidate.reference_strength, "")}`
      : "prompt-only";
    const quality = candidate.transformation_quality;
    const qualitySummary = quality
      ? `${quality.original_enough ? "original" : "similarity review"} · vocals ${quality.vocal_check_status}`
      : "quality gate pending";
    meta.textContent = `score ${formatMaybe(candidate.score, "")} · ${conditioning} · ${qualitySummary} · ${candidate.warnings?.[0] || "ready for review"}`;
    card.appendChild(meta);
    if (candidate.backing_audio_url) {
      card.appendChild(labelledAudio("Backing only", candidate.backing_audio_url));
    }
    if (candidate.mixed_preview_url) {
      card.appendChild(labelledAudio("Vocal + backing mix", candidate.mixed_preview_url));
    }
    refs.candidateGrid.appendChild(card);
  }
}

function renderSourcePreparation(preparation) {
  refs.sourcePreparationGrid.replaceChildren();
  if (!preparation) return;
  const card = document.createElement("article");
  card.className = "candidate-card source-preparation-card";
  const header = document.createElement("header");
  const title = document.createElement("strong");
  title.textContent = "Prepared source";
  const status = document.createElement("span");
  status.className = `pill ${preparation.separation_status === "completed" || preparation.separation_status === "not_required" ? "" : "warn"}`;
  status.textContent = preparation.detected_mode || "unknown";
  header.append(title, status);
  const meta = document.createElement("div");
  meta.className = "candidate-meta";
  meta.textContent = [
    `requested ${preparation.requested_mode}`,
    `confidence ${formatMaybe(preparation.detection_confidence, "")}`,
    `vocal ${preparation.vocal_detected ? "detected" : "not detected"}`,
    preparation.vocal_preserved ? "original singer preserved" : "instrumental output",
  ].join(" · ");
  card.append(header, meta);
  if (preparation.instrumental_audio_url) {
    card.appendChild(labelledAudio("Clean instrumental reference", preparation.instrumental_audio_url));
  }
  if (preparation.vocal_audio_url) {
    card.appendChild(labelledAudio("Separated original vocal", preparation.vocal_audio_url));
  }
  if (preparation.warnings?.length) {
    const warning = document.createElement("p");
    warning.className = "muted-text";
    warning.textContent = preparation.warnings.join(" ");
    card.appendChild(warning);
  }
  refs.sourcePreparationGrid.appendChild(card);
}

function labelledAudio(label, url) {
  const wrapper = document.createElement("div");
  const text = document.createElement("strong");
  text.textContent = label;
  const audio = document.createElement("audio");
  audio.controls = true;
  audio.src = url;
  const actions = document.createElement("div");
  actions.className = "button-row";
  const playButton = document.createElement("button");
  playButton.className = "secondary candidate-play-button";
  playButton.type = "button";
  playButton.textContent = "Play preview";
  playButton.setAttribute("aria-pressed", "false");
  playButton.addEventListener("click", async () => {
    if (!audio.paused) {
      audio.pause();
      playButton.textContent = "Play preview";
      playButton.setAttribute("aria-pressed", "false");
      return;
    }
    try {
      await audio.play();
      playButton.textContent = "Pause preview";
      playButton.setAttribute("aria-pressed", "true");
    } catch (error) {
      playButton.textContent = "Playback unavailable";
      playButton.title = error.message;
    }
  });
  audio.addEventListener("ended", () => {
    playButton.textContent = "Play preview";
    playButton.setAttribute("aria-pressed", "false");
  });
  const download = document.createElement("a");
  download.className = "secondary";
  download.href = url;
  download.download = url.split("/").pop() || "skarly-music.wav";
  download.textContent = "Download audio";
  actions.append(playButton, download);
  wrapper.append(text, audio, actions);
  return wrapper;
}

async function improveLyrics() {
  refs.improveLyricsButton.disabled = true;
  try {
    const data = await jsonFetch("/improve-lyrics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lyrics: refs.lyricsInput.value,
        language: refs.languageSelect.value,
        mood_tags: Array.from(state.selectedMoods),
        production_style: refs.productionStyleSelect.value,
        arrangement_style: refs.arrangementStyleSelect.value,
        preserve_meaning: true,
        intensity: "medium",
      }),
    });
    state.latestImprovedLyrics = data.improved_lyrics || "";
    refs.applyLyricsButton.disabled = !state.latestImprovedLyrics;
    renderAssistantResult(
      [
        `Detected: ${data.detected_language_style || "Unknown"}`,
        "",
        data.improved_lyrics || "No lyric rewrite returned.",
        "",
        ...(data.rhyme_notes || []).map((note) => `Rhyme: ${note}`),
        ...(data.pronunciation_notes || []).map((note) => `Pronunciation: ${note}`),
      ],
      data.warnings || []
    );
  } catch (error) {
    renderAssistantResult([error.message], [error.message]);
  } finally {
    refs.improveLyricsButton.disabled = false;
  }
}

async function suggestStyle() {
  refs.suggestStyleButton.disabled = true;
  try {
    const data = await jsonFetch("/producer/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lyrics: refs.lyricsInput.value,
        language: refs.languageSelect.value,
        mood_tags: Array.from(state.selectedMoods),
        genre: refs.genreSelect.value,
        production_style: refs.productionStyleSelect.value,
        arrangement_style: refs.arrangementStyleSelect.value,
        instruments: Array.from(state.selectedInstruments),
        bpm: parseNullableNumber(refs.bpmInput.value),
        key: refs.keyInput.value.trim() || null,
        duration_seconds: parseNullableNumber(refs.durationInput.value),
      }),
    });
    state.latestSuggestion = data;
    refs.applyStyleButton.disabled = false;
    renderAssistantResult(
      [
        `Preset: ${data.recommended_preset_id || "None"}`,
        `Style: ${data.recommended_production_style || "None"}`,
        `Arrangement: ${data.recommended_arrangement_style || "None"}`,
        `Mood: ${formatValue(data.recommended_mood_tags)}`,
        `Instruments: ${formatValue(data.recommended_instruments)}`,
        `BPM: ${formatValue(data.recommended_bpm)}`,
        "",
        ...(data.reasoning || []).map((item) => `Why: ${item}`),
        ...(data.prompt_hints || []).map((item) => `Prompt hint: ${item}`),
      ],
      data.warnings || []
    );
  } catch (error) {
    renderAssistantResult([error.message], [error.message]);
  } finally {
    refs.suggestStyleButton.disabled = false;
  }
}

async function explainQuality(job = state.latestJob, silent = false) {
  if (!job) {
    if (!silent) renderAssistantResult(["Generate audio first, then explain quality."], []);
    return;
  }
  refs.explainQualityButton.disabled = true;
  try {
    const data = await jsonFetch("/producer/explain-quality", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        quality_report: job.quality_report || null,
        diagnostics: job.diagnostics || null,
        mix_diagnostics: job.mix_diagnostics || null,
      }),
    });
    renderAssistantResult(
      [
        data.user_friendly_status || "Quality explanation",
        data.summary || "",
        "",
        ...(data.issues || []).map((item) => `Issue: ${item}`),
        ...(data.suggested_fixes || []).map((item) => `Fix: ${item}`),
      ],
      []
    );
  } catch (error) {
    if (!silent) renderAssistantResult([error.message], [error.message]);
  } finally {
    refs.explainQualityButton.disabled = false;
  }
}

function applyImprovedLyrics() {
  if (!state.latestImprovedLyrics) return;
  refs.lyricsInput.value = state.latestImprovedLyrics;
  setPill(refs.jobStatusPill, "Lyrics applied", "muted");
}

async function applyStyleSuggestion() {
  const suggestion = state.latestSuggestion;
  if (!suggestion) return;
  if (suggestion.recommended_preset_id && state.presets.some((preset) => preset.id === suggestion.recommended_preset_id)) {
    refs.presetSelect.value = suggestion.recommended_preset_id;
    state.selectedPresetId = suggestion.recommended_preset_id;
    applyPreset(currentPreset());
  }
  if (suggestion.recommended_genre) refs.genreSelect.value = suggestion.recommended_genre;
  if (suggestion.recommended_production_style) refs.productionStyleSelect.value = suggestion.recommended_production_style;
  if (suggestion.recommended_arrangement_style) refs.arrangementStyleSelect.value = suggestion.recommended_arrangement_style;
  if (suggestion.recommended_bpm) refs.bpmInput.value = suggestion.recommended_bpm;
  if (suggestion.recommended_key) refs.keyInput.value = suggestion.recommended_key;
  state.selectedMoods = new Set(suggestion.recommended_mood_tags || []);
  state.selectedInstruments = new Set(suggestion.recommended_instruments || []);
  renderChips();
  setPill(refs.jobStatusPill, "Style applied", "muted");
  await previewPrompt();
}

function renderAssistantResult(lines, warnings) {
  refs.assistantOutput.textContent = (lines || []).filter((line) => line !== null && line !== undefined).join("\n").trim() || "No assistant notes.";
  renderAssistantWarnings(warnings || []);
  refs.assistantStatus.textContent = "Rules mode";
}

function renderAssistantWarnings(warnings) {
  refs.assistantWarningList.replaceChildren();
  for (const warning of warnings) {
    const item = document.createElement("li");
    item.textContent = warning;
    refs.assistantWarningList.appendChild(item);
  }
}

async function mixCurrentBacking() {
  const latest = state.latestJob;
  const backingPath =
    latest?.backing_audio_path ||
    latest?.audio_export?.backing_audio_path ||
    latest?.generated_audio_path ||
    latest?.audio_export?.final_wav_path;
  const vocalPath = refs.vocalPathInput.value.trim();
  if (!vocalPath || !backingPath) {
    setPill(refs.jobStatusPill, "Mix needs files", "bad");
    refs.jobMessage.textContent = "Provide a vocal path and generate backing audio before manual mix.";
    return;
  }

  refs.manualMixButton.disabled = true;
  try {
    const data = await jsonFetch("/mix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        vocal_audio_path: vocalPath,
        backing_audio_path: backingPath,
        vocal_gain_db: parseNullableNumber(refs.vocalGainInput.value),
        backing_gain_db: parseNullableNumber(refs.backingGainInput.value),
        ducking_enabled: refs.duckingEnabledToggle.checked,
        ducking_amount: parseNullableNumber(refs.duckingAmountInput.value),
        output_format: "mp3",
      }),
    });
    const pseudoJob = {
      ...(latest || {}),
      status: data.status,
      message: data.status === "mix_success" ? "Manual vocal/backing mix completed." : "Manual vocal/backing mix failed.",
      audio_export: data.audio_export,
      quality_report: data.quality_report,
      mix_diagnostics: data.diagnostics,
      backing_audio_path: data.audio_export?.backing_audio_path || backingPath,
      backing_audio_url: data.audio_export?.backing_audio_url || latest?.backing_audio_url,
      mixed_preview_path: data.audio_export?.mixed_preview_path,
      mixed_preview_url: data.audio_export?.mixed_preview_url,
      final_mix_wav_path: data.audio_export?.final_mix_wav_path,
      final_mix_mp3_path: data.audio_export?.final_mix_mp3_path,
      final_mix_mp3_url: data.audio_export?.final_mix_mp3_url,
    };
    state.latestJob = pseudoJob;
    renderJob(pseudoJob);
    setPill(refs.jobStatusPill, data.status, statusVariant(data.status));
  } catch (error) {
    setPill(refs.jobStatusPill, "Mix failed", "bad");
    refs.jobMessage.textContent = error.message;
  } finally {
    refs.manualMixButton.disabled = false;
  }
}

async function loadProjects(silent = false) {
  try {
    const data = await jsonFetch("/projects");
    state.latestProjects = data.projects || [];
    renderProjectList(state.latestProjects);
    if (!silent) refs.projectStatus.textContent = `${data.count || 0} projects`;
  } catch (error) {
    refs.projectStatus.textContent = "Projects unavailable";
    if (!silent) refs.jobMessage.textContent = error.message;
  }
}

async function saveProject() {
  refs.saveProjectButton.disabled = true;
  try {
    const data = await jsonFetch("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildProjectPayload()),
    });
    state.latestProject = data;
    refs.projectStatus.textContent = "Saved";
    await loadProjects(true);
    refs.projectListSelect.value = data.project_id;
  } catch (error) {
    refs.projectStatus.textContent = "Save failed";
    refs.jobMessage.textContent = error.message;
  } finally {
    refs.saveProjectButton.disabled = false;
  }
}

async function saveCurrentJobAsProject() {
  const jobId = state.latestJob?.job_id;
  if (!jobId) {
    refs.projectStatus.textContent = "Generate first";
    refs.jobMessage.textContent = "Generate or load a job before saving from current job.";
    return;
  }
  refs.saveJobProjectButton.disabled = true;
  try {
    const name = refs.projectNameInput.value.trim();
    const query = name ? `?name=${encodeURIComponent(name)}` : "";
    const data = await jsonFetch(`/projects/from-job/${encodeURIComponent(jobId)}${query}`, { method: "POST" });
    state.latestProject = data;
    refs.projectNameInput.value = data.name || name;
    refs.projectStatus.textContent = "Job saved";
    await loadProjects(true);
    refs.projectListSelect.value = data.project_id;
  } catch (error) {
    refs.projectStatus.textContent = "Save failed";
    refs.jobMessage.textContent = error.message;
  } finally {
    refs.saveJobProjectButton.disabled = false;
  }
}

async function loadSelectedProject() {
  const projectId = refs.projectListSelect.value;
  if (!projectId) return;
  refs.loadProjectButton.disabled = true;
  try {
    const data = await jsonFetch(`/projects/${encodeURIComponent(projectId)}`);
    state.latestProject = data;
    applyProject(data);
    refs.projectStatus.textContent = "Loaded";
  } catch (error) {
    refs.projectStatus.textContent = "Load failed";
    refs.jobMessage.textContent = error.message;
  } finally {
    refs.loadProjectButton.disabled = false;
  }
}

async function exportManifest() {
  const payload = removeNullish({
    project_id: state.latestProject?.project_id || refs.projectListSelect.value || null,
    job_id: state.latestJob?.job_id || null,
    include_audio: true,
    include_prompts: true,
    include_quality_report: true,
    include_diagnostics: true,
    include_stems: true,
    format: "manifest_json",
  });
  if (!payload.project_id && !payload.job_id) {
    refs.exportOutput.textContent = "Save a project or generate a job before exporting.";
    return;
  }
  refs.exportManifestButton.disabled = true;
  try {
    const data = await jsonFetch("/exports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.latestExport = data;
    refs.exportOutput.textContent = [
      `Status: ${data.status}`,
      data.message ? `Message: ${data.message}` : null,
      data.manifest_path ? `Manifest: ${data.manifest_path}` : null,
      ...(data.warnings || []).map((warning) => `Warning: ${warning}`),
      `Files: ${formatValue(data.files || {})}`,
    ].filter(Boolean).join("\n");
    if (data.manifest_url) {
      refs.manifestLink.hidden = false;
      refs.manifestLink.href = data.manifest_url;
      refs.manifestLink.textContent = "Open manifest";
    } else {
      refs.manifestLink.hidden = true;
      refs.manifestLink.removeAttribute("href");
    }
  } catch (error) {
    refs.exportOutput.textContent = error.message;
  } finally {
    refs.exportManifestButton.disabled = false;
  }
}

async function showHealth() {
  refs.healthButton.disabled = true;
  try {
    const data = await jsonFetch("/health/full");
    const checks = data.checks || {};
    const lines = [
      `Status: ${data.status}`,
      `Env: ${data.app_env}`,
      `Version: ${data.version || "unknown"}`,
      ...(data.warnings || []).map((warning) => `Warning: ${warning}`),
      "",
      ...Object.entries(checks).map(([key, value]) => `${humanize(key)}: ${value.ok ? "OK" : "Needs attention"} - ${value.message || formatValue(value)}`),
    ];
    refs.healthOutput.textContent = lines.join("\n");
  } catch (error) {
    refs.healthOutput.textContent = error.message;
  } finally {
    refs.healthButton.disabled = false;
  }
}

async function cleanupDryRun() {
  refs.cleanupButton.disabled = true;
  try {
    const data = await jsonFetch("/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dry_run: true, include_outputs: false }),
    });
    refs.cleanupOutput.textContent = [
      `Status: ${data.status}`,
      `Files found: ${data.files_found}`,
      `Bytes found: ${data.bytes_found}`,
      ...(data.warnings || []).map((warning) => `Warning: ${warning}`),
    ].join("\n");
  } catch (error) {
    refs.cleanupOutput.textContent = error.message;
  } finally {
    refs.cleanupButton.disabled = false;
  }
}

async function separateStems() {
  const audioPath = refs.stemsSourceInput.value.trim() || primaryAudioPathFromJob(state.latestJob);
  if (!audioPath) {
    refs.stemsStatus.textContent = "Needs audio";
    refs.stemsOutput.textContent = "Generate backing or mixed audio first, or paste a source audio path.";
    return;
  }

  refs.separateStemsButton.disabled = true;
  refs.stemsStatus.textContent = "Separating";
  try {
    const data = await jsonFetch("/stems/separate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_path: audioPath,
        stems: ["vocals", "drums", "bass", "other"],
        engine: "demucs",
        output_format: "wav",
      }),
    });
    state.latestStems = data;
    renderStemResponse(data);
  } catch (error) {
    refs.stemsStatus.textContent = "Failed";
    refs.stemsOutput.textContent = error.message;
  } finally {
    refs.separateStemsButton.disabled = false;
  }
}

async function buildSectionPrompt() {
  refs.buildSectionPromptButton.disabled = true;
  try {
    const data = await jsonFetch("/sections/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildSectionEditRequest()),
    });
    state.latestSectionEdit = data;
    renderSectionResponse(data);
  } catch (error) {
    refs.sectionStatus.textContent = "Failed";
    refs.sectionOutput.textContent = error.message;
  } finally {
    refs.buildSectionPromptButton.disabled = false;
  }
}

async function editSection() {
  refs.editSectionButton.disabled = true;
  try {
    const data = await jsonFetch("/sections/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildSectionEditRequest()),
    });
    state.latestSectionEdit = data;
    renderSectionResponse(data);
  } catch (error) {
    refs.sectionStatus.textContent = "Failed";
    refs.sectionOutput.textContent = error.message;
  } finally {
    refs.editSectionButton.disabled = false;
  }
}

function buildSectionEditRequest() {
  return removeNullish({
    source_audio_path: primaryAudioPathFromJob(state.latestJob) || null,
    source_job_id: state.latestJob?.job_id || null,
    section_name: refs.sectionNameSelect.value,
    section_start_seconds: parseNullableNumber(refs.sectionStartInput.value),
    section_end_seconds: parseNullableNumber(refs.sectionEndInput.value),
    edit_instruction:
      refs.sectionInstructionInput.value.trim() ||
      "Make the selected section more emotional while preserving the song style.",
    lyrics: refs.lyricsInput.value || null,
    language: refs.languageSelect.value,
    genre: refs.genreSelect.value,
    production_style: refs.productionStyleSelect.value,
    arrangement_style: refs.arrangementStyleSelect.value,
    mood_tags: Array.from(state.selectedMoods),
    instruments: Array.from(state.selectedInstruments),
    bpm: parseNullableNumber(refs.bpmInput.value),
    key: refs.keyInput.value.trim() || null,
    duration_seconds: parseNullableNumber(refs.durationInput.value),
    preserve_vocal: true,
    preserve_style: true,
  });
}

function renderStemResponse(data) {
  refs.stemsStatus.textContent = data.status || "Unknown";
  const diagnostics = data.diagnostics || {};
  const lines = [
    `Status: ${data.status || "unknown"}`,
    `Engine: ${data.engine || "demucs"}`,
    data.source_audio_path ? `Source: ${data.source_audio_path}` : null,
    data.stems_dir ? `Folder: ${data.stems_dir}` : null,
    diagnostics.failed_step ? `Failed step: ${diagnostics.failed_step}` : null,
    diagnostics.error_message ? `Error: ${diagnostics.error_message}` : null,
    diagnostics.suggested_fix ? `Suggested fix: ${diagnostics.suggested_fix}` : null,
    ...(data.warnings || []).map((warning) => `Warning: ${warning}`),
  ].filter(Boolean);
  refs.stemsOutput.textContent = lines.join("\n") || "No stem diagnostics.";
  refs.stemPlayerGrid.replaceChildren();
  const urls = data.stem_urls || {};
  for (const [stem, url] of Object.entries(urls)) {
    const card = document.createElement("div");
    card.className = "stem-card";
    const title = document.createElement("strong");
    title.textContent = humanize(stem);
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = url;
    const link = document.createElement("a");
    link.href = url;
    link.textContent = "Export";
    link.download = `${stem}.wav`;
    card.append(title, audio, link);
    refs.stemPlayerGrid.appendChild(card);
  }
  if (!Object.keys(urls).length) {
    const empty = document.createElement("p");
    empty.className = "muted-text";
    empty.textContent = "No playable stems returned. Stem separation requires Demucs configuration.";
    refs.stemPlayerGrid.appendChild(empty);
  }
}

function renderSectionResponse(data) {
  refs.sectionStatus.textContent = data.status || "Unknown";
  const diagnostics = data.diagnostics || {};
  const lines = [
    `Status: ${data.status || "unknown"}`,
    `Mode: ${data.mode || "prompt_only"}`,
    data.message ? `Message: ${data.message}` : null,
    diagnostics.failed_step ? `Failed step: ${diagnostics.failed_step}` : null,
    diagnostics.error_message ? `Error: ${diagnostics.error_message}` : null,
    diagnostics.suggested_fix ? `Suggested fix: ${diagnostics.suggested_fix}` : null,
    ...(data.warnings || []).map((warning) => `Warning: ${warning}`),
    "",
    data.edit_prompt || "No edit prompt returned.",
  ].filter((line) => line !== null && line !== undefined);
  refs.sectionOutput.textContent = lines.join("\n");
  if (data.output_audio_url) {
    refs.sectionAudio.hidden = false;
    refs.sectionAudio.src = data.output_audio_url;
  } else {
    refs.sectionAudio.hidden = true;
    refs.sectionAudio.removeAttribute("src");
  }
}

function primaryAudioPathFromJob(job) {
  const exportData = job?.audio_export || {};
  return (
    refs.stemsSourceInput.value.trim() ||
    job?.mixed_preview_path ||
    exportData.mixed_preview_path ||
    job?.final_mix_wav_path ||
    exportData.final_mix_wav_path ||
    job?.backing_audio_path ||
    exportData.backing_audio_path ||
    job?.generated_audio_path ||
    exportData.final_wav_path ||
    exportData.final_mp3_path ||
    ""
  );
}

function buildProjectPayload() {
  const name =
    refs.projectNameInput.value.trim() ||
    (refs.lyricsInput.value.trim().split(/\s+/).slice(0, 5).join(" ") || "Untitled Skarly project");
  return removeNullish({
    name,
    lyrics: refs.lyricsInput.value || null,
    language: refs.languageSelect.value,
    genre: refs.genreSelect.value,
    production_style: refs.productionStyleSelect.value,
    arrangement_style: refs.arrangementStyleSelect.value,
    mood_tags: Array.from(state.selectedMoods),
    instruments: Array.from(state.selectedInstruments),
    bpm: parseNullableNumber(refs.bpmInput.value),
    key: refs.keyInput.value.trim() || null,
    duration_seconds: parseNullableNumber(refs.durationInput.value),
    source_job_id: state.latestJob?.job_id || null,
    audio_paths: collectAudioPaths(state.latestJob),
    notes: state.latestJob?.message || null,
  });
}

function collectAudioPaths(job) {
  const exportData = job?.audio_export || {};
  return removeNullish({
    backing: job?.backing_audio_path || exportData.backing_audio_path || null,
    generated: job?.generated_audio_path || exportData.final_wav_path || exportData.final_mp3_path || null,
    mixed_preview: job?.mixed_preview_path || exportData.mixed_preview_path || null,
    final_mix_wav: job?.final_mix_wav_path || exportData.final_mix_wav_path || null,
    final_mix_mp3: job?.final_mix_mp3_path || exportData.final_mix_mp3_path || null,
  });
}

function renderProjectList(projects) {
  refs.projectListSelect.replaceChildren();
  if (!projects.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No saved projects";
    refs.projectListSelect.appendChild(option);
    return;
  }
  for (const project of projects) {
    const option = document.createElement("option");
    option.value = project.project_id;
    option.textContent = project.name || project.project_id;
    refs.projectListSelect.appendChild(option);
  }
}

function applyProject(project) {
  refs.projectNameInput.value = project.name || "";
  refs.lyricsInput.value = project.lyrics || "";
  const settings = project.settings || {};
  if (settings.language) refs.languageSelect.value = settings.language;
  if (settings.genre && optionExists(refs.genreSelect, settings.genre)) refs.genreSelect.value = settings.genre;
  if (settings.production_style && optionExists(refs.productionStyleSelect, settings.production_style)) {
    refs.productionStyleSelect.value = settings.production_style;
  }
  if (settings.arrangement_style && optionExists(refs.arrangementStyleSelect, settings.arrangement_style)) {
    refs.arrangementStyleSelect.value = settings.arrangement_style;
  }
  state.selectedMoods = new Set(settings.mood_tags || []);
  state.selectedInstruments = new Set(settings.instruments || []);
  refs.bpmInput.value = settings.bpm || "";
  refs.keyInput.value = settings.key || "";
  refs.durationInput.value = settings.duration_seconds || "";
  renderChips();
  const pseudoJob = {
    job_id: project.source_job_id || project.project_id,
    status: "project_loaded",
    message: `Loaded project: ${project.name}`,
    quality_report: project.quality_report,
    diagnostics: project.diagnostics,
    backing_audio_path: project.audio_paths?.backing || project.audio_paths?.generated,
    backing_audio_url: project.audio_urls?.backing || project.audio_urls?.generated,
    mixed_preview_path: project.audio_paths?.mixed_preview,
    mixed_preview_url: project.audio_urls?.mixed_preview,
    final_mix_wav_path: project.audio_paths?.final_mix_wav,
    final_mix_mp3_path: project.audio_paths?.final_mix_mp3,
    final_mix_mp3_url: project.audio_urls?.final_mix_mp3,
  };
  state.latestJob = { ...(state.latestJob || {}), ...pseudoJob };
  renderAudio(pseudoJob);
}

function renderPromptData(data) {
  refs.positivePrompt.textContent = data.positive_prompt || "No positive prompt.";
  refs.negativePrompt.textContent = data.negative_prompt || "No negative prompt.";

  const summary = data.structured_summary || {};
  renderDetails(refs.summaryList, [
    ["Language", summary.language],
    ["Compatible genre", summary.genre],
    ["Genre / Style", summary.production_style || summary.genre],
    ["Arrangement Style", summary.arrangement_style],
    ["Mood", summary.mood_tags],
    ["Main Instruments", summary.instruments],
    ["BPM", summary.bpm],
    ["Key", summary.key],
    ["Duration", summary.duration_seconds ? `${summary.duration_seconds}s` : null],
    ["Mix Direction", summary.mix_direction],
  ]);

  renderDetails(refs.settingsList, objectEntries(data.recommended_settings));
  renderWarnings(data.warnings || []);
}

function renderJob(job) {
  const mode = job.generation_mode || state.generationMode || "mock";
  setPill(refs.phasePill, modeLabel(mode), isFallbackStatus(job.status) ? "warn" : mode === "ace_step" ? "" : "muted");
  setPill(refs.jobStatusPill, job.status || "Idle", statusVariant(job.status));
  renderDetails(refs.jobProgress, [
    ["Job ID", job.job_id],
    ["Mode", modeLabel(mode)],
    ["Generator", job.quality_report?.generator_name || job.diagnostics?.generator_name],
    ["Status", job.status],
    ["Progress", job.progress === undefined || job.progress === null ? null : `${Math.round(job.progress * 100)}%`],
    ["Backing URL", job.backing_audio_url || job.audio_export?.backing_audio_url],
    ["Mixed Preview URL", job.mixed_preview_url || job.audio_export?.mixed_preview_url],
    ["Final WAV", job.final_mix_wav_path || job.audio_export?.final_mix_wav_path],
    ["Final MP3", job.final_mix_mp3_path || job.audio_export?.final_mix_mp3_path],
  ]);
  refs.jobMessage.textContent = job.message || "No generation message.";
  renderDetails(refs.diagnosticsGrid, objectEntries(job.diagnostics));
  renderDetails(refs.mixDiagnosticsGrid, objectEntries(job.mix_diagnostics));
  renderDiagnosticLogs(job);
  renderDetails(refs.qualityGrid, objectEntries(job.quality_report));
  renderAudio(job);
}

function renderDiagnosticLogs(job) {
  const diagnostics = job?.diagnostics;
  const logs = Array.isArray(diagnostics?.last_logs) ? diagnostics.last_logs : [];
  const fallbackWarning = job?.status === "completed_fallback"
    ? ["ACE-Step failed or failed validation, so procedural_v2 fallback audio was generated."]
    : [];
  const fallbackReason = diagnostics?.fallback_reason ? [`Fallback reason: ${diagnostics.fallback_reason}`] : [];
  const fix = diagnostics?.suggested_fix ? [`Suggested fix: ${diagnostics.suggested_fix}`] : [];
  const error = diagnostics?.error_message ? [`Error: ${diagnostics.error_message}`] : [];
  const failedStep = diagnostics?.failed_step ? [`Failed step: ${diagnostics.failed_step}`] : [];
  const lines = [...fallbackWarning, ...failedStep, ...error, ...fallbackReason, ...fix, ...logs];
  refs.diagnosticLogs.textContent = lines.length ? lines.join("\n") : "No generation logs yet.";
}

function renderAudio(job) {
  const exportData = job.audio_export || {};
  const backingUrl =
    job.backing_audio_url ||
    exportData.backing_audio_url ||
    (!job.mixed_preview_url && !exportData.mixed_preview_url ? job.audio_url || job.preview_url : null);
  const mixedUrl =
    job.mixed_preview_url ||
    exportData.mixed_preview_url ||
    (job.mixed_preview_path ? job.audio_url || job.preview_url : null);

  if (backingUrl) {
    refs.generatedAudio.hidden = false;
    refs.generatedAudio.src = backingUrl;
    refs.audioPlaceholder.hidden = true;
  } else {
    refs.generatedAudio.hidden = true;
    refs.generatedAudio.removeAttribute("src");
    refs.audioPlaceholder.hidden = false;
    refs.audioPlaceholderText.textContent =
      isFailureStatus(job.status)
        ? "Generation failed or failed validation; no backing audio was returned."
        : "Backing preview appears here when ACE-Step or procedural_v2 returns a file.";
  }

  if (mixedUrl) {
    refs.mixedAudio.hidden = false;
    refs.mixedAudio.src = mixedUrl;
    refs.mixedPlaceholder.hidden = true;
  } else {
    refs.mixedAudio.hidden = true;
    refs.mixedAudio.removeAttribute("src");
    refs.mixedPlaceholder.hidden = false;
    refs.mixedPlaceholderText.textContent =
      job.status === "mix_failed"
        ? "Mix failed; generated backing remains available above."
        : "Add a vocal path to create a vocal-forward mixed preview.";
  }
}

function isFailureStatus(status) {
  return status === "failed" || status === "failed_validation" || status === "mix_failed" || status === "analysis_failed";
}

function isFallbackStatus(status) {
  return status === "completed_fallback" || status === "completed_needs_review" || status === "rights_required";
}

function statusVariant(status) {
  if (isFailureStatus(status)) return "bad";
  if (isFallbackStatus(status)) return "warn";
  return "";
}

function modeLabel(mode) {
  if (mode === "ace_step") return "ACE-Step";
  if (mode === "procedural_v2_fallback") return "procedural_v2 fallback";
  if (mode === "mix") return "Vocal/backing mix";
  if (mode === "online_vocal_to_music" || mode === "vocal_to_music") return "Online AI vocal-to-music";
  if (mode === "online_music_to_music" || mode === "music_to_music") return "Online AI music-to-music";
  if (mode === "mock") return "Mock";
  return mode || "Mock";
}

function renderWarnings(warnings) {
  refs.warningList.replaceChildren();
  for (const warning of warnings) {
    const item = document.createElement("li");
    item.textContent = warning;
    refs.warningList.appendChild(item);
  }
}

function renderDetails(container, entries) {
  container.replaceChildren();
  for (const [label, rawValue] of entries) {
    const item = document.createElement("div");
    item.className = "detail-item";
    const labelEl = document.createElement("span");
    labelEl.textContent = label;
    const valueEl = document.createElement("strong");
    valueEl.textContent = formatValue(rawValue);
    item.append(labelEl, valueEl);
    container.appendChild(item);
  }
}

function objectEntries(value) {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).map(([key, item]) => [humanize(key), item]);
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, options);
  let data = null;
  try {
    data = await response.json();
  } catch (_error) {
    data = null;
  }
  if (!response.ok) {
    const detail = data?.detail || `${response.status} ${response.statusText}`;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg || item).join(", ") : detail);
  }
  return data;
}

function parseNullableNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function removeNullish(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([_key, item]) => item !== null && item !== undefined && item !== "")
  );
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean)));
}

function formatMaybe(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "unknown";
  const numberValue = Number(value);
  if (Number.isFinite(numberValue)) return `${Math.round(numberValue * 100) / 100}${suffix}`;
  return `${value}${suffix}`;
}

function formatValue(value) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return "None";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function humanize(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function optionExists(select, value) {
  return Array.from(select.options).some((option) => option.value === value);
}

function setPill(element, text, variant = "") {
  element.className = `pill ${variant}`.trim();
  element.textContent = text;
}

refs.presetSelect.addEventListener("change", async () => {
  state.selectedPresetId = refs.presetSelect.value;
  applyPreset(currentPreset());
  await previewPrompt();
});

refs.previewButton.addEventListener("click", previewPrompt);
refs.generateButton.addEventListener("click", generateMock);
refs.manualMixButton.addEventListener("click", mixCurrentBacking);
refs.uploadVocalButton.addEventListener("click", () => uploadAudio("vocal"));
refs.uploadReferenceButton.addEventListener("click", () => uploadAudio("reference"));
refs.analyzeVocalButton.addEventListener("click", analyzeUploadedVocal);
refs.vocalToMusicButton.addEventListener("click", generateVocalToMusic);
refs.musicToMusicButton.addEventListener("click", generateMusicToMusic);
refs.regenerateOnlineButton.addEventListener("click", regenerateOnlineCandidate);
refs.saveProjectButton.addEventListener("click", saveProject);
refs.saveJobProjectButton.addEventListener("click", saveCurrentJobAsProject);
refs.loadProjectButton.addEventListener("click", loadSelectedProject);
refs.refreshProjectsButton.addEventListener("click", () => loadProjects());
refs.improveLyricsButton.addEventListener("click", improveLyrics);
refs.suggestStyleButton.addEventListener("click", suggestStyle);
refs.explainQualityButton.addEventListener("click", () => explainQuality());
refs.applyLyricsButton.addEventListener("click", applyImprovedLyrics);
refs.applyStyleButton.addEventListener("click", applyStyleSuggestion);
refs.separateStemsButton.addEventListener("click", separateStems);
refs.buildSectionPromptButton.addEventListener("click", buildSectionPrompt);
refs.editSectionButton.addEventListener("click", editSection);
refs.exportManifestButton.addEventListener("click", exportManifest);
refs.healthButton.addEventListener("click", showHealth);
refs.cleanupButton.addEventListener("click", cleanupDryRun);

for (const element of [
  refs.lyricsInput,
  refs.languageSelect,
  refs.genreSelect,
  refs.productionStyleSelect,
  refs.arrangementStyleSelect,
  refs.bpmInput,
  refs.keyInput,
  refs.durationInput,
  refs.energySelect,
  refs.vocalPathInput,
  refs.vocalGainInput,
  refs.backingGainInput,
  refs.vocalForwardToggle,
  refs.duckingEnabledToggle,
  refs.duckingAmountInput,
  refs.projectNameInput,
  refs.stemsSourceInput,
  refs.sectionNameSelect,
  refs.sectionStartInput,
  refs.sectionEndInput,
  refs.sectionInstructionInput,
]) {
  element.addEventListener("change", () => {
    setPill(refs.jobStatusPill, "Edited", "muted");
  });
}

loadPresets();
