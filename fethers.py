import os
import glob
import tempfile
import yt_dlp

try:
    import instaloader
except ImportError:
    instaloader = None  # only needed for the carousel path

YT_EXTRACTOR_ARGS = {"youtube": {"player_client": ["tv", "web_safari"]}}

def probe_content_type(url: str) -> str:
    """Classify a URL as 'video' or 'carousel' before downloading anything.

    YouTube (Shorts or regular videos) and Instagram Reels are always
    'video'. An instagram.com/p/... link could be a single image, a single
    video, or a multi-slide carousel — we ask yt_dlp for its info dict
    (no download) and check whether it reports a real video track. If not,
    treat it as a carousel, since yt_dlp is unreliable at actually pulling
    multi-image carousels and instaloader is a better tool for that.
    """
    if "instagram.com/p/" in url and "/reel/" not in url:
        ydl_opts = {"quiet": True,
                    "skip_download": True,
                    "extractor_args": YT_EXTRACTOR_ARGS,
                    }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info.get("vcodec") and info.get("vcodec") != "none":
                return "video"
        except Exception:
            pass
        return "carousel"
    return "video"


def fetch_video(url: str) -> str:
    """Downloads the actual video (Instagram Reel or YouTube video/Short) —
    not just the audio track — so Gemini can see frames as well as hear
    audio. Returns the local file path.
    """
    tmp_dir = tempfile.mkdtemp(prefix="video_")
    out_template = os.path.join(tmp_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": out_template,
        "format": "mp4/best[ext=mp4]/best",
        "quiet": True,
        "merge_output_format": "mp4",
        "extractor_args": YT_EXTRACTOR_ARGS,

    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        if not os.path.exists(path):
            # merge_output_format can rename the extension after postprocessing
            candidates = glob.glob(os.path.join(tmp_dir, "*"))
            if not candidates:
                raise FileNotFoundError(f"yt_dlp reported success but no file found in {tmp_dir}")
            path = candidates[0]
    return path


def fetch_caption_text(url: str) -> str:
    """Pulls the post/video's own written caption or description — the part
    creators use for 'these are the 5 habits...' style content with no
    useful speech (background music + a caption doing all the work).
    """
    ydl_opts = {"quiet": True,
                "skip_download": True,
                "extractor_args": YT_EXTRACTOR_ARGS,
                }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return (info.get("description") or "").strip()


def fetch_carousel_images(url: str) -> tuple[list[str], str]:
    """Downloads every slide of an Instagram carousel post plus its caption.
    Returns (list_of_image_paths_in_slide_order, caption_text).

    NOTE: anonymous Instagram scraping gets rate-limited/blocked fast — the
    same problem you already hit with Reddit. This is far more reliable
    with a logged-in session: log in once locally with
    `instaloader.Instaloader().login(user, pass)` then
    `.save_session_to_file(path)`, and point INSTALOADER_SESSION_FILE /
    INSTALOADER_USERNAME env vars at that saved session. Without a session
    this will work sometimes and get blocked other times.
    """
    if instaloader is None:
        raise RuntimeError("instaloader is not installed — run: pip install instaloader")

    tmp_dir = tempfile.mkdtemp(prefix="carousel_")
    loader = instaloader.Instaloader(
        dirname_pattern=tmp_dir,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )

    session_file = os.environ.get("INSTALOADER_SESSION_FILE")
    ig_user = os.environ.get("INSTALOADER_USERNAME")
    if session_file and ig_user and os.path.exists(session_file):
        loader.load_session_from_file(ig_user, session_file)

    shortcode = url.rstrip("/").split("/")[-1]
    post = instaloader.Post.from_shortcode(loader.context, shortcode)
    loader.download_post(post, target=tmp_dir)

    image_paths = sorted(glob.glob(os.path.join(tmp_dir, "*.jpg")))
    caption_text = post.caption or ""
    return image_paths, caption_text


def fetch_instagram_audio(url: str) -> str:
    """Kept for backward compatibility / as an audio-only fallback if a full
    video download ever fails. Prefer fetch_video() for new code — it gives
    Gemini frames as well as audio.
    """
    tmp_dir = tempfile.mkdtemp(prefix="audio_")
    out_template = os.path.join(tmp_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": out_template,
        "format": "bestaudio/best",
        "quiet": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "extractor_args": YT_EXTRACTOR_ARGS,

        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        base, _ = os.path.splitext(path)
        mp3_path = base + ".mp3"
        if os.path.exists(mp3_path):
            return mp3_path
        if os.path.exists(path):
            return path
    candidates = glob.glob(os.path.join(tmp_dir, "*"))
    if not candidates:
        raise FileNotFoundError(f"yt_dlp reported success but no file found in {tmp_dir}")
    return candidates[0]