"""LinUCB-based multi-armed bandit for topic recommendation."""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

STATE_VERSION = 1
# Planner heuristic scores above this are treated as a full keyword match.
HEURISTIC_SCORE_SCALE = 5.0


@dataclass(frozen=True)
class BanditSelection:
    """A topic choice plus the exact context vector it was scored with.

    LinUCB must be updated with the same vector used at selection time;
    recomputing it later would see post-selection recency/popularity values.
    """

    topic_idx: int
    topic: str
    context: np.ndarray


class TopicBandit:
    """Contextual bandit that picks a topic from a candidate shortlist.

    The conversation planner produces heuristic candidates; the bandit uses
    LinUCB estimates learned from per-turn rewards to choose among them, so
    reward feedback actually influences future topic selection.
    """

    def __init__(
        self,
        topics: List[str],
        alpha: float = 0.1,
        recency_window: float = 180.0,
        recency_penalty: float = 0.4,
        frequency_penalty: float = 0.3,
        min_exploration_probability: float = 0.05,
        max_history: int = 200,
    ):
        self.topics = topics
        self.n_topics = len(topics)
        self.conversation_history: List[Dict] = []
        self.max_history = max(int(max_history), 1)

        # LinUCB parameters
        self.emotion_labels = ['happy', 'sad', 'angry', 'surprised', 'neutral']
        self.max_subtopics = 5
        self.feature_dim = 4 + len(self.emotion_labels) + 2  # bias, heuristic score, popularity, recency, emotions, subtopic stats
        self.exploration_param = max(alpha, 0.01)
        self.A_matrices = [np.identity(self.feature_dim) for _ in range(self.n_topics)]
        self.A_inv_matrices = [np.identity(self.feature_dim) for _ in range(self.n_topics)]
        self.b_vectors = [np.zeros(self.feature_dim) for _ in range(self.n_topics)]

        # Legacy averages retained for stats/debugging
        self.values = np.zeros(self.n_topics)
        self.counts = np.zeros(self.n_topics)
        self.topic_frequency = np.zeros(self.n_topics)

        self.last_selected_times = np.zeros(self.n_topics)
        self.total_selections = 0
        self.subtopic_cache: Dict[str, List[str]] = {topic: [] for topic in topics}
        self.recency_window = max(recency_window, 1.0)
        self.recency_penalty = max(recency_penalty, 0.0)
        self.frequency_penalty = max(frequency_penalty, 0.0)
        self.min_exploration_probability = max(min_exploration_probability, 0.0)
        self.recent_topic_buffer: List[int] = []
        self.recent_buffer_size = 5

    def select_with_context(
        self,
        candidate_topics: Sequence[str],
        features: Optional[Dict[str, Any]] = None,
    ) -> Optional[BanditSelection]:
        """Pick one topic among the given candidates via LinUCB scores.

        Records the selection (counts/recency) and returns it together with
        the context vector that should later be passed to ``update``, or
        None when no candidate is known to the bandit.
        """
        candidate_indices = [
            self.topics.index(topic) for topic in candidate_topics if topic in self.topics
        ]
        if not candidate_indices:
            return None

        features = dict(features or {})
        features.setdefault("context_text", "")

        best_idx = candidate_indices[0]
        best_score = float('-inf')
        scores: List[Tuple[str, float]] = []
        vectors: Dict[int, np.ndarray] = {}

        for idx in candidate_indices:
            x = self._get_feature_vector(idx, features)
            vectors[idx] = x
            A_inv = self.A_inv_matrices[idx]
            theta = A_inv @ self.b_vectors[idx]
            exploration_bonus = self.exploration_param * np.sqrt(np.dot(x, A_inv @ x))
            score = float(np.dot(theta, x) + exploration_bonus) - self._calculate_topic_penalty(idx)
            scores.append((self.topics[idx], score))
            if score > best_score:
                best_score = score
                best_idx = idx

        if self.total_selections > 0 and np.random.rand() < self.min_exploration_probability:
            unexplored = [idx for idx in candidate_indices if self.topic_frequency[idx] == 0]
            best_idx = int(np.random.choice(unexplored or candidate_indices))

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Bandit candidate scores: %s (selected=%s)",
                ", ".join(f"{name}:{score:.3f}" for name, score in scores),
                self.topics[best_idx],
            )

        self._record_selection(best_idx)
        return BanditSelection(best_idx, self.topics[best_idx], vectors[best_idx])

    def select_from_candidates(
        self,
        candidate_topics: Sequence[str],
        features: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[int, str]]:
        """Tuple-returning variant of ``select_with_context``."""
        selection = self.select_with_context(candidate_topics, features)
        if selection is None:
            return None
        return selection.topic_idx, selection.topic

    def select_topic(self, context: str = "", features: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """LinUCB selection over the full topic list."""
        features = dict(features or {})
        features.setdefault("context_text", context or "")
        selected = self.select_from_candidates(self.topics, features)
        if selected is None:  # only possible with an empty topic list
            raise ValueError("TopicBandit has no topics to select from")
        return selected

    def _get_feature_vector(self, topic_idx: int, feature_payload: Dict[str, Any]) -> np.ndarray:
        """LinUCB 用の特徴量ベクトルを生成"""
        vector = np.zeros(self.feature_dim, dtype=float)
        idx = 0

        vector[idx] = 1.0  # bias
        idx += 1

        # How strongly the planner's keyword/emotion heuristics favour this
        # topic for the current utterance.
        heuristic_scores = feature_payload.get('heuristic_scores')
        raw_score = 0.0
        if isinstance(heuristic_scores, dict):
            candidate = heuristic_scores.get(self.topics[topic_idx])
            if isinstance(candidate, (int, float)):
                raw_score = float(candidate)
        vector[idx] = min(max(raw_score, 0.0) / HEURISTIC_SCORE_SCALE, 1.0)
        idx += 1

        total = max(float(self.total_selections), 1.0)
        vector[idx] = float(self.topic_frequency[topic_idx]) / total
        idx += 1

        last_time = self.last_selected_times[topic_idx]
        if last_time > 0:
            delta = max(time.time() - last_time, 0.0)
            vector[idx] = float(np.exp(-delta / 300.0))
        else:
            vector[idx] = 0.0
        idx += 1

        emotion_data = feature_payload.get('emotion') or {}
        primary_emotions = emotion_data.get('primary_emotions') if isinstance(emotion_data, dict) else None
        primary = ''
        if isinstance(primary_emotions, list) and primary_emotions:
            primary = str(primary_emotions[0]).lower()
        elif isinstance(emotion_data, str):
            primary = emotion_data.lower()

        for label in self.emotion_labels:
            vector[idx] = 1.0 if label == primary else 0.0
            idx += 1

        subtopics = feature_payload.get('subtopics')
        if not subtopics:
            topic = self.topics[topic_idx]
            subtopics = self.subtopic_cache.get(topic, [])

        if subtopics:
            vector[idx] = min(len(subtopics), self.max_subtopics) / float(self.max_subtopics)
        else:
            vector[idx] = 0.0
        idx += 1

        text_for_match = str(feature_payload.get('user_input') or feature_payload.get('context_text') or '')
        text_lower = text_for_match.lower()
        if subtopics:
            matches = sum(1 for item in subtopics if item and item.lower() in text_lower)
            vector[idx] = matches / float(len(subtopics))
        else:
            vector[idx] = 0.0
        idx += 1

        return vector

    def _record_selection(self, topic_idx: int) -> None:
        self.last_selected_times[topic_idx] = time.time()
        self.total_selections += 1
        self.topic_frequency[topic_idx] += 1
        self.counts[topic_idx] += 1
        self._record_recent_topic(topic_idx)

    def _record_recent_topic(self, topic_idx: int) -> None:
        self.recent_topic_buffer.append(topic_idx)
        if len(self.recent_topic_buffer) > self.recent_buffer_size:
            self.recent_topic_buffer.pop(0)

    def _calculate_topic_penalty(self, topic_idx: int) -> float:
        penalty = 0.0

        last_time = self.last_selected_times[topic_idx]
        if last_time > 0:
            delta = max(time.time() - last_time, 0.0)
            if delta < self.recency_window:
                penalty += self.recency_penalty * (1.0 - (delta / self.recency_window))

        if self.total_selections > 0:
            frequency_ratio = float(self.topic_frequency[topic_idx]) / float(self.total_selections)
            penalty += self.frequency_penalty * frequency_ratio

        if self.recent_topic_buffer.count(topic_idx) > 1:
            repeat_ratio = float(self.recent_topic_buffer.count(topic_idx)) / max(
                len(self.recent_topic_buffer), 1
            )
            penalty += self.recency_penalty * repeat_ratio * 0.5

        return penalty

    def update(
        self,
        topic_idx: int,
        reward: float,
        features: Optional[Dict[str, Any]] = None,
        context: Optional[np.ndarray] = None,
    ):
        """LinUCB パラメータの更新

        Pass ``context`` from a ``BanditSelection`` whenever possible;
        ``features`` recomputes the vector from the current bandit state.
        """
        if topic_idx < 0 or topic_idx >= self.n_topics:
            logger.warning("TopicBandit.update: invalid topic index %s", topic_idx)
            return

        if context is not None:
            x = np.asarray(context, dtype=float)
            if x.shape != (self.feature_dim,):
                logger.warning("TopicBandit.update: context has shape %s, expected (%s,)", x.shape, self.feature_dim)
                return
        else:
            x = self._get_feature_vector(topic_idx, dict(features or {}))
        A = self.A_matrices[topic_idx]
        b = self.b_vectors[topic_idx]

        A += np.outer(x, x)
        self.b_vectors[topic_idx] = b + reward * x
        try:
            self.A_inv_matrices[topic_idx] = np.linalg.inv(A)
        except np.linalg.LinAlgError:
            logger.exception("TopicBandit: failed to invert matrix for topic %s", self.topics[topic_idx])
            self.A_matrices[topic_idx] = np.identity(self.feature_dim)
            self.A_inv_matrices[topic_idx] = np.identity(self.feature_dim)
            self.b_vectors[topic_idx] = np.zeros(self.feature_dim)
            return

        self.values[topic_idx] += 0.1 * (reward - self.values[topic_idx])

    def get_topic_stats(self) -> Dict:
        """各トピックの統計情報を取得"""
        return {
            topic: {
                'value': self.values[i],
                'count': self.counts[i],
                'frequency': self.topic_frequency[i],
            }
            for i, topic in enumerate(self.topics)
        }

    def get_summary(self) -> Dict[str, Any]:
        """バンディットの概要情報を返す"""
        return {
            'topics': self.get_topic_stats(),
            'subtopics': self.subtopic_cache,
            'totalSelections': int(self.total_selections),
            'featureDim': self.feature_dim,
        }

    def add_to_history(self, user_input: str, response: str, topic: str, reward: Optional[float] = None):
        """会話履歴に追加"""
        entry: Dict[str, Any] = {
            'user_input': user_input,
            'response': response,
            'topic': topic,
            'timestamp': time.time()
        }
        if reward is not None:
            entry['reward'] = reward
        self.conversation_history.append(entry)
        if len(self.conversation_history) > self.max_history:
            del self.conversation_history[: len(self.conversation_history) - self.max_history]

    def record_topic_selection(
        self,
        topic: str,
        features: Optional[Dict[str, Any]] = None,
    ) -> Optional[BanditSelection]:
        """Record a topic choice made outside LinUCB (e.g. a forced continuation)."""
        if topic not in self.topics:
            logger.debug("TopicBandit.record_topic_selection: unknown topic %s", topic)
            return None

        topic_idx = self.topics.index(topic)
        context = self._get_feature_vector(topic_idx, dict(features or {}))
        self._record_selection(topic_idx)
        return BanditSelection(topic_idx, topic, context)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def to_state(self) -> Dict[str, Any]:
        """Serialise learned parameters to a JSON-friendly dict."""
        return {
            'version': STATE_VERSION,
            'feature_dim': self.feature_dim,
            'topics': {
                topic: {
                    'A': self.A_matrices[i].tolist(),
                    'b': self.b_vectors[i].tolist(),
                    'value': float(self.values[i]),
                    'count': float(self.counts[i]),
                    'frequency': float(self.topic_frequency[i]),
                }
                for i, topic in enumerate(self.topics)
            },
        }

    def load_state(self, state: Dict[str, Any]) -> int:
        """Restore parameters saved by ``to_state``; returns topics restored.

        Topics are matched by name, so adding or removing topic families
        keeps whatever still lines up. Incompatible states are ignored.
        """
        if not isinstance(state, dict) or state.get('version') != STATE_VERSION:
            logger.warning("TopicBandit.load_state: unsupported state version")
            return 0
        if state.get('feature_dim') != self.feature_dim:
            logger.warning("TopicBandit.load_state: feature_dim mismatch; starting fresh")
            return 0

        restored = 0
        saved_topics = state.get('topics') or {}
        for i, topic in enumerate(self.topics):
            saved = saved_topics.get(topic)
            if not isinstance(saved, dict):
                continue
            try:
                A = np.asarray(saved['A'], dtype=float)
                b = np.asarray(saved['b'], dtype=float)
                if A.shape != (self.feature_dim, self.feature_dim) or b.shape != (self.feature_dim,):
                    continue
                A_inv = np.linalg.inv(A)
            except (KeyError, TypeError, ValueError, np.linalg.LinAlgError):
                logger.warning("TopicBandit.load_state: skipping corrupt entry for %s", topic)
                continue
            self.A_matrices[i] = A
            self.A_inv_matrices[i] = A_inv
            self.b_vectors[i] = b
            self.values[i] = float(saved.get('value', 0.0))
            self.counts[i] = float(saved.get('count', 0.0))
            self.topic_frequency[i] = float(saved.get('frequency', 0.0))
            restored += 1

        if restored:
            self.total_selections = int(self.topic_frequency.sum())
        return restored
