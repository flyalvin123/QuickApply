from __future__ import annotations

import hashlib
import json
from typing import Any

SOURCE_SITE_PRIORITY = {
    "linkedin": 0,
    "indeed": 1,
}


def normalize_identity_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_source_site(source_site: str) -> str:
    return normalize_identity_text(source_site)


def source_site_display_name(source_site: str) -> str:
    normalized = normalize_source_site(source_site)
    if normalized == "linkedin":
        return "LinkedIn"
    if normalized == "indeed":
        return "Indeed"
    if not normalized:
        return "Unknown"
    return normalized.replace("_", " ").title()


def source_site_priority(source_site: str) -> int:
    normalized = normalize_source_site(source_site)
    return SOURCE_SITE_PRIORITY.get(normalized, 99)


def build_job_dedupe_key(
    *,
    title: str,
    company: str,
    location_text: str = "",
    city: str = "",
    state: str = "",
    country: str = "",
) -> str:
    _ = location_text, city, state, country
    # 中文注释：用户要求“同一职位 + 同一公司”跨来源、跨地点也只保留一条，
    # 所以这里的合并 key 明确只看 title 和 company，不再把地点混进去。
    stable_text = "|".join(
        [
            normalize_identity_text(title),
            normalize_identity_text(company),
        ]
    )
    return hashlib.sha1(stable_text.encode("utf-8")).hexdigest()


def make_source_variant(source_site: str, job_url: str) -> dict[str, str]:
    return {
        "site": normalize_source_site(source_site),
        "url": " ".join(str(job_url or "").split()),
    }


def _source_variant_key(variant: dict[str, Any]) -> tuple[str, str]:
    return (
        normalize_source_site(variant.get("site", "")),
        " ".join(str(variant.get("url", "") or "").split()),
    )


def load_source_variants(
    raw_value: str | None,
    *,
    fallback_site: str = "",
    fallback_url: str = "",
) -> list[dict[str, str]]:
    variants: list[dict[str, str]] = []
    try:
        parsed = json.loads(raw_value or "[]")
    except json.JSONDecodeError:
        parsed = []

    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            variant = make_source_variant(
                str(item.get("site", "")),
                str(item.get("url", "")),
            )
            if variant["site"] or variant["url"]:
                variants.append(variant)

    fallback_variant = make_source_variant(fallback_site, fallback_url)
    if fallback_variant["site"] or fallback_variant["url"]:
        variants.append(fallback_variant)
    return sort_and_dedup_source_variants(variants)


def sort_and_dedup_source_variants(
    variants: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for variant in variants:
        normalized = make_source_variant(
            str(variant.get("site", "")),
            str(variant.get("url", "")),
        )
        variant_key = _source_variant_key(normalized)
        if variant_key in seen or not any(variant_key):
            continue
        seen.add(variant_key)
        deduped.append(normalized)
    return sorted(
        deduped,
        key=lambda item: (
            source_site_priority(item.get("site", "")),
            source_site_display_name(item.get("site", "")),
            item.get("url", ""),
        ),
    )


def merge_source_variants(*collections: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, str]]:
    merged: list[dict[str, Any]] = []
    for collection in collections:
        merged.extend(collection)
    return sort_and_dedup_source_variants(merged)


def dump_source_variants(variants: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> str:
    return json.dumps(sort_and_dedup_source_variants(list(variants)), ensure_ascii=False)


def pick_primary_source_variant(
    variants: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, str]:
    ordered = sort_and_dedup_source_variants(list(variants))
    if not ordered:
        return {"site": "", "url": ""}
    for variant in ordered:
        if variant.get("url"):
            return variant
    return ordered[0]


def labeled_source_variants(
    raw_value: str | None,
    *,
    fallback_site: str = "",
    fallback_url: str = "",
) -> list[dict[str, str]]:
    variants = load_source_variants(
        raw_value,
        fallback_site=fallback_site,
        fallback_url=fallback_url,
    )
    total_by_site: dict[str, int] = {}
    for item in variants:
        site = item.get("site", "")
        total_by_site[site] = total_by_site.get(site, 0) + 1

    seen_by_site: dict[str, int] = {}
    labeled: list[dict[str, str]] = []
    for item in variants:
        site = item.get("site", "")
        display_name = source_site_display_name(site)
        seen_by_site[site] = seen_by_site.get(site, 0) + 1
        label = display_name
        if total_by_site.get(site, 0) > 1:
            label = f"{display_name}{seen_by_site[site]}"
        labeled.append(
            {
                "site": site,
                "url": item.get("url", ""),
                "label": label,
                "display_site": display_name,
            }
        )
    return labeled
