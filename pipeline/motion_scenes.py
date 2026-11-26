"""AI-authored HyperFrames scenes for the motion-graphics renderer.

For every narration beat the LLM writes three blocks — CSS, HTML and GSAP JS —
for a 1080x1920 animated scene. This module:

  * builds the authoring prompt (canvas, safe zones, palette, word timings),
  * extracts and sanitises the blocks (prefixes ids/classes so scenes can't
    collide, strips non-deterministic code, scopes element selectors),
  * wraps them in a valid HyperFrames sub-composition, and
  * provides a deterministic built-in fallback scene for when the AI's scene
    fails validation.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

W, H = 1080, 1920
# Where scene content may sit: inside the Shorts-safe area and above the caption band.
SAFE = {"x0": 120, "x1": 900, "y0": 300, "y1": 1040}
CAPTION_TOP = 1080
MAX_SCENE_WORDS = 10  # visible words allowed in a scene's HTML (keywords, not narration)

SYSTEM_PROMPT = f"""You are a senior motion designer who writes HyperFrames scenes: HTML + CSS + GSAP code \
that is rendered frame-by-frame into a vertical YouTube Short (1080x1920, 30fps).

You write ONE scene at a time. Reply with EXACTLY three fenced code blocks, in this order, nothing else:
```css
...styles...
```
```html
...markup (no <html>, <body>, <template>, <script> or <style> tags)...
```
```js
...GSAP code that adds tweens to the provided timeline `tl`...
```

ENVIRONMENT (already provided, do not recreate):
- A wrapper element (1080x1920, position:absolute, inset:0) contains your HTML. Background is already \
an animated gradient — keep your scene background TRANSPARENT.
- `tl` = a paused GSAP 3 timeline for this scene. Time 0 = scene start. `DUR` = scene length in seconds.
- `rand()` = seeded random in [0,1). `W`=1080, `H`=1920.
- CSS variables: --ink (main text), --accent, --accent2, --muted, --panel (translucent card fill), \
--font-display ("Archivo Black"), --font-body ("Montserrat").
- Color emoji render reliably and are the best way to show real things (🐕 🚀 🌍 🍯 🏔️).

LAYOUT RULES:
- Put ALL content inside x {SAFE['x0']}–{SAFE['x1']}px, y {SAFE['y0']}–{SAFE['y1']}px. Use position:absolute with \
left/top/width/height in px for every top-level element. y>{CAPTION_TOP} is reserved for captions — never put anything there.
- Keep the markup FLAT: hero, text and decorations are siblings at the top level, each with its own absolute \
canvas coordinates. If you do nest, a child's left/top are relative to its positioned parent, NOT the canvas.
- LAYOUT GRID (use it): HERO ZONE y 330–760 holds ONE dominant visual; TEXT ZONE y 800–1020 holds the keyword \
headline. Hero and text never overlap. Nothing above y 330.
- The hero must be BIG and fill the safe area: an emoji at font-size 260–420px, OR an inline SVG illustration \
~600–780px wide, OR a giant number 200–300px. Small icons floating in empty space are a failure.
- Around the hero add SUPPORTING MOTION behind it (z-index below): 6–14 small particles/dots, a pulsing ring, \
radiating lines, an SVG stroke draw-on, or a glow disc. Supporting elements may sit behind the hero but never behind text.
- On-screen text is KEYWORDS ONLY: ONE headline of 2–6 words (+ optionally one short label). NEVER write the \
narration sentence on screen and never make one span per narration word — captions already show it. \
At most 10 visible words in the whole scene; more is rejected automatically.
- The headline must fit inside the TEXT ZONE (y 800–1020, width ≤ 780px): at 120px, about 11 characters per line, \
max 2 lines. Use white-space:nowrap only if it fits; prefer shorter words over smaller type.
- Particles, sparkles, dots and rings must be empty <div>s styled with CSS (border-radius, background) or SVG \
shapes — never text characters or emoji — so they never count as overlapping text.
- Big type: headline 96–150px, numbers 150–260px, labels ≥ 40px. Bold, high contrast, uppercase optional.
- Never put text on top of other text, and never put an emoji or icon on top of text.

