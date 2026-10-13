/**
 * Chirp — shared UI constants
 *
 * Single source of truth for all default values shown in the UI.
 * Import from here instead of hardcoding numbers in components.
 */

export const DEFAULTS = {
  // Detection
  MIN_CONFIDENCE_DISPLAY:     0.15,   // hide detections below this in the UI
  BIRDNET_MIN_CONFIDENCE:     0.10,   // server BirdNET minimum confidence
  BIRDNET_OVERLAP:            1.5,    // analysis window overlap (0–2.9 s)
  BIRDNET_SENSITIVITY:        1.0,    // detection sensitivity (0.5–1.5)

  // Auto-purge
  AUTO_PURGE_MIN_CONFIDENCE:  0.65,   // keep recording if device conf >= this

  // Notifications
  NOTIFICATION_MIN_CONFIDENCE: 0.75,  // only notify above this confidence

  // Storage
  AUTO_DELETE_DAYS:           0,      // 0 = never auto-delete
  AUTO_ARCHIVE_DAYS:          0,      // 0 = never auto-archive
  MAX_RECORDINGS_GB:          0,      // 0 = unlimited

  // Recording device defaults
  RECORDING_MIN_GAP_SECONDS:  10,
  RECORDING_MAX_DURATION_SEC: 30,
  RECORDING_MAX_PER_HOUR:     0,      // 0 = unlimited

  // Location
  LOCATION_RADIUS_KM:         50,

  // SMTP
  SMTP_PORT:                  587,
}

/** Confidence level labels (matches backend likelihood scoring) */
export const CONFIDENCE_LABELS = {
  VERY_LIKELY: 0.70,
  LIKELY:      0.40,
  POSSIBLE:    0.15,
}

/** Distance unit options */
export const DISTANCE_UNITS = [
  { value: 'mi', label: 'Miles' },
  { value: 'km', label: 'Kilometres' },
]

/** Temperature unit options */
export const TEMP_UNITS = [
  { value: 'F', label: '°F' },
  { value: 'C', label: '°C' },
]
