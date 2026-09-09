# construction-pictograms

Excel、施工計画書、作業手順書などで使用する建設作業ピクトグラム集です。

## 収録内容

- SVG：Excelでの配置・拡大縮小用
- PNG：確認・簡易利用用（透過背景）
- YAML：各作品のID・日本語名・分類・備考
- [カタログ](catalog/catalog.md)
- [制作指示書（制作ルールの正本）](docs/pictogram_guidelines.md)

各ピクトグラムは黒一色で、背景は透明です。

## 作品の追加と自動生成

作業ブランチに `svg/<名前>.svg` と `metadata/<名前>.yml` を追加してpushすると、GitHub Actionsが透過PNGとカタログ全体を生成し、同じブランチへ自動コミットします。既存6作品もメタデータへ移行済みです。

生成物の `png/` と `catalog/catalog.md` は手動編集せず、SVGまたはYAMLを修正してください。Actionsの完了後に作業ブランチをpullし、生成結果を確認してPull Requestを作成します。mainへのマージは管理者が行います。

- [メタデータ形式・ローカル生成手順](docs/pictogram_guidelines.md#14-カタログ更新)
- [GitHub運用・自動実行の条件](docs/pictogram_guidelines.md#16-github運用ルール)
- [生成ワークフロー](.github/workflows/build-assets.yml)
