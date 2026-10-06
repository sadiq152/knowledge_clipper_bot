# Knowledge Clipper Bot

#### A Telegram bot that turns any link — Instagram Reel, Instagram carousel post, YouTube video/Short, or a general web link (e.g. Reddit) — into a structured summary: a title, a short summary, key takeaways, an action checklist, and further learning resources. Content is classified and routed automatically, then analyzed with Google Gemini.
<div align="center">
  <img width="250" height="250" alt="Logo" src="https://github.com/user-attachments/assets/73701993-2387-4dd5-8539-42c447619b5a" />
</div>

How it works

<img width="360" height="640" alt="demo" src="https://github.com/user-attachments/assets/a7e115c9-e2d3-4adc-bd40-fa4c6bb97486" />

Send the bot a link and it picks one of three pipelines based on what the link is:

Content type	Pipeline
Instagram Reel	Downloaded with yt-dlp (video + audio), analyzed with Gemini multimodal
Instagram carousel (multi-image post)	Slide images pulled via instaloader, analyzed with Gemini vision

Instagram's /p/... links can be a single image, single video, or a multi-slide carousel, so the bot probes the link first (checking for a real video track) before deciding which pipeline to use.

The result is formatted as a Telegram message with two layouts depending on content type:

Learning layout — Key Insights, action checklist, skills learned, tutorial links, further resources
Entertainment layout — scene summary, characters, source, and the core message (for content with no teachable takeaway)
