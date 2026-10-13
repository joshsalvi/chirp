"""
Chirp Server — Species Likelihood Service
Combines eBird recent observations with local detection history
to rank bird species by likelihood at a given location.
"""
import logging
import math
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import BirdProfile, Detection, Recording

logger = logging.getLogger("chirp.likelihood")

# Haversine distance threshold for "nearby" eBird observations
NEARBY_KM = 50


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class SpeciesLikelihoodService:
    """
    Ranks bird species by likelihood of appearing at a given location.

    Scoring components (weighted sum → 0-1):
      40% — eBird recent observations (last 30 days, within 50km)
      40% — Local Chirp detection history (last 90 days)
      20% — Seasonal factor (month-of-year from eBird if available)
    """

    def __init__(self, db: Session, ebird_api_key: Optional[str]):
        self.db = db
        self.ebird_api_key = ebird_api_key

    def get_likely_species(
        self, lat: Optional[float], lon: Optional[float], limit: int = 30
    ) -> List[Dict]:
        """
        Return a ranked list of likely species for the location.
        """
        if lat is None or lon is None:
            return self._local_only_ranking(limit)

        # 1. Get eBird recent observations
        ebird_species = self._get_ebird_recent(lat, lon)

        # 2. Get local detection history
        local_species = self._get_local_detections()

        # 3. Merge and score
        all_species = {}

        for species_code, obs_data in ebird_species.items():
            key = obs_data["common_name"]
            all_species[key] = {
                "common_name": obs_data["common_name"],
                "scientific_name": obs_data.get("scientific_name"),
                "ebird_species_code": species_code,
                "ebird_count": obs_data.get("count", 1),
                "ebird_obs_count": obs_data.get("num_observations", 0),
                "ebird_distance_km": obs_data.get("min_distance_km"),
                "local_count": 0,
                "last_seen_local": None,
                "label": None,
                "photo_url": None,
                "has_local_photo": False,
            }

        for common_name, local_data in local_species.items():
            if common_name not in all_species:
                all_species[common_name] = {
                    "common_name": common_name,
                    "scientific_name": local_data.get("scientific_name"),
                    "ebird_species_code": None,
                    "ebird_count": 0,
                    "ebird_obs_count": 0,
                    "ebird_distance_km": None,
                    "local_count": local_data["count"],
                    "last_seen_local": local_data["last_seen"],
                    "label": local_data.get("label"),
                    "photo_url": None,
                    "has_local_photo": False,
                }
            else:
                all_species[common_name].update({
                    "local_count": local_data["count"],
                    "last_seen_local": local_data["last_seen"],
                    "label": local_data.get("label"),
                })

        # 4. Fetch profile photos — single batched query instead of one
        # query per species. This loop previously issued one
        # db.query(BirdProfile).filter(common_name == X).first() per
        # species in all_species, which for a typical regional checklist
        # (100-300+ species, merged with local detections) meant 100-300+
        # round-trips to the database on every single load of the Likely
        # Species page. BirdProfile.common_name is indexed, so a single
        # IN (...) query covers every name in one round-trip; results are
        # then looked up from an in-memory dict keyed the same way the
        # per-name queries were, so the logic below is unchanged.
        all_names_list = list(all_species.keys())
        profiles_by_name = {}
        if all_names_list:
            for profile in (self.db.query(BirdProfile)
                             .filter(BirdProfile.common_name.in_(all_names_list))
                             .all()):
                profiles_by_name[profile.common_name] = profile

        for common_name in all_species:
            profile = profiles_by_name.get(common_name)
            if profile:
                if profile.photo_path and os.path.exists(profile.photo_path):
                    all_species[common_name]["photo_url"] = f"/api/v1/birds/{profile.id}/photo"
                    all_species[common_name]["has_local_photo"] = True
                elif profile.photo_url:
                    all_species[common_name]["photo_url"] = profile.photo_url
                if not all_species[common_name]["label"]:
                    all_species[common_name]["label"] = profile.label

        # 5. Compute scores
        max_ebird = max((s["ebird_obs_count"] for s in all_species.values()), default=1)
        max_local = max((s["local_count"] for s in all_species.values()), default=1)

        results = []
        for common_name, data in all_species.items():
            ebird_score = (data["ebird_obs_count"] / max(max_ebird, 1)) * 0.5

            local_score = (data["local_count"] / max(max_local, 1)) * 0.4

            # Distance decay for eBird observations
            dist = data.get("ebird_distance_km")
            dist_factor = 1.0 if dist is None else max(0.1, 1.0 - dist / NEARBY_KM)

            # Recency bonus for local detections
            recency = 0.0
            last_seen = data.get("last_seen_local")
            if last_seen:
                if isinstance(last_seen, str):
                    try:
                        from dateutil.parser import parse
                        last_seen = parse(last_seen)
                    except Exception:
                        last_seen = None
                if last_seen:
                    days_ago = (datetime.utcnow() - last_seen).days
                    recency = max(0, (90 - days_ago) / 90) * 0.1

            score = min(1.0, ebird_score * dist_factor + local_score + recency)

            likelihood_label = (
                "Very Likely" if score >= 0.7 else
                "Likely" if score >= 0.4 else
                "Possible" if score >= 0.15 else
                "Rare"
            )

            results.append({
                **data,
                "detection_count": data["local_count"],
                "last_seen": data["last_seen_local"].isoformat() if isinstance(data.get("last_seen_local"), datetime) else data.get("last_seen_local"),
                "likelihood_score": round(score, 4),
                "likelihood_label": likelihood_label,
            })

        results.sort(key=lambda x: x["likelihood_score"], reverse=True)
        return results[:limit]

    def _get_ebird_recent(self, lat: float, lon: float) -> Dict[str, Dict]:
        """Fetch recent eBird observations within NEARBY_KM km."""
        if not self.ebird_api_key:
            return {}
        try:
            resp = httpx.get(
                "https://api.ebird.org/v2/data/obs/geo/recent",
                params={
                    "lat": lat,
                    "lng": lon,
                    "dist": NEARBY_KM,
                    "back": 30,
                    "maxResults": 200,
                    "fmt": "json",
                },
                headers={"X-eBirdApiToken": self.ebird_api_key},
                timeout=15,
            )
            if resp.status_code != 200:
                return {}

            obs_list = resp.json()
            species_map = {}
            for obs in obs_list:
                code = obs.get("speciesCode", "")
                name = obs.get("comName", "")
                if not code or not name:
                    continue

                obs_lat = obs.get("lat")
                obs_lon = obs.get("lng")
                dist = None
                if obs_lat and obs_lon:
                    dist = haversine_km(lat, lon, obs_lat, obs_lon)

                if code not in species_map:
                    species_map[code] = {
                        "common_name": name,
                        "scientific_name": obs.get("sciName"),
                        "count": obs.get("howMany", 1) or 1,
                        "num_observations": 1,
                        "min_distance_km": dist,
                    }
                else:
                    species_map[code]["num_observations"] += 1
                    species_map[code]["count"] += obs.get("howMany", 1) or 1
                    if dist and (species_map[code]["min_distance_km"] is None or
                                 dist < species_map[code]["min_distance_km"]):
                        species_map[code]["min_distance_km"] = dist

            return species_map
        except Exception as e:
            logger.warning("eBird fetch failed: %s", e)
            return {}

    def _get_local_detections(self, days: int = 90) -> Dict[str, Dict]:
        """
        Get local (Chirp device) detection counts from last N days.

        Excludes Haikubox-sourced rows and soft-deleted recordings: this
        is specifically meant to represent the Pi's own sensor history
        for the species-likelihood score, not Haikubox's cloud
        detections (mixing the two would inflate a species' likelihood
        score and could incorrectly push its Field Guide classification
        up to "Likely"/"Very Likely" based on cloud data the device
        itself never actually heard) — see get_life_list's matching
        comment in api/birds.py for the same reasoning applied to the
        life list. Disabling Haikubox does not delete the underlying
        Recording rows (only hides them from the recordings-list
        endpoints), so this exclusion has to be explicit here rather
        than relying on the toggle state.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = (
            self.db.query(
                Detection.common_name,
                Detection.scientific_name,
                Detection.label,
                func.count(Detection.id).label("count"),
                func.max(Recording.trigger_timestamp).label("last_seen"),
            )
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(Recording.trigger_timestamp >= cutoff)
            .filter(Recording.deleted_at.is_(None))
            .filter(Recording.haikubox_detection_id.is_(None))
            .group_by(Detection.common_name)
            .all()
        )
        return {
            row.common_name: {
                "scientific_name": row.scientific_name,
                "label": row.label,
                "count": row.count,
                "last_seen": row.last_seen,
            }
            for row in rows
        }

    def _local_only_ranking(self, limit: int) -> List[Dict]:
        """Fall back to local detection history only (no GPS set)."""
        local = self._get_local_detections()
        results = []
        for name, data in local.items():
            results.append({
                "common_name": name,
                "scientific_name": data.get("scientific_name"),
                "ebird_species_code": None,
                "label": data.get("label"),
                "detection_count": data["count"],
                "last_seen": data["last_seen"].isoformat() if data.get("last_seen") else None,
                "likelihood_score": min(1.0, data["count"] / 20),
                "likelihood_label": "Detected",
                "photo_url": None,
                "has_local_photo": False,
            })
        results.sort(key=lambda x: x["likelihood_score"], reverse=True)
        return results[:limit]
