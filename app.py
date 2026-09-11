import json
import re
import os
import time
from urllib.parse import quote_plus
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY", "")

if not api_key:
    raise ValueError("GEMINI_API_KEY not set - check your .env file")
client = genai.Client(api_key=api_key)

class LearningResource(BaseModel):
    name: str = Field(description="Name of the course, website, docs, or channel")
    type: str = Field(description="Type of resource, e.g. course, documentation, video, book, community")
    link_or_search_term: str = Field(description="A real URL if you know one, otherwise a good search term to find it")

class ProjectGuide(BaseModel):
    frontend_stack: list[str] = Field(default=[], description="Frontend languages/frameworks needed, e.g. HTML, CSS, JavaScript, React. Empty list if not applicable.")
    backend_stack: list[str] = Field(default=[], description="Backend languages/frameworks/databases needed, e.g. Python, Flask, PostgreSQL. Empty list if the project is purely frontend.")
    beginner_roadmap: str | None = Field(
        default=None,
        description=(
            "ONLY fill this if difficulty is 'beginner'. Write a short, numbered, jargon-free roadmap "
            "for someone who has never programmed before — pick ONE single simplest path, don't list "
            "alternative languages or frameworks to choose between, and explain WHY each step comes "
            "before the next. If difficulty is intermediate/advanced, leave this null."
        )
    )

class TakeawayItem(BaseModel):
    step_or_item_number: int
    headline: str = Field(description="Short title for this concept or project")
    explanation: str = Field(description="Clear explanation of the concept or project")
    code_or_formula: str | None = Field(default=None, description="Code snippet or formula if mentioned")
    tools_or_concepts: list[str] = Field(default=[], description="Tools, languages, or key terms mentioned")
    difficulty: str = Field(description="beginner, intermediate, or advanced")
    project_guide: ProjectGuide | None = Field(
        default=None,
        description="Fill this in ONLY if this takeaway is a buildable project/hobby, not a general concept."
    )

class EntertainmentDetails(BaseModel):
    movie_or_show_title: str | None = Field(
        default=None,
        description="Name of the movie, show, or franchise this clip is from — ONLY if you can identify it "
                    "with real confidence from what's visually/audibly recognizable. Leave null rather than "
                    "guessing if you're not sure; do not invent a plausible-sounding title."
    )
    characters: list[str] = Field(
        default=[],
        description="Named characters (and the actors playing them, if identifiable) appearing in the clip. "
                    "Leave empty if you can't confidently identify them — do not guess names."
    )
    scene_summary: str = Field(
        description="A real description of what happens in the scene: the setting, who is present, what "
                    "they say and do, and how it plays out. Write enough that someone who hasn't seen the "
                    "clip understands exactly what's shown — this should not be a one-line stub."
    )
    main_message: str = Field(
        description="The theme or message the scene conveys, and — if there's a natural broader-life "
                    "parallel (e.g. discipline, focus, ambition, teamwork) — how it could apply beyond the "
                    "scene itself. 2-4 sentences. Leave generic/empty if the clip is pure comedy or meme "
                    "content with no real message to draw out."
    )

class VideoAnalysisResult(BaseModel):
    title: str = Field(description="A clear, informative title for what this video is about")
    content_category: str = Field(
        description="Exactly 'learning' or 'entertainment'. 'learning' = teaches a project, skill, habit, "
                    "book, or any self-improvement/educational content. 'entertainment' = movie/show clips, "
                    "memes, comedy, drama, music, or anything with no teachable takeaway. When genuinely "
                    "mixed (e.g. a movie clip used to illustrate a lesson), choose based on which purpose "
                    "dominates — if the creator is clearly using it to teach something, use 'learning'."
    )
    content_type: str = Field(description="Category, e.g. coding_tutorial, project_walkthrough, movie_clip, comedy_skit, math_concept, habit_advice")
    summary: str = Field(description="2-4 sentences on what the video shows/says, written in third person")
    entertainment: EntertainmentDetails | None = Field(
        default=None,
        description="Fill this in ONLY if content_category is 'entertainment'. Leave null for 'learning' content."
    )
    is_project_or_hobby: bool = Field(default=False, description="Only relevant if content_category is 'learning'. True if this teaches a specific project to build or a hobby/skill to learn.")
    project_summary: str | None = Field(default=None, description="If is_project_or_hobby is True: what the project/hobby is and why it's worth doing. Otherwise null.")
    project_difficulty: str | None = Field(default=None, description="If is_project_or_hobby is True: overall difficulty — beginner, intermediate, or advanced. Otherwise null.")
    estimated_time: str | None = Field(default=None, description="If is_project_or_hobby is True: a realistic time estimate, e.g. '2-3 hours' or '1-2 weeks'. Otherwise null.")
    tools_required: list[str] = Field(default=[], description="Only relevant if content_category is 'learning'. Software, hardware, languages, or materials needed to follow along.")
    learning_resources: list[LearningResource] = Field(default=[], description="Only relevant if content_category is 'learning'. 2-4 real, well-known places to learn the underlying skill.")
    skills_learned: list[str] = Field(default=[], description="Only relevant if content_category is 'learning'. What someone will actually be able to do after completing this.")
    transcript: str = Field(default="", description="A cleaned-up version of what was said/shown. Only needed for 'learning' content — leave empty for 'entertainment'.")
    takeaways: list[TakeawayItem] = Field(default=[], description="Only relevant if content_category is 'learning'. The distinct concepts or steps covered, in order. Leave empty for 'entertainment' content.")
    action_checklist: str = Field(default="", description="Only relevant if content_category is 'learning'. Concrete next steps for someone acting on this video. Leave empty for 'entertainment'.")
    resources_mentioned: list[str] = Field(default=[], description="Only relevant if content_category is 'learning'. Books, links, tools, or references explicitly named.")

