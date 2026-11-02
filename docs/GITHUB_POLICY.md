# GitHub運用方針 v1.0

## 初期設定
- 最初は **private**。公開ライセンス未選択であるため、公開前に権利と利用条件を決める。
- リポ名候補: `motionpack`。最初は個人所有を想定。説明: `Editable, engine-agnostic animated visual asset format and runtime (experimental)`。
- デフォルトは`main`。公開後のmainは動作確認済みの統合ブランチとする。
- ブランチ命名: `feat/<issue>-...`, `fix/<issue>-...`, `docs/<issue>-...`, `test/<issue>-...`。
- 変更はPRを原則とする。差分を小さく、Issueへのリンクをつける。
- マージ: squash mergeを基本。必要なら履歴維持の理由を明示。
- `main`へのforce push、削除、直接pushを禁止する設定を推奨。

## Rulesets／Branch protection
- Pull Request必須、必要なstatus check必須（チェックの実名が登録された後に有効化）。
- セキュリティ/互換性に関係するPRは独立した監査記録を必要とする。
- **AIレビューはGitHubの人間レビュー承認ではない**。人間1人のみの場合、実行不能な「他者承認必須」を無理に設定しない。運用上の人間マージ承認＋必須CIチェックで補完する。
- 権限、プラン、保護機能の利用可否はリポ作成後に実際の設定画面で確認。

## GitHub Actions
- `permissions: contents: read`など最小権限。PRからの未信頼入力に秘密情報を渡さない。
- 依存Actionはワークフロー依存関係ロックファイル、または検証済み完全SHAで固定。可変tagのみの参照を避ける。
- 標準CI（必須候補）: バリデータ、Python単体テスト、Node単体テスト、サンプルパッケージ化。
- 追加チェック: セキュリティ異常入力、コンフォーマンス、Visual smoke、性能比較（重い場合は夜間または手動）。
- CIが実際に1度成功してからそのjob名を必須チェックに設定する。存在しないチェックを先に必須化して作業を止めない。

## Issueラベル案
`type:feature`, `type:bug`, `type:security`, `type:spec`, `type:docs`, `area:runtime`, `area:asset`, `area:motion`, `area:format`, `area:tool`, `priority:p0`, `priority:p1`, `priority:p2`, `status:blocked`。

## リリース
- 0.xは実験版。形式の変更と互換性を明示する。可能な範囲でSemVer（Semantic Versioning／意味的バージョン管理）を適用。
- リリースの承認は人間メンテナーのみ。配布に含む画像の権利確認、ライセンス選定、セキュリティ監査、互換性・性能資料を添付。
- v1.0公開まで、独立したゲームエンジンアダプタや完全自動可動化の提供を約束しない。