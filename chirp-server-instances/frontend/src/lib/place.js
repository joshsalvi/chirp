// A site's location for display: the town and region without the house
// number, street, county or postcode, so the Field Guide doesn't show a
// home address to every member. "185, Woodland Street, South Natick,
// Natick, Middlesex County, Massachusetts, 01760, United States" →
// "South Natick, Natick, Massachusetts".
const STREET = /\b(street|st|road|rd|avenue|ave|lane|ln|drive|dr|way|court|ct|place|pl|boulevard|blvd|circle|cir|terrace|ter|highway|hwy|route|rte|parkway|pkwy|trail)\b\.?$/i

export function publicPlace(name) {
  if (!name) return name
  const parts = String(name).split(',').map(p => p.trim()).filter(Boolean)
  if (parts.length < 3) return parts.filter(p => !/\d/.test(p) || !STREET.test(p)).join(', ')
  const kept = parts.filter(p =>
    !/^\d+[a-z]?$/i.test(p) &&            // house number
    !/^\d{4,6}(-\d{4})?$/.test(p) &&       // postcode
    !STREET.test(p) &&                     // street
    !/^\d+\s/.test(p) &&                   // "185 Woodland Street"
    !/\bcounty\b/i.test(p) &&
    !/^(united states|usa|us)$/i.test(p))
  return kept.join(', ') || parts[parts.length - 1]
}
