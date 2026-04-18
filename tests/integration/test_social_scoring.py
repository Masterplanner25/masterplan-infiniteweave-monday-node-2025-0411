import pytest

from apps.social.models.social_models import SocialPost, TrustTier
from apps.social.routes.social_router import _compute_visibility_score


def test_visibility_score_trust_tier_weighting():
    base_post = SocialPost(
        author_id="u1",
        author_username="alpha",
        content="test",
        trust_tier_required=TrustTier.OBSERVER,
        likes=0,
        boosts=0,
        comments_count=0,
    )
    inner_post = SocialPost(
        author_id="u1",
        author_username="alpha",
        content="test",
        trust_tier_required=TrustTier.INNER_CIRCLE,
        likes=0,
        boosts=0,
        comments_count=0,
    )
    assert _compute_visibility_score(inner_post) > _compute_visibility_score(base_post)


def test_visibility_score_engagement_boosts_score():
    low_engagement = SocialPost(
        author_id="u1",
        author_username="alpha",
        content="test",
        trust_tier_required=TrustTier.OBSERVER,
        likes=0,
        boosts=0,
        comments_count=0,
    )
    high_engagement = SocialPost(
        author_id="u1",
        author_username="alpha",
        content="test",
        trust_tier_required=TrustTier.OBSERVER,
        likes=10,
        boosts=3,
        comments_count=4,
    )
    assert _compute_visibility_score(high_engagement) > _compute_visibility_score(low_engagement)
