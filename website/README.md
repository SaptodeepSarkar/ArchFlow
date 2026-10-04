# Vaani website

A static, dependency-free site. Serve this directory directly; no build command
is required. The typography uses system fonts, and the illustrations are HTML/SVG.

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory website
```

Open http://127.0.0.1:4173. The word-sketch buttons choose deterministic examples;
there is no microphone request, inference, tracking script or network upload.
Core content and navigation work with JavaScript disabled.

The icon mirrors `../brand/vaani-mark.svg`. Shared identity rules live in
`../brand/README.md`. Copy reflects the current development build on `work`,
including unverified physical-device release gates. Update branch/build links
when that implementation is released; do not advertise an unpublished binary.

For a static host such as Vercel, use `website` as the project root, no build
command/framework, and serve its files directly. Pushing a branch does not prove
production deployment: verify the hosting project's branch and resulting URL.
This refresh was reviewed locally; no production deployment was performed.
