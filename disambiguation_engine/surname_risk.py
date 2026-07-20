"""Small deployment-safe surname risk guard for initial-only matching.

The list is deliberately conservative: a match only disables a permissive
initial-signature repair.  It never forces two records to merge.  Romanized
Chinese entries mirror the validated frequency list from Project One; common
Japanese and Korean entries mirror its non-Chinese exclusion list.  Any name
written with CJK characters is also treated as high risk.
"""

from __future__ import annotations

import unicodedata


HIGH_RISK_EAST_ASIAN_ROMANIZED_SURNAMES = frozenset({
    # Chinese frequency list.
    "wang", "li", "zhang", "liu", "chen", "yang", "huang", "zhao",
    "wu", "zhou", "xu", "sun", "ma", "zhu", "hu", "guo", "he",
    "gao", "lin", "luo", "zheng", "liang", "xie", "song", "tang",
    "deng", "han", "feng", "cao", "peng", "zeng", "xiao", "tian",
    "dong", "pan", "yuan", "cai", "jiang", "yu", "du", "ye",
    "cheng", "wei", "su", "lu", "ding", "ren", "shen", "yao",
    "cui", "tan", "liao", "fan", "shi", "jin", "jia", "xia",
    "fu", "fang", "zou", "xiong", "bai", "meng", "qin", "qiu",
    "hou", "yin", "xue", "yan", "duan", "lei", "long", "tao",
    "gu", "mao", "hao", "gong", "shao", "wan", "qian", "dai",
    "mo", "kong", "xiang", "chang", "ouyang", "sima", "shangguan",
    "zhuge",
    # Common Japanese surnames.
    "sato", "saito", "suzuki", "takahashi", "tanaka", "watanabe",
    "ito", "yamamoto", "nakamura", "kobayashi", "kato", "yoshida",
    "yamada", "sasaski", "sasaki", "yamaguchi", "matsumoto", "inoue",
    "kimura", "hayashi", "shimizu", "yamazaki", "mori", "abe", "ikeda",
    "hashimoto", "ishikawa", "maeda", "fujita", "ogawa", "goto",
    "okada", "hasegawa", "murakami", "kondo", "ishii", "sakamoto",
    "endo", "aoki", "fujii", "nishimura", "fukuda", "ota", "miura",
    "fujiwara", "okamoto", "matsuda", "nakagawa", "nakano", "harada",
    "ono", "tamura", "takeuchi", "kaneko", "wada", "nakajima",
    # Common Korean surnames and romanization variants.
    "kim", "lee", "park", "choi", "jung", "jeong", "cho", "jo",
    "yoon", "yun", "jang", "lim", "im", "shin", "sin", "kwon",
    "hwang", "ahn", "an", "song", "ryu", "yoo", "yu", "hong",
    "jeon", "jun", "seo", "moon", "mun", "kang", "baek", "paik",
    "nam", "oh", "ha", "son", "chung",
})

COMMON_WESTERN_SURNAMES = frozenset({
    # UK government 2026 top-five licence-holder surnames; Khan is also rank
    # 427 in the U.S. Census Bureau 2010 surname table.
    "khan", "ali", "ahmed", "hussain", "singh",
    "smith", "johnson", "williams", "brown", "jones", "miller", "davis",
    "garcia", "rodriguez", "wilson", "martinez", "anderson", "taylor",
    "thomas", "hernandez", "moore", "martin", "jackson", "thompson",
    "white", "lopez", "lee", "gonzalez", "harris", "clark", "lewis",
    "robinson", "walker", "perez", "hall", "young", "allen", "sanchez",
    "wright", "king", "scott", "green", "baker", "adams", "nelson",
    "hill", "ramirez", "campbell", "mitchell", "roberts", "carter",
    "phillips", "evans", "turner", "torres", "parker", "collins",
    "edwards", "stewart", "flores", "morris", "nguyen", "murphy",
    "rivera", "cook", "rogers", "mueller", "muller", "schmidt",
    "schneider", "fischer", "weber", "meyer", "wagner", "becker",
    "schulz", "hoffmann", "koch", "richter", "klein", "wolf",
    "schroeder", "neumann", "schwartz", "bernard", "dubois", "robert",
    "richard", "petit", "durand", "leroy", "moreau", "simon", "laurent",
    "lefebvre", "michel", "david", "bertrand", "roux", "vincent",
    "fournier", "morel", "rossi", "russo", "ferrari", "esposito",
    "bianchi", "romano", "colombo", "ricci", "marino", "greco", "bruno",
    "gallo", "conti", "deluca", "fernandez", "gomez", "ruiz", "jimenez",
    "diaz", "ivanov", "smirnov", "kuznetsov", "popov", "vasiliev",
    "petrov", "sokolov", "mikhailov", "fedorov", "morozov", "volkov",
    "alekseev", "lebedev", "kowalski", "wisniewski", "dabrowski",
    "lewandowski", "wojcik", "kaminski", "kowalczyk", "zielinski",
    "szymanski", "wozniak", "korhonen", "virtanen", "makinen", "nieminen",
    "makela", "hamalainen", "laine", "heikkinen", "koskinen", "jarvinen",
    "jong", "jansen", "vries", "berg", "dijk", "bakker", "janssen",
    "visser", "smit", "meijer", "boer", "mulder", "groot", "bos", "vos",
    "peters", "savolainen", "desrichard", "friedemann", "aberson",
    "lukyanenko", "rutherford", "verhoeven", "santtila", "mignard",
    "adjodah", "tonello", "congedo", "cillo", "vatakis", "marttila",
})


def _contains_cjk(value: str) -> bool:
    for char in value:
        codepoint = ord(char)
        if (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0x3040 <= codepoint <= 0x30FF
            or 0xAC00 <= codepoint <= 0xD7AF
        ):
            return True
    return False


def is_high_risk_surname(value: str) -> bool:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    if not text:
        return True
    if _contains_cjk(text):
        return True
    decomposed = unicodedata.normalize("NFKD", text)
    key = "".join(
        char for char in decomposed
        if char.isalpha() and not unicodedata.combining(char)
    )
    return (
        key in HIGH_RISK_EAST_ASIAN_ROMANIZED_SURNAMES
        or key in COMMON_WESTERN_SURNAMES
    )


__all__ = [
    "COMMON_WESTERN_SURNAMES",
    "HIGH_RISK_EAST_ASIAN_ROMANIZED_SURNAMES",
    "is_high_risk_surname",
]
