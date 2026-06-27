#!/usr/bin/env python3
"""Two-phase sales copilot prototype for the AI business analyst test task."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
RESPONSES_URL = "https://api.openai.com/v1/responses"


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def extract_response_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str) and response["output_text"].strip():
        return response["output_text"].strip()

    parts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                parts.append(content["text"])
    if parts:
        return "\n".join(part.strip() for part in parts if part.strip()).strip()

    return json.dumps(response, ensure_ascii=False, indent=2)


def openai_response(
    *,
    api_key: str,
    model: str,
    instructions: str,
    user_input: str,
    max_output_tokens: int,
    timeout: int,
) -> tuple[str, dict[str, Any]]:
    payload = {
        "model": model,
        "instructions": instructions,
        "input": user_input,
        "max_output_tokens": max_output_tokens,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        RESPONSES_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenAI API request failed: {error.reason}") from error

    parsed = json.loads(raw)
    return extract_response_text(parsed), parsed


def compact_response_meta(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": response.get("id"),
        "model": response.get("model"),
        "status": response.get("status"),
        "usage": response.get("usage"),
    }


def phase1_input(sample: dict[str, Any]) -> str:
    relevant = {
        "product_context": sample["product_context"],
        "sales_manager": sample["sales_manager"],
        "client_card": sample["client_card"],
        "past_touchpoints": sample["past_touchpoints"],
        "upcoming_call": sample["upcoming_call"],
    }
    return (
        "Сформируй бриф фазы 1 по входным данным ниже.\n\n"
        "Входные данные JSON:\n"
        f"{json.dumps(relevant, ensure_ascii=False, indent=2)}"
    )


def phase2_input(sample: dict[str, Any], phase1_brief: str) -> str:
    relevant = {
        "product_context": sample["product_context"],
        "sales_manager": sample["sales_manager"],
        "client_card": sample["client_card"],
        "call_transcript": sample["call_transcript"],
    }
    return (
        "Разбери состоявшийся звонок фазы 2. Обязательно сравни звонок с брифом фазы 1.\n\n"
        "Бриф фазы 1:\n"
        f"{phase1_brief}\n\n"
        "Входные данные и транскрипт JSON:\n"
        f"{json.dumps(relevant, ensure_ascii=False, indent=2)}"
    )


def write_demo_html(sample: dict[str, Any], brief: str, review: str, model: str, path: Path) -> None:
    client = sample["client_card"]["company_name"]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    phase1_source = {
        "client_card": sample["client_card"],
        "past_touchpoints": sample["past_touchpoints"],
        "upcoming_call": sample["upcoming_call"],
    }
    phase2_source = {
        "brief_used": "outputs/phase1_brief.md",
        "call_transcript": sample["call_transcript"],
    }

    def pre(value: Any) -> str:
        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False, indent=2)
        return f"<pre>{html.escape(rendered)}</pre>"

    document = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sales Copilot Demo</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5c6773;
      --line: #d8dee6;
      --soft: #f6f8fa;
      --accent: #126b5f;
      --accent-soft: #e5f3ef;
      --warn: #8a5a00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
      line-height: 1.45;
    }}
    header {{
      padding: 28px 34px 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 21px;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0 0 10px;
      font-size: 16px;
      letter-spacing: 0;
      color: var(--accent);
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    main {{
      padding: 24px 34px 36px;
    }}
    section {{
      margin-bottom: 28px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 26px;
    }}
    section:last-child {{ border-bottom: 0; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(320px, 0.95fr) minmax(380px, 1.25fr);
      gap: 18px;
      align-items: start;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}
    .panel h3 {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--accent-soft);
    }}
    pre {{
      margin: 0;
      padding: 14px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      line-height: 1.48;
      background: var(--soft);
      max-height: 720px;
      overflow: auto;
    }}
    .output pre {{
      background: #ffffff;
      font-size: 13px;
    }}
    .note {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 900px) {{
      header, main {{ padding-left: 18px; padding-right: 18px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Sales Copilot: демо для {html.escape(client)}</h1>
    <div class="meta">
      <span>Модель: {html.escape(model)}</span>
      <span>Сгенерировано: {html.escape(generated_at)}</span>
      <span>Фазы связаны через бриф из outputs/phase1_brief.md</span>
    </div>
  </header>
  <main>
    <section id="phase1">
      <h2>Фаза 1 - подготовка к звонку</h2>
      <div class="grid">
        <div class="panel">
          <h3>Вход: карточка клиента и касания</h3>
          {pre(phase1_source)}
        </div>
        <div class="panel output">
          <h3>Выход: короткий бриф менеджеру</h3>
          {pre(brief)}
        </div>
      </div>
    </section>
    <section id="phase2">
      <h2>Фаза 2 - разбор после звонка</h2>
      <div class="grid">
        <div class="panel">
          <h3>Вход: бриф фазы 1 и транскрипт</h3>
          {pre(phase2_source)}
        </div>
        <div class="panel output">
          <h3>Выход: рекомендации и микро-урок</h3>
          {pre(review)}
        </div>
      </div>
      <p class="note">Скриншоты для сдачи: demo/screenshots/phase1.png и demo/screenshots/phase2.png.</p>
    </section>
  </main>
</body>
</html>
"""
    write_text(path, document)

    def single_phase_document(
        *,
        page_title: str,
        heading: str,
        source_title: str,
        source: Any,
        output_title: str,
        output: str,
    ) -> str:
        return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17202a;
      background: #ffffff;
      line-height: 1.45;
    }}
    header {{ padding: 28px 34px 18px; border-bottom: 1px solid #d8dee6; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 21px; letter-spacing: 0; }}
    h3 {{ margin: 0; padding: 12px 14px; font-size: 16px; color: #126b5f; background: #e5f3ef; border-bottom: 1px solid #d8dee6; }}
    main {{ padding: 24px 34px 36px; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px 14px; color: #5c6773; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: minmax(320px, 0.95fr) minmax(380px, 1.25fr); gap: 18px; align-items: start; }}
    .panel {{ border: 1px solid #d8dee6; border-radius: 8px; background: #fff; overflow: hidden; }}
    pre {{
      margin: 0;
      padding: 14px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      line-height: 1.48;
      background: #f6f8fa;
      max-height: 1060px;
      overflow: hidden;
    }}
    .output pre {{ background: #ffffff; font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(page_title)}</h1>
    <div class="meta">
      <span>Клиент: {html.escape(client)}</span>
      <span>Модель: {html.escape(model)}</span>
      <span>Сгенерировано: {html.escape(generated_at)}</span>
    </div>
  </header>
  <main>
    <h2>{html.escape(heading)}</h2>
    <div class="grid">
      <div class="panel">
        <h3>{html.escape(source_title)}</h3>
        {pre(source)}
      </div>
      <div class="panel output">
        <h3>{html.escape(output_title)}</h3>
        {pre(output)}
      </div>
    </div>
  </main>
</body>
</html>
"""

    write_text(
        path.parent / "phase1.html",
        single_phase_document(
            page_title="Sales Copilot - фаза 1",
            heading="Подготовка к звонку: вход -> бриф",
            source_title="Вход: карточка клиента и касания",
            source=phase1_source,
            output_title="Выход: короткий бриф менеджеру",
            output=brief,
        ),
    )
    write_text(
        path.parent / "phase2.html",
        single_phase_document(
            page_title="Sales Copilot - фаза 2",
            heading="Разбор звонка: бриф + транскрипт -> рекомендации",
            source_title="Вход: бриф фазы 1 и транскрипт",
            source=phase2_source,
            output_title="Выход: рекомендации и микро-урок",
            output=review,
        ),
    )


def run(args: argparse.Namespace) -> int:
    env = {**os.environ, **load_dotenv(PROJECT_ROOT / ".env")}
    api_key = env.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is missing in .env or environment.", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir

    sample = json.loads(input_path.read_text(encoding="utf-8"))
    prompt1 = read_text(PROJECT_ROOT / "prompts" / "phase1_brief.md")
    prompt2 = read_text(PROJECT_ROOT / "prompts" / "phase2_review.md")

    started = time.time()
    print(f"Running phase 1 with model {args.model}...")
    brief, raw1 = openai_response(
        api_key=api_key,
        model=args.model,
        instructions=prompt1,
        user_input=phase1_input(sample),
        max_output_tokens=args.max_output_tokens,
        timeout=args.timeout,
    )
    write_text(out_dir / "phase1_brief.md", brief)

    print("Running phase 2 with phase 1 brief as input...")
    review, raw2 = openai_response(
        api_key=api_key,
        model=args.model,
        instructions=prompt2,
        user_input=phase2_input(sample, brief),
        max_output_tokens=args.max_output_tokens,
        timeout=args.timeout,
    )
    write_text(out_dir / "phase2_review.md", review)

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "input_file": str(input_path.relative_to(PROJECT_ROOT)),
        "outputs": {
            "phase1_brief": str((out_dir / "phase1_brief.md").relative_to(PROJECT_ROOT)),
            "phase2_review": str((out_dir / "phase2_review.md").relative_to(PROJECT_ROOT)),
        },
        "duration_seconds": round(time.time() - started, 2),
        "phase1_response": compact_response_meta(raw1),
        "phase2_response": compact_response_meta(raw2),
        "secret_handling": "OPENAI_API_KEY was read from .env/environment and was not written to outputs.",
    }
    write_text(out_dir / "run_metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    write_demo_html(sample, brief, review, args.model, PROJECT_ROOT / "demo" / "demo.html")

    print(f"Saved {out_dir / 'phase1_brief.md'}")
    print(f"Saved {out_dir / 'phase2_review.md'}")
    print("Saved demo/demo.html")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a two-phase sales copilot prototype.")
    parser.add_argument("--input", default="data/sample_client.json", help="Path to synthetic client JSON.")
    parser.add_argument("--out", default="outputs", help="Output directory for generated Markdown files.")
    parser.add_argument("--model", default="gpt-5.4-mini", help="OpenAI model for both phases.")
    parser.add_argument("--max-output-tokens", type=int, default=2200, help="Max output tokens per phase.")
    parser.add_argument("--timeout", type=int, default=90, help="HTTP timeout in seconds.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
