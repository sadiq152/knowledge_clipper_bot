import os
import re
import threading
import sqlite3
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Import the functions you wrote
from fethers import probe_content_type, fetch_video, fetch_caption_text, fetch_carousel_images
from app import analyse_video, analyse_images, analyse_url_with_search

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live")

def run_web():
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()

threading.Thread(target=run_web, daemon=True).start()
load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set - check your .env file")

DB_PATH = "bot_logs.db"

def init_db():
    """Creates the interactions table if it doesn't exist yet. Safe to call
    every time the bot starts - CREATE TABLE IF NOT EXISTS is a no-op if
    the table is already there."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            message_text TEXT,
            bot_response TEXT,
            status TEXT,
            timestamp TEXT NOT NULL
            )
    """)
    conn.commit()
    conn.close()

def log_interaction(update: Update, message_text: str, bot_response: str, status: str = "ok"):
    """Records one message-in / response-out pair. Called from both /start
    and handle_message so every touch with the bot gets logged, not just
    successful link analyses. Never raises - a logging failure should
    never break the bot's actual reply to the user."""
    try:
        user = update.effective_user
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO interactions
               (user_id, username, first_name, message_text, bot_response, status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
               (
                   user.id,
                   user.username,
                   user.first_name,
                   message_text,
                   bot_response,
                   status,
                   datetime.now(timezone.utc).isoformat(),
               ),

        )
        conn.commit()
        conn.close()

    except Exception as e:
        print("Failed to log interaction:", e)
def sanitize(text) -> str:
    if text is None:
        return ""
    text = str(text)
    # Escape markdown special chars used by legacy "Markdown" parse_mode
    return re.sub(r'([_*`\[\]])', r'\\\1', text)

def format_bot_response(data: dict) -> str:
    """Formats the extracted JSON into clean Telegram markdown. Dispatches to
    a learning-style layout (Key Insights / checklist / skills / resources)
    or an entertainment-style layout (scene summary / message / source)
    based on content_category. Defaults to the learning layout if
    content_category is missing, for backward compatibility.
    """
    if data.get("content_category") == "entertainment":
        return format_entertainment_response(data)
    return format_learning_response(data)


def format_entertainment_response(data: dict) -> str:
    """Layout for movie/show clips, memes, and other content with no
    teachable takeaway — no Key Insights, no checklist, no difficulty tags.
    """
    title = data.get("title", "Untitled Content")
    summary = data.get("summary", "")
    content_type = data.get("content_type", "entertainment")
    ent = data.get("entertainment") or {}

    source = sanitize(ent.get("movie_or_show_title") or "")
    characters = ent.get("characters", [])
    characters_text = ", ".join(sanitize(c) for c in characters) if characters else ""
    scene_summary = sanitize(ent.get("scene_summary", ""))
    main_message = sanitize(ent.get("main_message", ""))

    parts = [
        f"🎬 *{sanitize(title)}*",
        f"🏷️ Category: `{content_type}`",
        "",
        f"_{sanitize(summary)}_",
    ]
    if source:
        parts += ["", f"📽️ *From:* {source}"]
    if characters_text:
        parts += ["", f"🎭 *Characters:* {characters_text}"]
    if scene_summary:
        parts += ["", f"📝 *Scene:*\n{scene_summary}"]
    if main_message:
        parts += ["", f"💭 *Message:*\n{main_message}"]

    return "\n".join(parts)