ANIMATION RULES (critical — breaking them breaks the render):
- Add every tween to `tl` with an explicit position: tl.fromTo(sel, {{from}}, {{to}}, timeInSeconds).
- Allowed: tl.fromTo, tl.to, tl.set, tl.from, gsap.set. FORBIDDEN: gsap.to / gsap.from / gsap.timeline / \
setTimeout / setInterval / requestAnimationFrame / Date / Math.random / fetch / play() / pause() / CSS @keyframes / \
CSS transition / CSS animation.
- Animate transforms (x, y, scale, rotation) and opacity — never left/top/width/height. \
Never put `transform` in CSS on elements you animate (use GSAP x/y/scale instead; set start state in fromTo).
- `repeat` must be a finite number (never -1). Keep every tween inside [0, DUR].
- Element entrances in the first 0.6s, then keep things moving (subtle drift, pulses, counters, draw-ons) — \
no dead frames. Start the scene exit (fade/scale/slide out) at DUR-0.35 and finish by DUR-0.05.
- Sync key reveals to the spoken word times you are given (reveal a number when it is said).
- Every id and class you use MUST start with the given prefix (e.g. s2-title). Select elements by id/class.
- Stagger with the `stagger` property inside the vars object (tl.fromTo(".s2-dot", {{...}}, {{..., stagger: 0.08}}, 0.2)) \
— never chain .stagger(). Only use the `tl` variable; never create other timelines.
- Counters: tween a plain object and write textContent in onUpdate. SVG: inline <svg> with stroke-dasharray draw-ons is great.

DESIGN GOAL: a premium, punchy explainer look — one clear visual idea per scene (a giant number, a comparison, \
an illustrated object made of emoji + shapes, a map pin, a timeline, a stamp, a progress bar). Vary layouts \
between scenes. Make it feel custom-made for THIS fact."""


def build_user_prompt(
    *,
    sid: str,
    index: int,
    total: int,
    title: str,
    narration: str,
    sentence: str,
    duration: float,
    words: list[dict[str, Any]],
    previous: list[str],
) -> str:
    role = "HOOK (first scene — must grab attention instantly; strong visual on frame 0)" if index == 0 else (
        "PAYOFF (final scene — memorable closer)" if index == total - 1 else "BUILD (supporting detail)"
    )
    word_times = ", ".join(f"{w['text']}@{w['t']:.2f}s" for w in words)
    prev = "\n".join(f"- {p}" for p in previous[-3:]) or "- (none yet)"
    return f"""VIDEO: "{title}"
FULL NARRATION: {narration}

THIS SCENE: {index + 1} of {total} — {role}
ID/CLASS PREFIX: {sid}-
DURATION (DUR): {duration:.2f}s
NARRATION DURING THIS SCENE: "{sentence}"
SPOKEN WORD TIMES (seconds from scene start): {word_times}

PREVIOUS SCENES (use a DIFFERENT layout/visual idea):
{prev}

