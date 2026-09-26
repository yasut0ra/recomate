"""Chat orchestration engine for RecoMate.

Owns the per-turn pipeline: emotion analysis, runtime context, conversation
planning with bandit-assisted topic selection, LLM generation with fallback,
reward scoring, and persistence. All request-scoped state lives in local
variables or per-user sessions, so the engine is safe to call from FastAPI's
threadpool without cross-request leakage.
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from openai import OpenAI

from .db.session import get_session
from .emotion_analyzer import EmotionAnalyzer
from .services.chat_payloads import build_chat_history_entry
from .services.consent import get_consent_setting
from .services.conversation_planner import ConversationPlan, ConversationPlanner
from .services.episodes import build_episode_tags, build_recent_episode_context, record_episode
from .services.memory import build_memory_context, promote_episode_to_memory_if_relevant
from .services.mood import get_recent_moods
from .services.preferences import apply_preference_feedback, get_preference_profile
from .services.rewarding import blend_turn_reward, calculate_response_reward
from .services.text_cleanup import clean_assistant_response
from .services.users import resolve_local_user
from .topic_bandit import BanditSelection, TopicBandit
from .turn_analyzer import EMOTION_LABELS, TurnAnalyzer, expression_payload

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are RecoMate, a personal Japanese companion AI. "
    "Reply in natural, warm Japanese (ja-JP), stay emotionally attuned, and avoid sounding pushy, generic, or clinical. "
    "Sound like a close companion, not a doctor, counselor, interviewer, or coach. "
    "Start by acknowledging the user's feeling or situation, then add one connective detail, shared observation, or gentle next step. "
    "Prefer reflection and companionship over repeated questioning, and do not end with a question unless the user clearly asked for help or clarification. "
    "Keep the reply within two short sentences and 120 Japanese characters or fewer."
)

DEFAULT_USER_KEY = "local"
MAX_SESSION_HISTORY = 50
PROMPT_HISTORY_LIMIT = 3
# A reply arriving later than this is a new conversation, not a reaction.
IMPLICIT_FEEDBACK_WINDOW_SECONDS = 30 * 60

BANDIT_STATE_ENV = 'RECOMATE_BANDIT_STATE_PATH'
DEFAULT_BANDIT_STATE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'bandit_state.json'

FALLBACK_PATTERNS: Dict[str, List[str]] = {
    'happy': [
        "それはうれしいね。こっちまで少し明るくなるよ。",
        "いい流れだね。その余韻、しばらく味わっていたくなる。",
        "それはにやけるやつだね。大事にしたくなる感じがある。",
    ],
    'sad': [
        "それはしんどかったね。今は無理に整えなくて大丈夫だよ。",
        "話してくれてありがとう。その重さはちゃんと重かったと思う。",
        "ちゃんとつらかったよね。ここでは少し力を抜いていて。",
    ],
    'angry': [
        "それは腹が立つよね。その引っかかりは軽く流せないやつだ。",
        "その怒りは自然だと思う。すぐ整えなくても大丈夫。",
        "かなりもやっとしたよね。いったんそのまま受け止めたい。",
    ],
    'surprised': [
        "それはびっくりするね。少し心が追いつかない感じもありそう。",
        "急な展開だったんだね。しばらく頭の中で反芻しそうだ。",
        "思ってない方向に動いたんだね。余韻が残るのも自然だよ。",
    ],
}

DEFAULT_FALLBACK_RESPONSES = [
    "うまく言葉をまとめきれなかったけど、ちゃんとそばにいたいと思ってる。",
    "少し考えこんじゃったけど、急がず同じ景色を見ていたい。",
    "いったん落ち着いて受け止めたいな。今は無理に整理しなくて大丈夫だよ。",
]

RESPONSE_GUIDELINES = [
    "1文目で感情や状況を短く受け止める。",
    "2文目は会話プランに沿って所感・共感・小さな提案のいずれかを自然に添える。",
    "相棒として返し、診察・面談・カウンセリングの聞き取りのように進めない。",
    "ユーザーが明確に質問や相談をしていない限り、質問で締めない。",
    "原因追及や過度な深掘りを避け、少し余白を残す。",
    "話題ラベルをそのまま言わず、自然な会話として返す。",
    "直近の会話文脈があれば、それを踏まえて自然に続ける。",
    "関連する記憶があっても、不自然に引用せず会話に溶かす。",
    "好みの口調は反映するが、説明的なメタ発言はしない。",
]


# The reply and the face to show while saying it come from one generation
# call, so the assistant's emotion needs no separate analysis request.
REPLY_RESPONSE_FORMAT: Dict[str, Any] = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'companion_reply',
        'strict': True,
        'schema': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['reply', 'expression'],
            'properties': {
                'reply': {'type': 'string'},
                'expression': {'type': 'string', 'enum': list(EMOTION_LABELS)},
            },
        },
    },
}


@dataclass
class GeneratedReply:
    """Reply text plus the expression the model chose, if it gave a valid one."""

    text: str
    expression: Optional[str] = None


def parse_generated_reply(content: str) -> GeneratedReply:
    """Read the structured reply; tolerate plain text from non-conforming models."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        data = None
    if isinstance(data, dict) and isinstance(data.get('reply'), str):
        expression = data.get('expression')
        return GeneratedReply(
            text=clean_assistant_response(data['reply']),
            expression=expression if expression in EMOTION_LABELS else None,
        )
    return GeneratedReply(text=clean_assistant_response(content or ''))