def format_learning_response(data: dict) -> str:
    """Layout for project/skill/habit content — Key Insights, action
    checklist, skills learned, tutorial links, and further resources.
    """
    title = data.get("title", "Untitled Content")
    summary = data.get("summary", "")
    content_type = data.get("content_type", "General")
     
    # Format checklist
    checklist = data.get("action_checklist", "")
    if isinstance(checklist, list):
        checklist_text = "\n".join([f"• [ ] {item}" for item in checklist])
    else:
        steps = re.split(r'(?=\d+\.\s)', str(checklist).strip())
        steps = [s.strip() for s in steps if s.strip()]
        checklist_text = "\n".join(f"• {sanitize(s)}" for s in steps) if steps else "_None provided_"
    # Format takeaways
    takeaways_text = ""
    for item in data.get("takeaways", []):
        num = item.get("step_or_item_number", "")
        headline = item.get("headline", "")
        explanation = item.get("explanation", "")
        code = item.get("code_or_formula")
        diff = item.get("difficulty", "")
        
        diff_tag = f" `[{diff.upper()}]`" if diff else ""
        takeaways_text += f"\n*{num}. {headline}*{diff_tag}\n{explanation}\n"
        if code:
            takeaways_text += f"```\n{code}\n```\n"
    skills = data.get("skills_learned", [])
    skills_text = "\n".join(f"• {sanitize(s)}" for s in skills) if skills else ""

    resources = data.get("learning_resources", [])
    resource_lines = []
    for r in resources:
        name = sanitize(r.get("name", ""))
        link = r.get("link_or_search_term", "")
        if link and link.startswith("http"):
            resource_lines.append(f"• [{name}]({link})")
        else:
            # Not a real URL — show as a search term instead of a broken link
            resource_lines.append(f"• {name} — search: _{sanitize(link)}_")
    resources_text = "\n".join(resource_lines)

    video_lines = []
    for item in data.get("takeaways", []):
        guide = item.get("project_guide")
        if not guide:
            continue
        for link in guide.get("tutorial_links", []) or []:
            vt = sanitize(link.get("title", "Tutorial"))
            vu = link.get("url", "")
            vc = sanitize(link.get("channel", ""))
            if not vu:
                continue
            if vc:
                video_lines.append(f"• [{vt}]({vu}) — _{vc}_")
            else:
                video_lines.append(f"• [{vt}]({vu})")
    video_starters_text = "\n".join(video_lines)
    parts = [
        f"📌 *{title}*",
        f"🏷️ Category: `{content_type}`",
        "",
        f"_{summary}_",
        "",
        f"💡 *Key Insights:*\n{takeaways_text.strip()}",
        "",
        f"📋 *Action Checklist:*\n{checklist_text}",
    ]
    if skills_text:
        parts += ["", f"🛠️ *Skills Learned:*\n{skills_text}"]
    if video_starters_text:
        parts += ["", f"▶️ *Instant Video Starters:*\n{video_starters_text}"]
    if resources_text:
        parts += ["", f"🔗 *Where to Learn More:*\n{resources_text}"]
 
    return "\n".join(parts)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 *Knowledge Clipper Bot*\n\n"
        "Send or share any link here:\n"
        "• *Instagram Reels*\n"
        "• *YouTube Shorts & Videos*\n"
        "I'll break them down into actionable steps and code snippets!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")
    log_interaction(update, "/start", welcome_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Extract the first URL found in the message
    url_match = re.search(r'(https?://[^\s]+)', text)
    if not url_match:
        await update.message.reply_text("Please share a valid link (Instagram or YouTube).")
        return

    url = url_match.group(1)
    status_msg = await update.message.reply_text("⏳ Fetching and analyzing content...")

    try:
        is_youtube = "youtube.com" in url or "youtu.be" in url
        is_instagram = "instagram.com" in url

        if is_youtube or is_instagram:
            content_type = "video" if is_youtube else probe_content_type(url)

            if content_type == "carousel":
                # Route 1: Instagram carousel post -> multiple images -> Gemini vision
                await status_msg.edit_text("🖼️ Downloading carousel slides...")
                image_paths, caption_text = fetch_carousel_images(url)

                await status_msg.edit_text("🧠 Analyzing slides with Gemini...")
                data = analyse_images(image_paths, caption_text)

                for path in image_paths:
                    if os.path.exists(path):
                        os.remove(path)
            else:
                # Route 2: Reel / Short -> real video (frames + audio) -> Gemini multimodal
                await status_msg.edit_text("🎬 Downloading video...")
                video_path = fetch_video(url)
                caption_text = fetch_caption_text(url)

                await status_msg.edit_text("🧠 Analyzing video with Gemini...")
                data = analyse_video(video_path, caption_text)

                if os.path.exists(video_path):
                    os.remove(video_path)

        # Route 3: Reddit / General Web -> Search Grounding
        else:
            await status_msg.edit_text("🔎 Accessing post content with Gemini Search...")
            data = analyse_url_with_search(url)

        # Format and return result
        reply = format_bot_response(data)
        try:
            await status_msg.edit_text(reply, parse_mode="Markdown")
            log_interaction(update, text, reply, status="ok")
        except Exception as parse_err:
            fallback_error = f"⚠️ Formatting error, showing raw text:\n\n{reply}"
            await status_msg.edit_text(fallback_error)
            log_interaction(update, text, fallback_error, status="Markdown_parse_error")
            print("Markdown parse error:", parse_err)
    except Exception as e:
        error_reply = f"❌ Failed to process: {str(e)}"
        await status_msg.edit_text(error_reply)
        log_interaction(update, text, error_reply, status="error")


if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Telegram Bot is running and waiting for links...")
    app.run_polling()