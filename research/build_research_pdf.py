"""Build the final, visually verifiable Skarly research report PDF."""

from __future__ import annotations

import html
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "Skarly_Research_Internship_Report.pdf"
ARTIFACTS = ROOT / "research" / "artifacts"
SCREENSHOTS = ROOT / "docs" / "ui-screenshots"
WORDMARK = ROOT / "lyricmorph-mobile" / "assets" / "skarly-wordmark.png"

GOLD = colors.HexColor("#C6AA6A")
NAVY = colors.HexColor("#0B1B2B")
INK = colors.HexColor("#17202A")
BLUE = colors.HexColor("#2E74B5")
MUTED = colors.HexColor("#5B6570")
PALE = colors.HexColor("#F4F6F9")
GREEN = colors.HexColor("#2E6F58")
RED = colors.HexColor("#9B1C1C")


def safe(value):
    return html.escape(str(value), quote=False)


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverKicker", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=GOLD, alignment=TA_CENTER, spaceAfter=12))
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=colors.white, alignment=TA_CENTER, spaceAfter=12))
styles.add(ParagraphStyle(name="CoverSubtitle", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=12.5, leading=18, textColor=colors.HexColor("#D5D9DF"), alignment=TA_CENTER, spaceAfter=24))
styles.add(ParagraphStyle(name="CoverMeta", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=15, textColor=colors.HexColor("#BFC5CC"), alignment=TA_CENTER))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=BLUE, spaceBefore=13, spaceAfter=7, keepWithNext=True))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=BLUE, spaceBefore=10, spaceAfter=5, keepWithNext=True))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.2, leading=14.2, textColor=INK, spaceAfter=7))
styles.add(ParagraphStyle(name="Bulletx", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=13.5, textColor=INK, leftIndent=16, firstLineIndent=-8, bulletIndent=4, spaceAfter=5))
styles.add(ParagraphStyle(name="Captionx", parent=styles["BodyText"], fontName="Helvetica-Oblique", fontSize=8.4, leading=11, textColor=MUTED, alignment=TA_CENTER, spaceBefore=3, spaceAfter=8))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontName="Helvetica-Oblique", fontSize=8, leading=10.5, textColor=MUTED, spaceBefore=3, spaceAfter=5))
styles.add(ParagraphStyle(name="Calloutx", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.2, textColor=INK, leftIndent=4, rightIndent=4))
styles.add(ParagraphStyle(name="Codex", parent=styles["Code"], fontName="Courier", fontSize=7.8, leading=10, textColor=colors.HexColor("#E9EDF2"), backColor=colors.HexColor("#111318"), borderPadding=8, spaceBefore=4, spaceAfter=8))


def p(text, style="Bodyx"):
    return Paragraph(safe(text).replace("\n", "<br/>"), styles[style])


def heading(text, level=1):
    return Paragraph(safe(text), styles["H1x" if level == 1 else "H2x"])


def bullet(text):
    return Paragraph(safe(text), styles["Bulletx"], bulletText="-")


