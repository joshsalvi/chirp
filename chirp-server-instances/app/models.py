"""
Chirp Server Database Models
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime,
    Text, JSON, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from .database import Base


def new_uuid():
    return str(uuid.uuid4())


class BirdPhoto(Base):
    """
    A user-submitted photo for a bird profile (distinct from the auto-enriched
    primary photo_path/extra_photos, which come from Wikipedia/iNaturalist).
    Optionally AI-checked against the profile's species for a sanity-check
    confirmation — see services/photo_id.py.
    """
    __tablename__ = "bird_photos"

    id = Column(String, primary_key=True, default=new_uuid)
    bird_profile_id = Column(String, ForeignKey("bird_profiles.id"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    uploaded_by = Column(String, nullable=True)       # username, if auth is enabled
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    # AI species-confirmation result (see services/photo_id.py) — entirely
    # optional; only populated if an Anthropic API key is configured in
    # Settings. ai_checked distinguishes "we tried and got an answer" from
    # "no key configured, never attempted" so the UI can show the right
    # state instead of treating both as failure.
    ai_checked = Column(Boolean, default=False)
    ai_match = Column(Boolean, nullable=True)          # True/False/None (None = inconclusive)
    ai_guess = Column(String, nullable=True)           # species name(s) the AI identified
    ai_note = Column(Text, nullable=True)              # short free-text explanation


class Recording(Base):
    """
    A single audio recording from a Chirp device.
    Contains the raw WAV file and all associated detections.
    """
    __tablename__ = "recordings"

    id = Column(String, primary_key=True, default=new_uuid)
    filename = Column(String, nullable=False, index=True)
    wav_path = Column(String, nullable=False)
    json_path = Column(String, nullable=True)
    spectrogram_path = Column(String, nullable=True)

    # Timing
    trigger_timestamp = Column(DateTime, nullable=False, index=True)
    duration_seconds = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Audio properties
    sample_rate = Column(Integer, default=48000)
    channels = Column(Integer, default=2)
    pre_roll_seconds = Column(Float, default=5.0)
    energy_db = Column(Float, nullable=True)
    # A rough, species-agnostic in-band-vs-floor estimate, computed once
    # server-side during processing (see audio_processor.compute_snr_db's
    # own docstring for the full reasoning) — NOT the same thing as
    # energy_db above, which is a device-reported trigger-time loudness
    # level with no noise-floor comparison at all, and is only ever
    # present for device uploads in the first place. This is computed the
    # same way for every recording regardless of source, specifically so
    # a genuinely noisy recording can be flagged without anyone needing
    # to export the audio and measure it by hand.
    snr_db = Column(Float, nullable=True)
    device_count = Column(Integer, default=1)

    # Source device info
    device_id = Column(String, nullable=True, index=True)     # Optional device identifier
    latitude = Column(Float, nullable=True)        # Device GPS lat at time of recording
    longitude = Column(Float, nullable=True)       # Device GPS lon
    haikubox_detection_id = Column(String, nullable=True, index=True)  # Haikubox dedup key (serial:species:timestamp)
    bird_buddy_media_id = Column(String, nullable=True, index=True, unique=True)  # Bird Buddy media id — dedup key
    bird_buddy_video_path = Column(String, nullable=True)  # original video, preserved for future photo/video support — not used for playback (wav_path holds the extracted audio)

    # Bat echolocation activity (see chirp-device/chirp/bat_detector.py).
    # Bat recordings flow through this same Recording/Detection table (one
    # Detection row, common_name="Bat") so they show up in RecordingsList,
    # the life list, and the field guide automatically, the same as any
    # bird — but pulse-train stats don't fit the Detection schema, so they're
    # kept here as a JSON blob instead of new bird-shaped columns.
    is_bat = Column(Boolean, default=False, index=True)
    bat_metadata = Column(JSON, nullable=True)   # {pulse_count, peak_freq_hz, mean_pulse_duration_ms,
                                                   #  swept_fraction, sample_rate, species_guess?}
                                                   # species_guess (added by services/bat_species_classifier.py
                                                   # via api/recordings.py's _process_bat_recording_bg, only
                                                   # present when bat_species_id_enabled and the recording met
                                                   # the minimum duration for a fair classification) is itself:
                                                   # {model, model_trained_on, top_species, top_non_species,
                                                   #  all_species, all_non_species, num_windows, validated: False}
                                                   # validated is always False today — a species only actually
                                                   # gets asserted as this Detection's common_name/scientific_name
                                                   # (elsewhere, not in this JSON blob) when top_species clears
                                                   # bat_species_id_min_confidence AND beats top_non_species;
                                                   # this blob itself always reflects everything the classifier
                                                   # actually saw, asserted or not, for full transparency.

    # AI second-opinion re-check on this recording's call (services/call_reanalysis.py)
    # — per-recording, on-demand only (a "Re-check this call" button on the
    # detail page), no scheduled job.
    ai_reanalysis_note = Column(Text, nullable=True)
    ai_reanalysis_generated_at = Column(DateTime, nullable=True)
    ai_reanalysis_error = Column(String, nullable=True)
    ai_reanalysis_verdict = Column(String, nullable=True)  # "consistent" | "inconsistent" | "uncertain" — parsed from the model's own structured response, not inferred client-side

    # User-supplied metadata
    label = Column(String, nullable=True)    # Custom display name / label
    notes = Column(Text, nullable=True)      # Free-text notes

    # Live Detect session recording — the full continuous audio for a
    # Live Detect walk, saved as one Recording at Stop (see
    # live_detect.py's save_session()) rather than leaving a scatter of
    # tiny per-detection clips. Detections from those original small
    # clips get re-parented here (with adjusted timestamps) and the
    # small clips themselves get deleted, so this is genuinely one
    # Recording per session, not an additional summary alongside them.
    is_live_session = Column(Boolean, default=False, index=True)

    # The individual, few-second clip a single Live Detect poll creates
    # while a session is still in progress — meant to be transient: it
    # either gets consolidated into one is_live_session=True recording
    # when the person saves the session (see save_session's own
    # re-parenting + delete logic above), or gets left behind if they
    # never save one. Reported directly from a real deployment: leaving
    # a Live Detect page open for a couple of minutes created 407 of
    # these, none ever cleaned up, burying every real recording in the
    # main list under them. Marked explicitly at creation time (see
    # live_detect.py's own analyze endpoint) rather than inferred from
    # the "livedetect_" filename prefix, so the main recordings list can
    # exclude these specifically without an unreliable, string-based
    # rule and without also excluding the one real, consolidated session
    # recording that same prefix also happens to share.
    is_live_detect_clip = Column(Boolean, default=False, index=True)
    # When the BirdNET v3 shadow pass last scored this recording (Experimental)
    shadow_checked_at = Column(DateTime, nullable=True)

    # iNaturalist submission
    inat_observation_id  = Column(String, nullable=True)   # e.g. "369739156"
    inat_observation_url = Column(String, nullable=True)   # full URL

    # Processing state
    processing_status = Column(
        SAEnum("pending", "processing", "done", "error", name="proc_status"),
        default="pending", index=True
    )
    processing_error = Column(Text, nullable=True)

    # File metadata
    file_size_bytes = Column(Integer, nullable=True)   # size of audio file on disk

    # Soft delete — recording is hidden from counts AND lists; files kept
    # on disk until storage_manager's age/size pruning removes them later
    # (or a hard delete removes everything immediately). This is NOT the
    # same thing as archiving below — soft-deleted recordings disappear
    # from statistics, archived ones must not.
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Archive — distinct from deleted_at by design. An archived recording
    # stays fully visible everywhere (recordings list, detection counts,
    # species statistics, life list) with its detections, spectrogram,
    # and notes all intact — only the audio file itself is gone, along
    # with anything that depends on having one (playback, WAV download,
    # iNaturalist sound-observation submission, server-side BirdNET
    # re-analysis). This is the opt-in, reversible disk-space-saving
    # action; deleted_at above is the separate, harsher "hide everything"
    # action. The two are independent: a recording could in principle be
    # both, though normal usage is one or the other.
    archived_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    detections = relationship("Detection", back_populates="recording",
                               cascade="all, delete-orphan", lazy="selectin")
    near_misses = relationship("NearMiss", cascade="all, delete-orphan", lazy="select")
    reanalysis_runs = relationship("ReanalysisRun", cascade="all, delete-orphan", lazy="select")
    shadow_detections = relationship("ShadowDetection", cascade="all, delete-orphan", lazy="select")

    @property
    def top_species(self) -> Optional[str]:
        if self.detections:
            best = max(self.detections, key=lambda d: d.confidence)
            return best.common_name
        return None

    @property
    def max_confidence(self) -> float:
        if self.detections:
            return max(d.confidence for d in self.detections)
        return 0.0

    def __repr__(self):
        return f"<Recording {self.id[:8]} {self.trigger_timestamp} {self.top_species}>"


class Detection(Base):
    """
    A single species detection within a recording.
    """
    __tablename__ = "detections"

    id = Column(String, primary_key=True, default=new_uuid)
    recording_id = Column(String, ForeignKey("recordings.id"), nullable=False, index=True)

    # Species identification
    common_name = Column(String, nullable=False, index=True)
    scientific_name = Column(String, nullable=True)
    label = Column(String, nullable=False, index=True)
    confidence = Column(Float, nullable=False, index=True)

    # Temporal location within the recording (seconds from start of recording)
    start_time = Column(Float, default=0.0)
    end_time = Column(Float, default=3.0)

    # Clip path (short excerpt for this detection)
    clip_path = Column(String, nullable=True)

    # Source: "device" (from Pi's BirdNET) or "server" (re-analyzed server-side)
    source = Column(String, default="device", index=True)

    # Relationships
    recording = relationship("Recording", back_populates="detections")
    # bird profile looked up in API layer by label

    def __repr__(self):
        return f"<Detection {self.common_name} {self.confidence:.0%} @ {self.start_time:.1f}s>"


class BirdProfile(Base):
    """
    Enriched bird species profile.
    Cached data from eBird, iNaturalist, Xeno-canto, Wikipedia.
    """
    __tablename__ = "bird_profiles"

    id = Column(String, primary_key=True, default=new_uuid)
    label = Column(String, unique=True, nullable=False, index=True)  # BirdNET label
    common_name = Column(String, nullable=False, index=True)
    scientific_name = Column(String, nullable=True)

    # True for the generic "Bat" pseudo-species AND any confidently-
    # classified specific bat species — a real, reliable flag rather than
    # guessing from label/common_name text (which is user-editable and can
    # diverge, as a real profile-renaming incident this session showed).
    # Set explicitly at profile-creation time by ensure_profile()'s
    # is_bat parameter — see bird_enricher.py. Used by the frontend to
    # correctly disable bird-specific map sources (eBird Status & Trends,
    # iNaturalist Geomodel, BirdLife International, All About Birds range
    # maps) for any bat profile, generic or species-specific — none of
    # those sources have meaningful bat range data, unlike Macaulay
    # Library (media only, works fine for any taxonomic group).
    is_bat = Column(Boolean, default=False, index=True)

    # Wikipedia / general description
    description = Column(Text, nullable=True)
    description_source = Column(String, nullable=True)

    # Media
    photo_path = Column(String, nullable=True)       # Local path to downloaded photo
    photo_url = Column(String, nullable=True)        # Source URL for photo
    photo_credit = Column(String, nullable=True)     # Attribution
    photo_thumb_path = Column(String, nullable=True) # 300px thumbnail

    # Call/song media — JSON list of {path, url, source, type, quality}
    call_media = Column(JSON, default=list)
    # Monthly frequency from iNaturalist histogram (12 floats, Jan-Dec, 0-1 normalized)
    monthly_frequency = Column(JSON, nullable=True)

    # iNaturalist data
    inaturalist_id = Column(Integer, nullable=True)
    inaturalist_url = Column(String, nullable=True)

    # eBird data — JSON with taxonomy, range info, etc.
    ebird_data = Column(JSON, nullable=True)
    ebird_species_code = Column(String, nullable=True, index=True)

    # Taxonomy
    order_name = Column(String, nullable=True)
    family_name = Column(String, nullable=True)

    # Rich description — stored as JSON array of {section, text} dicts
    # Allows multi-section display with headers in the WebGUI
    description_sections = Column(JSON, nullable=True)

    # Distribution / range
    range_map_url    = Column(String, nullable=True)
    range_map_source = Column(String, nullable=True)   # "aab" | "macaulay" | "wikipedia"
    conservation_status = Column(String, nullable=True) # e.g. "LC", "NT", "VU"
    conservation_authority = Column(String, nullable=True)  # e.g. "IUCN"

    # Cornell Lab of Ornithology / All About Birds — a real, distinct
    # source from Wikipedia/iNaturalist, curated specifically for birds
    # (behavior, ID, backyard tips) rather than general-purpose. "aab_"
    # prefix throughout, matching the existing range_map_source="aab"
    # convention. aab_description, when present, is PREFERRED over the
    # Wikipedia-sourced `description` field for journal/profile use —
    # see bird_enricher.py's own comment on why. aab_cool_facts is a
    # real, distinct list of specific, citable facts (Cornell Lab's own
    # "Cool Facts" section) — genuinely different material from a
    # general description, well-suited to journal entries specifically
    # asking for a "did you know" moment.
    aab_url = Column(String, nullable=True)              # the real source page, for attribution
    aab_description = Column(Text, nullable=True)         # Cornell Lab's own "Basic Description"
    aab_cool_facts = Column(JSON, nullable=True)          # list[str] — real, specific facts
    aab_habitat = Column(String, nullable=True)           # short tag, e.g. "Open Woodlands"
    aab_food = Column(String, nullable=True)              # short tag, e.g. "Insects"
    aab_nesting = Column(String, nullable=True)           # short tag, e.g. "Tree"
    aab_behavior = Column(String, nullable=True)          # short tag, e.g. "Ground Forager"
    # Length range from AAB's "Measurements" section on the /id (not
    # /overview) page — a separate fetch from everything above, since
    # that's a genuinely different AAB page/tab. Stored as parsed floats
    # (cm, the canonical unit for the At a Glance size-comparison ruler)
    # alongside the original display text (keeps both imperial and
    # metric, and AAB's own exact wording, without re-deriving it).
    aab_length_min_cm = Column(Float, nullable=True)
    aab_length_max_cm = Column(Float, nullable=True)
    aab_length_text = Column(String, nullable=True)       # AAB's own text, e.g. "9.8-11.8 in (25-30 cm)"
    # Real conservation short-tag ("Low Concern") that the existing
    # habitat/food/nesting/behavior scraper already extracted alongside
    # those four — it was just never assigned to a field, silently
    # discarded on every enrichment pass until this was noticed.
    aab_conservation = Column(String, nullable=True)
    # Full narrative paragraphs from AAB's own separate /lifehistory
    # page — genuinely different content from the short tags above,
    # which come from /overview. Powers the Life History card.
    aab_habitat_text = Column(Text, nullable=True)
    aab_food_text = Column(Text, nullable=True)
    aab_nesting_text = Column(Text, nullable=True)
    aab_behavior_text = Column(Text, nullable=True)
    aab_conservation_text = Column(Text, nullable=True)
    aab_fetched_at = Column(DateTime, nullable=True)

    # Per-species legend for the BirdLife DataZone map, extracted directly
    # from that species' live page DOM (not a fixed global swatch list —
    # BirdLife's map has up to 12 possible categories and any given species
    # only shows the subset that applies to it). JSON list of {color, label}.
    # Populated by fetch_birdlife_range_map_full() at enrichment time and
    # re-extracted whenever the BirdLife map itself is refreshed.
    birdlife_legend  = Column(JSON, nullable=True)
    # Same idea for the AAB/Cornell map. AAB pages render their own
    # per-species legend text (e.g. "Year-round Breeding Migration
    # Nonbreeding" for Arctic Tern, only the applicable categories present)
    # — read directly from that text via _extract_aab_legend in
    # bird_enricher.py, with colors assigned from AAB's documented fixed
    # 4-color convention since the legend text isn't reliably paired with
    # its swatch element in the DOM the way BirdLife's is.
    aab_legend       = Column(JSON, nullable=True)
    # When either map source was last actually fetched (vs. just having a
    # stale cached file). Lets the eager pre-fetch step in enrich_profile()
    # skip species that were already fetched recently instead of
    # re-running Playwright on every "Refresh All Data" for every bird.
    range_maps_prefetched_at = Column(DateTime, nullable=True)

    # Additional photos beyond the primary photo
    extra_photos = Column(JSON, default=list)  # [{url, credit, thumb_url}]

    # User notes (free-text, editable from the profile page)
    notes = Column(Text, nullable=True)

    # Enrichment metadata
    last_enriched = Column(DateTime, nullable=True)
    enrichment_complete = Column(Boolean, default=False)

    # AI-written presence summary (services/profile_summary.py) — a short
    # note about THIS species' detection pattern in this specific yard
    # (when it shows up, how often), distinct from `description` above
    # (Wikipedia's general species text, not personalized at all). Cached
    # per-profile rather than regenerated on every page view, since a
    # species' overall presence pattern changes slowly — manual
    # regenerate button is the escape hatch, same pattern as the
    # Dashboard's daily journal.
    ai_presence_summary = Column(Text, nullable=True)
    ai_presence_summary_generated_at = Column(DateTime, nullable=True)
    ai_presence_summary_error = Column(String, nullable=True)

    def __repr__(self):
        return f"<BirdProfile {self.common_name}>"


class AiUsageLog(Base):
    """
    One row per successful AI provider call, across every feature that
    uses services/ai_providers.py (photo_id, call_reanalysis,
    daily_summary, profile_summary). Not logged on failure — a failed
    call didn't consume a meaningful amount of the provider's actual
    generation cost the way a completed one did, and the per-feature
    error is already visible elsewhere (AppSettings.daily_summary_error,
    BirdProfile.ai_presence_summary_error, Recording.ai_reanalysis_error)
    without needing a row here too.
    """
    __tablename__ = "ai_usage_log"
    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)   # "anthropic" | "openai" | "gemini"
    feature = Column(String, nullable=False)    # "photo_id" | "call_reanalysis" | "daily_summary" | "profile_summary"
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PushSubscription(Base):
    """
    One row per browser/device that's granted notification permission and
    subscribed via the PushManager API — the actual mechanism a PWA needs
    to receive a notification while closed or in the background (the
    existing notify_new_bird/notify_daily_digest settings only ever sent
    email; this is the real device-push counterpart).

    Tied to a user when the app is running with auth enabled, nullable
    otherwise (single-user/no-auth installs) — either way, a subscription
    represents one specific browser's push endpoint, not an account, so a
    user with the PWA installed on two phones has two rows here.
    """
    __tablename__ = "push_subscriptions"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    endpoint = Column(String, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    user_agent = Column(String, nullable=True)   # for display in Settings ("Chrome on Pixel 8", etc.) — best-effort, browser-reported
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)


class ApnsDeviceToken(Base):
    """
    One row per native iOS device (Capacitor app, not the PWA) that's
    registered for push via Apple Push Notification service — the actual
    mechanism the native app needs, since APNs and Web Push are two
    genuinely different systems (different registration flow, different
    token format, different delivery protocol) despite both ending up as
    "a push notification" from the person's point of view. See
    services/apns_push.py for why this couldn't just reuse
    PushSubscription — APNs needs one opaque device-token string, not an
    endpoint/p256dh/auth triple, and is sent over its own HTTP/2 API with
    JWT bearer auth rather than through a browser's Push API at all.

    Deliberately a separate table rather than nullable columns bolted
    onto PushSubscription — the two mechanisms don't share enough shape
    to make one shared table clearer than two focused ones, and keeping
    them separate means a bug in one send path can't touch the other's
    data.
    """
    __tablename__ = "apns_device_tokens"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    device_token = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)


class InboxNotification(Base):
    """
    One row per notification per person: what the Notifications tab lists.
    Written by services/notification_inbox.record() whenever the server
    sends a push (new bird, daily digest, test), whether or not the push
    itself reached a phone, so the tab is the full history. user_id is None
    only when sign-in is off (one shared inbox).
    """
    __tablename__ = "inbox_notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    kind = Column(String, nullable=True)        # "new-bird" | "daily-digest" | "test" | ...
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    data = Column(JSON, nullable=True)          # details shown when it's opened (daily digest)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True)


class BirdWatch(Base):
    """A species someone asked to be told about. mode "every": a push for each
    recording it's detected in (at most one per 10 minutes per species);
    "daily": one evening summary of the day's detections. See
    services/bird_watch.py."""
    __tablename__ = "bird_watches"
    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    common_name = Column(String, nullable=False)
    mode = Column(String, nullable=False, default="every")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_notified_at = Column(DateTime, nullable=True)


class AppSettings(Base):
    """
    Persistent application settings (single row, id always = 1).
    """
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, default=1)

    # Location (used for species likelihood and eBird queries)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String, nullable=True)

    # API keys (override env vars if set here)
    ebird_api_key    = Column(String, nullable=True)
    ebird_st_api_key = Column(String, nullable=True)   # eBird S&T Data Products key
    server_url       = Column(String, nullable=True)   # Public base URL e.g. https://ourchirp.com
    haikubox_serial  = Column(String, nullable=True)   # Haikubox device serial number
    haikubox_device_id = Column(String, nullable=True) # Device.id of the virtual Haikubox device row
    # Master on/off for the entire Haikubox feature — the sync loop, the
    # virtual device row, all Haikubox-sourced recordings/detections, the
    # dedicated /haikubox page, and every Haikubox-specific UI surface
    # (Devices card, bird/bat profile link, Recordings list banner,
    # Settings status panel). Off by default — having a serial number
    # configured is necessary but not sufficient; this is the actual
    # kill switch. Distinct from simply clearing haikubox_serial: turning
    # this off pauses everything without losing the configured serial, so
    # re-enabling later doesn't require re-entering it.
    haikubox_enabled = Column(Boolean, default=False)

    # Bird Buddy integration — same shape as Haikubox above (external
    # source, own polling loop, virtual Device row per synced feeder), but
    # one account can own multiple feeders, so selection is a list rather
    # than a single serial. Password stored plaintext like every other
    # credential in this app (smtp_password, ssh_password) — masked on API
    # responses, never echoed back raw.
    bird_buddy_enabled  = Column(Boolean, default=False)
    bird_buddy_email    = Column(String, nullable=True)
    bird_buddy_password = Column(String, nullable=True)
    bird_buddy_selected_feeders = Column(JSON, nullable=True)  # list[str] of feeder ids; null/empty = sync all
    bird_buddy_last_sync_at = Column(DateTime, nullable=True)
    bird_buddy_last_sync_error = Column(String, nullable=True)

    # Experimental: bat echolocation detection (see chirp-device/chirp/bat_detector.py)
    bat_detection_enabled = Column(Boolean, default=False)
    bat_detection_device_name = Column(String, nullable=True)  # substring to match ultrasonic mic name

    # Experimental, off by default: server-side bat SPECIES classification via
    # BatDetect2 (see services/bat_species_id.py). Separate toggle from plain
    # bat detection above — detection just flags "ultrasonic activity exists,"
    # this attempts (with real but limited reliability) to guess a species.
    # IMPORTANT CAVEAT users should see wherever this is surfaced: the
    # bundled BatDetect2 model is trained on 17 UK bat species only. For any
    # deployment outside the UK (Chirp's documented example deployment is
    # Massachusetts), every prediction is necessarily a best-effort guess at
    # the closest acoustic match among UK species, NOT a validated
    # identification of the actual (likely non-UK) species present. Backend
    # plumbing and storage exist so this can be tested and so results are
    # ready to use once a non-UK-trained or fine-tuned model becomes
    # available — see bat_species_id.py's module docstring for the full
    # reasoning and the plan for surfacing this in bird/bat profiles later.
    # Bat detection quality filters (pushed to managed_config on devices)
    bat_active_hours_start  = Column(String,  default="20:00")  # HH:MM local time
    bat_active_hours_end    = Column(String,  default="06:00")  # HH:MM local time
    bat_min_swept_fraction  = Column(Float,   default=0.3)      # 0–1; 0 = disabled
    bat_max_pulse_rate      = Column(Float,   default=60.0)     # pulses/sec ceiling
    bat_discard_likely_interference = Column(Boolean, default=False)  # opt-in — off means flag only, on drops the event outright before it's ever saved
    # Experimental, off by default — see AudioProcessor.remove_bat_wobble
    # docstring for the actual technique and its known tradeoff (can clip
    # a real call's content if its frequency briefly coincides with the
    # tracked interference ridge in the same STFT frame). When true, the
    # background processing pipeline pre-generates the de-wobbled cache
    # automatically for every new bat recording; it does NOT change what
    # plays by default — that stays an explicit per-recording toggle in
    # the player either way, this setting only controls whether the cache
    # is ready in advance or generated lazily on first request.
    bat_auto_remove_wobble = Column(Boolean, default=False)

    # Optional: powers AI species-confirmation on user-uploaded bird photos
    # (services/photo_id.py). Without this set, photo upload still works —
    # there's just no AI confirmation step.
    anthropic_api_key = Column(String, nullable=True)
    openai_api_key = Column(String, nullable=True)
    gemini_api_key = Column(String, nullable=True)
    # Ollama — self-hosted, no API key. A base URL (e.g. http://localhost:11434 or
    # a LAN address if it's running on a different machine) and a model name
    # (whatever the user has actually pulled locally — there's no single
    # right default the way there is for a hosted API).
    ollama_base_url = Column(String, nullable=True)
    ollama_model = Column(String, nullable=True)
    # Per-feature AI provider assignment — {"photo_id": "anthropic", "call_reanalysis": "anthropic",
    # "daily_summary": null, "profile_summary": null}. A feature key mapped to null/missing means
    # disabled — its corresponding UI (card, section, button) doesn't render at all, not an error
    # state. Keys used elsewhere: photo_id (services/photo_id.py), call_reanalysis (api/birds.py's
    # re-analysis endpoint), daily_summary (Dashboard card), profile_summary (BirdProfile page).
    ai_feature_providers = Column(JSON, nullable=True)
    # "HH:MM" 24h, interpreted in this server's configured timezone (AppSettings.timezone) —
    # when the daily summary regenerates. Experimental feature, one scheduled time for now.
    daily_summary_schedule_time = Column(String, nullable=True, default="07:00")
    # List of "HH:MM" strings for multiple generation times per day, e.g.
    # ["07:00", "17:00"]. Kept alongside the older single-time field so an
    # existing config keeps working without a migration — scheduler
    # prefers this list when set, else wraps the single value in a list.
    daily_summary_schedule_times = Column(JSON, nullable=True)
    daily_summary_text = Column(Text, nullable=True)          # cached generated content
    daily_summary_generated_at = Column(DateTime, nullable=True)

    # Scheduled Bird Profile presence-summary refresh — off by default.
    # Without this, a profile's summary only ever generates once, on
    # first view, and then sits unchanged indefinitely even as real
    # detection counts and "most recently seen" keep moving — this
    # periodically regenerates ones that have gone stale rather than
    # requiring someone to notice and hit the manual Regenerate button.
    profile_summary_auto_refresh = Column(Boolean, default=False)
    # How old a summary needs to be (in days) before it's considered
    # stale and eligible for regeneration. 7 as a default balances "stays
    # reasonably current" against not re-running this for a species whose
    # presence pattern hasn't meaningfully changed since yesterday.
    profile_summary_refresh_days = Column(Integer, default=7)
    # Local hour (0-23, interpreted in AppSettings.timezone, same as the
    # daily summary scheduler) the refresh check runs at — defaults to
    # 3am, a low-traffic hour, since this can mean many back-to-back AI
    # calls in one run for a yard with a lot of species.
    profile_summary_refresh_hour = Column(Integer, default=3)

    # Scheduled database backups — see services/backup_service.py. On by
    # default, unlike most scheduled AI features in this file: those cost
    # real money/compute per run against a hosted API or a local model,
    # so defaulting them off is the safe choice; a SQLite backup is cheap
    # (a few seconds, a few dozen MB at most for a typical install) and
    # is a pure safety net with no real downside — defaulting it on
    # matches what most people would actually want without having to
    # know to go find the toggle first.
    auto_backup_enabled = Column(Boolean, default=True)
    # Local hour (0-23, AppSettings.timezone) the nightly backup runs at
    # — same low-traffic-hour convention as the other daily scheduler loops.
    auto_backup_hour = Column(Integer, default=3)
    # How many most-recent backups to keep before pruning the oldest —
    # 14 (two weeks of dailies) balances real recovery value (a backup
    # from 3 days ago is far more useful than one from 3 minutes ago,
    # since most data-loss scenarios are noticed with some delay) against
    # unbounded disk growth from a "keep everything forever" default.
    auto_backup_retention_count = Column(Integer, default=14)
    # Status tracking, previously entirely absent — a failure was only
    # ever a server-log line (logger.warning in main.py's scheduler
    # loop), invisible from Settings with no way to tell "hasn't run
    # yet today" apart from "has been silently failing for weeks."
    # Mirrors the same last-run/error pattern already used for
    # daily_summary/weekly_summary/inat refresh elsewhere in this file.
    auto_backup_last_run_at = Column(DateTime, nullable=True)      # every attempt, success or failure
    auto_backup_last_success_at = Column(DateTime, nullable=True)  # only successful attempts
    auto_backup_last_error = Column(String, nullable=True)         # cleared on the next success

    # AI personality sliders (Settings -> AI Features) — govern the tone
    # of Daily Journal and Bird Profile Summaries. See
    # services/personality.py for how these numbers become actual prompt
    # instructions, and why the defaults below specifically (60, 50, 35)
    # matter: they're calibrated to reproduce the SAME tone the hardcoded
    # prompts used before these sliders existed, so leaving all three
    # untouched changes nothing about existing output.
    ai_personality_friendliness = Column(Integer, default=60)
    ai_personality_informational = Column(Integer, default=50)
    ai_personality_irreverence = Column(Integer, default=35)

    # A fourth slider, added later than the original three: how much
    # actual LENGTH/depth an entry gets, not just its tone. The
    # original three sliders all shape voice and content density
    # within a FIXED paragraph count (2-3 for Daily, 3-4 for Weekly,
    # hardcoded in each prompt) — none of them actually let someone ask
    # for a longer, more thorough entry with more room for real
    # teaching/explanation, which is a genuinely different axis from
    # "how fact-dense is each sentence." Default (50) is calibrated the
    # same way as the original three: it reproduces the exact paragraph
    # counts the prompts already hardcoded before this existed, so
    # leaving it untouched changes nothing about existing output.
    ai_personality_depth = Column(Integer, default=50)

    # A fifth slider: WHY vs. WHAT — whether entries actively explore
    # reasons behind what happened (ecological/behavioral speculation,
    # clearly framed as real possibility not certainty) or stick to a
    # grounded account of what was observed. Distinct from all four
    # existing sliders — see personality.py's own comment on
    # _CURIOSITY_TEXT for the full reasoning. Default (50) calibrated
    # the same way as the other four: mid-band, a real but moderate
    # amount of "why" exploration, matching what the hardcoded prompts
    # already did before any of these sliders existed.
    ai_personality_curiosity = Column(Integer, default=50)

    # Optional web search grounding for Daily/Weekly Journal — off by
    # default. Currently only does anything when the assigned provider
    # for that feature is Anthropic specifically (see ai_providers.py's
    # call_chat_completion docstring for why: Anthropic's web_search
    # tool runs server-side in a single call, while OpenAI/Gemini/Ollama
    # each have incompatible or nonexistent tool-use mechanisms that
    # would need their own separate implementation). Settings UI is
    # responsible for making that limitation visible rather than
    # implying this works with every provider.
    ai_web_search_enabled = Column(Boolean, default=False)
    # Last ~5 entries' opening lines, used only as anti-repetition context
    # for the next generation — never displayed.
    daily_summary_recent_openings = Column(JSON, nullable=True)
    daily_summary_error = Column(String, nullable=True)       # last generation error, if any — card stays hidden while this is set

    # Weekly Journal — same shape as Daily Journal above (cached text +
    # generated_at + error), plus its own independent schedule (a day of
    # week rather than daily) and the actual date range it covers, since
    # "this week" needs to be shown to the person, not just assumed.
    weekly_summary_text = Column(Text, nullable=True)
    weekly_summary_generated_at = Column(DateTime, nullable=True)
    weekly_summary_period_start = Column(DateTime, nullable=True)  # start of the actual 7-day window this entry covers
    weekly_summary_period_end = Column(DateTime, nullable=True)    # end of that window
    weekly_summary_error = Column(String, nullable=True)
    weekly_summary_recent_openings = Column(JSON, nullable=True)   # same anti-repetition purpose as daily_summary_recent_openings
    # 0=Monday .. 6=Sunday, default 6 (Sunday) — a natural "week just
    # ended, here's the wrap-up" moment, unlike picking an arbitrary
    # weekday.
    weekly_summary_schedule_day = Column(Integer, default=6)
    weekly_summary_schedule_hour = Column(Integer, default=7)

    # Display preferences
    timezone = Column(String, default="America/New_York")
    dark_mode = Column(Boolean, default=True)

    # Notification settings
    notifications_enabled = Column(Boolean, default=False)
    # VAPID key pair for Web Push — generated once on first use (see
    # services/push_notifications.py's get_or_create_vapid_keys) and
    # persisted here rather than regenerated per-request, since every
    # existing subscription is cryptographically tied to whatever public
    # key was used when the browser subscribed — rotating this would
    # silently invalidate every subscription already stored.
    vapid_public_key = Column(String, nullable=True)
    vapid_private_key = Column(String, nullable=True)

    # Native iOS push (APNs) — the counterpart to the VAPID fields above,
    # for the Capacitor app rather than the PWA. All four fields come
    # from Apple Developer's own console (Certificates, Identifiers &
    # Profiles -> Keys, for a token-based .p8 auth key — the modern
    # approach, not the older per-app push certificate that needs
    # yearly renewal). Off/unconfigured until someone actually enters
    # these — see services/apns_push.py for how they're used.
    apns_team_id = Column(String, nullable=True)     # Apple Developer Team ID (10 chars)
    apns_key_id = Column(String, nullable=True)       # the .p8 key's own Key ID (10 chars)
    apns_bundle_id = Column(String, nullable=True)    # e.g. com.joshuasalvimd.chirp — must match capacitor.config.ts's appId exactly
    apns_auth_key = Column(Text, nullable=True)       # the .p8 file's full PEM content, pasted in as text
    apns_production = Column(Boolean, default=True)   # False only for a TestFlight/dev-signed build talking to Apple's sandbox APNs environment
    # Self-hosted servers without an APNs key send iPhone pushes through a
    # relay (ourchirp.com by default); the token comes from its admin.
    push_relay_url = Column(String, nullable=True)
    push_relay_token = Column(String, nullable=True)
    notification_min_confidence = Column(Float, default=0.75)
    notification_webhook_url = Column(String, nullable=True)

    # Detection display
    min_confidence_display = Column(Float, default=0.15)
    # Per-species BirdNET thresholds {common name: score}, replacing
    # birdnet_min_confidence (or the night-caller floor) for those species.
    birdnet_species_thresholds = Column(JSON, default=dict)
    # Night callers (owls, nightjars, rails...): "night" (own floors),
    # "global" (birdnet_min_confidence) or "per_species" (see
    # night_threshold_species, {common name: True = night floor}).
    night_threshold_mode = Column(String, default="night")
    night_threshold_species = Column(JSON, default=dict)
    show_low_confidence = Column(Boolean, default=True)

    # Bat species classification — real fix for previously-dead scaffolding:
    # this column existed in database.py's migration list but was never
    # actually declared here on the model class, meaning it could never be
    # correctly read from the database at all (same bug class as
    # Device.ssh_username, fixed earlier this session) — combined with the
    # fact that services/bat_species_id.py (the module the old code tried
    # to import) never actually existed, this setting was 100% non-
    # functional regardless of what value anyone set it to. Off by default:
    # real testing this session (see app/services/bat_species_classifier.py's
    # own docstring) found the classifier can confidently misclassify pure
    # silence as a specific species, so this needs a real person's informed
    # opt-in, not silent default-on behavior.
    bat_species_id_enabled = Column(Boolean, default=False)
    # Minimum confidence (0-1) required before a classification result
    # actually overwrites a Detection's generic "Bat" label with a specific
    # species name — below this, the guess is still stored for transparency
    # (see Recording.bat_metadata) but never surfaces as an asserted
    # identification anywhere in the UI, iNaturalist submissions, or the
    # Field Guide/Life List.
    bat_species_id_min_confidence = Column(Float, default=0.75)

    # BirdNET analysis parameters
    birdnet_min_confidence = Column(Float, default=0.05)   # min confidence for analysis — lowered from 0.10 per direct request to increase sensitivity (HaikuBox catching more activity than ChirpPi)
    birdnet_overlap = Column(Float, default=2.5)           # window overlap (0-2.9) — raised from 1.5 per direct request, so a call landing right at a window boundary is less likely to be missed
    birdnet_sensitivity = Column(Float, default=1.5)       # detection sensitivity (0.5-1.5) — raised from 1.0 (the BirdNET-Analyzer default) to the max per direct request
    birdnet_lat = Column(Float, nullable=True)             # lat for species filtering (uses gps if null)
    birdnet_lon = Column(Float, nullable=True)
    birdnet_week = Column(Integer, nullable=True)          # week of year for filtering (null=auto)

    # iNaturalist token — set_at tracked so we can warn when >23 h old
    inat_api_token    = Column(String, nullable=True)
    inat_token_set_at = Column(DateTime, nullable=True)
    # Automated refresh — JWTs expire in 24h, and manually visiting
    # /users/api_token and pasting the JSON every day is real, recurring
    # friction. With these four, Chirp fetches and refreshes inat_api_token
    # itself via the OAuth2 Resource Owner Password Credentials flow: an
    # access_token from /oauth/token (using client_id/secret from a
    # one-time registered iNat OAuth app + the user's own iNat login),
    # which is then exchanged for the actual JWT at /users/api_token. See
    # services/inat_auth.py.
    inat_username = Column(String, nullable=True)
    inat_password = Column(String, nullable=True)
    inat_oauth_client_id = Column(String, nullable=True)
    inat_oauth_client_secret = Column(String, nullable=True)
    inat_auto_refresh_enabled = Column(Boolean, default=False)
    dashboard_mode_reset_v1_done = Column(Boolean, default=False)  # one-time: clears every user's dashboard_mode once so the first-login picker shows for everyone after this feature shipped, not just brand-new accounts
    inat_last_refresh_error = Column(String, nullable=True)

    # Admin-configurable Dashboard sections — which of Dashboard's cards
    # show up, set separately for the full/detailed layout and the
    # simplified one (see DASHBOARD_SECTIONS in app/api/app_settings.py
    # for the fixed list of valid section ids). Null/empty means every
    # section — the same "null = no restriction" convention already used
    # for bird_buddy_selected_feeders above — so an existing deployment
    # that's never touched this setting keeps seeing everything it
    # already did, not a dashboard that silently goes blank.
    dashboard_sections_full = Column(JSON, nullable=True)
    dashboard_sections_simplified = Column(JSON, nullable=True)

    # Auth
    auth_enabled = Column(Boolean, default=False)

    # Device API keys (JSON list of {id, name, key, created_at})
    device_api_keys = Column(JSON, default=list)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    distance_unit              = Column(String, default="mi")   # "mi" | "km"
    temperature_unit           = Column(String, default="F")    # "F" | "C"
    auto_delete_recordings_days= Column(Integer, default=0)     # 0=never
    # Independent from the hard-delete timer above — e.g. "archive after
    # 30 days, hard-delete after 365" is exactly the two-stage lifecycle
    # this pair of settings is meant to support. Archiving removes only
    # the audio file (see Recording.archived_at's docstring); it's the
    # reversible, opt-in disk-space-saving step that happens well before
    # the much harsher, permanent hard-delete.
    auto_archive_recordings_days= Column(Integer, default=0)    # 0=never
    auto_purge_min_confidence  = Column(Float, default=0.65)   # keep if device conf >= this
    auto_purge_all_device      = Column(Boolean, default=False) # if True: purge ALL when server finds 0
    # Automatically hard-delete recordings with 0 server-side detections after processing
    auto_purge_empty_recordings  = Column(Boolean, default=False)
    max_recordings_gb          = Column(Float, default=0.0)     # 0=unlimited; triggers cleanup
    share_location_with_ebird  = Column(Boolean, default=False)
    share_detections_public    = Column(Boolean, default=False)
    # Range map source visibility — JSON: {"aab": true, "geomodel": true, "birdlife": true}
    range_map_sources          = Column(JSON, nullable=True)
    range_map_source_order     = Column(JSON, nullable=True)  # list of source ids in display order

    # Recording behaviour pushed to devices via managed config
    recording_min_gap_seconds  = Column(Integer, default=10)    # min cooldown between recordings
    recording_max_duration_sec = Column(Integer, default=30)    # max recording length (seconds)
    recording_max_per_hour     = Column(Integer, default=0)     # 0=unlimited

    # Server-side storage management
    storage_compress_on_upload = Column(Boolean, default=True)  # transcode WAV on arrival (format set by storage_compress_quality)
    storage_compress_quality   = Column(String,  default="lossless")  # "lossless" (FLAC, default: re-analysis sees the same audio) | "medium" (Opus 64k) | "low" (Opus 24k)
    storage_max_dir_gb         = Column(Float,   default=0.0)   # 0=unlimited; prune oldest first
    storage_cleanup_keep_flagged = Column(Boolean, default=True) # never auto-delete labelled recs

    # Server-side re-analysis
    server_reanalyze_on_upload       = Column(Boolean, default=True)
    # When server re-analysis runs, auto-delete device detections (keep only server)
    server_reanalyze_delete_device   = Column(Boolean, default=True)

    # Show deleted/soft-deleted recordings in all counts and lists
    # False (default): only non-deleted recordings count toward stats/life list/likely birds
    # True: all detections counted regardless of recording deletion status
    show_deleted_detections          = Column(Boolean, default=False)

    # Range maps — experimental feature, off by default
    # Set to True in Settings to enable range map fetching and display
    range_maps_enabled         = Column(Boolean, default=False)

    # iNaturalist observation heatmap — experimental, off by default
    observation_heatmap_enabled = Column(Boolean, default=False)

    # Manual "Re-analyze" button on a recording's own detail page (re-runs
    # BirdNET/bat pipeline on demand) — on by default, matching existing
    # behavior before this setting existed. An admin might turn this off
    # to stop people re-triggering analysis at will, e.g. to control
    # server load or API costs, without touching the automatic pipeline
    # that runs on every new recording.
    allow_manual_reanalyze = Column(Boolean, default=True)

    # Which named color palette detection colors are assigned from —
    # see frontend/src/lib/detectionColors.js for the full palette
    # definitions and the even-spread-by-species-count assignment
    # algorithm this drives (also mirrored server-side in
    # audio_processor.py for the spectrogram's own baked-in overlay
    # colors, so the two always agree). One of: "vivid" (default),
    # "colorblind_safe", "pastel", "high_contrast".
    detection_color_palette = Column(String, default="vivid")

    # Rumble Removal mode — "auto" (default, matches existing behavior:
    # the toggle is shown and defaults on for bird recordings, still
    # user-overridable per recording), "enabled" (forced on always, no
    # toggle needed), or "disabled" (feature hidden entirely). See
    # audio_processor.py's enhance_audio() docstring for the underlying
    # filter itself (a plain high-pass, matching LiveDetect.jsx's own
    # rumble filter — not the bandpass this used to be).
    rumble_removal_mode = Column(String, default="auto")

    # AI Enhance (Experimental) — neural-network denoising via a pretrained
    # Demucs-based model (see app/services/ai_enhance.py), independent from
    # the classical bandpass+noisereduce Enhanced/Rumble removed toggles.
    # Off by default: requires torch/torchaudio (not installed by default,
    # same optional-heavy-dependency pattern as bat_species_id_enabled) and
    # downloads a ~75MB model on first use.
    ai_enhance_enabled = Column(Boolean, default=False)
    # When on, RecordingDetail.jsx defaults new (non-bat) recordings'
    # players to AI Enhance instead of Original — mirrors how
    # rumble-removal already defaults to on, but kept a separate opt-in
    # given AI Enhance's real CPU/first-use-download cost.
    ai_enhance_auto_apply = Column(Boolean, default=False)

    # Experimental detection models (Settings → Experimental; see
    # services/birdnet3.py and services/nighthawk_service.py).
    # BirdNET v3: shadow = also score each recording and show the result for
    # comparison; main = use it instead of BirdNET 2.4 in the server pass.
    exp_birdnet3_shadow = Column(Boolean, default=False)
    exp_birdnet3_main = Column(Boolean, default=False)
    exp_birdnet3_min_conf = Column(Float, default=0.5)
    # Nighthawk: stations upload night audio between these local times and the
    # server lists the night flight calls it finds (threshold in percent).
    exp_nighthawk_enabled = Column(Boolean, default=False)
    exp_nighthawk_start = Column(String, default="21:00")
    exp_nighthawk_end = Column(String, default="05:00")
    exp_nighthawk_threshold = Column(Integer, default=80)
    # Dry/wet mix passed to ai_enhance.enhance_wav() — 0.0 = fully
    # AI-denoised, 1.0 = original passthrough. Default matches
    # biodenoising's own upstream CLI default.
    ai_enhance_dry = Column(Float, default=0.1)

    # One-time migration flag — true once every existing recording's
    # spectrogram has been force-regenerated under the even-spread
    # color algorithm (see audio_processor.py's own pick_species_colors).
    # Needed because the cache-filename change that normally invalidates
    # a stale spectrogram only kicks in for a NON-default palette — a
    # recording already using the default "vivid" palette (the common
    # case) would otherwise keep serving its spectrogram from before
    # this fix, forever, since nothing about its own cache key ever
    # changed. Checked once at startup; the background sweep itself
    # sets this true when it finishes.
    spectrograms_regenerated_for_color_fix = Column(Boolean, default=False)

    # One-time (per instance), startup-triggered backfill: this instance's
    # local User table can contain accounts with no corresponding
    # registry-level GlobalUser/Membership at all — most notably every
    # user OTHER than the importing admin, when this instance's database
    # came from POST /instances/import (see that endpoint: it only ever
    # created a Membership for the person doing the import, leaving every
    # other real, carried-over local account unable to actually log in
    # and invisible to the Global Admin panel's own instance-member list,
    # which reads Membership exclusively — a real, reported mismatch
    # between the local Users page and Global Admin). Checked once at
    # startup; the background sweep itself sets this true when it finishes.
    local_users_membership_backfilled = Column(Boolean, default=False)

    # SMTP email settings
    smtp_host           = Column(String, nullable=True)
    smtp_port           = Column(Integer, default=587)
    smtp_username       = Column(String, nullable=True)
    smtp_password       = Column(String, nullable=True)
    smtp_from_address   = Column(String, nullable=True)
    smtp_use_tls        = Column(Boolean, default=True)
    admin_email         = Column(String, nullable=True)   # receives registration alerts
    notify_on_register  = Column(Boolean, default=True)   # email admin on new registration
    digest_hour         = Column(Integer, default=7)       # legacy: UTC hour the digest used to go out; read once as the email hour (scheduled_push.digest_hours)
    digest_last_sent_on = Column(String, nullable=True)    # legacy, unused
    # Daily digest send hours, local time (timezone above). From noon on a
    # digest covers that day so far; earlier, yesterday. See scheduled_push.
    digest_push_hour    = Column(Integer, nullable=True)   # default 21
    digest_email_hour   = Column(Integer, nullable=True)   # default: the legacy digest_hour converted, else 21
    digest_push_sent_on  = Column(String, nullable=True)   # day (YYYY-MM-DD) the last digest push covered
    digest_email_sent_on = Column(String, nullable=True)   # day the last digest email covered

    # Activity log — login + page-view tracking for admin visibility.
    # Deliberately minimal in scope: who did what, when, from where. No
    # request bodies, no recording/note content, no credentials ever touch
    # this table. See ActivityLog model below.
    activity_log_enabled        = Column(Boolean, default=True)
    activity_log_track_ip       = Column(Boolean, default=True)   # off = only who/when/what-page is recorded, no IP/browser string
    activity_log_retention_days = Column(Integer, default=90)     # 0 = keep forever

class SpeciesObservation(Base):
    """
    Cache of eBird recent observations for location-based likelihood.
    Refreshed periodically.
    """
    __tablename__ = "species_observations"

    id = Column(String, primary_key=True, default=new_uuid)
    ebird_species_code = Column(String, nullable=False, index=True)
    common_name = Column(String, nullable=False)
    scientific_name = Column(String, nullable=True)
    observation_date = Column(DateTime, nullable=False)
    location_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    how_many = Column(Integer, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """Admin/viewer accounts for the WebGUI."""
    __tablename__ = "users"
    id         = Column(String, primary_key=True, default=new_uuid)
    username   = Column(String, unique=True, nullable=False, index=True)
    email      = Column(String, nullable=True)
    hashed_pw  = Column(String, nullable=False)
    role       = Column(String, default="viewer")   # "admin" | "submitter" | "viewer"
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    active             = Column(Boolean, default=True)
    display_name        = Column(String, nullable=True)   # optional friendly name
    inat_api_token      = Column(String, nullable=True)   # per-user iNaturalist token (submitters)
    inat_token_set_at   = Column(DateTime, nullable=True)  # when inat_api_token was last set/refreshed — mirrors AppSettings' field, needed once auto-refresh can target a user's own token instead of only the global one
    inat_last_refresh_error = Column(String, nullable=True)  # last auto-refresh error for THIS user's token, distinct from AppSettings.inat_last_refresh_error
    inat_username = Column(String, nullable=True)  # this user's own iNat account, for auto-refreshing THEIR personal token specifically
    inat_password = Column(String, nullable=True)
    inat_oauth_client_id = Column(String, nullable=True)
    inat_oauth_client_secret = Column(String, nullable=True)
    pending_approval    = Column(Boolean, default=False)  # registration awaiting admin approval
    notify_new_bird    = Column(Boolean, default=True)   # email on new species detection
    notify_daily_digest = Column(Boolean, default=False) # daily detection digest email
    notify_daily_digest_push = Column(Boolean, default=False)  # same digest, as a push notification instead — a real, separate preference, not tied to the email one, since someone might reasonably want one channel and not the other
    notify_new_bird_push = Column(Boolean, default=True)       # push for a new species
    notify_device_offline_push = Column(Boolean, default=False)   # admins: a station stopped reporting, and when it's back
    notify_device_offline_email = Column(Boolean, default=False)
    notify_daily_journal_push = Column(Boolean, default=True)  # 6 pm push with the Daily Journal
    notify_weekly_journal_push = Column(Boolean, default=True) # Sunday noon push with the Weekly Journal
    dashboard_mode = Column(String, nullable=True)  # 'simplified' | 'detailed' | None (not yet chosen — triggers the first-login picker)
    last_seen_whats_new_version = Column(String, nullable=True)  # last app version this user has dismissed the "What's New" popup for — shows again whenever it doesn't match the current version
    photo_url            = Column(String, nullable=True)  # profile photo (uploaded or set by URL)


class ActivityLog(Base):
    """
    Login and page-view activity, for admin visibility only.

    Deliberately minimal in scope: who did what, when, and (optionally) from
    where — event_type, path, timestamp, IP, browser string. Never stores
    request bodies, recording/note content, passwords, or tokens. This is an
    audit trail in the same spirit as a login page's own server log, not a
    behavioral-tracking or analytics system.

    `user_id` is nullable (auth-disabled/single-user mode has no real user
    to attribute events to) and `username` is denormalized so history
    survives a user account being deleted later. IP/user-agent are only
    populated when AppSettings.activity_log_track_ip is true — the whole
    table is a no-op (nothing written) when AppSettings.activity_log_enabled
    is false, and old rows are purged automatically per
    AppSettings.activity_log_retention_days (0 = keep forever).
    """
    __tablename__ = "activity_log"

    id         = Column(String, primary_key=True, default=new_uuid)
    user_id    = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    username   = Column(String, nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)   # "login" | "login_failed" | "logout" | "page_view"
    path       = Column(String, nullable=True)                # route, for page_view events only
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ShareToken(Base):
    """Shareable public links for recordings (no auth required)."""
    __tablename__ = "share_tokens"
    token        = Column(String, primary_key=True)
    recording_id = Column(String, ForeignKey("recordings.id"), nullable=False, index=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    expires_at   = Column(DateTime, nullable=True)
    view_count   = Column(Integer, default=0)


class RegionalSpecies(Base):
    """
    eBird species expected in the configured region.
    Populated by background fetch when GPS + eBird key are set.
    Updated monthly.
    """
    __tablename__ = "regional_species"
    id                = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ebird_species_code= Column(String, nullable=False, index=True)
    common_name       = Column(String, nullable=False, index=True)
    scientific_name   = Column(String, nullable=True)
    family_com_name   = Column(String, nullable=True)
    order_name        = Column(String, nullable=True)
    # Frequency data: JSON list of 12 monthly frequency values (0-1)
    monthly_frequency = Column(JSON, nullable=True)
    # Current month likelihood (0-1) derived from monthly_frequency
    current_likelihood= Column(Float, default=0.0, index=True)
    # Whether this species has been locally detected
    locally_detected  = Column(Boolean, default=False, index=True)
    days_seen         = Column(Integer, default=0)   # unique days seen in last 30
    total_days        = Column(Integer, default=30)  # total unique observation days
    photo_url         = Column(String, nullable=True)
    region_code       = Column(String, nullable=True, index=True)
    fetched_at        = Column(DateTime, default=datetime.utcnow)


class Device(Base):
    """
    A paired Raspberry Pi recording device.
    Created when the Pi calls /api/v1/devices/pair with its API key.
    """
    __tablename__ = "devices"

    id         = Column(String, primary_key=True, default=new_uuid)
    name       = Column(String, nullable=False, default="Chirp Device")
    api_key_id = Column(String, nullable=True, index=True)  # FK → AppSettings.device_api_keys[].id; null for virtual devices (e.g. Haikubox, Bird Buddy)
    bird_buddy_feeder_id = Column(String, nullable=True, index=True)  # Bird Buddy feeder id, for virtual devices representing one feeder

    # Hardware reported by Pi on pairing / heartbeat
    hostname       = Column(String, nullable=True)
    ip_address     = Column(String, nullable=True)
    # Stable, cross-network IP the device reports over Tailscale/Headscale
    # (see chirp-device's own tailscale_manager.py) — separate from
    # ip_address above, which is the device's local LAN IP and only ever
    # reachable when the server and the device happen to be on the same
    # network. Populated the same way, via heartbeat; null whenever
    # Tailscale isn't installed, isn't enabled, or hasn't connected yet.
    # The SSH terminal and any other direct-to-device feature try this as
    # a fallback (or an explicit alternative) when the local IP isn't
    # reachable.
    tailscale_ip   = Column(String, nullable=True)
    platform       = Column(String, nullable=True)   # "Raspberry Pi 5 Model B Rev 1.0"
    os_version     = Column(String, nullable=True)
    coral_present  = Column(Boolean, default=False)
    mic_count      = Column(Integer, default=1)
    mic_names      = Column(JSON, default=list)       # ["Blue Yeti USB", "USB Microphone"]
    birdnet_backend= Column(String, default="cpu")    # "cpu" | "coral"
    coral_form_factor= Column(String, nullable=True)   # "m2_pcie" | "usb" | ""
    coral_model_present = Column(Boolean, nullable=True)  # compiled BirdNET EdgeTPU model present (None = older device)
    connect_via    = Column(String, nullable=True)      # "auto" | "lan" | "tailscale" — how the server reaches the device (services/device_net.py)
    device_version = Column(String, nullable=True)    # chirp-device software version
    bat_status     = Column(JSON, nullable=True)       # last-reported BatDetector.get_status() — level_db, active_hours, pulses_seen, events_fired, last_heartbeat_age_s

    # SSH username for the Devices page's "push credentials" / SSH terminal
    # features — remembered per device so it doesn't need re-entering every
    # time. This was previously set via plain attribute access
    # (device.ssh_username = ...) without being declared as a Column here,
    # which means SQLAlchemy treated it as a transient Python attribute that
    # was never actually written to the database — it looked like it saved
    # (the in-memory object held the value) but was silently gone again
    # after any server restart. Declaring it here is the actual fix; the
    # column already existed in _migrate_columns()'s pending list for
    # existing databases.
    ssh_username   = Column(String, nullable=True)

    # SSH password — opt-in, admin-only to set (PUT /{id}/ssh-credentials),
    # stored plaintext like every other credential in this app (smtp_password,
    # device API keys) since there's no encryption-at-rest layer anywhere in
    # this codebase to be consistent with — masked in API responses the same
    # way smtp_password is (_mask_key), never echoed back raw. An earlier
    # version of this comment said passwords are "never persisted, by
    # design" — that was a real, deliberate choice at the time, explicitly
    # superseded now: convenience (not re-entering it for every mic check on
    # a single-admin home server) was judged to outweigh the tradeoff for
    # this specific use case. Key-based SSH auth is still tried first
    # everywhere this is used; this is only ever a fallback.
    ssh_password   = Column(String, nullable=True)

    @property
    def connect_address(self):
        """Address the server uses to reach this device right now."""
        from .services.device_net import device_address
        try:
            return device_address(self)
        except Exception:
            return self.ip_address

    @property
    def ssh_password_set(self) -> bool:
        """
        Computed, not a column — lets DeviceOut (response_model, populated
        via from_attributes) expose "is a password saved" without ever
        including the actual ssh_password value in any API response. Plain
        Python properties on a SQLAlchemy model are read correctly by
        Pydantic's from_attributes the same way real columns are.
        """
        return bool(self.ssh_password)

    # Connectivity
    last_seen = Column(DateTime, nullable=True, index=True)
    status    = Column(String, default="never_connected")  # "online" | "offline" | "never_connected"
    offline_since = Column(DateTime, nullable=True)   # last heartbeat before an announced outage (services/device_alerts.py)

    # Server-managed config (deep-merged onto device's local config.yaml)
    # The device polls this and applies it at runtime without requiring a restart.
    managed_config = Column(JSON, default=dict)

    # Config version handshake — server increments config_version when config changes.
    # Device reports config_applied_version in heartbeats to confirm receipt.
    config_version         = Column(Integer, default=0)
    config_applied_version = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    def is_online(self) -> bool:
        """
        Whether this device has reported in recently enough to be
        considered online. The staleness window must match how often this
        device TYPE actually reports in — a real Pi heartbeats roughly
        every 30s (see chirp-device/config.yaml's heartbeat_interval_seconds
        default), so a short window correctly flags it offline soon after
        it actually goes down. A virtual Haikubox or Bird Buddy device only
        updates last_seen once per sync cycle (every 15 minutes — see
        services/haikubox_sync.py and services/bird_buddy_sync.py's
        POLL_INTERVAL_SECONDS), so applying that same short window to
        either of them meant it was computed as "offline" for roughly 13 of
        every 15 minutes even when sync was working completely normally —
        not a real connectivity problem, just a mismatched threshold.
        list_devices() recomputes and persists this on every page load, so
        the bug was visible essentially every time anyone looked at the
        Devices page. (Bird Buddy was added after this fix originally
        shipped for Haikubox only — same bug, same fix, just missed on the
        newer integration until now.)
        """
        if not self.last_seen:
            return False
        now = datetime.utcnow()
        delta = (now - self.last_seen).total_seconds()
        if self.platform in ("Haikubox", "Bird Buddy") or self.birdnet_backend in ("haikubox", "bird_buddy"):
            # 15-minute sync interval — allow roughly 2 missed cycles
            # (30 min) before considering it actually offline, the same
            # ~4x-the-interval grace period a real Pi's 120s/30s ratio
            # already gives it.
            return delta < 1800
        return delta < 120  # 2-minute heartbeat window for real Pi devices

class Comment(Base):
    """
    Shared comment/note attached to a bird profile or recording.
    All authenticated users can post; visible to everyone (comment board model).
    """
    __tablename__ = "comments"

    id         = Column(String, primary_key=True, default=new_uuid)
    # One of these is set, the other is None
    bird_profile_id = Column(String, ForeignKey("bird_profiles.id"), nullable=True, index=True)
    recording_id    = Column(String, ForeignKey("recordings.id"),    nullable=True, index=True)

    author    = Column(String, nullable=False, default="Anonymous")  # username at time of post
    body      = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    # No default here, deliberately — reported directly: every comment
    # showed "(edited)" immediately on posting, never edited at all.
    # Root cause was here: with default=datetime.utcnow on BOTH columns,
    # SQLAlchemy calls each column's default callable separately at
    # INSERT time, so created_at and updated_at end up as two
    # independent datetime.utcnow() calls a few microseconds apart —
    # never equal, even for a brand-new comment. The frontend's own
    # "was this edited" check (Comments.jsx) compares updated_at !==
    # created_at, which was therefore true for every comment ever
    # posted. Leaving updated_at unset (None) until a genuine edit
    # triggers onupdate is the fix — the API's own comment
    # serializers (birds.py/recordings.py _comment_out) already guard
    # updated_at with "if c.updated_at else None", so this doesn't
    # introduce a null-handling bug either.
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # soft-delete


class BatActivity(Base):
    """
    A detected bat-echolocation activity event, uploaded by the device's
    experimental BatDetector (chirp-device/chirp/bat_detector.py).

    Note this is fundamentally different from Recording/Detection: there is
    no species identification (no bundled classifier exists for this), just
    pulse-train activity stats. raw_clip_path stores the audio at its true
    native high sample rate (inaudible/near-silent to humans); the enhanced
    (downshifted) version is generated on demand and cached, mirroring the
    bird audio-enhancement pattern in services/audio_processor.py.
    """
    __tablename__ = "bat_activity"

    id = Column(String, primary_key=True, default=new_uuid)
    device_id = Column(String, ForeignKey("devices.id"), nullable=True, index=True)

    started_at = Column(DateTime, nullable=False, index=True)
    ended_at = Column(DateTime, nullable=False)
    pulse_count = Column(Integer, nullable=False)
    peak_freq_hz = Column(Float, nullable=False)
    mean_pulse_duration_ms = Column(Float, nullable=True)
    swept_fraction = Column(Float, nullable=True)   # 0-1, fraction of pulses showing an FM sweep
    sample_rate = Column(Integer, nullable=False)    # true native sample rate of raw_clip_path

    raw_clip_path = Column(String, nullable=True)    # native-rate WAV, inaudible/near-silent to humans
    enhanced_clip_path = Column(String, nullable=True)  # cached downshifted WAV (generated on demand)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class MonthlyDiversityStats(Base):
    """
    One persisted row per CALENDAR MONTH of species-diversity metrics
    (Statistics page's Diversity Trend chart — see api/recordings.py's
    diversity_trend()). Written once a month is fully in the past and
    its numbers can never change again; the current, still-accumulating
    month is always computed live instead of read from here.

    Exists so "all time" (potentially years of months) doesn't mean
    re-scanning every Detection row on every request — the on-the-fly
    per-month query is cheap for the ~12 months the chart used to be
    hardcoded to, but that cost multiplies with however many months a
    longer window asks for. A finished month's own numbers are fixed
    forever, so computing each one once and storing it turns "all time"
    into a handful of missing-row backfills (once) plus cheap primary-key
    reads (every time after) rather than the full scan repeating on
    every single request, for every session, forever.

    Purely a cache in the sense that it's fully reconstructable from
    Detection/Recording data — deleting this table and letting it
    backfill again would reproduce identical numbers, given identical
    underlying data. It is NOT purely a cache in the sense that it's
    long-lived (kept indefinitely, not TTL'd like statistics_cache) and
    intentionally survives a restart, both because it's expensive enough
    to be worth not recomputing and because a manual bulk-delete of very
    old recordings later shouldn't silently rewrite a month's already-
    published historical diversity numbers out from under someone.
    """
    __tablename__ = "monthly_diversity_stats"

    month = Column(String, primary_key=True)  # "YYYY-MM", local calendar month
    species_richness = Column(Integer, nullable=False)
    total_detections = Column(Integer, nullable=False)
    shannon_index = Column(Float, nullable=True)
    simpson_index = Column(Float, nullable=True)
    evenness = Column(Float, nullable=True)
    computed_at = Column(DateTime, default=datetime.utcnow)


class NearMiss(Base):
    """A night caller's best window that scored but wasn't kept, one row per
    species per analysis (see birdnet_pass._near_misses). Used to set
    per-species thresholds from what BirdNET almost reported."""
    __tablename__ = "near_misses"

    id = Column(String, primary_key=True, default=new_uuid)
    recording_id = Column(String, ForeignKey("recordings.id"), nullable=False, index=True)
    common_name = Column(String, nullable=False, index=True)
    scientific_name = Column(String, nullable=True)
    label = Column(String, nullable=True)
    confidence = Column(Float, nullable=False)
    start_time = Column(Float, default=0.0)
    end_time = Column(Float, default=3.0)
    threshold = Column(Float, nullable=True)   # what it needed then
    reason = Column(String, nullable=True)     # below threshold | no hoot | no hoot at its pitch | outscored by another owl
    band = Column(String, nullable=True)       # "full" or "band" (200-2000 Hz copy)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ReanalysisRun(Base):
    """One Re-analyze of one recording: the detections before it (every
    column, so Undo can restore them), what changed, and the settings used."""
    __tablename__ = "reanalysis_runs"

    id = Column(String, primary_key=True, default=new_uuid)
    recording_id = Column(String, ForeignKey("recordings.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")   # running | done | error | undone
    use_ai_enhance = Column(Boolean, default=False)
    min_conf = Column(Float, nullable=True)
    before = Column(JSON, default=list)           # detection rows before the run
    changes = Column(JSON, default=list)          # [{species, change, was, now, reason}]
    summary = Column(String, nullable=True)
    undone_at = Column(DateTime, nullable=True)


class ContentReport(Base):
    """A note (comment) someone reported to the site's admins."""
    __tablename__ = "content_reports"
    id          = Column(String, primary_key=True, default=new_uuid)
    comment_id  = Column(String, index=True, nullable=False)
    reporter    = Column(String, nullable=False)
    author      = Column(String, nullable=True)
    reason      = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)


