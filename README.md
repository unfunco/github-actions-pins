# GitHub Actions Pins

A repository for tracking pinned GitHub Actions metadata.

The source list lives in `actions.csv`. Each row contains two columns:
`action,ref_override`, leaving `ref_override` empty when no override is needed.

`gh pin` can open an issue titled `Add actions to pin list` with the `pins`
label. The issue workflow validates its `owner/action@ref` entries and opens an
auto-merge pull request that updates both `actions.csv` and `pins.json`.
Action subpaths remain part of the pin key, while metadata resolves against the
root `owner/repo`. Full commit SHA references do not need pin-list entries.

The published `pins.json` file is deployed to
[`https://unfun.co/pins.json`](https://unfun.co/pins.json).

## License

© 2026 [Daniel Morris]\
Made available under the terms of the [MIT License].

[daniel morris]: https://unfun.co
[mit license]: LICENSE.md