def callout(label, text, fill=PALE, accent=GOLD):
    content = Paragraph(f'<font color="#{accent.hexval()[2:]}"><b>{safe(label).upper()}</b></font>&nbsp;&nbsp;{safe(text)}', styles["Calloutx"])
    table = Table([[content]], colWidths=[6.35 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 0.7, accent),
        ("LINEBEFORE", (0, 0), (0, -1), 5, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return KeepTogether([table, Spacer(1, 7)])


def data_table(headers, rows, widths):
    data = [[Paragraph(f"<b>{safe(value)}</b>", ParagraphStyle(name=f"th{id(headers)}{i}", parent=styles["Bodyx"], textColor=colors.white, fontSize=8.6, leading=10.5, alignment=TA_CENTER)) for i, value in enumerate(headers)]]
    cell_style = ParagraphStyle(name=f"td{id(rows)}", parent=styles["Bodyx"], fontSize=8.4, leading=10.5, spaceAfter=0)
    for row in rows:
        data.append([Paragraph(safe(value), cell_style) for value in row])
    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9CED4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F8F9FB")))
    table.setStyle(TableStyle(commands))
    return table


def scaled_image(path, max_width=6.25 * inch, max_height=5.8 * inch):
    path = Path(path)
    image = Image(str(path))
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    image.hAlign = "CENTER"
    return image


def figure(path, caption, max_width=6.25 * inch, max_height=5.5 * inch):
    path = Path(path)
    if not path.is_file():
        return []
    return [scaled_image(path, max_width, max_height), Paragraph(safe(caption), styles["Captionx"])]


def later_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(7.5 * inch, 10.55 * inch, "SKARLY  /  RESEARCH INTERNSHIP REPORT")
    canvas.setStrokeColor(colors.HexColor("#D6DADE"))
    canvas.setLineWidth(0.5)
    canvas.line(1 * inch, 10.42 * inch, 7.5 * inch, 10.42 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(1 * inch, 0.48 * inch, "Skarly research artifact")
    canvas.drawRightString(7.5 * inch, 0.48 * inch, f"Page {doc.page}")
    canvas.restoreState()


def first_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#050607"))
    canvas.rect(0, 0, LETTER[0], LETTER[1], stroke=0, fill=1)
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.2)
    canvas.line(1 * inch, 0.7 * inch, 7.5 * inch, 0.7 * inch)
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    summary = json.loads((ARTIFACTS / "research_summary.json").read_text(encoding="utf-8"))
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=LETTER, rightMargin=1 * inch, leftMargin=1 * inch,
        topMargin=0.82 * inch, bottomMargin=0.72 * inch,
        title="Skarly Audio Intelligence and Five-Version Music Generation",
        author="Skarly Research Project",
        subject="Research internship report",
    )
    story = []
    story += [Spacer(1, 0.55 * inch), Paragraph("RESEARCH INTERNSHIP PROJECT", styles["CoverKicker"])]
    if WORDMARK.is_file():
        story += [scaled_image(WORDMARK, 5.7 * inch, 2.25 * inch), Spacer(1, 0.1 * inch)]
    story += [
        Paragraph("Audio Intelligence and<br/>Five-Version Music Generation", styles["CoverTitle"]),
        Paragraph("System design, neural models, signal analysis, UI evidence, and reproducible procedure", styles["CoverSubtitle"]),
        callout("Project boundary", "The working vocal-to-music and music-to-music paths were tested as a guest and left unchanged. New work is limited to a result-screen player, research notebook, screenshots, documentation, and packaging.", fill=colors.HexColor("#F4E9CD"), accent=GOLD),
        Spacer(1, 0.18 * inch),
        Paragraph("Prepared 18 July 2026<br/>Skarly local research build<br/>Case-study audio: 225.048-second vocal recording", styles["CoverMeta"]),
        PageBreak(),
    ]

    story += [heading("Executive abstract"), p("Skarly is a local full-stack creator studio that accepts a vocal, full song, or music reference; analyses the complete decoded recording; creates five differentiated producer blueprints; generates new backing arrangements with ACE-Step; preserves or separates the singer according to the selected mode; and exports playable mixes, stems, maps, and disclosure metadata."), callout("Outcome", "The live guest test completed successfully with the supplied MP3: private upload, full-song analysis, five producer plans, CUDA generation, five playable versions, and export preparation all rendered in the browser. The result UI now includes a compact message-style player beneath the five final versions.", fill=colors.HexColor("#EAF4EF"), accent=GREEN)]
    story += [data_table(["Evidence", "Observed result"], [
        ["Input duration", "225.048 seconds, complete-song scope"],
        ["Signal map", "23 vocal phrases across 6 detected sections"],
        ["Production estimate", "Approximately 170 BPM; C# minor; up-tempo pop start"],
        ["Runtime", "NVIDIA GeForce RTX 5070 Laptop GPU; ACE-Step 1.5 turbo"],
        ["Generation telemetry", "7,718 MB peak VRAM; 113-second render"],
        ["Diversity gate", "10/10 producer pairs passed; thresholds remain prototype"],
    ], [1.55 * inch, 4.8 * inch]), p("Source: live local guest run and executed notebook, 18 July 2026.", "Smallx")]

    story += [heading("1. Scope, originality, and safety boundary"), p("This research pass treats the existing application as the system under study. The implementation was mapped from the repository's own modules and run-time evidence. The notebook's signal-processing code was written specifically for this project using transparent NumPy/SciPy operations. No external template code was inserted into the model, generator, source separation, mixing, or API paths.")]
    for item in [
        "Protected working scope: vocal-to-music and music-to-music generation, source preparation, ACE-Step calls, mixing, quality validation, and storage contracts.",
        "Allowed presentation scope: one selected-version player, screenshots, research charts, report assets, and plug-and-play setup documentation.",
        "Data boundary: the attached audio is used for the live test and notebook execution, but it is excluded from Git and is not treated as training data.",
        "Research boundary: checkpoint metrics are reported as observed; limitations and prototype thresholds remain explicit.",
    ]: story.append(bullet(item))

    story += [heading("2. Working system architecture")] + figure(ARTIFACTS / "model_architecture.png", "Figure 1. Working architecture and the boundary between analysis, generation, mixing, and export.") + [p("The architecture separates recognition from synthesis. Classifier heads guide routing and producer-plan construction; they do not generate audio and do not clone a singer. ACE-Step generates instrumental backing directions. The adaptive mixer reuses the preserved vocal and makes space with phrase-aware multiband ducking.")]

    story += [heading("3. End-to-end procedure")]
    steps = [
        ("Local upload", "The guest client transfers the selected audio to local storage and verifies it before analysis."),
        ("Source preparation", "Vocal-only input is preserved; full-song or music input uses Demucs when the selected mode requires separation."),
        ("Complete-song analysis", "The backend maps tempo, key, phrases, energy and structure and aggregates learned predictions over the full duration."),
        ("Creator confirmation", "Language, style, BPM, key, mood, and mix focus remain visible and editable."),
        ("Five producer plans", "Distinct palettes specify instrumentation, groove, bass movement, energy arc, stereo treatment, and prompt."),
        ("CUDA generation", "ACE-Step renders a new backing per producer plan and records model, device, VRAM, time, seed, and fallback state."),
        ("Protected vocal mix", "The original vocal is reused; source duration is authoritative; phrase-aware ducking avoids masking."),
        ("Quality gates", "Decode, duration, loudness, silence, vocal leakage, compatibility, and pairwise diversity are checked."),
        ("Selection and revision", "Five versions stay playable; stem remixing avoids regeneration; one-producer revision preserves the other four."),
        ("Export", "WAV, MP3, instrumental, vocal, song map, analysis, seeds, telemetry, disclosure, and studio bundle are prepared."),
    ]
    for index, (title, body) in enumerate(steps, 1): story.append(Paragraph(f"<b>{index}. {safe(title)}.</b> {safe(body)}", styles["Bodyx"]))

    story += [PageBreak(), heading("4. Models and algorithms used"), data_table(["Component", "Role", "Project implementation"], [
        ["ACE-Step 1.5", "Music generation", "Five new instrumental backings from producer blueprints on CUDA."],
        ["AutoencoderOobleck VAE", "Shared encoder", "Frozen ACE-Step encoder; latent mean and standard deviation create a 128-D embedding."],
        ["Multi-head NN", "Audio intelligence", "LayerNorm, two 256-D GELU layers, dropout, and calibrated independent heads."],
        ["Legacy mel-CNN", "Research compatibility", "64-band log-mel; Conv2D 24/48/96; pooling; 96-D embedding; language/genre heads."],
        ["Demucs", "Source separation", "Validated vocal or instrumental stems for full-song/music routing."],
        ["Basic Pitch", "Melody/MIDI", "Preferred MIDI extraction with guarded fallback behavior."],
        ["Whisper", "Lyrics/language", "Optional transcription and language evidence."],
        ["Adaptive mixer", "Vocal preservation", "Phrase-aware ducking, balance control, exact duration, and export validation."],
    ], [1.3 * inch, 1.35 * inch, 3.7 * inch]), p("Source: repository training modules, worker, services, and mixer.", "Smallx")]

    story += [heading("5. Neural network and CNN research")] + figure(ARTIFACTS / "nn_cnn_comparison.png", "Figure 2. Legacy convolutional network compared with the current shared-encoder neural architecture.") + [p("The legacy network explains convolution directly: kernels learn local time-frequency shapes and pooling adds small shift tolerance. The current direction is better aligned with Skarly: a frozen pretrained music-audio encoder supplies a richer representation while compact task heads learn routing decisions.")] + figure(ARTIFACTS / "cnn_training_curves.png", "Figure 3. Real training and grouped-validation curves from the retained training-history export.") + [callout("Interpretation", "The selected legacy checkpoint reached 96.77% grouped-validation language accuracy and 54.35% broad-genre accuracy at epoch 15. Language routing can be guarded; fine-grained style selection still needs creator confirmation.", fill=colors.HexColor("#FFF7E6"), accent=GOLD)]

    story += [heading("6. Case-study audio analysis"), p(f"The notebook analysed the supplied {summary['duration_seconds']:.3f}-second recording without adding it to the repository. FFmpeg decoded a temporary mono stream; SciPy/NumPy code then computed waveform, RMS, zero-crossing activity, STFT, mel energy, MFCCs, spectral flux, chroma, and a transparent key hypothesis.")] + figure(ARTIFACTS / "audio_overview.png", "Figure 4. Waveform, short-time RMS, and zero-crossing activity across the complete recording.") + figure(ARTIFACTS / "spectrogram.png", "Figure 5. Log-frequency STFT spectrogram.") + figure(ARTIFACTS / "mel_mfcc.png", "Figure 6. Mel spectrogram and first 20 MFCCs.") + figure(ARTIFACTS / "chroma_key.png", "Figure 7. Rhythm evidence and pitch-class energy.") + [callout("Why estimates differ", f"The transparent notebook heuristic proposed {summary['notebook_tempo_bpm']:.1f} BPM and {summary['notebook_key_hypothesis']}; production reported about 170 BPM and C# minor. Windowing, half/double-time choices, pitch weighting, and confidence logic can disagree, so the UI exposes correction instead of declaring one estimate ground truth.", fill=colors.HexColor("#FDEEEE"), accent=RED)]

    story += [heading("7. Live guest UI validation"), p("The browser test used guest mode and the supplied audio through the normal UI. Upload, analysis, producer selection, processing, version playback, library, profile, recording, and export states were captured as PNG evidence.")]
    for filename, caption in [
        ("02-creator-setup.png", "Figure 8. Local creator setup."),
        ("04-upload-empty.png", "Figure 9. Local audio input and mode selection."),
        ("06-audio-detected.png", "Figure 10. Complete-song detection evidence."),
        ("08-processing.png", "Figure 11. CUDA generation progress and device telemetry."),
    ]: story += figure(SCREENSHOTS / filename, caption, 6.0 * inch, 3.4 * inch)

    story += [heading("8. Five final versions and the UI enhancement"), data_table(["Version", "Direction", "Differentiator"], [
        ["1", "Bollywood Acoustic", "Guitar, piano, light tabla, warm bass, hook strings"],
        ["2", "Modern Bollywood Pop", "Electronic drums, synth bass, wide pads, plucked hook"],
        ["3", "Sufi Live", "Harmonium, tabla/dholak, claps, live bass, sarangi"],
        ["4", "Punjabi Rhythm", "Dhol, tumbi, punch bass, hand percussion, bright synth"],
        ["5", "Cinematic Urban", "Felt piano, atmosphere, deep percussion, strings, sub bass"],
    ], [0.55 * inch, 1.75 * inch, 4.05 * inch]), p("A new final-version preview sits beneath the five cards. It follows the supplied voice-message reference: circular headphone avatar, play/pause control, blue progress line and knob, elapsed/total time, pale-green surface, and completion ticks. It reads existing playback state and adds no generation or remix behavior.")]
    story += figure(SCREENSHOTS / "19-final-preview-added.png", "Figure 12. Reference-inspired final-version player below the five completed versions.", 6.0 * inch, 3.4 * inch)

    story += [heading("9. Quality assurance, ethics, and limitations")]
    for item in [
        "The TypeScript application passes tsc --noEmit after the UI addition.",
        "The notebook has 9 executed code cells and zero error outputs; plots were regenerated from the attached input.",
        "The source audio is excluded from Git and not used for training; contribution remains opt-in and off by default.",
        "No voice cloning path is introduced. The singer is preserved as an input stem, not re-synthesized as an identity model.",
        "The ten pairwise diversity checks passed, but thresholds remain prototype until independent human calibration.",
        "One song is a case study, not a dataset-level evaluation. Production claims need singer-disjoint, rights-cleared data and listening panels.",
    ]: story.append(bullet(item))

    story += [heading("10. Plug-and-play reproduction"), p("Clone the repository, create environment files from the checked-in offline examples, start the model service, backend, and web UI in order, then optionally rerun the notebook with permitted audio."), Paragraph("# 1) Start ACE-Step<br/>powershell -ExecutionPolicy Bypass -File .\\tools\\start-ace-step-api.ps1<br/><br/># 2) Start FastAPI/backend helpers<br/>powershell -ExecutionPolicy Bypass -File .\\tools\\start-local-studio.ps1<br/><br/># 3) Start Expo web UI<br/>cd .\\lyricmorph-mobile<br/>npm install<br/>npm run web<br/><br/># 4) Optional research notebook<br/>$env:SKARLY_AUDIO_PATH='C:\\path\\to\\permitted-audio.mp3'<br/>jupyter notebook .\\research\\Skarly_Audio_Intelligence_Research.ipynb", styles["Codex"]), callout("First-run expectation", "ACE-Step weights, GPU drivers, FFmpeg, and local tool paths are environment-specific. Example environment files document variables without committing secrets.", fill=colors.HexColor("#F4E9CD"), accent=GOLD)]

    story += [heading("11. Conclusion"), p("The project now reads as a research internship build rather than only a product demo: the workflow is evidenced, neural and convolutional paths are explained, real checkpoint curves are plotted, a permitted audio case study is reproducible, the UI is catalogued, and the generator boundaries remain intact. Analysis informs routing, ACE-Step generates new backings, the original singer is protected in mixing, and quality gates remain explicit about production readiness."), PageBreak(), heading("Appendix A. UI screenshot catalogue"), p("The following viewport captures document the guest journey and major product states. Full-resolution PNG files are delivered in docs/ui-screenshots/.")]
    screenshot_files = sorted(SCREENSHOTS.glob("*.png"))
    for index, path in enumerate(screenshot_files, 1):
        story += figure(path, f"UI-{index:02d}. {path.stem.replace('-', ' ').title()}.", 5.85 * inch, 3.28 * inch)
        if index % 2 == 0 and index < len(screenshot_files): story.append(PageBreak())

    story += [PageBreak(), heading("Appendix B. Code provenance map"), data_table(["Area", "Repository source"], [
        ["Expo UI and result player", "lyricmorph-mobile/App.tsx"],
        ["API contracts and V2 orchestration", "lyricmorph-backend/app/main.py"],
        ["Audio worker and generation routing", "lyricmorph-backend/app/worker.py"],
        ["Frozen encoder and multi-head NN", "lyricmorph-backend/training/audio_intelligence.py"],
        ["Legacy mel-CNN", "lyricmorph-backend/training/train_audio_classifier.py"],
        ["Vocal analysis", "lyricmorph-backend/app/services/vocal_analysis.py"],
        ["ACE-Step wrapper", "lyricmorph-backend/app/services/ace_step_wrapper.py"],
        ["Stem separation", "lyricmorph-backend/app/services/stems_service.py"],
        ["Adaptive mixing", "lyricmorph-backend/app/mixer.py"],
        ["Executable research", "research/Skarly_Audio_Intelligence_Research.ipynb"],
    ], [2.35 * inch, 4.0 * inch]), p("All paths are relative to the repository root. Report generated from the local working tree.", "Smallx")]

    doc.build(story, onFirstPage=first_page, onLaterPages=later_page)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    build()
