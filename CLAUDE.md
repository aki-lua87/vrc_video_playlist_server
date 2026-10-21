# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

VRChat上で同一のURLから異なるYouTube動画を再生するためのサーバーシステム。VRChatワールド向けのYouTube動画APIを提供し、ワールドを更新することなくプレイリスト機能を実現します。

## アーキテクチャ

### コア技術スタック
- **フレームワーク**: AWS Serverless (Lambda + API Gateway)
- **言語**: Python 3.13
- **データベース**: DynamoDB
- **CDN**: CloudFront + S3
- **デプロイ**: Serverless Framework v4 (WSLから mise 経由)

### プロジェクト構造
```
src/
├── lambda/                     # 個別のLambda関数ハンドラー (handler.pyのみ)
│   ├── get_yt_channel/         # チャンネルのn番目の動画
│   ├── get_yt_channel_list/    # チャンネルのタイトルリスト
│   ├── get_yt_playlist*/       # プレイリスト動画・タイトル
│   ├── get_yt_query*/          # 検索ベース動画・タイトル
│   ├── get_yt_*_continuous_play*/ # 連続再生
│   ├── get_ss_video*/          # スプレッドシート(GAS)動画
│   └── post_yt_channel_regist/ # チャンネル登録
└── layers/utils/python/        # 共有ユーティリティ (utilsLayer)
    ├── httputils.py            # リクエスト解析・レスポンス生成・UA判定
    ├── videolist.py            # 動画リストのキャッシュ取得/更新
    ├── channelid.py            # @ハンドル・URL → UC形式チャンネルID
    ├── ddbutils.py             # DynamoDB操作
    └── ytutils.py              # YouTube API・RSS操作
tests/                          # オフラインテスト (AWS/YouTubeアクセス不要)
```

### データフロー
1. **登録**: チャンネルをPOST APIで登録して動画取得を有効化
2. **キャッシュ**: 動画リストをDynamoDBにキャッシュ (`latest_update` で更新単位を判定)
3. **取得**: VRChatがチャンネル/プレイリストID + インデックス (n) で動画リクエスト
4. **配信**: VRCプレイヤーにはYouTube URLへ302リダイレクト

### APIエンドポイント
- `/video/yt/channel/regist` - YouTubeチャンネル登録 (body の channel_id は UCxxxx / @ハンドル / チャンネルURL / 動画URL)
- `/yt/ch/resolve?q=...` - チャンネル指定をUC形式IDに変換 (確認用)
- `/yt/ch/{channel_id}/video?n=X` - チャンネルの特定動画取得
- `/yt/ch/{channel_id}/titles` - チャンネル動画タイトルリスト取得
- `/yt/pl/{playlist_id}/video?n=X` - プレイリストの特定動画取得
- `/yt/search/video?q=query&n=X` - 検索ベース動画取得
- `/ss/video?ssid=gas_id&n=X` - スプレッドシート動画取得

## 開発コマンド

### デプロイ (WSL)
```bash
cp .env.example .env   # 初回のみ。値を埋めて mise trust
mise run deploy        # prod
mise run deploy:dev    # dev
mise run deploy:fn get_yt_channel   # 関数単体
mise run logs get_yt_channel        # 直近30分のログ
```
依存ライブラリは `dockerizePip: true` でLambdaと同じ環境(Docker)でビルドする。WSLホストでビルドするとglibc不一致でimportエラー(502)になる。

### テスト
```bash
python -m unittest discover -s tests
```

## 環境設定

### .env (デプロイ時)
- `API_KEY`: YouTube Data API v3 キー
- `DEPLOY_BUCKET`: Serverlessデプロイ用バケット
- `LAMBDA_IAM`: Lambda関数用IAMロールARN

Lambdaの環境変数 (`VRC_VIDEO_TABLE` / `API_KEY` / `CF_DOMAIN`) は provider.environment で全関数共通。

### DynamoDBスキーマ
複合キーを使用したメインテーブル構造:
- `user_id` (HASH): レコードタイプ識別子 (例: 'yt_channnel_id', 'list_yt_ch')
- `video_id` (RANGE): チャンネルID、プレイリストID、またはクエリ文字列
- 自動レコード削除のためのTTL有効
- `auther` / `yt_channnel_id` などの綴りは既存データ・レスポンス互換のため変更しない

## 重要な実装詳細

### ユーザーエージェント検出 (httputils.client_type)
- Quest: `stagefright` を含むUA → YouTube URLへリダイレクト
- PC: `Accept-Encoding: identity` → YouTube URLへリダイレクト
- その他 (YTTL・StringLoader等): `{"title": ...}` のJSONを返却
- Quest向けのyt-dlpによる直接URL解決は廃止 (PCと同じ処理)

### 更新戦略 (videolist)
- チャンネル・検索: 時間単位更新、プレイリスト: 日単位更新
- YouTube API障害時は古いキャッシュにフォールバック (キャッシュも無ければ nf.mp4)

### チャンネル指定の解決 (channelid)
- 内部・DynamoDBのキーは常にUC形式ID (UCで始まる24文字)
- パスの `{channel_id}` は UCxxxx か @ハンドル (registに渡した値をそのまま使うクライアントのため)
- regist の body は URL も可: `/@` `/channel/` `/user/` `/c/` と動画URL (`watch?v=` `youtu.be` `shorts`)
- 解決方法: @ハンドル=channels.list forHandle、/user/=forUsername、動画=videos.list (各1 unit)、/c/=チャンネルページのcanonicalをスクレイピング
- 結果は `user_id='yt_channel_alias'` に7日キャッシュ (見つからない結果は1時間)。API障害時はキャッシュしない

## 重要な注意事項
- 全Lambda関数は個別パッケージ化 (handler.pyのみ)。共通処理はutilsLayer、外部ライブラリはpythonRequirementsレイヤー
