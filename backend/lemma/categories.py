"""Map fine-grained Portuguese product names to generic, visually recognisable categories.

Compliance is judged at this level (banana vs orange), not variety (Fuji vs Gala),
and packaged products (e.g. "EMB. 3KG", "500 G") get their own category because
they look different from the loose product.
"""
import re
import unicodedata

# Ordered: first rule whose words all appear in the name wins (put specific rules first).
RULES: list[tuple[str, str]] = [
    ("BATATA DOCE", "sweet potatoes"),
    ("BATATA", "potatoes"),
    ("CEBOLINHA", "chives"),
    ("CEBOLA ROXA", "red onions"),
    ("CEBOLA", "onions"),
    ("COUVE BROCOLO", "broccoli"),
    ("COUVE FLOR", "cauliflowers"),
    ("COUVE ROXA", "red cabbages"),
    ("COUVE PORTUGUESA", "collard greens"),
    ("COUVE", "white cabbages"),
    ("MELANCIA", "watermelons"),
    ("MELOA", "melons"),
    ("MELAO", "melons"),
    ("MAMAO", "papayas"),
    ("PAPAIA", "papayas"),
    ("MARACUJA", "passion fruits"),
    ("GRANADILHA", "granadillas"),
    ("PITAYA AMARELA", "yellow dragon fruits"),
    ("PITAYA", "red dragon fruits"),
    ("MACA GRANNY", "green apples"),
    ("MACA GOLDEN", "yellow apples"),
    ("MACA REINETA", "russet apples"),
    ("MACA", "red apples"),
    ("PERA", "pears"),
    ("PESSEGO", "peaches"),
    ("NECTARINA", "nectarines"),
    ("ALPERCE", "apricots"),
    ("CEREJA", "cherries"),
    ("MORANGO", "strawberries"),
    ("UVA RED", "red grapes"),
    ("UVA", "green grapes"),
    ("KIWI GOLD", "golden kiwis"),
    ("KIWI", "kiwis"),
    ("LIMAO", "lemons"),
    ("LIMA", "limes"),
    ("CLEMENTINA", "clementines"),
    ("LARANJA", "oranges"),
    ("MANGA", "mangoes"),
    ("GOIABA", "guavas"),
    ("CHUCHU", "chayotes"),
    ("CURGETE", "zucchinis"),
    ("PEPINO", "cucumbers"),
    ("BERINGELA", "eggplants"),
    ("PIMENTO VERDE", "green bell peppers"),
    ("PIMENTO VERMELHO", "red bell peppers"),
    ("FEIJAO VERDE", "green beans"),
    ("GENGIBRE", "ginger"),
    ("ALFACE", "lettuce"),
    ("ALHO", "garlic"),
    ("ABACATE", "avocados"),
    ("ABACAXI", "pineapples"),
    ("ABOBORA", "pumpkins"),
    ("TOMATE CHERRY", "cherry tomatoes"),
    ("TOMATE MINI", "cherry tomatoes"),
    ("TOMATE CACHO", "vine tomatoes"),
    ("TOMATE CORACAO", "beefsteak tomatoes"),
    ("TOMATE", "tomatoes"),
    ("BANANA", "bananas"),
]

PACKAGED_SUFFIX = " (packaged)"

# Product families whose loose varieties (Fuji vs Gala...) the variety model tries to tell apart.
FAMILY_RULES: list[tuple[str, str]] = [
    ("MACA", "apples"),
    ("BANANA", "bananas"),
    ("PERA", "pears"),
    ("MELAO", "melons"),
    ("MELOA", "melons"),
    ("MELANCIA", "watermelons"),
    ("TOMATE", "tomatoes"),
    ("PESSEGO", "peaches"),
    ("MANGA", "mangoes"),
    ("MAMAO", "papayas"),
    ("PAPAIA", "papayas"),
]

# Things that can be in an area that are no product at all.
EMPTY_PROMPTS = [
    "a photo of an empty basket in a supermarket",
    "a photo of an empty crate on a supermarket shelf",
    "a photo of an empty black supermarket shelf",
    "a photo of a supermarket shelf covered by a grey cloth",
]

_TEMPLATES = [
    "a photo of {} in a supermarket display",
    "a close-up photo of {} in a store basket",
]
_PACKAGED_TEMPLATES = [
    "a photo of {} in plastic bags or packages in a supermarket",
    "a close-up photo of packaged {} on a store shelf",
]
# A weight right after a number, e.g. "500 G", "EMB. 3KG", "1.5 KG"; not a calibre like "73/85 KG".
_PACKAGED_RE = re.compile(r"(?<![/\w.])\d+(\.\d+)?\s*(KG|G|GR)\b")


def normalize(name: str) -> str:
    """Upper-case, strip accents (MAÇÃ -> MACA)."""
    s = unicodedata.normalize("NFKD", name.upper())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def is_packaged(product_name: str) -> bool:
    return bool(_PACKAGED_RE.search(normalize(product_name)))


def category_of(product_name: str) -> str:
    """Generic category key, e.g. 'bananas' or 'potatoes (packaged)'. Raises if no rule matches."""
    words = set(re.findall(r"[A-Z]+", normalize(product_name)))
    for rule, noun in RULES:
        if set(rule.split()) <= words:
            return noun + (PACKAGED_SUFFIX if is_packaged(product_name) else "")
    raise KeyError(f"no category rule for product {product_name!r}; add one to lemma/categories.py RULES")


def family_of(product_name: str) -> str | None:
    """Variety family of a *loose* product (e.g. 'apples'), None for packaged or family-less products."""
    if is_packaged(product_name):
        return None
    words = set(re.findall(r"[A-Z]+", normalize(product_name)))
    return next((fam for rule, fam in FAMILY_RULES if set(rule.split()) <= words), None)


def base_noun(category: str) -> str:
    return category.removesuffix(PACKAGED_SUFFIX)


def prompts_for(category: str) -> list[str]:
    templates = _PACKAGED_TEMPLATES if category.endswith(PACKAGED_SUFFIX) else _TEMPLATES
    return [t.format(base_noun(category)) for t in templates]


def all_categories() -> list[str]:
    """Every category key a rule can produce (loose and packaged)."""
    nouns = list(dict.fromkeys(noun for _, noun in RULES))
    return nouns + [n + PACKAGED_SUFFIX for n in nouns]


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from lemma.planogram import load_areas

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "dataset" / "planogram.json"
    names = sorted({a.product_name for areas in load_areas(path).values() for a in areas})
    for n in names:
        print(f"{category_of(n):32} {family_of(n) or '-':12} <- {n}")
    print(f"\n{len(names)} products -> {len({category_of(n) for n in names})} categories")
