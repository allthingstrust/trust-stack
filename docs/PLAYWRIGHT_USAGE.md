# Playwright Usage

Playwright is an optional fetch strategy that the AR pipeline uses when a target page needs JavaScript rendering or the usual HTTP fetch returns thin or rejected content.

## When the pipeline switches to Playwright

1. The normal `requests`-based fetcher in `ingestion.page_fetcher` either returns a non-200 response (e.g., bot protection) **or** the parsed text is too short ("thin content").
2. The page fetcher logs `Attempting Playwright-rendered fetch...` and retries the URL using Playwright so the browser executes any client-side code before the HTML is handed back to the normal ingestion flow.
3. Playwright runs inside a headless Chromium browser, so it captures the fully rendered DOM before the AR pipeline extracts articles, metadata, and inline resources.

## Installing and enabling Playwright

1. Install the dependency:
   ```bash
   pip install playwright>=1.35.0
   ```
2. Provision the browsers (Chromium, Firefox, WebKit):
   ```bash
   playwright install
   ```
3. Enable the fallback via environment variable:
   ```bash
   export AR_USE_PLAYWRIGHT=1
   ```
   The pipeline checks this flag before invoking Playwright so the feature remains opt-in.

## Configuration notes

- The pipeline only uses Playwright for specific domains or when thin content is detected, so enabling the env var does not force Playwright for every page.
- Playwright is slower and heavier than a normal request, so keep it disabled by default unless you track JavaScript-heavy sources in your run.
- The `requirements.txt` already pins the dependency, and deployment docs (`docs/DEPLOYMENT.md`) list the same install steps if you need to provision Playwright on a production host.

## Operational tips

- Tail `logs/output.txt` (or `output_final.txt`) to verify whether the renderer kicked in; you will see lines like `Attempting Playwright-rendered fetch for ...` when the fallback fires.
- If Playwright fails due to missing browsers or firewall rules, the caller still receives the earlier HTTP error, so ensure the runtime environment allows headless Chromium to start.
- When debugging, reproduce the thin-content scenario locally by running `python reproduce_issue.py` against a JS-heavy URL with `AR_USE_PLAYWRIGHT=1` set.

Playwright lives entirely within the ingestion step, so the rest of the pipeline (scoring, reporting, etc.) sees the enriched HTML just like any other fetcher output.