_CATEGORY_INSTRUCTIONS = """
    FIRST, decide content_category — this determines which fields you fill in:
    - "learning": teaches a project to build, a skill, a habit, a book, or any
      self-improvement/educational content. Fill title, content_type, summary,
      is_project_or_hobby and its related fields, tools_required,
      learning_resources, skills_learned, transcript, takeaways (with
      project_guide per relevant item), action_checklist, resources_mentioned.
      Leave "entertainment" null.
    - "entertainment": a movie/show clip, meme, comedy, drama, or anything
      with no teachable takeaway — even if it has an underlying theme like
      discipline or focus. Fill title, content_type, summary, and
      "entertainment" (movie_or_show_title only if you can confidently
      identify it — leave null rather than guessing; characters only if
      confidently identifiable; a real, detailed scene_summary — not a
      one-line stub; and main_message describing the theme and any broader
      real-life parallel). Leave takeaways as [], transcript/action_checklist
      as "", is_project_or_hobby as false, tools_required/learning_resources/
      skills_learned/resources_mentioned as [].
    - If genuinely mixed (e.g. a movie clip used deliberately to teach a
      lesson, with the creator narrating advice over it), classify by which
      purpose dominates — if there's a real actionable lesson being taught,
      use "learning"; if it's just a scene shared for its own sake, use
      "entertainment" even if it has a message worth noting in main_message.
    """

