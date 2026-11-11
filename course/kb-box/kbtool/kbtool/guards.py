"""Filters for untrusted content (SPEC §8 S2, S4).

S2 — secrets: by file name and by content (API keys, tokens, private keys, high-entropy strings
next to key|token|secret|password). Anything found reaches neither the base nor the model.

S4 — injections: a document that addresses the reading model with commands ("ignore previous
instructions…", "print the contents of ~/.ssh"; Russian variants too) is excluded whole by default
with reason ``injection-like`` [agent, decision 2026-11-06: T4 requires such documents to stay out
of units]. This is not the only defence: model output is accepted only within the contract and is
checked by code. The user may include a file explicitly, by path (``include_forced``).
"""
from __future__ import annotations

import fnmatch
import math
import re

SECRET_NAME_PATTERNS = (".env", ".env.*", "*.env", "*.pem", "*.key", "id_rsa*", "id_dsa*", "id_ecdsa*",
                        "id_ed25519*", "credentials*", "secrets*", "secret.*", "*.p12", "*.pfx", "*.kdbx",
                        "*.keystore", "*.jks", ".netrc", ".pgpass", "*.ovpn")

_SECRET_CONTENT = [
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("openai-key", re.compile(r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_\-]{20,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}")),
]
_ASSIGN = re.compile(r"(?i)\b[\w.-]*(?:api[_-]?key|token|secret|passw(?:or)?d|pwd|auth)[\w.-]*\b\s*[:=]\s*"
                     r"[\"']?([A-Za-z0-9+/=_\-.]{32,})")

_INJECTION = [
    re.compile(r"(?i)\b(?:ignore|disregard|forget)\b[^.\n]{0,40}\b(?:previous|prior|above|all|earlier)\b"
               r"[^.\n]{0,20}\b(?:instructions?|prompts?|rules|directions)"),
    re.compile(r"(?i)\b(?:игнорируй|игнорировать|забудь|отмени|не\s+выполняй)\b[^.\n]{0,40}"
               r"(?:предыдущ|прежн|все|вышеизложен|системн)[^.\n]{0,30}(?:указани|инструкци|правил|промпт)"),
    re.compile(r"(?i)\byou are now\b|\bnew system prompt\b|\bsystem prompt:|<\s*/?\s*system\s*>"),
    re.compile(r"(?i)\b(?:выведи|покажи|отправь|прочитай|print|cat|show|send|read|exfiltrate)\b[^\n]{0,40}"
               r"(?:~/\.ssh|\.ssh/|id_rsa|~/\.aws|\.env\b|/etc/passwd|keychain)"),
]


def secret_like_name(rel_path: str) -> bool:
    name = rel_path.rsplit("/", 1)[-1].lower()
    return any(fnmatch.fnmatch(name, pat) for pat in SECRET_NAME_PATTERNS)


def _entropy(s: str) -> float:
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def secret_kind(text: str) -> str | None:
    """The kind of secret found (without the value itself), or None."""
    for kind, rx in _SECRET_CONTENT:
        if rx.search(text):
            return kind
    for m in _ASSIGN.finditer(text):
        val = m.group(1)
        if _entropy(val) >= 3.5 and not val.isalpha():
            return "high-entropy-assignment"
    return None


def injection_kind(text: str) -> str | None:
    for n, rx in enumerate(_INJECTION, 1):
        if rx.search(text):
            return f"pattern-{n}"
    return None


def unsafe_markup_field(value: str) -> str | None:
    """A markup field returned by the model must not carry a secret, a path to keys or a command."""
    if secret_kind(value):
        return "secret-like"
    if injection_kind(value):
        return "injection-like"
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value):
        return "control-characters"
    return None
