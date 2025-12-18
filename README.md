# Keki AI - AI動画ナレーションジェネレーター


**🌐 公式サイト: https://keki.ai/**

**🎉 完全無料のオープンソースソフトウェア（OSS）です！**

PDFスライドを日本語音声付きの動画に変換するツールです。VOICEVOXを使用して、選択可能なキャラクターによる対話形式のナレーションを生成できます。

## 🌟 オープンソースだから実現できること

### 💰 完全無料
- **ソースコード公開** - GitHubで全てのコードを公開
- **商用利用可能** - 個人・法人問わず無料で利用可能
- **🆓 改変・再配布完全自由** - **MITライセンス**により、**商用・非商用問わず自由に改変・再配布・二次利用が可能**です。コードの修正、機能追加、独自バージョンの作成など、あらゆる用途で自由にご利用いただけます
- **音声合成も無料** - VOICEVOXは無料で使える日本語音声合成エンジン
- **隠れたコストなし** - サブスクリプションや追加料金は一切不要
- **利用制限なし** - 機能制限や使用回数制限なし

### 🔍 完全な透明性
- ソースコードを確認し、何が行われているか把握できます
- セキュリティ監査や脆弱性チェックが可能
- 不正なデータ収集やバックドアの心配なし

### 🔒 データの完全管理
- 機密情報がクラウドに送信されることなく、自社サーバーで処理
- 社内ポリシーに完全準拠した運用が可能
- GDPRやその他のプライバシー規制に対応

### 🛠️ カスタマイズ自由
- 自社の要件に合わせて機能追加・改変が可能
- 独自のワークフローやビジネスロジックの実装
- 既存システムとのシームレスな統合

※ AIによる対話生成機能を使用する場合のみ、各AIプロバイダーのAPIキーが必要です（OpenAI、Claude等）
※ LLM（大規模言語モデル）の使用料金は、各プロバイダーの従量課金に基づきユーザー負担となります

## 🎬 PDFから動画へ変換

### 設定可能な項目
- 🎭 **キャラクター選択**: 四国めたん、ずんだもん、春日部つむぎなど18種類から選択
- 💬 **会話スタイル**: 友達風、ビジネスライク、ラジオ風、解説風など
- ⏱️ **目標時間**: 動画の長さを分単位で指定

### 編集機能
- 🤖 **AI再生成**: スライドごとに対話内容をAIに再生成させる
- ✍️ **手動編集**: テキストエリアで直接対話内容を修正
- 🎭 **スピーカー変更**: 発言者（四国めたん/ずんだもん）を切り替え
- 🔄 **リアルタイム反映**: 編集内容が即座に動画生成に反映

## ユースケース

### 🏢 コーポレート／サービス紹介動画
自社のビジネスモデルや新製品の魅力を、ナレーション付きの短い映像でわかりやすく伝えます。営業資料やウェブサイトへの組み込みで、訴求力がアップします。

### 📱 プロモーション＆キャンペーン動画
商品ローンチやセール情報を、TikTokやYouTube Shorts向けのショート動画として自動生成。縦型フォーマットにも対応し、SNSでの拡散を後押しします。

### 📊 財務レポート／マーケット分析の動画化
決算説明資料や市場調査レポートを、視覚的に訴えるアニメーション動画に変換。専門知識がない人にも要点が伝わりやすくなります。

### 🎓 社内研修・オンボーディング教材
マニュアルや研修スライドをベースにした解説動画を生成。新入社員向けやリモート研修での理解促進に役立ちます。

### 💻 技術勉強会のプレゼン動画
セミナー用スライドやハンドアウトの骨子を取りまとめ、ポイント解説付きの動画に。参加者への事前配布資料や復習コンテンツとして活用できます。

### 🔧 OSSハンズオンチュートリアル
オープンソースライブラリやツールのインストール手順から基本操作までを、実演イメージの動画でガイド。ドキュメントだけでは難しい操作感をサポートします。

### 📰 雑学・ニュースダイジェスト動画
気になるトピックや最新ニュースをサクッと解説。短い尺で要点をまとめたコンテンツを自動生成し、視聴者の興味を引きつけます。

## 特徴

### 現在の機能
- 📄 PDFページをスライド画像に変換
- 🎙️ VOICEVOXを使用した高品質な日本語音声合成（18種類のキャラクター）
- 💬 複数のAIプロバイダーによる自然な対話形式のナレーション自動生成
  - OpenAI (GPT-5.2, GPT-5.1, GPT-5, GPT-4o, GPT-4, GPT-3.5)
  - Claude (Anthropic)
  - Google Gemini
  - DeepSeek
