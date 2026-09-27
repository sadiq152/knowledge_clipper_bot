import os
import glob
import tempfile
import yt_dlp
import requests
import re
import pickle
try:
    import instaloader
except ImportError:
    instaloader = None  # only needed for the carousel path

YT_EXTRACTOR_ARGS = {"youtube": {"player_client": ["tv", "web_safari", "ios", "android"]}}

_IG_COOKIE_PATH = None

def _instagram_cookiefile():
    """Builds a Netscape-format cookies file for yt-dlp from the instaloader
    session file, so yt-dlp can fetch Instagram posts that need a login.
    Returns None if no usable session exists.
    """
    global _IG_COOKIE_PATH
    if _IG_COOKIE_PATH and os.path.exists(_IG_COOKIE_PATH):
        return _IG_COOKIE_PATH

    session_file = os.environ.get("INSTALOADER_SESSION_FILE")
    if not session_file or not os.path.exists(session_file):
        return None
    try:
        with open(session_file, "rb") as f:
            cookies = pickle.load(f)
    except Exception:
        return None
    if not isinstance(cookies, dict) or not cookies.get("sessionid"):
        return None

    fd, path = tempfile.mkstemp(prefix="igcookies_", suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for name, value in cookies.items():
            f.write(f".instagram.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}\n")
    _IG_COOKIE_PATH = path
    return path

def _base_opts(url: str) -> dict:
    opts = {"quiet": True,}
    if "instagram.com" in url:
        cookiefile = _instagram_cookiefile()
        if cookiefile:
            opts["cookiefile"] = cookiefile
    return opts

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
        ydl_opts = {**_base_opts(url),
                    "skip_download": True,
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
        **_base_opts(url),
        "outtmpl": out_template,
        "format": "mp4/best[ext=mp4]/best",
        "merge_output_format": "mp4",

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
    ydl_opts = {
        **_base_opts(url),
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return (info.get("description") or "").strip()

def fetch_carousel_images(url: str) -> tuple[list[str], str]:
    """Downloads every slide of an Instagram post plus its caption.
    Returns (list_of_image_paths_in_slide_order, caption_text).
    """
    if instaloader is None:
        raise RuntimeError("instaloader is not installed — run: pip install instaloader")

    m = re.search(r"instagram\.com/(?:[\w.]+/)?(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Could not extract Instagram shortcode from: {url}")
    shortcode = m.group(1)

    loader = instaloader.Instaloader(
        quiet=True,
        download_videos=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
    )

    session_file = os.environ.get("INSTALOADER_SESSION_FILE")
    ig_user = os.environ.get("INSTALOADER_USERNAME")
    if session_file and ig_user and os.path.exists(session_file):
        loader.load_session_from_file(ig_user, session_file)

    post = instaloader.Post.from_shortcode(loader.context, shortcode)

    # Read slide URLs straight from the post data instead of using
    # download_post(), which has a fragile logged-in code path.
    if post.typename == "GraphSidecar":
        edges = post._field("edge_sidecar_to_children", "edges")
        urls = [e["node"]["display_url"] for e in edges]
    else:
        urls = [post.url]
    urls = [u for u in urls if u]
    if not urls:
        raise RuntimeError("No slide images found in this post")

    tmp_dir = tempfile.mkdtemp(prefix="carousel_")
    image_paths = []
    for i, img_url in enumerate(urls, start=1):
        resp = requests.get(img_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        path = os.path.join(tmp_dir, f"slide_{i:02d}.jpg")
        with open(path, "wb") as f:
            f.write(resp.content)
        image_paths.append(path)

    return image_paths, post.caption or ""