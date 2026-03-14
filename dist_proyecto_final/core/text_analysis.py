# core/text_analysis.py
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from statistics import mean
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü]+", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.!?;:])\s+")
VOWELS = "aeiouáéíóúü"

SPANISH_STOPWORDS = {
    "a", "al", "algo", "alguna", "algunas", "alguno", "algunos", "ante", "como", "con", "contra",
    "cual", "cuales", "de", "del", "desde", "donde", "dos", "el", "ella", "ellas", "ellos", "en",
    "entre", "era", "erais", "eran", "eras", "eres", "es", "esa", "esas", "ese", "eso", "esos",
    "esta", "estaba", "estaban", "estado", "estais", "estamos", "estan", "estar", "este", "esto",
    "estos", "fue", "fueron", "ha", "han", "hasta", "hay", "la", "las", "le", "les", "lo", "los",
    "mas", "me", "mi", "mis", "mucho", "muy", "ni", "no", "nos", "nuestra", "nuestro", "o", "os",
    "para", "pero", "por", "que", "quien", "se", "ser", "si", "sin", "sobre", "su", "sus", "te",
    "tenia", "ti", "tu", "tus", "un", "una", "uno", "unos", "y", "ya",
}

VERB_SUFFIXES = (
    "ar", "er", "ir", "ado", "ido", "ando", "iendo", "aré", "eré", "iré", "aba", "aban", "ían", "ia",
    "aste", "iste", "aron", "ieron", "amos", "emos", "imos", "áis", "éis", "ís", "an", "en", "ó", "ió",
)
ADJECTIVE_SUFFIXES = (
    "al", "able", "ible", "oso", "osa", "osos", "osas", "ivo", "iva", "ivos", "ivas", "ante", "ente",
)
NOUN_SUFFIXES = (
    "ción", "sión", "dad", "tad", "umbre", "ez", "eza", "ismo", "ista", "or", "ora", "ores", "oras",
)


@dataclass(slots=True)
class TextEvent:
    token: str
    metric: int
    midi_value: int
    duration_ms: int
    category: str
    work_type: str
    sentence_index: int
    token_index: int
    lexical_density: float
    cadence_strength: int
    sentence_length: int
    pause_after_ms: int = 0
    note_hint: int = 60
    debug: dict[str, Any] | None = None