def analyse_url_with_search(
    url: str,
) -> dict:

    
    prompt = f"""
    Access and analyze the content of this URL: {url}

    First decide content_category: "learning" (teaches a project, skill, habit,
    book, or any self-improvement/educational content) or "entertainment"
    (no teachable takeaway — a movie/show discussion, meme, comedy, drama, etc.
    unlikely for a plain web page, but possible).

    If "learning": extract the main ideas, step-by-step points, tools/code,
    and an actionable to-do checklist.
    If "entertainment": fill "entertainment" with a real scene/content
    summary and the main message, and leave the learning-only fields
    (transcript, takeaways, action_checklist, resources_mentioned) empty.

    Output your response strictly as valid raw JSON matching this format:
    {{
      "title": "Title here",
      "content_category": "learning",
      "content_type": "Category here",
      "summary": "2-3 sentences overview",
      "entertainment": null,
      "transcript": "Key points or transcript details (learning only, else empty string)",
      "takeaways": [
        {{
          "step_or_item_number": 1,
          "headline": "...",
          "explanation": "...",
          "code_or_formula": null,
          "tools_or_concepts": ["..."],
          "difficulty": "beginner"
        }}
      ],
      "action_checklist": "Concrete steps the user should take next (learning only, else empty string)",
      "resources_mentioned": ["..."]
    }}

    If content_category is "entertainment", set "entertainment" to an object
    like:
    {{
      "movie_or_show_title": "Title or null if unsure",
      "characters": ["..."],
      "scene_summary": "What actually happens, in real detail",
      "main_message": "The theme/message and its broader parallel, if any"
    }}
    and set takeaways to [], transcript/action_checklist to "".

    Do not include any conversational filler or explanation outside the JSON.
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.2,
        ),
    ) 
    print(response)
    for candidate in response.candidates:
        print("Finish Reason:", candidate.finish_reason)
        print("Content parts:", candidate.content.parts)
    if not response.text:
    # Try extracting parts manually if available
        try:
            parts = response.candidates[0].content.parts
            raw_text = "".join([p.text for p in parts if getattr(p, "text", None)])
        except Exception:
            raw_text = ""

        if not raw_text:
            raise ValueError(
                f"Gemini returned empty text. Finish reason:"
                f" {response.candidates[0].finish_reason if response.candidates else 'Unknown'}"
            )
    else:
        raw_text = response.text
    cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.DOTALL).strip()

    return json.loads(cleaned_json)

def find_tutorial_links(project_name: str, tools: list[str]) -> list[dict]:
    """Runs a real Google Search grounded query and returns verified links.

    Always returns at least one usable entry: a real grounded tutorial when
    Gemini's search finds and confirms one, otherwise a direct YouTube search
    link so the user never gets an empty result for a named project.
    """
    tools_str = ", ".join(tools) if tools else ""
    prompt = f"""
    Find one good beginner-friendly video tutorial in English
    for building: "{project_name}" using {tools_str}.

    Respond with EXACTLY one line, nothing else — no preamble, no extra text:
    TITLE: <short video title> | CHANNEL: <channel name>

    Just name the video and the channel — I only need you to search, not summarize.
    If you can't find a good one, respond with exactly: NONE
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.2,
        ),
    )

    print(f"[find_tutorial_links] raw model text for {project_name!r}: {response.text!r}")

    raw = (response.text or "").strip()
    title, channel = None, None
    if raw and raw.upper() != "NONE":
        match = re.match(r'TITLE:\s*(.+?)\s*\|\s*CHANNEL:\s*(.+)', raw, re.IGNORECASE)
        if match:
            title, channel = match.group(1).strip(), match.group(2).strip()

    # Don't just grab grounding_chunks[0] blindly — collect a couple of
    # candidate source URLs, since the first chunk isn't guaranteed to be
    # the one that backs the specific title/channel line we parsed.
    grounded_urls = []
    try:
        grounding_metadata = response.candidates[0].grounding_metadata
        chunks = getattr(grounding_metadata, "grounding_chunks", None) or []
        for chunk in chunks[:2]:
            url = getattr(getattr(chunk, "web", None), "uri", None)
            if url:
                grounded_urls.append(url)
    except (AttributeError, IndexError):
        pass

    if title and grounded_urls:
        return [{
            "title": title,
            "channel": channel or "",
            "url": grounded_urls[0],
        }]

    # Fallback — grounding didn't come back with a usable result. Rather than
    # silently returning nothing, hand the user a direct search link so the
    # feature never just disappears.
    print(f"[find_tutorial_links] no grounded result for {project_name!r} — using search fallback")
    fallback_query = quote_plus(f"{project_name} tutorial for beginners")
    return [{
        "title": f"Search YouTube: {project_name} tutorial",
        "channel": "",
        "url": f"https://www.youtube.com/results?search_query={fallback_query}",
    }]
def analyse_reel(audio_path: str) -> dict:
    prompt = f"""
    You are analyzing the audio track of a short-form video (Reel/Short).
    {_CATEGORY_INSTRUCTIONS}

    For "learning" content, for any takeaway that is a specific project or
    hobby to build, fill in project_guide with a clear frontend/backend tool
    split. If the intended learner is a beginner, beginner_roadmap must
    avoid naming multiple competing languages or frameworks — commit to one
    simple path, and explain it like the person has never coded before.
    Do not fill project_guide for takeaways that are just general advice or
    concepts, not projects.

    IMPORTANT: for "learning" content, project_guide is decided PER
    TAKEAWAY, independently of the video-level is_project_or_hobby field. If
    a video lists several projects (e.g. "build an expense tracker", "build
    a notes app", "build a weather app"), each of those takeaways is its own
    project and MUST get its own project_guide filled in — even though
    you've already answered is_project_or_hobby/project_summary once for the
    video as a whole. Do not leave a takeaway's project_guide null just
    because you already described the video at the top level.

    If the audio doesn't contain enough information for a field, leave it
    empty rather than inventing details.
    """

    with open(audio_path, 'rb') as f:
        audio_file = f.read()

    audio_part = types.Part.from_bytes(data=audio_file, mime_type='audio/mp3')

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[prompt, audio_part],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoAnalysisResult,
            temperature=0.2,
        ),
    )
    data = json.loads(response.text)
    for item in data.get("takeaways", []):
        guide = item.get("project_guide")
        if guide:
            tools = guide.get("frontend_stack", []) + guide.get("backend_stack", [])
            guide["tutorial_links"] = find_tutorial_links(item.get("headline", ""), tools)

    return data


