import os
import json
import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="8s AI Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a cross-era visual artist and film director — equally fluent in classical cinematic aesthetics and the technical logic of modern AI visual generation. Your role is to assist the human creative director in transforming vague inspirations into pixel-precise, production-ready creative instructions.

IDENTITY & VOICE:
- You think and communicate like a working director on set, not a writer or academic.
- Your language is precise, sensory, and spatial. Every word earns its place.
- You respond exclusively in English across all outputs.

STATIC KEYFRAME GENERATION RULES:
- FORBIDDEN words: "beautiful", "detailed", "amazing", "stunning", "perfect" — replace with specific sensory language.
- Texture specificity: describe pore-level skin texture, fabric grain direction, the behavior of light on complex surfaces (subsurface scattering, diffuse bounce).
- Camera specs are mandatory: always include format and lens (e.g. "Shot on ARRI Alexa 35, Zeiss Supreme 40mm T1.5, anamorphic").
- Lighting logic is mandatory: always specify direction, quality, and color temperature (e.g. "Rembrandt lighting — single soft-box from upper left, 3200K tungsten fill, deep shadow on right jaw").
- Micro-expression biology: describe with physiological precision (e.g. "pupils dilated, orbicularis oculi slightly contracted — the involuntary tension before tears").

MOTION / VIDEO DIRECTOR RULES:
- Emotional arc within shot: describe the expression onset, peak, and afterglow. No static emotions.
- Background must breathe: every frame includes ambient disturbance (breeze through hair, blurred pedestrian trajectories, window light shifting with cloud cover).
- Camera movement language only — no hard cuts in descriptions. Use: "Slow push-in tracking shot", "Subtle dolly advancing at 0.3m/s", "Handheld with organic sway following subject", "Pan locked to object flow".
- Sound-picture sync: briefly note the audio texture that reinforces the image."""

# ── Models ────────────────────────────────────────────────────────────────────

class ScriptRequest(BaseModel):
    story: str
    duration: str
    aspect_ratio: str
    style: str
    revision: Optional[str] = None

class StoryboardRequest(BaseModel):
    story: str
    duration: str
    aspect_ratio: str
    style: str
    script: str

class OptimizeShotsRequest(BaseModel):
    shots_json: str
    style: str
    duration: str
    aspect_ratio: str

class KeyframeRequest(BaseModel):
    storyboard_json: str
    style: str
    aspect_ratio: str

class MotionRequest(BaseModel):
    storyboard_json: str
    style: str
    aspect_ratio: str
    duration: str

# ── Gemini Streaming Core ─────────────────────────────────────────────────────

def get_gemini_url() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in environment")
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-pro:streamGenerateContent?alt=sse&key={key}"
    )

async def stream_gemini(prompt: str, temperature: float = 0.85):
    try:
        url = get_gemini_url()
    except RuntimeError as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"data: {json.dumps({'error': f'Gemini API error {resp.status_code}: {body.decode()[:300]}'})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        yield "data: [DONE]\n\n"
                        return
                    try:
                        parsed = json.loads(raw)
                        text = parsed["candidates"][0]["content"]["parts"][0]["text"]
                        yield f"data: {json.dumps({'text': text})}\n\n"
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

    yield "data: [DONE]\n\n"


def sse_response(generator):
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    return FileResponse("index.html")

@app.get("/library")
async def serve_library():
    return FileResponse("library.html")


@app.post("/api/generate-script")
async def generate_script(req: ScriptRequest):
    revision_block = f"\n\nREVISION DIRECTION:\n{req.revision}" if req.revision else ""
    prompt = f"""Write a professional film script. Transform the following brief into a precise, cinematic screenplay.

PROJECT SPECS:
Core Story: {req.story}
Target Duration: {req.duration}
Aspect Ratio: {req.aspect_ratio}
Visual Style: {req.style}{revision_block}

