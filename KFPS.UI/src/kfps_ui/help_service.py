from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .models import DictListModel


def _default_help_path() -> Path:
    source_ui = Path(__file__).resolve().parents[2]
    frozen_root = Path(getattr(sys, "_MEIPASS", source_ui))
    frozen_help = frozen_root / "KFPS.UI" / "help" / "topics.json"
    if frozen_help.is_file():
        return frozen_help
    return source_ui / "help" / "topics.json"


class HelpService(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._category_model = DictListModel(["key", "title", "summary", "count"])
        self._topic_model = DictListModel(["key", "category", "title", "summary", "keywords", "match"])
        self._query = ""
        self._category = "all"
        self._topics: list[dict[str, Any]] = []
        self._categories: list[dict[str, Any]] = []
        self._filtered: list[dict[str, Any]] = []
        self._index = 0
        self._load()
        self._refresh()

    @Property(QObject, constant=True)
    def categoryModel(self):
        return self._category_model

    @Property(QObject, constant=True)
    def topicModel(self):
        return self._topic_model

    @Property(str, notify=changed)
    def query(self) -> str:
        return self._query

    @Property(str, notify=changed)
    def selectedCategory(self) -> str:
        return self._category

    @Property(str, notify=changed)
    def title(self) -> str:
        return self._selected().get("title", "No help topic selected")

    @Property(str, notify=changed)
    def summary(self) -> str:
        return self._selected().get("summary", "Try another category or search term.")

    @Property(str, notify=changed)
    def categoryTitle(self) -> str:
        selected = self._selected()
        key = selected.get("category", "")
        return self._category_title(key)

    @Property(str, notify=changed)
    def breadcrumb(self) -> str:
        if not self._filtered:
            return "Help"
        parts = ["Help", self.categoryTitle, self.title]
        return " / ".join(part for part in parts if part)

    @Property(str, notify=changed)
    def resultSummary(self) -> str:
        total = len(self._topics)
        visible = len(self._filtered)
        if self._query.strip():
            return f"{visible} of {total} topics match \"{self._query.strip()}\""
        if self._category != "all":
            return f"{visible} topic(s) in {self._category_title(self._category)}"
        return f"{total} help topics"

    @Property(bool, notify=changed)
    def hasResults(self) -> bool:
        return bool(self._filtered)

    @Property("QVariantList", notify=changed)
    def sections(self):
        return list(self._selected().get("sections", []))

    @Property("QVariantList", notify=changed)
    def steps(self):
        return list(self._selected().get("steps", []))

    @Property("QVariantList", notify=changed)
    def pitfalls(self):
        return list(self._selected().get("pitfalls", []))

    @Property("QVariantList", notify=changed)
    def relatedTopics(self):
        selected = self._selected()
        related_keys = selected.get("related", [])
        by_key = {topic["key"]: topic for topic in self._topics}
        return [
            {
                "key": key,
                "title": by_key[key].get("title", key),
                "summary": by_key[key].get("summary", ""),
            }
            for key in related_keys
            if key in by_key
        ]

    @Property(str, notify=changed)
    def supportChecklist(self) -> str:
        topic = next((item for item in self._topics if item.get("key") == "support-checklist"), None)
        if not topic:
            return ""
        lines = ["KFPS support checklist:"]
        lines.extend(f"- {step}" for step in topic.get("steps", []))
        return "\n".join(lines)

    @Slot(str)
    def search(self, text: str):
        self._query = text or ""
        self._index = 0
        self._refresh()
        self.changed.emit()

    @Slot(str)
    def setCategory(self, key: str):
        self._category = key or "all"
        self._index = 0
        self._refresh()
        self.changed.emit()

    @Slot(int)
    def select(self, index: int):
        if 0 <= index < len(self._filtered):
            self._index = index
            self.changed.emit()

    @Slot(str)
    def selectTopic(self, key: str):
        for index, topic in enumerate(self._filtered):
            if topic.get("key") == key:
                self._index = index
                self.changed.emit()
                return
        for topic in self._topics:
            if topic.get("key") == key:
                self._category = topic.get("category", "all")
                self._query = ""
                self._refresh()
                for index, filtered in enumerate(self._filtered):
                    if filtered.get("key") == key:
                        self._index = index
                        break
                self.changed.emit()
                return

    @Slot()
    def copySupportChecklist(self):
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(self.supportChecklist)

    @Slot(result=str)
    def selectedTopicText(self) -> str:
        topic = self._selected()
        lines = [topic.get("title", ""), topic.get("summary", "")]
        if topic.get("steps"):
            lines.append("\nSteps:")
            lines.extend(f"{index + 1}. {step}" for index, step in enumerate(topic["steps"]))
        for section in topic.get("sections", []):
            lines.append(f"\n{section.get('heading', '')}")
            lines.append(section.get("body", ""))
        if topic.get("pitfalls"):
            lines.append("\nWatch out:")
            lines.extend(f"- {item}" for item in topic["pitfalls"])
        return "\n".join(line for line in lines if line is not None)

    def _load(self):
        path = _default_help_path()
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self._categories = [dict(item) for item in payload.get("categories", [])]
        self._topics = [dict(item) for item in payload.get("topics", [])]

    def _refresh(self):
        query = self._query.strip().lower()

        def matches(topic: dict[str, Any]) -> bool:
            if self._category != "all" and topic.get("category") != self._category:
                return False
            if not query:
                return True
            haystack = " ".join(
                [
                    topic.get("key", ""),
                    topic.get("category", ""),
                    topic.get("title", ""),
                    topic.get("summary", ""),
                    " ".join(topic.get("keywords", [])),
                    " ".join(topic.get("steps", [])),
                    " ".join(section.get("heading", "") + " " + section.get("body", "") for section in topic.get("sections", [])),
                    " ".join(topic.get("pitfalls", [])),
                ]
            ).lower()
            return query in haystack

        self._filtered = [topic for topic in self._topics if matches(topic)]
        if self._index >= len(self._filtered):
            self._index = 0
        self._replace_models(query)

    def _replace_models(self, query: str):
        counts = {item["key"]: 0 for item in self._categories}
        for topic in self._topics:
            key = topic.get("category")
            if key in counts:
                counts[key] += 1
        category_rows = [
            {
                "key": "all",
                "title": "All",
                "summary": "Every guide, walkthrough, and troubleshooting topic.",
                "count": len(self._topics),
            }
        ]
        category_rows.extend(
            {
                "key": item["key"],
                "title": item["title"],
                "summary": item.get("summary", ""),
                "count": counts.get(item["key"], 0),
            }
            for item in self._categories
        )
        self._category_model.replace(category_rows)
        self._topic_model.replace(
            [
                {
                    "key": topic.get("key", ""),
                    "category": self._category_title(topic.get("category", "")),
                    "title": topic.get("title", ""),
                    "summary": topic.get("summary", ""),
                    "keywords": ", ".join(topic.get("keywords", [])[:4]),
                    "match": "Search match" if query else self._category_title(topic.get("category", "")),
                }
                for topic in self._filtered
            ]
        )

    def _selected(self) -> dict[str, Any]:
        if not self._filtered:
            return {}
        return self._filtered[max(0, min(self._index, len(self._filtered) - 1))]

    def _category_title(self, key: str) -> str:
        if key == "all":
            return "All"
        for item in self._categories:
            if item.get("key") == key:
                return item.get("title", key)
        return key