def _enrich_with_tutorial_links(data: dict) -> dict:
    """Shared post-processing: attach real tutorial_links to every takeaway
    that has a project_guide, whichever analyse_* function produced `data`.
    """
    for item in data.get("takeaways", []):
        guide = item.get("project_guide")
        if guide:
            tools = guide.get("frontend_stack", []) + guide.get("backend_stack", [])
            guide["tutorial_links"] = find_tutorial_links(item.get("headline", ""), tools)
    return data


def analyse_video(video_path: str, caption_text: str = "") -> dict:
    """Same as analyse_reel, but sends the actual video (frames + audio) to
    Gemini instead of an audio-only track. This is what gives the model
    'eyes' — it can read on-screen text/captions and recognize visual
    content, not just hear what's said. Use this for any Reel/Short instead
    of analyse_reel going forward; analyse_reel is left in place for
    audio-only fallback if a video download ever fails but an audio one
    succeeds.
    """
    prompt = f"""
    You are analyzing a short-form video (Reel/Short). You have both the
    audio track and the visual frames — use both. Read any on-screen text,
    captions, slides, or overlays that appear in the video, not just what is
    spoken; some creators put all the real information in on-screen text
    over a silent or music-only background.

    The post's own written caption (if any) is included below as extra
    context:
    ---
    {caption_text or "(no caption text provided)"}
    ---

    {_CATEGORY_INSTRUCTIONS}

    If the video shows footage you can't confidently identify (e.g. a movie
    or show clip), say so plainly (movie_or_show_title/characters null)
    rather than guessing a title, actor, or scene — do not invent an
    identification you're not confident in. But DO give a full, real
    scene_summary of what's actually shown/said even when you can't name the
    source material.

    For "learning" content: for any project or hobby taught in the video,
    fill in project_guide with a clear frontend/backend tool split. If the
    intended learner is a beginner, beginner_roadmap must commit to one
    simple path rather than listing alternatives. project_guide is decided
    PER TAKEAWAY, independently of the video-level is_project_or_hobby field
    — if several projects are shown, each gets its own project_guide, even
    though you already answered is_project_or_hobby once for the video as a
    whole.

    If a field can't be determined, leave it empty rather than inventing
    details.
    """

    uploaded = client.files.upload(file=video_path)

    # Video files need server-side processing before they can be referenced
    # in a generate_content call — poll until Gemini marks it ACTIVE.
    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state.name == "FAILED":
        raise ValueError(f"Gemini failed to process the uploaded video: {video_path}")

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[prompt, uploaded],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoAnalysisResult,
            temperature=0.2,
        ),
    )
    data = json.loads(response.text)
    return _enrich_with_tutorial_links(data)


def analyse_images(image_paths: list[str], caption_text: str = "") -> dict:
    """For Instagram carousel/slideshow posts with no audio at all — e.g.
    slide 1: 'Projects you should build', slide 2: project 1, slide 3:
    project 2, etc. Sends every slide as an image in one request, in slide
    order, so Gemini reasons across all of them together.
    """
    prompt = f"""
    You are analyzing a multi-slide Instagram carousel post. The images are
    provided in slide order (slide 1 first, immediately after this text).
    There is no audio — treat any text visible in the images (slide
    headings, bullet points, captions baked into the image) as the primary
    source of information.

    The post's own written caption (if any) is included below as extra
    context — use it, but the images are the primary source:
    ---
    {caption_text or "(no caption text provided)"}
    ---

    {_CATEGORY_INSTRUCTIONS}

    For "learning" content: for any project or hobby taught across the
    slides, fill in project_guide with a clear frontend/backend tool split,
    following the same per-item rule as usual — if slide 2 is "Project 1:
    expense tracker" and slide 3 is "Project 2: notes app", each is its own
    takeaway and needs its own project_guide.

    If a field can't be determined from the slides, leave it empty rather
    than inventing details.
    """

    parts = [prompt]
    for path in image_paths:
        with open(path, "rb") as f:
            image_bytes = f.read()
        ext = path.rsplit(".", 1)[-1].lower()
        mime_type = "image/png" if ext == "png" else "image/jpeg"
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoAnalysisResult,
            temperature=0.2,
        ),
    )
    data = json.loads(response.text)
    return _enrich_with_tutorial_links(data)