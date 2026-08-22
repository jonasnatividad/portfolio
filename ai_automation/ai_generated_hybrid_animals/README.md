# AI-Generated Hybrid Animals

An end-to-end content pipeline: an LLM writes an image prompt and social caption for a randomly generated hybrid-animal concept, an image model renders it, and the result is auto-posted to X (Twitter) with the caption and hashtags attached.

---

## Example Output

![Example generated hybrid animal](example_output.jpg)

---

## How It Works

1. **Randomize a concept** — Randomly picks two distinct animals, an environment, and an action from curated word lists (e.g. "a hybrid between a *lynx* and a *narwhal*, in a *fjord*, *gliding*")
2. **Prompt generation** — Sends the concept to GPT-3.5 to write a detailed image-generation prompt plus a Twitter-ready caption (≤185 characters), in a single structured response
3. **Image generation** — Feeds the generated prompt to Gemini 2.5 Flash Image ("Nano Banana") and saves the returned image bytes directly
4. **Publish** — Uploads the image and posts the caption + hashtags to X via the Tweepy API

```mermaid
flowchart LR
  RAND[Randomize animal pair\n+ environment + action] --> GPT[GPT-3.5:\nwrite image prompt + caption]
  GPT --> GEMINI[Gemini 2.5 Flash Image\n"Nano Banana":\ngenerate image]
  GEMINI --> SAVE[Save image bytes]
  SAVE --> POST[Post image + caption\nto X via Tweepy]
```

---

## Repo Structure

```
ai_generated_hybrid_animals/
├── main.py             # Randomize → prompt → generate → post
└── example_output.jpg  # Sample generated image
```

---

## Key Technical Decisions

**Single LLM call for both prompt and caption** — Rather than two separate API calls, one GPT-3.5 request returns a structured `Image prompt: ... Caption: ...` response that's parsed client-side, reducing latency and cost per run.

**Curated word lists over open-ended randomness** — Animals, environments, and actions are drawn from hand-picked lists rather than left fully open to the LLM, keeping output visually coherent and avoiding degenerate/duplicate combinations (the two animals are also guaranteed distinct).

**Gemini 2.5 Flash Image over DALL·E for rendering** — Nano Banana returns raw image bytes directly in the response (`inline_data`), removing the extra download-by-URL round trip DALL·E's API required.

**Credentials via environment variables** — OpenAI, Gemini, and X API keys are loaded from environment variables via `python-dotenv`, never hardcoded.

---

## Configuration

| Variable | Description |
|---|---|
| `OPEN_AI_API_KEY` | OpenAI API key (GPT-3.5 prompt + caption generation) |
| `GEMINI_API_KEY` | Google Gemini API key (image generation) |
| `X_API_KEY` | X (Twitter) API key |
| `X_API_SECRET_KEY` | X API secret key |
| `X_BEARER_TOKEN` | X bearer token |
| `X_ACCESS_TOKEN` | X access token |
| `X_ACCESS_TOKEN_SECRET` | X access token secret |
