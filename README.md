# paper-digest

A self-hosted weekly digest of new scientific papers. It queries arXiv and OpenAlex,
downloads the PDFs, reads them with a local LLM, and emails you a detailed report.

Out of the box it tracks AI, computer vision, audio and video signal processing, and
sign language technology, but the topics are just keyword weights in a config file, so
it works for any field.

Reports are written in English.

## How it works

```
1. Collect     arXiv API + OpenAlex, sliding window of N days
2. Select      keyword scoring, SQLite dedup so a paper is never reported twice
3. Read        PDF download, text extraction, smart truncation
4. Summarize   structured summary from a local LLM (Ollama)
5. Report      HTML + Markdown
6. Deliver     SMTP
```

Everything except step 4 is lightweight and runs comfortably on a Raspberry Pi. Step 4
is always an HTTP call to an Ollama server, which may be the same machine or another
one on your network.

## Requirements

- **Docker** and the Compose plugin
- **[Ollama](https://ollama.com)** with a model pulled, reachable over HTTP
- An **SMTP account** to send the report (Gmail works, with an app password)

### Setting up Ollama

Install Ollama, then pull a model:

```bash
ollama pull qwen3.5:9b
```

`qwen3.5:9b` needs roughly 6 GB of VRAM. On a smaller GPU use `qwen3.5:4b`, which is
about 3 GB and noticeably weaker on long documents but perfectly usable. Any model
Ollama can serve will work; set the name in `config.yaml`.

**If Ollama runs on a different machine than this project**, it must listen on the
network rather than on localhost only. Set the environment variable `OLLAMA_HOST` to
`0.0.0.0:11434` on that machine and restart Ollama, then allow port 11434 through its
firewall. This is the single most common setup failure.

A Raspberry Pi cannot run a 9B model itself. On a Pi, point `ollama.url` at a desktop
or server that has a GPU.

## Configuration

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

Neither file is tracked by Git.

### What to replace, and where

| Value | File | Key | Notes |
| --- | --- | --- | --- |
| Ollama address | `config.yaml` | `ollama.url` | `http://IP:11434`. Use the machine's LAN IP, not `localhost`, unless Ollama runs in the same container network |
| Model name | `config.yaml` | `ollama.model` | Must match `ollama list` exactly |
| HTTP token | `config.yaml` | `http.token` | Any random string. Protects the manual trigger endpoint |
| Run day and time | `config.yaml` | `schedule` | `weekday: 0` is Monday |
| Your topics | `config.yaml` | `scoring.keywords` | Weight per keyword. The main lever |
| arXiv categories | `config.yaml` | `sources.arxiv.categories` | See the [arXiv taxonomy](https://arxiv.org/category_taxonomy) |
| Sender address | `.env` | `SMTP_USER` | |
| Sender password | `.env` | `SMTP_PASSWORD` | For Gmail this is an **app password**, not your account password |
| Recipient | `.env` | `MAIL_TO` | Comma-separated for several recipients |
| Contact email | `.env` | `OPENALEX_MAILTO` | Optional. Gets you into OpenAlex's faster polite pool |

Gmail app passwords are created at
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) and
require two-factor authentication on the account.

Everything else in `config.example.yaml` has a working default.

## Deploying with Docker

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

The container starts a scheduler that fires on the day and time set in
`config.yaml`, plus an HTTP endpoint on port 8137 for manual runs. It stays up between
runs and costs nothing while idle.

Data is persisted in `./data`, mounted into the container:

```
data/reports/    generated HTML and Markdown reports
data/pdf/        downloaded PDFs
data/state.sqlite  which papers have already been reported
```

Deleting `data/state.sqlite` makes the next run treat every paper as new.

### Checking the setup

Run these before waiting a week for the first scheduled report:

```bash
# Is the SMTP configuration correct? Sends a test email
docker compose run --rm digest test-mail

# Is Ollama reachable from inside the container?
docker compose run --rm digest test-ollama

# Full run, writes the report to data/reports/ without emailing it
docker compose run --rm digest run --no-mail --verbose
```

If `test-ollama` fails while Ollama works fine on its host, it is almost always the
`OLLAMA_HOST` binding described above.

### Updating

```bash
git pull
docker compose build
docker compose up -d
```

Your `config.yaml`, `.env` and `data/` are untouched.

## Running without Docker

Useful for development, or to validate the configuration before building an image.
Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**The `.env` file is loaded automatically**, the same one Docker reads. Real
environment variables take precedence over it, so a single value can be overridden
inline without editing the file:

```bash
MAIL_TO=someone.else@example.com python -m digest run --verbose
```

`.env` is resolved relative to the project root, so run these commands from there.

Then the same commands the container runs:

```bash
python -m digest test-ollama
python -m digest test-mail
python -m digest run --no-mail --verbose
python -m digest serve             # scheduler + HTTP endpoint, Ctrl+C to stop
```

The config file and the data directory are read from two optional environment
variables, defaulting to `config.yaml` and `./data` in the current directory. Useful
for keeping a throwaway setup next to the real one:

```bash
VEILLE_CONFIG=config.dev.yaml VEILLE_DATA=/tmp/digest-dev python -m digest run --no-mail
```

### Making the test loop fast

A default run collects hundreds of papers and reads fifteen in full, which takes 10 to
25 minutes. For a quick end-to-end check, copy `config.yaml` and shrink it:

- `window.lookback_days: 2`
- `selection.max_papers: 2`
- `ollama.wait_minutes: 0` so an unreachable Ollama fails immediately instead of
  retrying for an hour

That brings a complete run down to a couple of minutes. The report still lands in
`data/reports/`, so you can open the HTML in a browser and see exactly what the email
would look like.

## Triggering a run manually

```bash
curl -X POST -H "X-Token: your_token" http://HOST:8137/run
curl -H "X-Token: your_token" http://HOST:8137/status
```

`/run` starts a run in the background and returns immediately. `/status` reports
whether a run is in progress and how the last one ended.

## Tuning

| Key | Effect |
| --- | --- |
| `selection.max_papers` | Papers read in full. GPU time scales linearly |
| `selection.min_score` | Raise it if the digest is too noisy |
| `scoring.keywords` | Keyword weights. Title matches count double |
| `window.lookback_days` | Search window. Keep it aligned with the schedule |
| `extraction.max_chars` | Text sent to the model. Keep it under the context window |
| `ollama.num_ctx` | 8192 is safe on 8 GB of VRAM. With `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` on the Ollama host, try 16384 or 32768 and raise `max_chars` to match |
| `ollama.think` | Reasoning mode. Slow and unnecessary for structured summarization |
| `ollama.wait_minutes` | How long to wait if the Ollama machine is asleep when the job fires |

Budget roughly 40 to 90 seconds per paper on a consumer GPU, so 10 to 25 minutes for a
15-paper digest.

## Home Assistant integration (optional)

Trigger the digest by voice or from a dashboard. In `configuration.yaml`:

```yaml
rest_command:
  run_paper_digest:
    url: "http://DIGEST_HOST:8137/run"
    method: POST
    headers:
      X-Token: !secret digest_token

rest:
  - resource: "http://DIGEST_HOST:8137/status"
    scan_interval: 600
    headers:
      X-Token: !secret digest_token
    sensor:
      - name: "Paper digest"
        value_template: "{{ value_json.last_run.status if value_json.last_run else 'never' }}"
        json_attributes_path: "$.last_run.details"
        json_attributes:
          - selected
          - summarized
          - mail_sent
```

Add an `intent_script` and a file under `config/custom_sentences/` if you want a voice
command. Custom sentences require a full Home Assistant restart, not just a config
reload.

## Known limitations

- OpenAlex only exposes a PDF for open-access papers. Otherwise the summary is based on
  the abstract alone.
- arXiv rate-limits its API, so a 3-second delay is applied between requests.
- Summaries reflect extracted text only. Figures and image-based tables are ignored.
- Conference proceedings usually appear on arXiv first. OpenAlex is the safety net for
  journal publications.
- The summary quality is bounded by the model you run. A 4B model will miss nuances a
  9B model catches, especially on long papers.

## License

See `LICENSE`.