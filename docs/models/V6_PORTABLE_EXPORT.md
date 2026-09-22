# V6 portable formatter export

V6's current trained candidate is the bounded hashed source-grounded tagger,
not the rejected free-form Qwen formatter. Its 208,539 parameters predict
closed token, punctuation, structure, speech-act, and emoji labels; rendering
remains deterministic.

`tools/export_v6_tagger.py` converts the local PyTorch checkpoint into a
little-endian float32 package with a versioned header and tensor manifest. The
format contains no transcript or user data and is suitable for native Linux
and Android loaders without Python or PyTorch.

Export an existing local candidate:

```sh
python3 tools/export_v6_tagger.py \
  --model /home/saptodeep/.local/share/vaani/formatter-v6/tagger-augmented-grouped-20/model.pt \
  --config /home/saptodeep/.local/share/vaani/formatter-v6/tagger-augmented-grouped-20/config.json \
  --out /tmp/vaani-v6-tagger/model.v6tg
```

The export is an interoperability milestone, not a promotion decision. The
current independent challenge result is 0/18 learned-plan exact for the saved
tagger family; the deterministic closed-cue fallback remains required. Native
loaders must reproduce the Python logits/labels and pass the same challenge,
protected-span, memory, and latency gates before either platform selects this
package by default.

## Runtime placement

Linux looks for `~/.local/share/vaani/cleanup/model.v6tg` (or the equivalent
`$XDG_DATA_HOME/vaani/cleanup/model.v6tg`). Android looks for
`files/models/formatter/model.v6tg`. If the file is absent or fails parsing or
source-preservation checks, both platforms retain their existing safe fallback.