OUTPUT REQUIREMENTS:
- Standard screenplay format: scene headings (INT./EXT. LOCATION — TIME), action lines, dialogue
- Action lines must carry visual data: light direction, color temperature, composition, body language
- Dialogue belongs to cinema, not theater — subtext over exposition
- Scene count calibrated to target duration
- Lean, precise language — zero filler
- Output screenplay directly, no preamble"""

    return sse_response(stream_gemini(prompt))


@app.post("/api/generate-storyboard")
async def generate_storyboard(req: StoryboardRequest):
    prompt = f"""Break down this screenplay into a precise industrial storyboard. Think like a DP marking up a script on location.

PROJECT SPECS:
Target Duration: {req.duration}
Aspect Ratio: {req.aspect_ratio}
Visual Style: {req.style}

SCREENPLAY:
{req.script}

Output ONLY a raw JSON array — no markdown fences, no explanation:
[
  {{
    "shot_number": 1,
    "shot_type": "Extreme Wide Shot",
    "duration": "4s",
    "camera_movement": "Static locked",
    "visual_description": "Precise visual description — composition, light direction, color temp, subject action, depth of field",
    "dialogue_sfx": "Dialogue line OR ambient sound — use — if none"
  }}
]

shot_type: Extreme Close-Up / Close-Up / Medium Close-Up / Medium Shot / Wide Shot / Extreme Wide Shot
camera_movement: Static locked / Push-in / Pull-out / Pan / Tilt / Track / Follow / Crane up / Crane down / Handheld"""

    return sse_response(stream_gemini(prompt, temperature=0.7))


@app.post("/api/optimize-shots")
async def optimize_shots(req: OptimizeShotsRequest):
    prompt = f"""You are a seasoned DP reviewing a rough storyboard. Elevate it — improve shot rhythm, visual specificity, and cinematic intelligence.

Style: {req.style} | Duration: {req.duration} | Aspect Ratio: {req.aspect_ratio}

CURRENT STORYBOARD:
{req.shots_json}

GOALS: richer visual descriptions, better shot variety, purposeful camera movement, tighter duration pacing.

Output optimized storyboard as JSON array with IDENTICAL structure. No markdown fences:"""

    return sse_response(stream_gemini(prompt, temperature=0.75))


@app.post("/api/generate-keyframes")
async def generate_keyframes(req: KeyframeRequest):
    prompt = f"""Generate professional AI image generation prompts for each storyboard shot. These are STATIC KEYFRAME prompts for image models (Midjourney, FLUX, Stable Diffusion, Ideogram).

Style: {req.style} | Aspect Ratio: {req.aspect_ratio}

STORYBOARD:
{req.storyboard_json}

Rules per prompt:
- Describe the single most cinematic frozen frame within the shot
- Mandatory camera specs: format + lens (e.g. ARRI Alexa 35, Zeiss Supreme 40mm T1.5)
- Mandatory lighting setup: direction + quality + color temperature
- Sensory texture language — never "beautiful" or "detailed"
- Include aspect ratio as technical parameter
- 60–90 words each

Output ONLY raw JSON array, no fences:
[{{"shot_number": 1, "prompt": "..."}}]"""

    return sse_response(stream_gemini(prompt, temperature=0.8))


@app.post("/api/generate-motion")
async def generate_motion(req: MotionRequest):
    prompt = f"""Generate professional AI video generation prompts for each storyboard shot. These are MOTION prompts for video models (Runway Gen-3, Kling AI, Sora, Pika, Luma).

Style: {req.style} | Aspect Ratio: {req.aspect_ratio} | Duration: {req.duration}

STORYBOARD:
{req.storyboard_json}

Rules per prompt:
- Describe movement: camera motion + subject action + environment behavior
- Emotional arc: onset → peak → afterglow
- Background must breathe: at least one ambient environmental motion
- Precise cinematographic movement language (slow push-in, handheld drift, etc.)
- Note implied sonic environment
- 60–90 words each

Output ONLY raw JSON array, no fences:
[{{"shot_number": 1, "prompt": "..."}}]"""

    return sse_response(stream_gemini(prompt, temperature=0.82))