class TextAnalyzer:
    def tokenize(self, content: str) -> list[str]:
        return TOKEN_RE.findall(content)

    def normalize_text(self, content: str) -> str:
        normalized = unicodedata.normalize("NFKC", content)
        return normalized.replace("\r\n", "\n").replace("\r", "\n")

    def strip_accents(self, value: str) -> str:
        return "".join(
            ch for ch in unicodedata.normalize("NFD", value) if unicodedata.category(ch) != "Mn"
        )

    def count_syllables(self, token: str) -> int:
        base = self.strip_accents(token.lower())
        groups = re.findall(r"[aeiou]+", base)
        return max(1, len(groups))

    def classify_token(self, token: str) -> str:
        lower = token.lower()
        accentless = self.strip_accents(lower)
        if lower in SPANISH_STOPWORDS:
            return "func"
        if accentless.endswith(VERB_SUFFIXES):
            return "verb"
        if accentless.endswith(ADJECTIVE_SUFFIXES):
            return "adj"
        if accentless.endswith(NOUN_SUFFIXES) or token[:1].isupper():
            return "noun"
        if accentless.endswith("mente"):
            return "adv"
        if len(token) <= 3:
            return "func"
        return "noun"

    def detect_work_type(self, content: str) -> str:
        lines = [line.strip() for line in self.normalize_text(content).splitlines() if line.strip()]
        if len(lines) >= 4:
            short_or_medium = sum(1 for line in lines if 3 <= len(line.split()) <= 16)
            ratio = short_or_medium / max(1, len(lines))
            if ratio >= 0.6:
                return "verse"
        return "prose"

    def split_units(self, content: str, work_type: str) -> list[str]:
        clean = self.normalize_text(content)
        if work_type == "verse":
            units = [line.strip() for line in clean.splitlines() if line.strip()]
            return units or [clean]
        pieces = [piece.strip() for piece in SENTENCE_SPLIT_RE.split(clean) if piece.strip()]
        return pieces or [clean]

    def metric_for_token(
        self,
        token: str,
        category: str,
        lexical_density: float,
        sentence_length: int,
        cadence_strength: int,
        sentence_index: int,
    ) -> int:
        syllables = self.count_syllables(token)
        ascii_weight = sum(ord(ch) for ch in token)
        category_weight = {"verb": 42, "noun": 30, "adj": 24, "adv": 18, "func": 8}.get(category, 12)
        density_bonus = int(lexical_density * 40)
        cadence_bonus = cadence_strength * 6
        flow_bonus = min(sentence_length * 2, 40)
        position_bonus = (sentence_index % 8) * 4
        return ascii_weight + syllables * 22 + category_weight + density_bonus + cadence_bonus + flow_bonus + position_bonus

    def normalize(self, value: int, min_value: int, max_value: int) -> int:
        if min_value == max_value:
            return 64
        scaled = ((value - min_value) / (max_value - min_value)) * 127
        curved = int(round(math.sqrt(max(0.0, scaled / 127)) * 127))
        return max(0, min(127, curved))

    def analyze_structure(self, content: str) -> dict[str, Any]:
        work_type = self.detect_work_type(content)
        units = self.split_units(content, work_type)
        unit_tokens = [self.tokenize(unit) for unit in units]
        unit_lengths = [len(tokens) for tokens in unit_tokens if tokens]
        all_tokens = [token for tokens in unit_tokens for token in tokens]
        categories = [self.classify_token(token) for token in all_tokens]
        lexical_tokens = [token.lower() for token, cat in zip(all_tokens, categories) if cat not in {"func"}]
        lexical_density = (len(lexical_tokens) / max(1, len(all_tokens))) if all_tokens else 0.0
        diversity = len(set(lexical_tokens)) / max(1, len(lexical_tokens)) if lexical_tokens else 0.0
        return {
            "work_type": work_type,
            "units": units,
            "unit_lengths": unit_lengths,
            "avg_unit_length": round(mean(unit_lengths), 2) if unit_lengths else 0,
            "lexical_density": round(lexical_density, 4),
            "lexical_diversity": round(diversity, 4),
            "token_count": len(all_tokens),
            "verb_ratio": round(sum(1 for c in categories if c == "verb") / max(1, len(all_tokens)), 4),
            "noun_ratio": round(sum(1 for c in categories if c == "noun") / max(1, len(all_tokens)), 4),
            "adjective_ratio": round(sum(1 for c in categories if c == "adj") / max(1, len(all_tokens)), 4),
            "cadence": (
                "regular con cesuras y pulsos estables"
                if work_type == "verse"
                else "fluida e irregular con frases narrativas"
            ),
        }

    def build_events(self, content: str, bpm: int) -> list[TextEvent]:
        work_type = self.detect_work_type(content)
        units = self.split_units(content, work_type)
        if not units:
            return []

        beat_ms = max(120, int(60000 / max(1, bpm)))
        lexical_density_global = self.analyze_structure(content)["lexical_density"]
        raw_rows: list[dict[str, Any]] = []

        for sentence_index, unit in enumerate(units, start=1):
            tokens = self.tokenize(unit)
            if not tokens:
                continue
            unit_categories = [self.classify_token(token) for token in tokens]
            lexical_count = sum(1 for cat in unit_categories if cat != "func")
            lexical_density = lexical_count / max(1, len(tokens))
            sentence_length = len(tokens)
            cadence_strength = max(1, min(10, round((sentence_length / 3) if work_type == "verse" else (sentence_length / 5))))

            for token_index, (token, category) in enumerate(zip(tokens, unit_categories), start=1):
                metric = self.metric_for_token(
                    token=token,
                    category=category,
                    lexical_density=lexical_density,
                    sentence_length=sentence_length,
                    cadence_strength=cadence_strength,
                    sentence_index=sentence_index,
                )
                syllables = self.count_syllables(token)
                base_duration = beat_ms
                if work_type == "verse":
                    duration_ms = base_duration + syllables * 45 + (25 if token_index % 2 == 0 else 0)
                else:
                    duration_ms = base_duration + len(token) * 18 + min(sentence_length * 5, 160)
                pause_after_ms = 0
                if work_type == "verse" and token_index == max(1, len(tokens) // 2):
                    pause_after_ms = max(60, beat_ms // 5)
                if token_index == len(tokens):
                    pause_after_ms += max(80, beat_ms // 4) if work_type == "verse" else max(50, beat_ms // 6)
                raw_rows.append(
                    {
                        "token": token,
                        "metric": metric,
                        "category": category,
                        "sentence_index": sentence_index,
                        "token_index": token_index,
                        "lexical_density": round((lexical_density + lexical_density_global) / 2, 4),
                        "cadence_strength": cadence_strength,
                        "sentence_length": sentence_length,
                        "duration_ms": duration_ms,
                        "pause_after_ms": pause_after_ms,
                        "work_type": work_type,
                        "syllables": syllables,
                    }
                )

        if not raw_rows:
            return []

        metrics = [row["metric"] for row in raw_rows]
        min_value = min(metrics)
        max_value = max(metrics)
        events: list[TextEvent] = []
        for row in raw_rows:
            midi_value = self.normalize(row["metric"], min_value, max_value)
            note_hint = 48 + ((row["sentence_index"] * 7 + row["syllables"] * 3 + row["token_index"]) % 36)
            events.append(
                TextEvent(
                    token=row["token"],
                    metric=row["metric"],
                    midi_value=midi_value,
                    duration_ms=row["duration_ms"],
                    category=row["category"],
                    work_type=row["work_type"],
                    sentence_index=row["sentence_index"],
                    token_index=row["token_index"],
                    lexical_density=row["lexical_density"],
                    cadence_strength=row["cadence_strength"],
                    sentence_length=row["sentence_length"],
                    pause_after_ms=row["pause_after_ms"],
                    note_hint=note_hint,
                    debug={"syllables": row["syllables"]},
                )
            )
        return events
