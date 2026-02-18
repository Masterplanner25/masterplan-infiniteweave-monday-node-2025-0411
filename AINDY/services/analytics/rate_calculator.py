def calculate_rates(data: dict):

    visibility = data.get("passive_visibility", 0)
    interactions = data.get("interaction_volume", 0)
    attention = data.get("deep_attention_units", 0)
    intent = data.get("intent_signals", 0)
    conversions = data.get("conversion_events", 0)
    reach = data.get("unique_reach", 0)

    return {
        "interaction_rate": interactions / visibility if visibility else 0,
        "attention_rate": attention / visibility if visibility else 0,
        "intent_rate": intent / reach if reach else 0,
        "conversion_rate": conversions / intent if intent else 0,
        "discovery_ratio": data.get("active_discovery", 0) / visibility if visibility else 0,
        "growth_rate": data.get("growth_velocity", 0) / reach if reach else 0,
    }
