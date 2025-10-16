# Recomate Codex Brief v1（開発AI向け仕様・指示）

> 目的：この文書を GitHub Copilot / Code LLM（以下 Codex）に与え、**Recomate を“相棒AI”へ進化**させるための設計・実装方針と具体タスクを明示する。

---

## 0. North Star（最終像）
- **性別非固定・気まぐれ・多面関係**（相棒/家族/友だち/恋人近似）をブレンドする“私専用”の相棒AI。
- **2D→3D**へ段階進化（Live2D→VRM/Unity）。
- **メモリ透明**（閲覧/編集/固定/忘却/学習停止）と**境界尊重**（夜間モード/プッシュ強度/敏感話題ロック）。
- ローカル優先（ASR/TTS/短文LLMはオンデバイス）、重タスクのみクラウド併用。

---

## 1. 非交渉要件（Non‑Negotiables）
1) **動くデモを常時維持**：朝/昼/夜の儀式フローは常に動作。
2) **プライバシ**：会話ログはローカル保存可能、学習停止・忘却がワンクリック。
3) **互換性**：表情/仕草イベントは抽象化（face/eye/mouth/gesture）し、2D/3Dで共用。
4) **境界**：夜間モード時は提案強度を落とす、敏感話題は自動回避。

---

## 2. アーキテクチャ（High‑Level）
```
[Front] Next.js + Live2D Panel + WebRTC Mic
   │ REST/WebSocket
[API] FastAPI (Gateway)
   ├─ Persona/Mood Service（状態機械）
   ├─ Memory Service（要約・圧縮・検索）
   ├─ Rituals Service（朝/昼/夜）
   ├─ Preference/Consent Service（境界・同意）
   ├─ Album Service（週次アルバム）
   ├─ Style Adapter（好み学習：DPO/PEFT入口）
   └─ LLM Orchestrator（RAG/ツール呼び分け; ローカルLLM優先）
[Data] Postgres（構造化） + Qdrant/FAISS（ベクトル） + S3互換（画像/音声）
[Local] Whisper small/int8, VOICEVOX（TTS）, Ollama(LLM)
```

---

## 3. データモデル（DDL雛形 / 追加）
```sql
-- users
CREATE TABLE users (
  id UUID PRIMARY KEY,
  display_name TEXT NOT NULL,
  timezone TEXT DEFAULT 'Asia/Tokyo',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- episodes: 生ログ
CREATE TABLE episodes (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  ts TIMESTAMPTZ NOT NULL,
  text TEXT NOT NULL,
  mood_user TEXT,
  mood_ai TEXT,
  tags TEXT[] DEFAULT '{}'
);

-- memories: 圧縮メモリ
CREATE TABLE memories (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  summary_md TEXT NOT NULL,
  keywords TEXT[] DEFAULT '{}',
  last_ref TIMESTAMPTZ,
  pinned BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- preferences: 口調/境界/儀式
CREATE TABLE preferences (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  tone FLOAT DEFAULT 0.6,
  humor FLOAT DEFAULT 0.5,
  style_notes JSONB DEFAULT '{}',
  tts_voice TEXT DEFAULT 'voicevox:normal',
  boundaries_json JSONB DEFAULT '{"night_mode":true,"push_intensity":"soft","private_topics":["個人特定情報"]}'
);

-- mood_logs: ムード状態ログ
CREATE TABLE mood_logs (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  ts TIMESTAMPTZ DEFAULT now(),
  state TEXT NOT NULL,
  trigger TEXT,
  weight_map_json JSONB
);

-- rituals: 朝/夜台本
CREATE TABLE rituals (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  morning_yaml TEXT,
  night_yaml TEXT,
  enabled BOOLEAN DEFAULT true
);

-- album_weekly: 週次アルバム
CREATE TABLE album_weekly (
  week_id TEXT,
  user_id UUID REFERENCES users(id),
  highlights_json JSONB,
  wins_json JSONB,
  photos JSONB,
  quote_best TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (week_id, user_id)
);

-- consent_settings: 同意/境界
CREATE TABLE consent_settings (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  night_mode BOOLEAN DEFAULT true,
  push_intensity TEXT DEFAULT 'soft',
  private_topics TEXT[] DEFAULT ARRAY['個人特定情報'],
  learning_paused BOOLEAN DEFAULT false
);

-- agent_state: 利己性4メーター
CREATE TABLE agent_state (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  curiosity FLOAT DEFAULT 0.3,
  rest FLOAT DEFAULT 0.5,
  orderliness FLOAT DEFAULT 0.6,
  closeness FLOAT DEFAULT 0.5,
  last_request_ts TIMESTAMPTZ
);

-- agent_requests: AIからのお願いログ
CREATE TABLE agent_requests (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  kind TEXT NOT NULL,           -- 'memory_cleanup' | 'album_asset' | 'quiet_mode' | 'topic_taste'
  payload JSONB,
  ts TIMESTAMPTZ DEFAULT now(),
  accepted BOOLEAN
);
```

---