@dataclass
class ChatTurnResult:
    """Everything a caller needs to build a chat response payload."""

    response: str
    user_emotion: Optional[Dict[str, Any]]
    assistant_emotion: Optional[Dict[str, Any]]
    reward: Optional[float]
    turn_metadata: Dict[str, Any]
    history: List[Dict[str, Any]]
    used_fallback: bool = False


class UnknownTurnError(LookupError):
    """Raised when feedback targets a turn this process does not know."""


@dataclass
class _TurnLearning:
    """Bandit bookkeeping for one turn until the user's reaction is known.

    The bandit is updated once the next user message arrives (implicit
    engagement) and again on explicit 👍/👎, always with the context vector
    captured at selection time.
    """

    selection: BanditSelection
    response_reward: float
    user_text: str
    response_text: str
    created_at: float
    learnable: bool
    resolved: bool = False
    feedback: Optional[bool] = None


@dataclass
class _UserSession:
    """In-memory per-user conversation state."""

    history: deque = field(default_factory=lambda: deque(maxlen=MAX_SESSION_HISTORY))
    turns: 'OrderedDict[str, _TurnLearning]' = field(default_factory=OrderedDict)
    lock: threading.Lock = field(default_factory=threading.Lock)


class ChatEngine:
    def __init__(self) -> None:
        load_dotenv()
        self._default_api_key = os.getenv('OPENAI_API_KEY')
        self._default_client = self._create_client(self._default_api_key)
        self.system_prompt = os.getenv('OPENAI_SYSTEM_PROMPT', SYSTEM_PROMPT)
        self.chat_model = (os.getenv('OPENAI_CHAT_MODEL') or '').strip() or 'gpt-4.1-mini'
        self.chat_fallback_model = (os.getenv('OPENAI_FALLBACK_CHAT_MODEL') or '').strip() or 'gpt-4o-mini'

        self.emotion_analyzer = EmotionAnalyzer()
        self.turn_analyzer = TurnAnalyzer(self.emotion_analyzer)
        self.conversation_planner = ConversationPlanner()
        self.topics = self.conversation_planner.topic_families
        self.bandit = TopicBandit(self.topics)
        self._bandit_lock = threading.Lock()
        self._bandit_state_path = self._resolve_bandit_state_path()
        self._load_bandit_state()

        self._sessions: Dict[str, _UserSession] = {}
        self._sessions_lock = threading.Lock()
        self._context_degraded_logged = False

    # ------------------------------------------------------------------
    # Clients
    # ------------------------------------------------------------------
    @property
    def llm_configured(self) -> bool:
        return self._default_client is not None

    def _create_client(self, api_key: Optional[str]) -> Optional[OpenAI]:
        if not api_key:
            logger.warning("OpenAI API key is not configured; LLM features will use fallback responses.")
            return None
        try:
            return OpenAI(api_key=api_key)
        except Exception as exc:
            logger.error("Failed to initialise OpenAI client: %s", exc)
            return None

    def _resolve_client(self, api_key: Optional[str]) -> Optional[OpenAI]:
        """Return a client for this request without mutating shared state."""
        if not api_key or api_key == self._default_api_key:
            return self._default_client
        try:
            return OpenAI(api_key=api_key)
        except Exception as exc:
            logger.error("Failed to initialise request-scoped OpenAI client: %s", exc)
            return self._default_client

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    def _session_key(self, user_id: Optional[UUID]) -> str:
        return str(user_id) if user_id else DEFAULT_USER_KEY

    def _session_for(self, user_id: Optional[UUID], create: bool = True) -> Optional[_UserSession]:
        key = self._session_key(user_id)
        with self._sessions_lock:
            session = self._sessions.get(key)
            if session is None and create:
                session = _UserSession()
                self._sessions[key] = session
            return session

    def get_serialised_history(self, user_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        session = self._session_for(user_id, create=False)
        if session is None:
            return []
        with session.lock:
            return list(session.history)

    # ------------------------------------------------------------------
    # Emotion helpers
    # ------------------------------------------------------------------
    def emotion_label(self, emotion_payload: Optional[Dict[str, Any]]) -> str:
        if not emotion_payload:
            return 'neutral'
        primary = emotion_payload.get('primary_emotions')
        if isinstance(primary, list) and primary:
            candidate = primary[0]
            if isinstance(candidate, str) and candidate:
                return candidate.lower()
        return 'neutral'

    def analyze_emotion_label(self, text: str, api_key: Optional[str] = None) -> str:
        return self.emotion_label(self.turn_analyzer.analyze_text(self._resolve_client(api_key), text))

    # ------------------------------------------------------------------
    # Topic stats
    # ------------------------------------------------------------------
    def topic_summary(self) -> Dict[str, Any]:
        with self._bandit_lock:
            return self.bandit.get_summary()

    # ------------------------------------------------------------------
    # Bandit learning & persistence
    # ------------------------------------------------------------------
    def _resolve_bandit_state_path(self) -> Optional[Path]:
        raw = os.getenv(BANDIT_STATE_ENV)
        if raw is None:
            return DEFAULT_BANDIT_STATE_PATH
        raw = raw.strip()
        if not raw or raw.lower() in {'off', 'none', 'false', '0'}:
            return None
        return Path(raw).expanduser()

    def _load_bandit_state(self) -> None:
        path = self._bandit_state_path
        if path is None or not path.exists():
            return
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
            restored = self.bandit.load_state(state)
            logger.info('Restored topic bandit state for %d topics from %s', restored, path)
        except Exception as exc:
            logger.warning('Failed to load topic bandit state from %s: %s', path, exc)

    def _save_bandit_state_locked(self) -> None:
        """Persist bandit parameters; caller must hold ``_bandit_lock``."""
        path = self._bandit_state_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(path.name + '.tmp')
            tmp_path.write_text(json.dumps(self.bandit.to_state()), encoding='utf-8')
            os.replace(tmp_path, path)
        except OSError as exc:
            logger.warning('Failed to save topic bandit state to %s: %s', path, exc)

    def _learn(self, learning: _TurnLearning, reward: float) -> None:
        with self._bandit_lock:
            self.bandit.update(learning.selection.topic_idx, reward, context=learning.selection.context)
            self._save_bandit_state_locked()

    def _turn_awaiting_reaction(self, session: _UserSession) -> Optional[_TurnLearning]:
        """The previous turn, if it still needs an implicit reaction reward."""
        with session.lock:
            learning = next(reversed(session.turns.values()), None)
        if learning is None or learning.resolved or not learning.learnable:
            return None
        return learning

    def _resolve_previous_turn(
        self,
        session: _UserSession,
        learning: _TurnLearning,
        engagement: Optional[float],
    ) -> None:
        """Reward the previous turn's topic by how the user just reacted.

        ``engagement`` is None when the reply came too late to count as a
        reaction; the turn then learns from its reply quality alone.
        """
        with session.lock:
            if learning.resolved:  # 👍/👎 arrived in the meantime
                return
            learning.resolved = True
        if engagement is None:
            reward = learning.response_reward
        else:
            reward = blend_turn_reward(learning.response_reward, engagement)
        self._learn(learning, reward)

    def _sync_feedback_to_profile(self, user_id: Optional[UUID], like: bool) -> bool:
        """Mirror feedback into stored preferences; False if learning is paused."""
        session = None
        try:
            session = get_session()
            user = resolve_local_user(session, user_id)
            if get_consent_setting(session, user.id).learning_paused:
                return False
            apply_preference_feedback(session, user.id, like=like)
        except Exception as exc:
            logger.debug('Preference feedback not persisted: %s', exc)
        finally:
            if session is not None:
                session.close()
        return True

    def apply_feedback(self, turn_id: str, like: bool, user_id: Optional[UUID] = None) -> Dict[str, Any]:
        """Apply explicit 👍/👎 on a turn to the topic bandit and preferences."""
        session = self._session_for(user_id, create=False)
        if session is None:
            raise UnknownTurnError(turn_id)
        with session.lock:
            learning = session.turns.get(turn_id)
            if learning is None:
                raise UnknownTurnError(turn_id)
            already_rated = learning.feedback is not None
            if not already_rated:
                learning.feedback = like
                learning.resolved = True

        result: Dict[str, Any] = {
            'turn_id': turn_id,
            'topic': learning.selection.topic,
            'applied': False,
            'reward': None,
            'reason': None,
        }
        if already_rated:
            result['reason'] = 'already_rated'
        elif not learning.learnable:
            result['reason'] = 'not_learnable'
        elif not self._sync_feedback_to_profile(user_id, like):
            result['reason'] = 'learning_paused'
        else:
            reward = 1.0 if like else 0.0
            self._learn(learning, reward)
            result.update(applied=True, reward=reward)
        return result

    # ------------------------------------------------------------------
    # Runtime context
    # ------------------------------------------------------------------
    def _resolve_local_hour(self, timezone_name: Optional[str]) -> int:
        resolved_timezone = timezone_name or 'Asia/Tokyo'
        try:
            return datetime.now(ZoneInfo(resolved_timezone)).hour
        except ZoneInfoNotFoundError:
            logger.debug('Unknown timezone %s; falling back to Asia/Tokyo', resolved_timezone)
        except Exception:
            logger.debug('Failed to resolve local hour for timezone %s', resolved_timezone, exc_info=True)
        return datetime.now(ZoneInfo('Asia/Tokyo')).hour

    def _default_runtime_context(self, user_id: Optional[UUID]) -> Dict[str, Any]:
        return {
            'user_id': str(user_id) if user_id else None,
            'display_name': 'Local User',
            'timezone': 'Asia/Tokyo',
            'local_hour': self._resolve_local_hour('Asia/Tokyo'),
            'mood_state': '穏やか',
            'consent': {
                'night_mode': True,
                'push_intensity': 'medium',
                'private_topics': ['個人特定情報'],
                'learning_paused': False,
            },
            'preferences': {
                'tone': 0.6,
                'humor': 0.5,
                'style_notes': {},
                'style_summary': {
                    'tone_style': '親しみやすく自然体',
                    'humor_style': '必要なときだけ軽くユーモアを混ぜる',
                    'length_style': '短く収める',
                    'metaphor_style': '比喩は必要なときだけ軽く使う',
                    'formality_style': 'フラットで自然な口調',
                },
                'tts_voice': 'voicevox:normal',
            },
            'recent_episode_context': [],
            'memory_context': [],
        }

    def _build_runtime_context(self, user_id: Optional[UUID], current_text: str = '') -> Dict[str, Any]:
        session = None
        try:
            session = get_session()
            user = resolve_local_user(session, user_id)
            mood_state, _ = get_recent_moods(session, user.id, limit=5)
            consent = get_consent_setting(session, user.id)
            preferences = get_preference_profile(session, user.id)
            recent_episode_context = build_recent_episode_context(session, user.id, query=current_text, limit=3)
            memory_context = build_memory_context(session, user.id, query=current_text, limit=3)
            timezone_name = getattr(user, 'timezone', None) or 'Asia/Tokyo'
            self._context_degraded_logged = False
            return {
                'user_id': str(user.id),
                'display_name': user.display_name,
                'timezone': timezone_name,
                'local_hour': self._resolve_local_hour(timezone_name),
                'mood_state': mood_state,
                'consent': {
                    'night_mode': bool(consent.night_mode),
                    'push_intensity': consent.push_intensity,
                    'private_topics': list(consent.private_topics or []),
                    'learning_paused': bool(consent.learning_paused),
                },
                'preferences': preferences,
                'recent_episode_context': recent_episode_context,
                'memory_context': memory_context,
            }
        except Exception as exc:
            if not self._context_degraded_logged:
                logger.warning(
                    'Database context unavailable; chat will run without memory/preferences: %s', exc
                )
                self._context_degraded_logged = True
            else:
                logger.debug('Runtime context fallback (database still unavailable): %s', exc)
            return self._default_runtime_context(user_id)
        finally:
            if session is not None:
                session.close()

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------
    def _build_message_history(
        self,
        session_pairs: List[Dict[str, Any]],
        persistent_history: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, str]]:
        history_messages: List[Dict[str, str]] = []
        for entry in session_pairs[-PROMPT_HISTORY_LIMIT:]:
            if not isinstance(entry, dict):
                continue
            user_text = entry.get('user_input')
            assistant_text = entry.get('response')
            if user_text:
                history_messages.append({'role': 'user', 'content': str(user_text)})
            if assistant_text:
                history_messages.append({'role': 'assistant', 'content': str(assistant_text)})
        if history_messages:
            return history_messages

        for entry in (persistent_history or [])[-PROMPT_HISTORY_LIMIT:]:
            if not isinstance(entry, dict):
                continue
            user_text = entry.get('user_text')
            assistant_text = entry.get('assistant_text')
            if user_text:
                history_messages.append({'role': 'user', 'content': str(user_text)})
            if assistant_text:
                history_messages.append({'role': 'assistant', 'content': str(assistant_text)})
        return history_messages

    def _prepare_user_prompt(
        self,
        user_text: str,
        plan: ConversationPlan,
        emotion_payload: Dict[str, Any],
        runtime_context: Dict[str, Any],
    ) -> str:
        payload = {
            'user_input': user_text,
            'conversation_plan': plan.to_prompt_payload(),
            'detected_emotion': emotion_payload,
            'runtime_context': {
                'display_name': runtime_context.get('display_name'),
                'mood_state': runtime_context.get('mood_state'),
                'timezone': runtime_context.get('timezone'),
                'local_hour': runtime_context.get('local_hour'),
                'preferences': runtime_context.get('preferences'),
                'recent_episode_context': runtime_context.get('recent_episode_context'),
                'memory_context': runtime_context.get('memory_context'),
            },
            'response_guidelines': RESPONSE_GUIDELINES,
        }
        payload_text = json.dumps(payload, ensure_ascii=False, default=str)
        return (
            'Generate one natural Japanese companion reply for RecoMate. '
            'Use the conversation plan to decide tone, continuity, and whether to ask a follow-up. '
            'Return JSON: `reply` is the reply text only; `expression` is the face RecoMate shows '
            'while saying it (happy, sad, angry, surprised, or neutral).\n'
            + payload_text
        )

    # ------------------------------------------------------------------
    # LLM invocation
    # ------------------------------------------------------------------
    def _model_chain(self) -> List[str]:
        models = [self.chat_model, self.chat_fallback_model]
        return [model for index, model in enumerate(models) if model and model not in models[:index]]

    def _call_language_model(self, client: OpenAI, messages: List[Dict[str, str]]) -> GeneratedReply:
        if not messages:
            raise ValueError('No messages provided to the language model')
        last_error: Optional[Exception] = None
        for model in self._model_chain():
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format=REPLY_RESPONSE_FORMAT,
                )
                reply = parse_generated_reply(completion.choices[0].message.content or '')
                if reply.text:
                    return reply
                logger.warning('Model %s returned an empty response', model)
            except Exception as exc:
                last_error = exc
                logger.warning('Chat completion failed on model %s: %s', model, exc)
        if last_error is not None:
            raise last_error
        return GeneratedReply(text='')

    def _fallback_response(self, emotion: str) -> str:
        patterns = FALLBACK_PATTERNS.get(emotion) or DEFAULT_FALLBACK_RESPONSES
        return clean_assistant_response(random.choice(patterns))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist_turn(
        self,
        *,
        user_text: str,
        response_text: str,
        emotion: str,
        emotion_payload: Optional[Dict[str, Any]],
        runtime_context: Dict[str, Any],
        topic_family: Optional[str],
        allow_memory_promotion: bool,
    ) -> Dict[str, Any]:
        raw_user_id = runtime_context.get('user_id')
        if not isinstance(raw_user_id, str) or not raw_user_id.strip():
            return {}
        try:
            user_id = UUID(raw_user_id)
        except ValueError:
            logger.debug('Invalid runtime_context user_id: %s', raw_user_id)
            return {}

        session = None
        try:
            session = get_session()
            user = resolve_local_user(session, user_id)
            mood_state = runtime_context.get('mood_state')
            consent = runtime_context.get('consent') or {}
            tags = build_episode_tags(
                topic_family=topic_family,
                emotion_label=emotion,
                mood_state=mood_state if isinstance(mood_state, str) else None,
            )
            episode = record_episode(
                session,
                user_id=user.id,
                user_text=user_text,
                assistant_text=response_text,
                mood_user=emotion,
                mood_ai=mood_state if isinstance(mood_state, str) else None,
                tags=tags,
            )
            memory = None
            if allow_memory_promotion:
                memory = promote_episode_to_memory_if_relevant(
                    session,
                    episode,
                    topic_family=topic_family,
                    emotion_payload=emotion_payload,
                    learning_paused=bool(consent.get('learning_paused')),
                )
            if memory is not None and 'auto_memory' not in (episode.tags or []):
                episode.tags = list(episode.tags or []) + ['auto_memory']
                session.add(episode)
                session.commit()
                session.refresh(episode)
            return {
                'episode_id': str(episode.id),
                'memory_id': str(memory.id) if memory is not None else None,
                'topic': topic_family,
                'user_id': str(user.id),
            }
        except Exception as exc:
            logger.debug('Failed to persist chat turn: %s', exc, exc_info=True)
            return {}
        finally:
            if session is not None:
                session.close()

    # ------------------------------------------------------------------
    # Main turn pipeline
    # ------------------------------------------------------------------
    def handle_turn(
        self,
        text: str,
        user_id: Optional[UUID] = None,
        api_key: Optional[str] = None,
    ) -> ChatTurnResult:
        client = self._resolve_client(api_key)
        runtime_context = self._build_runtime_context(user_id, current_text=text)
        session = self._session_for(user_id)
        assert session is not None

        consent = runtime_context.get('consent') or {}
        learning_allowed = not bool(consent.get('learning_paused'))

        previous_turn = self._turn_awaiting_reaction(session) if learning_allowed else None
        judge_reaction = (
            previous_turn is not None
            and time.time() - previous_turn.created_at <= IMPLICIT_FEEDBACK_WINDOW_SECONDS
        )
        analysis = self.turn_analyzer.analyze_turn(
            client,
            user_text=text,
            previous_user_text=previous_turn.user_text if judge_reaction else None,
            previous_reply=previous_turn.response_text if judge_reaction else None,
        )
        emotion_payload = analysis.emotion
        emotion = self.emotion_label(emotion_payload)
        if previous_turn is not None:
            self._resolve_previous_turn(
                session,
                previous_turn,
                analysis.reaction_score if judge_reaction else None,
            )

        with session.lock:
            session_pairs = list(session.history)

        persisted_history = runtime_context.get('recent_episode_context')
        if not isinstance(persisted_history, list):
            persisted_history = []
        # Session entries carry their topic in true turn order; persisted
        # episodes are relevance-ranked, so only use them after a restart.
        recent_history = session_pairs[-4:] if session_pairs else list(persisted_history)[-4:]

        bandit_features: Dict[str, Any] = {
            'user_input': text,
            'context_text': text,
            'emotion': emotion_payload or {},
        }
        selection: Optional[BanditSelection] = None

        def bandit_selector(candidates: List[Tuple[str, float]]) -> Optional[str]:
            nonlocal selection
            features = dict(bandit_features, heuristic_scores=dict(candidates))
            with self._bandit_lock:
                selection = self.bandit.select_with_context([topic for topic, _ in candidates], features)
            return selection.topic if selection is not None else None

        plan = self.conversation_planner.plan(
            user_text=text,
            emotion_payload=emotion_payload,
            recent_history=recent_history,
            mood_state=runtime_context.get('mood_state'),
            consent_profile=runtime_context.get('consent'),
            local_hour=runtime_context.get('local_hour'),
            topic_selector=bandit_selector,
        )
        if selection is None or selection.topic != plan.topic_family:
            features = dict(bandit_features, heuristic_scores=plan.topic_scores)
            with self._bandit_lock:
                selection = self.bandit.record_topic_selection(plan.topic_family, features)

        messages: List[Dict[str, str]] = [{'role': 'system', 'content': self.system_prompt}]
        messages.extend(self._build_message_history(session_pairs, persisted_history))
        messages.append({'role': 'user', 'content': self._prepare_user_prompt(text, plan, emotion_payload, runtime_context)})

        used_fallback = False
        generated = GeneratedReply(text='')
        if client is None:
            used_fallback = True
        else:
            try:
                generated = self._call_language_model(client, messages)
            except Exception as exc:
                logger.error('LLM response generation failed: %s', exc)
                used_fallback = True
        response_text = generated.text
        if not response_text:
            used_fallback = True
            response_text = self._fallback_response(emotion)

        if not used_fallback and generated.expression:
            assistant_emotion = expression_payload(generated.expression)
        else:
            # Canned text, or a model that ignored the schema: keywords suffice.
            assistant_emotion = self.turn_analyzer.analyze_text(None, response_text)
        reward = calculate_response_reward(
            user_text=text,
            response_text=response_text,
            user_emotion=emotion_payload,
            assistant_emotion=assistant_emotion,
        )

        # Fallback responses are canned text; letting them train the bandit
        # would reward topics for words the model never chose. Learning is
        # deferred until the user reacts (next message or 👍/👎).
        learnable = not used_fallback and learning_allowed
        if learnable:
            with self._bandit_lock:
                self.bandit.add_to_history(text, response_text, plan.topic_family, reward=reward)

        turn_id = uuid4().hex
        with session.lock:
            if selection is not None:
                session.turns[turn_id] = _TurnLearning(
                    selection=selection,
                    response_reward=reward,
                    user_text=text,
                    response_text=response_text,
                    created_at=time.time(),
                    learnable=learnable,
                )
                while len(session.turns) > MAX_SESSION_HISTORY:
                    session.turns.popitem(last=False)
            session.history.append(
                build_chat_history_entry(
                    user_input=text,
                    response=response_text,
                    user_emotion=emotion_payload,
                    assistant_emotion=assistant_emotion,
                    reward=reward,
                    timestamp=datetime.now().timestamp(),
                    turn_id=turn_id,
                    topic=plan.topic_family,
                )
            )
            history = list(session.history)

        persisted = self._persist_turn(
            user_text=text,
            response_text=response_text,
            emotion=emotion,
            emotion_payload=emotion_payload,
            runtime_context=runtime_context,
            topic_family=plan.topic_family,
            allow_memory_promotion=not used_fallback,
        )
        turn_metadata = {
            **persisted,
            'turn_id': turn_id,
            'topic': plan.topic_family,
            'feedback_enabled': learnable,
        }
        if analysis.reaction is not None:
            turn_metadata['previous_turn_reaction'] = analysis.reaction

        return ChatTurnResult(
            response=response_text,
            user_emotion=emotion_payload,
            assistant_emotion=assistant_emotion,
            reward=reward,
            turn_metadata=turn_metadata,
            history=history,
            used_fallback=used_fallback,
        )
