"""Check-in tag features for lifestyle similarity."""

from typing import Dict, Optional, Set

ALL_TAGS = [
    "coffee", "nightlife", "fitness", "foodie", "outdoors",
    "arts", "music", "travel", "gaming", "wellness",
]

# Maps sessiontracker.primary_type (Google Places) → ALL_TAGS bucket
TAG_TYPE_MAP = {
    "cafe": "coffee",
    "coffee_shop": "coffee",
    "bakery": "coffee",
    "bar": "nightlife",
    "night_club": "nightlife",
    "lounge": "nightlife",
    "pub": "nightlife",
    "gym": "fitness",
    "fitness_center": "fitness",
    "sports_complex": "fitness",
    "stadium": "fitness",
    "restaurant": "foodie",
    "meal_takeaway": "foodie",
    "meal_delivery": "foodie",
    "supermarket": "foodie",
    "grocery_or_supermarket": "foodie",
    "food": "foodie",
    "park": "outdoors",
    "hiking_area": "outdoors",
    "campground": "outdoors",
    "national_park": "outdoors",
    "park_trail": "outdoors",
    "museum": "arts",
    "art_gallery": "arts",
    "performing_arts_theater": "arts",
    "library": "arts",
    "concert_hall": "music",
    "music_venue": "music",
    "tourist_attraction": "travel",
    "airport": "travel",
    "train_station": "travel",
    "lodging": "travel",
    "hotel": "travel",
    "amusement_center": "gaming",
    "bowling_alley": "gaming",
    "video_arcade": "gaming",
    "spa": "wellness",
    "yoga_studio": "wellness",
    "beauty_salon": "wellness",
    "physiotherapist": "wellness",
}

_TAG_INDEX = {t: i for i, t in enumerate(ALL_TAGS)}


def primary_type_to_tag(primary_type: Optional[str]) -> Optional[str]:
    """Normalize a sessiontracker primary_type to an ALL_TAGS bucket."""
    if not primary_type:
        return None
    key = primary_type.strip().lower()
    if key in ALL_TAGS:
        return key
    return TAG_TYPE_MAP.get(key)


def empty_tag_counts() -> Dict[str, int]:
    return {t: 0 for t in ALL_TAGS}


def lifestyle_similarity(a: Dict[str, int], b: Dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(t, 0) * b.get(t, 0) for t in ALL_TAGS)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    if na <= 0 or nb <= 0:
        return 0.0
    return min(1.0, dot / (na * nb))


def checkin_overlap(my_places: Set[str], cand_places: Set[str]) -> float:
    if not my_places or not cand_places:
        return 0.0
    overlap = len(my_places & cand_places)
    denom = max(1, min(len(my_places), len(cand_places)))
    return min(1.0, overlap / denom)
