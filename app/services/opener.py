"""A first message that is one word gets its own call.

Usually it is the keyword she was asked to comment under a reel, and the word is all there is: no
history to read and nothing about her to extract, so the main reader has nothing to do. But the word
still means something. STOP is not a welcome, "human" is a request for a person, "price?" is a
question, and AMH deserves an AMH opening rather than the same TTC question as every other word
(manual v4.1 §O).

So one small call, with its own prompt and Sonia's own examples (`prompts_simple/opener.md`),
decides which of four things the word is and, for an ordinary word, writes the reply. There is no
keyword list: a word nobody has seen before works the day the reel goes out. The brain acts on the
`action`; only `reply` sends anything the model wrote.
"""
from openai import AsyncOpenAI

from app.services.prompts import build_opener_prompt
from app.services.reader import _coerce

ACTIONS = ("stop", "human", "price", "reply")


async def read_opener(
    client: AsyncOpenAI,
    word: str,
    *,
    model: str,
    tuning: dict,
) -> tuple[dict, dict]:
    """Return ({"action", "reply"}, usage). Raises on anything it can't act on."""
    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_opener_prompt()},
            {"role": "user", "content": word},
        ],
        **tuning,
    )
    data = _coerce(response.choices[0].message.content or "")
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
    }
    action = data.get("action")
    reply = (data.get("reply") or "").strip()
    if action not in ACTIONS or (action == "reply" and not reply):
        raise ValueError(f"Opener returned nothing usable: {data!r}")
    return {"action": action, "reply": reply if action == "reply" else ""}, usage
