# v1.0.1 - Patch: Tag Detection Fixes

Three bug fixes, no new features, no workflow changes needed.

---

## What was broken

**`furry with non-furry` and similar compound tags were losing their underscores.**
The natural language detector used a stop word list to distinguish NL prose from tags. That list included common words like `with`, `out`, `from`, `at`, `in`, `on`, `by` - which are also extremely common in Danbooru compound tags. `furry with non-furry`, `tongue out`, `from behind`, `looking at viewer`, `thumbs up`, `bent over` were all being misidentified as natural language and having their spaces preserved rather than converted to underscores. For a node pack built for the furry community this was an embarrassingly visible bug.

**`breasts` was surviving the filter when `no_breasts` appeared earlier in the same tag list.**
The negation guard was scanning the entire input string for negation context. When evaluating a standalone `breasts` tag it found `no` near `breasts` elsewhere in the string and incorrectly decided `breasts` was negated. In a comma-separated tag list, `no_breasts` and `breasts` are two independent instructions with no grammatical relationship to each other.

**`lizardman \(warcraft\)` and similar Danbooru copyright tags were being mangled.**
The tag formatter was doing a blanket space-to-underscore conversion that stripped backslashes, turning `lizardman \(warcraft\)` into malformed output. Backslash-escaped sequences are now protected through the conversion and restored intact.

---

## Who should update

Anyone using the Gender Tag Filter with TIPO output that contains compound tags - which is essentially everyone using this in a furry workflow. The `breasts` fix is particularly important if your tag source ever produces both `no_breasts` and `breasts` as separate tags, which TIPO does.

No changes to node inputs, outputs, or workflow JSON. Drop in the updated files and restart ComfyUI.