Write the scene now (three code blocks: css, html, js)."""


# ── extraction & sanitising ───────────────────────────────────────────────

_FENCE = re.compile(r"```([a-zA-Z]*)\s*\n(.*?)```", re.S)

_JS_FORBIDDEN = [
    (r"\bsetTimeout\s*\(", "setTimeout"),
    (r"\bsetInterval\s*\(", "setInterval"),
    (r"\brequestAnimationFrame\s*\(", "requestAnimationFrame"),
    (r"\bDate\s*\.\s*now\b|\bnew\s+Date\b", "Date"),
    (r"\bperformance\s*\.\s*now\b", "performance.now"),
    (r"\bfetch\s*\(|XMLHttpRequest", "network access"),
    (r"\.\s*play\s*\(|\.\s*pause\s*\(", "play()/pause()"),
    (r"window\s*\.\s*__timelines", "window.__timelines"),
    (r"\bgsap\s*\.\s*(?:to|from|fromTo|timeline)\s*\(", "gsap.to/from/timeline (use tl.*)"),
    (r"\bimport\s|\brequire\s*\(", "imports"),
]
_HTML_FORBIDDEN = [
    (r"<\s*(script|iframe|video|audio|link|img|object|embed|template)\b", "forbidden tag"),
    (r"(?:src|href)\s*=\s*[\"']\s*https?:", "external URL"),
]


class SceneError(ValueError):
    pass


def extract_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for lang, body in _FENCE.findall(text or ""):
        lang = lang.lower()
        key = {"javascript": "js", "htm": "html"}.get(lang, lang)
        if key in ("css", "html", "js") and key not in blocks:
            blocks[key] = body.strip()
    if "html" not in blocks or "js" not in blocks:
        raise SceneError("reply must contain ```css, ```html and ```js code blocks")
    blocks.setdefault("css", "")
    return blocks


def _rename_tokens(src: str, mapping: dict[str, str], sigil: str) -> str:
    if not mapping:
        return src
    names = sorted(mapping, key=len, reverse=True)
    pat = re.compile(re.escape(sigil) + r"(" + "|".join(map(re.escape, names)) + r")(?![\w-])")
    return pat.sub(lambda m: sigil + mapping[m.group(1)], src)


def _rename_in_js_strings(js: str, ids: dict[str, str], classes: dict[str, str]) -> str:
    def fix(m: re.Match) -> str:
        s = m.group(0)
        s = _rename_tokens(s, ids, "#")
        s = _rename_tokens(s, classes, ".")
        # getElementById("x") / classList.add("x") style bare names
        quote, inner = s[0], s[1:-1]
        if inner in ids:
            return quote + ids[inner] + quote
        if inner in classes:
            return quote + classes[inner] + quote
        return s

    return re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`", fix, js)


def _scope_css(css: str, sid: str) -> str:
    """Drop @-rules, strip transitions/animations, scope bare element selectors."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # remove @-blocks (one nesting level) and @-statements
    css = re.sub(r"@[\w-]+[^{;]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    css = re.sub(r"@[\w-]+[^;{]*;", "", css)
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        body = re.sub(r"(?:^|;)\s*(?:transition|animation)[\w-]*\s*:[^;]*", ";", body)
        parts = []
        for s in sel.split(","):
            s = s.strip()
            if not s:
                continue
            if s in (":root", "html", "body", "*", "#root"):
                s = f'[data-composition-id="{sid}"] *' if s == "*" else f'[data-composition-id="{sid}"]'
            elif f"{sid}-" not in s:
                s = f'[data-composition-id="{sid}"] {s}'
            parts.append(s)
        if parts:
            out.append(f"{', '.join(parts)} {{{body.strip()}}}")
    return "\n".join(out)


def sanitize(blocks: dict[str, str], sid: str) -> dict[str, str]:
    html, css, js = blocks["html"], blocks["css"], blocks["js"]

    # pull any inline <style> into css, drop stray wrappers
    for m in re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S | re.I):
        css += "\n" + m
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"</?(?:html|head|body)[^>]*>", "", html, flags=re.I)

    # On-screen text must be keywords: a full sentence duplicates the captions and
    # overflows the text zone into the caption band.
    visible = html_lib.unescape(re.sub(r"<[^>]+>", " ", html))
    n_words = len([t for t in visible.split() if re.search(r"[A-Za-z]", t)])
    if n_words > MAX_SCENE_WORDS:
        raise SceneError(
            f"HTML has {n_words} words of visible text (max {MAX_SCENE_WORDS}). Do NOT write the narration on "
            "screen — captions already show it. Use a 2–6 word keyword headline plus at most one short label."
        )

    for pat, what in _HTML_FORBIDDEN:
        if re.search(pat, html, re.I):
            raise SceneError(f"HTML uses {what}")
    for pat, what in _JS_FORBIDDEN:
        if re.search(pat, js):
            raise SceneError(f"JS uses {what}")
    if "tl." not in js:
        raise SceneError("JS never adds tweens to `tl`")

    # deterministic replacements
    js = re.sub(r"\bMath\s*\.\s*random\s*\(\s*\)", "rand()", js)
    js = re.sub(r"repeat\s*:\s*-\s*1\b", "repeat: Math.ceil(DUR)", js)
    js = re.sub(r"\bconst\s+tl\s*=\s*[^;]+;", "", js)  # model re-declared the timeline
    # model re-declared a wrapper-provided binding (e.g. `const DUR = 4;`) → page-wide SyntaxError
    js = re.sub(r"\b(?:const|let|var)\s+(?:DUR|W|H|rand|_s)\s*=\s*[^;\n]*;?", "", js)
    js = re.sub(r"\bfunction\s+rand\s*\([^)]*\)\s*\{[^}]*\}", "", js)

    # prefix ids / classes so scenes never collide
    prefix = f"{sid}-"
    ids = {i: prefix + i for i in re.findall(r"\bid\s*=\s*[\"']([^\"']+)[\"']", html) if not i.startswith(prefix)}
    classes: dict[str, str] = {}
    for cl in re.findall(r"\bclass\s*=\s*[\"']([^\"']+)[\"']", html):
        for c in cl.split():
            if not c.startswith(prefix) and c != "clip":
                classes[c] = prefix + c

    def fix_attr_ids(m: re.Match) -> str:
        v = m.group(2)
        return f'{m.group(1)}"{ids.get(v, v)}"'

    html = re.sub(r"(\bid\s*=\s*)[\"']([^\"']+)[\"']", fix_attr_ids, html)

    def fix_attr_classes(m: re.Match) -> str:
        v = " ".join(classes.get(c, c) for c in m.group(2).split() if c != "clip")
        return f'{m.group(1)}"{v}"'

    html = re.sub(r"(\bclass\s*=\s*)[\"']([^\"']+)[\"']", fix_attr_classes, html)
    html = _rename_tokens(html, ids, "#")  # url(#grad), href="#sym"
    css = _rename_tokens(_rename_tokens(css, ids, "#"), classes, ".")
    js = _rename_in_js_strings(js, ids, classes)

    # never let scene markup time itself — the scene host owns timing
    html = re.sub(r"\sdata-(?:start|duration|track-index|composition-[\w-]+)\s*=\s*[\"'][^\"']*[\"']", "", html)

    return {"html": html.strip(), "css": _scope_css(css, sid), "js": js.strip()}