## 4. API（必須エンドポイント雛形）
### Chat / Mood / Rituals
- `POST /chat` → {message} → {reply, mood, events[]}
- `POST /mood/transition` → {trigger} → {state, weights}
- `GET /rituals/morning` → {script, events}
- `GET /rituals/night` → {script, events}

### Memory / Album
- `POST /memory/commit` → {episode_id} → {memory_id}
- `GET /memory/search?q=...` → {memories[]}
- `POST /album/weekly/generate` → {week_id?} → {album_url}

### Preference / Consent
- `GET /consent` / `PATCH /consent` → 境界・同意設定の取得/更新
- `POST /preferences/feedback` → {like, tone_delta, length_delta, metaphor_delta}

### Agent “利己性”
- `POST /agent/request` → AIのお願いを1件生成（クールダウン/境界チェック込み）
- `POST /agent/ack` → {request_id, accepted, reason?}

**Live2Dイベント例**
```json
{"event":"face","value":"smile_soft"}
{"event":"eye","value":"wink"}
{"event":"mouth","value":"open_wide"}
```

---

## 5. ローカルLLM／音声I/O接続
- **LLM**：Ollama 優先（例: `qwen2.5:7b-instruct`, `llama3.1-swallow:8b`）。
- **ASR**：Whisper small/int8 ローカル。
- **TTS**：VOICEVOX または COEIROINK（HTTP API）。
- **方針**：短文はローカル、長文や高度推論はクラウドへフォールバック（Feature‑flag）。

---

## 6. 実装タスク（M0→M1）
### M0（今期：2〜4週間）
- [ ] DDL 適用（上記）
- [ ] `/rituals/morning` `/rituals/night` 実装（ムード反映台本 + Live2Dイベント）
- [ ] メモリ書き戻し `/memory/commit` と検索 `/memory/search`
- [ ] 週次アルバム `/album/weekly/generate`
- [ ] 同意パネル `/consent` GET/PATCH
- [ ] フロント：Live2Dパネル、メモリ透明UI、朝/夜ビュー
- [ ] ユニットテスト：境界違反時のフォールバック、メモリ往復精度

### M1（+1〜3ヶ月）
- [ ] ムード状態機械（穏やか/陽気/ツン/いたずら/哲学/心配 + 乱数）
- [ ] “利己性” 4メーター + `/agent/request` `/agent/ack`
- [ ] 好み学習：👍/👎からスタイル変調（長さ/比喩/敬語）
- [ ] 擬似3D（視線/頷き）

---

## 7. Codex向けプロンプト（例）
**/docs/codex_prompt.md** に保存推奨。
```md
あなたは RecoMate の開発AIです。以下を厳守して実装してください：
- 設計は docs/ の "Recomate Codex Brief v1" に従う。
- まずは API: /rituals/morning, /rituals/night, /memory/commit, /album/weekly/generate を実装。
- DB は PostgreSQL、マイグレーションは Alembic。エラーハンドリングと型付けを徹底。
- Live2D イベントは {event, value} を配列で返す。未知値は禁止。
- テストは pytest。境界違反ケースを最優先。
- コードは docstring と型ヒントを必ず付与。
```

---

## 8. コーディング規約
- Python: Ruff + Black、mypy strict
- フロント: TypeScript strict、ESLint + Prettier
- Commits: Conventional Commits（例: `feat(rituals): add morning endpoint`）

---

## 9. 受け入れ基準（Acceptance）
- 朝/夜フローが E2E で通る（UIでセリフと表情が同期）。
- メモリ透明UIで閲覧/編集/固定/忘却が機能。
- 週次アルバムが生成・再訪可能。
- 夜間モード時、提案強度が soft に落ちることをテストで保証。

---

## 10. 既知のリスクと対策
- 依存/押し付け: プッシュ強度の既定=soft、ヘルスチェック週1。
- 人格ブレ: ムード乱数を±0.15、核価値は固定、回帰テスト必須。
- 2D→3D移行: イベント語彙の固定（face/eye/mouth/gesture）。

---

### 付録A：朝/夜スクリプト（短縮版/日本語）
```json
{
  "morning": {
    "穏やか": "おはよう。水一杯から始めよっか。今日の一歩は？",
    "陽気":   "おはよー！昨日の続き、光ってたよ。5分だけ振り返ろ？",
    "哲学":   "今日のテーマは『小さい選択が未来を折る』。ひとつだけ選ぼう。"
  },
  "night": {
    "穏やか": "3行だけ今日を貸して。私が要約するね。",
    "ツン":   "未完は明日の証拠。歯磨き→整頓→おやすみ。",
    "心配":   "眠り浅そう？予定を柔らかく組み直そう。"
  }
}
```

### 付録B：Live2D イベント辞書
- face: `smile_soft|smile_big|neutral_tsun|mischief|think|worry`
- eye:  `blink_normal|blink_fast|half|wink|up_left|down_right`
- mouth:`a_i_u|open_wide|small|hmm|grin`

---

> v1: このブリーフはスプリントごとに更新。次版で OpenAPI(Swagger) と Alembic マイグレーションの自動生成スクリプトを添付する。