- 🎬 スライドと音声を同期した動画生成
- ✏️ Webアプリで対話内容を編集・再生成可能
- ⚙️ Web UIでのLLMプロバイダー選択とモデル設定（APIキーはブラウザ側で管理）
- 📊 CSV形式での対話スクリプトのインポート/エクスポート
- ✅ 👥 マルチユーザー対応のAPIキー管理（ブラウザのlocalStorageに保存・サーバー側には保存しない）
- ✅ 🧯 エラー内容の詳細表示と動画生成の再試行ボタン（失敗したジョブをワンクリックで再実行）

### 開発中の機能 🚧
- 🗄️ データベース統合（SQLite/PostgreSQL）による永続化
- 🧪 包括的なテストスイート（ユニットテスト、統合テスト）
- 📝 改善されたエラーハンドリングとログシステム（構造化ログ、トレースID など）
- 🔒 セキュリティ強化（CORS設定、入力検証の追加、APIレート制限）
- 📈 パフォーマンス最適化と監視機能
- 🎞️ BGM・トランジションなどの簡易アニメーション効果（動画の見た目改善）
- 📂 プロジェクト履歴画面（過去ジョブの再編集・再生成、動画の再ダウンロード）

### 計画中の機能 🔮
- 👥 ユーザー認証と権限管理システム
- 📦 バッチ処理（複数PDFファイルの一括変換）
- 🌍 多言語サポートの拡張
- 🎨 キャラクター立ち絵＋吹き出し付きレイアウト（簡易アバターによる解説）
- ⏱️ スライドごとの重要度設定と自動時間調整
- 🧩 プレゼン／研修／セミナー向けテンプレートプリセット
- 🔄 APIバージョン管理
- ⚡ CI/CDパイプラインの自動化

## インストール

### 1. リポジトリのクローン
```bash
git clone https://github.com/nomadcafe/keki.git
cd keki
```

### 2. 起動（推奨：手動起動）

**セキュリティ上の理由から、手動での起動を推奨します。**

```bash
# 1. .envファイルを手動で作成（.env.exampleを確認してから）
cp .env.example .env

# 2. .envファイルを編集して必要な設定を行う（APIキーなど）
# エディタで.envファイルを開き、必要な値を設定してください

# 3. Docker Composeで起動
docker-compose up -d

# ログを確認する場合
docker-compose logs -f
```

**重要：セキュリティのベストプラクティス**
- `.env`ファイルには機密情報（APIキーなど）が含まれるため、必ず手動で確認・編集してください
- `.env`ファイルをGitにコミットしないでください（既に.gitignoreに含まれています）
- 本番環境では、環境変数を直接設定するか、シークレット管理サービスを使用してください


### Docker Compose設定の詳細

`docker-compose.yml`では以下の3つのサービスを定義しています：

#### 1. **voicevox** サービス（音声合成エンジン）
```yaml
voicevox:
  image: voicevox/voicevox_engine:cpu-ubuntu20.04-latest
  ports:
    - "50021:50021"
```
- **役割**: 日本語テキストを音声に変換する音声合成エンジン
- **イメージ**: VOICEVOXの公式DockerイメージのCPU版を使用
- **ポート**: 50021番ポートでAPIを提供
- **特徴**: GPU不要で動作し、18種類のキャラクターボイスが利用可能

#### 2. **api** サービス（バックエンドAPI）
```yaml
api:
  build:
    context: .
    dockerfile: Dockerfile.api
  ports:
    - "8002:8000"
  volumes:
    - ./uploads:/app/uploads
    - ./slides:/app/slides
    - ./audio:/app/audio
    - ./output:/app/output
    - ./data:/app/data
  environment:
    - VOICEVOX_URL=http://voicevox:50021
  depends_on:
    - voicevox
```
- **役割**: PDFの処理、対話生成、音声生成、動画作成を行うAPIサーバー
- **ポート**: ホストの8002番ポートをコンテナの8000番にマッピング
- **ボリューム**: 
  - `uploads`: アップロードされたPDFファイル
  - `slides`: PDFから変換されたスライド画像
  - `audio`: 生成された音声ファイル
  - `output`: 最終的な動画ファイル
  - `data`: 対話スクリプトのJSONファイル
- **環境変数**: VOICEVOXへの接続URLを設定（サービス間通信）
- **依存関係**: voicevoxサービスが起動してから起動

