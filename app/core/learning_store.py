"""Local Adaptive Learning Store for JEV/LEYA Engine Feedback Loop.

Persists user corrections, removals, and additions into a local JSON store
(user_feedback_rules.json), dynamically adapting JEV/LEYA relevance weights
in a 100% offline and privacy-preserving manner (LGPD compliant).

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Stop words to ignore during feedback feature extraction
PORTUGUESE_STOP_WORDS = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com", "nao", "não",
    "uma", "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi",
    "ao", "ele", "das", "tem", "seu", "sua", "ou", "ser", "quando", "muito", "nos",
    "ja", "já", "eu", "tambem", "também", "so", "só", "pelo", "pela", "ate", "até",
    "isso", "ela", "entre", "era", "depois", "sem", "mesmo", "aos", "ter", "seus",
    "quem", "nas", "me", "esse", "eles", "estao", "estão", "voce", "você", "tinha",
    "foram", "essa", "num", "nem", "suas", "meu", "as", "minha", "numa", "pelos",
    "elas", "havia", "seja", "qual", "sera", "será", "nos", "nós", "tenho", "lhe",
    "deles", "essas", "esses", "pelas", "este", "fosse", "dele", "tu", "te", "voces",
    "vos", "lhes", "meus", "minhas", "teu", "tua", "teus", "tuas", "nosso", "nossa",
    "nossos", "nossas", "dela", "delas", "esta", "estes", "estas", "aquele", "aquela",
    "aqueles", "aquelas", "isto", "aquilo", "estou", "esta", "estamos", "estao",
    "estive", "esteve", "estivemos", "estiveram", "estava", "estavamos", "estavam",
    "hei", "ha", "havemos", "hao", "houve", "houvemos", "houveram", "houvera",
    "houveramos", "haja", "hajamos", "hajam", "houvesse", "houvessemos", "houvessem",
    "houver", "houvermos", "houverem", "houverei", "houvera", "houveremos", "houverao",
    "houveria", "houveriamos", "houveriam", "sou", "somos", "sao", "era", "eramos",
    "eram", "fui", "foi", "fomos", "foram", "fora", "foramos", "seja", "sejamos",
    "sejam", "fosse", "fossemos", "fossem", "for", "formos", "forem", "serei", "sera",
    "seremos", "serao", "seria", "seriamos", "seriam", "tenho", "tem", "temos", "tem",
    "tinha", "tinhamos", "tinham", "tive", "teve", "tivemos", "tiveram", "tivera",
    "tiveramos", "tenha", "tenhamos", "tenham", "tivesse", "tivessemos", "tivessem",
    "tiver", "tivermos", "tiverem", "terei", "tera", "teremos", "terao", "teria",
    "teriamos", "teriam"
}


class LearningStore:
    """Manages persistent feedback weights and adaptive learning rules for JEV/LEYA."""

    _instance: Optional["LearningStore"] = None

    def __init__(self, store_path: Optional[Path] = None):
        if store_path is None:
            base_dir = Path(__file__).resolve().parent
            store_path = base_dir / "user_feedback_rules.json"
        self.store_path = Path(store_path)
        self.penalized_terms: Dict[str, float] = {}
        self.boosted_terms: Dict[str, float] = {}
        self.history: List[Dict] = []
        self.load()

    @classmethod
    def get_instance(cls, store_path: Optional[Path] = None) -> "LearningStore":
        """Returns the singleton instance of the LearningStore."""
        if cls._instance is None:
            cls._instance = LearningStore(store_path)
        return cls._instance

    def load(self) -> None:
        """Loads learned weights and feedback history from local JSON."""
        if not self.store_path.exists():
            self._save_default()
            return

        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.penalized_terms = data.get("penalized_terms", {})
                self.boosted_terms = data.get("boosted_terms", {})
                self.history = data.get("history", [])
        except Exception:
            self._save_default()

    def _save_default(self) -> None:
        """Initializes and saves the default store structure."""
        self.penalized_terms = {}
        self.boosted_terms = {}
        self.history = []
        self.save()

    def save(self) -> None:
        """Saves current weights and history to local JSON."""
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "author": "FChNeto",
                "last_updated": datetime.now().isoformat(),
                "penalized_terms": self.penalized_terms,
                "boosted_terms": self.boosted_terms,
                "history": self.history[-50:],  # Keep recent history
            }
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # Fail silently to avoid breaking offline flow
            pass

    def _extract_keywords(self, text: str) -> List[str]:
        """Extracts meaningful n-grams and legal keywords from text."""
        if not text:
            return []
        clean = re.sub(r"[^\w\s-]", " ", text.lower())
        words = [w.strip() for w in clean.split() if len(w.strip()) > 3]
        filtered = [w for w in words if w not in PORTUGUESE_STOP_WORDS]

        keywords: List[str] = []
        # Add filtered unigrams
        keywords.extend(filtered)

        # Add 2-word bigrams for context
        for i in range(len(filtered) - 1):
            keywords.append(f"{filtered[i]} {filtered[i+1]}")

        return keywords

    def record_removal(self, text: str, source: str = "history") -> None:
        """Records an item or text segment removed by the user, penalizing matching terms."""
        if not text:
            return
        keywords = self._extract_keywords(text)
        for kw in keywords:
            curr = self.penalized_terms.get(kw, 0.0)
            self.penalized_terms[kw] = min(0.80, round(curr + 0.15, 2))
            # If it was previously boosted, reduce boost
            if kw in self.boosted_terms:
                self.boosted_terms[kw] = max(0.0, round(self.boosted_terms[kw] - 0.15, 2))
                if self.boosted_terms[kw] == 0.0:
                    del self.boosted_terms[kw]

        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "action": "removal",
            "source": source,
            "sample_snippet": text[:80],
            "keywords_count": len(keywords),
        })
        self.save()

    def record_addition(self, text: str, source: str = "history") -> None:
        """Records an item or text segment added by the user, boosting matching terms."""
        if not text:
            return
        keywords = self._extract_keywords(text)
        for kw in keywords:
            curr = self.boosted_terms.get(kw, 0.0)
            self.boosted_terms[kw] = min(0.80, round(curr + 0.15, 2))
            # If it was previously penalized, reduce penalty
            if kw in self.penalized_terms:
                self.penalized_terms[kw] = max(0.0, round(self.penalized_terms[kw] - 0.15, 2))
                if self.penalized_terms[kw] == 0.0:
                    del self.penalized_terms[kw]

        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "action": "addition",
            "source": source,
            "sample_snippet": text[:80],
            "keywords_count": len(keywords),
        })
        self.save()

    def compute_learned_adjustment(self, text: str) -> float:
        """Computes a learned score adjustment (-0.50 to +0.50) based on accumulated user feedback."""
        if not text:
            return 0.0
        text_lower = text.lower()
        delta = 0.0

        # Check penalized terms
        for term, weight in self.penalized_terms.items():
            if term in text_lower:
                delta -= weight * 0.50

        # Check boosted terms
        for term, weight in self.boosted_terms.items():
            if term in text_lower:
                delta += weight * 0.50

        return max(-0.50, min(0.50, round(delta, 2)))

    def record_feedback(self, original_data: dict, edited_data: dict) -> Dict[str, int]:
        """Compares original vs user-edited summary data and updates learning weights."""
        stats = {"removals": 0, "additions": 0}

        # 1. Compare Chronological History
        orig_hist = original_data.get("chronological_history", [])
        edited_hist = edited_data.get("chronological_history", [])

        orig_ids = {h.get("doc_id") or h.get("description", ""): h for h in orig_hist if isinstance(h, dict)}
        edited_ids = {h.get("doc_id") or h.get("description", ""): h for h in edited_hist if isinstance(h, dict)}

        # Removed history items
        for k, item in orig_ids.items():
            if k not in edited_ids:
                desc = item.get("description", "")
                self.record_removal(desc, source="history")
                stats["removals"] += 1

        # Added history items
        for k, item in edited_ids.items():
            if k not in orig_ids:
                desc = item.get("description", "")
                self.record_addition(desc, source="history")
                stats["additions"] += 1

        # 2. Compare Witnesses
        orig_wit = {w.get("name", "").strip().lower() for w in original_data.get("witnesses", []) if isinstance(w, dict)}
        edited_wit = {w.get("name", "").strip().lower() for w in edited_data.get("witnesses", []) if isinstance(w, dict)}

        for w_name in orig_wit - edited_wit:
            self.record_removal(w_name, source="witness")
            stats["removals"] += 1

        for w_name in edited_wit - orig_wit:
            self.record_addition(w_name, source="witness")
            stats["additions"] += 1

        # 3. Compare Facts
        orig_facts = original_data.get("facts_summary", "") or ""
        edited_facts = edited_data.get("facts_summary", "") or ""
        if len(orig_facts) > len(edited_facts) + 50:
            # Significant text removed from facts
            self.record_removal(orig_facts[:200], source="facts")
            stats["removals"] += 1
        elif len(edited_facts) > len(orig_facts) + 50:
            # Text added to facts
            self.record_addition(edited_facts[:200], source="facts")
            stats["additions"] += 1

        return stats
