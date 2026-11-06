# セキュリティ方針 v1.0

## 守る対象
- ユーザーの元画像、生成履歴、制作データ、ローカルファイル、PC環境、CI資格情報。
- `.motionpack`およびその中のmanifest・画像・マスク・素材を **未信頼入力** として取り扱う。

## 脅威と最低限の対策
1. **ZIP展開攻撃**: `../`、絶対パス、シンボリックリンク、ZIP bomb、巨大展開・極端なentry数を拒否。展開先境界を実パスで検証。
2. **データ型/数値攻撃**: JSONの巨大ネスト、巨大配列、NaN、Infinity、負の寸法、無効な時間/ループを制限。
3. **画像デコーダ**: 解像度・ピクセル総数・ファイルサイズ・展開後メモリの上限。外部デコーダの既知脆弱性を追う。
4. **実行コード注入**: パッケージ内JavaScript、HTML、任意シェーダー、実行可能コードは初期形式では禁止。SVGを扱う場合もスクリプト・外部参照等を適切に除去/制限し、表示環境を保護。
5. **外部通信・プライバシー**: 初期Runtimeはオフライン、ローカル資産優先。AI制作ツールによる外部送信は利用者の明示指定がない限り禁止。
6. **リソース枯渇**: ネストしたノード・パーティクル数・高負荷エフェクト・無限再帰を制限。再生停止・タイムアウトの仕組み。
7. **依存関係**: ライブラリの権限・ライセンス・供給元・バージョンを検査。CIトークンの最小権限、Actionの厳密固定。
8. **秘密情報**: リポジトリにAPIキー・認証トークン・個人画像をコミットしない。秘密が混入した場合はローテーションと履歴除去を検討。

## セキュリティ上のリリースゲート
- 高/重大の未解決問題がある場合は公開停止（例外は人間が文書で決定）。
- Fuzz（ファジング／不正・ランダム入力の自動検査）と異常サンプルを継続追加。
- 実装者と監査者を分離し、レビュー結果に修正コミットと再テストを対応づける。

## 禁止事項
- 不明なパッケージを権限の高いプロセスで実行しない。
- ブラウザやランタイムのsandboxだけを信頼して検証を省略しない。
- セキュリティ問題を一般公開Issueに詳細開示しない（現在Public。Private vulnerability reporting等の非公開報告経路を整える）。

## 配布前に追加すべきもの
脆弱性連絡窓口、パーサ・画像処理のサンドボックス、公開後の修正・通知手順、依存ソフトウェア一覧。窓口のメールアドレスは未指定なので推測して記載しない。