class ContentBlock(Base):
    """Someone whose notes a person chose not to see."""
    __tablename__ = "content_blocks"
    id             = Column(String, primary_key=True, default=new_uuid)
    user_id        = Column(String, index=True, nullable=False)
    blocked_author = Column(String, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)



class ShadowDetection(Base):
    """A detection from an experimental model run alongside the main pass
    (BirdNET v3 shadow mode): shown for comparison, never used for alerts,
    the life list or profiles."""
    __tablename__ = "shadow_detections"

    id = Column(String, primary_key=True, default=new_uuid)
    recording_id = Column(String, ForeignKey("recordings.id"), nullable=False, index=True)
    model = Column(String, nullable=False, default="birdnet3", index=True)
    common_name = Column(String, nullable=False, index=True)
    scientific_name = Column(String, nullable=True)
    label = Column(String, nullable=True)
    confidence = Column(Float, nullable=False)
    start_time = Column(Float, default=0.0)
    end_time = Column(Float, default=5.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class NightChunk(Base):
    """One stretch of night audio a station uploaded for Nighthawk
    (services/nighthawk_service.py). The audio is deleted once analyzed;
    each call found keeps a short clip (FlightCall)."""
    __tablename__ = "night_chunks"

    id = Column(String, primary_key=True, default=new_uuid)
    device_id = Column(String, nullable=True, index=True)
    started_at = Column(DateTime, nullable=False, index=True)      # UTC
    duration_seconds = Column(Float, default=0.0)
    sample_rate = Column(Integer, nullable=True)
    path = Column(String, nullable=True)                           # cleared once deleted
    status = Column(String, default="pending", index=True)          # pending | processing | done | error
    error = Column(String, nullable=True)
    calls = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)


class FlightCall(Base):
    """A night flight call Nighthawk found. Nighthawk names a species when
    it is confident and otherwise a sound group (e.g. ZEEP), family or
    order: `category` is the most specific of those, `level` which one."""
    __tablename__ = "flight_calls"

    id = Column(String, primary_key=True, default=new_uuid)
    chunk_id = Column(String, ForeignKey("night_chunks.id"), nullable=True, index=True)
    device_id = Column(String, nullable=True, index=True)
    detected_at = Column(DateTime, nullable=False, index=True)     # UTC
    night = Column(String, nullable=False, index=True)              # local date the night began, YYYY-MM-DD
    level = Column(String, nullable=False)                          # species | group | family | order
    category = Column(String, nullable=False, index=True)           # eBird code, group code, family or order
    common_name = Column(String, nullable=True)                     # species only
    scientific_name = Column(String, nullable=True)
    family = Column(String, nullable=True)
    order = Column(String, nullable=True)
    group = Column(String, nullable=True)
    prob = Column(Float, nullable=False)
    prob_species = Column(Float, nullable=True)
    duration = Column(Float, default=0.0)
    clip_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
