# Multimodal Tool Routing Reference

---

## parse_pdf

**When to use:**
- Extract text, tables, and metadata from PDF files
- Analyze PDF documents for content summarization

**When NOT to use:**
- Non-PDF files → use `read_file`
- Image-only PDFs without OCR → results may be empty

---

## transcribe_audio

**When to use:**
- Convert speech in audio files to text with timestamps
- Transcribe recordings, voice memos, podcasts

**When NOT to use:**
- Generating audio from text → use `generate_audio`
- Non-audio files → use `read_file`

**Output note:** Returns text with timestamped segments.

---

## generate_image

**When to use:**
- Create images from text descriptions (AI image generation)
- Generate diagrams, illustrations, or concept art
- The image is auto-saved to `generated_images/` and displayed in the UI

**When NOT to use:**
- Analyzing existing images → use `analyze_image`
- Diagrams with structured data → prefer `emit_visualization` with Mermaid

**Output note:** Returns JSON with `saved_path` and `relative_path` to the saved PNG file.

---

## generate_audio

**When to use:**
- Convert text to spoken audio (text-to-speech / TTS)
- Create voiceovers, narration, or audio content from text
- The audio is auto-saved to `generated_audio/` as MP3

**When NOT to use:**
- Transcribing existing audio to text → use `transcribe_audio`
- Playing or streaming audio → save it first, then provide the path

**Output note:** Returns JSON with `saved_path` and `relative_path` to the saved MP3 file. Optional `voice` parameter: alloy, echo, fable, onyx, nova, shimmer.

---

## export_pdf

**When to use:**
- Convert markdown content to a PDF document
- Create formatted reports, documents, or presentations as PDF

**When NOT to use:**
- Reading existing PDFs → use `parse_pdf`
- Writing text files → use `write_file`

---

## Multimodal Tool Aliases

| Alias | Canonical |
|---|---|
| `parsepdf`, `pdf_parse`, `read_pdf` | `parse_pdf` |
| `transcribeaudio`, `speech_to_text` | `transcribe_audio` |
| `generateimage`, `create_image`, `dall_e` | `generate_image` |
| `generateaudio`, `text_to_speech`, `tts` | `generate_audio` |
| `exportpdf`, `markdown_to_pdf` | `export_pdf` |