#### 3. **frontend** サービス（Webアプリ）
```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  ports:
    - "3000:3000"
  environment:
    - PUBLIC_API_URL=http://localhost:8002
  depends_on:
    - api
```
- **役割**: ユーザーインターフェースを提供するWebアプリケーション
- **ポート**: 3000番ポートでWebアプリにアクセス
- **環境変数**: APIサーバーのURLを設定
- **依存関係**: apiサービスが起動してから起動

#### ネットワーク設定
```yaml
networks:
  default:
    name: app-network
```
- 全サービスが同一ネットワーク（app-network）に接続
- サービス間はサービス名で通信可能（例：`http://voicevox:50021`）

これで以下のサービスが起動します：
- Webアプリ: http://localhost:3000
- API: http://localhost:8002
- VOICEVOX: http://localhost:50021

### Docker Composeの基本操作

```bash
# サービスの起動（バックグラウンド実行）
docker-compose up -d

# サービスの停止
docker-compose down

# サービスの再起動（コード変更を反映）
docker-compose restart api

# ログの確認
docker-compose logs -f api      # APIのログをリアルタイム表示
docker-compose logs frontend    # フロントエンドのログ表示
docker-compose logs voicevox    # VOICEVOXのログ表示

# コンテナの状態確認
docker-compose ps

# 再ビルド（Dockerfileを変更した場合）
docker-compose build --no-cache api
docker-compose up -d

# 完全なクリーンアップ（データも削除）
docker-compose down -v
```

### 4. ローカル環境での起動（代替方法）

#### Backend (API)の起動
```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload
```

#### Frontend (Webアプリ)の起動
```bash
cd frontend
npm install
npm run dev
```

#### VOICEVOXの起動
VOICEVOXを別途ダウンロードして起動してください。

## 使用方法

### Webアプリでの使い方（推奨）

1. ブラウザで `http://localhost:3000` にアクセス
2. 初回起動時は設定画面（`http://localhost:3000/settings`）でLLMプロバイダーのAPIキーを設定
3. PDFファイルをアップロード
4. 以下の設定を行う：
   - 目安時間（分）
   - スピーカー1（デフォルト：四国めたん）
   - スピーカー2（デフォルト：ずんだもん）
   - 会話スタイル（友達風、ビジネス風など）
5. 「動画を生成」ボタンをクリック
6. 生成された対話を確認・編集
7. 動画をダウンロード

### スクリプトでの使い方（上級者向け）

1. PDFファイルを`uploads/`ディレクトリに配置
2. VOICEVOXを起動（デフォルト: http://localhost:50021）
3. 対話と音声を生成：
   ```bash
   python scripts/generate_audio.py
   ```
4. 動画を生成：
   ```bash
   python scripts/create_video.py
   ```

## 必要な環境

- Python 3.8+
- VOICEVOX（音声合成エンジン）
- OpenAI APIキー（対話生成用）
- Node.js 18+（Webアプリ用）

### 推奨：Docker環境での実行

Dockerを使用すれば、VOICEVOXやNode.jsの環境構築が不要になります。

## プロジェクト構成

```
keki/
├── api/                    # FastAPI Backend
│   ├── core/              # コア機能
│   │   ├── dialogue_generator.py    # LLMによる対話生成（GPT-5.2等対応）
│   │   ├── dialogue_refiner.py      # 対話内容の調整
│   │   ├── audio_generator.py       # VOICEVOX音声生成
│   │   ├── video_creator.py         # 動画作成
│   │   └── pdf_processor.py         # PDF処理
│   ├── routers/           # APIルーター
│   │   ├── jobs.py        # ジョブ管理
│   │   ├── auth.py        # 認証
│   │   ├── settings.py    # 設定
│   │   └── speakers.py    # 音声
│   └── main.py            # FastAPIアプリケーション
├── frontend/              # SvelteKit Frontend
│   ├── src/              
│   │   └── routes/       # Webアプリ画面
│   └── package.json      
├── src/                   # 共通ライブラリ
│   ├── dialogue_video_creator.py    # 高品質動画作成
│   └── voicevox_generator.py        # VOICEVOX制御
├── docker-compose.yml     # Docker設定
├── uploads/              # アップロードされたPDF
├── output/               # 生成された動画
├── slides/               # 抽出されたスライド画像
└── audio/                # 生成された音声ファイル
```

## API仕様

### 主要エンドポイント

#### ジョブ管理
- **POST /api/jobs/upload** - PDFアップロードとジョブ作成
  - Parameters: file, target_duration, speaker1_id, speaker2_id, conversation_style
