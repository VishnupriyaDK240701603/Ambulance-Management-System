"""Detailed Explainable AI Decision Inspector Modal."""
from __future__ import annotations

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from panda3d.core import TextNode

from src.models.decision_record import DecisionRecord


class DecisionInspectorModal:
    """Detailed visual inspector displaying structured algorithm decision audits."""

    def __init__(self, parent):
        self.parent = parent

        # Centered floating dialog frame
        self.frame = DirectFrame(
            parent=self.parent,
            frameColor=(0.08, 0.11, 0.15, 0.98),
            frameSize=(-0.95, 0.95, -0.65, 0.65),
            pos=(0, 0, 0.05),
            relief=1
        )
        self.frame.hide()

        # Header title
        self.header_label = DirectLabel(
            parent=self.frame,
            text="EXPLAINABLE AI — ALGORITHMIC DECISION AUDIT",
            text_scale=0.038,
            text_fg=(0.20, 0.85, 0.95, 1.0),
            pos=(0, 0, 0.58),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0)
        )

        # Main details text
        self.details_label = DirectLabel(
            parent=self.frame,
            text="No decision selected.",
            text_scale=0.026,
            text_fg=(0.92, 0.94, 0.98, 1.0),
            pos=(-0.88, 0, 0.48),
            text_align=TextNode.ALeft,
            frameColor=(0, 0, 0, 0)
        )

        # Close button
        self.btn_close = DirectButton(
            parent=self.frame,
            text="Close Audit",
            text_scale=0.030,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0.75, 0.22, 0.22, 1.0),
            frameSize=(-0.18, 0.18, -0.035, 0.035),
            pos=(0.70, 0, -0.58),
            command=self.hide,
            relief=1
        )

    def show_decision(self, record: DecisionRecord) -> None:
        """Render complete structured evidence for the specified decision record."""
        lines = [
            f"Decision ID: {record.id} | Type: {record.decision_type.value} | State Version: {record.state_version}",
            f"Timestamp: {record.timestamp:.1f}s | Target Entity: {record.target_entity_id}",
            f"Selected Action / Winner: {record.selected_name} (ID: {record.selected_id})",
            f"Summary: {record.reasoning_summary}",
            "-" * 95,
            f"ELIGIBLE CANDIDATES EVALUATED ({len(record.eligible_candidates)}):"
        ]

        if record.eligible_candidates:
            for idx, c in enumerate(record.eligible_candidates, 1):
                m_str = ", ".join(f"{k}: {v}" for k, v in c.metrics.items())
                s_str = ", ".join(f"{k}: {v}" for k, v in c.score_components.items())
                lines.append(f"  #{idx} {c.name} — Composite Score: {c.score:.2f}")
                lines.append(f"     Metrics: {m_str}")
                if s_str:
                    lines.append(f"     Score Breakdown: {s_str}")
        else:
            lines.append("  (None met all eligibility requirements)")

        lines.append("-" * 95)
        lines.append(f"REJECTED CANDIDATES & EXCLUSIONS ({len(record.rejected_candidates)}):")
        if record.rejected_candidates:
            for c in record.rejected_candidates:
                lines.append(f"  • {c.name}: REJECTED — {c.rejection_reason}")
        else:
            lines.append("  (No candidates were rejected on preconditions)")

        self.details_label["text"] = "\n".join(lines[:22])
        self.frame.show()

    def hide(self) -> None:
        self.frame.hide()

    def is_visible(self) -> bool:
        return not self.frame.isHidden()
