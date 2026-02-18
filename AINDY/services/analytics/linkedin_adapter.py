from services.analytics.rate_calculator import calculate_rates


def linkedin_adapter(raw):

    interaction_volume = raw.likes + raw.comments + raw.shares
    intent_signals = raw.profile_views + raw.link_clicks

    canonical_data = {
        "masterplan_id": raw.masterplan_id,
        "platform": "linkedin",
        "scope_type": raw.scope_type,
        "scope_id": raw.scope_id,
        "period_type": raw.period_type,
        "period_start": raw.period_start,
        "period_end": raw.period_end,

        "passive_visibility": raw.impressions,
        "active_discovery": raw.search_appearances,
        "unique_reach": raw.members_reached,
        "interaction_volume": interaction_volume,
        "deep_attention_units": raw.watch_time_minutes,
        "intent_signals": intent_signals,
        "conversion_events": raw.follows,
        "growth_velocity": raw.new_followers,
        "audience_quality_score": raw.audience_quality_score,
    }

    canonical_data.update(calculate_rates(canonical_data))

    return canonical_data
