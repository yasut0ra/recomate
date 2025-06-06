import numpy as np
import openai
import os
from typing import List, Dict, Tuple
import time

class TopicBandit:
    def __init__(self, topics: List[str], alpha: float = 0.1):
        self.topics = topics
        self.n_topics = len(topics)
        self.alpha = alpha
        self.values = np.zeros(self.n_topics)
        self.counts = np.zeros(self.n_topics)
        self.conversation_history: List[Dict] = []
        
    def select_topic(self, epsilon: float = 0.1, context: str = "") -> Tuple[int, str]:
        """コンテキストを考慮したトピック選択"""
        if np.random.random() < epsilon:
            # 探索：LLMを使用して関連トピックを選択
            return self._explore_with_llm(context)
        else:
            # 活用：現在の最良のトピックを選択
            topic_idx = np.argmax(self.values)
            return topic_idx, self.topics[topic_idx]
    
    def _explore_with_llm(self, context: str) -> Tuple[int, str]:
        """LLMを使用して関連トピックを探索"""
        try:
            prompt = f"""
            以下の会話の文脈を考慮して、最も適切なトピックを選択してください。
            利用可能なトピック: {', '.join(self.topics)}
            
            会話の文脈: {context}
            
            最も適切なトピックを1つだけ選んでください。
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは会話の文脈に基づいて最適なトピックを選択するアシスタントです。"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            selected_topic = response.choices[0].message.content.strip()
            topic_idx = self.topics.index(selected_topic)
            return topic_idx, selected_topic
            
        except Exception as e:
            print(f"LLMによるトピック選択でエラーが発生: {e}")
            # エラー時はランダム選択にフォールバック
            topic_idx = np.random.randint(self.n_topics)
            return topic_idx, self.topics[topic_idx]
    
    def evaluate_response(self, response: str, user_input: str) -> float:
        """LLMを使用して応答の質を評価"""
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
            
            evaluation = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは会話の質を評価する専門家です。各基準の評価と総合評価を返してください。"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # 評価結果から数値のみを抽出
            score_text = evaluation.choices[0].message.content.strip()
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
        try:
            prompt = f"""
            「{main_topic}」に関連する、具体的な会話のトピックを5つ生成してください。
            各トピックは具体的で、会話を発展させやすいものにしてください。
            
            形式：
            1. トピック1
            2. トピック2
            ...
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは会話のトピックを生成する専門家です。"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            subtopics = response.choices[0].message.content.strip().split('\n')
            return [topic.split('. ')[1] for topic in subtopics if '. ' in topic]
            
        except Exception as e:
            print(f"サブトピック生成でエラーが発生: {e}")
            return []
    
    def update(self, topic_idx: int, reward: float):
        """選択したトピックの報酬に基づいて価値を更新"""
        self.counts[topic_idx] += 1
        self.values[topic_idx] += self.alpha * (reward - self.values[topic_idx])
    
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