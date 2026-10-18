"""English lyrics as syllables with stress, for fitting words to a melody (docs/melody-writing.md).

How many syllables a word has comes from the CMU pronouncing dictionary (the
`pronouncing` package); where to split the spelling comes from simple English
rules (vowel groups, a silent final e, V-CV and VC-CV, digraphs kept
together). The split only decides how the word is printed under the notes
("fea-thers"), so a rare odd split costs nothing but looks; the count and the
stress are what matter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pronouncing

VOWELS = set("aeiouy")
KEEP_WITH_NEXT = ("th", "sh", "ch", "ph", "wh", "qu")
KEEP_WITH_PREVIOUS = ("ck", "gh")
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "of", "to", "in", "on", "at", "by", "for", "with", "from",
    "as", "is", "it", "its", "it's", "that", "this", "be", "was", "were", "are", "am", "i", "i'm", "you",
    "he", "she", "we", "they", "me", "my", "your", "his", "her", "our", "their", "so", "than", "then", "if",
    "when", "can", "do", "does", "has", "had", "have", "will", "would",
}
ONSETS = {"bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "sc", "sk", "sl", "sm", "sn", "sp",
          "st", "sw", "tr", "tw", "th", "sh", "ch", "ph", "wh", "qu", "wr"}
STOP_LIQUID = {"bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr"}
# Spellings the rules split wrongly, fixed by hand.
EXCEPTIONS = {
    "every": ["ev", "ery"], "heaven": ["hea", "ven"], "being": ["be", "ing"], "fire": ["fire"],
    "hour": ["hour"], "our": ["our"], "alleluia": ["al", "le", "lu", "ia"], "hallelujah": ["hal", "le", "lu", "jah"],
    "evening": ["eve", "ning"], "different": ["dif", "ferent"], "family": ["fam", "ily"], "maybe": ["may", "be"],
    "something": ["some", "thing"], "nothing": ["noth", "ing"], "someone": ["some", "one"],
    "everything": ["ev", "ery", "thing"], "everyone": ["ev", "ery", "one"], "anyone": ["an", "y", "one"],
    "lonely": ["lone", "ly"], "lovely": ["love", "ly"], "loneliness": ["lone", "li", "ness"],
    "without": ["with", "out"], "within": ["with", "in"], "into": ["in", "to"], "upon": ["up", "on"],
    "today": ["to", "day"], "tonight": ["to", "night"], "myself": ["my", "self"], "yourself": ["your", "self"],
    "forever": ["for", "ev", "er"], "never": ["nev", "er"], "ever": ["ev", "er"], "over": ["o", "ver"],
}


@dataclass
class Syllable:
    text: str            # as printed, punctuation on the last syllable of a word
    weight: float        # how strongly it's stressed: 2 primary, 1 secondary, 0 none; 1.5 / 0.3 for one-syllable words
    word: int            # index of its word in the line
    word_end: bool
    line_end: bool = False
    line_start: bool = False


@dataclass
class Line:
    text: str
    syllables: list[Syllable] = field(default_factory=list)


@dataclass
class Section:
    name: str            # verse, chorus, bridge, prechorus, intro, outro, ...
    lines: list[Line] = field(default_factory=list)


def clean(word: str) -> str:
    return re.sub(r"[^a-z']", "", word.lower()).strip("'")


def dictionary_stresses(word: str) -> list[int] | None:
    """Stress digits per syllable; of the dictionary's pronunciations, the one with the fewest
    syllables, since singers elide ("ev'ry", "fire" in one)."""
    phones = pronouncing.phones_for_word(clean(word))
    if not phones:
        return None
    return min(([int(d) for d in pronouncing.stresses(p)] for p in phones), key=len)


def vowel_groups(w: str) -> list[tuple[int, int]]:
    """(start, end) of each run of vowels; a y at the start of a word is a consonant."""
    groups, i = [], 0
    while i < len(w):
        consonant = (w[i] == "y" and (i == 0 or (i + 1 < len(w) and w[i + 1] in VOWELS))) or \
            (w[i] == "u" and i > 0 and w[i - 1] == "q")
        if w[i] in VOWELS and not consonant:
            j = i
            while j < len(w) and w[j] in VOWELS and not (w[j] == "y" and j + 1 < len(w) and w[j + 1] in VOWELS):
                j += 1
            j = max(j, i + 1)                 # always move on
            groups.append((i, j))
            i = j
        else:
            i += 1
    # A final silent e ("hope", "soul" has none) isn't a syllable, except "-le" after a consonant ("table").
    if len(groups) > 1 and w.endswith("e") and groups[-1] == (len(w) - 1, len(w)):
        if not (w.endswith("le") and len(w) > 2 and w[-3] not in VOWELS):
            groups.pop()
    # "-es" and "-ed" endings that aren't syllables ("perches" is, "loves" isn't): let the dictionary decide.
    return groups


SUFFIXES = ("est", "ing")


def _suffix(w: str) -> str:
    return next((x for x in SUFFIXES if w.endswith(x) and len(w) > len(x) + 2), "")


def split_points(w: str, groups: list[tuple[int, int]]) -> list[int]:
    """Where to cut between consecutive vowel groups."""
    cuts = []
    for (s1, e1), (s2, _) in zip(groups, groups[1:]):
        cluster = w[e1:s2]
        if not cluster:
            cuts.append(e1)                       # vowel meets vowel: "li-on"
        elif _suffix(w) and s2 == len(w) - len(_suffix(w)) and len(cluster) <= 2 and \
                not (len(cluster) == 2 and cluster[0] == cluster[1]):
            cuts.append(s2)                       # a suffix keeps its own syllable: "sweet-est", "morn-ing"
                                                  # (but a doubled consonant splits: "run-ning")
        elif cluster in ("w", "x"):
            cuts.append(e1 + 1)                   # "flow-er", "ex-it"
        elif len(cluster) == 1:
            cuts.append(e1)                       # V-CV: "o-pen"
        elif s2 == len(w) - 1 and w.endswith("le") and cluster.endswith("l"):
            cuts.append(s2 - 2)                   # consonant + le: "ta-ble", "lit-tle"
        elif cluster.endswith("tch"):
            cuts.append(s2)                       # "kitch-en", "watch-ing"
        elif len(cluster) >= 3:
            # VCCCV: the next syllable takes the last two consonants if they can start a word
            # ("chil-dren", "ex-treme"), else just the last one ("dark-ness", "light-ning").
            cuts.append(s2 - 2 if cluster[-2:] in ONSETS else s2 - 1)
        elif cluster in KEEP_WITH_PREVIOUS:
            cuts.append(e1 + 2)                   # "pick-et", "laugh-ing"
        elif cluster in KEEP_WITH_NEXT:
            cuts.append(s2 - 2)                   # "fea-thers", "per-ches"
        elif cluster in STOP_LIQUID:
            cuts.append(e1)                       # "a-cross", "se-cret" (but "sis-ter", "win-ter")
        else:
            cuts.append(e1 + 1)                   # VC-CV: "win-dow"
    return cuts


def split_word(word: str, count: int) -> list[str]:
    """`word` (as written, with punctuation) cut into `count` syllables."""
    letters = clean(word)
    if letters in EXCEPTIONS and len(EXCEPTIONS[letters]) == count and "".join(EXCEPTIONS[letters]) == letters:
        parts = EXCEPTIONS[letters]
    elif count <= 1 or len(letters) < 2:
        return [word]
    else:
        groups = vowel_groups(letters)
        # A silent e in "-ed" or "-es" ("believed", "promised") isn't a syllable.
        if len(groups) > count and re.search(r"e[ds]$", letters) and groups[-1] == (len(letters) - 2, len(letters) - 1):
            groups.pop()
        # Too many groups: merge the closest neighbours; too few: split long vowel runs.
        while len(groups) > count and len(groups) > 1:
            gaps = [groups[k + 1][0] - groups[k][1] for k in range(len(groups) - 1)]
            k = gaps.index(min(gaps))
            groups[k:k + 2] = [(groups[k][0], groups[k + 1][1])]
        while len(groups) < count:
            longest = max(range(len(groups)), key=lambda k: groups[k][1] - groups[k][0])
            s, e = groups[longest]
            if e - s < 2:
                break
            groups[longest:longest + 1] = [(s, s + 1), (s + 1, e)]
        if len(groups) != count:
            return [word] if count == 1 else _even_split(word, count)
        cuts = split_points(letters, groups)
        parts, last = [], 0
        for c in cuts:
            parts.append(letters[last:c])
            last = c
        parts.append(letters[last:])
    return _restore(word, parts)


def _even_split(word: str, count: int) -> list[str]:
    letters = clean(word)
    size = max(1, len(letters) // count)
    parts = [letters[k * size:(k + 1) * size] for k in range(count - 1)] + [letters[(count - 1) * size:]]
    return _restore(word, parts)


def _restore(word: str, parts: list[str]) -> list[str]:
    """Put the original letters (case, apostrophes) and punctuation back onto the parts."""
    out, pos = [], 0
    letters = [i for i, ch in enumerate(word) if ch.isalpha() or ch == "'"]
    lead = word[:letters[0]] if letters else ""
    for k, part in enumerate(parts):
        take = len(part)
        idx = letters[pos:pos + take]
        pos += take
        text = "".join(word[i] for i in idx)
        out.append(text)
    tail_start = letters[-1] + 1 if letters else 0
    out[0] = lead + out[0]
    out[-1] = out[-1] + word[tail_start:]
    return out


def syllabify_word(word: str) -> list[tuple[str, float]]:
    """[(syllable text, stress weight)] for one word."""
    letters = clean(word)
    stresses = dictionary_stresses(word)
    if stresses is None:
        count = max(1, len(vowel_groups(letters)))
        stresses = [1] + [0] * (count - 1)
    parts = split_word(word, len(stresses))
    if len(parts) != len(stresses):
        stresses = [1] + [0] * (len(parts) - 1)
    if len(parts) == 1:
        return [(parts[0], 0.3 if letters in FUNCTION_WORDS else 1.5)]
    weights = {1: 2.0, 2: 1.0, 0: 0.0}
    return [(p, weights[s]) for p, s in zip(parts, stresses)]


def syllabify_line(text: str) -> Line:
    line = Line(text.strip())
    words = [w for w in re.split(r"\s+", text.strip()) if re.search(r"[A-Za-z]", w)]
    for wi, w in enumerate(words):
        sylls = syllabify_word(w)
        for k, (s, weight) in enumerate(sylls):
            line.syllables.append(Syllable(s, weight, wi, word_end=k == len(sylls) - 1))
    if line.syllables:
        line.syllables[0].line_start = True
        line.syllables[-1].line_end = True
    return line


SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def parse_lyrics(text: str) -> list[Section]:
    """Lyrics with [Verse]/[Chorus]/... tags into sections of lines (untagged text is a verse)."""
    from .lora import section_tag
    sections: list[Section] = []
    for raw in text.splitlines():
        m = SECTION.match(raw)
        if m:
            sections.append(Section(section_tag(m.group(1)) or "verse"))
            continue
        line = " ".join(re.sub(r"\[[^\]]*\]", " ", raw).split())
        if not line:
            continue
        if not sections:
            sections.append(Section("verse"))
        sections[-1].lines.append(syllabify_line(line))
    return [s for s in sections if s.lines]


def all_syllables(sections: list[Section]) -> list[Syllable]:
    return [s for sec in sections for line in sec.lines for s in line.syllables]
