import numpy as np
import os
import logging
from typing import List, Dict, Tuple, Optional, Any
from openai import OpenAI
import time

logger = logging.getLogger(__name__)


class TopicBandit:
    """LinUCB-based multi-armed bandit for topic recommendation."""

    def __init__(self, topics: List[str], alpha: float = 0.1, client: Optional[OpenAI] = None):
        self.topics = topics
        self.n_topics = len(topics)
        self.conversation_history: List[Dict] = []

        # LinUCB parameters
        self.emotion_labels = ['happy', 'sad', 'angry', 'surprised', 'neutral']
        self.feature_dim = 4 + len(self.emotion_labels)  # bias, keyword match, popularity, recency, emotion one-hot
        self.exploration_param = max(alpha, 0.01)
        self.A_matrices = [np.identity(self.feature_dim) for _ in range(self.n_topics)]
        self.A_inv_matrices = [np.identity(self.feature_dim) for _ in range(self.n_topics)]
        self.b_vectors = [np.zeros(self.feature_dim) for _ in range(self.n_topics)]

        # Legacy averages retained for stats/debugging
        self.values = np.zeros(self.n_topics)
        self.counts = np.zeros(self.n_topics)

        self.last_selected_times = np.zeros(self.n_topics)
        self.total_selections = 0
        self._last_contexts: Dict[int, str] = {}
        self._last_features: Dict[int, Dict[str, Any]] = {}

        self.client: Optional[OpenAI] = None
        self._client_initialisation_error: Optional[Exception] = None

        if client is not None:
            self.client = client
        else:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                try:
                    self.client = OpenAI(api_key=api_key)
                except Exception as exc:
                    self._client_initialisation_error = exc
                    logger.warning("TopicBandit could not initialise OpenAI client: %s", exc)
                    self.client = None
            else:
                logger.warning("TopicBandit: OpenAI API key is not configured; exploration and evaluation will use fallbacks.")

    def set_client(self, client: Optional[OpenAI]):
        """Update the OpenAI client instance used for bandit decisions."""
        self.client = client
        
    def select_topic(self, context: str = "", features: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """LinUCB でコンテキストを考慮したトピックを選択"""
        context = context or ""
        if features is None:
            features = {"context_text": context}
        else:
            features = dict(features)
            features.setdefault("context_text", context)

        best_score = float('-inf')
        best_idx = 0

        for idx in range(self.n_topics):
            x = self._get_feature_vector(idx, features)
            A_inv = self.A_inv_matrices[idx]
            theta = A_inv @ self.b_vectors[idx]
            exploration_bonus = self.exploration_param * np.sqrt(np.dot(x, A_inv @ x))
            score = float(np.dot(theta, x) + exploration_bonus)

            if score > best_score:
                best_score = score
                best_idx = idx

        self._last_contexts[best_idx] = context
        self._last_features[best_idx] = features
        current_time = time.time()
        self.last_selected_times[best_idx] = current_time
        self.total_selections += 1
        return best_idx, self.topics[best_idx]
    
    def _explore_with_llm(self, context: str) -> Tuple[int, str]:
        """LLMを使用して関連トピックを探索"""
        if self.client is None:
            logger.warning("TopicBandit: OpenAI client unavailable; selecting a random topic instead of LLM-guided exploration.")
            topic_idx = np.random.randint(self.n_topics)
            return topic_idx, self.topics[topic_idx]

        try:
            prompt = f"""
            以下の会話の文脈を考慮して、最も適切なトピックを選択してください。
            利用可能なトピック: {', '.join(self.topics)}
            
            会話の文脈: {context}
            
            最も適切なトピックを1つだけ選んでください。
            """
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは会話の文脈に基づいて最適なトピックを選択するアシスタントです。"},
                    {"role": "user", "content": prompt}
                ]
            )

            selected_topic = (response.choices[0].message.content or '').strip()
            topic_idx = self.topics.index(selected_topic)
            return topic_idx, selected_topic
            
        except Exception as e:
            print(f"LLMによるトピック選択でエラーが発生: {e}")
            # エラー時はランダム選択にフォールバック
            topic_idx = np.random.randint(self.n_topics)
            return topic_idx, self.topics[topic_idx]

    def _get_feature_vector(self, topic_idx: int, feature_payload: Dict[str, Any]) -> np.ndarray:
        """LinUCB 用の特徴量ベクトルを生成"""
        vector = np.zeros(self.feature_dim, dtype=float)
        idx = 0

        vector[idx] = 1.0  # bias
        idx += 1

        context_text = str(feature_payload.get('context_text', '') or '')
        context_lower = context_text.lower()
        topic_keyword = self.topics[topic_idx].lower()
        vector[idx] = 1.0 if topic_keyword in context_lower else 0.0
        idx += 1

        total = max(float(self.total_selections), 1.0)
        vector[idx] = float(self.counts[topic_idx]) / total
        idx += 1

        last_time = self.last_selected_times[topic_idx]
        if last_time > 0:
            delta = max(time.time() - last_time, 0.0)
            vector[idx] = float(np.exp(-delta / 300.0))
        else:
            vector[idx] = 0.0
        idx += 1

        emotion_data = feature_payload.get('emotion') or {}
        primary_emotions = emotion_data.get('primary_emotions')
        primary = ''
        if isinstance(primary_emotions, list) and primary_emotions:
            primary = str(primary_emotions[0]).lower()
        elif isinstance(emotion_data, str):
            primary = emotion_data.lower()

        for label in self.emotion_labels:
            vector[idx] = 1.0 if label == primary else 0.0
            idx += 1

        return vector
    
    def evaluate_response(self, response: str, user_input: str) -> float:
        """LLMを使用して応答の質を評価"""
        if self.client is None:
            logger.warning("TopicBandit: OpenAI client unavailable; returning default evaluation score.")
            return 0.5

        try:
            prompt = f"""
            以下の会話の応答を評価してください：
            
            ユーザーの入力: {user_input}
            VTuberの応答: {response}
            
            以下の基準で0.0から1.0の間で評価してください：
            1. 応答の自然さと適切さ
            2. 感情表現の豊かさ
            3. 会話の継続性
            4. トピックとの関連性
            
            各基準の評価と総合評価を以下の形式で返してください：
            1. 0.8 (自然さと適切さ)
            2. 0.7 (感情表現の豊かさ)
            3. 0.9 (会話の継続性)
            4. 0.8 (トピックとの関連性)
            
            総合評価: 0.8
            """
            
            evaluation = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは会話の質を評価する専門家です。各基準の評価と総合評価を返してください。"},
                    {"role": "user", "content": prompt}
                ]
            )

            score_text = (evaluation.choices[0].message.content or '').strip()
            print("\n評価結果:")
            print(score_text)
            
            try:
                # 総合評価を探す
                import re
                match = re.search(r'総合評価:\s*(\d+\.?\d*)', score_text)
                if match:
                    score = float(match.group(1))
                else:
                    # 総合評価が見つからない場合は最初の数値を探す
                    match = re.search(r'\d+\.?\d*', score_text)
                    if match:
                        score = float(match.group())
                    else:
                        score = 0.5  # デフォルト値
            except ValueError:
                score = 0.5  # デフォルト値
            
            return max(0.0, min(1.0, score))  # 0.0から1.0の範囲に制限
            
        except Exception as e:
            print(f"応答評価でエラーが発生: {e}")
            return 0.5  # エラー時は中立的な評価を返す
    
    def generate_subtopics(self, main_topic: str) -> List[str]:
        """メイントピックに関連するサブトピックを生成"""
        if self.client is None:
            logger.warning("TopicBandit: OpenAI client unavailable; skipping subtopic generation.")
            return []

        try:
            prompt = f"""
            「{main_topic}」に関連する、具体的な会話のトピックを5つ生成してください。
            各トピックは具体的で、会話を発展させやすいものにしてください。
            
            形式：
            1. トピック1
            2. トピック2
            ...
            """
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは会話のトピックを生成する専門家です。"},
                    {"role": "user", "content": prompt}
                ]
            )

            subtopics = (response.choices[0].message.content or '').strip().split('\n')
            return [topic.split('. ')[1] for topic in subtopics if '. ' in topic]
            
        except Exception as e:
            print(f"サブトピック生成でエラーが発生: {e}")
            return []
    
    def update(self, topic_idx: int, reward: float, features: Optional[Dict[str, Any]] = None):
        """LinUCB パラメータの更新"""
        if topic_idx < 0 or topic_idx >= self.n_topics:
            logger.warning("TopicBandit.update: invalid topic index %s", topic_idx)
            return

        if features is None:
            features = self._last_features.get(topic_idx)
            if features is None:
                features = {"context_text": self._last_contexts.get(topic_idx, "")}
        else:
            features = dict(features)
            features.setdefault("context_text", self._last_contexts.get(topic_idx, ""))

        x = self._get_feature_vector(topic_idx, features)
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

        self.counts[topic_idx] += 1
        self.values[topic_idx] += 0.1 * (reward - self.values[topic_idx])
    
    def get_topic_stats(self) -> Dict:
        """各トピックの統計情報を取得"""
        return {
            topic: {
                'value': value,
                'count': count
            }
            for topic, value, count in zip(self.topics, self.values, self.counts)
        }
    
    def add_to_history(self, user_input: str, response: str, topic: str):
        """会話履歴に追加"""
        self.conversation_history.append({
            'user_input': user_input,
            'response': response,
            'topic': topic,
            'timestamp': time.time()
        })
    
    def get_stats(self) -> Dict:
        """トピックの統計情報を取得"""
        stats = {}
        for i, topic in enumerate(self.topics):
            stats[topic] = {
                'count': self.counts[i],
                'avg_reward': self.values[i] / max(1, self.counts[i]),
                'expected_reward': self.values[i]
            }
        return stats 