- **GET /api/jobs/{job_id}/status** - ジョブ進行状況確認
- **GET /api/jobs** - 全ジョブリスト取得
- **DELETE /api/jobs/{job_id}** - ジョブ削除

#### 対話・動画生成
- **POST /api/jobs/{job_id}/generate-dialogue** - 対話スクリプト生成
- **PUT /api/jobs/{job_id}/dialogue** - 対話スクリプト編集
- **POST /api/jobs/{job_id}/generate-video** - ワンクリック動画生成
- **GET /api/jobs/{job_id}/download** - 完成動画ダウンロード

#### 音声・スピーカー
- **GET /api/speakers** - VOICEVOX話者一覧取得
- **POST /api/voice-sample** - 音声サンプル生成

#### データ管理
- **GET /api/jobs/{job_id}/dialogue** - 対話スクリプト取得
- **GET /api/jobs/{job_id}/dialogue/csv** - CSV形式でダウンロード
- **POST /api/jobs/{job_id}/dialogue/csv** - CSVからインポート
- **GET /api/jobs/{job_id}/slides** - スライド画像リスト
- **GET /api/jobs/{job_id}/metadata** - ジョブメタデータ

#### LLM設定
- **GET /api/settings/providers** - LLMプロバイダー一覧と状態
- **POST /api/settings/provider** - プロバイダー設定保存
- **DELETE /api/settings/provider/{provider}** - プロバイダー削除
- **POST /api/settings/test-key** - APIキー有効性テスト
- **PUT /api/settings** - 全般設定更新

### スクリプト機能

#### 音声生成スクリプト
```bash
# 表現豊かな音声生成（抑揚1.2、フェードアウト付き）
python scripts/generate_audio.py

# カタカナ変換音声生成
python scripts/generate_katakana_audio.py

# シンプル音声生成
python scripts/generate_katakana_audio_simple.py
```

#### 動画作成スクリプト
```bash
# 高品質動画作成（フェードアウト処理、最適化された間隔）
python scripts/create_video.py

# テスト動画作成
python scripts/create_katakana_test_video.py
```

### VOICEVOX話者ID
- 2: 四国めたん（ノーマル）
- 3: ずんだもん（ノーマル）
- 8: 春日部つむぎ（ノーマル）
- 10: 波音リツ（ノーマル）
- 13: 青山龍星（ノーマル）
- 16: 九州そら（ノーマル）
- 20: もち子さん（ノーマル）

## 主な機能

### 対話生成機能
- 最新のLLM（GPT-5.2等）を使用した自然な対話生成
- スライドの重要度を自動判定し、時間配分を最適化
- スライド間の文脈を保持した一貫性のある対話


### 音声品質
- 抑揚を1.2に設定して表現豊かな音声を実現
- 各音声の終わりに50msのフェードアウトを適用
- 話者間の間隔を0.8秒に最適化
- キャラクターごとの話速調整

## 🐛 トラブルシューティング

問題が解決しない場合は、[GitHub Issues](https://github.com/nomadcafe/keki/issues)で報告してください。可能な限り詳細な情報（エラーメッセージ、環境情報、再現手順など）を含めてください。

## 出力

- 生成された動画ファイル（output/ディレクトリ）
- スライド画像（slides/ディレクトリ）
- 音声ファイル（audio/ディレクトリ）

## 🗺️ 更新履歴

最新の変更内容については [更新履歴](https://keki.ai/changelog) をご覧ください。

## 🤝 貢献

Keki AIへの貢献を歓迎します！バグ報告や機能提案は [GitHub Issues](https://github.com/nomadcafe/keki/issues) でお願いします。

## 📚 ドキュメント

- [README.md](README.md) - プロジェクト概要とクイックスタート

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。

### VOICEVOX音声利用時の注意事項

生成された音声を使用する際は、以下の規約を遵守してください：

- **クレジット表記が必要です**
  - 動画や作品で音声を使用する場合、必ず「VOICEVOX:キャラクター名」の表記を行ってください
  - 例：「VOICEVOX:ずんだもん」「VOICEVOX:四国めたん」

- **各キャラクターの利用規約を遵守してください**
  - キャラクターごとに個別の利用規約があります
  - 公序良俗に反する利用は禁止されています
  - 詳細は各キャラクターの公式ページをご確認ください

## 🌟 スターとフォーク

このプロジェクトが役に立ったら、⭐スターを付けていただけると嬉しいです！また、フォークして独自の改善を加えることも歓迎します。
