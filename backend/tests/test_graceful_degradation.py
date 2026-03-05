"""Unit tests for L6.5 GracefulDegradation."""

from __future__ import annotations

import pytest

from app.services.graceful_degradation import (
    DegradationResponse,
    FailedAttempt,
    GracefulDegradation,
    _generate_suggestions,
)


# ── FailedAttempt ────────────────────────────────────────────────────


class TestFailedAttempt:
    def test_to_dict(self):
        a = FailedAttempt(tool="pandoc", command="pandoc x.md", error="not found", error_category="missing_dependency")
        d = a.to_dict()
        assert d["tool"] == "pandoc"
        assert d["error"] == "not found"
        assert d["error_category"] == "missing_dependency"

    def test_frozen(self):
        a = FailedAttempt(tool="x")
        with pytest.raises(AttributeError):
            a.tool = "y"  # type: ignore[misc]


# ── DegradationResponse ─────────────────────────────────────────────


class TestDegradationResponse:
    def test_to_dict(self):
        r = DegradationResponse(
            task="Convert", fully_resolved=False,
            partial_results=["HTML done"],
            failed_attempts=[FailedAttempt(tool="pandoc", error="not found")],
            suggestions=["Install pandoc"],
            explanation="Partial success",
            confidence=0.5,
        )
        d = r.to_dict()
        assert d["task"] == "Convert"
        assert d["fully_resolved"] is False
        assert len(d["partial_results"]) == 1
        assert len(d["failed_attempts"]) == 1
        assert d["confidence"] == 0.5

    def test_frozen(self):
        r = DegradationResponse(task="x")
        with pytest.raises(AttributeError):
            r.task = "y"  # type: ignore[misc]


# ── format_for_user ──────────────────────────────────────────────────


class TestFormatForUser:
    def test_fully_resolved_short(self):
        r = DegradationResponse(task="Convert PDF", fully_resolved=True)
        text = r.format_for_user()
        assert "completed" in text.lower()
        assert "Convert PDF" in text

    def test_partial_results_shown(self):
        r = DegradationResponse(
            task="Convert",
            partial_results=["HTML generated"],
            failed_attempts=[FailedAttempt(tool="pandoc", error="missing")],
            suggestions=["Install pandoc"],
        )
        text = r.format_for_user()
        assert "Partial results:" in text
        assert "HTML generated" in text
        assert "pandoc" in text

    def test_suggestions_shown(self):
        r = DegradationResponse(
            task="Convert",
            failed_attempts=[FailedAttempt(tool="x", error="e")],
            suggestions=["Try plan B"],
        )
        text = r.format_for_user()
        assert "Suggested next steps:" in text
        assert "Try plan B" in text

    def test_explanation_shown(self):
        r = DegradationResponse(
            task="Convert",
            explanation="All approaches exhausted.",
        )
        text = r.format_for_user()
        assert "All approaches exhausted." in text


# ── _generate_suggestions ───────────────────────────────────────────


class TestGenerateSuggestions:
    def test_missing_dependency_suggestion(self):
        attempts = [FailedAttempt(tool="x", error_category="missing_dependency")]
        s = _generate_suggestions(attempts)
        assert any("install" in x.lower() for x in s)

    def test_permission_suggestion(self):
        attempts = [FailedAttempt(tool="x", error_category="permission")]
        s = _generate_suggestions(attempts)
        assert any("permission" in x.lower() for x in s)

    def test_transient_suggestion(self):
        attempts = [FailedAttempt(tool="x", error_category="transient")]
        s = _generate_suggestions(attempts)
        assert any("try again" in x.lower() for x in s)

    def test_deduplicates_categories(self):
        attempts = [
            FailedAttempt(tool="a", error_category="missing_dependency"),
            FailedAttempt(tool="b", error_category="missing_dependency"),
        ]
        s = _generate_suggestions(attempts)
        # Only one suggestion for the same category
        dep_count = sum(1 for x in s if "install" in x.lower())
        assert dep_count == 1

    def test_unknown_category_fallback(self):
        attempts = [FailedAttempt(tool="x", error_category="unknown_xyz")]
        s = _generate_suggestions(attempts)
        assert len(s) >= 1
        assert any("different approach" in x.lower() for x in s)

    def test_empty_attempts_fallback(self):
        s = _generate_suggestions([])
        assert len(s) >= 1


# ── GracefulDegradation.build_response ───────────────────────────────


class TestBuildResponse:
    def test_all_failed(self):
        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Convert",
            attempts=[
                FailedAttempt(tool="pandoc", error="not found", error_category="missing_dependency"),
                FailedAttempt(tool="wkhtmltopdf", error="not found", error_category="missing_dependency"),
            ],
        )
        assert not resp.fully_resolved
        assert resp.confidence == 0.0
        assert len(resp.failed_attempts) == 2
        assert len(resp.suggestions) >= 1
        assert "failed" in resp.explanation.lower()

    def test_partial_success(self):
        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Convert",
            attempts=[FailedAttempt(tool="pandoc", error="not found")],
            partial_results=["HTML version ready"],
        )
        assert not resp.fully_resolved
        assert resp.confidence > 0.0
        assert resp.confidence < 1.0
        assert "partial" in resp.explanation.lower()

    def test_no_attempts_with_partials_fully_resolved(self):
        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Simple task",
            partial_results=["Done"],
        )
        assert resp.fully_resolved
        assert resp.confidence == 1.0

    def test_custom_explanation(self):
        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Task",
            attempts=[FailedAttempt(tool="x", error="e")],
            explanation="Custom reason.",
        )
        assert resp.explanation == "Custom reason."

    def test_no_attempts_no_partials(self):
        gd = GracefulDegradation()
        resp = gd.build_response(task="Nothing")
        assert not resp.fully_resolved
        assert resp.confidence == 0.0
        assert "No approaches" in resp.explanation

    def test_confidence_formula(self):
        """confidence = partials / (partials + failures)."""
        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Task",
            attempts=[FailedAttempt(tool="a", error="e"), FailedAttempt(tool="b", error="e")],
            partial_results=["p1", "p2"],
        )
        # 2 / (2 + 2) = 0.5
        assert resp.confidence == pytest.approx(0.5)
