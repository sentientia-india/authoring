from course_mcp_server.gamification import (
    GameEvent,
    GamificationConfig,
    LearnerGameState,
    apply_game_event,
    build_open_badge_assertion,
    build_xapi_statement,
    default_badge_rules,
)


def test_game_event_awards_xp_and_badge():
    state = LearnerGameState(learner_id="learner1", course_id="course1")
    config = GamificationConfig(badge_rules=default_badge_rules())
    event = GameEvent(
        learner_id="learner1",
        course_id="course1",
        event_type="scenario_completed",
        object_id="scenario1",
        score=90,
    )
    state = apply_game_event(state, event, config)
    assert state.xp >= config.xp_scenario_mastery
    assert any(a.badge_id == "badge_scenario_master" for a in state.achievements)


def test_xapi_statement_shape():
    state = LearnerGameState(learner_id="learner1", course_id="course1")
    event = GameEvent(learner_id="learner1", course_id="course1", event_type="question_answered", object_id="q1", correct=True, score=100)
    statement = build_xapi_statement(event, state)
    assert statement["actor"]
    assert statement["verb"]
    assert statement["object"]
    assert statement["result"]["score"]["scaled"] == 1.0


def test_open_badge_scaffold():
    state = LearnerGameState(learner_id="learner1", course_id="course1")
    event = GameEvent(learner_id="learner1", course_id="course1", event_type="course_completed", object_id="course1", score=91)
    state = apply_game_event(state, event, GamificationConfig(badge_rules=default_badge_rules()))
    assertion = build_open_badge_assertion(state, state.achievements[0], "https://issuer.example")
    assert "OpenBadgeCredential" in assertion["type"]
