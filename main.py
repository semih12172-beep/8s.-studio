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

class PromptsRequest(BaseModel):
    storyboard_json: str
    style: str
    aspect_ratio: str

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
                    yield f"data: {json.dumps({'error': f'Gemini API error {resp.status_code}: {body.decode()[:200]}'})}\n\n"
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


@app.post("/api/generate-script")
async def generate_script(req: ScriptRequest):
    revision_block = f"\n\n【修改要求】\n{req.revision}" if req.revision else ""

    prompt = f"""你是一位顶尖电影编剧，擅长将概念转化为精炼有力、具有画面感的剧本。

【项目规格】
核心故事：{req.story}
目标时长：{req.duration}
画幅比例：{req.aspect_ratio}
创作风格：{req.style}{revision_block}

【输出要求】
- 使用标准剧本格式：场景标题（INT./EXT. 场景 时间）、动作描述、对白
- 每个场景描述必须有具体的视觉画面感（光线、色调、构图）
- 控制在目标时长范围内
- 语言精炼有力，避免平铺直叙
- 直接输出剧本正文，无需任何前言或说明"""

    return sse_response(stream_gemini(prompt))


@app.post("/api/generate-storyboard")
async def generate_storyboard(req: StoryboardRequest):
    prompt = f"""你是一位专业电影分镜师。将以下剧本拆解为精确的工业级分镜表。

【项目规格】
目标时长：{req.duration}
画幅比例：{req.aspect_ratio}
创作风格：{req.style}

【剧本内容】
{req.script}

【严格输出格式】
直接输出JSON数组，禁止使用markdown代码块（不要```json）：
[
  {{
    "shot_number": 1,
    "shot_type": "大全景",
    "duration": "4s",
    "camera_movement": "固定",
    "visual_description": "具体的画面描述，包括构图、光线方向、色调、主体动作",
    "dialogue_sfx": "对白原文 或 音效描述，无则填—"
  }}
]

景别（shot_type）可选：大特写 / 特写 / 近景 / 中景 / 全景 / 大全景
运镜（camera_movement）可选：固定 / 推 / 拉 / 摇 / 移 / 跟 / 升 / 降
时长格式：数字+s（如 3s、5s、8s）"""

    return sse_response(stream_gemini(prompt, temperature=0.7))


@app.post("/api/optimize-shots")
async def optimize_shots(req: OptimizeShotsRequest):
    prompt = f"""你是一位顶尖电影分镜师。请优化以下分镜表，提升其电影感、节奏感和视觉叙事层次。

【项目规格】
风格：{req.style}
时长：{req.duration}
画幅：{req.aspect_ratio}

【当前分镜】
{req.shots_json}

【优化方向】
1. 增强视觉描述的具体性和电影感（光线质感、色调、构图细节）
2. 优化景别组合，使节奏更有变化
3. 运镜更精准，与情绪/叙事匹配
4. 时长分配更合理

以完全相同的JSON结构输出优化结果，直接输出JSON数组，禁止markdown标记："""

    return sse_response(stream_gemini(prompt, temperature=0.75))


@app.post("/api/generate-prompts")
async def generate_prompts(req: PromptsRequest):
    prompt = f"""You are an expert AI prompt engineer for cinematic image and video generation.

Project Context:
- Visual Style: {req.style}
- Aspect Ratio: {req.aspect_ratio}

Storyboard:
{req.storyboard_json}

Generate one professional English prompt per shot, optimized for AI generation models (Runway Gen-3, Kling AI, Sora, Midjourney).

Output ONLY a JSON array (no markdown code blocks):
[
  {{
    "shot_number": 1,
    "prompt": "your detailed prompt here"
  }}
]

Each prompt must include:
- Shot type and framing (e.g. "extreme wide shot", "tight close-up")
- Camera movement as descriptive text (e.g. "slow push-in", "static locked")
- Specific lighting (direction, quality, color temperature)
- Color palette and mood/atmosphere
- Subject action and environment detail
- Technical style reference (e.g. "shot on ARRI ALEXA, anamorphic lens")
- Style keywords from: {req.style}
- Length: 50-80 words per prompt"""

    return sse_response(stream_gemini(prompt, temperature=0.8))
