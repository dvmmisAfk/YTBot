"""Channel niches: system prompt + defaults for Groq script generation.

Active preset: world_facts — catchy world/culture/science trivia Shorts.
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
    renderer: str  # "slideshow" (default) or "motion"


PRESETS: dict[str, ChannelPreset] = {
    "world_facts": {
        "id": "world_facts",
        "label": "World & culture facts Short",
        "renderer": "slideshow",
        "min_words": 60,
        "tts_voice": "en-US-GuyNeural",
        "caption_font": "Arial.ttf",
        "caption_font_name": "Arial",
        "yt_token_env": "YT_REFRESH_TOKEN",
        "description_hashtags": [
            "DidYouKnow", "FunFacts", "WorldFacts", "AmazingFacts",
            "Culture", "Geography", "History", "ScienceFacts",
            "LearnOnYouTube", "MindBlown",
        ],
        "groq_system_hint": (
            "You are a viral YouTube Shorts fact creator. You turn surprising, real-world trivia "
            "into scroll-stopping 30-second videos that make viewers say 'Wait, WHAT?!'\n\n"

            "FACT CRAFT:\n"
            "• HOOK FIRST — open with the most shocking part of the fact. "
            "Start with 'Did you know…', a bold number, or a counterintuitive claim. "
            "Never open with 'Today we're going to learn about…'\n"
            "• ONE CORE FACT per video — pick ONE mind-blowing truth and build everything around it. "
            "Add 2-3 supporting details that make it stick (numbers, comparisons, context).\n"
            "• USE SPECIFICS — real country names, dates, numbers, and comparisons "
            "('that's taller than the Eiffel Tower', 'more people than live in Canada'). "
            "Specificity = credibility + shareability.\n"
            "• PACING: Mix short punchy sentences with one longer payoff line. "
            "Sound like a friend telling you something wild, not a textbook.\n"
            "• ENDING: Land a memorable closer — restate the fact in a new way, "
            "a 'let that sink in' moment, or a question that makes them want to comment.\n\n"

            "TOPIC RANGE: Geography, cultures, food traditions, animals, history oddities, "
            "language quirks, inventions, records, space, psychology, everyday objects — "
            "anything with a genuine 'I had no idea' factor.\n\n"

            "TONE: Energetic, curious, upbeat. Family-friendly. No politics, no controversy, "
            "no made-up facts. If unsure, pick a well-known verified fact. No hashtags in narration.\n\n"

            "CRITICAL LENGTH: full_narration MUST be 75-95 English words (~28-32 sec spoken). "
            "Tight and punchy — every word earns its place.\n\n"

            "IMAGE PROMPTS: Write 5 vivid scene descriptions in English only — "
            "documentary/travel photography style showing the subject of the fact. "
            "Vary shots: wide landscape, cultural detail, close-up of the object/phenomenon, "
            "people in context (generic, not identifiable), iconic location. "
            "Bright, colorful, real-world — NOT horror, NOT dark, NOT cartoon."
        ),
        "segment_count": 5,
        "image_style_suffix": (
            ", vibrant documentary photography, National Geographic style, warm natural lighting, "
            "rich saturated colors, photorealistic, travel magazine quality, "
            "no text, no captions, no watermark, no logos"
        ),
        "image_negative_prompt": (
            "blurry, low quality, watermark, logo, text, title, signature, ugly, grainy, "
            "dark, horror, scary, gore, cartoon, anime, oversaturated, distorted"
        ),
        "topic_pool": [
            # Geography & nature
            "the country that has no rivers at all",
            "a lake in Africa that can explode and release deadly gas",
            "the town in Norway where the sun doesn't set for months",
            "why Iceland has almost no mosquitoes",
            "the desert that used to be a lush green forest",
            "a waterfall in Venezuela that falls from such height the water turns to mist",
            "the island nation that is sinking due to rising sea levels",
            "why Australia is wider than the moon",
            "the coldest inhabited place on Earth where people still live normally",
            "a forest in Poland where trees grow in perfect curved shapes",
            # Culture & traditions
            "why people in Spain eat dinner at 10 PM",
            "the Japanese tradition of repairing broken pottery with gold",
            "why brides in India wear red instead of white",
            "the country where pointing with your index finger is considered rude",
            "why Scottish men wear kilts and what they symbolize",
            "the Mexican holiday where families welcome back spirits with food and music",
            "why Thai people wai instead of shaking hands",
            "the Ethiopian coffee ceremony that can take hours",
            "why Finnish babies sleep in cardboard boxes provided by the government",
            "the Korean age system where you are 1 year old at birth",
            # Food & cuisine
            "why pineapple on pizza is actually popular in one country",
            "the fruit that is illegal to bring into the US from certain countries",
            "why Swiss chocolate became world-famous",
            "the spice that was once worth more than gold",
            "why people in the UK call french fries 'chips'",
            "the world's most expensive coffee made from animal droppings",
            "why bread in Germany has over 3000 varieties",
            "the country that eats the most ice cream per person",
            "why sushi was originally a way to preserve fish",
            "the cheese that is illegal in some countries due to bacteria",
            # History oddities
            "the war that lasted only 38 minutes",
            "why the Great Wall of China cannot be seen from space with the naked eye",
            "the ancient Roman punishment for killing your father",
            "why Napoleon was actually average height for his time",
            "the library that burned down and set human knowledge back centuries",
            "why Vikings never actually wore horned helmets",
            "the empire that lasted over 1000 years but most people forget about",
            "why Cleopatra lived closer in time to the iPhone than to the pyramids",
            "the shortest-reigning king who ruled for only 20 minutes",
            "why the Titanic had a sister ship that also sank",
            # Science & animals
            "why octopuses have three hearts and blue blood",
            "the animal that can sleep while flying",
            "why bananas are technically berries but strawberries are not",
            "the bird that can mimic chainsaws and camera shutters",
            "why honey never spoils — archaeologists found edible honey in Egyptian tombs",
            "the fish that can live out of water for years",
            "why your stomach gets a new lining every few days",
            "the ant that can carry 50 times its body weight",
            "why flamingos are pink because of what they eat",
            "the animal that has been to space before humans",
            # Language & communication
            "why there is no word for 'yes' in Irish Gaelic",
            "the language with the most words in the world",
            "why English has more words than any other language",
            "the country with over 700 spoken languages",
            "why the @ symbol is called different things in different countries",
            "the word that is the same in almost every language on Earth",
            "why Japanese has three different writing systems",
            "the language that has no future tense",
            "why sign language is not universal — there are hundreds of them",
            "the longest word in the English dictionary",
            # Records & inventions
            "why the QWERTY keyboard was designed to slow you down",
            "the invention that was rejected 12 times before becoming famous",
            "why bubble wrap was originally invented as wallpaper",
            "the country with the most time zones",
            "why the first computer bug was an actual insect",
            "the tallest building in the world and how long it took to build",
            "why Post-it Notes were invented by accident",
            "the sport invented in one country but dominated by another",
            "why the Olympic rings have those specific five colors",
            "the phone that was sold for over 100 million units",
            # Space & psychology
            "why a day on Venus is longer than its year",
            "the planet where it rains diamonds",
            "why astronauts grow taller in space",
            "the human brain uses the same amount of power as a light bulb",
            "why you can't hum while holding your nose",
            "the optical illusion that proves your brain fills in gaps",
            "why we forget most of our dreams within minutes of waking",
            "the country that has a national holiday for napping",
            "why laughing is contagious — the science behind it",
            "the phobia that is the most common in the world",
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
