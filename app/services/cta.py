"""The word that started the conversation, and the one reply it gets.

Most conversations do not begin with a message. They begin with a comment on a reel: Sonia says
"comment AMH and I'll send it to you", ManyChat opens the DM, and the first thing in the transcript
is the single word she typed. "AMH". "BLOOD SUGAR". "READY".

That word is an opener and nothing else. It is not a question, it is not a fact about her, and it
is emphatically not a lead qualifying herself: "READY" means she watched a reel to the end, not
that she is ready to book, and "IVF" is a reel topic rather than a treatment she is having. Every
one of them arrives with the same amount of information about her, which is none.

So the reply is one fixed line from config, sent without calling a model at all. Sonia wrote it, it
welcomes her and asks the two discovery questions, and then it stops and waits. There is nothing
here for a writer to improve: a generated reply to a bare keyword either invents context it does
not have or answers the topic at length, and the second one is worse, because a wall of text about
AMH is the whole conversation spent before she has said a word about herself.

Matching is deliberately strict. Her whole message has to *be* a keyword, not contain one, because
"how do I lower my AMH" is a woman asking a question and belongs to the brain like any other.
"""
import re
import unicodedata

_STRIP = re.compile(r"[^a-z0-9 ]+")


def normalise(text: str) -> str:
    """Casefold, drop accents and punctuation, collapse the spaces.

    "AMH", "amh!", "Amh 🤍" and "  AMH  " are one keyword typed four ways, and a woman commenting on
    a reel from her phone produces all four. Accents go too, so a Spanish keyword matches whether or
    not she reached for the accented character.
    """
    decomposed = unicodedata.normalize("NFKD", text or "").casefold()
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_STRIP.sub(" ", without_accents).split())


def keywords(cfg: dict) -> set[str]:
    """The configured CTA words, normalised. One per line, and commas work too."""
    raw = (cfg.get("cta_keywords") or "").replace(",", "\n")
    return {word for word in (normalise(line) for line in raw.splitlines()) if word}


def is_opener(history: list[dict], cfg: dict) -> bool:
    """Whether this turn is nothing but CTA keywords on an untouched conversation.

    Two conditions, both necessary. Nothing has been said back to her yet, because the keyword is
    how a conversation starts and a woman typing "ready" on turn six is answering something. And
    every message she has sent is a keyword on its own: if she typed "AMH" and then "I'm 38 and my
    AMH is 0.4", she has started the conversation herself and the fixed line would talk over her.
    """
    if not history or any(m.get("role") == "assistant" for m in history):
        return False

    configured = keywords(cfg)
    if not configured:
        return False

    said = [m.get("content", "") for m in history if m.get("role") == "user"]
    normalised = [normalise(text) for text in said]
    return bool(normalised) and all(text in configured for text in normalised)
