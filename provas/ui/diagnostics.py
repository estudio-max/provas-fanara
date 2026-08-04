"""Compact editorial diagnosis panel."""
from __future__ import annotations

from collections import Counter

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..modelos import BookPlan
from ..projeto import DiagnosticSummary


class DiagnosticsPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("diagnosticsPanel")
        self.setFixedWidth(235)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(0)

        title = QLabel("Diagnóstico editorial")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        layout.addSpacing(8)
        self.summary_label = QLabel("O diagnóstico aparece depois da análise.")
        self.summary_label.setObjectName("mutedText")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        layout.addSpacing(24)

        self.pages_value = self._metric(layout, "Páginas")
        self.photos_value = self._metric(layout, "Fotografias usadas")
        self.impact_value = self._metric(layout, "Páginas de impacto")
        self.order_value = self._metric(layout, "Ordem preservada")
        self.order_value.setObjectName("metricTextValue")

        layout.addSpacing(16)
        warnings_title = QLabel("Observações")
        warnings_title.setObjectName("sectionTitle")
        layout.addWidget(warnings_title)
        layout.addSpacing(8)
        self.warnings_label = QLabel("Nenhum alerta no momento.")
        self.warnings_label.setObjectName("mutedText")
        self.warnings_label.setWordWrap(True)
        layout.addWidget(self.warnings_label)
        layout.addStretch(1)

    def _metric(self, layout: QVBoxLayout, label: str) -> QLabel:
        row = QFrame()
        row.setObjectName("metricRow")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 8, 0, 8)
        row_layout.setSpacing(4)
        name = QLabel(label)
        name.setObjectName("mutedText")
        value = QLabel("—")
        value.setObjectName("metricValue")
        row_layout.addWidget(name)
        row_layout.addWidget(value)
        layout.addWidget(row)
        return value

    def set_plan(self, plan: BookPlan, *, failed_count: int = 0) -> None:
        distribution = Counter(len(page.photo_ids) for page in plan.pages)
        photos = len({photo_id for page in plan.pages for photo_id in page.photo_ids})
        impact = distribution[1]
        self.summary_label.setText(
            "A sequência está pronta para revisão."
            if not failed_count
            else f"{failed_count} fotografia(s) precisam de atenção."
        )
        self.pages_value.setText(str(len(plan.pages)))
        self.photos_value.setText(str(photos))
        self.impact_value.setText(str(impact))
        self.order_value.setText("Calculada no projeto")
        self.warnings_label.setText(
            "Nenhum alerta no momento."
            if not failed_count
            else "Confira os arquivos que não puderam ser lidos e tente novamente."
        )

    def set_summary(self, summary: DiagnosticSummary) -> None:
        self.pages_value.setText(str(summary.page_count))
        self.photos_value.setText(str(summary.valid_count))
        self.impact_value.setText(str(summary.distribution.get(1, 0)))
        self.order_value.setText(f"{summary.preserved_order_percent:.0f}%")
        self.summary_label.setText(
            f"{summary.valid_count} válidas · {summary.failed_count} com problema"
        )
        self.warnings_label.setText("\n\n".join(summary.warnings) or "Nenhum alerta no momento.")
