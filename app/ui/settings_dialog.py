"""Settings dialog for LLM provider configuration and per-step routing."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.providers.config import load_provider_config, save_provider_config
from app.storage.models import ProviderConfig

STEP_LABELS = {
    "planner": "场景规划师 (Planner)",
    "characters": "角色意图 (Characters)",
    "writer": "写作 (Writer)",
    "reviewer": "审阅 (Reviewer)",
    "fact_extractor": "事实提取 (Fact Extractor)",
    "state_updater": "状态更新 (State Updater)",
    "bible_assistant": "Story Bible Assistant",
}

PROVIDER_CHOICES = ["ollama", "deepseek"]


class SettingsDialog(QDialog):
    """App-level settings for LLM providers and per-step routing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LLM 设置")
        self.setMinimumWidth(500)

        self._config = load_provider_config()

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_ollama_tab(), "Ollama")
        tabs.addTab(self._build_deepseek_tab(), "DeepSeek")
        tabs.addTab(self._build_routing_tab(), "步骤路由")
        layout.addWidget(tabs)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _build_ollama_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self.ollama_host = QLineEdit(self._config.ollama_host)
        form.addRow("主机地址:", self.ollama_host)

        self.ollama_model = QLineEdit(self._config.ollama_model)
        form.addRow("模型名称:", self.ollama_model)

        return w

    def _build_deepseek_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(12)

        self.deepseek_model = QLineEdit(self._config.deepseek_model)
        form.addRow("模型名称:", self.deepseek_model)

        self.deepseek_base_url = QLineEdit(self._config.deepseek_base_url)
        form.addRow("API 地址:", self.deepseek_base_url)

        self.deepseek_api_key = QLineEdit(self._config.deepseek_api_key)
        self.deepseek_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API Key:", self.deepseek_api_key)

        return w

    def _build_routing_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        header = QLabel("为每个管道步骤选择 LLM 提供商：")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(12)

        self._routing_combos: dict[str, QComboBox] = {}
        for step_id, label in STEP_LABELS.items():
            combo = QComboBox()
            combo.addItems(PROVIDER_CHOICES)
            current = self._config.routing.get(step_id, "ollama")
            if current in PROVIDER_CHOICES:
                combo.setCurrentText(current)
            form.addRow(label, combo)
            self._routing_combos[step_id] = combo

        layout.addLayout(form)
        layout.addStretch()
        return w

    def _on_save(self) -> None:
        self._config.ollama_host = self.ollama_host.text().strip()
        self._config.ollama_model = self.ollama_model.text().strip()
        self._config.deepseek_model = self.deepseek_model.text().strip()
        self._config.deepseek_base_url = self.deepseek_base_url.text().strip()
        self._config.deepseek_api_key = self.deepseek_api_key.text().strip()

        for step_id, combo in self._routing_combos.items():
            self._config.routing[step_id] = combo.currentText()

        save_provider_config(self._config)
        self.accept()
