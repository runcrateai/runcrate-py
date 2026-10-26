# Runcrate Python SDK

Official Python SDK for the [Runcrate](https://runcrate.ai) API.

## Installation

```bash
pip install runcrate-sdk
```

## Quick Start

```python
from runcrate import Runcrate

client = Runcrate(api_key="rc_live_...")

# Chat completion
response = client.models.chat_completion(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# List GPU instances
instances = client.instances.list()

# Create an instance
instance = client.instances.create(
    name="training-run",
    ssh_key_id="key_abc123",
    gpu_type="A100",
)

# Check status
status = client.instances.get_status(instance.id)
print(status.status, status.ip)

# Check billing
balance = client.billing.get_balance()
print(f"Credits: ${balance.credits_balance}")

client.close()
```

## Async Usage

```python
import asyncio
from runcrate import AsyncRuncrate

async def main():
    async with AsyncRuncrate(api_key="rc_live_...") as client:
        response = await client.models.chat_completion(
            model="meta-llama/Meta-Llama-3.1-8B-Instruct",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)

asyncio.run(main())
```

## Configuration

```python
client = Runcrate(
    api_key="rc_live_...",                        # or set RUNCRATE_API_KEY env var
    base_url="https://runcrate.ai",               # infra API (default)
    inference_url="https://api.runcrate.ai",      # model inference API (default)
    timeout=30.0,                                 # request timeout in seconds
    max_retries=3,                                # retry on 429/5xx with exponential backoff (Retry-After honoured up to 60s; never a 502 launch_refused)
)
```

Reads, updates and deletes are retried on 429, 5xx, timeouts and lost connections. A request that creates or launches something is never sent twice by accident:

- Job submits and reruns send an `Idempotency-Key`, which the server honours, so they are retried like reads.
- Instance, schedule and volume creates also send an `Idempotency-Key`, but those routes do not deduplicate it yet; `schedules.run_now` sends none. Once one of these, or a run-now, may have reached Runcrate (a timeout, a lost connection, a 500, 502 or 504) it is not sent again and the error is raised: check `instances.list()` before launching again. Only a 429 or 503, which say nothing was launched, and a connection that never opened are retried.
- A launch waits at least 75 seconds (a job submit 135) for its answer, whatever `timeout` is, so the client does not give up while the server is still launching.

## Model Inference

The `client.models` resource connects to `api.runcrate.ai` for AI model inference. Same API key works for both infrastructure and inference.

### Chat Completions

```python
# Standard request
response = client.models.chat_completion(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in 3 sentences."},
    ],
    max_tokens=256,
    temperature=0.7,
)
print(response.choices[0].message.content)
print(f"Tokens used: {response.usage.total_tokens}")

# Streaming
for chunk in client.models.chat_completion(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "Write a poem about GPUs"}],
    stream=True,
):
    delta = chunk.get("choices", [{}])[0].get("delta", {})
    print(delta.get("content", ""), end="", flush=True)
```

### Image Generation

```python
result = client.models.generate_image(
    model="black-forest-labs/FLUX.1-schnell",
    prompt="A futuristic city skyline at sunset",
    width=1024,
    height=1024,
)
# result.data[0].b64_json contains the base64-encoded image
```

### Video Generation

```python
# Submit video job (async processing)
job = client.models.generate_video(
    model="google/veo-3.0",
    prompt="A drone flyover of a mountain landscape",
    duration=8,
)
print(f"Job ID: {job.id}, Status: {job.status}")

# Poll until complete
import time
while True:
    job = client.models.get_video_status(job.id)
    print(f"Status: {job.status}")
    if job.status in ("completed", "failed"):
        break
    time.sleep(5)

# Download the video
if job.status == "completed":
    video_bytes = client.models.download_video(job.id)
    with open("output.mp4", "wb") as f:
        f.write(video_bytes)
```

### Text-to-Speech

```python
audio_bytes = client.models.text_to_speech(
    model="openai/tts-1",
    input="Hello, welcome to Runcrate!",
    voice="alloy",
    response_format="mp3",
)
with open("speech.mp3", "wb") as f:
    f.write(audio_bytes)
```

### Transcription (Speech-to-Text)

```python
with open("audio.wav", "rb") as f:
    result = client.models.transcribe(
        model="openai/whisper-1",
        file=f,
        filename="audio.wav",
    )
print(result.text)
print(f"Duration: {result.duration}s")
```

## Infrastructure Resources

### Instances

```python
client.instances.list(search="my-gpu")
client.instances.create(name="run", ssh_key_id="key", gpu_type="A100")
client.instances.get("instance-id")
client.instances.terminate("instance-id")
client.instances.get_status("instance-id")
client.instances.list_types(gpu_type="A100", region="us-east")
```

### Schedules

Start an instance or a job later: once at a time (`run_at`), or on a recurring 5-field `cron` read in an IANA `timezone`. A schedule starts within about 2 minutes of its time, as you, in the environment it was created in. `spec` is the create body of that kind and must set `max_runtime_minutes`.

```python
from datetime import datetime
from zoneinfo import ZoneInfo

# Every night at 02:00 London time
nightly = client.schedules.create(
    kind="job",
    cron="0 2 * * *",
    timezone="Europe/London",
    name="nightly-train",
    spec={"command": "python train.py", "gpu_type": "H100", "max_runtime_minutes": 120},
)
print(nightly.next_run_at)

# Once, tomorrow morning. run_at must carry a timezone: a naive datetime raises ValueError.
client.schedules.create(
    kind="instance",
    run_at=datetime(2026, 10, 21, 9, 0, tzinfo=ZoneInfo("Europe/London")),
    spec={"name": "eval-box", "gpu_type": "A100", "ssh_key_id": "key_abc123", "max_runtime_minutes": 60},
)

client.schedules.list()
client.schedules.get(nightly.id)
client.schedules.update(nightly.id, enabled=False)        # pause
client.schedules.update(nightly.id, enabled=True)         # resume from the next occurrence
client.schedules.update(nightly.id, cron="0 3 * * 1-5")   # retime
run = client.schedules.run_now(nightly.id)                # launch now; run.job or run.instance
client.schedules.delete(nightly.id)
```

Recurring runs must be at least 15 minutes apart, `run_at` can be up to 365 days ahead, and you can have at most 50 schedules per environment and 200 per workspace. `overlap="skip"` (the default) skips a run while the previous one is still live; `overlap="allow"` starts it anyway. `run_now` raises `InsufficientCreditsError` with `code == "BUDGET_REACHED"` when the environment's monthly budget is spent.

Each run launches as `schedule.run_as`, the person who created the schedule or last changed its spec or timing or resumed it, using the same kind of sign-in (`run_as_credential`: `"user"`, `"api_key"` or `"agent"`). If that API key is revoked or the agent sign-in ends, the schedule pauses with `last_status == "credential_revoked"`. Resume it to run as you.

#### Auto-stop for unattended work

When an agent or script launches instances, set a max runtime and an idle stop so a forgotten
instance ends on its own:

```python
instance = client.instances.create(
    name="agent-run",
    ssh_key_id="key_abc123",
    gpu_type="H100",
    max_runtime_minutes=240,   # terminate after 4 hours running (5 to 10080)
    idle_shutdown_minutes=30,  # terminate after 30 idle minutes (5 to 1440)
)

instance = client.instances.get(instance.id)
print(instance.auto_stop_at)   # when max runtime will stop it, or None
print(instance.stop_reason)    # None while running, else "user", "max_runtime", "idle",
                               # "budget", "low_balance", "failed" or "system"
```

- `max_runtime_minutes`: the clock starts when the instance first becomes running. An alert goes
  out 10 minutes before the stop.
- `idle_shutdown_minutes`: idle means GPU utilisation under 5% with nobody connected (SSH, web terminal or editor); GPU instances only.

Change the limits on a running instance, for example to extend before a long job. Max runtime
counts from when it started, so pass the total; an argument left out keeps its value and `None`
turns it off:

```python
client.instances.update(instance.id, max_runtime_minutes=480, idle_shutdown_minutes=None)
```
- Both default to `None` (no limit, idle stop off) and are left out of the request. Values out
  of range raise `UnprocessableEntityError` (HTTP 422, `validation_error`).

### Jobs

A job runs one command on its own fresh GPU machine, which stops (and stops billing) when the command ends. Files the command writes to `$RUNCRATE_OUTPUT_DIR` are kept 30 days.

```python
import os

job = client.jobs.run(
    command="python train.py --epochs 3 && cp model.pt $RUNCRATE_OUTPUT_DIR/",
    gpu_type=["A4000", "L40S"],     # tried in order; an entry may carry its count, "H100:2"
    max_runtime_minutes=60,         # required, 1 to 10080; each attempt stops after this long
    template="ubuntu-train",
    env={"HF_TOKEN": os.environ["HF_TOKEN"]},
    tags={"project": "vision"},
    max_retries=2,                  # a machine failure is retried; retry_on=["nonzero_exit"] retries the command's own
    code={"git": {"url": "https://github.com/acme/train", "ref": "main"}},
)

for chunk in client.jobs.follow_logs(job.id):   # the output as it is written, until the job ends
    print(chunk.text, end="")

done = client.jobs.wait(job.id, timeout=3600)   # polls with backoff; JobWaitTimeoutError past the timeout
print(done.status, done.exit_code, done.cost_usd)

for artifact in client.jobs.artifacts.list(job.id):
    client.jobs.artifacts.download(job.id, artifact.path, to=os.path.basename(artifact.path))
```

Send local code instead of a repository: `upload = client.jobs.uploads.upload("./my-project")` packs the directory (without `.git`, `__pycache__` and `node_modules`) and sends it; run with `code={"upload_id": upload.upload_id}` within 24 hours.

| Method | What it does |
|---|---|
| `jobs.run(**spec, idempotency_key=None)` | Runs one job. |
| `jobs.run_group(**spec, count= or params=, max_parallel=)` | Runs `count` copies, or one job per `params` entry (each merged over `env`); answers the group with its jobs. |
| `jobs.get(id)`, `jobs.list(status=, tags=, group_id=, q=, gpu_type=, created_after=, limit=, cursor=)`, `jobs.list_all(...)` | Reads jobs, newest first. `list` answers one page (`has_more`, `cursor`); `list_all` pages through. |
| `jobs.cancel(id)`, `jobs.delete(id)` | Cancels a live job; deletes a job that ended, with its logs and outputs. |
| `jobs.rerun(id, **overrides)` | Runs the spec again as a new job, with its env values; `env` is merged over them. |
| `jobs.logs(id, after=, limit=, follow=)`, `jobs.follow_logs(id, after=0)` | One page of output; or every chunk as it is written until the job ends. |
| `jobs.events(id)`, `jobs.metrics(id, step=)` | The timeline (queued, launch attempts, started, exited, ...); GPU use per step. |
| `jobs.wait(id, timeout=, poll_interval=2, max_poll_interval=30)` | Polls until the job ends, the gap doubling. |
| `jobs.artifacts.list(id)`, `.url(id, path)`, `.download(id, path, to=None)` | Outputs; a signed URL valid an hour (the API key never goes to it). |
| `jobs.uploads.upload(dir_or_tar_gz_or_bytes)` | Sends your code as a tar.gz. |
| `job_groups.get(id)`, `job_groups.cancel(id)` | A group's status counts and cost; cancels its live jobs. |

`AsyncRuncrate` has the same methods (`follow_logs` and `list_all` are async iterators). Every submit and rerun sends an `Idempotency-Key`, a new one per call or yours, and its retries reuse it: a retry after a timeout answers the first job instead of starting a second. Pass your own key to make a submit safe to repeat across processes for 24 hours.

### Environments

```python
client.environments.list()
client.environments.create(name="staging")
client.environments.get("env-id")
client.environments.update("env-id", name="production")
client.environments.delete("env-id")

env = client.environments.get("env-id")
print(env.monthly_budget_usd)    # None when the environment has no cap
print(env.month_to_date_usd)     # this UTC month's spend: GPU instances plus inference
print(env.budget_remaining_usd)  # None when the environment has no cap
```

Monthly budgets are read-only here. A workspace owner or admin sets them in the dashboard under
Workspace settings. At 100% of the budget, launches in that environment raise
`InsufficientCreditsError` with `code == "BUDGET_REACHED"`, running instances in it stop with
`stop_reason == "budget"`, and inference calls with its API keys fail with
`code == "budget_exceeded"` until the month ends or the budget is raised.

### Secrets

Secrets are environment variables every instance and job launched in an environment gets, such as `HF_TOKEN`. The SDK lists their names, never their values; a workspace owner or manager sets them in the [dashboard](https://runcrate.ai/dashboard/settings/secrets). A value passed for one launch (`env_vars`) wins over the secret of the same name.

```python
secrets = client.secrets.list()  # [Secret(key="HF_TOKEN", sensitive=False, updated_at=...)]
has_token = any(s.key == "HF_TOKEN" for s in secrets)
```

### SSH Keys

```python
client.ssh_keys.list()
client.ssh_keys.create(name="my-key", public_key="ssh-ed25519 AAAA...")
client.ssh_keys.delete("key-id")
```

### Storage

```python
client.storage.list()
client.storage.get("volume-id")
```

### Billing

```python
balance = client.billing.get_balance()
print(balance.credits_balance, balance.burn_usd_per_hour, balance.runway_hours)
client.billing.list_transactions(limit=10, offset=0)
client.billing.usage(from_date="2025-01-01", to_date="2025-01-31")
```

An agent or program can top up the balance from the workspace's saved card. The API key needs the billing permission, which a workspace owner or manager turns on (with daily and monthly caps) on the dashboard API keys page. Cards are only added on the dashboard.

```python
topup = client.billing.top_up(amount_usd=50)  # 20 to 10000
if topup.status == "succeeded":
    print(f"New balance: ${topup.balance_usd}")
elif topup.status == "requires_action":
    # Nothing is charged until a workspace owner or manager confirms it here.
    print(f"Confirm at {topup.confirm_url} before {topup.expires_at}")
elif topup.status == "declined":
    print(topup.reason, topup.message)

# Calling again with the same key never charges twice: it answers the top-up's current
# status, which is how a "processing" or "requires_action" top-up is polled.
topup = client.billing.top_up(amount_usd=50, idempotency_key=topup.idempotency_key)
```

Without `idempotency_key` the SDK makes one (a UUID) and returns it on the result. A reached cap, no saved card or a payment hold raise `InsufficientCreditsError` (`code` is `TOPUP_CAP_REACHED`, `NO_PAYMENT_METHOD` or `PAYMENT_HOLD`); a key without the billing permission raises `PermissionDeniedError`.

While the first request with a key is still being charged, the SDK waits and asks again for its result. Every error `top_up` raises carries the key it sent as `idempotency_key`, so after a timeout or a lost connection the same top-up can be sent again without charging twice:

```python
from runcrate import ConnectionError, TimeoutError

try:
    topup = client.billing.top_up(amount_usd=50)
except (TimeoutError, ConnectionError) as e:
    topup = client.billing.top_up(amount_usd=50, idempotency_key=e.idempotency_key)
```

```python
# Auto-recharge: when the balance falls below threshold_usd, top it up to target_usd.
client.billing.get_auto_recharge()
client.billing.set_auto_recharge(enabled=True, threshold_usd=20, target_usd=100)
client.billing.set_auto_recharge(enabled=False, threshold_usd=20, target_usd=100)  # off

for card in client.billing.list_payment_methods():
    print(card.brand, card.last4, card.exp_month, card.exp_year, card.default)
```

### Templates

```python
client.templates.list(search="cuda", category="ml", page_size=10)
```

## Error Handling

```python
from runcrate import Runcrate, NotFoundError, InsufficientCreditsError, RateLimitError

client = Runcrate(api_key="rc_live_...")

try:
    instance = client.instances.get("nonexistent")
except NotFoundError as e:
    print(f"Not found: {e.message}")
except InsufficientCreditsError as e:
    if e.code == "BUDGET_REACHED":
        print(f"Environment budget reached: {e.message}")
    else:
        print(f"Need more credits: {e.message}")
except RateLimitError as e:
    print(f"Rate limited: {e.message}")
```

## Pagination

```python
# Transactions support offset-based pagination
page = client.billing.list_transactions(limit=10, offset=0)
print(page.data)        # list of Transaction objects
print(page.has_more)    # True if more pages exist
print(page.total)       # total count

# Templates support page-based pagination
templates = client.templates.list(page=1, page_size=25)
```

## Requirements

- Python >= 3.9
- httpx >= 0.25.0
- pydantic >= 2.0
