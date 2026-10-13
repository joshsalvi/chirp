"""
Chirp Server — Hardcoded "Bat" Species Profile Content
=========================================================
Chirp's bat-echolocation detector identifies bat activity but cannot
currently identify species from a pulse train alone (no bundled acoustic
classifier exists for this — see chirp-device/chirp/bat_detector.py for the
full explanation). Rather than enrich a "Bat" BirdProfile through the normal
per-species pipeline (Wikipedia/iNaturalist/eBird article lookup, which
expects a real binomial name and would either fail or return nonsense for
a label that spans 1,500+ species), this module provides a single static,
hand-written profile covering bats as a group and the biology of
echolocation in general.

Content is original prose, written by synthesizing and substantially
rewording the general-audience facts found in the Wikipedia articles
"Bat" (https://en.wikipedia.org/wiki/Bat) and "Animal echolocation"
(https://en.wikipedia.org/wiki/Animal_echolocation), per Chirp's standing
copyright policy of paraphrase-don't-quote. It is not a verbatim or
close-paraphrase reproduction of either article, and intentionally
reorganizes the material around what a Chirp user actually wants to know
after seeing a bat detection: what a "Bat" detection means and doesn't
mean, what's actually happening acoustically, and where to read further.

If/when a real acoustic bat-species classifier becomes available
(chirp-device/chirp/bat_detector.py's docstring discusses why none
currently ships with Chirp), this module's single generic profile can be
retired in favor of normal per-species enrichment, the same pipeline birds
already use.
"""

BAT_LABEL = "Bat"
BAT_COMMON_NAME = "Bat"
BAT_SCIENTIFIC_NAME = "Chiroptera"

BAT_DESCRIPTION_SECTIONS = [
    {
        "section": "About this detection",
        "text": (
            "Chirp's bat detector listens for the ultrasonic pulse trains bats "
            "produce while echolocating and flags activity when it finds a "
            "matching pattern, but it does not identify which species made the "
            "call. Telling bat species apart from their calls alone is a hard "
            "problem even for dedicated acoustic classifiers and specialist "
            "software, since many species' calls overlap heavily in frequency "
            "and structure, and reliable separation generally also requires "
            "things this system doesn't have, such as comparison against a "
            "library of reference calls recorded in the same region. For now, "
            "every detection is logged simply as \"Bat.\" If species-level bat "
            "identification becomes practical to add in a future version, this "
            "page will be replaced by individual species profiles, the same way "
            "every detected bird species already gets its own page."
        ),
    },
    {
        "section": "What bats are",
        "text": (
            "Bats are the only group of mammals capable of true, sustained "
            "flight, rather than the brief gliding seen in animals like flying "
            "squirrels. Their wings are formed from a thin skin membrane "
            "stretched across long, spread fingers, the same basic bone layout "
            "as a human hand. With over 1,400 known species, bats are the "
            "second-largest order of mammals after rodents, accounting for "
            "roughly a fifth of all mammal species, and they are found on "
            "every continent except Antarctica. Body size varies enormously "
            "across the group, from Kitti's hog-nosed bat, barely the size of "
            "a large bumblebee, to flying foxes with wingspans over five feet."
        ),
    },
    {
        "section": "How echolocation works",
        "text": (
            "Most bats navigate and hunt in total darkness by producing short, "
            "very high-frequency calls and listening to the returning echoes, "
            "a sense called echolocation. By timing how long an echo takes to "
            "come back and comparing what each ear hears, a bat can build a "
            "detailed picture of its surroundings, including the size, "
            "texture, and movement of nearby objects, all from sound alone. "
            "Calls fall into two broad styles: frequency-modulated sweeps, "
            "which give very precise distance information and work well for "
            "navigating cluttered spaces like a forest canopy, and constant-"
            "frequency tones, which carry farther and let a bat detect a "
            "moving target's speed through the Doppler effect, the same "
            "principle behind a siren changing pitch as it passes by. Many "
            "species combine both in a single call. Most echolocation calls "
            "fall roughly between 9 kHz and 200 kHz, almost entirely above the "
            "upper limit of human hearing (commonly cited as around 20 kHz), "
            "which is exactly why specialized ultrasonic microphones, like the "
            "one this device uses, are needed to pick them up at all."
        ),
    },
    {
        "section": "Behavior and ecology",
        "text": (
            "Most bats are nocturnal, spending daylight hours roosting in "
            "caves, trees, crevices, or buildings, then emerging at dusk to "
            "feed. Diet varies widely by species: most bats eat insects, many "
            "others feed on fruit or nectar, and a small number of species, "
            "found only in the Americas, feed on blood. Insect-eating bats "
            "are voracious, often eating well over their own body weight in "
            "insects each night, making them a significant natural check on "
            "agricultural pests and mosquito populations. Fruit- and nectar-"
            "feeding bats are, in turn, important pollinators and seed "
            "dispersers for many plant species, including several that "
            "people rely on commercially."
        ),
    },
    {
        "section": "Conservation",
        "text": (
            "Bat populations face pressure from habitat loss, wind turbine "
            "collisions, and, in North America, white-nose syndrome, a fungal "
            "disease that has killed millions of bats since it was first "
            "identified in 2006. A 2020 IUCN assessment found that roughly "
            "16% of evaluated bat species are threatened or near-threatened, "
            "with about 18% too poorly studied to assess. Many countries "
            "protect bats and their roosts by law. Long-term detection data "
            "like the kind this device collects, tracking when and how often "
            "bat activity occurs at a given location over time, is exactly "
            "the sort of information conservation researchers use to monitor "
            "population trends, even without species-level detail."
        ),
    },
    {
        "section": "Further reading",
        "text": (
            "This page summarizes general bat biology and echolocation for "
            "Chirp users; it intentionally leaves out a great deal. For the "
            "full picture, including bat taxonomy, anatomy, reproduction, and "
            "cultural history, see Wikipedia's \"Bat\" article "
            "(en.wikipedia.org/wiki/Bat). For a deeper technical treatment of "
            "echolocation itself, including how it evolved and how it's used "
            "by dolphins and a handful of other animals besides bats, see "
            "Wikipedia's \"Animal echolocation\" article "
            "(en.wikipedia.org/wiki/Animal_echolocation)."
        ),
    },
]

# Sources cited on the profile page (NOT used for enrichment fetching —
# this profile is fully static and never re-enriched).
BAT_SOURCES = [
    {"label": "Bat — Wikipedia", "url": "https://en.wikipedia.org/wiki/Bat"},
    {"label": "Animal echolocation — Wikipedia", "url": "https://en.wikipedia.org/wiki/Animal_echolocation"},
]
