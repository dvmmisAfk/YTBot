# Session handoff — HyperFrames motion-graphics renderer

> **SHELVED (2026-11-26):** The user found the motion output not good enough. world_facts is back on the DeAPI
> image slideshow (`"renderer": "slideshow"`). The workflow is restored to public uploads, 8 a day. The motion code
> is still in the repo (`pipeline/motion_*.py`) and still runs with `--renderer motion` or `SHORT_RENDERER=motion`,
> but nothing uses it. Everything below is history for anyone who picks it up again.

_Last updated: 2026-11-26. Read this first when you pick the work back up._

## Goal

The **world_facts** channel currently makes slideshows: 5 AI images with captions. The goal is to replace that with
**custom animated motion graphics**, rendered by **HyperFrames** inside the GitHub Action.

The user's decisions:

- **Approach: hybrid AI-written scenes.** For every video, Groq (`openai/gpt-oss-120b`) writes fresh CSS, HTML and
  GSAP code for each scene. Each scene goes through these steps:
  1. The code is cleaned and checked locally.
  2. It is validated with `hyperframes check`.
  3. If it fails, the errors go back to the AI for one retry.
  4. If it still fails, a deterministic built-in fallback scene replaces it.
- **No AI images.** The video is animated graphics only.
- **world_facts only.** ghost_stories stays on the slideshow renderer.
- **Rollout: private uploads first.** The scheduled workflow should upload with `--privacy private` for a few days
  so the user can review quality before switching back to public.

## Already done and pushed (commit `7bec04b`)

- Groq retired `llama-3.1-8b-instant` and `llama-3.3-70b-versatile`. CI now uses `openai/gpt-oss-120b`.
- `pipeline/groq_script.py` falls back to another model when one is not found. gpt-oss models run with
  `reasoning_effort="low"` and `max_tokens` ≥ 4096.
- The models this key could use (as of 2026-11-26): `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`.

## Uncommitted work in progress (`git status`)

