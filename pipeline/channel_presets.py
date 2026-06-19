"""Channel niches: system prompt + defaults for Groq script generation.

Only the ghost_stories niche is active. All other presets have been removed.
"""

from __future__ import annotations

from typing import TypedDict


class Variant(TypedDict, total=False):
    """One output variant — same images, different audio/subs/upload target."""
    lang: str
    label: str
    tts_voice: str
    caption_font: str
    caption_font_name: str
    yt_token_env: str
    min_words: int


class ChannelPreset(TypedDict, total=False):
    id: str
    label: str
    groq_system_hint: str
    segment_count: int
    topic_pool: list[str]
    image_style_suffix: str
    image_negative_prompt: str
    language: str
    tts_voice: str
    caption_font: str
    caption_font_name: str
    min_words: int
    variants: list[Variant]
    topic_rotation: str
    yt_token_env: str
    extra_yt_token_envs: list[str]
    description_hashtags: list[str]


PRESETS: dict[str, ChannelPreset] = {
    "ghost_stories": {
        "id": "ghost_stories",
        "label": "Ghost / horror storytime Short",
        "min_words": 60,
        "tts_voice": "en-US-ChristopherNeural",
        "caption_font": "CreepsterCaps.ttf",
        "caption_font_name": "Creepster",
        "yt_token_env": "YT_REFRESH_TOKEN",
        "description_hashtags": [
            "GhostStory", "Horror", "Scary", "Storytime",
            "SpookyStory", "HorrorShorts", "CreepyStory",
            "GhostStories", "ScaryStory", "HorrorStorytime",
        ],
        "groq_system_hint": (
            "You are a master horror storyteller for YouTube Shorts. Your ghost stories are gripping, "
            "atmospheric, and genuinely unsettling — they stop scrolling and leave viewers with chills.\n\n"

            "STORY CRAFT:\n"
            "• Open MID-SCENE — no preamble. First line creates immediate unease. "
            "\"The door at the end of the hall opened on its own again.\" "
            "Never start with 'Today I want to tell you...'\n"
            "• Use SPECIFIC, REAL details: give characters real names, use exact times ('3:14 AM'), "
            "name exact places ('Room 217', 'Maple Grove Road'). Specificity creates believability.\n"
            "• Build dread through SENSORY DETAILS — the cold spot, the smell of damp earth, "
            "the sound of breathing behind a wall. Don't name the monster; describe its effects.\n"
            "• PACING: Short punchy sentences = fast heartbeat tension. Long slow sentences = suffocating dread. "
            "Alternate deliberately.\n"
            "• NEVER explain the supernatural — ambiguity is horror's most powerful tool.\n"
            "• ENDING (most important): Final 1-2 sentences must land a chill. An unanswered question, "
            "a dark realization, or a twist that recontextualizes everything. The last word should echo.\n\n"

            "TONE: Eerie, dread-filled, atmospheric. NOT gory, NOT explicit violence. "
            "PG-13 horror — psychological, not physical. Original characters only. No hashtags in narration.\n\n"

            "CRITICAL LENGTH: full_narration MUST be 75-95 English words. "
            "This creates ~28-32 seconds of audio. Tight and punchy — every word earns its place. "
            "Count carefully — never go below 75 words or above 100 words.\n\n"

            "IMAGE PROMPTS: Write 5 cinematic horror scene descriptions in English only. "
            "Each should capture a DIFFERENT moment and visual element — vary between: "
            "wide establishing shots of the haunted location, medium shots of the character reacting, "
            "close-ups of the horrifying detail, the entity partially revealed, the chilling aftermath. "
            "Every image should feel like a still from a horror film."
        ),
        "segment_count": 5,
        "image_style_suffix": (
            ", dark atmospheric horror illustration, deep shadows with single eerie light source, "
            "muted desaturated palette with pops of sickly pale green or cold blue, "
            "thick bold outlines, ghostly translucent figures, dramatic chiaroscuro lighting, "
            "sinister oppressive mood, professional horror storybook art quality, "
            "cinematic composition, high contrast, no text, no watermark, no logos"
        ),
        "image_negative_prompt": (
            "photorealistic, photograph, happy, cheerful, bright, colorful, anime eyes, blurry, "
            "low quality, watermark, logo, text, title, signature, ugly, grainy, "
            "gore, blood, nudity, child-unsafe, cartoon mascot, cute"
        ),
        "topic_pool": [
            # Classic haunted locations
            "a ghost haunting an empty school corridor at 3 AM",
            "a strange presence in a family home the night after a funeral",
            "something unexplained on a solo hike through dense fog",
            "a ghost encounter in a hospital elevator after visiting hours",
            "a haunted old cabin discovered during a camping trip",
            "a ghost on the last train carriage that shouldn't be running",
            "something wrong with the new neighbor who only comes out at night",
            "a spirit locked in the grandparents' attic for decades",
            "an abandoned playground where swings move with no wind",
            "a ghost at a roadside motel in room 13",
            "strange events at a wedding venue the night before the ceremony",
            "a haunted library where books rearrange themselves after midnight",
            "something watching from the tree line at the edge of the yard",
            "a ghost during a complete blackout in a storm",
            "an eerie presence in a nursing home corridor at 4 AM",
            "something in the basement that the family never talks about",
            "a ghost on a deserted beach during low tide",
            "a haunted elevator in a 1970s apartment building",
            "a strange figure at a bus stop at exactly 3:33 AM",
            "something whispering from the drain in an old well",
            "a ghost in a classroom the night after the last student left forever",
            "a haunted antique mirror bought from a widow's estate sale",
            "a spirit tied to an old family photograph found in a locked chest",
            "something in the fog on a mountain road in November",
            "a ghost at a summer camp that closed after a drowning accident",
            # Modern / suburban settings
            "a haunted smart home where the AI assistant answers questions no one asked",
            "a ghost seen on CCTV footage in an empty parking garage at 2 AM",
            "something wrong in a hotel room that was double-booked with a guest who checked in years ago",
            "a presence in an Airbnb where the host's photo on the wall keeps changing position",
            "a ghost on a night shift alone in an office building on the top floor",
            "something in the woods behind a new housing development built on old farmland",
            "a haunted apartment where the previous tenant never actually moved out",
            "a ghost encountered during a solo late-night drive through rural countryside",
            "something in a basement with a freshly poured concrete floor no one remembers pouring",
            "a presence in a storage unit filled with a stranger's belongings and one unlocked diary",
            "a ghost in a dressing room of a closed department store",
            "something inside a smart refrigerator that starts speaking at night",
            "a haunted Zoom call where an extra participant joins who no one recognizes",
            # Haunted objects
            "a music box that plays a melody no one taught it",
            "a vintage telephone that rings and connects to someone who died in 1987",
            "a child's drawing found sealed in the walls during a kitchen renovation",
            "a rocking chair that still rocks in a house where no one lives",
            "a shadow that appears in every photograph taken in one specific room",
            "a clock that stopped at the exact moment someone in the house died twenty years ago",
            "a locked diary found in a thrift store that describes events from the future",
            "a radio that turns on at 3 AM and plays a station that was shut down in 1993",
            "a doll that was donated to charity three times and always finds its way home",
            "a painting that slowly changes every night when the lights are off",
            "an old camcorder with footage of a place no one in the family has ever been",
            # Supernatural encounters
            "a child ghost that only the family dog can see but always barks at the same corner",
            "a duplicate of the main character seen standing at their own bedroom window from outside",
            "a ghost that only appears in mirrors and watches but never moves",
            "a presence that perfectly mimics the voice of someone's late mother",
            "a figure that appears at funerals to sit in the front row and then vanishes",
            "a ghost that leaves wet footprints leading to the lake but never leading back",
            "a shadow person seen at the top of the stairs in three different houses in one family",
            "a hitchhiker who vanishes from a moving car on a locked highway",
            "a figure seen at the window of a house that burned down fifteen years ago",
            # Psychological / ambiguous horror
            "a person who wakes with no memory of the last three hours and muddy hands",
            "a family that notices their child has been saying a dead relative's name in their sleep",
            "a recurring nightmare that leads to a real address that actually exists",
            "a person who receives a voicemail from their own number that they never made",
            "a twin who realizes their sibling has been dead for a week but keeps appearing at dinner",
            "a woman who realizes the reflection in her new house's mirror is two seconds behind",
            # Folklore and atmospheric
            "a ghost road where drivers always see the same hitchhiker who disappears before they stop",
            "a childhood home the family visits that others insist has been demolished for years",
            "a bridge where rescuers hear crying every night but never find anyone below",
            "a haunted lighthouse that still sends signals on frequencies decommissioned in 1941",
            "a ghost town the family drives through on a road trip but cannot find on any map afterward",
            "a forest trail that always leads hikers back to the same clearing no matter which way they turn",
            "a remote farmhouse where every clock in the house stopped at the same time on the same night",
        ],
    },
}


def list_channel_ids() -> list[str]:
    return sorted(PRESETS.keys())


def get_preset(channel_id: str) -> ChannelPreset:
    key = channel_id.strip().lower().replace("-", "_")
    if key not in PRESETS:
        raise KeyError(f"Unknown channel preset {channel_id!r}. Try: {', '.join(list_channel_ids())}")
    return PRESETS[key]
