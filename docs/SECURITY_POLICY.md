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
- readerは入力pathが通常ファイルを指すことをopen前に確認し、open後もfile descriptorの種別を確認する。stat時の`(st_dev, st_ino)`とopen後の`fstat`を照合し、報告された識別情報が異なる場合は解析・copy前に拒否する。Pythonが識別tupleを返せない場合（device/inodeの欠落・非整数、または0以下のinodeを含む）はopen前にfail-closedで拒否する。ただし、正の`(st_dev, st_ino)`が全filesystemで一意かつ安定とは保証できず、ID再利用や衝突では差し替えを検出できない場合がある。通常ファイルを指すsymlinkは、両確認が同じtargetを示す限り従来どおり受理する。OSが`O_NONBLOCK`を提供する場合は付けて開く。path検査とopenは原子的ではなく、同時に差し替えられるpathでは特殊ファイルをopenしてから拒否する可能性がある。別のregular fileへの差し替えは識別情報が利用可能な環境で検出するが、すべてのpath raceを排除する保証ではない。Pythonの`O_NONBLOCK`はUnix限定であり、このflagがなく、かつFIFO等のブロックする特殊ファイルを扱うOSでは、検査後の差し替えでopenが停止し得る。CIではLinux/macOS/Windowsの限定的なreader動作を確認するが、Windowsを含む全環境でのpath競合対策を保証しない。これは実験的readerの制約であり、攻撃者が変更できるpathの安全な読込保証ではない。
- `tools/archive_reader.py` はentry名・種別・件数・宣言サイズ・圧縮率を検査してから、manifestと参照画像だけを上限付きで読み込む。任意のentryは展開しない。`.png`/`.jpg`/`.jpeg`/`.webp`拡張子のassetに限り、形式別ヘッダーから寸法を事前検査し、既定では辺8192px、1画像またはWebP各フレーム16,000,000画素、PNG/JPEG/WebP参照ラスター合計64,000,000画素をtool上限として拒否する。アニメーションWebPはキャンバス画素に全フレーム面積を加算し、ANMF領域と内側bitstream寸法を検査する。PNG仕様上限の2^31−1 px/edgeは設定にかかわらず拒否する。JPEGのDNLによる後続高さ指定は未対応。画素デコードや完全な画像検証は行わず、別拡張子への内容偽装を独立検出せず、後続デコーダも保護しない。
- ZIP reader、SVG validator、ラスター画像ヘッダーパーサーにAtheris 3.1.0のtest-only coverage-guided fuzz targetを用意し、隔離ラスターdecoderにはAtherisによるblack-box mutation targetを用意する。各targetはPRで15秒、週次・手動で300秒実行する。入力は各64 KiB、各caseは2秒、job全体は25分で制限し、Linux x86-64 / CPython 3.12 wheelをhash pinする。各fuzz targetは許可済みseedだけを受け入れ、seed corpusを最大16ファイル/1 MiBに制限して一時領域へコピーする。GitHub Actionsはread-only権限でsecretを渡さず、crash artifactsを自動公開しない。ヘッダーtargetはdimension parserのみを検査し、decoder targetはPillow workerを別プロセスで呼び出す。decoder targetは辺512px・合計262,144画素、正常/異常PNG・JPEG・WebP seedを使い、Pillowは既存のhash固定済み`requirements-image.txt`からbinary wheelのみインストールする。Atherisは子workerやnative Pillow codecのcoverage feedbackを受け取れないため、このtargetはPillow内部のcoverage-guided探索ではない。通常の画像拒否は入力結果として受け入れるが、worker内部例外・異常終了・不正応答・timeout・worker resource-limit failureはfuzz failureとする。隔離実行はsandboxではなく、有限時間のfuzz campaignも継続的・網羅的な安全性保証ではない。PyPIはAtheris 3.1.0にprovenance attestationを掲載していないため、依存導入時は公式upstreamとApache-2.0ライセンスを確認し、wheel hashを固定する。
- readerの既定上限はツールの運用制限であり、形式全体の互換保証や本番向けセキュリティ保証ではない。`zipfile` の解析前にZIP終端レコードからentry数と中央ディレクトリサイズ（既定2 MiB）を検査する。既定の`read_package()`は`read_package_isolated()`を呼び出し、40 MiBまでの入力snapshot、既定30秒・最大300秒のwall-clock期限、40 MiBの応答上限、worker終了・回収を適用し、ZIP64とマルチディスクZIPを拒否する。WindowsではJob終了確認とworker process waitに共有の5秒budgetを使い、一時ディレクトリの一時的な共有違反・アクセス拒否の再試行に別途最大5秒を使う。停止処理ではstdout reader threadの同期I/Oを`CancelSynchronousIo`で中断しようとするが、すべての同期OS API呼出しをbudget内に確実に止める保証ではない。workerまたはreaderの終了を確認できない場合は読込を失敗させ、一時snapshotをパス付きで保持する。`read_package_in_process()`は明示的な同一プロセス解析APIとして残す。workerは呼出元と同じOS権限を持ち、sandboxではない。snapshotはコピー内容をSHA-256でhashし、同じopen descriptorをもう一度上限付きで読み、byte数とhashが一致することを確認するため、size/file ID/mtimeが維持されたin-place変更も検知する。追加で最大40 MiBを読み、原子的snapshotや同時writerの排除は保証しない。既定メモリ制限はLinuxでworkerごとに512 MiBの仮想アドレス空間、Windowsでworkerごとに512 MiBのコミット済みメモリとJob Object全体で512 MiBのコミット済みメモリ。WindowsのJob-wide上限はworkerとJobに属する子プロセスの合計を制限する。macOSでは全プロセスメモリのハード上限を保証できない。これらはsandboxではなく、ファイル・ネットワーク権限を制限しない。
- `decode_raster_assets_isolated()` は既定で辺8192px、1画像16MP、入力合計64MP、デコード後合計64MP、アセット1件12 MiB、入力合計32 MiBを上限とし、PNG/JPEG/WebP静止画だけをPillow workerでRGBAへ変換する。呼出元はZIP reader等で検査済みの参照asset bytesを渡し、workerにZIP pathや任意entryを開かせない。応答の長さ・形式・寸法・RGBA byte数を親側で再検証する。期限超過、過大出力、異常終了、途中応答は全体を失敗させ、Pillow未導入時にbrowser decoderへfallbackしない。workerの既定メモリ制限はLinuxの512 MiB address-space、Windowsの512 MiB per-process committed memoryと512 MiB job-wide committed memory。WindowsではJob Objectに属するworkerと子プロセスの合計をjob-wide上限で制限する。macOSにハードメモリ制限はない。workerは呼出元と同じOS権限を持ちsandboxではない。workerまたはstdout readerの終了を確認できない場合は、デコード用一時領域をパス付きで保持する。Animated WebPはこのAPIでは拒否し、通常のpreview経路は変更しない。
- 通常の `read_package()` / `read_package_isolated()` は任意の `source/` payloadを展開・返却せず、manifestからruntime assetとして参照される場合は拒否する。明示的な `import_legacy_package()` は検証済みZIP内の全regular-file payloadを既存のentry数・archive bytes・総展開サイズ・圧縮率上限の下で読み、sourceをopaque bytesとしてsnapshotに保持する。sourceのsignatureや内容は検査・解釈しない。isolated応答は40 MiBで上限を設け、超過時は全体を失敗させる。このopt-in readerもOS sandboxではない。いずれのAPIも入力アーカイブ自体を変更しない。
- `source/` 以外の通常entryは、最大512 bytesの展開済みprefixからZIP/gzip/bzip2/xz/7-Zip/RAR/tarの既知signatureを検査し、未参照entryも該当時は拒否する。これは限定的なsignature検査であり、未知variantやpolyglotは識別できない。`source/` はopaqueのまま検査しない。
- packagerはmanifestとその参照assetだけを出力し、未参照ファイルや `source/` を自動同梱しない。runtime assetからの `source/` 参照とローカルproject上のsymlinkを含むpathはvalidatorで拒否する。検証に使った上限付きasset bytesをZIPとpreviewにも使い、検証後のpath再オープンを避ける。dirfd/O_NOFOLLOW対応環境では各path componentを固定したdirectory descriptorの下で開く。他環境ではpathとfile identityを再確認するが、全ての並行directory差替えを防ぐ保証はない。packagerはシリアライズ済みmanifest（asset pathを含む）と同梱対象の参照asset bytesを走査し、PEM秘密鍵ヘッダー、GitHub/Slack/OpenAI token-like value、AWS access-key ID-like valueを検出した場合はカテゴリと「package metadata」またはmanifest順の重複除外済み参照asset列における1始まり位置のみを表示し、pathや検出値は出力しない。既定では警告してbuildを継続し、該当内容をZIPとpreviewに含める。`--fail-on-secret-like` 指定時は検出でbuildを失敗させ、出力作成や既存出力の置換前に停止する。これは既知形式に対する未完全なヒューリスティックであり、画像pixel、変換・符号化済み値、未知形式等は検出せず、誤検知もあり得る。秘密の不在を保証しない。
- SVG検査は現行validatorの限定的な静的サブセット検査を再利用し、要素ごとの属性allowlistを適用する。未知属性は拒否するが、属性値の全SVG文法検証や任意renderer向けの完全な無害化は行わない。DTD・entity宣言・外部参照を拒否し、同一SVG内gradientへの `fill` / `stroke` の `url(#id)` のみ許可する。SVG validatorには上記の短時間Atheris smoke fuzzingを追加済みだが、rendererや画像デコーダの隔離、長時間・継続的なファジングは未実施。

## Browser visual CI
- `.github/workflows/visual-regression.yml` は Playwright 1.65.0 のnpm依存をlockfile/integrity hashで固定し、npm lifecycle scriptsを実行せずに導入する。対応Chromiumを含むUbuntu 24.04コンテナはPlaywrightのバージョンとOCI digestの両方で固定する。Workflowは `contents: read` のみで、checkout credentialsを永続化せず、secretsを渡さない。
- ブラウザ上では preview のHTTP(S)要求を遮断して検査するが、これはrunner全体のegress制限ではない。依存・コンテナ取得にはCI setup時のネットワークが必要であり、Visual Workflow内のPRコードも通常のPR trust boundaryで実行される。
- Artifactには候補スクリーンショットPNG、ブラウザ/時刻メタデータ、性能計測JSONを14日間保存する。Artifactはリポジトリアクセス権を持つ利用者が取得可能な情報として扱い、秘密情報を含めない。
