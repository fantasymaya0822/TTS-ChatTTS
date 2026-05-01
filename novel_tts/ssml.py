from __future__ import annotations

from html import escape


def build_ssml(*, text: str, voice: str, locale: str, rate: str) -> str:
    escaped = escape(text, quote=False)
    return (
        f'<speak version="1.0" xml:lang="{escape(locale)}" '
        'xmlns="http://www.w3.org/2001/10/synthesis">\n'
        f'  <voice name="{escape(voice)}">\n'
        f'    <prosody rate="{escape(rate)}">\n'
        f"{escaped}\n"
        "    </prosody>\n"
        "  </voice>\n"
        "</speak>\n"
    )

