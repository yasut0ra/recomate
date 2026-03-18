"""Heuristic conversation planning for Japanese companion dialogue."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Any, Dict, List, Sequence


TOPIC_LIBRARY: Dict[str, Dict[str, List[str] | tuple[str, ...]]] = {
    "最近のできごと": {
        "keywords": (
            "今日",
            "最近",
            "この前",
            "さっき",
            "週末",
            "出来事",
            "イベント",
            "ニュース",
            "話したい",
        ),
        "focus_points": [
            "何が起きたのかを短く言い換える",
            "一番印象に残った場面に触れる",
            "今の気持ちにつながる部分を拾う",
        ],
    },
    "仕事・学び": {
        "keywords": (
            "仕事",
            "会議",
            "上司",
            "同僚",
            "職場",
            "残業",
            "学校",
            "授業",
            "勉強",
            "課題",
            "試験",
            "研究",
            "就活",
        ),
        "focus_points": [
            "負担になっている場面を具体化する",
            "うまくいった点と詰まった点を分ける",
            "次に取りやすい小さな一歩を探る",
        ],
    },
    "人間関係": {
        "keywords": (
            "友達",
            "家族",
            "親",
            "恋人",
            "彼氏",
            "彼女",
            "先輩",
            "後輩",
            "人間関係",
            "ケンカ",
            "仲直り",
            "返信",
        ),
        "focus_points": [
            "相手との距離感や温度差に触れる",
            "言葉にしにくい引っかかりを整理する",
            "無理のない伝え方を一緒に考える",
        ],
    },
    "趣味・好きなもの": {
        "keywords": (
            "ゲーム",
            "映画",
            "アニメ",
            "漫画",
            "音楽",
            "本",
            "旅行",
            "散歩",
            "カフェ",
            "料理",
            "推し",
            "趣味",
            "ライブ",
        ),
        "focus_points": [
            "好きな理由や良かった点を膨らませる",
            "その話題で気分がどう動いたかを拾う",
            "次に楽しめそうな方向へ軽く広げる",
        ],
    },
    "体調・生活リズム": {
        "keywords": (
            "眠い",
            "寝不足",
            "疲れた",
            "しんどい",
            "体調",
            "風邪",
            "頭痛",
            "お腹",
            "食欲",
            "休みたい",
            "だるい",
            "生活リズム",
        ),
        "focus_points": [
            "今つらいポイントを一つに絞る",
            "休息や負担軽減を優先して考える",
            "責めない言い方で整え方を提案する",
        ],
    },
    "悩み・気持ち整理": {
        "keywords": (
            "悩み",
            "不安",
            "つらい",
            "辛い",
            "落ち込む",
            "モヤモヤ",
            "ストレス",
            "怖い",
            "寂しい",
            "苦しい",
            "相談",
            "困ってる",
        ),
        "focus_points": [
            "気持ちを先に受け止めて言い換える",
            "問題そのものと感情を分けて整理する",
            "押しつけずに次の一歩を探る",
        ],
    },
    "将来・目標": {
        "keywords": (
            "将来",
            "目標",
            "夢",
            "進路",
            "転職",
            "引っ越し",
            "挑戦",
            "やりたい",
            "続けたい",
            "計画",
        ),
        "focus_points": [
            "ぼんやりした希望を言語化する",
            "現実の制約と願いを両方見る",
            "次に確認すべきことを一つに絞る",
        ],
    },
    "軽い雑談": {
        "keywords": (
            "暇",
            "雑談",
            "なんとなく",
            "ひま",
            "話そ",
            "話そう",
            "おしゃべり",
        ),
        "focus_points": [
            "軽い温度感で話しやすさを保つ",
            "答えやすい切り口を一つだけ出す",
            "話題を押しつけず余白を残す",
        ],
    },
}

CONTINUITY_MARKERS = (
    "その続き",
    "続き",
    "それで",
    "そのあと",
    "ちなみに",
    "前の話",
    "さっきの",
    "この前の",
)

ADVICE_MARKERS = (
    "どうしたら",
    "どうすれば",
    "したほうが",
    "した方が",
    "相談",
    "アドバイス",
    "助けて",
    "困ってる",
)

QUESTION_MARKERS = ("？", "?", "どう", "なんで", "なぜ", "どっち", "教えて")
SENSITIVE_MARKERS = ("住所", "本名", "電話番号", "連絡先", "学校名", "会社名", "口座", "クレカ")

NEGATIVE_EMOTIONS = {"sad", "angry", "fear", "disgust"}
POSITIVE_EMOTIONS = {"happy", "joy", "trust", "anticipation"}
SURPRISED_EMOTIONS = {"surprised"}


@dataclass(frozen=True)
class ConversationPlan:
    """Structured plan for a single assistant reply."""

    topic_family: str
    response_intent: str
    continuity: str
    follow_up_style: str
    mood_hint: str
    focus_points: List[str]
    matched_keywords: List[str]
    recent_topics: List[str]
    avoid_patterns: List[str]
    boundary_mode: str
    push_intensity: str
    quiet_hours: bool

    def to_prompt_payload(self) -> Dict[str, Any]:
        return {
            "topic_family": self.topic_family,
            "response_intent": self.response_intent,
            "continuity": self.continuity,
            "follow_up_style": self.follow_up_style,
            "mood_hint": self.mood_hint,
            "focus_points": self.focus_points,
            "matched_keywords": self.matched_keywords,
            "recent_topics": self.recent_topics,
            "avoid_patterns": self.avoid_patterns,
            "boundary_mode": self.boundary_mode,
            "push_intensity": self.push_intensity,
            "quiet_hours": self.quiet_hours,
        }


class ConversationPlanner:
    """Select a topic family and reply intent for Japanese dialog."""

    @property
    def topic_families(self) -> List[str]:
        return list(TOPIC_LIBRARY.keys())

    def plan(
        self,
        user_text: str,
        emotion_payload: Dict[str, Any] | None = None,
        recent_history: Sequence[Dict[str, Any]] | None = None,
        mood_state: str | None = None,
        consent_profile: Dict[str, Any] | None = None,
        local_hour: int | None = None,
    ) -> ConversationPlan:
        text = _normalise_text(user_text)
        recent_topics = self._extract_recent_topics(recent_history)
        last_topic = recent_topics[-1] if recent_topics else None
        continuity_marker = any(marker in text for marker in CONTINUITY_MARKERS)
        emotion_label = self._extract_primary_emotion(emotion_payload)
        intensity = self._extract_intensity(emotion_payload)
        push_intensity = self._extract_push_intensity(consent_profile)
        asks_advice = any(marker in text for marker in ADVICE_MARKERS)
        asks_question = any(marker in text for marker in QUESTION_MARKERS)
        quiet_hours = bool(consent_profile and consent_profile.get("night_mode")) and local_hour is not None and (
            local_hour >= 22 or local_hour < 7
        )
        sensitive_mode = self._detect_sensitive_mode(text, consent_profile)

        scores: Dict[str, float] = {}
        matches_by_topic: Dict[str, List[str]] = {}
        for topic_family, profile in TOPIC_LIBRARY.items():
            keywords = profile["keywords"]
            matches = [keyword for keyword in keywords if keyword in text]
            matches_by_topic[topic_family] = matches
            score = 0.0
            for keyword in matches:
                score += 2.2 if len(keyword) >= 3 else 1.4

            repeat_count = recent_topics.count(topic_family)
            if last_topic == topic_family:
                if continuity_marker:
                    score += 3.0
                elif matches:
                    score += 0.8
                else:
                    score -= 1.0

            if repeat_count > 1 and not continuity_marker:
                score -= 1.1 * float(repeat_count - 1)

            scores[topic_family] = score

        self._apply_emotion_bias(scores, emotion_label, text)
        self._apply_mood_bias(scores, mood_state)
        selected_topic = self._pick_topic(scores, matches_by_topic, recent_topics, continuity_marker)
        selected_matches = matches_by_topic.get(selected_topic, [])
        continuity = self._resolve_continuity(selected_topic, last_topic, continuity_marker)
        response_intent = self._resolve_intent(
            emotion_label,
            continuity,
            push_intensity,
            quiet_hours,
            asks_advice,
            asks_question,
        )
        follow_up_style = self._resolve_follow_up_style(
            emotion_label,
            intensity,
            continuity,
            push_intensity,
            quiet_hours,
            sensitive_mode,
            asks_advice,
            asks_question,
        )
        mood_hint = self._resolve_mood_hint(emotion_label, continuity, mood_state, quiet_hours)
        focus_points = self._build_focus_points(selected_topic, selected_matches)
        avoid_patterns = self._build_avoid_patterns(
            emotion_label,
            continuity,
            recent_topics,
            selected_topic,
            push_intensity,
            quiet_hours,
            sensitive_mode,
        )

        return ConversationPlan(
            topic_family=selected_topic,
            response_intent=response_intent,
            continuity=continuity,
            follow_up_style=follow_up_style,
            mood_hint=mood_hint,
            focus_points=focus_points,
            matched_keywords=selected_matches[:3],
            recent_topics=recent_topics,
            avoid_patterns=avoid_patterns,
            boundary_mode="sensitive" if sensitive_mode else "standard",
            push_intensity=push_intensity,
            quiet_hours=quiet_hours,
        )

    def _extract_recent_topics(self, recent_history: Sequence[Dict[str, Any]] | None) -> List[str]:
        topics: List[str] = []
        if not recent_history:
            return topics
        for entry in recent_history[-4:]:
            if not isinstance(entry, dict):
                continue
            topic = entry.get("topic")
            if isinstance(topic, str) and topic:
                topics.append(topic)
        return topics

    def _extract_primary_emotion(self, emotion_payload: Dict[str, Any] | None) -> str:
        if not emotion_payload:
            return "neutral"
        primary = emotion_payload.get("primary_emotions")
        if isinstance(primary, list) and primary:
            candidate = primary[0]
            if isinstance(candidate, str):
                return _normalise_emotion_label(candidate)
        if isinstance(emotion_payload.get("emotion"), str):
            return _normalise_emotion_label(str(emotion_payload["emotion"]))
        return "neutral"

    def _extract_intensity(self, emotion_payload: Dict[str, Any] | None) -> float:
        if not emotion_payload:
            return 0.5
        raw = emotion_payload.get("intensity")
        if isinstance(raw, (float, int)):
            return max(0.0, min(1.0, float(raw)))
        return 0.5

    def _extract_push_intensity(self, consent_profile: Dict[str, Any] | None) -> str:
        if not consent_profile:
            return "medium"
        raw = consent_profile.get("push_intensity")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lower()
        return "medium"

    def _apply_emotion_bias(self, scores: Dict[str, float], emotion_label: str, text: str) -> None:
        if emotion_label in NEGATIVE_EMOTIONS:
            scores["悩み・気持ち整理"] += 1.7
            if any(keyword in text for keyword in TOPIC_LIBRARY["体調・生活リズム"]["keywords"]):
                scores["体調・生活リズム"] += 1.2
        elif emotion_label in POSITIVE_EMOTIONS:
            scores["最近のできごと"] += 1.0
            scores["趣味・好きなもの"] += 0.8
        elif emotion_label in SURPRISED_EMOTIONS:
            scores["最近のできごと"] += 1.2

    def _apply_mood_bias(self, scores: Dict[str, float], mood_state: str | None) -> None:
        if mood_state == "心配":
            scores["悩み・気持ち整理"] += 0.8
            scores["体調・生活リズム"] += 0.4
        elif mood_state == "陽気":
            scores["最近のできごと"] += 0.5
            scores["趣味・好きなもの"] += 0.5
        elif mood_state == "哲学":
            scores["将来・目標"] += 0.7
        elif mood_state == "いたずら":
            scores["軽い雑談"] += 0.4
        elif mood_state == "穏やか":
            scores["最近のできごと"] += 0.2

    def _pick_topic(
        self,
        scores: Dict[str, float],
        matches_by_topic: Dict[str, List[str]],
        recent_topics: List[str],
        continuity_marker: bool,
    ) -> str:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ordered:
            return "軽い雑談"

        fallback = "軽い雑談"
        last_topic = recent_topics[-1] if recent_topics else None

        if ordered[0][1] <= 0.0:
            if continuity_marker and last_topic:
                return last_topic
            return fallback

        selected_topic = ordered[0][0]
        if not continuity_marker and last_topic and selected_topic == last_topic:
            repeated_recently = recent_topics[-2:] == [last_topic, last_topic]
            has_explicit_match = bool(matches_by_topic.get(selected_topic))
            if repeated_recently and not has_explicit_match:
                for candidate, score in ordered[1:]:
                    if score >= ordered[0][1] - 0.8:
                        return candidate

        return selected_topic

    def _resolve_continuity(self, selected_topic: str, last_topic: str | None, continuity_marker: bool) -> str:
        if selected_topic == last_topic and continuity_marker:
            return "継続"
        if selected_topic == last_topic:
            return "深掘り"
        if last_topic:
            return "話題転換"
        return "導入"

    def _resolve_intent(
        self,
        emotion_label: str,
        continuity: str,
        push_intensity: str,
        quiet_hours: bool,
        asks_advice: bool,
        asks_question: bool,
    ) -> str:
        if quiet_hours and emotion_label in NEGATIVE_EMOTIONS:
            return "静かにそばで受け止める"
        if emotion_label in NEGATIVE_EMOTIONS and asks_advice:
            return "まず共感してから小さく整理を手伝う" if push_intensity == "soft" else "共感してから小さく整理を手伝う"
        if emotion_label in NEGATIVE_EMOTIONS:
            return "まず受け止めて安心できる返事をする"
        if emotion_label in POSITIVE_EMOTIONS:
            return "一緒によろこびの温度を上げる"
        if asks_advice:
            if push_intensity == "soft":
                return "押しつけず選択肢をそっと置く"
            return "必要なら小さく提案する"
        if continuity == "継続":
            return "前の流れのまま並んで話す"
        if asks_question:
            return "答えつつ自然につなぐ"
        return "雑談として気楽に受け止める"

    def _resolve_follow_up_style(
        self,
        emotion_label: str,
        intensity: float,
        continuity: str,
        push_intensity: str,
        quiet_hours: bool,
        sensitive_mode: bool,
        asks_advice: bool,
        asks_question: bool,
    ) -> str:
        if sensitive_mode:
            return "追加質問はせず、境界を尊重する"
        if quiet_hours:
            return "質問で締めず、静かに余白を残す"
        if emotion_label in NEGATIVE_EMOTIONS and intensity >= 0.65 and not asks_advice and not asks_question:
            return "質問せず受け止めを優先する"
        if push_intensity == "soft" and not asks_advice and not asks_question:
            return "基本は質問せず、ひとこと添えて余白を残す"
        if asks_advice:
            return "最初は質問せず、小さな選択肢を1つ置く"
        if asks_question:
            return "答えたあと、必要なら軽い問いを1つだけ添える"
        if continuity in {"継続", "深掘り"}:
            return "質問より相づちと所感でつなぐ"
        return "質問で広げず、ひとこと添えて会話を続ける"

    def _resolve_mood_hint(
        self,
        emotion_label: str,
        continuity: str,
        mood_state: str | None,
        quiet_hours: bool,
    ) -> str:
        if quiet_hours:
            return "夜間モードとして静かで低刺激なトーンを保つ"
        if mood_state == "心配":
            return "慎重に安心感を優先する"
        if mood_state == "陽気":
            return "少し明るめに親しみを出す"
        if mood_state == "哲学":
            return "やや内省的で落ち着いたトーンにする"
        if emotion_label in NEGATIVE_EMOTIONS:
            return "決めつけず、落ち着いて寄り添う"
        if emotion_label in POSITIVE_EMOTIONS:
            return "少し明るめに温度感を合わせる"
        if continuity in {"継続", "深掘り"}:
            return "前の文脈を覚えている雰囲気を出す"
        return "親しみやすく軽やかに話す"

    def _build_focus_points(self, topic_family: str, matched_keywords: List[str]) -> List[str]:
        profile = TOPIC_LIBRARY.get(topic_family, {})
        defaults = list(profile.get("focus_points", []))
        leading = [f"ユーザーが触れた「{keyword}」から話を組み立てる" for keyword in matched_keywords[:2]]
        focus_points = leading + defaults
        return focus_points[:3]

    def _build_avoid_patterns(
        self,
        emotion_label: str,
        continuity: str,
        recent_topics: List[str],
        selected_topic: str,
        push_intensity: str,
        quiet_hours: bool,
        sensitive_mode: bool,
    ) -> List[str]:
        avoid_patterns: List[str] = []
        if sensitive_mode:
            avoid_patterns.append("個人特定情報や敏感話題を深追いしない")
        avoid_patterns.extend(
            [
                "二文を超えて長引かせない",
                "質問を詰め込みすぎない",
                "診察や面談のような聞き取り方をしない",
            ]
        )
        if emotion_label in NEGATIVE_EMOTIONS:
            avoid_patterns.append("強い断定や押しつけを避ける")
        if push_intensity == "soft":
            avoid_patterns.append("結論を急がず、提案を押しつけない")
        if quiet_hours:
            avoid_patterns.append("テンションを上げすぎず静かに返す")
        if continuity == "話題転換":
            avoid_patterns.append("前の話題を急に切り捨てた印象を出さない")
        if recent_topics.count(selected_topic) >= 2:
            avoid_patterns.append("同じ切り口を繰り返し押し込まない")
        unique_patterns: List[str] = []
        for pattern in avoid_patterns:
            if pattern not in unique_patterns:
                unique_patterns.append(pattern)
        return unique_patterns[:3]

    def _detect_sensitive_mode(self, text: str, consent_profile: Dict[str, Any] | None) -> bool:
        if any(marker in text for marker in SENSITIVE_MARKERS):
            return True
        if not consent_profile:
            return False
        private_topics = consent_profile.get("private_topics")
        if not isinstance(private_topics, list):
            return False
        for topic in private_topics:
            if not isinstance(topic, str) or not topic:
                continue
            if topic in text:
                return True
            if topic == "個人特定情報" and any(marker in text for marker in SENSITIVE_MARKERS):
                return True
        return False


def _normalise_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def _normalise_emotion_label(label: str) -> str:
    mapping = {
        "喜び": "happy",
        "嬉しい": "happy",
        "悲しみ": "sad",
        "悲しい": "sad",
        "怒り": "angry",
        "驚き": "surprised",
        "恐れ": "fear",
        "不安": "fear",
        "嫌悪": "disgust",
        "信頼": "trust",
        "期待": "anticipation",
        "中立": "neutral",
    }
    normalised = _normalise_text(label)
    return mapping.get(normalised, normalised or "neutral")