## 実験的ZIP readerの範囲
- readerは入力pathが通常ファイルを指すことをopen前に確認し、open後もfile descriptorの種別を確認する。OSが`O_NONBLOCK`を提供する場合は付けて開く。path検査とopenは原子的ではなく、同時に差し替えられるpathでは特殊ファイルをopenしてから拒否する可能性がある。Pythonの`O_NONBLOCK`はUnix限定であり、このflagがなく、かつFIFO等のブロックする特殊ファイルを扱うOSでは、検査後の差し替えでopenが停止し得る。CIではLinux/macOS/Windowsの限定的なreader動作を確認するが、Windowsを含む全環境でのpath競合対策を保証しない。これは実験的readerの制約であり、攻撃者が変更できるpathの安全な読込保証ではない。
- `tools/archive_reader.py` はentry名・種別・件数・宣言サイズ・圧縮率を検査してから、manifestと参照画像だけを上限付きで読み込む。任意のentryは展開しない。`.png`/`.jpg`/`.jpeg`/`.webp`拡張子のassetに限り、形式別ヘッダーから寸法を事前検査し、既定では辺8192px、1画像またはWebP各フレーム16,000,000画素、PNG/JPEG/WebP参照ラスター合計64,000,000画素をtool上限として拒否する。アニメーションWebPはキャンバス画素に全フレーム面積を加算し、ANMF領域と内側bitstream寸法を検査する。PNG仕様上限の2^31−1 px/edgeは設定にかかわらず拒否する。JPEGのDNLによる後続高さ指定は未対応。画素デコードや完全な画像検証は行わず、別拡張子への内容偽装を独立検出せず、後続デコーダも保護しない。
- ZIP reader、SVG validator、ラスター画像ヘッダーパーサーにAtheris 3.1.0のtest-only coverage-guided fuzz targetを用意し、それぞれPRでは15秒、週次・手動では300秒実行する。入力は各64 KiB、各caseは2秒、job全体は20分で制限し、Linux x86-64 / CPython 3.12 wheelをhash pinする。各fuzz targetは許可済みseedだけを受け入れ、seed corpusを最大16ファイル/1 MiBに制限して一時領域へコピーする。GitHub Actionsはread-only権限でsecretを渡さず、crash artifactsを自動公開しない。ラスターtargetはheader/dimension parserのみを検査し、画像pixel decoderは実行しない。これは有限時間のfuzz campaignであり、継続的・網羅的な安全性保証ではない。PyPIは当該releaseにprovenance attestationを掲載していないため、依存導入時は公式upstreamとApache-2.0ライセンスを確認し、wheel hashを固定する。
- readerの既定上限はツールの運用制限であり、形式全体の互換保証や本番向けセキュリティ保証ではない。`zipfile` の解析前にZIP終端レコードからentry数と中央ディレクトリサイズ（既定2 MiB）を検査する。既存`read_package()`は呼出元プロセス内で解析する。別APIの`read_package_isolated()`は40 MiBまでの入力snapshot、最大300秒のwall-clock期限、40 MiBの応答上限、worker終了・回収を提供し、ZIP64とマルチディスクZIPを拒否する。既定メモリ制限はLinuxで512 MiBの仮想アドレス空間、Windowsで512 MiBのコミット済みプロセスメモリ。macOSでは全プロセスメモリのハード上限を保証できない。これらはsandboxではなく、ファイル・ネットワーク権限を制限しない。
- 任意の `source/` はメタデータと宣言サイズだけを検査し、展開・解釈しない。readerの戻り値にも含めず、manifestからruntime assetとして参照される場合は拒否する。入力アーカイブ自体は変更しない。
- packagerはmanifestとその参照assetだけを出力し、未参照ファイルや `source/` を自動同梱しない。runtime assetからの `source/` 参照とローカルproject上のsymlinkを含むpathはvalidatorで拒否する。検証に使った上限付きasset bytesをZIPとpreviewにも使い、検証後のpath再オープンを避ける。dirfd/O_NOFOLLOW対応環境では各path componentを固定したdirectory descriptorの下で開く。他環境ではpathとfile identityを再確認するが、全ての並行directory差替えを防ぐ保証はない。packagerはシリアライズ済みmanifest（asset pathを含む）と同梱対象の参照asset bytesを走査し、PEM秘密鍵ヘッダー、GitHub/OpenAI token-like value、AWS access-key ID-like valueを検出した場合はカテゴリと「package metadata」またはmanifest順の重複除外済み参照asset列における1始まり位置のみを表示し、pathや検出値は出力しない。既定では警告してbuildを継続し、該当内容をZIPとpreviewに含める。`--fail-on-secret-like` 指定時は検出でbuildを失敗させ、出力作成や既存出力の置換前に停止する。これは既知形式に対する未完全なヒューリスティックであり、画像pixel、変換・符号化済み値、未知形式等は検出せず、誤検知もあり得る。秘密の不在を保証しない。
- SVG検査は現行validatorの限定的な静的サブセット検査を再利用し、要素ごとの属性allowlistを適用する。未知属性は拒否するが、属性値の全SVG文法検証や任意renderer向けの完全な無害化は行わない。DTD・entity宣言・外部参照を拒否し、同一SVG内gradientへの `fill` / `stroke` の `url(#id)` のみ許可する。SVG validatorには上記の短時間Atheris smoke fuzzingを追加済みだが、rendererや画像デコーダの隔離、長時間・継続的なファジングは未実施。
