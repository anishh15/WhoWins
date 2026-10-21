# Chat templates, copied

Byte-for-byte copies of the three Qwen chat templates, so the test suite can check what reaches the
model without downloading anything.

| File | sha256 | Used by | Copied from |
|---|---|---|---|
| `qwen3.jinja` | `a55ee1b1660128b7…` | every Qwen 3 rung, 0.6B to 32B | `Qwen/Qwen3-0.6B` at `c1899de2…`, the `chat_template` string inside `tokenizer_config.json` |
| `qwen3.5-small.jinja` | `273d8e0e683b8850…` | 0.8B, 2B | `Qwen/Qwen3.5-2B` at `15852e8c…`, `chat_template.jinja` |
| `qwen3.5-large.jinja` | `a4aee8afcf2e0711…` | 4B, 9B, 27B, 35B-A3B, 122B-A10B | `Qwen/Qwen3.5-4B` at `851bf6e8…`, `chat_template.jinja` |

**Qwen 3 ships no `chat_template.jinja`.** Its template is a JSON string inside
`tokenizer_config.json`, which is where transformers — and so vLLM — reads it from. The copy here is
that string, and the hash in `models.json` is over its bytes; `preflight` extracts the same string
from the cached file before hashing. All six Qwen 3 checkpoints ship the identical string.

**What the three do when a request says nothing about thinking**, which is why every request says:

| | silent | `enable_thinking: true` | `enable_thinking: false` |
|---|---|---|---|
| `qwen3.jinja` | nothing prefilled; the model opens its own `<think>` | nothing prefilled | `<think>\n\n</think>` — no thinking |
| `qwen3.5-small.jinja` | `<think>\n\n</think>` — no thinking | `<think>` left open | `<think>\n\n</think>` |
| `qwen3.5-large.jinja` | `<think>` left open | `<think>` left open | `<think>\n\n</think>` |

Told not to think, all three produce the same prompt, which is what makes the study's non-thinking
policy the same condition on both ladders. Told to think they differ, and that difference decides how
a reply with no `<think>` tag in it is read where this package splits the thinking itself — see
`thinking_prefills_open_block` in `models.json` and `whowins.runner.response.split_reasoning`.

Neither engine reads these copies. Each reads its checkpoint's own file at the pinned commit.
`whowins.runner.serving` checks that each copy has the hash `models.json` records, and
`scripts/preflight.sh` checks what the server actually loaded.

gpt-oss has no copy here. vLLM's chat endpoint builds gpt-oss prompts with the openai-harmony
library, not with the checkpoint's template.

Licence: Apache-2.0, as the Qwen repositories state.