def wrap_scene(sid: str, parts: dict[str, str], duration: float, seed: int) -> str:
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; overflow: visible; color: var(--ink); font-family: var(--font-body); }}
    /* hard floor: scene content can never reach the caption band */
    #{sid}-safe {{ position: absolute; left: 0; top: 0; width: {W}px; height: {CAPTION_TOP - 20}px; overflow: hidden; }}
{_indent(parts['css'], 4)}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="{W}" data-height="{H}">
    <div id="{sid}-safe">
{_indent(parts['html'], 6)}
    </div>
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      const DUR = {duration:.3f}, W = {W}, H = {H};
      let _s = {seed % 2147483647 or 1};
      const rand = () => ((_s = (_s * 16807) % 2147483647) - 1) / 2147483646;
      {{
{_indent(parts['js'], 8)}
      }}
      window.__timelines["{sid}"] = tl;
{_indent(_fit_js(sid), 6)}
    }})();
  </script>
</template>
"""


def _fit_js(sid: str) -> str:
    """Shrink any text element that overflows its own box or the safe area.

    Static layout only (font-size); uses offset geometry, so GSAP transforms are
    ignored and the result is the same at every seek position. Runs immediately
    and again once web fonts are ready (Archivo Black is wider than fallbacks).
    """
    x0, x1, y1 = SAFE["x0"], SAFE["x1"], CAPTION_TOP - 40
    return f"""function fitText() {{
  const stage = document.getElementById("{sid}-safe");
  if (!stage) return;
  const pos = (el) => {{
    let x = 0, y = 0, n = el;
    while (n && n !== stage) {{ x += n.offsetLeft || 0; y += n.offsetTop || 0; n = n.offsetParent; }}
    return {{ x, y }};
  }};
  const bad = (el) => {{
    if (el.scrollWidth > el.clientWidth + 2) return true;
    const p = pos(el), r = p.x + el.offsetWidth, b = p.y + el.offsetHeight;
    return p.x < {x0} - 2 || r > {x1} + 2 || b > {y1};
  }};
  const texty = Array.from(stage.querySelectorAll("*")).filter((el) =>
    !(el instanceof SVGElement) &&
    Array.from(el.childNodes).some((c) => c.nodeType === 3 && /[A-Za-z0-9]/.test(c.textContent)));
  texty.forEach((el) => {{
    const base = parseFloat(getComputedStyle(el).fontSize) || 0;
    if (!base || !el.offsetWidth) return;
    const dims = () => el.scrollWidth + "x" + el.offsetWidth + "x" + el.offsetHeight;
    let size = base, before = dims();
    while (bad(el) && size > base * 0.45) {{
      size *= 0.92; el.style.fontSize = size.toFixed(1) + "px";
      const now = dims();
      if (now === before) {{  // box-driven: font size no longer helps, undo this step
        size /= 0.92; el.style.fontSize = size >= base - 0.1 ? "" : size.toFixed(1) + "px"; break;
      }}
      before = now;
    }}
  }});
}}
fitText();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitText);"""


def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else "" for line in text.splitlines())


# ── built-in fallback scene ───────────────────────────────────────────────

_STOP = set("""a an the and or but of to in on at for with by from is are was were be been it its this that these those
as than then so very just did do does you your we our they their he she his her i me my not no yes into over under
about after before up down out off what which who whom how why when where can could would should will shall may might
must has have had more most such""".split())


def _key_words(words: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    scored = []
    for i, w in enumerate(words):
        t = re.sub(r"[^\w%$.,' -]", "", w["text"]).strip(".,' ")
        if not t or t.lower() in _STOP:
            continue
        score = len(t)
        if re.search(r"\d", t):
            score += 20
        if t[0].isupper() and i > 0:
            score += 8
        scored.append((score, i, {**w, "text": t}))
    best = sorted(scored, key=lambda x: -x[0])[:limit]
    return [w for _, _, w in sorted(best, key=lambda x: x[1])]


def fallback_scene_parts(sid: str, words: list[dict[str, Any]], duration: float, index: int) -> dict[str, str]:
    """Deterministic kinetic-type scene: key words stack in on their spoken times over a pulsing ring."""
    keys = _key_words(words) or [{"text": "Did you know?", "t": 0.2}]
    p = sid
    rows = []
    js = [
        f'tl.fromTo("#{p}-ring", {{scale: 0.4, opacity: 0, rotation: -90}}, {{scale: 1, opacity: 1, rotation: 0, duration: 0.7, ease: "back.out(1.6)"}}, 0);',
        f'tl.to("#{p}-ring", {{rotation: 180, duration: Math.max(DUR - 0.8, 0.5), ease: "none"}}, 0.7);',
        f'tl.fromTo("#{p}-dot", {{scale: 0}}, {{scale: 1, duration: 0.5, ease: "elastic.out(1, 0.5)"}}, 0.15);',
        f'tl.to("#{p}-dot", {{scale: 1.18, duration: 0.6, yoyo: true, repeat: Math.max(1, Math.floor(DUR / 0.6) - 2), ease: "sine.inOut"}}, 0.7);',
        f'tl.fromTo("#{p}-bar", {{scaleX: 0}}, {{scaleX: 1, duration: 0.6, ease: "power3.out"}}, 0.3);',
    ]
    sizes = []
    for w in keys:
        n = len(w["text"])
        sizes.append(140 if n <= 6 else (112 if n <= 9 else max(64, int(1000 / n))))
    avail = SAFE["y1"] - 660
    need = sum(sizes) + 24 * (len(sizes) - 1)
    if need > avail:
        sizes = [int(z * avail / need) for z in sizes]
    top = 660
    for k, w in enumerate(keys):
        txt = html_lib.escape(w["text"].upper())
        size = sizes[k]
        color = "var(--accent)" if k == 0 else ("var(--ink)" if k == 1 else "var(--accent2)")
        rows.append(
            f'<div id="{p}-w{k}" class="{p}-word" style="top:{top}px;font-size:{size}px;color:{color}">{txt}</div>'
        )
        t = max(0.05, min(float(w["t"]), duration - 0.8))
        js.append(
            f'tl.fromTo("#{p}-w{k}", {{y: 80, opacity: 0, scale: 0.85}}, {{y: 0, opacity: 1, scale: 1, duration: 0.45, ease: "back.out(1.8)"}}, {t:.2f});'
        )
        top += size + 24
    js.append(
        f'tl.to("#{p}-stage", {{opacity: 0, scale: 0.94, duration: 0.3, ease: "power2.in"}}, Math.max(DUR - 0.35, 0.1));'
    )
    emoji_cycle = ["⚡", "🌍", "🔍", "💡", "⭐", "🧠", "🔥"]
    html = f"""<div id="{p}-stage" class="{p}-stage">
  <svg id="{p}-ring" class="{p}-ring" width="420" height="420" viewBox="0 0 420 420">
    <circle cx="210" cy="210" r="190" fill="none" stroke="var(--accent2)" stroke-width="10" stroke-dasharray="40 26" stroke-linecap="round"/>
  </svg>
  <div id="{p}-dot" class="{p}-dot">{emoji_cycle[index % len(emoji_cycle)]}</div>
  <div id="{p}-bar" class="{p}-bar"></div>
  {''.join(rows)}