| File | State |
|---|---|
| `pipeline/edge_tts_synth.py` | ✅ Adds `synthesize_with_words()`, which returns `(duration, words[{text,start,end,sentence}], sentences)` using Edge TTS `boundary="WordBoundary"`. Tested and working. |
| `pipeline/groq_script.py` | ✅ Adds rate-limit handling and a `chat_text(system, user, max_tokens, temperature)` helper. Free tier on 120b is **8,000 tokens per minute**: per-minute 429s are retried after `retry-after`; daily-limit 429s mark the model exhausted and fall back to the next model. |
| `pipeline/motion_scenes.py` | ✅ New. Holds the scene-writing prompt (`SYSTEM_PROMPT`, `build_user_prompt`), `extract_blocks` (pulls the ```css/```html/```js blocks out of the reply) and `sanitize`. Sanitising bans timers, `Date`, `fetch`, `gsap.to`, external URLs and `<img>`/`<script>`; replaces `Math.random`→`rand()` and `repeat:-1`→finite; prefixes every id and class with `sN-`; scopes bare CSS selectors; strips CSS transitions and animations. Also `wrap_scene` (the sub-composition template with `tl`, `DUR`, `W`, `H`, `rand`) and `fallback_scene_parts` (kinetic keyword scene). |
| `pipeline/motion_video.py` | ✅ New. See "How `motion_video.py` works" below. |
| `scripts/run_short.py` | ⚠️ **Half edited and currently broken.** See "Next steps". |

### How `motion_video.py` works

- **`plan_scenes`:** one scene per sentence. Sentences shorter than 2.4 s are merged into a neighbour, with at most
  `MOTION_MAX_SCENES` scenes (default 6).
- **Root `index.html`:** animated gradient and blob background, the scene hosts, a captions sub-composition, a
  voiceover `<audio>`, and BGM (`dobb.mp3`, looped and trimmed with ffmpeg, volume 0.18).
- **`_captions_html`:** word-synced captions, 3 words per group. The current word is highlighted in the accent
  colour. Captions sit at y=1080 and x 120–900.
- **`check_project`:** runs `check --json --safe-zone shorts`. Its JSON has sections (`lint`, `runtime`, `layout`, …),
  each with `findings[{code, severity, message, sourceFile, fixHint, text}]`. It returns `(errors, issues)` keyed by
  scene id.
- **`build_motion_short(...)`:** does the authoring, check and repair rounds, then calls `render_project` →
  `npx --yes hyperframes@0.9.96 render --quality looks --fps 30`.
- **Environment variables:**
  - `HYPERFRAMES_VERSION` (default 0.9.96)
  - `HYPERFRAMES_CMD` (overrides the CLI command)
  - `MOTION_AI_SCENES=0` (fallback scenes only)
  - `MOTION_RENDER_QUALITY` (`draft`, `looks` or `delivery`)
  - `MOTION_MAX_SCENES`
- Secrets (`GROQ_*`, `YT_*`, …) are removed from the environment passed to the CLI.

## Test results so far

- **Fallback-only build** (`MOTION_AI_SCENES=0`): passed the check and rendered a 1080×1920, 26.6 s MP4 with audio in
  about 220 s on draft quality, locally on Windows.
- **Bugs found and fixed after that test:**
  - Fallback keywords overlapped the captions.
  - Multi-word tokens lost their spaces ("NOVEMBER1957").
  - Captions crossed the Shorts right-edge safe zone.
  - Captions used CSS variables in GSAP colour tweens (now literal colours).
- **First full AI-authored test:** finished. It rendered a 26.6 s video in 90 s on draft quality, with 5 scenes; 3 kept
  their AI scenes and 2 were replaced by fallbacks. The output was in a temporary scratchpad folder and may be gone.
  What it showed:
  - **Bug, must fix:** s4 re-declared `const DUR`, which is already declared by `wrap_scene`. That caused a page-wide
    syntax error (`Identifier 'DUR' has already been declared`). Fix: in `sanitize()`, strip
    `(const|let|var) (DUR|W|H|rand|_s) = …;` declarations, as is already done for `tl`.
  - **Overlap:** `content_overlap` findings (emoji sitting on top of a headline) caused repairs, and in round 2 two
    scenes were swapped for fallbacks. Overlap seems to be reported as an error once it is severe.
  - **Quality:** the AI scenes work but look **sparse and underwhelming**: small emoji, a plain text block and lots of
    empty space. S2 also had text placed too high (Shorts top edge).
  - **Prompt changes to make in `SYSTEM_PROMPT`:**
    - Demand big hero visuals: emoji 260–420px, or an SVG illustration filling about 60% of the safe area.
    - Fill the safe area.
    - Ask for one dominant element plus supporting motion such as particles, rings and draw-ons.
    - Give a concrete layout grid: a hero zone at y 330–760 and a text zone at y 800–1020.
    - Possibly include one complete example scene in the prompt to anchor quality (it costs tokens).

## Status update (2026-11-26, later session)

Steps 1–4 are done and committed:

- `run_short.py` has `--renderer`, `_render_motion_and_upload` and `_finish`. world_facts has `"renderer": "motion"`.
- `sanitize()` strips re-declared `DUR`/`W`/`H`/`rand`/`_s`. Scene JS runs in its own block.
- Scenes with more than `MAX_SCENE_WORDS` (10) visible words are rejected, and the reason goes back for the retry.
- Every scene is wrapped in `#sN-safe`, a clip box ending at y 1060, so content can never cover the captions.
- `_fit_js` shrinks overflowing text (down to 45% at most), runs again on `document.fonts.ready`, and undoes the
  step when the box, not the font, is the problem.
- `composition script error: sN` runtime errors are now attributed to scene sN. Before this, a crashed s3 left
  6 s of blank frames that passed the check.
- `escaped_container` and `container_overflow` are now repairable warnings.
- The prompt asks for a big hero visual, a layout grid, keyword-only text, shape particles, stagger written as a
  property, and flat markup.
- The workflow has Node 22, the emoji font, npm and HyperFrames caching, a browser pre-warm, `--privacy private`,
  and uploads each run's mp4, `motion_status.json` and `script.json`.

Local test results:

- **Run 1:** 1 of 5 scenes kept its AI version (text overflowed into the captions).
- **Run 2:** 3 of 4 kept their AI version, and the visuals fit the topic (banana and strawberry).
- **Fit step:** re-checking run 2 with the fit step gave no errors.

## Next steps

1. Watch the manual workflow run: render time, Groq token use, and the private upload.
2. Review the private uploads for a few days. Then switch `--privacy private` back to `public` in
   `.github/workflows/world_facts.yml`.
3. Possible improvements:
   - Built-in fallback scenes look plain: a small icon, and weak keyword choice ("KNOW").
   - Hero emoji are still on the small side.
   - Frame 0 is background-only (the thumbnail).

## Risks to watch

- **Groq daily tokens:** a video costs about 25–35k tokens (5–6 scene calls plus the script). 8 runs a day may go
  over 120b's daily limit; the code then falls back to `gpt-oss-20b`. Consider fewer runs or fewer scenes if that
  happens.
- **Groq per-minute limit:** 8k tokens per minute means pauses of about 40 s between scene calls. That is expected
  and fits inside the job's 60-minute timeout.
- **CI render time:** GitHub runners have no GPU. Expect roughly 4–10 min per Short.
- **gsap CDN:** `index.html` loads gsap from jsdelivr (the HyperFrames scaffold default). It should be fine in CI.

## Useful local commands

- **HyperFrames CLI for manual checks:**
  `node "C:/Users/Divyam/.claude/skills/hyperframes/scripts/plugin-cli.mjs" check --json` (run it inside a generated
  `output/runs/<run>/motion` project).
- **Python 3.13 locally:** set `PYTHONIOENCODING=utf-8`, or the emoji in the logs crash the Windows console.
