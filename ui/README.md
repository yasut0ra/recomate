# recomate UI

`ui/` は recomate の現役フロントエンドです。React + TypeScript + Vite をベースにしつつ、開発中は Electron シェルからも起動できます。

## 主要コマンド

```bash
npm install
npm run dev
npm run dev:web
npm run lint
npm run build
```

- `npm run dev`
  - `npm run dev:desktop` のエイリアスです。
  - Vite と Electron を同時起動します。
  - FastAPI は別途 `http://127.0.0.1:8000` で起動しておく前提です。
- `npm run dev:web`
  - Vite のみ起動します。
- `npm run build`
  - TypeScript ビルドと Vite の本番ビルドを実行します。

## 構成

- `src/App.tsx`
  - 画面全体の合成。
- `src/context/ChatContext.tsx`
  - 会話送信、音声再生、文字起こし、トピック統計の管理。
- `src/context/useChatContext.ts`
  - チャットコンテキスト用フック。
- `src/api/`
  - FastAPI との通信レイヤー。
- `src/components/`
  - 会話 UI と、リチュアル/メモリ/ムード/Agent Request の検証パネル群。

## API 接続先

- デフォルトは `http://127.0.0.1:8000`
- `VITE_API_BASE_URL` で変更可能

## 備考

- `ui/electron-main.js` は現行の簡易 Electron エントリです。
- 旧 Electron エントリは `legacy/electron/main.js` に退避しています。