</div>"""
    css = f"""
.{p}-stage {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; }}
.{p}-ring {{ position: absolute; left: 300px; top: 220px; }}
.{p}-dot {{ position: absolute; left: 360px; top: 280px; width: 300px; height: 300px; border-radius: 50%;
  background: var(--panel); display: flex; align-items: center; justify-content: center; font-size: 150px; }}
.{p}-bar {{ position: absolute; left: 310px; top: 618px; width: 400px; height: 12px; border-radius: 6px;
  background: var(--accent); transform-origin: left center; }}
.{p}-word {{ position: absolute; left: {SAFE['x0']}px; width: {SAFE['x1'] - SAFE['x0']}px; text-align: center;
  font-family: var(--font-display); line-height: 1; letter-spacing: -0.01em; text-shadow: 0 8px 30px rgba(0,0,0,.35); }}
"""
    return {"html": html, "css": _scope_css(css, sid), "js": "\n".join(js)}


def scene_summary(parts: dict[str, str]) -> str:
    """Very short description of a scene's markup, fed back so the next scene varies its layout."""
    text = re.sub(r"<[^>]+>", " ", parts.get("html", ""))
    text = " ".join(text.split())[:80]
    kinds = []
    h = parts.get("html", "")
    if "<svg" in h:
        kinds.append("svg")
    if "onUpdate" in parts.get("js", ""):
        kinds.append("counter")
    return f"{'/'.join(kinds) or 'text'}: {text}" if text else "/".join(kinds) or "graphic"


def dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False)
