# ChatGPT + GitHub 開発引き継ぎ

更新日: 2026-11-14  
対象リポジトリ: [708san/motionpack](https://github.com/708san/motionpack)  
この文書は作業手順と現状の引き継ぎ用です。公開形式の仕様を追加・変更する決定ではありません。

## 先に読む文書

新しいChatGPTセッションでは、必ずGitHub上の最新mainから次を読み、Issueと照合してください。

- [AGENTS.md](../AGENTS.md)
- [開発ガバナンス](DEVELOPMENT_GOVERNANCE_V1.md)
- [役割と委譲](AGENT_ROLES.md)
- [GitHub運用](GITHUB_POLICY.md)
- [品質方針](QUALITY_POLICY.md)
- [セキュリティ方針](SECURITY_POLICY.md)
- [統治されたロードマップ](ROADMAP_GOVERNED.md)
- 公開形式を変える作業では [FORMAT_SPEC.md](FORMAT_SPEC.md)

GitHub mainの最新状態を唯一の基準にします。2026-11-14に確認したmainは `d186235c18639147fcbf30d3f8f7b24c7cdddcaa` でした。ローカルの古いremote-tracking refをmainだと思い込まず、作業ブランチをGitHubの最新mainから作ってください。既存のローカルブランチ、未コミット作業、stashをreset、clean、checkout、popしてはいけません。

## ChatGPTとGitHubの役割

- **GitHub**をIssue、ソース、ブランチ、PR、必須チェック、レビュー、生成artifactの正本にします。
- **ChatGPT**は調査、変更案、コード作成、テスト結果の読解、画像・動画の実物確認を行います。
- **ユーザー/maintainer**は製品仕様の未決事項と作品の見た目を判断します。ChatGPTのQAやCI成功だけで人間の作品承認を代替しません。

GitHub連携を使う場合も、変更はIssueに紐づく専用ブランチとPRに載せます。mainへ直接commitしません。重要な仕様選択、作品の見た目、セキュリティ境界を推測で決めず、選択肢と影響を短く示して回答を待ちます。無関係な作業は続けて構いません。

## 開発ループ

1. 最新main、対象Issue、関連する仕様・品質・セキュリティ文書、コード、テストを読む。
2. 非自明な変更はIssue/PR本文に目的、範囲、受入条件、テスト、rollbackを記録する。Issueがある場合はそこへ結び付ける。
3. GitHub上の最新mainから作業ブランチを切る。担当ファイル群ごとに責任者を一人にし、レビュー・QAは編集担当と分ける。
4. 不具合なら再現テストを先に追加し、実装後に関連テストとREADME/CIで指定された一式を実行する。実行したコマンドと結果をPRに記す。実行していない検査をpassと書かない。
5. PRの差分、全必須CI、必要な独立レビューを確認する。現行の主要workflowは MotionPack checks、governance checks、isolated archive reader、browser visual regression、ZIP reader fuzz。実行結果はPR head SHAに結び付けて確認する。
6. ユーザーが実物を確認する必要がある変更では、CIの緑だけで終えず、画像や再生できる動画をPR artifactに含める。ユーザーの指摘をIssue/PRへ記録し、同じPRまたは後続PRで直して再度成果物を作る。
7. 必須ゲートが通り、レビュー指摘が解消し、必要なmaintainer判断がそろった時だけmergeする。リリース、license、重大な仕様判断、作品承認は明示的なmaintainer判断を要する。

## 画像・動きの反復確認

MotionPackの見た目・動きは、静止画の差分だけでは評価できません。今後の代表作品レビューでは次を守ってください。

- PR artifactに状態ごとのPNGに加え、押下から動きの終了まで連続再生できる短い動画（WebM等）を付ける。
- ファイル名でcanvas cropと全画面viewport captureを明確に区別する。viewport画像はPNG寸法も機械検査する。
- 冒頭、中間、終端、復帰を撮影し、画面外へのはみ出し、二重輪郭、急なpose切替、途中の残像、mobileでの大きさを実画像と動画で見る。
- 画像内容をChatGPT側で開けない場合、その制約を明記する。「CI成功」「artifactが存在する」だけで視覚確認済みと言わない。ユーザーにActions runのArtifactsから取得・添付してもらい、実物を確認してから修正する。
- 人間レビュー前の画像をbaselineに昇格しない。ユーザーが採用した状態、artifact/run、viewport、判断、残修正をIssue #122に記録する。物理端末の確認はPlaywright emulationと区別する。

### 次の視覚作業の具体的な引き継ぎ

[Issue #122](https://github.com/708san/motionpack/issues/122)のmaintainerコメントは、PR #144のcandidateを却下しています。140msに目立つ二重輪郭があり、190msにもghostingが残り、squish/returnが一貫した動きに見えません。レビュー対象として提示された `seal-idle-390x844.png` は全画面390×844のviewport画像ではなく、横長のcanvas cropでした。maintainerは全画面での確認に必要な証拠が提示セットにないとして却下しています。実際に確認する画像・動きの詳細は[却下コメント](https://github.com/708san/motionpack/issues/122#issuecomment-6827752668)を参照してください。

したがってPR #144のartifactは承認済み作品やvisual baselineとして使わないでください。新候補では動きを再設計し、正確に命名した全画面画像と再生可能動画を提出します。元のイラストとprovenanceを保持し、出力を直接見てから次の修正を決めてください。

## 2026-11-14時点のプロジェクト状態

| 項目 | 現状 |
|---|---|
| v0.x形式 | v0.1〜v0.4は実験形式。後方互換のfixtureとreaderはあるが、安定規格ではない。 |
| v1.0形式とreader/writer | [Issue #120](https://github.com/708san/motionpack/issues/120)はopen。安定したv1 schema、統合reader/validator、loss-aware writer、read/write roundtripは未完成。manifest-only capability preflightは完全なv1 readerではない。 |
| Raster契約 | PR #173までにPNG/JPEG/WebPの大枠は記録済み。詳細受理規則とfixtureの一部は[Issue #154](https://github.com/708san/motionpack/issues/154)で未決。決定コメントを読んでからformatへ反映する。 |
| Untrusted input security | [Issue #4](https://github.com/708san/motionpack/issues/4)はopen。reader/worker/fuzz/SVG制約は防御層であり、OS sandboxやproduction-safe importの保証ではない。 |
| Artwork/motion | [Issue #122](https://github.com/708san/motionpack/issues/122)はopen。PR #144 candidateはmaintainerに却下された。新しいcandidateでhuman reviewをやり直す。 |
| Release | license、作品・動きの承認、セキュリティ連絡/対応手順、対応環境とperformance gate等が残る。AI authoringはv1.0 core要件ではない。 |

### Issue #154で勝手に決めない raster 細則

- PNGのMUST/SHALLとSHOULDだけの違反の扱い。
- Progressive JPEGのscan間整合、table定義時期、およびmarker状態の細部。
- WebPのVP8L alpha hintの扱い、metadata順序、未知chunk位置。
- v0.xで受理したIHDR-only PNGをv1出力へ移す時のunsupported/repair扱い。

質問と推奨案は[ArchitectのIssueコメント](https://github.com/708san/motionpack/issues/154#issuecomment-6827131928)にあります。回答のない選択を実装やFORMAT_SPECへ持ち込まないでください。すでに決まった大枠を質問し直さず、未決項目だけ扱います。

## 次のChatGPTセッション用プロンプト

> MotionPackの開発をGitHub連携で続けます。まず最新mainから `AGENTS.md`、`docs/CHATGPT_GITHUB_HANDOFF.md` と関連するgovernance/quality/security/spec文書を読み、open Issueとmainの状態を確認してください。ローカルの古いbranch/ref/stashは変更しないでください。  
>   
> Issue #122のPR #144 candidateはmaintainerが却下済みです。過去のartifactを承認済みとして扱わず、Issueの却下コメントに沿ってsquish/return motionとviewport framingを改修してください。実際に動いている短いWebM、canvas cropと区別した390×844全画面capture、寸法・画面内boundsの検査をPR artifactに含め、画像と動画をChatGPT上で実見しながら反復します。画像をこちらで見られない場合は、見たふりをせず、ユーザーにartifactを添付してもらってから評価します。作品の採否はmaintainer判断を待ち、承認前にbaseline化やmergeをしません。  
>   
> Issue #154の未決raster仕様は選択を推測しないでください。まず再現テスト、作業範囲とrollbackを記録し、専用branch/PRで変更、required checksと独立reviewを確認してください。Issue #4やv1.0全体を部分PRで完了扱いしないでください。

## 履歴/状態の扱い

この引き継ぎPRで変更するのは本書だけです。形式仕様、コード、サンプル画像、baselineは変更しません。作業を開始するたびに、GitHub上の最新mainとIssueコメントを読み直し、この文書より新しいmaintainer判断を優先してください。
