# Hero background video — generation brief

Prompt and specs for the 15-second loop that sits behind the landing-page headline.

> **Status: installed.** A generated clip is live at `frontend/assets/hero-loop.mp4`.
> Source was 1280×720, 24 fps, 15.07 s, 8.8 MB with a stray AAC track. Re-encoded to
> **1.78 MB, 14.33 s, no audio**, with a 0.8 s crossfade closing the loop (the shot is a slow
> push-in, so first and last frames did not match — the seam now measures 2.7/255 mean
> difference, i.e. invisible). Keep the prompt below for regenerating or producing variants.

---

## Where the file goes

| | |
|---|---|
| **File name** | `hero-loop.mp4` |
| **Repo path** | `frontend/assets/hero-loop.mp4` |
| **Served URL** | `/assets/hero-loop.mp4` |
| **VPS path** | `/var/www/protactics/frontend/assets/hero-loop.mp4` |

The name and location are **not adjustable** — [landing.html](frontend/landing.html) probes this exact
URL with a `HEAD` request and mounts the video only if it returns 200. Drop the file in, commit,
`git pull` on the server. No code change, no restart: `frontend/` is bind-mounted and served from disk.

Until the file exists, the hero falls back to the canvas radar animation. Nothing breaks either way.

---

## Read this before generating

The video is **not** shown at full strength. It is composited like this:

```css
.hero-stage video{object-fit:cover;opacity:.22;mix-blend-mode:screen;filter:saturate(130%) contrast(115%);}
```

Three consequences that decide whether the footage works at all:

1. **`mix-blend-mode:screen` makes black transparent.** Only pixels brighter than the background
   show. Footage must be **near-black with small, intense highlights**. A flat mid-grey shot will
   render as grey haze that washes out the headline.
2. **`opacity:.22` throws away 78% of it.** Low-contrast footage disappears entirely. Push contrast
   hard in the source: crushed blacks, hot speculars.
3. **An elliptical mask hides the edges** (`ellipse 60% 75% at 50% 42%`). Keep the subject centred;
   assume the outer third is invisible. And the centre sits **directly behind white headline text**,
   so keep it comparatively calm — busy motion dead-centre fights legibility.

Also: it plays `muted`, `loop`, `autoplay`, `playsinline`. **Audio is irrelevant — it will never be
heard.** The loop point must be invisible.

---

## The prompt

Paste as-is into Sora, Veo, Runway Gen-3, Kling, or Pika. Written in English because every major
generator is trained on English captions. **2,396 characters** — 1,604 under the 4,000 limit, so
there is room to bolt on extra direction if your generator wants it.

```text
A 15-second continuous cinematic aerial shot of a working container port terminal at night, filmed
during deep blue hour. Photorealistic, shot on a full-frame cinema camera with an anamorphic 40mm
lens, shallow atmospheric depth.

Subject: rows of stacked shipping containers receding into darkness, three towering ship-to-shore
gantry cranes in silhouette, one crane trolley gliding slowly along its boom. A container vessel
berthed alongside. Wet asphalt on the quay reflecting the light. Faint sea haze drifting through the
beams, catching them.

Lighting: the scene is overwhelmingly dark — deep navy-black sky, black water, containers reading
almost as silhouettes. Illumination comes only from small intense point sources: warm amber sodium
floodlights on the crane gantries, cool cyan-white LED work lamps along the quay, scattered red
aircraft-warning beacons pulsing slowly on the crane peaks, and their long specular reflections
smeared across wet ground and still water. High dynamic range, crushed blacks, glowing highlights,
strong contrast between the black mass of the terminal and the bright pinpoints of light.

Color palette: near-black backdrop, electric cyan, warm amber-orange, occasional deep gold. Cold
teal shadows. No warm daylight, no sunrise, no colour cast in the sky.

Camera motion: one single unbroken take, no cuts. A very slow, steady lateral drift to the right
combined with an almost imperceptible push forward, as if from a slowly hovering drone. Smooth and
weightless, no handheld shake, no whip pans, no speed ramps. The movement should feel patient and
observational.

Composition: the centre of frame stays relatively calm and dark — a broad open stretch of quay — with
the brightest activity, cranes and light clusters arranged toward the lower third and the left and
right edges.

Loop: the final frame must match the opening frame closely enough to loop seamlessly and invisibly.

Mood: precise, industrial, controlled, quietly powerful. The feeling of a large logistics operation
running smoothly through the night under constant surveillance.

Negative: no text, no lettering, no numbers, no logos, no readable brand names on containers, no
watermarks, no people, no faces, no vehicles driving toward camera, no lens flares sweeping across
frame, no rapid cuts, no strobing, no daylight, no fog machine haze, no cartoon or CGI look, no
oversaturation.
```

---

## Encoding

Generators output oversized files. Re-encode before committing:

```bash
ffmpeg -i raw.mp4 \
  -vf "scale=1920:-2,format=yuv420p" \
  -c:v libx264 -profile:v main -preset slow -crf 26 \
  -movflags +faststart -an -t 15 \
  frontend/assets/hero-loop.mp4
```

- `-an` strips audio — it can never be heard, so it is pure payload.
- `-movflags +faststart` puts the index first so playback starts before the full download.
- `-crf 26` is deliberately soft. At 22% opacity behind text, compression artefacts are invisible,
  and this is a decorative asset on a page people load to log in.
- **Target: 2–4 MB.** Above ~6 MB, reconsider — the canvas fallback costs nothing and looks good.

If the generated loop point is visible, crossfade the tail into the head:

```bash
ffmpeg -i raw.mp4 -filter_complex \
  "[0]split[a][b];[a]trim=0:14.5,setpts=PTS-STARTPTS[main];
   [b]trim=14.5:15,setpts=PTS-STARTPTS[tail];
   [main][tail]xfade=transition=fade:duration=0.5:offset=14[v]" \
  -map "[v]" -c:v libx264 -crf 26 -an frontend/assets/hero-loop.mp4
```

---

## Checking it

After deploying, confirm the browser actually mounts it:

```bash
curl -s -o /dev/null -w "%{http_code} %{size_download}\n" http://161.97.77.100:8090/assets/hero-loop.mp4
```

A 200 means the `HEAD` probe will succeed and the video will appear. Then load the landing page and
check the one thing that matters: **the headline must still read cleanly.** If the text has gone
muddy, the footage is too bright — regenerate darker, or drop `opacity` from `.22` to `.15` in
[landing.html](frontend/landing.html).

### Two gotchas when testing

**Headless Chrome reports `prefers-reduced-motion: reduce`.** The video and the canvas radar both
sit behind that guard, so a plain headless screenshot shows *neither* and looks like a broken
deploy. Pass `--force-prefers-no-reduced-motion` to see what a real visitor sees:

```bash
chrome --headless=new --force-prefers-no-reduced-motion \
       --autoplay-policy=no-user-gesture-required \
       --window-size=1440,900 --screenshot=hero.png http://localhost:8000/
```

**The video does not load below 760 px viewport width.** That is deliberate — 1.78 MB for a
hero a few centimetres tall, usually over mobile data, is a bad trade. The canvas animation
still runs there.
